import re
import random 
from typing import List, Dict, Any
from sqlalchemy.orm import Session
import google.genai as genai
from google.genai import types
from langchain_chroma import Chroma
from core.config import GEMMA_API_KEY
from core.models import ChatMessage, Restaurant
from core.geo import calculate_distance
from api.saju import _get_oheng_analysis_data
from saju.message_generator import define_oheng_messages
from vectordb.vectordb_util import get_embeddings, get_chroma_client, COLLECTION_NAME_RESTAURANTS

client = genai.Client(api_key=GEMMA_API_KEY)
model_name = "gemma-3-4b-it"

embeddings = get_embeddings()
chroma_client = get_chroma_client()

vectorstore_restaurants = Chroma(
    client=chroma_client,
    collection_name=COLLECTION_NAME_RESTAURANTS,
    embedding_function=embeddings
)

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

# 오행별 일반화 설명
OHAENG_DESCRIPTION = {
    "목(木)": "상큼하고 신선한 느낌의 음식, 야채가 들어간 가벼운 메뉴",
    "화(火)": "매콤하거나 자극적인 맛의 음식",
    "토(土)": "든든하고 안정감 있는 음식",
    "금(金)": "고소하고 짭짤한 맛의 음식",
    "수(水)": "시원하고 촉촉한 느낌의 음식, 국물이나 음료류"
}

MAX_MESSAGES = 10  # 최근 대화 10개만 기억


# 오행별 음식 목록에서 랜덤으로 count개만큼만 문자열로 반환
def get_food_recommendations_for_ohaeng(oheng: str, count: int = 3) -> str:
    foods = OHAENG_FOOD_LISTS.get(oheng)
    recommended_foods = random.sample(foods, min(count, len(foods)))
    return ', '.join(recommended_foods)

def normalize_to_hangul(oheng_name: str) -> str:
    return re.sub(r'\([^)]*\)', '', oheng_name).strip()


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

# 첫 메시지 생성 - 오행 기반 추천 메시지만
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

NO_RESULT_TEMPLATE = {
    "message": "아쉽게도 **{menu_name}** 메뉴를 파는 식당을 주변 5km 내에서 찾지 못했어. 😢\n\n다른 메뉴를 추천해줄까?",
    "restaurants": [],
    "count": 0
}
    
def build_no_result(menu_name: str):
    data = NO_RESULT_TEMPLATE.copy()
    data["message"] = data["message"].format(menu_name=menu_name)
    return data

