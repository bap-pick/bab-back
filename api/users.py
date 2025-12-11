from fastapi import APIRouter, Depends, Query, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session
from botocore.exceptions import ClientError
from datetime import date, time
from core.firebase_auth import verify_firebase_token # Firebase ID 토큰 검증
from core.db import get_db # DB 세션 의존성
from core.models import User # SQLAlchemy User 모델
from core.s3 import get_s3_client, S3_BUCKET_NAME, S3_REGION 
from saju.saju_service import calculate_today_saju_iljin, recalculate_and_update_saju
from services.user_cache_service import UserCacheService

router = APIRouter(prefix="/users", tags=["users"])

# 기본 이미지 URL
DEFAULT_PROFILE_IMAGE_KEY = "default/default_profile.png" # S3에 올린 경로와 파일명
DEFAULT_PROFILE_IMAGE_URL = (
    f"https://{S3_BUCKET_NAME}.s3.{S3_REGION}.amazonaws.com/{DEFAULT_PROFILE_IMAGE_KEY}"
)


# 내 정보 조회 API
@router.get("/me")
async def get_my_info(
    uid: str = Depends(verify_firebase_token),
    fields: str = Query(None, description="쉼표로 구분된 필요한 필드 목록"),
    db: Session = Depends(get_db)
):
    cache_service = UserCacheService()
    today = date.today()
    
    user = None # DB에서 조회한 user 객체를 저장할 변수
    
    # 1. 사용자 프로필 캐시 조회 및 user_dict 생성
    cached_profile = cache_service.get_user_profile(uid)
    
    if cached_profile:
        user_dict = cached_profile
    else:
        # DB에서 사용자 조회
        user = db.query(User).filter(User.firebase_uid == uid).first() # firebase_uid 사용
        if not user:
            raise HTTPException(status_code=404, detail="등록되지 않은 사용자입니다.")
        
        # User 객체에서 dict 생성
        user_dict = {
            "email": user.email,
            "nickname": user.nickname,
            "gender": user.gender,
            "birthDate": user.birth_date,
            "birthTime": user.birth_time,
            "birthCalendar": user.birth_calendar,
            "profileImage": user.profile_image,
            "daySky": user.day_sky,
            "ohengWood": user.oheng_wood,
            "ohengFire": user.oheng_fire,
            "ohengEarth": user.oheng_earth,
            "ohengMetal": user.oheng_metal,
            "ohengWater": user.oheng_water,
        }
        # DB 조회 후 캐시 저장
        cache_service.set_user_profile(uid, user_dict)
    
    # 1. S3 기본 이미지 로직 적용
    final_profile_image = user_dict.get('profileImage')
    # None이거나, 빈 문자열이거나, 공백 문자열인 경우 기본 URL로 대체
    if not final_profile_image or not str(final_profile_image).strip(): 
        user_dict['profileImage'] = DEFAULT_PROFILE_IMAGE_URL
        
    # 2. 오늘의 오행 점수 계산
    today_oheng_scores = {} # 오행 점수 결과를 담을 딕셔너리
    should_calculate_oheng = True
    
    if fields:
        requested_fields = set(f.strip() for f in fields.split(","))
        oheng_fields = {"ohengWood", "ohengFire", "ohengEarth", "ohengMetal", "ohengWater"}
        
        # 요청된 필드 목록에 오행 관련 필드가 하나도 없으면 계산을 건너뜀
        if not any(f in requested_fields for f in oheng_fields):
            should_calculate_oheng = False
    
    if should_calculate_oheng:
        # 캐시 조회 로직
        cached_oheng = cache_service.get_user_today_oheng(uid, today)
        
        if cached_oheng:
            today_oheng_scores = cached_oheng
        else:
            # DB 조회(user 객체)가 없으면 캐시된 dict으로 임시 User 객체 재구성
            if not user:
                user = User(
                    firebase_uid=uid, 
                    # user_dict의 데이터로 User 객체의 사주 관련 필드를 복원
                    birth_date=user_dict["birthDate"],
                    birth_time=user_dict["birthTime"],
                    birth_calendar=user_dict["birthCalendar"],
                    day_sky=user_dict["daySky"],
                    oheng_wood=user_dict["ohengWood"],
                    oheng_fire=user_dict["ohengFire"],
                    oheng_earth=user_dict["ohengEarth"],
                    oheng_metal=user_dict["ohengMetal"],
                    oheng_water=user_dict["ohengWater"],
                )
            
            try:
                # 오늘의 일진 계산
                iljin_data = await calculate_today_saju_iljin(user, db)
                today_oheng_scores = iljin_data["today_oheng_percentages"]
                cache_service.set_user_today_oheng(uid, today, today_oheng_scores)
                
            except Exception as e:
                print(f"오행 계산 오류: {e}")
                today_oheng_scores = {
                    "ohengWood": 0.0, "ohengFire": 0.0, 
                    "ohengEarth": 0.0, "ohengMetal": 0.0, "ohengWater": 0.0
                }
    
    # 3. 최종 응답 생성: 계산된 오행 점수를 user_dict에 업데이트
    user_dict.update({
        "ohengWood": today_oheng_scores.get("ohengWood", 0.0),
        "ohengFire": today_oheng_scores.get("ohengFire", 0.0),
        "ohengEarth": today_oheng_scores.get("ohengEarth", 0.0),
        "ohengMetal": today_oheng_scores.get("ohengMetal", 0.0),
        "ohengWater": today_oheng_scores.get("ohengWater", 0.0),
    })
    
    # 필드 필터링: 최종적으로 요청된 필드만 반환
    if fields:
        # 요청된 필드 목록 재사용
        requested_fields = set(f.strip() for f in fields.split(","))
        user_dict = {k: v for k, v in user_dict.items() if k in requested_fields}
    
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
    nickname: str = Form(None),
    profile_image_s3_key: str = Form(None),
    gender: str = Form(None),
    birth_date: str = Form(None),      
    birth_time: str = Form(None),      
    birth_calendar: str = Form(None),  
    unknown_time: str = Form(None)     
):
    cache_service = UserCacheService()

    user = db.query(User).filter(User.firebase_uid == uid).first()
    if not user:
        raise HTTPException(status_code=404, detail="등록되지 않은 사용자입니다.")

    has_update_data = any([nickname, profile_image_s3_key, gender, birth_date, birth_time, birth_calendar, unknown_time])
    if not has_update_data:
        raise HTTPException(status_code=400, detail="수정할 데이터가 없습니다.")

    # 닉네임 및 프로필 이미지 수정
    if nickname is not None:
        user.nickname = nickname

    if profile_image_s3_key:
        user.profile_image = f"https://{S3_BUCKET_NAME}.s3.{S3_REGION}.amazonaws.com/{profile_image_s3_key}"
        
    # 사주 재계산 필요 여부 플래그
    is_saju_data_changed = False 

    # 생년월일/달력 수정 로직
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
        
    # 태어난 시간 수정 로직
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

    # 캐시 무효화
    cache_service.invalidate_user_profile(uid)

    # 새 데이터로 캐시 갱신
    cache_service.set_user_profile(uid, user)
    
    return {
        "message": "회원 정보 수정 성공",
        "nickname": user.nickname,
        "profile_image": user.profile_image,
        "gender": user.gender,
        "birthDate": user.birth_date.isoformat(),
        "birthTime": user.birth_time.strftime("%H:%M") if user.birth_time else None,
        "birthCalendar": user.birth_calendar,
    }