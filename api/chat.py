from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from core.db import get_db
from core.models import ChatRoom, ChatMessage, ChatroomMember, User 
from core.firebase_auth import verify_firebase_token
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
    # room_id 필드는 DB의 name 필드(VARCHAR)로 매핑되므로, int 대신 str을 사용하는 것이 더 일반적입니다.
    # 그러나 기존 코드의 int를 유지하고 DB에 name=int로 저장합니다.
    room_id: int 

# ---------------- 임시 메모리용 ----------------
Chat_rooms = {} 


# ---------------- 채팅방 생성 ----------------
@router.post("/create")
async def create_chatroom(
    data: ChatRoomCreateRequest,
    uid: str = Depends(verify_firebase_token),
    db: Session = Depends(get_db)
):
    # ... 기존 로직 유지 ...
    chatroom = ChatRoom(name=str(data.room_id), is_group=False)
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
    # Firebase UID를 DB User ID(PK)로 변환
    user = db.query(User).filter(User.firebase_uid == uid).first()
    user_db_id = user.id

    # 채팅방 확인 및 챗봇 ID 설정: 채팅방이 없으면 DB 저장 안 함
    chatroom = db.query(ChatRoom).filter(ChatRoom.id == request.room_id).first()
    chatbot_user_id = 1 # 챗봇 ID (예: 1) 사용
    
    user_message_id = None
    
    # LLM 호출
    try:
        response = client.models.generate_content(
            model=model_name,
            contents=[request.message],
            config=types.GenerateContentConfig(temperature=0)
        )
        assistant_reply = response.text.strip() if response.text else "응답 없음"
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"LLM API 호출 실패: {e}")

    # DB 저장 
    if chatroom:
        try:
            # 1. 유저 메시지 객체 생성
            user_chat_message = ChatMessage(
                chatroom_id=chatroom.id,
                user_id=user_db_id,
                content=request.message,
                message_type='text',
            )
            
            # 2. AI 메시지 객체 생성
            assistant_chat_message = ChatMessage(
                chatroom_id=chatroom.id,
                user_id=chatbot_user_id,
                content=assistant_reply,
                message_type='text',
            )
            
            # 3. 두 메시지를 세션에 추가
            db.add(user_chat_message)
            db.add(assistant_chat_message)
            
            # 4. commit 없이 refresh하여 ID를 가져옴
            db.flush() # ID 생성을 위해 flush
            user_message_id = user_chat_message.id

            # 5. ChatRoom의 last_message_id 업데이트
            chatroom.last_message_id = assistant_chat_message.id
            
            db.commit()

        except Exception as e:
            db.rollback()
            print(f"Error: DB transaction failed for room {request.room_id}. Error: {e}")
            # 이 경우 클라이언트에게는 LLM 응답을 반환할 수 있지만, DB에 기록되지 않음
    
    # 최종 응답 반환
    return {
        "reply": {"role": "assistant", "content": assistant_reply},
        "user_message_id": user_message_id
    }
    
    