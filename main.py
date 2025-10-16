from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import firebase_admin
from firebase_admin import credentials
import os
from dotenv import load_dotenv
from api import auth, users, saju
from core.s3 import initialize_s3_client
import json 

# 환경 변수 로드
load_dotenv(override=True) 

# Firebase 키 경로 설정
# 1) Render Secret File 경로
RENDER_KEY_PATH = "/etc/secrets/firebase-key.json"
# 2) 로컬 환경 변수에서 경로 로드 (로컬 개발 환경)
LOCAL_KEY_PATH = os.getenv("GOOGLE_APPLICATION_CREDENTIALS") 

# 실행 환경에 따라 사용할 최종 경로 결정
FIREBASE_KEY_TO_USE = None
ENV_NAME = "Unknown"

if os.path.exists(RENDER_KEY_PATH):
    # Render 환경 감지: Secret File이 존재하는 경우
    FIREBASE_KEY_TO_USE = RENDER_KEY_PATH
    ENV_NAME = "Render Production"
elif LOCAL_KEY_PATH and os.path.exists(LOCAL_KEY_PATH):
    # 로컬 환경 감지: LOCAL_FIREBASE_KEY_PATH 변수가 있고 파일이 존재하는 경우
    FIREBASE_KEY_TO_USE = LOCAL_KEY_PATH
    ENV_NAME = "Local Development"
else:
    # 키 파일을 찾을 수 없는 경우
    print(f"Firebase 키 파일을 찾을 수 없습니다. 현재 환경: {ENV_NAME}")

# Firebase Admin SDK 초기화
if FIREBASE_KEY_TO_USE:
    try:
        cred = credentials.Certificate(FIREBASE_KEY_TO_USE)
        
        if not firebase_admin._apps:
            firebase_admin.initialize_app(cred)
            print(f"Firebase SDK 초기화 성공 ({ENV_NAME}). 경로: {FIREBASE_KEY_TO_USE}")
            
    except Exception as e:
        print(f"Firebase 초기화 중 심각한 오류: {e}")
        # 초기화 실패 시 앱이 계속 실행되도록 pass 처리
        pass 
else:
    # 키가 없어 초기화가 불가능한 경우 (대개 로컬 설정 오류)
    print("경고: Firebase를 사용할 수 없습니다. 서비스 기능에 제한이 있을 수 있습니다.")
    

# S3 클라이언트 초기화 (Render/로컬 환경 변수에서 AWS_ACCESS_KEY_ID 등을 사용)
initialize_s3_client()

# FastAPI 앱 생성
app = FastAPI()

RENDER_DOMAIN = "https://bab-back.onrender.com" # Render 주소 추가

origins = [
    "http://127.0.0.1:5500",
    RENDER_DOMAIN,
    "https://bab-front-jet.vercel.app",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,     # 쿠키/세션 허용
    allow_methods=["*"],
    allow_headers=["*"],
)

# 라우터 등록
app.include_router(auth.router)
app.include_router(users.router)
app.include_router(saju.router)