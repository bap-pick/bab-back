import os
from dotenv import load_dotenv

load_dotenv()

FIREBASE_API_KEY = os.getenv("FIREBASE_API_KEY")
GEMMA_API_KEY = os.getenv("GEMMA_API_KEY")
GOOGLE_APPLICATION_CREDENTIALS = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")

DB_HOST = os.getenv("DB_HOST")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_NAME = os.getenv("DB_NAME")
DB_PORT = os.getenv("DB_PORT", 3306)

AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
AWS_S3_BUCKET_NAME = os.getenv("AWS_S3_BUCKET_NAME")
AWS_S3_REGION = os.getenv("AWS_S3_REGION")

CHROMA_HOST = os.getenv("CHROMA_HOST", "localhost")
CHROMA_PORT = int(os.getenv("CHROMA_PORT", 8001))