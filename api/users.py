from fastapi import APIRouter, Depends, Query, HTTPException, Depends, UploadFile, File, Form
from sqlalchemy.orm import Session

from core.firebase_auth import verify_firebase_token # Firebase ID 토큰 검증
from core.db import get_db # DB 세션 의존성
from core.models import User # SQLAlchemy User 모델
from core.s3 import get_s3_client, S3_BUCKET_NAME, S3_REGION 

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

    user_dict = {
        "email": user.email,
        "nickname": user.nickname,
        "gender": user.gender,
        "birthDate": user.birth_date,
        "birthTime": user.birth_time,
        "birthCalendar": user.birth_calendar,
        "profileImage": user.profile_image,
        "ohengWood": user.oheng_wood,
        "ohengFire": user.oheng_fire,
        "ohengEarth": user.oheng_earth,
        "ohengMetal": user.oheng_metal,
        "ohengWater": user.oheng_water,
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
    s3_client = Depends(get_s3_client), 
    nickname: str = Form(None),
    profile_image: UploadFile = File(None)
):
    # DB에서 사용자 조회 (여기까지는 로그에서 성공 확인)
    user = db.query(User).filter(User.firebase_uid == uid).first()
    if not user:
        raise HTTPException(status_code=404, detail="등록되지 않은 사용자입니다.")

    # 닉네임 수정
    if nickname:
        user.nickname = nickname

    # 프로필 이미지 수정: S3 사용
    if profile_image:
        s3 = s3_client
        s3_key = f"profile_images/{uid}_{profile_image.filename}"

        try:
            # S3 업로드 실행
            s3.upload_fileobj(
                profile_image.file,
                S3_BUCKET_NAME,              
                s3_key,                      
                ExtraArgs={'ContentType': profile_image.content_type}
            )

            # DB에 저장할 Public URL 생성
            user.profile_image = f"https://{S3_BUCKET_NAME}.s3.{S3_REGION}.amazonaws.com/{s3_key}"

        except Exception as e:
            import traceback
            traceback.print_exc() 
            raise HTTPException(status_code=500, detail=f"S3 업로드 실패: {e}")

    db.commit()
    db.refresh(user)

    return {
        "message": "회원 정보 수정 성공",
        "nickname": user.nickname,
        "profile_image": user.profile_image
    }