from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime
from pydantic import BaseModel
from core.db import get_db
from core.firebase_auth import verify_firebase_token
from core.models import User, Scrap

router = APIRouter(prefix="/scraps")

class ScrapCreate(BaseModel):
    restaurant_id: int

# 스크랩 등록
@router.post("/")
def create_scrap(
    scrap_data: ScrapCreate,
    db: Session = Depends(get_db),
    uid: str = Depends(verify_firebase_token)
):
    restaurant_id = scrap_data.restaurant_id
    user = db.query(User).filter(User.firebase_uid == uid).first()
    if not user:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다.")

    existing_scrap = db.query(Scrap).filter(
        Scrap.user_id == user.id,
        Scrap.restaurant_id == restaurant_id
    ).first()

    if existing_scrap:
        return {"message": "이미 스크랩된 식당입니다.", 
                "scrap": {"user_id": user.id, "restaurant_id": restaurant_id, "created_at": existing_scrap.created_at}}

    new_scrap = Scrap(user_id=user.id, restaurant_id=restaurant_id, created_at=datetime.utcnow())
    db.add(new_scrap)
    db.commit()

    return {
        "message": "스크랩 성공",
        "scrap": {
            "user_id": user.id,
            "restaurant_id": restaurant_id,
            "created_at": new_scrap.created_at
        }
    }

# 스크랩 삭제
@router.delete("/{restaurant_id}")
def delete_scrap(
    restaurant_id: int,
    db: Session = Depends(get_db),
    uid: str = Depends(verify_firebase_token)
):
    user = db.query(User).filter(User.firebase_uid == uid).first()
    if not user:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다.")

    scrap = db.query(Scrap).filter(
        Scrap.user_id == user.id,
        Scrap.restaurant_id == restaurant_id
    ).first()
    if not scrap:
        raise HTTPException(status_code=404, detail="스크랩 정보를 찾을 수 없습니다.")

    db.delete(scrap)
    db.commit()
    return {"message": "스크랩 취소 성공", "restaurant_id": restaurant_id}

# 스크랩 상태 확인
@router.get("/{restaurant_id}")
def get_scrap_status(
    restaurant_id: int,
    db: Session = Depends(get_db),
    uid: str = Depends(verify_firebase_token)
):
    user = db.query(User).filter(User.firebase_uid == uid).first()
    if not user:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다.")

    scrap = db.query(Scrap).filter(
        Scrap.user_id == user.id,
        Scrap.restaurant_id == restaurant_id
    ).first()

    return {"is_scrapped": bool(scrap)}
