from google import genai
from google.genai import types
from datetime import datetime
import pymysql, os, json, re
from dotenv import load_dotenv

load_dotenv()

api_key = os.getenv("GEMMA_API_KEY")
client = genai.Client(api_key=api_key)
model_name = "gemma-3-4b-it"


def load_fortune(birth_date: str = "2000년 10월 28일", gender: str = "여성"):
    global today_fortune
    
    # 오늘의 운세
    today = datetime.today()
    today_str = today.strftime("%Y년 %m월 %d일")
    
    # LLM 프롬프트 생성
    prompt = f"""
    오늘 날짜는 {today_str}입니다.
    {birth_date}에 태어난 {gender}의 오늘 운세를 알려주세요.
    Disclaimer는 제외해주세요.
    """
    try:
        response = client.models.generate_content(
            model=model_name,
            contents=prompt,
            config=types.GenerateContentConfig(temperature=0.5, topP=0.9)
        )
        today_fortune = response.text.strip()
        return today_fortune
    except Exception as e:
        today_fortune = "오늘 운세를 불러오지 못했습니다."
        return today_fortune

# 여기서부터는 식당 db 조회해서 사용자의 메시지에 맞는 식당 추천
# 이 코드에선 안 됨 다른 코드에선 됐는데
def is_restaurant_question_llm(user_input: str):
    prompt = f"""
    아래 질문이 식당이나 음식 추천과 관련이 있는지 판단해 주세요.
    질문: "{user_input}"
    답변은 'yes' 또는 'no'로만 해주세요.
    """
    response = client.models.generate_content(
        model=model_name,
        contents=prompt,
        config=types.GenerateContentConfig(temperature=0)
    )
    answer = response.text.strip().lower()
    return answer == "yes"

def handle_user_question_with_fortune(user_input: str, fortune: str):
    # 예: 식당 관련 질문이면 기존 로직, 일반 질문이면 LLM에게 답변
    if is_restaurant_question_llm(user_input):
        # 식당 질문이면 운세도 고려
        user_input_with_context = f"오늘 운세: {fortune}\n사용자 질문: {user_input}"
        return get_llm_response(user_input_with_context)
    else:
        # 일반 질문
        response = client.models.generate_content(
            model=model_name,
            contents=f"오늘 운세: {fortune}\n사용자 질문: {user_input}",
            config=types.GenerateContentConfig(temperature=0.7, topP=0.9)
        )
        return response.text.strip()


def get_llm_response(user_input: str):
    # 1. 조건 추출
    prompt_json = f"""
    식당에 대한 사용자의 질문에서 SQL 쿼리 조건을 추출해줘.
    사용자의 질문에서 지역, 카테고리, 메뉴, 편의시설(간편결제, 남/녀 화장실 구분, 단체 이용 가능, 대기공간, 무선 인터넷, 무한 리필, 반려동물 동반, 배달, 비건 메뉴, 유기농 메뉴, 유아시설, 유아의자, 장애인, 휠체어, 주차, 포장 이 중에 문자열이 있으면 해당 문자열 넣기)을 JSON으로만 반환해."
    질문에 언급되지 않은 필드는 NULL을 사용해. 절대 설명하지 말고 JSON만 출력해

    예시:
    입력: 도봉구에 있는 반려동물 동반이 가능한 카페 추천해줘
    출력: {{"address": "도봉구", "category": "카페", "facilities":"반려동물 동반"}}

    입력: 도봉구에 있는 포장 가능한 중식 식당 추천해줘
    출력: {{"address": "도봉구", "category": "중식",  "facilities":"포장"}}
    
    입력: 도봉구에 비건 식당 알려줘
    출력:  {{"address": "도봉구", "category": "null",  "facilities":"비건 메뉴"}}

    질문: {user_input}
    """
    extract = client.models.generate_content(
        model=model_name,
        contents=prompt_json,
        config=types.GenerateContentConfig(temperature=0.1, topP=0.9, maxOutputTokens=125)
    )
    raw_text = extract.text.strip().strip("```").strip()
    match = re.search(r'(\{.*\})', raw_text, re.DOTALL)
    if match:
        conditions = json.loads(match.group(1))
    else:
        conditions = {}

    # 2. DB 조회
    conn = pymysql.connect(
        host=os.getenv("DB_HOST"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        database=os.getenv("DB_NAME"),
        port=int(os.getenv("DB_PORT")),
        charset='utf8mb4'
    )
    cursor = conn.cursor(pymysql.cursors.DictCursor)
    sql = "SELECT r.name, r.category, r.address, GROUP_CONCAT(f.name) AS facilities FROM Restaurants r LEFT JOIN RestaurantFacilities rf ON r.id = rf.restaurant_id LEFT JOIN Facilities f ON rf.facility_id = f.id WHERE 1=1"
    if conditions.get("address"):
        sql += f" AND r.address LIKE '%{conditions['address']}%'"
    if conditions.get("category") and conditions['category'].lower() != "null":
        sql += f" AND r.category LIKE '%{conditions['category']}%'"
    if conditions.get("facilities") and conditions['facilities'].lower() != "null":
        sql += f"""
        AND r.id IN (
            SELECT rf2.restaurant_id
            FROM RestaurantFacilities rf2
            JOIN Facilities f2 ON rf2.facility_id = f2.id
            WHERE f2.name = '{conditions['facilities']}'
        )
        """
    sql += " GROUP BY r.id;"
    cursor.execute(sql)
    rows = cursor.fetchall()
    cursor.close()
    conn.close()

    results = []
    for row in rows[:5]:
        results.append({
            "name": row['name'],
            "category": row['category'],
            "address": row['address'],
            "facilities": row['facilities'].split(',') if row['facilities'] else []
        })

    # 3. 자연어 추천 생성
    llm_prompt = f"""
    사용자가 '{user_input}'라고 질문했습니다.
    조회된 식당 데이터 상위 5개:
    {results}
    이름과 위치, 카테고리 정보를 포함해 자연스럽게 추천 문장으로 만들어주세요.
    """
    response = client.models.generate_content(
        model=model_name,
        contents=llm_prompt,
        config=types.GenerateContentConfig(temperature=0.5, topP=0.9)
    )
    return response.text.strip()
