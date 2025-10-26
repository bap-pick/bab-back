import asyncio
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import firebase_admin
from firebase_admin import credentials
import os
from dotenv import load_dotenv
from api import auth, users, chat, saju, restaurants
from core.s3 import initialize_s3_client
import uvicorn

load_dotenv(override=True) 

app = FastAPI()

# Firebase 초기화
def initialize_firebase_sync():
    # Firebase 키 경로 설정
    RENDER_KEY_PATH = "/etc/secrets/firebase-key.json"
    LOCAL_DEV_KEY_PATH = os.getenv("GOOGLE_APPLICATION_CREDENTIALS") 
    FIREBASE_KEY_TO_USE = None
    ENV_NAME = "Unknown"

    if os.path.exists(RENDER_KEY_PATH):
        FIREBASE_KEY_TO_USE = RENDER_KEY_PATH
        ENV_NAME = "Render Production"
    elif LOCAL_DEV_KEY_PATH and os.path.exists(LOCAL_DEV_KEY_PATH):
        FIREBASE_KEY_TO_USE = LOCAL_DEV_KEY_PATH
        ENV_NAME = "Local Development"
    else:
        print(f"Firebase 키 파일을 찾을 수 없습니다. 현재 환경: {ENV_NAME}")
        
    if FIREBASE_KEY_TO_USE:
        try:
            cred = credentials.Certificate(FIREBASE_KEY_TO_USE)
            # 이미 초기화되었는지 확인
            if not firebase_admin._apps:
                firebase_admin.initialize_app(cred)
                print(f"Firebase SDK 초기화 성공 ({ENV_NAME}). 경로: {FIREBASE_KEY_TO_USE}")
            
        except Exception as e:
            print(f"Firebase 초기화 중 오류 발생: {e}")
            # 초기화 실패 시 서버 시작을 막기 위해 예외를 다시 발생
            raise RuntimeError(f"Firebase 초기화 실패: {e}")
    else:
        print("경고: Firebase를 사용할 수 없습니다.")

# S3 클라이언트 초기화
def initialize_s3_sync():
    s3_client_info = initialize_s3_client()
    if s3_client_info:
        print(s3_client_info)
    else:
        print("S3 클라이언트 초기화 실패")
    
@app.on_event("startup")
async def startup_event():
    try:
        await asyncio.gather(
            asyncio.to_thread(initialize_firebase_sync),
            asyncio.to_thread(initialize_s3_sync) 
        )
    except Exception as e:
        print(f"초기화 중 오류 발생: {e}")
        # 초기화 실패 시 서버 시작을 막기 위해 예외 발생
        raise


origins = [
    "http://127.0.0.1:5500",
    "https://bab-back.onrender.com",
    "https://bab-front-jet.vercel.app",]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 라우터 등록
app.include_router(auth.router)
app.include_router(users.router)
app.include_router(chat.router)
app.include_router(saju.router)
app.include_router(restaurants.router)

# Static 파일
os.makedirs("static/profile_images", exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    
    # Uvicorn 실행
    uvicorn.run(
        "main:app", 
        host="0.0.0.0", 
        port=port, 
        reload=False
    )