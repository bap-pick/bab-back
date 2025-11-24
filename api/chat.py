import re
import json
import datetime
import pytz
import logging
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status,  WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session, joinedload
from pydantic import BaseModel
from core.db import get_db
from core.models import ChatRoom, ChatMessage, ChatroomMember, User
from core.firebase_auth import verify_firebase_token, get_user_uid_from_websocket_token
from core.websocket_manager import ConnectionManager, get_connection_manager
from api.chain import build_conversation_history, generate_llm_response, get_initial_chat_message, recommend_restaurants, is_initial_recommendation_request


router = APIRouter(prefix="/chat", tags=["chat"])
logger = logging.getLogger(__name__)

# KST 시간대 정의 (UTC+9)
KST = pytz.timezone('Asia/Seoul') 
UTC = pytz.timezone('UTC')

# 요청 모델
class MessageRequest(BaseModel):
    room_id: int
    message: str

class ChatRoomCreateRequest(BaseModel):
    name: Optional[str] = None
    is_group: bool = False
    invited_uids: Optional[List[str]] = None # 초대한 사용자 목록


# 가장 최근에 선택한 메뉴명 추출
def get_latest_selected_menu(db: Session, room_id: int) -> Optional[str]:
    chatroom = db.query(ChatRoom).filter(ChatRoom.id == room_id).first()
    
    if chatroom:
        return chatroom.selected_menu
    return None

# 메뉴 선택 시 위치 선택 메시지 출력 
def process_menu_selection(db: Session, chatroom: ChatRoom, llm_output: str) -> Optional[dict]:
    menu_name_match = re.search(r"\[MENU_SELECTED:(.+?)\]", llm_output)
    if not menu_name_match:
        return None
    
    selected_menu = menu_name_match.group(1).strip()

    chatroom.selected_menu = selected_menu
    db.add(chatroom)
    db.commit()
    
    # 위치 선택 프롬프트 메시지 생성
    assistant_reply = f"그러면 {selected_menu} 먹으러 갈 식당 추천해줄게! 위치는 어디로 할까?\n\n 원하는 위치를 입력하거나 아래 버튼 중 하나를 골라줘!"
    message_type = "location_select"
    
    # DB 저장 (extra_data는 JSON 문자열로 변환하여 저장)
    assistant_message = ChatMessage(
        room_id=chatroom.id,
        sender_id="assistant",
        role="assistant",
        content=assistant_reply,
        message_type=message_type, 
        timestamp=datetime.datetime.utcnow(),
    )
    db.add(assistant_message)
    db.commit()
    db.refresh(assistant_message)
        
    chatroom.last_message_id = assistant_message.id 
    db.add(chatroom)
    db.commit()
        
    return {
        "id": assistant_message.id,
        "role": "assistant",
        "message_type": message_type,
        "content": assistant_reply
    }
    
