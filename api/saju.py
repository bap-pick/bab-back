from fastapi import APIRouter, Depends, HTTPException, Depends
from sqlalchemy.orm import Session

from core.firebase_auth import verify_firebase_token # Firebase ID 토큰 검증
from core.db import get_db # DB 세션 의존성
from core.models import User # SQLAlchemy User 모델

from typing import Dict, Tuple, List, Any
from saju.oheng_analyzer import classify_and_determine_recommendation 
from saju.saju_service import calculate_today_saju_iljin
from saju.restaurant_recommender import get_top_restaurants_by_oheng
from saju.message_generator import define_oheng_messages

router = APIRouter(prefix="/saju", tags=["saju"])

# 사용자의 사주 오행 데이터 가져오기
def get_user_oheng_scores(db: Session, user_id: str) -> Dict[str, float]:
    user = db.query(User).filter(User.firebase_uid == user_id).first()
    
    if not user:
        raise HTTPException(status_code=404, detail="등록된 사용자를 찾을 수 없습니다.")

    if (user.oheng_wood is None or user.oheng_fire is None or 
        user.oheng_earth is None or user.oheng_metal is None or 
        user.oheng_water is None):
        raise HTTPException(status_code=404, detail="사용자의 오행 분석 데이터가 아직 준비되지 않았습니다.")

    return {
        "목(木)": user.oheng_wood,
        "화(火)": user.oheng_fire,
        "토(土)": user.oheng_earth,
        "금(金)": user.oheng_metal,
        "수(水)": user.oheng_water,
    }
    
# 오행 분석 결과 추출
async def _get_oheng_analysis_data(uid: str, db: Session) -> Tuple[List[str], List[str], str, Dict[str, float]]:
    user = db.query(User).filter(User.firebase_uid == uid).first()
    
    if not user:
        raise HTTPException(status_code=404, detail="등록된 사용자를 찾을 수 없습니다.")

    # 1. 오늘의 일진 기반 오행 비율 계산
    try:
        iljin_data = await calculate_today_saju_iljin(user, db)
        oheng_scores_english = iljin_data["today_oheng_percentages"]
        
        oheng_scores_korean = {
            "목(木)": oheng_scores_english.get("ohengWood", 0.0),
            "화(火)": oheng_scores_english.get("ohengFire", 0.0),
            "토(土)": oheng_scores_english.get("ohengEarth", 0.0),
            "금(金)": oheng_scores_english.get("ohengMetal", 0.0),
            "수(水)": oheng_scores_english.get("ohengWater", 0.0),
        }

    except Exception as e:
        print(f"Error calculating today's saju for {uid}: {e}")
        raise HTTPException(status_code=500, detail="간지 기반 오행 데이터를 가져오는 데 실패했습니다.")
        
    # 2. 오행 비율 유형 분류
    analysis_result = classify_and_determine_recommendation(oheng_scores_korean)
    
    oheng_type = analysis_result["oheng_type"]
    lacking_oheng = analysis_result["primary_supplement_oheng"]
    strong_oheng = analysis_result["secondary_control_oheng"]
    
    return lacking_oheng, strong_oheng, oheng_type, oheng_scores_korean


# 사용자의 사주 오행 비율 분석 결과 반환
@router.get("/analyze")
async def get_personalized_recommendation(
    uid: str = Depends(verify_firebase_token),
    db: Session = Depends(get_db)
):
    # 오행 분석 결과를 가져옴
    lacking_oheng, strong_oheng, oheng_type, oheng_scores_korean = await _get_oheng_analysis_data(uid, db)

    # 규칙 기반 메시지 및 대상 오행 추출
    headline, advice, recommended_ohengs_weights, control_ohengs, strong_ohengs = define_oheng_messages(lacking_oheng, strong_oheng, oheng_type)    

    # 제어 오행 리스트 중복 제거
    unique_control_ohengs = list(set(control_ohengs))
    
    # 디버깅: 부족 오행, 과다 오행, 제어 오행, 가중치 딕셔너리 출력
    print(f"부족 오행: {lacking_oheng}")
    print(f"과다 오행: {strong_ohengs}")
    print(f"제어 오행 (강한 오행의 상극 오행, 중복 제거): {unique_control_ohengs}")
    print(f"오행 가중치 딕셔너리: {recommended_ohengs_weights}")
    
    # 최종 결과 반환
    return {
        "user_id": uid,
        "oheng_analysis_scores": oheng_scores_korean, 
        "user_type": oheng_type, 
        "recommendation_headline": headline, 
        "recommendation_advice": advice, 
        "supplement_oheng": lacking_oheng, 
        "control_oheng": strong_oheng, 
        "recommended_ohengs_weights": recommended_ohengs_weights, # 가중치 딕셔너리 반환
        "recommended_restaurants": [] 
    }

# 오행 맞춤 식당 추천 결과 반환
@router.get("/restaurants")
async def get_recommended_restaurants(
    uid: str = Depends(verify_firebase_token),
    db: Session = Depends(get_db),
    top_k: int = 5 
):
    # 오행 분석 결과를 가져옴
    lacking_oheng, strong_oheng, oheng_type, _ = await _get_oheng_analysis_data(uid, db)
    
    # 추천 오행 가중치 딕셔너리를 추출
    _, _, recommended_ohengs_weights, _, _ = define_oheng_messages(lacking_oheng, strong_oheng, oheng_type)
    
    # 식당 검색 서비스 호출
    recommended_restaurants = get_top_restaurants_by_oheng(
        oheng_weights=recommended_ohengs_weights,
        top_k=top_k
    )

    # 4. 최종 결과 반환
    return {
        "recommended_ohengs_weights_used": recommended_ohengs_weights,
        "restaurants": recommended_restaurants
    }