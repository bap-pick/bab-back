from fastapi import APIRouter, Depends, HTTPException, Depends
from sqlalchemy.orm import Session

from core.firebase_auth import verify_firebase_token # Firebase ID 토큰 검증
from core.db import get_db # DB 세션 의존성
from core.models import User # SQLAlchemy User 모델

from typing import Dict
from saju.oheng_analyzer import classify_and_determine_recommendation 
from saju.message_generator import define_oheng_messages

router = APIRouter(prefix="/saju")

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

# 사용자의 사주 오행 비율 분석 결과 반환
@router.get("/analyze")
async def get_personalized_recommendation(
    uid: str = Depends(verify_firebase_token),
    db: Session = Depends(get_db)
):
    # 1. DB에서 오행 비율 데이터 가져오기
    try:
        oheng_scores = get_user_oheng_scores(db, uid)
    except HTTPException as e:
        raise e
    except Exception as e:
        # 기타 DB 연결 또는 쿼리 오류 처리
        print(f"DB Error fetching user data: {e}")
        raise HTTPException(status_code=500, detail="데이터베이스에서 사용자 데이터를 가져오는 데 실패했습니다.")
        
    # 2. 오행 비율 유형 분류 로직 실행
    analysis_result = classify_and_determine_recommendation(oheng_scores)
    
    oheng_type = analysis_result["oheng_type"]
    lacking_oheng = analysis_result["primary_supplement_oheng"]
    strong_oheng = analysis_result["secondary_control_oheng"]

    # 3. 규칙 기반 메시지 생성
    headline, advice = define_oheng_messages(lacking_oheng, strong_oheng, oheng_type)
    
    # 4. 최종 결과 반환
    return {
        "user_id": uid,
        "oheng_analysis_scores": oheng_scores,   
        "user_type": oheng_type,                 
        "recommendation_headline": headline,     
        "recommendation_advice": advice,         
        "supplement_oheng": lacking_oheng,       
        "control_oheng": strong_oheng,           
        "recommended_restaurants": []            
    }
