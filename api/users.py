from fastapi import APIRouter, Depends, Query, HTTPException, Depends, UploadFile, File, Form
from sqlalchemy.orm import Session
import os, shutil

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
        "gender": user.gender,
        "birthDate": user.birth_date,
        "birthTime": user.birth_time,
        "birthCalendar": user.birth_calendar,
        "profileImage": user.profile_image
    }

    if fields:
        requested_fields = set(f.strip() for f in fields.split(","))
        filtered_user = {k: v for k, v in user_dict.items() if k in requested_fields}
        return filtered_user

    return user_dict

# PATCH: 내 정보 수정
@router.patch("/me")
async def patch_my_info(
    uid: str = Depends(verify_firebase_token),
    db: Session = Depends(get_db),
    nickname: str = Form(None),
    profile_image: UploadFile = File(None)
):
    # DB에서 사용자 조회
    user = db.query(User).filter(User.firebase_uid == uid).first()
    if not user:
        raise HTTPException(status_code=404, detail="등록되지 않은 사용자입니다.")

    # 닉네임 수정
    if nickname:
        user.nickname = nickname

    # 프로필 이미지 수정
    if profile_image:
        save_dir = "static/profile_images"
        os.makedirs(save_dir, exist_ok=True)
        file_path = os.path.join(save_dir, f"{uid}_{profile_image.filename}")

        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(profile_image.file, buffer)

        # 웹에서 접근 가능한 URL 형태로 DB 저장
        user.profile_image = f"http://127.0.0.1:8000/{file_path.replace(os.sep, '/')}"


    db.commit()
    db.refresh(user)

    return {
        "message": "회원 정보 수정 성공",
        "nickname": user.nickname,
        "profile_image": user.profile_image  # URL 반환
    }