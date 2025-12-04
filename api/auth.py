from fastapi import APIRouter, HTTPException, Depends, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session
import datetime

from core.firebase_auth import verify_firebase_token # Firebase ID 토큰 검증
from core.db import get_db # DB 세션 의존성
from core.models import User # SQLAlchemy User 모델

from saju.saju_service import calculate_saju_and_save # 사주 계산 및 저장 함수

router = APIRouter(prefix="/auth", tags=["auth"])

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

# 게스트용 요청 모델
class GuestLoginRequest(BaseModel):
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
    response: Response,
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
    db.flush() # User의 Primary Key(ID) 미리 확보
    
    # 사주 계산 및 저장 함수 호출
    try:
        await calculate_saju_and_save(user=user, db=db)
    except Exception as e:
        db.rollback()
        print(f"Saju calculation failed for user {uid}: {e}") 
        raise HTTPException(status_code=500, detail="회원가입 중 사주 데이터 계산/저장에 실패했습니다.")

    db.commit()
    db.refresh(user)

    response.set_cookie(
        key="session_uid",
        value=uid,
        max_age=3600,
        httponly=True,
        secure=False,
        samesite="Lax"
    )

    db.commit()
    db.refresh(user)
    
    return {"message": "회원가입 및 자동 로그인 성공", "uid": uid}


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


# 게스트 로그인/가입 API
@router.post("/guest-login")
async def guest_login(
    response: Response,
    data: GuestLoginRequest,
    uid: str = Depends(verify_firebase_token),
    db: Session = Depends(get_db)
):
    # 이미 DB에 존재하는지 확인 (익명 사용자가 재접속 시)
    user = db.query(User).filter(User.firebase_uid == uid).first()

    # 신규 게스트라면 DB에 등록
    if not user:
        # birthdate 처리
        birth_date = datetime.datetime.strptime(data.birthDate, "%Y-%m-%d").date()
        
        # time 처리
        if data.timeUnknown:
            birth_time = None
        else:
            try:
                hour = int(data.birthHour)
                minute = int(data.birthMinute)
                birth_time = datetime.time(hour=hour, minute=minute)
            except ValueError:
                raise HTTPException(status_code=400, detail="출생시간이 올바르지 않습니다.")
        
        # User 객체 생성 - 익명용 더미 이메일 생성
        dummy_email = f"guest_{uid[:8]}@bapick.guest"
        
        user = User(
            firebase_uid=uid,
            email=dummy_email,
            nickname=data.nickname,
            gender=data.gender,
            birth_date=birth_date,
            birth_time=birth_time,
            birth_calendar=data.birthCalendar,
        )
        
        db.add(user)
        db.flush() 

        # 사주 계산 로직 수행
        try:
            await calculate_saju_and_save(user=user, db=db)
        except Exception as e:
            db.rollback()
            print(f"Guest Saju calculation failed: {e}")
            raise HTTPException(status_code=500, detail="게스트 정보 저장 실패")

        db.commit()
        db.refresh(user)

    # 쿠키 발급 (로그인 처리)
    response.set_cookie(
        key="session_uid",
        value=uid,
        max_age=3600,
        httponly=True,
        secure=False,
        samesite="Lax"
    )

    return {"message": "게스트 로그인 성공", "uid": uid}