from fastapi import APIRouter, Depends, Query, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session
from typing import Dict, Any 
from botocore.exceptions import ClientError
from datetime import date, time
from core.firebase_auth import verify_firebase_token # Firebase ID 토큰 검증
from core.db import get_db # DB 세션 의존성
from core.models import User # SQLAlchemy User 모델
from core.s3 import get_s3_client, S3_BUCKET_NAME, S3_REGION 
from saju.saju_service import calculate_today_saju_iljin, recalculate_and_update_saju

router = APIRouter(prefix="/users", tags=["users"])

# 내 정보 조회 API
@router.get("/me")
async def get_my_info(
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
        iljin_data = await calculate_today_saju_iljin(user, db)
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
# @router.patch("/me")
# async def patch_my_info(
#     uid: str = Depends(verify_firebase_token),
#     db: Session = Depends(get_db),
#     s3_client = Depends(get_s3_client), 
#     nickname: str = Form(None),
#     profile_image_s3_key: str = Form(None)  # 브라우저가 업로드 후 전달
# ):
#     # DB에서 사용자 조회
#     user = db.query(User).filter(User.firebase_uid == uid).first()
#     if not user:
#         raise HTTPException(status_code=404, detail="등록되지 않은 사용자입니다.")

#     # 만약 닉네임/이미지 둘 다 보내지 않았다면
#     if not nickname and not profile_image_s3_key:
#         raise HTTPException(status_code=400, detail="수정할 데이터가 없습니다.")

#     # 닉네임 수정
#     if nickname:
#         user.nickname = nickname

#     if profile_image_s3_key:
#         # DB에 저장할 Public URL 생성
#         user.profile_image = f"https://{S3_BUCKET_NAME}.s3.{S3_REGION}.amazonaws.com/{profile_image_s3_key}"
        
#     db.commit()
#     db.refresh(user)

#     return {
#         "message": "회원 정보 수정 성공",
#         "nickname": user.nickname,
#         "profile_image": user.profile_image
#     }
# PATCH: 내 정보 수정
@router.patch("/me")
async def patch_my_info(
    uid: str = Depends(verify_firebase_token),
    db: Session = Depends(get_db),
    nickname: str = Form(None),
    profile_image_s3_key: str = Form(None),  # 브라우저가 업로드 후 전달
    # --- 생년월일/성별 관련 필드 ---
    gender: str = Form(None),
    birth_date: str = Form(None),      
    birth_time: str = Form(None),      
    birth_calendar: str = Form(None),  
    unknown_time: str = Form(None)     
    # ----------------------------
):
    user = db.query(User).filter(User.firebase_uid == uid).first()
    if not user:
        raise HTTPException(status_code=404, detail="등록되지 않은 사용자입니다.")

    has_update_data = any([nickname, profile_image_s3_key, gender, birth_date, birth_time, birth_calendar, unknown_time])
    if not has_update_data:
        raise HTTPException(status_code=400, detail="수정할 데이터가 없습니다.")

    # 닉네임 및 프로필 이미지 수정 (기존 로직 유지)
    if nickname is not None:
        user.nickname = nickname

    if profile_image_s3_key:
        user.profile_image = f"https://{S3_BUCKET_NAME}.s3.{S3_REGION}.amazonaws.com/{profile_image_s3_key}"
        
    # --- 사주 재계산 필요 여부 플래그 ---
    is_saju_data_changed = False 

    # --- 생년월일/달력 수정 로직 ---
    if gender and user.gender != gender:
        user.gender = gender

    if birth_date:
        try:
            new_birth_date = date.fromisoformat(birth_date)
            if user.birth_date != new_birth_date:
                user.birth_date = new_birth_date
                is_saju_data_changed = True # 변경됨
        except ValueError:
            raise HTTPException(status_code=400, detail="유효하지 않은 birth_date 형식입니다. (YYYY-MM-DD)")

    if birth_calendar and user.birth_calendar != birth_calendar:
        user.birth_calendar = birth_calendar
        is_saju_data_changed = True # 변경됨
        
    # --- 태어난 시간 수정 로직 ---
    is_unknown_time = unknown_time == 'true'
    new_birth_time = None
    
    if is_unknown_time:
        new_birth_time = None
    elif birth_time:
        try:
            h, m = map(int, birth_time.split(':'))
            new_birth_time = time(h, m)
        except (ValueError, IndexError):
            raise HTTPException(status_code=400, detail="유효하지 않은 birth_time 형식입니다. (HH:MM)")
    
    # birth_time이 변경되었는지 확인 및 업데이트
    if user.birth_time != new_birth_time:
        user.birth_time = new_birth_time
        is_saju_data_changed = True


    # 사주 정보가 변경되었다면 재계산 로직 실행
    if is_saju_data_changed:
        # 사주 기둥 및 오행 점수를 재계산하고 User 모델을 업데이트
        await recalculate_and_update_saju(user, db) 

    db.commit()
    db.refresh(user)

    return {
        "message": "회원 정보 수정 성공",
        "nickname": user.nickname,
        "profile_image": user.profile_image,
        "gender": user.gender,
        "birthDate": user.birth_date.isoformat(),
        "birthTime": user.birth_time.strftime("%H:%M") if user.birth_time else None,
        "birthCalendar": user.birth_calendar,
    }