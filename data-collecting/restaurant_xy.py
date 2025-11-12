import os
import pymysql
import pandas as pd
from dotenv import load_dotenv

# 1. .env 로드
load_dotenv()

# 2. DB 연결
conn = pymysql.connect(
    host=os.getenv("DB_HOST"),
    user=os.getenv("DB_USER"),
    password=os.getenv("DB_PASSWORD"),
    database=os.getenv("DB_NAME"),
    port=int(os.getenv("DB_PORT")),
    charset='utf8mb4'
)
cur = conn.cursor()

# 3. CSV 파일 불러오기
# 예: 식당_좌표.csv 파일에 'id', 'latitude', 'longitude' 컬럼이 있어야 함
csv_path = "식당_좌표.csv"
df = pd.read_csv(csv_path)

# 4. 데이터 확인 (앞부분만)
print(df.head())

# 5. 데이터베이스 업데이트
try:
    sql = "UPDATE Restaurants SET latitude = %s, longitude = %s WHERE id = %s"
    data = [(row['latitude'], row['longitude'], row['id']) for _, row in df.iterrows()]
    cur.executemany(sql, data)
    conn.commit()
    print(f"{cur.rowcount}개의 행이 업데이트되었습니다.")

except Exception as e:
    print("오류 발생:", e)
    conn.rollback()

finally:
    cur.close()
    conn.close()
