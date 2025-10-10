#!/usr/bin/env python
# coding: utf-8

# In[1]:


from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from core.db import get_db
from core.models import ChatRoom
from core.firebase_auth import verify_firebase_token


# In[ ]:


load_dotenv()


# In[ ]:


router = APIRouter(prefix="/chat", tags=["chat"])


# In[ ]:


# 요청 모델
class MessageRequest(BaseModel):
    room_id: str
    message: str

class ChatRoomCreateRequest(BaseModel):
    room_id: str


# In[ ]:


# 채팅방 생성
@router.post("/create")
async def create_chatroom(
    data: ChatRoomCreate,
    uid: str = Depends(verify_firebase_token),
    db: Session = Depends(get_db)
):
    chatroom = ChatRoom(name=data.name, owner_uid=uid)
    db.add(chatroom)
    db.commit()
    db.refresh(chatroom)
    return {"message": "채팅방 생성 완료", "chatroom_id": chatroom.id}


# In[ ]:


# 채팅방 목록 조회
@router.get("/list")
async def list_chatrooms(
    uid: str = Depends(verify_firebase_token),
    db: Session = Depends(get_db)
):
    rooms = db.query(ChatRoom).filter(ChatRoom.owner_uid == uid).all()
    return [
        {"id": room.id, "name": room.name, "created_at": room.created_at}
        for room in rooms
    ]


# In[ ]:


# 채팅방 삭제
@router.delete("/{room_id}")
async def delete_chatroom(
    room_id: int,
    uid: str = Depends(verify_firebase_token),
    db: Session = Depends(get_db)
):
    room = db.query(ChatRoom).filter(ChatRoom.id == room_id, ChatRoom.owner_uid == uid).first()
    if not room:
        raise HTTPException(status_code=404, detail="채팅방을 찾을 수 없음")

    db.delete(room)
    db.commit()
    return {"message": "삭제 완료"}


# In[ ]:


#채팅 보내기
@router.post("/send")
def send_message(request: MessageRequest):
    room_id = request.room_id
    user_message = request.message

    if room_id not in chat_rooms:
        raise HTTPException(status_code=404, detail="채팅방을 찾을 수 없음")

    # 유저 메시지 저장
    chat_rooms[room_id].append({"role": "user", "content": user_message})


    #LLM API 호출
    LLM_API_URL = os.getenv("LLM_API_URL")
    LLM_API_KEY = os.getenv("LLM_API_KEY")

    if not LLM_API_URL or not LLM_API_KEY:
        raise HTTPException(status_code=500, detail="API 설정 누락") #.env 확인

    headers = {
        "Authorization": f"Bearer {LLM_API_KEY}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": "gemma-3",
        "messages": chat_rooms[room_id]
    }

    try:
        response = requests.post(LLM_API_URL, headers=headers, json=payload)
        response.raise_for_status()
        data = response.json()

        assistant_reply = data.get("reply", "불러오기 실패")
        chat_rooms[room_id].append({"role": "assistant", "content": assistant_reply})

        return {"reply": assistant_reply, "history": chat_rooms[room_id]}

    except requests.RequestException as e:
        raise HTTPException(status_code=500, detail=f" API 호출 실패: 


# In[ ]:





# In[ ]:





# In[ ]:




