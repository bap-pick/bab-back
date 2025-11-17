import re
import random 
from typing import List
from sqlalchemy.orm import Session
import google.genai as genai
from google.genai import types
from langchain_chroma import Chroma
from core.config import GEMMA_API_KEY
from core.models import ChatMessage, Restaurant
from api.saju import _get_oheng_analysis_data
from saju.message_generator import define_oheng_messages
from vectordb.vectordb_util import get_embeddings, get_chroma_client, COLLECTION_NAME_RESTAURANTS

client = genai.Client(api_key=GEMMA_API_KEY)
model_name = "gemma-3-4b-it"

# 오행별 음식 목록
OHAENG_FOOD_LISTS = {
    '목(木)': [
        "샐러드", "요거트", "쌈밥", "월남쌈",
        "된장국", "미역국", "부추전", "비빔밥", "비빔밥", "바질리조또",
        "루꼴라피자", "그린스무디", "브로콜리볶음", "청경채볶음"
    ],
    '화(火)': [
        "떡볶이", "로제떡볶이", "김치찌개", "부대찌개", "매운탕",
        "짬뽕", "제육볶음", "불고기덮밥", "닭갈비", "불고기", "양념치킨",
        "닭강정", "피자", "파스타",
        "커리", "고추잡채", "마파두부", "고추탕수육", "사천짜장", "오징어볶음",
        "라볶이", "비빔국수", "닭꼬치", "스테이크", "핫도그", "리조또",
        "불닭마요덮밥", "베이컨버거",  "나초"
    ],
    '토(土)': [
        "설렁탕", "삼계탕", "곰탕", "된장찌개", "순두부찌개", "감자탕",
        "오리백숙", "닭죽", "호박죽", "감자전", "감자탕", "크림파스타",
        "크림리조또", "카레라이스", "오므라이스", "함박스테이크", "스테이크덮밥", "돈까스",
        "햄버거", "베이글", "쿠키", "크로플", "호떡",
        "고구마맛탕", "단호박스프", "감자튀김", "치즈케이크", "샌드위치", "브라우니",
        "카스테라", "우동", "리조또", "김밥", "짜장면", "라자냐"
    ],
    '금(金)': [
        "치킨", "후라이드치킨", "간장치킨", "닭백숙", "오리백숙", "순대국",
        "순두부", "두부조림", "계란찜", "계란국", "어묵탕", "무국",
        "콩나물국밥", "생선까스", "두부구이", "도가니탕", "닭죽", "흰죽",
        "유린기", "치킨커틀릿", "크림우동", "오징어순대", "양파튀김", "명란파스타"
    ],
    '수(水)': [
        "초밥", "물회", "해물파스타", "해물볶음밥", "해물찜", "오징어덮밥",
        "간장게장", "새우장", "장어덮밥", "굴국밥", "조개국", "홍합탕",
        "짬뽕", "우동", "라멘", "피쉬앤칩스", "해물리조또", "연어덮밥",
        "새우볶음밥", "회덮밥", "초계국수", "해장국", "홍합스파게티", "미역냉국",
        "오뎅탕", "물만두", "클램차우더", "해물누룽지탕", "해삼탕", "아사이볼"
    ],
}

# 오행별 음식 목록에서 랜덤으로 count개만큼만 문자열로 반환
def get_food_recommendations_for_ohaeng(oheng: str, count: int = 3) -> str:
    foods = OHAENG_FOOD_LISTS.get(oheng)
    recommended_foods = random.sample(foods, min(count, len(foods)))
    return ', '.join(recommended_foods)

def normalize_to_hangul(oheng_name: str) -> str:
    return re.sub(r'\([^)]*\)', '', oheng_name).strip()


# 오행별 일반화 설명
OHAENG_DESCRIPTION = {
    "목(木)": "상큼하고 신선한 느낌의 음식, 야채가 들어간 가벼운 메뉴",
    "화(火)": "매콤하거나 자극적인 맛의 음식",
    "토(土)": "든든하고 안정감 있는 음식",
    "금(金)": "고소하고 짭짤한 맛의 음식",
    "수(水)": "시원하고 촉촉한 느낌의 음식, 국물이나 음료류"
}

