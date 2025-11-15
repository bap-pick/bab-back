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
        "샐러드", "시저샐러드", "아보카도샐러드", "유자샐러드", "그릭요거트", "요거트볼",
        "스무디볼", "바질파스타", "시금치크림파스타", "그린커리", "쌈밥", "월남쌈",
        "냉이된장국", "미역국", "부추전", "비빔밥", "채소비빔밥", "바질리조또",
        "루꼴라피자", "그린스무디", "케일샐러드", "쑥국", "브로콜리볶음", "청경채볶음"
    ],
    '화(火)': [
        "떡볶이", "로제떡볶이", "불닭볶음면", "김치찌개", "부대찌개", "매운탕",
        "짬뽕", "제육볶음", "불고기덮밥", "닭갈비", "불고기", "양념치킨",
        "치킨너겟", "닭강정", "치즈피자", "마르게리타피자", "토마토파스타", "로제파스타",
        "스파이시커리", "고추잡채", "마파두부", "고추탕수육", "사천짜장", "오징어볶음",
        "라볶이", "비빔국수", "닭꼬치", "스테이크", "핫도그", "토마토리조또",
        "불닭마요덮밥", "베이컨버거", "고추두부볶음", "김말이튀김", "피자", "나초"
    ],
    '토(土)': [
        "설렁탕", "삼계탕", "곰탕", "된장찌개", "순두부찌개", "감자탕",
        "오리백숙", "닭죽", "호박죽", "감자전", "감자탕", "크림파스타",
        "크림리조또", "카레라이스", "오므라이스", "함박스테이크", "스테이크덮밥", "돈까스",
        "햄버거", "베이글", "쿠키", "머핀", "크로플", "호떡",
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
            lacking_parts.append(f"{oheng} 기운의 음식 {foods}") 
            
        lacking_foods_str = '과 '.join(lacking_parts)
        
        # 첫 번째 문장: 부족 오행 기운 보충 조언
        lacking_advice = f"{lacking_oheng_str} 기운이 약하니 {lacking_foods_str}을(를) 추천해. "
    
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
            f"{prefix}강한 {strong_oheng_str} 기운은 {control_oheng_str} 기운으로 눌러주면 좋아! "
            f"따라서 {control_oheng_str} 기운을 채울 수 있는 {control_foods_str}을(를) 추천해."
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

    for doc in validated_restaurants[:3]:
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

    prompt = (
        "너는 오늘의 운세와 오행 기운에 맞춰 음식을 추천해주는 챗봇 '밥풀이'야. "
        "너의 목표는 사용자의 운세에 부족한 오행 기운을 채워줄 수 있는 음식을 추천하는 거야. "
        "항상 반말로 대화해. "
        "첫 인사(예: '안녕! 나는 오늘의 운세에 맞춰 행운의 맛집을 추천해주는 밥풀이야!')는 이미 보냈으니까 절대 다시 하지 마. "

        "[출력 지침] "
        "너는 오직 아래 대화 규칙 중 하나를 골라, 그 규칙에 명시된 형식으로만 답변해야 해. "

        "[대화 규칙]"
        "1. 사용자가 음식과 관련 없는 질문이나 감정 표현을 하면 "
        "  (예: 피곤해, 귀찮아, 씻기 싫다, 심심하다, 졸리다, 외로워, 공부하기 싫어, 짜증난다, '오늘 정말 지친다' 등), "
        "  감정에는 짧게 공감하되, 자세한 대화나 설명은 하지 마. "
        "  답변은 오직 다음 형식(템플릿) 중 하나를 선택해야 해. 다른 텍스트는 추가하지 마:"
        "  * 형식 1 (공감 후 유도): '힘들었구나. 네 운세에 좋은 기운을 채워줄 음식이라도 골라봐!'"
        "  * 형식 2 (공감 후 유도): '많이 피곤하겠다. 오행 기운을 북돋아 줄 메뉴를 어서 골라봐.'"
        "  이 상황에서는 절대로 직접적인 음식 이름, 메뉴 목록, 식당에 대한 언급을 하지 마. 특히, 규칙 2의 '그러면 ~ 어때?' 형식은 절대 금지야."
        "  절대로 스스로 메뉴를 선택하여 [MENU_SELECTED] 태그를 반환하면 안 돼. 이는 사용자가 메뉴를 명확히 선택할 때만 허용돼."

        "2. 사용자가 '다른 메뉴', '다른 거', '~ 빼고', '별로야', '바꿔줘', '안 땡겨' 같은 말을 하면 "
        f"  그건 이전 추천을 거부한 거야. 이전에 추천한 메뉴 목록 {current_foods_str}는 **절대로 다시 언급하지 말고**, LLM의 지식 기반을 활용하여 **3가지의 완전히 새로운 메뉴**를 생성해야 해."
        "  답변은 딱 한 문장으로 이렇게 말해: "
        "  '그러면 [음식명1], [음식명2], [음식명3] 중 하나는 어때?' "
        "  운세나 오행 언급 없이 음식 이름만 제시해. "

        "3. 사용자가 '~ 좋다', '~ 먹을래', '~ 먹고 싶어', '~로 할게', '~ 알려줘' 등 특정 메뉴를 확정 짓는 표현을 사용하거나, "
        "  이전에 추천된 메뉴 중 하나를 긍정적으로 언급하며 확정하면 (예: '비빔밥 좋다!'), "
        "  이전에 추천했든, 사용자가 새로 요청했든, 사용자가 최종 선택한 그 음식 이름으로 **오직 [MENU_SELECTED:메뉴 이름] 형태로만 반환해야 해.** "
        "  이 태그 외의 다른 대화 텍스트(예: 오행 설명, 공감 표현, 질문)는 단 1글자도 추가하면 안 돼. 오직 태그 하나만 반환해야 해."
        "  절대로 규칙 2의 형태('그러면 ~ 어때?')를 반환해서는 안 돼."
        "  예시 1: 사용자가 '비빔밥 좋다!'라고 하면, 응답은 **'[MENU_SELECTED:비빔밥]'**여야 해."
        "  예시 2: 사용자가 '파스타 먹을래'라고 하면, 응답은 '[MENU_SELECTED:파스타]'여야 해."
        "  이 태그 외의 응답은 규칙 1 또는 2를 적용해야 해."

        "대화 전체에서 반말 유지, 문장은 간결하고 친절하게. "
        "지금부터 사용자의 입력이 들어올 거야. "
        "입력에 따라 위 규칙 중 하나를 골라서 적용해. "
        "입력이 규칙 1에 해당하면 음식 이름을 절대 내뱉지 말고 오행만 언급해. "
        "규칙 2나 3일 때만 음식 이름을 말해.\n\n"
        f"{conversation_history}"
        f"사용자: {user_message}"
    )

    response = client.models.generate_content(
        model=model_name,
        contents=[prompt],
        config=types.GenerateContentConfig(temperature=0.7)
    )

    llm_response_text = response.text.strip()
        
    return llm_response_text