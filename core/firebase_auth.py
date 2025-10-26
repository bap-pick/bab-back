from firebase_admin import auth
from fastapi import HTTPException, Header
import logging

logger = logging.getLogger(__name__)

def verify_firebase_token(authorization: str = Header(...)):
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="토큰 형식이 잘못되었습니다.")
        
    id_token = authorization.split(" ")[1].strip() # 공백 제거 추가
    
    try:
        # clock_skew_seconds 인자를 추가하여 5초 허용 오차 추가
        decoded_token = auth.verify_id_token(
            id_token,
            clock_skew_seconds=5
        )
        return decoded_token["uid"]
    
    except Exception as e:
        logger.error(f"에러: {e}")
        
        # 시간 오류
        if "Token used too early" in str(e):
            raise HTTPException(status_code=401, detail="인증 오류: 서버 시각 동기화에 문제가 있습니다.")
        
        # 그 외 일반적인 오류
        raise HTTPException(status_code=401, detail="유효하지 않은 토큰입니다.")