# 위치 선택 후 식당 검색 수행 (LOCATION_SELECTED 태그가 있는 경우)
def process_location_selection_tag(db: Session, chatroom: ChatRoom, user_message_content: str, user_message_id: int) -> Optional[Dict[str, Any]]:
    
    location_selection_regex = re.compile(r"\[LOCATION_SELECTED:(SAVED_LOCATION|CURRENT_LOCATION|MANUAL_LOCATION)\]\|(-?\d+\.\d+)\|(-?\d+\.\d+)")
    match = location_selection_regex.match(user_message_content)

    if not match:
        return None
        
    # 1. 사용자가 정한 주소의 위도, 경도
    action_type = match.group(1).strip()
    lat = float(match.group(2))
    lon = float(match.group(3))
    
    # 2. ChatRoom에서 제일 최근 선택한 메뉴 조회
    selected_menu = get_latest_selected_menu(db, chatroom.id)

    # 3. 식당 검색 및 추천 데이터 생성
    print(f"[DEBUG] 식당 검색 시작: 메뉴={selected_menu}, 위도={lat}, 경도={lon}")
    restaurant_data = recommend_restaurants(selected_menu, db, lat, lon)
    
    # 4. 검색 결과 확인
    restaurants = restaurant_data.get("restaurants", [])
    
    if not restaurants or len(restaurants) == 0:        
        # 검색 실패 메시지 생성
        no_result_msg = restaurant_data["message"]

        # DB에 저장
        no_result_message = ChatMessage(
            room_id=chatroom.id,
            sender_id="assistant",
            role="assistant",
            content=no_result_msg,
            message_type="text",
            timestamp=datetime.datetime.utcnow()
        )
        db.add(no_result_message)
        db.commit()
        db.refresh(no_result_message)
        
        # ChatRoom 상태 초기화
        chatroom.selected_menu = None
        chatroom.last_message_id = no_result_message.id
        db.add(chatroom)
        db.commit()
        
        return {
            "replies": [{
                "id": no_result_message.id,
                "role": "assistant",
                "message_type": "text",
                "content": no_result_msg
            }],
            "user_message_id": user_message_id
        }
        
    # 5. 검색 결과가 있을 때: ChatRoom 상태 초기화
    print(f"[DEBUG] 식당 검색 성공: {len(restaurants)}개 발견")
    chatroom.selected_menu = None
    db.add(chatroom)
    db.commit() 

    # 6. 메시지 데이터 준비
    initial_msg_content = restaurant_data.get("initial_message", f"그러면 {selected_menu} 먹으러 갈 식당을 추천해줄게! 😋")
    final_msg_content = restaurant_data.get("final_message", "다른 행운의 맛집도 추천해줄까?")
    
    card_data = {
        "restaurants": restaurant_data.get("restaurants", []),
        "count": restaurant_data.get("count", 0)
    }
    card_msg_content = json.dumps(card_data, ensure_ascii=False)

    
    # 7. DB에 3가지 메시지 순차적으로 저장
    # 1) initial_message 저장
    initial_message = ChatMessage(
        room_id=chatroom.id,
        sender_id="assistant",
        role="assistant",
        content=initial_msg_content,
        message_type="text",
        timestamp=datetime.datetime.utcnow() 
    )
    db.add(initial_message)

    # 2) 추천 식당 리스트 저장 (restaurant_cards)
    card_message = ChatMessage(
        room_id=chatroom.id,
        sender_id="assistant",
        role="assistant",
        content=card_msg_content,
        message_type="restaurant_cards",
        timestamp=datetime.datetime.utcnow() + datetime.timedelta(seconds=1) 
    )
    db.add(card_message)

    # 3) final_message 저장
    final_message = ChatMessage(
        room_id=chatroom.id,
        sender_id="assistant",
        role="assistant",
        content=final_msg_content,
        message_type="text",
        timestamp=datetime.datetime.utcnow() + datetime.timedelta(seconds=2)
    )
    db.add(final_message)
        
    # DB 커밋: 모든 메시지 한 번에 저장
    db.commit() 
    db.refresh(initial_message)
    db.refresh(card_message)
    db.refresh(final_message)
        
    # 마지막 메시지 ID 업데이트
    chatroom.last_message_id = final_message.id 
    db.add(chatroom)
    db.commit()
        
    # 8. 프론트엔드 반환 형식 구성
    return {
        "replies": [
            {
                "id": initial_message.id,
                "role": "assistant", 
                "message_type": "text", 
                "content": initial_msg_content
            },
            {
                "id": card_message.id,
                "role": "assistant",
                "message_type": "restaurant_cards",
                "content": card_msg_content
            },
            {
                "id": final_message.id,
                "role": "assistant", 
                "message_type": "text", 
                "content": final_msg_content
            },
        ],
        "user_message_id": user_message_id
    }
    
    
# 메시지 객체를 JSON 형태로 변환 (WebSocket 브로드캐스트용)
def chat_message_to_json(msg: ChatMessage, sender_name: str, current_user_uid: str, sender_profile_url: Optional[str] = None) -> dict:
    is_me = msg.sender_id == current_user_uid 
    
    return {
        "id": msg.id,
        "room_id": msg.room_id,
        "sender_id": msg.sender_id,
        "sender_name": sender_name,
        "sender_profile_url": sender_profile_url,
        "role": msg.role,
        "content": msg.content,
        "message_type": msg.message_type,
        "timestamp": msg.timestamp.isoformat(),
        "is_me": is_me 
    }


