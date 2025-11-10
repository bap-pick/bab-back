import requests
import json

# NCP 콘솔에서 복사한 클라이언트ID와 클라이언트Secret 값
client_id = "faq1jcjgjp"
client_secret = "uvZtRjKFHCDCw9lBACgYqJy0EkTy3NPSeAV5qqHM"


# 주소 텍스트
query = ""

#
endpoint = "https://maps.apigw.ntruss.com/map-geocode/v2/geocode"
url = f"{endpoint}?query={query}"

# 헤더
headers = {
    "X-NCP-APIGW-API-KEY-ID": client_id,
    "X-NCP-APIGW-API-KEY": client_secret,
}

# 요청
res = requests.get(url, headers=headers)

# --- 응답 출력 ---
if res.status_code == 200:
    data = res.json()
    # indent=2 : 들여쓰기, ensure_ascii=False : 한글 안 깨지게
    pretty_data = json.dumps(data, indent=2, ensure_ascii=False)
    print(pretty_data)
else:
    # 401 오류 대신 다른 오류가 날 수도 있으니 확인용
    print(f"API 요청에 실패했습니다. 상태 코드: {res.status_code}")
    print(f"응답 내용: {res.text}")