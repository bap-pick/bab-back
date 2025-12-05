from firebase_admin import auth
from fastapi import HTTPException, Header
import logging

logger = logging.getLogger(__name__)

def verify_firebase_token(authorization: str = Header(...)):
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="토큰 형식이 잘못되었습니다.")
        
    id_token = authorization.split(" ")[1].strip() # 공백 제거 추가
    
    try:
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
    


# WebSocket 연결 시 사용자 인증 처리 
async def get_user_uid_from_websocket_token(id_token: str) -> str:
    logger.info(f"[WS Auth] 토큰 검증 시작, len={len(id_token)}")
    
    if id_token.startswith("Bearer "):
        id_token = id_token.split(" ")[1].strip()
        logger.info("[WS Auth] Bearer 접두사 제거")
    
    try:
        decoded_token = auth.verify_id_token(
            id_token,
            clock_skew_seconds=5
        )
        uid = decoded_token["uid"]
        logger.info(f"[WS Auth] 검증 성공: uid={uid}")
        return uid
    
    except auth.ExpiredIdTokenError as e:
        logger.error(f"[WS Auth] 토큰 만료: {str(e)}")
        raise Exception("토큰이 만료되었습니다")
    except auth.RevokedIdTokenError as e:
        logger.error(f"[WS Auth] 토큰 취소: {str(e)}")
        raise Exception("토큰이 취소되었습니다")
    except Exception as e:
        logger.error(f"[WS Auth] 검증 실패: {type(e).__name__} - {str(e)}")
        raise Exception(f"인증 실패: {str(e)}")