# 식당 추천 응답 처리 및 브로드캐스트
async def handle_restaurant_recommendation(
    room_id: int,
    selected_menu: str,
    db: Session,
    manager: ConnectionManager,
    chatroom: ChatRoom
):    
    # 식당 검색
    restaurant_data = recommend_restaurants(selected_menu, db)
    
    # 1) 초기 메시지
    initial_msg_content = restaurant_data.get("initial_message")
    initial_message = ChatMessage(
        room_id=room_id,
        sender_id="assistant",
        role="assistant",
        content=initial_msg_content,
        message_type="text",
        timestamp=datetime.datetime.utcnow()
    )
    db.add(initial_message)
    db.flush()
    
    # 초기 메시지 브로드캐스트
    await manager.broadcast(
        room_id,
        json.dumps({
            "type": "new_message",
            "message": {
                "id": initial_message.id,
                "role": "assistant",
                "sender_name": "밥풀이",
                "content": initial_msg_content,
                "message_type": "text",
                "timestamp": initial_message.timestamp.isoformat()
            }
        })
    )
    
    # 2) 식당 카드 메시지
    card_data = {
        "restaurants": restaurant_data.get("restaurants", []),
        "count": restaurant_data.get("count", 0)
    }
    card_msg_content = json.dumps(card_data, ensure_ascii=False)
    card_message = ChatMessage(
        room_id=room_id,
        sender_id="assistant",
        role="assistant",
        content=card_msg_content,
        message_type="restaurant_cards",
        timestamp=datetime.datetime.utcnow() + datetime.timedelta(seconds=1)
    )
    db.add(card_message)
    db.flush()
    
    # 카드 메시지 브로드캐스트
    await manager.broadcast(
        room_id,
        json.dumps({
            "type": "new_message",
            "message": {
                "id": card_message.id,
                "role": "assistant",
                "sender_name": "밥풀이",
                "content": card_msg_content,
                "message_type": "restaurant_cards",
                "timestamp": card_message.timestamp.isoformat()
            }
        })
    )
    
    # 3) 최종 메시지
    final_msg_content = restaurant_data.get("final_message")
    final_message = ChatMessage(
        room_id=room_id,
        sender_id="assistant",
        role="assistant",
        content=final_msg_content,
        message_type="text",
        timestamp=datetime.datetime.utcnow() + datetime.timedelta(seconds=2)
    )
    db.add(final_message)
    db.commit()
    db.refresh(final_message)
    
    # 최종 메시지 브로드캐스트
    await manager.broadcast(
        room_id,
        json.dumps({
            "type": "new_message",
            "message": {
                "id": final_message.id,
                "role": "assistant",
                "sender_name": "밥풀이",
                "content": final_msg_content,
                "message_type": "text",
                "timestamp": final_message.timestamp.isoformat()
            }
        })
    )
    
    # last_message_id 업데이트
    chatroom.last_message_id = final_message.id
    db.add(chatroom)
    db.commit()


