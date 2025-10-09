from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session

from core.firebase_auth import verify_firebase_token # Firebase ID 토큰 검증
from core.db import get_db # DB 세션 의존성
from core.models import User # SQLAlchemy User 모델

router = APIRouter(prefix="/users")

# 내 정보 조회 API
@router.get("/me")
def get_my_info(
    uid: str = Depends(verify_firebase_token),
    fields: str = Query(None, description="쉼표로 구분된 필요한 필드 목록"),
    db: Session = Depends(get_db)
):
    # DB에서 사용자 조회
    user = db.query(User).filter(User.firebase_uid == uid).first()
    if not user:
        raise HTTPException(status_code=404, detail="등록되지 않은 사용자입니다.")

    # 필요한 필드만 선택
    user_dict = {
        "email": user.email,
        "nickname": user.nickname,
        "birthdate": user.birthdate,
        "gender": user.gender,
    }

    if fields:
        requested_fields = set(f.strip() for f in fields.split(","))
        filtered_user = {k: v for k, v in user_dict.items() if k in requested_fields}
        return filtered_user

    return user_dict
