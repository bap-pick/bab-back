from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.responses import Response
import firebase_admin
from firebase_admin import credentials
import os
from dotenv import load_dotenv
from api import auth, users

# 환경 변수 로드 
load_dotenv(override=True)
service_account_path = "/etc/secrets/firebase-key.json" 
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = service_account_path

# Firebase Admin SDK 초기화 
cred = credentials.Certificate(service_account_path)
firebase_admin.initialize_app(cred)

# FastAPI 앱 생성
app = FastAPI()

RENDER_DOMAIN = "https://bab-back.onrender.com" 

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
#app.include_router(saju.router)

os.makedirs("static/profile_images", exist_ok=True)

app.mount("/static", StaticFiles(directory="static"), name="static")