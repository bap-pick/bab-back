from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from core.db import get_db
from core.models import ChatRoom, ChatMessage
from core.firebase_auth import verify_firebase_token
import datetime
import os
from dotenv import load_dotenv

# 최신 Google Gen AI SDK
import google.genai as genai

router = APIRouter(prefix="/chat", tags=["chat"])

# ---------------- 요청 모델 ----------------
class MessageRequest(BaseModel):
    room_id: int
    message: str

class ChatRoomCreateRequest(BaseModel):
    room_id: int

# ---------------- 임시 메모리용 ----------------
Chat_rooms = {}

# ---------------- .env 로드 및 클라이언트 설정 ----------------
load_dotenv()
client = genai.Client(api_key=os.getenv("GEMMA_API_KEY"))

# ---------------- 채팅방 생성 ----------------
@router.post("/create")
async def create_chatroom(
    data: ChatRoomCreateRequest,
    uid: str = Depends(verify_firebase_token),
    db: Session = Depends(get_db)
):
    chatroom = ChatRoom(name=data.room_id)
    db.add(chatroom)
    db.commit()
    db.refresh(chatroom)

    room_id_str = str(chatroom.id)
    Chat_rooms[room_id_str] = []
    print(f"메모리 chat_rooms에 추가됨: {room_id_str}")

    return {"message": "채팅방 생성 완료", "chatroom_id": room_id_str}

# ---------------- 채팅방 목록 조회 ----------------
@router.get("/list")
async def list_chatrooms(
    uid: str = Depends(verify_firebase_token),
    db: Session = Depends(get_db)
):
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
def send_message(
    request: MessageRequest,
    uid: str = Depends(verify_firebase_token),
    db: Session = Depends(get_db)
):
    # 1️⃣ 채팅방 확인
    chatroom = db.query(ChatRoom).filter(ChatRoom.id == request.room_id).first()
    if not chatroom:
        raise HTTPException(status_code=404, detail="채팅방을 찾을 수 없음")

    # 2️⃣ 유저 메시지 DB 저장
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

    # 3️⃣ 클라우드 LLM 호출
    try:
        response = client.models.generate_content(
            model="gemma3:4b",  # 사용할 모델
            content=[request.message]  # 단일 문자열
        )
        

        assistant_reply = response.output_text.strip() if response.output_text else "응답 없음"

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"LLM API 호출 실패: {e}")

    # 4️⃣ AI 답변 DB 저장
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

    # 5️⃣ 최종 응답 반환
    return {
        "reply": {"role": "assistant", "content": assistant_reply},
        "user_message_id": chat_message.id
    }