# WebSocket으로 받은 메시지를 처리하고 브로드캐스트
async def handle_websocket_message(
    room_id: int,
    uid: str,
    user: User,
    message_content: str,
    db: Session,
    manager: ConnectionManager
):

    # 1. 채팅방 조회
    chatroom = db.query(ChatRoom).filter(ChatRoom.id == room_id).first()
    if not chatroom:
        return
    
    # 2. 위치 선택 메시지인지 먼저 확인 
    is_location_message = message_content.startswith('[LOCATION_SELECTED:')
    
    # 3. 사용자 메시지 DB 저장
    chat_message = ChatMessage(
        room_id=room_id,
        sender_id=uid,
        role="user",
        content=message_content,
        timestamp=datetime.datetime.utcnow()
    )
    db.add(chat_message)
    db.commit()
    db.refresh(chat_message)

    sender_profile_url = user.profile_image 
    
    # 4. 위치 선택 메시지가 아닐 때만 사용자 메시지 브로드캐스트
    if not is_location_message:
        user_msg_json = chat_message_to_json(chat_message, user.nickname, uid, sender_profile_url)
        await manager.broadcast(
            room_id, 
            json.dumps({"type": "new_message", "message": user_msg_json})
        )

    # 5. 위치 선택 메시지 처리 (LLM 호출 전에 처리)
    if is_location_message:        
        location_result = process_location_selection_tag(db, chatroom, message_content, chat_message.id)
        
        if location_result and location_result.get("replies"):
            # 식당 추천 결과를 순차적으로 브로드캐스트
            for reply_msg in location_result["replies"]:
                # DB에서 저장된 메시지 조회
                db_message = db.query(ChatMessage).filter(
                    ChatMessage.id == reply_msg["id"]
                ).first()
                
                if db_message:
                    bot_msg_json = chat_message_to_json(
                        db_message,
                        "밥풀이",
                        uid
                    )
                    await manager.broadcast(
                        room_id,
                        json.dumps({"type": "new_message", "message": bot_msg_json})
                    )
            return

    # 6. 챗봇 호출 여부 결정
    MENTION_TAG = "@밥풀이"
    is_llm_triggered = (not chatroom.is_group) or (
        chatroom.is_group and MENTION_TAG in message_content
    )
    
    if not is_llm_triggered:
        chatroom.last_message_id = chat_message.id
        db.add(chatroom)
        db.commit()
        return
    
    # 7. LLM 호출 및 응답 처리
    try:
        # 멘션 태그 제거
        user_message_for_llm = message_content
        if chatroom.is_group:
            user_message_for_llm = message_content.replace(MENTION_TAG, "").strip()
        
        # 대화 내역 불러오기
        conversation_history = build_conversation_history(db, room_id)
        
        # 그룹 채팅에서 처음 메뉴 추천 요청인지 확인
        if chatroom.is_group and is_initial_recommendation_request(user_message_for_llm, conversation_history):
            # 상세 추천 메시지 생성
            detailed_message_content = await get_initial_chat_message(uid, db)
            
            detailed_message = ChatMessage(
                room_id=room_id,
                sender_id="assistant",
                role="assistant",
                content=detailed_message_content,
                message_type="text",
                timestamp=datetime.datetime.utcnow()
            )
            db.add(detailed_message)
            db.commit()
            db.refresh(detailed_message)
            
            # 상세 추천 메시지 브로드캐스트
            bot_msg_json = chat_message_to_json(
                detailed_message, 
                "밥풀이", 
                uid
            )
            await manager.broadcast(
                room_id,
                json.dumps({"type": "new_message", "message": bot_msg_json})
            )
            
            chatroom.last_message_id = detailed_message.id
            db.add(chatroom)
            db.commit()
            return
        
        # 일반적인 LLM 호출 (초기 추천이 아닌 경우)
        #current_foods = get_latest_recommended_foods(db, room_id)
        llm_output = generate_llm_response(conversation_history, user_message_for_llm)
        
        # 메뉴 선택 시 위치 설정 메시지 출력
        location_select_reply = process_menu_selection(db, chatroom, llm_output)
        
        if location_select_reply:
            # DB에 저장된 메시지 (location_select 타입)를 조회하여 ID/Timestamp 확보
            assistant_message = db.query(ChatMessage).filter(
                ChatMessage.id == chatroom.last_message_id
            ).first()
            
            # 봇 응답 브로드캐스트 (location_select 메시지)
            bot_msg_json = chat_message_to_json(
                assistant_message, 
                "밥풀이", 
                uid
            )

            await manager.broadcast(
                room_id,
                json.dumps({"type": "new_message", "message": bot_msg_json})
            )
            return
        
        else:
            # 일반 텍스트 응답 처리
            assistant_message = ChatMessage(
                room_id=room_id,
                sender_id="assistant",
                role="assistant",
                content=llm_output,
                message_type="text",
                timestamp=datetime.datetime.utcnow()
            )
            db.add(assistant_message)
            db.commit()
            db.refresh(assistant_message)
            
            # 봇 응답 브로드캐스트
            bot_msg_json = chat_message_to_json(
                assistant_message, 
                "밥풀이", 
                uid
            )
            await manager.broadcast(
                room_id,
                json.dumps({"type": "new_message", "message": bot_msg_json})
            )
            
            chatroom.last_message_id = assistant_message.id
            db.add(chatroom)
            db.commit()
            
    except Exception as e:
        logger.error(f"LLM 처리 중 오류: {e}")
        # 에러 메시지 전송
        await manager.broadcast(
            room_id,
            json.dumps({
                "type": "error",
                "message": "메시지 처리 중 오류가 발생했습니다."
            })
        )

