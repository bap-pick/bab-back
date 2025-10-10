from fastapi import APIRouter, HTTPException, Depends, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session
import datetime

from core.firebase_auth import verify_firebase_token # Firebase ID 토큰 검증
from core.db import get_db # DB 세션 의존성
from core.models import User # SQLAlchemy User 모델

router = APIRouter(prefix="/auth")

# 회원가입 요청 모델
class RegisterRequest(BaseModel):
    email: str
    nickname: str
    gender: str
    birthCalendar: str
    birthDate: str
    birthHour: str
    birthMinute: str
    timeUnknown: bool

# 회원가입 API
@router.post("/register")
async def register_user(
    data: RegisterRequest,
    uid: str = Depends(verify_firebase_token),
    db: Session = Depends(get_db)
):
    # 이미 가입된 사용자인지 확인
    existing_user = db.query(User).filter(User.firebase_uid == uid).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="이미 가입된 사용자입니다.")

    # birthdate 처리: 문자열 -> date 객체 변환
    birth_date = datetime.datetime.strptime(data.birthDate, "%Y-%m-%d").date()
    
    # birthHour / birthMinute 처리
    if data.timeUnknown:
        birth_time = None
    else:
        try:
            hour = int(data.birthHour)
            minute = int(data.birthMinute)
            if not (0 <= hour < 24) or not (0 <= minute < 60):
                raise ValueError
            birth_time = datetime.time(hour=hour, minute=minute)
        except ValueError:
            raise HTTPException(status_code=400, detail="출생시간이 올바르지 않습니다.")

    # User 객체 생성
    user = User(
        firebase_uid=uid,
        email=data.email,
        nickname=data.nickname,
        gender=data.gender,
        birth_date=birth_date,
        birth_time=birth_time,
        birth_calendar=data.birthCalendar
    )
    
    db.add(user)
    db.commit()
    db.refresh(user)

    return {"message": "회원가입 성공", "uid": uid}


# 로그인 API
@router.post("/login")
def login(
    response: Response,
    uid: str = Depends(verify_firebase_token),
    db: Session = Depends(get_db)
):
    # DB에서 사용자 확인
    user = db.query(User).filter(User.firebase_uid == uid).first()
    if not user:
        raise HTTPException(status_code=404, detail="등록되지 않은 사용자입니다.")

    # 쿠키 발급
    response.set_cookie(
        key="session_uid",
        value=uid,
        max_age=3600,        # 1시간 유지
        httponly=True,       # JS에서 접근 불가
        secure=False,        # True=HTTPS 환경에서만 전송, 테스트라서 false
        samesite="Lax"       # CSRF 기본 보호
    )

    return {"message": "로그인 성공", "uid": uid}