import re
import json
import datetime
import pytz
import logging
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, status,  WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session, joinedload
from pydantic import BaseModel
from core.db import get_db
from core.models import ChatRoom, ChatMessage, ChatroomMember, User
from core.firebase_auth import verify_firebase_token, get_user_uid_from_websocket_token
from api.chain import build_conversation_history, generate_llm_response, get_initial_chat_message, search_and_recommend_restaurants, get_latest_recommended_foods, is_initial_recommendation_request
from core.websocket_manager import ConnectionManager, get_connection_manager

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

Chat_rooms = {}

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
    restaurant_data = search_and_recommend_restaurants(selected_menu, db)
    
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
    
    # 2. 사용자 메시지 DB 저장
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
    
    # 3. 사용자 메시지 브로드캐스트
    user_msg_json = chat_message_to_json(chat_message, user.nickname, uid, sender_profile_url)
    await manager.broadcast(
        room_id, 
        json.dumps({"type": "new_message", "message": user_msg_json})
    )

    # 4. 챗봇 호출 여부 결정
    MENTION_TAG = "@밥풀이"
    is_llm_triggered = (not chatroom.is_group) or (
        chatroom.is_group and MENTION_TAG in message_content
    )
    
    if not is_llm_triggered:
        # LLM 호출 없이 종료
        chatroom.last_message_id = chat_message.id
        db.add(chatroom)
        db.commit()
        return
    
    # 5. LLM 호출 및 응답 처리
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
        current_foods = get_latest_recommended_foods(db, room_id)
        llm_output = generate_llm_response(
            conversation_history, 
            user_message_for_llm, 
            current_recommended_foods=current_foods
        )
        
        # 메뉴 선택 여부 확인
        menu_match = re.search(r"\[MENU_SELECTED:(.+?)\]", llm_output.strip())
        
        if menu_match:
            # 식당 추천 응답 처리
            await handle_restaurant_recommendation(
                room_id=room_id,
                selected_menu=menu_match.group(1).strip(),
                db=db,
                manager=manager,
                chatroom=chatroom
            )
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
    Chat_rooms[room_id_str] = []
    
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
        
        member_count = None
        #member_profiles = [] 
        
        if room.is_group:
            member_count = db.query(ChatroomMember).filter(
                ChatroomMember.chatroom_id == room.id
            ).count()
            
            # members = db.query(User).join(ChatroomMember).filter(
            #     ChatroomMember.chatroom_id == room.id,
            #     User.id != user.id  # 현재 사용자 제외
            # ).limit(4).all()  # 최대 4명만

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
            "member_count": member_count 
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
    
    # LLM 호출 조건
    # A) 1:1 채팅인 경우 (not chatroom.is_group)
    # B) 그룹 채팅이면서 멘션 태그가 포함된 경우 (chatroom.is_group and MENTION_TAG in request.message)
    is_llm_triggered = (not chatroom.is_group) or (chatroom.is_group and MENTION_TAG in request.message)
    
    # LLM 호출하지 않는 경우 (그룹 채팅 + 멘션 없음)
    if not is_llm_triggered:
        chatroom.last_message_id = chat_message.id 
        db.add(chatroom)
        db.commit()
        return {"message": "메시지 전송 완료 (LLM 미호출)", "user_message_id": chat_message.id}
    
    # LLM 호출하는 경우
    try:
        # 멘션 태그 제거
        user_message_for_llm = request.message
        if chatroom.is_group:
            # 그룹 채팅일 경우에만 멘션 태그를 제거하여 LLM에 전달
            user_message_for_llm = request.message.replace(MENTION_TAG, "").strip()
            
        # 1) 기존 대화 내역 불러오기
        conversation_history = build_conversation_history(db, chatroom.id)
        
        # 2) 현재 음식 추천 목록 전달        
        current_foods = get_latest_recommended_foods(db, chatroom.id)
        
        # 3) LLM 호출
        #llm_output = generate_llm_response(conversation_history, request.message, current_recommended_foods=current_foods)
        llm_output = generate_llm_response(conversation_history, user_message_for_llm, current_recommended_foods=current_foods)
        
        # 4) 응답에 MENU_SELECTED 태그가 있는 경우 사용자가 특정 메뉴를 선택한 것으로 간주
        menu_match = re.search(r"\[MENU_SELECTED:(.+?)\]", llm_output.strip())

        # 사용자가 특정 메뉴를 선택한 경우 식당 추천 답변
        if menu_match:
            selected_menu = menu_match.group(1).strip()
            # 식당 유사도 검색 함수 호출
            restaurant_data = search_and_recommend_restaurants(selected_menu, db)

            # DB에 LLM 답변 저장
            # 1) initial_message (그러면 **{menu_name}**을(를) 파는 식당을 추천해줄게! 😋) 저장
            initial_msg_content = restaurant_data.get("initial_message")
            initial_message = ChatMessage(
                room_id=chatroom.id,
                sender_id="assistant",
                role="assistant",
                content=initial_msg_content,
                message_type="text",
                timestamp=datetime.datetime.utcnow() 
            )
            db.add(initial_message)

            # 2) 추천 식당 리스트 저장
            card_data = {
                "restaurants": restaurant_data.get("restaurants", []),
                "count": restaurant_data.get("count", 0)
            }
            card_msg_content = json.dumps(card_data, ensure_ascii=False)
            
            card_message = ChatMessage(
                room_id=chatroom.id,
                sender_id="assistant",
                role="assistant",
                content=card_msg_content,
                message_type="restaurant_cards",
                timestamp=datetime.datetime.utcnow() + datetime.timedelta(seconds=1) 
            )
            db.add(card_message)

            # 3) final_message (다른 행운의 맛집도 추천해줄까?) 저장
            final_msg_content = restaurant_data.get("final_message")
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
            
            # 마지막 메시지 ID 업데이트 (가장 마지막 메시지인 final_message의 ID 사용)
            chatroom.last_message_id = final_message.id 
            db.add(chatroom)
            db.commit()
            
            return {
                "replies": [
                    {
                        "role": "assistant", 
                        "message_type": "text", 
                        "content": initial_msg_content # 초기 메시지 텍스트
                    },
                    {
                        "role": "assistant",
                        "message_type": "restaurant_cards",
                        "content": card_msg_content # 추천 식당 데이터 JSON 문자열
                    },
                    {
                        "role": "assistant", 
                        "message_type": "text", 
                        "content": final_msg_content # 종료 메시지 텍스트
                    },
                ],
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