# 웹소켓 엔드포인트
@router.websocket("/ws/{room_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    room_id: int,
    token: str,  # 쿼리 파라미터로 전달: ws://...?token=xxx
    db: Session = Depends(get_db),
    manager: ConnectionManager = Depends(get_connection_manager)
):
    try:
        # 1. 토큰 검증
        uid = await get_user_uid_from_websocket_token(token)
        
        # 2. 사용자 및 권한 확인
        user = db.query(User).filter(User.firebase_uid == uid).first()
        if not user:
            await websocket.close(code=1008, reason="등록되지 않은 사용자")
            return
        
        # 3. 채팅방 멤버 확인
        member = db.query(ChatroomMember).filter(
            ChatroomMember.chatroom_id == room_id,
            ChatroomMember.user_id == user.id
        ).first()
        
        if not member:
            await websocket.close(code=1008, reason="채팅방 접근 권한 없음")
            return
        
        # 4. WebSocket 연결 등록
        await manager.connect(room_id, uid, websocket)
        
        try:
            # 5. 메시지 수신 대기
            while True:
                data = await websocket.receive_text()
                message_data = json.loads(data)
                
                # 메시지 타입에 따른 처리
                if message_data.get("type") == "message":
                    await handle_websocket_message(
                        room_id=room_id,
                        uid=uid,
                        user=user,
                        message_content=message_data.get("content"),
                        db=db,
                        manager=manager
                    )
                    
        except WebSocketDisconnect:
            manager.disconnect(room_id, websocket)
            logger.info(f"WebSocket disconnected: Room {room_id}, User {uid}")
            
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        await websocket.close(code=1011, reason=str(e))