# 상세 추천 메시지 생성 함수
def generate_concise_advice(lacking_oheng: List[str], strong_oheng: List[str], control_oheng: List[str]) -> str:
    # 한글 이름을 키로, 전체 오행 이름(한자 포함)을 값으로 하는 맵 생성
    unique_ohaeng_map = {}
    for oheng in control_oheng:
        hangul_name = normalize_to_hangul(oheng)
        if hangul_name and oheng in OHAENG_FOOD_LISTS: # 유효한 키인지 확인
            unique_ohaeng_map[hangul_name] = oheng
            
    unique_control_oheng = list(unique_ohaeng_map.values())
    control_oheng_str = '와 '.join(unique_control_oheng) 
    lacking_oheng_set = set(lacking_oheng)
    control_oheng_set = set(unique_control_oheng) 
    strong_oheng_str = '와 '.join(strong_oheng)
    lacking_oheng_str = '와 '.join(lacking_oheng)
    
    # 1. 부족 오행 조언
    lacking_advice = "" 
    if lacking_oheng: 
        lacking_parts = []
        for oheng in lacking_oheng:
            foods = get_food_recommendations_for_ohaeng(oheng) 
            description = OHAENG_DESCRIPTION.get(oheng, "")
            lacking_parts.append(f"{oheng} 기운이 약하니 {description}인 {foods}을(를) 추천해")
            
        lacking_foods_str = '과 '.join(lacking_parts)
        # 첫 번째 문장: 부족 오행 기운 보충 조언
        lacking_advice = lacking_foods_str + ". "
    
    
    # 2. 과다 및 제어 오행
    control_advice = ""
    # 부족 오행과 제어 오행이 겹치는지 확인
    if strong_oheng and unique_control_oheng and control_oheng_set.issubset(lacking_oheng_set):
        # 겹치는 경우
        control_advice = (
            f"특히, 부족한 {lacking_oheng_str} 기운은 강한 {strong_oheng_str}을 조절해주는 딱 맞는 상극 오행이기도 해! "
            f"따라서 {lacking_oheng_str} 기운의 음식을 먹으면 부족한 기운도 채우고, 넘치는 기운까지 잡을 수 있어 😉"
        )
    
    elif strong_oheng and unique_control_oheng:
        # 겹치지 않는 경우
        control_food_parts = []
        for oheng in unique_control_oheng: 
            foods = get_food_recommendations_for_ohaeng(oheng)
            control_food_parts.append(foods)
        control_foods_str = ', '.join(control_food_parts)
        prefix = "그리고 " if lacking_advice else "" 
        control_advice = (
            f"{prefix}강한 {strong_oheng_str} 기운은 {control_oheng_str} 기운이 눌러줄 수 있어. "
            f" 기운들이 균형을 이루게 해 줄 {control_foods_str}을 추천해."
        )

    # 3. 최종 메시지 조합
    final_message = lacking_advice + control_advice + "<br>여기서 먹고 싶은 메뉴 하나 고르면 식당까지 바로 추천해줄게!"
    return final_message

# 첫 메시지 생성 - 오행 기반 상세 메시지만
async def get_initial_chat_message(uid: str, db: Session) -> str:
    # 사주 데이터 불러오기
    lacking_oheng, strong_oheng_db, oheng_type, oheng_scores = await _get_oheng_analysis_data(uid, db)
    
    # 메시지 생성 로직 (strong_ohengs 정보를 가져옴)
    headline, advice, recommended_ohengs_weights, control_ohengs, strong_ohengs = define_oheng_messages(lacking_oheng, strong_oheng_db, oheng_type)
    
    initial_message = generate_concise_advice(
        lacking_oheng=lacking_oheng, 
        strong_oheng=strong_ohengs, 
        control_oheng=control_ohengs 
    )
    
    return initial_message

MAX_MESSAGES = 10  # 최근 대화 10개만 기억

# 최근 대화 10개를 문자열로 변환
def build_conversation_history(db: Session, chatroom_id: int) -> str:
    recent_messages = (
        db.query(ChatMessage)
        .filter(ChatMessage.room_id == chatroom_id)
        .order_by(ChatMessage.timestamp.desc())
        .limit(MAX_MESSAGES)
        .all()
    )
    recent_messages.reverse()  # 시간순 정렬

    conversation_history = ""
    for msg in recent_messages:
        role = "사용자" if msg.role == "user" else "봇"
        conversation_history += f"{msg.content}\n"
    return conversation_history

