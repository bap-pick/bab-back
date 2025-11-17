import asyncio
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import firebase_admin
from firebase_admin import credentials
import os
from dotenv import load_dotenv
from api import auth, users, chat, saju, restaurants, scraps, friends
from core.s3 import initialize_s3_client
import uvicorn

# ---------------------------------------------------------
# 1) .env 절대경로로 정확하게 로드
# ---------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ENV_PATH = os.path.join(BASE_DIR, ".env")
load_dotenv(dotenv_path=ENV_PATH, override=True)


# ---------------------------------------------------------
# 2) FastAPI 인스턴스 생성
# ---------------------------------------------------------
app = FastAPI()


# ---------------------------------------------------------
# 3) Firebase 초기화 함수
# ---------------------------------------------------------
def initialize_firebase_sync():
    RENDER_KEY_PATH = "/etc/secrets/firebase-key.json"
    LOCAL_KEY_PATH = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")  # from .env
    FIREBASE_KEY_TO_USE = None
    ENV_NAME = "Unknown"

    # 1) Render 환경 키
    if os.path.exists(RENDER_KEY_PATH):
        FIREBASE_KEY_TO_USE = RENDER_KEY_PATH
        ENV_NAME = "Render Production"

    # 2) 로컬 환경 키 (.env에서 읽기)
    elif LOCAL_KEY_PATH and os.path.exists(LOCAL_KEY_PATH):
        FIREBASE_KEY_TO_USE = LOCAL_KEY_PATH
        ENV_NAME = "Local Development"

    else:
        print(f"Firebase 키 파일을 찾을 수 없습니다. 현재 환경: {ENV_NAME}")

    # 실제 초기화
    if FIREBASE_KEY_TO_USE:
        try:
            cred = credentials.Certificate(FIREBASE_KEY_TO_USE)

            # 이미 초기화된 경우 중복 초기화 방지
            if not firebase_admin._apps:
                firebase_admin.initialize_app(cred)
                print(f"Firebase SDK 초기화 성공 ({ENV_NAME}) 경로: {FIREBASE_KEY_TO_USE}")

        except Exception as e:
            print(f"Firebase 초기화 중 오류 발생: {e}")
            raise RuntimeError(f"Firebase 초기화 실패: {e}")
    else:
        print("경고: Firebase를 사용할 수 없습니다.")


# ---------------------------------------------------------
# 4) S3 초기화
# ---------------------------------------------------------
def initialize_s3_sync():
    s3_client_info = initialize_s3_client()
    if s3_client_info:
        print(s3_client_info)
    else:
        print("S3 클라이언트 초기화 실패")


# ---------------------------------------------------------
# 5) 서버 시작 시 Firebase + S3 초기화
# ---------------------------------------------------------
@app.on_event("startup")
async def startup_event():
    try:
        await asyncio.gather(
            asyncio.to_thread(initialize_firebase_sync),
            asyncio.to_thread(initialize_s3_sync)
        )
    except Exception as e:
        print(f"초기화 중 오류 발생: {e}")
        raise


# ---------------------------------------------------------
# 6) CORS 설정
# ---------------------------------------------------------
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


# ---------------------------------------------------------
# 7) 라우터 등록 (friends 포함)
# ---------------------------------------------------------
app.include_router(auth.router)
app.include_router(users.router)
app.include_router(chat.router)
app.include_router(saju.router)
app.include_router(restaurants.router)
app.include_router(scraps.router)
app.include_router(friends.router)

# ---------------------------------------------------------
# 8) Static 파일 설정
# ---------------------------------------------------------
os.makedirs("static/profile_images", exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")


# ---------------------------------------------------------
# 9) 로컬 실행 시 Uvicorn Run
# ---------------------------------------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=port,
        reload=False   # 주의: reload=True면 비동기 초기화가 꼬릴 수 있음
    )