# 채팅방 생성 
@router.post("/create")
async def create_chatroom(
    data: ChatRoomCreateRequest,
    uid: str = Depends(verify_firebase_token),
    db: Session = Depends(get_db)
):
    # DB에서 사용자 조회 및 검증
    user = db.query(User).filter(User.firebase_uid == uid).first()
    if not user:
        raise HTTPException(status_code=404, detail="등록되지 않은 사용자입니다.")
    
    # 멤버 등록 (UID 목록 수집 및 닉네임 조회)
    all_member_uids = [uid]
    if data.is_group and data.invited_uids:
        for invited_uid in data.invited_uids:
            if invited_uid != uid and invited_uid not in all_member_uids:
                all_member_uids.append(invited_uid)
    
    members_to_add = db.query(User).filter(
        User.firebase_uid.in_(all_member_uids)
    ).all()

    # 그룹 채팅방 이름 설정    
    if data.name:
        final_room_name = data.name
    elif not data.is_group:
        final_room_name = "밥풀이"
    else:
        # 채팅방 멤버 닉네임 최대 3개 표시
        nicknames = [member.nickname for member in members_to_add]
        
        # 닉네임이 3개 초과일 경우 (예: "A, B, C 외 2명") 처리
        if len(nicknames) > 3:
            display_names = ", ".join(nicknames[:3])
            final_room_name = f"{display_names} 외 {len(nicknames) - 3}명"
        else:
            final_room_name = ", ".join(nicknames)
        
    # 채팅방 생성 및 저장
    chatroom = ChatRoom(name=final_room_name, is_group=data.is_group)
    db.add(chatroom)
    db.commit()
    db.refresh(chatroom) # DB에서 자동 생성된 chatroom.id를 가져옴

    # ChatroomMember 등록
    for member_user in members_to_add:
        role = "owner" if member_user.id == user.id else "member"
        
        member = ChatroomMember(
            user_id=member_user.id,
            chatroom_id=chatroom.id,
            role=role,
            joined_at=datetime.datetime.utcnow()
        )
        db.add(member)
        
    # 초기 메시지 생성 (조건부)
    last_message_id = None
    initial_message_content = None 
    
    # 그룹 채팅이 아닐 경우에만 봇 메시지 생성
    if not data.is_group:
        # 1. 초기 메시지 생성 및 저장 (Greeting Message)
        greeting_message_content = "안녕! 나는 오늘의 운세에 맞춰 행운의 맛집을 추천해주는 '밥풀이'야🍀";
        greeting_message = ChatMessage(
            room_id=chatroom.id, 
            role="assistant", 
            content=greeting_message_content,
            sender_id="assistant"
        )
        db.add(greeting_message)
        db.commit()

        # 2. 상세 추천 메시지 생성 및 저장
        detailed_message_content = await get_initial_chat_message(uid, db)
        detailed_message = ChatMessage(
            room_id=chatroom.id, 
            role="assistant", 
            content=detailed_message_content,
            sender_id="assistant"
        )
        
        db.add(detailed_message)
        db.commit()
    
        db.flush() # ID를 얻기 위해 flush
        last_message_id = detailed_message.id
        initial_message_content = detailed_message_content
        
    # last_message_id를 가장 최근 메시지인 상세 추천 메시지의 ID로 설정
    chatroom.last_message_id = last_message_id # 상세 메시지를 마지막 메시지로 설정
    db.add(chatroom)
    db.commit()

    room_id_str = str(chatroom.id)
    
    return {
        "message": "채팅방 생성 완료",
        "chatroom_id": room_id_str,
        "is_group": chatroom.is_group,
        "name": final_room_name,
        "initial_message": initial_message_content
    }


# 채팅방 목록 조회 
@router.get("/list")
async def list_chatrooms(
    uid: str = Depends(verify_firebase_token),
    is_group: Optional[bool] = None, 
    db: Session = Depends(get_db)
):
    # DB에서 사용자 조회 및 검증
    user = db.query(User).filter(User.firebase_uid == uid).first()
    if not user:
        raise HTTPException(status_code=404, detail="등록되지 않은 사용자입니다.")
    
    # 현재 사용자가 속한 ChatRoom만 조회
    query = db.query(ChatRoom).join(
        ChatroomMember
    ).filter(
        ChatroomMember.user_id == user.id
    )

    # is_group 필터 적용
    if is_group is not None:
        query = query.filter(ChatRoom.is_group == is_group)
    
    # 최신 메시지 Eager Loading
    rooms = query.options(
        joinedload(ChatRoom.latest_message)
    ).all()
        
    result = []
    for room in rooms:
        latest_msg = room.latest_message
        latest_content = latest_msg.content if latest_msg else "대화 내용 없음"
        latest_timestamp = latest_msg.timestamp if latest_msg else None
        
        # 채팅방 멤버 수와 프로필 사진 목록
        member_count = None
        member_profiles = [] 
        
        if room.is_group:
            member_count = db.query(ChatroomMember).filter(
                ChatroomMember.chatroom_id == room.id
            ).count()
            
            members = db.query(User).join(ChatroomMember).filter(
                ChatroomMember.chatroom_id == room.id,
                User.id != user.id  # 현재 사용자 제외
            ).limit(4).all()  # 최대 4명만

            member_profiles = [
                {
                    "nickname": m.nickname,
                    "profile_image": m.profile_image or None
                }
                for m in members
            ]
            
        # 시간대 변환 로직
        kst_timestamp = None
        if latest_timestamp:
            if latest_timestamp.tzinfo is None:
                utc_dt = UTC.localize(latest_timestamp)
            else:
                utc_dt = latest_timestamp.astimezone(UTC)
            kst_dt = utc_dt.astimezone(KST)
            kst_timestamp = kst_dt.isoformat()
        
        result.append({
            "id": room.id,
            "name": room.name,
            "is_group": room.is_group,
            "last_message_content": latest_content,
            "last_message_timestamp": kst_timestamp,
            "member_count": member_count,
            "member_profiles": member_profiles
        })
        
    return result