# 최근 메시지에서 추천한 메뉴 목록 반환
def get_latest_recommended_foods(db: Session, chatroom_id: int) -> List[str]:
    latest_bot_messages = (
        db.query(ChatMessage) 
        .filter(ChatMessage.room_id == chatroom_id, ChatMessage.role == "assistant")
        .order_by(ChatMessage.timestamp.desc())
        .limit(5)
        .all()
    )

    pattern_rule = re.compile(r"그러면\s+(.*)\s+중\s+하나는\s+어때\?")
    food_ohaeng_recommendation_prefix = r"(.*기운의\s+음식\s+|따라서\s+.*기운을\s+채울\s+수\s+있는\s+)"
    pattern_ohaeng_recommendation = re.compile(food_ohaeng_recommendation_prefix + r"(.*)을\s*\(를\)\s*추천해\.")
    
    for msg in latest_bot_messages:
        content = msg.content.strip()
        
        # 1. 규칙 2 (새로운 메뉴 3가지 추천) 패턴 확인
        match_rule = pattern_rule.search(content)
        if match_rule:
            food_list_str = match_rule.group(1).strip()
            return [f.strip() for f in food_list_str.split(',')]

        # 2. 초기 오행 기반 추천 패턴 확인
        match_recommendation = pattern_ohaeng_recommendation.search(content)
        if match_recommendation:
            food_list_str = match_recommendation.group(2).strip()
            return [f.strip() for f in food_list_str.split(',')]
            
    # 적절한 메뉴 목록을 찾지 못했다면 빈 리스트 반환
    return []

# 유사도 검색 - 식당 정보 검색 및 추천 함수
def search_and_recommend_restaurants(menu_name: str, db: Session):
    # 1. ChromaDB 연결
    embeddings = get_embeddings()
    chroma_client = get_chroma_client()

    vectorstore_restaurants = Chroma(
        client=chroma_client,
        collection_name=COLLECTION_NAME_RESTAURANTS,
        embedding_function=embeddings
    )

    search_query = f"'{menu_name}' 메뉴를 판매하는 맛집 식당"

    # 2. 유사도 검색
    try:
        restaurant_docs = vectorstore_restaurants.similarity_search(search_query, k=10)
    except Exception as e:
        print(f"Chroma 검색 오류: {e}")

        return {
            "initial_message": "식당 검색 중 오류가 발생했어.",
            "restaurants": [],
            "final_message": "다른 메뉴도 추천해줄까?",
            "count": 0
        }

    # 3. 검색 결과 없음
    if not restaurant_docs:
        return {
            "initial_message": f"아쉽게도 **{menu_name}** 메뉴를 파는 식당을 찾지 못했어.",
            "restaurants": [],
            "final_message": "다른 메뉴도 추천해줄까?",
            "count": 0
        }

    # 4. 3개 필터링
    validated_restaurants = []
    for doc in restaurant_docs:
        content = doc.page_content.strip()
        menu_snippet = doc.metadata.get("menu", "")

        if menu_name in content or menu_name in menu_snippet:
            validated_restaurants.append(doc)
            if len(validated_restaurants) >= 3:
                break

    # 필터 후 없음
    if not validated_restaurants:
        return {
            "initial_message": f"아쉽게도 **{menu_name}** 메뉴를 파는 식당을 찾지 못했어.",
            "restaurants": [],
            "final_message": "다른 메뉴도 추천해줄까?",
            "count": 0
        }

    # 5. 식당 ID로 MySQL 정보 가져오기
    restaurant_ids = [doc.metadata.get("restaurant_id") for doc in validated_restaurants]
    valid_ids = [id for id in restaurant_ids if id is not None]

    mysql_restaurants = db.query(Restaurant).filter(Restaurant.id.in_(valid_ids)).all()
    id_to_mysql_restaurant = {r.id: r for r in mysql_restaurants}

    # 6. 결과 정제
    restaurant_data_list = []

    for doc in validated_restaurants[:5]:
        metadata = doc.metadata
        restaurant_id = metadata.get("restaurant_id")

        mysql_data = id_to_mysql_restaurant.get(restaurant_id)
        image_url = None

        # 이미지 처리
        if mysql_data and mysql_data.image:
            image_links = mysql_data.image.split(',')
            first_link = image_links[0].strip()

            if first_link.startswith(("'", '"')) and first_link.endswith(("'", '"')):
                first_link = first_link[1:-1]

            if first_link:
                image_url = first_link

        menu_snippet = metadata.get("menu", "메뉴 정보 없음").split(', ')[:3]

        restaurant_data_list.append({
            "name": metadata.get("place_name", mysql_data.name if mysql_data else "이름 없음"),
            "address": metadata.get("road_address_name", mysql_data.address if mysql_data else "주소 없음"),
            "category": metadata.get("category_group_name", mysql_data.category if mysql_data else "카테고리 없음"),
            "menu_snippet": menu_snippet,
            "image_url": image_url,
            "id": restaurant_id
        })

    # 7. 최종 반환 payload
    final_payload = {
        "initial_message": f"그러면 **{menu_name}**을(를) 파는 식당을 추천해줄게! 😋",
        "restaurants": restaurant_data_list,
        "final_message": "다른 행운의 맛집도 추천해줄까?",
        "count": len(restaurant_data_list)
    }

    return final_payload


