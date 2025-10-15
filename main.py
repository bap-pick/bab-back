from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import firebase_admin
from firebase_admin import credentials
import os
from dotenv import load_dotenv
from api import auth, users, saju
from core.s3 import initialize_s3_client
import tempfile

# 환경 변수 로드 
load_dotenv(override=True)

GOOGLE_APPLICATION_CREDENTIALS = os.getenv("GOOGLE_APPLICATION_CREDENTIALS") 

# Firebase Admin SDK 초기화 
if GOOGLE_APPLICATION_CREDENTIALS:
    try:
        # JSON 문자열을 임시 파일로 생성
        with tempfile.NamedTemporaryFile(mode='w', delete=False, encoding='utf-8') as tmp_file:
            tmp_file.write(GOOGLE_APPLICATION_CREDENTIALS)
            temp_path = tmp_file.name

        # Firebase SDK에 임시 파일 경로 전달
        cred = credentials.Certificate(temp_path)
        firebase_admin.initialize_app(cred)
        
    except Exception as e:
        print(f"Firebase 초기화 중 오류: {e}")
        pass 
else:
    print("환경 변수 GOOGLE_APPLICATION_CREDENTIALS을 찾을 수 없습니다.")

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