# 특정 채팅방의 메시지 조회
@router.get("/messages/{room_id}")
async def get_messages(
    room_id: int, 
    uid: str = Depends(verify_firebase_token),
    db: Session = Depends(get_db)
):
    # 1. 사용자 인증 및 권한 확인
    user = db.query(User).filter(User.firebase_uid == uid).first()
    if not user:
        raise HTTPException(status_code=404, detail="사용자 인증 실패")

    member = db.query(ChatroomMember).filter(
        ChatroomMember.chatroom_id == room_id,
        ChatroomMember.user_id == user.id
    ).first()
    
    if not member:
        raise HTTPException(status_code=403, detail="이 채팅방에 접근할 권한이 없습니다.")

    # 채팅방 정보 조회
    chatroom = db.query(ChatRoom).filter(ChatRoom.id == room_id).first()

    # 2. 메시지 조회
    messages = db.query(ChatMessage).filter(
        ChatMessage.room_id == room_id
    ).order_by(ChatMessage.timestamp).all()

    # 3. 반환할 데이터 포맷
    result = []
    for msg in messages:
        sender_profile_url = None
        
        if msg.sender_id == "assistant":
            # 봇 메시지인 경우
            sender_name = "밥풀이"
        else:
            # 일반 사용자 메시지인 경우
            sender = db.query(User).filter(User.firebase_uid == msg.sender_id).first()
            sender_name = sender.nickname if sender and sender.nickname else "알 수 없음"
            sender_profile_url = sender.profile_image if sender else None
        
        result.append({
            "id": msg.id,
            "user_id": msg.sender_id,
            "role": msg.role,
            "sender_id": msg.sender_id,
            "sender_name": sender_name,
            "sender_profile_url": sender_profile_url,
            "content": msg.content,
            "message_type": msg.message_type,
            "timestamp": msg.timestamp.isoformat() if msg.timestamp else None
        })
    
    # 딕셔너리로 반환
    return {
        "messages": result,
        "is_group": chatroom.is_group if chatroom else False,
        "chatroom_name": chatroom.name if chatroom else f"채팅방 #{room_id}"
    }


# 채팅방 삭제 
@router.delete("/{room_id}")
async def delete_chatroom(
    room_id: int,
    uid: str = Depends(verify_firebase_token),
    db: Session = Depends(get_db)
):
    # 1. DB에서 사용자 조회 및 검증
    user = db.query(User).filter(User.firebase_uid == uid).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="등록되지 않은 사용자입니다.")
    
    # 2. DB에서 ChatRoom 조회
    room = db.query(ChatRoom).filter(ChatRoom.id == room_id).first()
    if not room:
        # 채팅방이 이미 삭제되었거나 존재하지 않는 경우
        return {"message": "채팅방을 찾을 수 없습니다. 이미 삭제되었을 수 있습니다."} 
        
    # 사용자가 해당 방의 멤버인지 확인
    member = db.query(ChatroomMember).filter(
        ChatroomMember.chatroom_id == room_id,
        ChatroomMember.user_id == user.id 
    ).first()
    if not member:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="이 채팅방을 삭제할 권한이 없습니다.")

    try:
        # 3. 채팅방 삭제
        db.delete(room)         
        db.commit()

    except Exception as e:
        db.rollback() 
        print(f"채팅방 삭제 중 오류 발생: {e}")

    return {"message": "채팅방 삭제 완료"}


