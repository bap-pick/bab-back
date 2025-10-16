from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import firebase_admin
from firebase_admin import credentials
import os
from dotenv import load_dotenv
from api import auth, users, saju
from core.s3 import initialize_s3_client
import json 

# 환경 변수 로드 (Render에서는 .env 대신 대시보드 변수가 주로 사용됨)
load_dotenv(override=True)

# 1. 환경 변수 로드
GOOGLE_APPLICATION_CREDENTIALS_JSON = os.getenv("GOOGLE_APPLICATION_CREDENTIALS") 

# Firebase Admin SDK 초기화 
if GOOGLE_APPLICATION_CREDENTIALS_JSON:
    try:
        # JSON 문자열을 딕셔너리로 파싱 (!!! 가장 중요한 수정 !!!)
        cred_dict = json.loads(GOOGLE_APPLICATION_CREDENTIALS_JSON)
        
        # 딕셔너리를 사용하여 Firebase SDK 초기화
        cred = credentials.Certificate(cred_dict)
        
        # 이미 초기화되었는지 확인 후 초기화 진행
        if not firebase_admin._apps:
            firebase_admin.initialize_app(cred)
            print("Firebase SDK 초기화 성공 (JSON 딕셔너리 사용).")
            
    except Exception as e:
        # JSON 파싱 오류나 다른 초기화 오류가 여기서 잡힙니다.
        print(f"Firebase 초기화 중 심각한 오류: {e}")
        pass 
else:
    print("환경 변수 GOOGLE_APPLICATION_CREDENTIALS을 찾을 수 없습니다. (초기화 실패)")
    # 이 메시지가 로그에 보이면 Render 대시보드에서 환경 변수 설정을 재확인해야 합니다.

# 3. S3 클라이언트 초기화
initialize_s3_client()

# FastAPI 앱 생성
app = FastAPI()

RENDER_DOMAIN = "https://bab-back.onrender.com" # Render 주소 추가

origins = [
    "http://127.0.0.1:5500",
    RENDER_DOMAIN,
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,       # 쿠키/세션 허용
    allow_methods=["*"],
    allow_headers=["*"],
)

# 라우터 등록
app.include_router(auth.router)
app.include_router(users.router)
app.include_router(saju.router)