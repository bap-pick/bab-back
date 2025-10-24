from fastapi import APIRouter, Depends, Query, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session
from typing import Dict, Any 
from botocore.exceptions import ClientError

from core.firebase_auth import verify_firebase_token # Firebase ID 토큰 검증
from core.db import get_db # DB 세션 의존성
from core.models import User # SQLAlchemy User 모델
from core.s3 import get_s3_client, S3_BUCKET_NAME, S3_REGION 
from saju.saju_service import calculate_today_saju_iljin # 오늘의 간지 계산

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
        
    # 오늘의 일진 기반 오행 점수 계산
    today_oheng_scores: Dict[str, float] = {}
    try:
        iljin_data = calculate_today_saju_iljin(user, db)
        today_oheng_scores = iljin_data["today_oheng_percentages"]
        
    except Exception as e:
        print(f"Error calculating today's saju for {uid}: {e}")
        today_oheng_scores = {k: 0.0 for k in ["ohengWood", "ohengFire", "ohengEarth", "ohengMetal", "ohengWater"]}

    # 사용자 정보 딕셔너리 생성
    user_dict: Dict[str, Any] = {
        "email": user.email,
        "nickname": user.nickname,
        "gender": user.gender,
        "birthDate": user.birth_date,
        "birthTime": user.birth_time,
        "birthCalendar": user.birth_calendar,
        "profileImage": user.profile_image,
        
        # 오늘의 일진에 따라 보정된 오행 비율
        "ohengWood": today_oheng_scores.get("ohengWood", 0.0),
        "ohengFire": today_oheng_scores.get("ohengFire", 0.0),
        "ohengEarth": today_oheng_scores.get("ohengEarth", 0.0),
        "ohengMetal": today_oheng_scores.get("ohengMetal", 0.0),
        "ohengWater": today_oheng_scores.get("ohengWater", 0.0),
    }
    
    if fields:
        requested_fields = set(f.strip() for f in fields.split(","))
        filtered_user = {k: v for k, v in user_dict.items() if k in requested_fields}
        return filtered_user

    return user_dict

@router.post("/generate-presigned-url")
async def generate_presigned_url(
    uid: str = Depends(verify_firebase_token),
    s3_client = Depends(get_s3_client), 
    filename: str = Form(...),
    content_type: str = Form(...)
):
    s3_key = f"profile_images/{uid}_{filename}"
    try:
        presigned_url = s3_client.generate_presigned_url(
            "put_object",
            Params={
                "Bucket": S3_BUCKET_NAME,
                "Key": s3_key,
                "ContentType": content_type
            },
            ExpiresIn=3600  # 1시간 유효
        )
    except ClientError as e:
        raise HTTPException(status_code=500, detail=f"S3 presigned URL 생성 실패: {e}")

    return {"presigned_url": presigned_url, "s3_key": s3_key}


# PATCH: 내 정보 수정
@router.patch("/me")
async def patch_my_info(
    uid: str = Depends(verify_firebase_token),
    db: Session = Depends(get_db),
    s3_client = Depends(get_s3_client), 
    nickname: str = Form(None),
    #profile_image: UploadFile = File(None)
    profile_image_s3_key: str = Form(None)  # 브라우저가 업로드 후 전달
):
    # DB에서 사용자 조회
    user = db.query(User).filter(User.firebase_uid == uid).first()
    if not user:
        raise HTTPException(status_code=404, detail="등록되지 않은 사용자입니다.")

    # 만약 닉네임/이미지 둘 다 보내지 않았다면
    if not nickname and not profile_image_s3_key:
        raise HTTPException(status_code=400, detail="수정할 데이터가 없습니다.")

    # 닉네임 수정
    if nickname:
        user.nickname = nickname

    # # 프로필 이미지 수정: S3 사용
    # if profile_image:
    #     s3 = s3_client
    #     s3_key = f"profile_images/{uid}_{profile_image.filename}"

    #     try:
    #         # S3 업로드 실행
    #         s3.upload_fileobj(
    #             profile_image.file,
    #             S3_BUCKET_NAME,             
    #             s3_key,                     
    #             ExtraArgs={'ContentType': profile_image.content_type}
    #         )

    #         # DB에 저장할 Public URL 생성
    #         user.profile_image = f"https://{S3_BUCKET_NAME}.s3.{S3_REGION}.amazonaws.com/{s3_key}"

    #     except Exception as e:
    #         import traceback
    #         traceback.print_exc() 
    #         raise HTTPException(status_code=500, detail=f"S3 업로드 실패: {e}")

    if profile_image_s3_key:
        # DB에 저장할 Public URL 생성
        user.profile_image = f"https://{S3_BUCKET_NAME}.s3.{S3_REGION}.amazonaws.com/{profile_image_s3_key}"
        
    db.commit()
    db.refresh(user)

    return {
        "message": "회원 정보 수정 성공",
        "nickname": user.nickname,
        "profile_image": user.profile_image
    }