# 메시지 전송 
@router.post("/send")
async def send_message(
    request: MessageRequest,
    uid: str = Depends(verify_firebase_token),
    db: Session = Depends(get_db),
    manager: ConnectionManager = Depends(get_connection_manager)
):
    # DB에서 사용자 조회 및 검증
    user = db.query(User).filter(User.firebase_uid == uid).first()
    if not user:
        raise HTTPException(status_code=404, detail="등록되지 않은 사용자입니다.")
    
    # DB에서 채팅방 확인
    chatroom = db.query(ChatRoom).filter(ChatRoom.id == request.room_id).first()
    if not chatroom:
        raise HTTPException(status_code=404, detail="채팅방을 찾을 수 없음")

    # 유저 메시지 DB 저장
    chat_message = ChatMessage(
        room_id=chatroom.id,
        sender_id=uid,
        role="user",
        content=request.message,
        timestamp=datetime.datetime.utcnow()
    )
    db.add(chat_message)
    db.commit()
    db.refresh(chat_message)
    
    # 유저 메시지 WebSocket 브로드캐스트
    user_msg_json = chat_message_to_json(
        chat_message, 
        user.nickname, 
        uid
    )
    # 모든 클라이언트에게 메시지를 즉시 전송
    await manager.broadcast(chatroom.id, json.dumps({"type": "new_message", "message": user_msg_json}))
        
    # 챗봇 호출 여부 결정
    MENTION_TAG = "@밥풀이"
    
    # LLM 호출 조건: 1:1 채팅 / 그룹 채팅이면서 멘션 태그가 포함된 경우
    is_llm_triggered = (not chatroom.is_group) or (chatroom.is_group and MENTION_TAG in request.message)
    
    # LLM 호출하지 않는 경우 (그룹 채팅 + 멘션 없음)
    if not is_llm_triggered:
        chatroom.last_message_id = chat_message.id 
        db.add(chatroom)
        db.commit()
        return {"message": "메시지 전송 완료 (LLM 미호출)", "user_message_id": chat_message.id}
            
    try:
        # 사용자가 위치를 반환한 경우 (메뉴 선택 > 위치 선택 > 식당 추천) 
        user_message_content = request.message
        location_select_result = process_location_selection_tag(db, chatroom, user_message_content, chat_message.id)
        
        if location_select_result:
            # 태그가 발견되면 식당 추천 로직 실행 후 즉시 반환 (LLM 호출하지 않음)
            return location_select_result
    
        # 사용자가 위치를 반환하지 않은 경우 LLM 호출
        # 멘션 태그 제거
        user_message_for_llm = request.message
        if chatroom.is_group:
            # 그룹 채팅일 경우에만 멘션 태그를 제거하여 LLM에 전달
            user_message_for_llm = request.message.replace(MENTION_TAG, "").strip()
        
        # 1) 기존 대화 내역 불러오기
        conversation_history = build_conversation_history(db, chatroom.id)
        
        # 3) LLM 호출
        llm_output = generate_llm_response(conversation_history, user_message_for_llm)
        
        # 메뉴 선택
        location_select_reply = process_menu_selection(db, chatroom, llm_output)
        if location_select_reply:
            return {
                "reply": location_select_reply,
                "user_message_id": chat_message.id
            }
        
        # 식당 추천 이외의 다른 답변
        else:
            # 일반 텍스트 응답
            assistant_reply = llm_output
            message_type = "text"
            
            # LLM 응답 저장
            assistant_message = ChatMessage(
                room_id=chatroom.id,
                sender_id="assistant",
                role="assistant",
                content=assistant_reply,
                message_type=message_type,
                timestamp=datetime.datetime.utcnow()
            )
            db.add(assistant_message)
            db.commit()
            db.refresh(assistant_message)
            
            chatroom.last_message_id = assistant_message.id 
            db.add(chatroom)
            db.commit()
    
            # 일반 텍스트는 하나만 리스트로 반환
            return {
                "reply": {"role": "assistant", "content": assistant_reply},
                "user_message_id": chat_message.id
            }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"LLM 처리 중 오류: {e}")
