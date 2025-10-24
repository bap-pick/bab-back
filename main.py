from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import firebase_admin
from firebase_admin import credentials
import os
from dotenv import load_dotenv
from api import auth, users, chat, saju
from core.s3 import initialize_s3_client

# 환경 변수 로드
load_dotenv(override=True) 

# Firebase 키 경로 설정
# 1) Render Secret File 경로
RENDER_KEY_PATH = "/etc/secrets/firebase-key.json"
# 2) 로컬 환경 변수에서 경로 로드 (로컬 개발 환경)
LOCAL_DEV_KEY_PATH = os.getenv("GOOGLE_APPLICATION_CREDENTIALS") 

# 실행 환경에 따라 사용할 최종 경로 결정
FIREBASE_KEY_TO_USE = None
ENV_NAME = "Unknown"

if os.path.exists(RENDER_KEY_PATH):
    # Render 환경 감지: Secret File이 존재하는 경우
    FIREBASE_KEY_TO_USE = RENDER_KEY_PATH
    ENV_NAME = "Render Production"
elif LOCAL_DEV_KEY_PATH and os.path.exists(LOCAL_DEV_KEY_PATH): # 변수명 변경 반영
    # 로컬 환경 감지: LOCAL_DEV_KEY_PATH 변수가 있고 파일이 존재하는 경우
    FIREBASE_KEY_TO_USE = LOCAL_DEV_KEY_PATH
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
        # 초기화 중 오류 발생 시 서버 중단
        print(f"Firebase 초기화 중 오류 발생 및 서버 시작 실패: {e}")
        raise RuntimeError(f"Firebase 초기화 실패: {e}")
else:
    print("경고: Firebase를 사용할 수 없습니다.")


# S3 클라이언트 초기화 및 디버그 로깅
s3_client_info = initialize_s3_client()
if s3_client_info:
    print(s3_client_info)
else:
    print("경고: S3 클라이언트 초기화 실패 (AWS 환경 변수 확인)")


# FastAPI 앱 생성
app = FastAPI()

origins = [
    "http://127.0.0.1:5500",
    "https://bab-back.onrender.com",
    "https://bab-front-jet.vercel.app",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 기존 라우터 등록
app.include_router(auth.router)
app.include_router(users.router)
app.include_router(chat.router)
app.include_router(saju.router)

# Static 파일
os.makedirs("static/profile_images", exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")