# 유사도 검색 - 식당 정보 검색 및 추천 함수
def search_and_recommend_restaurants(menu_name: str, db: Session, lat: float, lon: float, action_type: str) -> Dict[str, Any]:    
    # 검색 쿼리 정의: 사용자가 선택한 메뉴
    query_text = menu_name

    # 2. 벡터DB 유사도 검색
    try:
        restaurant_docs = vectorstore_restaurants.similarity_search(query_text, k=50)
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
        return build_no_result(menu_name)


    # 4. 메뉴명 기반 필터링 (content나 metadata에 메뉴명이 있는지 확인)
    restaurant_ids_from_chroma = []
    chroma_results_map = {}
    
    menu_name_normalized = menu_name.replace(" ", "").lower()  # 공백 제거, 소문자 변환
    
    for doc in restaurant_docs:
        restaurant_id = doc.metadata.get("restaurant_id")
        if not restaurant_id:
            continue
        
        # 중복 체크
        if restaurant_id in restaurant_ids_from_chroma:
            continue
            
        # 메뉴명 매칭 검증
        content = doc.page_content.replace(" ", "").lower()
        menu_metadata = doc.metadata.get("menu", "").replace(" ", "").lower()
        
        # 메뉴명이 content나 menu 메타데이터에 포함되어 있는지 확인
        if menu_name_normalized in content or menu_name_normalized in menu_metadata:
            restaurant_ids_from_chroma.append(restaurant_id)
            chroma_results_map[restaurant_id] = doc
            
    print(f"[DEBUG] 메뉴명 필터링 후: {len(restaurant_ids_from_chroma)}개 식당")

    # 5. 필터링 후 결과 없음
    if not restaurant_ids_from_chroma:
        return build_no_result(menu_name)

        
    # 6. DB에서 식당 정보 조회
    db_restaurants_list = db.query(Restaurant).filter(
        Restaurant.id.in_(restaurant_ids_from_chroma)
    ).all()
    
    db_restaurants_map = {r.id: r for r in db_restaurants_list}
    print(f"[DEBUG] DB 조회 완료: {len(db_restaurants_list)}개 식당 정보")
    
    # 7. 거리 계산, 이미지 처리, 필터링 및 데이터 통합
    temp_restaurants_with_distance = []
    MAX_DISTANCE_KM = 5.0  # 최대 검색 반경 5km
    
    for restaurant_id, doc in chroma_results_map.items():
        restaurant = db_restaurants_map.get(restaurant_id)
        
        if not restaurant:
            continue
            
        # 좌표를 DB 모델 객체에서 가져옵니다.
        rest_lat = getattr(restaurant, 'latitude', None)
        rest_lon = getattr(restaurant, 'longitude', None)
        
        if rest_lat is None or rest_lon is None:
            print(f"[DEBUG] 좌표 없음: {restaurant.name}")
            continue
            
        # 거리 계산 및 필터링
        distance_km = calculate_distance(lat, lon, rest_lat, rest_lon)
        
        if distance_km > MAX_DISTANCE_KM:
            continue
            
        distance_m = int(round(distance_km * 1000))
        
        processed_image_url = None
        if restaurant.image:
            image_links = restaurant.image.split(',')
            first_link = image_links[0].strip()

            if first_link.startswith(("'", '"')) and first_link.endswith(("'", '"')):
                first_link = first_link[1:-1]

            if first_link:
                processed_image_url = first_link
                
        restaurant_data = {
            "id": restaurant.id,
            "name": restaurant.name,
            "category": restaurant.category,
            "address": restaurant.address,
            "lat": rest_lat,
            "lon": rest_lon,
            "distance_km": round(distance_km, 2), 
            "distance_m": distance_m,              
            "description": doc.page_content, 
            "image": processed_image_url,
        }
        temp_restaurants_with_distance.append(restaurant_data)
    
    # 8. 거리순 정렬 및 최종 목록 추출
    temp_restaurants_with_distance.sort(key=lambda x: x["distance_km"])
    recommended_restaurants = temp_restaurants_with_distance[:3]
    
    print(f"[DEBUG] 최종 추천: {len(recommended_restaurants)}개 식당")

    # 9. 최종 응답 구성
    if recommended_restaurants:
        return {
            "initial_message": f"그러면 **{menu_name}** 먹으러 갈 식당 추천해줄게! 😋",
            "restaurants": recommended_restaurants,
            "final_message": "다른 행운의 맛집도 추천해줄까?",
            "count": len(recommended_restaurants)
        }
    else:
        return build_no_result(menu_name)

# 단체 채팅에서 사용자 메시지가 메뉴 추천 요청인지 감지하는 함수
def is_initial_recommendation_request(user_message: str, conversation_history: str) -> bool:
    # 대화 기록에서 봇의 상세 추천 메시지 패턴 확인
    has_bot_recommendation = bool(
        re.search(r"기운이 약하니|기운은.*조절해주는|기운으로 눌러주면", conversation_history)
    )
    
    # 봇의 추천 메시지가 있다면 return
    if has_bot_recommendation:
        return False
    
    # 추천 관련 키워드
    recommendation_keywords = [
        "골라", "추천", "뭐 먹", "뭘 먹", "먹을거", "먹을 거",
        #"점심", "저녁", "아침", "식사", "맛집", "메뉴", "음식",
    ]
    
    # 사용자의 메시지에 추천 관련 키워드가 있는지 확인
    user_message_lower = user_message.lower()
    return any(keyword in user_message_lower for keyword in recommendation_keywords)


# llm 호출 및 응답 반환
def generate_llm_response(conversation_history: str, user_message: str) -> str:
    prompt = f"""
    너는 오늘의 운세와 오행 기운에 맞춰 음식을 추천해주는 챗봇 '밥풀이'야. 
    너의 목표는 사용자의 운세에 부족한 오행 기운을 채워줄 수 있는 음식을 추천하는 거야. 
    첫 인사는 절대 반복금지. 문장은 간결하게 
    
    사용자의 입력 메시지에서 '@밥풀' 멘션 태그는 이미 제거된 상태이니, '@밥풀' 멘션을 언급하지 않고 자연스럽게 답변하면 돼.
    
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

    response = client.models.generate_content(
        model=model_name,
        contents=[prompt],
        config=types.GenerateContentConfig(temperature=0.7)
    )

    llm_response_text = response.text.strip()
        
    return llm_response_text