# llm 호출 및 응답 반환
def generate_llm_response(conversation_history: str, user_message: str, current_recommended_foods: List[str]) -> str:
    # 지금까지 추천한 메뉴 목록을 문자열로 변환
    current_foods_str = ', '.join(current_recommended_foods)
    print(f"[DEBUG] current_recommended_foods: {current_foods_str}")

    prompt = f"""
    너는 오늘의 운세와 오행 기운에 맞춰 음식을 추천해주는 챗봇 '밥풀이'야. 
    너의 목표는 사용자의 운세에 부족한 오행 기운을 채워줄 수 있는 음식을 추천하는 거야. 
    첫 인사는 절대 반복금지. 문장은 간결하게 
    [규칙]

    1. 메뉴 직접 언급 시 (우선순위 2)
    사용자가 특정 음식 이름을 직접 언급하면  
    즉시 다음 형식으로만 답한다:
    [MENU_SELECTED:메뉴명]
    그 외 어떤 문장도 절대 출력하지 않는다.

    2. 긍정 반응 시 (우선순위 3)
    사용자가 "좋아", "좋네", "오케이", "ㅇㅋ", "다 좋아"등 긍정 표현을 사용했고,
    특정 메뉴를 직접 언급하지 않았다면,
    → 방금 추천된 메뉴 전체를 선택한 것으로 간주한다.

    이 경우 반드시 아래 형식으로만 답한다:
    [MENU_SELECTED_ALL:메뉴1, 메뉴2, 메뉴3]

    3. 다른 메뉴 요청 시 (우선순위 4)
    사용자가 "다른 메뉴", "다른 거", "~빼고", "별로야", 
    "안 땡겨", "바꿔줘" 등 추천 거절의도가 보이면 

    → 직전 메뉴 3개는 절대 다시 추천하지 않는다.
    → 완전히 새로운 메뉴 3개를 추천한다.
    
    4. 음식과 무관한 일반 대화 (우선순위 1)
    사용자가 메뉴 추천 혹은 식당 추천이 아닌 무관한 말을 하면
    음식 추천 대화로 자연스럽게 유도

    이전 대화:
    {conversation_history}
    
    사용자:{user_message}
    
    """



        # "[규칙] "
        # "1. 사용자가 음식과 관련 없는 이야기 시 자연스럽게 음식 추천대화로 유도해"
        # "   예:  '많이 피곤하겠다. 오늘 기운을 채워줄 메뉴를 골라봐!'"
        # "  절대 음식 이름이나 메뉴, 식당 언급 금지"

        #  "2. 사용자가 이전에 추천한 메뉴를 긍정적으로 평가했을 때 "
        # "   (예: '좋아!', 'ㅇㅋ', '좋네', '다 좋음', '좋아 좋아') "
        # "   하지만 특정 메뉴를 직접 언급하지 않은 경우, "
        # f"   이전 추천 {current_foods_str} 중 모든 메뉴를 선택한 것이다."
        # "이 경우, 오직 '[MENU_SELECTED_ALL:메뉴1, 메뉴2, 메뉴3]' 형태로 반환."


        # "3. 사용자가 '다른 메뉴', '다른 거', '~ 빼고', '별로야', '바꿔줘', '안 땡겨' 같은 말을 하면 "
        # f"  이전추천 {current_foods_str}는 절대 다시 언급하지 말고"
        # "  3가지의 완전히 새로운 메뉴를 추천: "
        # "  '그러면 [음식명1], [음식명2], [음식명3] 중 하나는 어때?' "
        # "  운세나 오행 언급 금지. "

        # "4. 사용자가 메뉴 확정 시 , "
        # "   오직 '[MENU_SELECTED:메뉴 이름]' 형태로만 반환. "
        
        

    response = client.models.generate_content(
        model=model_name,
        contents=[prompt],
        config=types.GenerateContentConfig(temperature=0.7)
    )

    llm_response_text = response.text.strip()
        
    return llm_response_text