import boto3
from botocore.exceptions import NoCredentialsError
from fastapi import HTTPException
from .config import AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_S3_REGION, AWS_S3_BUCKET_NAME

# S3 클라이언트 및 버킷 정보 설정
S3_CLIENT = None
S3_BUCKET_NAME = AWS_S3_BUCKET_NAME
S3_REGION = AWS_S3_REGION

# S3 클라이언트 초기화 함수
def initialize_s3_client():
    global S3_CLIENT
    
    if not all([AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_S3_REGION, AWS_S3_BUCKET_NAME]):
        print("S3 환경 변수가 설정되지 않았습니다.")
        return None

    try:
        S3_CLIENT = boto3.client(
            's3',
            aws_access_key_id=AWS_ACCESS_KEY_ID,
            aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
            region_name=AWS_S3_REGION
        )
        print("S3 클라이언트 초기화 성공.")
        return S3_CLIENT

    except NoCredentialsError:
        print("AWS 자격 증명(Credentials)이 잘못되었습니다.")
        return None
    except Exception as e:
        print(f"S3 클라이언트 초기화 실패: {e}")
        return None

# FastAPI 의존성 주입용 S3 클라이언트 함수
def get_s3_client():
    # S3 클라이언트가 아직 초기화되지 않았다면 초기화 시도
    if S3_CLIENT is None:
        initialize_s3_client()
    
    if S3_CLIENT is None:
        # 클라이언트가 초기화되지 않았으면 500 에러 반환 (환경 변수 문제나 서버가 정상 실행 중이 아님)
        raise HTTPException(status_code=500, detail="S3 서비스에 접근할 수 없습니다.")
        
    return S3_CLIENT