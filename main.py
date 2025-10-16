from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import firebase_admin
from firebase_admin import credentials
import os
from dotenv import load_dotenv
from api import auth, users, saju
from core.s3 import initialize_s3_client
import json 

FIREBASE_KEY_PATH = "/etc/secrets/firebase-key.json" 

# 2. Firebase Admin SDK 초기화 
if os.path.exists(FIREBASE_KEY_PATH):
    try:
        # 파일 경로를 사용하여 Firebase SDK 초기화
        cred = credentials.Certificate(FIREBASE_KEY_PATH)
        
        # 이미 초기화되었는지 확인 후 초기화 진행
        if not firebase_admin._apps:
            firebase_admin.initialize_app(cred)
            print("Firebase SDK 초기화 성공 (Secret File 사용).")
            
    except Exception as e:
        print(f"Firebase 초기화 중 심각한 오류: {e}")
        pass 
else:
    print(f"오류: Firebase Secret File을 찾을 수 없습니다. 경로 확인: {FIREBASE_KEY_PATH}")
    # 이 메시지가 로그에 보이면 Render Secret Files 설정을 다시 확인해야 합니다.
    
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