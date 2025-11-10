from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload
from pydantic import BaseModel
from core.db import get_db
from core.models import ChatRoom, ChatMessage, ChatroomMember, User
from core.firebase_auth import verify_firebase_token
import datetime
<<<<<<< HEAD
from typing import Optional, List
from google import genai
from google.genai import types
from core.config import GEMMA_API_KEY
import pytz
=======
from typing import Optional
>>>>>>> 5b61414 (채팅 초기 메세지 설정 및 llm 프롬프트 튜닝)

from .chain import build_conversation_history, generate_llm_response,get_initial_chat_message


router = APIRouter(prefix="/chat", tags=["chat"])

# KST 시간대 정의 (UTC+9)
KST = pytz.timezone('Asia/Seoul') 
UTC = pytz.timezone('UTC')

# ---------------- 요청 모델 ----------------
class MessageRequest(BaseModel):
    room_id: int
    message: str

class ChatRoomCreateRequest(BaseModel):
    name: Optional[str] = None
    is_group: bool = False

Chat_rooms = {}


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
    
    # 채팅방 생성 및 저장
    chatroom = ChatRoom(name=data.name, is_group=data.is_group)
    db.add(chatroom)
    db.commit()
    db.refresh(chatroom) # DB에서 자동 생성된 chatroom.id를 가져옴

<<<<<<< HEAD
    # Chatroom_members 테이블에 저장 (유저 id와 채팅방 id)
    chatroom_member = ChatroomMember(
        user_id=user.id,
        chatroom_id=chatroom.id,
        role="owner", # role 'owner'
        joined_at=datetime.datetime.utcnow()
    )
    db.add(chatroom_member)
    db.commit() # ChatroomMember 저장
=======
    #  초기 메시지 생성
    system_message = await get_initial_chat_message(uid, db)
    db.add(ChatMessage(room_id=chatroom.id, role="system", content=system_message, sender_id="system"))
    db.commit()
>>>>>>> 5b61414 (채팅 초기 메세지 설정 및 llm 프롬프트 튜닝)
    
    room_id_str = str(chatroom.id)
    Chat_rooms[room_id_str] = []
    
    return {"message": "채팅방 생성 완료", "chatroom_id": room_id_str, "initial_message": system_message}


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
        
        if room.is_group:
            member_count = db.query(ChatroomMember).filter(
                ChatroomMember.chatroom_id == room.id
            ).count()

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


#  채팅방 삭제 
@router.delete("/{room_id}")
async def delete_chatroom(
    room_id: int,
    uid: str = Depends(verify_firebase_token),
    db: Session = Depends(get_db)
):
    # DB에서 사용자 조회 및 검증
    user = db.query(User).filter(User.firebase_uid == uid).first()
    if not user:
        raise HTTPException(status_code=404, detail="등록되지 않은 사용자입니다.")
    
    # DB에서 채팅방 조회
    room = db.query(ChatRoom).filter(ChatRoom.id == room_id).first()
    if not room:
        raise HTTPException(status_code=404, detail="채팅방을 찾을 수 없음")

    db.delete(room)
    db.commit()

    room_key = str(room_id)
    if room_key in Chat_rooms:
        del Chat_rooms[room_key]
    return {"message": "삭제 완료"}

<<<<<<< HEAD
# ---------------- 특정 채팅방의 메시지 조회 ----------------
@router.get("/messages/{room_id}", response_model=List[dict])
async def get_messages(
    room_id: int, 
    uid: str = Depends(verify_firebase_token),
    db: Session = Depends(get_db)
):
    # 1. 사용자 인증 및 권한 확인 (사용자가 이 방의 멤버인지 확인)
    user = db.query(User).filter(User.firebase_uid == uid).first()
    if not user:
        raise HTTPException(status_code=404, detail="사용자 인증 실패")

    member = db.query(ChatroomMember).filter(
        ChatroomMember.chatroom_id == room_id,
        ChatroomMember.user_id == user.id
    ).first()
    
    if not member:
        raise HTTPException(status_code=403, detail="이 채팅방에 접근할 권한이 없습니다.")

    # 2. 메시지 조회 (최신 메시지가 가장 아래로 오도록 오름차순 정렬)
    messages = db.query(ChatMessage).filter(
        ChatMessage.room_id == room_id
    ).order_by(ChatMessage.timestamp).all()

    # 3. 반환할 데이터 포맷
    result = []
    for msg in messages:
        # 메시지를 보낸 사용자 정보도 함께 조회하여 전달
        sender = db.query(User).filter(User.id == msg.sender_id).first()
        
        result.append({
            "id": msg.id,
            "user_id": msg.sender_id,
            "role": msg.role,
            "sender_name": sender.nickname if sender and sender.nickname else "알 수 없음",
            "content": msg.content,
            "timestamp": msg.timestamp.isoformat() if msg.timestamp else None
        })
        
    return result

# ---------------- 메시지 전송 ----------------
=======

#  메시지 전송 
>>>>>>> 5b61414 (채팅 초기 메세지 설정 및 llm 프롬프트 튜닝)
@router.post("/send")
async def send_message(
    request: MessageRequest,
    uid: str = Depends(verify_firebase_token),
    db: Session = Depends(get_db)
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
    
    # LLM 로직
    try:
        conversation_history = build_conversation_history(db, chatroom.id)
        assistant_reply = generate_llm_response(conversation_history, request.message)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"LLM 처리 중 오류: {e}")

    # AI 응답 저장
    assistant_message = ChatMessage(
        room_id=chatroom.id,
        sender_id="assistant",
        role="assistant",
        content=assistant_reply,
        timestamp=datetime.datetime.utcnow()
    )
    db.add(assistant_message)
    db.commit()
    db.refresh(assistant_message)

    # Chat_rooms 테이블의 last_message_id에 ai 답변의 id를 추가
    chatroom.last_message_id = assistant_message.id 
    db.add(chatroom)
    db.commit()
    
    # 최종 응답 반환
    return {
        "reply": {"role": "assistant", "content": assistant_reply},
        "user_message_id": chat_message.id
    }
    

    
