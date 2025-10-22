from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from core.db import get_db
from core.models import ChatRoom, ChatMessage, User
from core.firebase_auth import verify_firebase_token
import datetime
from typing import Optional
from google import genai
from google.genai import types
from core.config import GEMMA_API_KEY

client = genai.Client(api_key=GEMMA_API_KEY) 
model_name = "gemma-3-4b-it"

router = APIRouter(prefix="/chat", tags=["chat"])

# ---------------- 요청 모델 ----------------
class MessageRequest(BaseModel):
    room_id: int
    message: str

class ChatRoomCreateRequest(BaseModel):
    name: Optional[str] = None
    is_group: bool = False

Chat_rooms = {}

# ---------------- 채팅방 생성 ----------------
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

    room_id_str = str(chatroom.id)
    Chat_rooms[room_id_str] = []
    
    return {"message": "채팅방 생성 완료", "chatroom_id": room_id_str}

# ---------------- 채팅방 목록 조회 ----------------
@router.get("/list")
async def list_chatrooms(
    uid: str = Depends(verify_firebase_token),
    db: Session = Depends(get_db)
):
    # DB에서 사용자 조회 및 검증
    user = db.query(User).filter(User.firebase_uid == uid).first()
    if not user:
        raise HTTPException(status_code=404, detail="등록되지 않은 사용자입니다.")
    
    rooms = db.query(ChatRoom).all()
    return [
        {"id": room.id, "name": room.name, "created_at": room.created_at}
        for room in rooms
    ]

# ---------------- 채팅방 삭제 ----------------
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

# ---------------- 메시지 전송 ----------------
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

    # LLM 클라우드 API 호출
    try:
        response = client.models.generate_content(
            model=model_name,
            contents=[request.message],
            config=types.GenerateContentConfig(temperature=0)
        )
        
        assistant_reply = response.text.strip() if response.text else "응답 없음"

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"LLM API 호출 실패: {e}")

    # AI 답변 DB 저장
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

    # 최종 응답 반환
    return {
        "reply": {"role": "assistant", "content": assistant_reply},
        "user_message_id": chat_message.id
    }
