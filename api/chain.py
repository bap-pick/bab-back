import google.genai as genai
from google.genai import types
from core.config import GEMMA_API_KEY
from core.models import ChatMessage
from sqlalchemy.orm import Session
from api.saju import _get_oheng_analysis_data
from saju.message_generator import define_oheng_messages
from typing import List
import random 
import re 
from vectordb.vectordb_util import get_embeddings, get_chroma_client, COLLECTION_NAME_RESTAURANTS
from langchain_chroma import Chroma

client = genai.Client(api_key=GEMMA_API_KEY)
model_name = "gemma-3-4b-it"

# 오행별 음식 목록
OHAENG_FOOD_LISTS = {
    '목(木)': [
        "미네스트로네", "토마토파스타", "케밥", "또르띠야", "고추잡채", "시저샐러드", 
        "청경채볶음", "비빔밥", "치아씨푸딩", "시푸드샐러드", "루꼴라피자", "스무디볼", 
        "아보카도샐러드", "요거트볼", "그릭요거트", "오트밀", "그래놀라", "시금치", "바질파스타",
        "바질리조또", "샐러드", "월남쌈"
    ],
    '화(火)': [
        "로스트치킨", "국물떡볶이", "페퍼로니피자", "고추짬뽕", "미트볼", "사천닭날개", 
        "비빔국수", "카레떡볶이", "새우튀김", "팔라펠", "카레빵", "마파두부", 
        "마늘볶음밥", "춘권", "닭꼬치", "새우깐풍기", "치킨커틀릿", "고추튀김", 
        "삼선짬뽕", "라조기", "사천탕수육", "고추탕수육", "샤와르마", "치킨너겟", 
        "꿔바새우", "제육김밥", "베이컨버거", "마늘탕수육", "마늘닭", "탕수육", 
        "오징어튀김", "유린기", "인도커리", "깐쇼닭", "프라이드치킨", "로제떡볶이", 
        "깐풍기", "사천짜장", "어향가지", "라볶이", "치즈피자", "바비큐립", 
        "마라새우", "팬케이크", "마라샹궈", "홍쇼육", "닭강정", "치즈떡볶이", 
        "사천두부", "마라탕", "오향장육", "타불레", "고추새우", "떡볶이", 
        "바질파스타", "스팸마요덮밥", "마늘새우", "알리오올리오", "스테이크샐러드", "미트스파게티", 
        "오믈렛", "불닭마요덮밥", "유린새우", "부리또", "가스파초", "오향닭", 
        "브루스케타", "불고기김밥", "꿔바로우", "제육덮밥", "팔락파니르", "새우크림리조또", 
        "카레라면", "비프스튜", "마르게리타피자", "청초새우", "핫도그", "클럽샌드위치", 
        "브라우니", "프렌치토스트", "새우크로켓", "양주볶음밥", "마라훠궈", "파히타", 
        "나초", "깐쇼새우", "고추두부볶음", "북경오리", "토마토계란볶음", "베이컨샐러드", 
        "김말이튀김", "갈릭브레드", "마라새우", "치킨스튜", "도넛", "피자", 
        "비프버거", "팔보채", "양고기꼬치", "홍쇼육", "난자완스", "스테이크", 
        "파파담", "탄두리치킨"
    ],
    '토(土)': [
        "고기만두", "머핀", "베이글", "크림새우", "바게트", "군밤", 
        "쿠키", "핫케이크", "돈까스김밥", "참치마요김밥", "부추전", "피타빵", 
        "떡라면", "크림우동", "버섯리조또", "마카로니샐러드", "감자전", "난", 
        "마카롱", "송이덮밥", "짜춘권", "군고구마", "짜장밥", "후무스", 
        "치즈그라탕", "호빵", "크로켓", "호떡", "햄버거", "돈가스", 
        "브라우니", "포테이토샐러드", "찐만두", "크레페", "리조또", "마카로니앤치즈", 
        "전가복", "감자튀김", "김치전", "라자냐", "김밥", "불고기피자", 
        "라면", "고르곤졸라피자", "감자그라탕", "계란볶음밥", "함박스테이크", "잡채밥", 
        "짜장면", "잔치국수", "샌드위치", "수제버거", "우육면", "타코", 
        "덮밥", "주먹밥", "찹쌀도너츠", "김치라면", "크림파스타", "새우볶음밥", 
        "게살볶음밥", "고르곤졸라피자", "떡꼬치", "멸치주먹밥", "감자핫도그", "치즈볼", 
        "떡산적", "모둠튀김", "떡국", "우동", "무사카", "볶음우동", 
        "쫄면", "계란빵", "유부초밥", "뇨끼", "가지볶음", "비리야니", 
        "감자범벅", "탕수새우", "짜파게티", "새우김밥", "고구마튀김", 
        "돈까스", "고르곤졸라피자"
    ],
    '금(金)': [
        "짜이", "순대볶음", "닭백숙", "오리백숙", "삼계탕", "계란찜", 
        "생선찜", "두부찜", "모두부", "두부구이", "순두부", "순두부찌개", 
        "맑은생선국", "맑은도가니탕", "닭죽", "흰죽", "양파볶음"
    ],
    '수(水)': [
        "해산물리조또", "해삼탕", "유자새우", "어묵꼬치", "하가우", "스튜", 
        "홍합탕", "오뎅", "클램차우더", "새우딤섬", "훠궈", "새우완탕", 
        "해물그라탕", "콘스프", "해파리냉채", "해물누룽지탕", "파스타", "브로콜리수프", 
        "어묵탕", "유산슬밥", "피쉬앤칩스", "도미찜", "샥스핀찜", "짬뽕", 
        "물만두", "양장피", "수블라키", "아사이볼", "삼선우동", "홍합탕"
    ],
}

# 오행별 음식 목록 중 랜덤 count개만큼만 문자열로 반환
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
            f"따라서 {lacking_oheng_str} 기운의 음식을 먹으면 부족함도 채우고, 넘치는 기운까지 잡을 수 있어 😉"
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
    final_message = lacking_advice + control_advice + " 여기서 먹고 싶은 메뉴 하나 고르면 식당까지 바로 추천해줄게!"
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

    # 규칙 2 패턴: '그러면 [음식명1], [음식명2], [음식명3] 중 하나는 어때?'
    pattern_rule2 = re.compile(r"그러면\s+(.*)\s+중\s+하나는\s+어때\?")
    
    # 초기 추천/상세 조언 패턴: '따라서 ... 기운을 채울 수 있는 [음식 목록]을(를) 추천해.'
    pattern_initial_advice = re.compile(r"따라서\s+.*기운을\s+채울\s+수\s+있는\s+(.*)을\s*\(를\)\s*추천해\.")

    for msg in latest_bot_messages:
        content = msg.content.strip()
        
        # 1. 규칙 2 (새로운 메뉴 3가지 추천) 패턴 확인
        match_rule2 = pattern_rule2.search(content)
        if match_rule2:
            food_list_str = match_rule2.group(1).strip()
            # 콤마로 분리하여 리스트로 반환: ['음식명1', '음식명2', '음식명3']
            return [f.strip() for f in food_list_str.split(',')]

        # 2. 초기 추천/상세 조언 패턴 확인
        match_advice = pattern_initial_advice.search(content)
        if match_advice:
            food_list_str = match_advice.group(1).strip()
            # 콤마로 분리하여 리스트로 반환: ['시저샐러드', '토마토파스타', ...]
            return [f.strip() for f in food_list_str.split(',')]
            
        # [MENU_SELECTED] 이후의 식당 추천 메시지는 추천 목록이 아니므로 무시하고 그 이전 메시지로 넘어갑니다.

    # 적절한 메뉴 목록을 찾지 못했다면 빈 리스트 반환
    return []

# 유사도 검색 - 식당 정보 검색 및 추천 함수
def search_and_recommend_restaurants(menu_name: str, db: Session) -> str:
    # 1. ChromaDB 연결
    embeddings = get_embeddings()
    chroma_client = get_chroma_client()

    vectorstore_restaurants = Chroma(
        client=chroma_client,
        collection_name=COLLECTION_NAME_RESTAURANTS,
        embedding_function=embeddings
    )
    
    # 2. 메뉴 이름으로 유사 식당 검색 (k=10)
    search_query = f"'{menu_name}' 메뉴를 판매하는 맛집 식당"
    
    try:
        restaurant_docs = vectorstore_restaurants.similarity_search(search_query, k=10)
    except Exception as e:
        print(f"Chroma 검색 오류: {e}")
        return "검색에 문제가 생겼어. 다시 시도해 줘."

    if not restaurant_docs:
        return f"앗, 아쉽게도 '{menu_name}' 메뉴를 파는 식당 정보는 아직 없어. 다른 메뉴를 추천해 줄까?"

    validated_restaurants = []
    for doc in restaurant_docs:
        content = doc.page_content.strip()
        menu_snippet = doc.metadata.get("menu", "") 
        
        # 식당의 내용(content)이나 메타데이터 메뉴에 menu_name(사용자 요청 메뉴)가 있는지 확인
        if menu_name in content or menu_name in menu_snippet:
            validated_restaurants.append(doc)
            if len(validated_restaurants) >= 3:
                break # 3개만 찾으면 필터링 중단
                
    # 필터링 후에도 결과가 없는 경우 처리
    if not validated_restaurants:
        return f"앗, 아쉽게도 '{menu_name}' 메뉴를 파는 식당 정보는 아직 없어. 다른 메뉴를 추천해 줄까?"
    
    
    # 3. 검색 결과 파싱 및 메시지 조합
    recommendation_messages = []
    
    for idx, doc in enumerate(validated_restaurants, 1):
        content = doc.page_content.strip()
        
        try:            
            # 1. 식당 이름 추출: 문장 시작 부분에 있을 가능성 높음. (이름은 ~에 위치해 있습니다.)
            name_match = re.search(r"^([^은]+)은\s+([^에]+)에\s+위치해\s+있습니다\.", content)
            
            # 2. 카테고리 추출: "주요 카테고리는 [카테고리]이며"
            category_match = re.search(r"주요\s+카테고리는\s+([^이]+)이며", content)
            
            # 3. 메뉴 추출: "메뉴는 [메뉴 목록]입니다." 또는 "메뉴를 제공합니다."
            menu_match = re.search(r"제공합니다\.\s*([^.$]*)", content)
            
            if name_match:
                name = name_match.group(1).strip()
                address = name_match.group(2).strip()
            else:
                # name_match가 없는 경우 메타데이터에서 이름과 주소 가져오기
                name = doc.metadata.get("name", f"식당 {idx}")
                address = doc.metadata.get("address", "주소 불명").split('(')[0].strip()
            
            category = category_match.group(1).strip() if category_match else "카테고리 불명"
            
            menu_snippet = doc.metadata.get("menu", "대표 메뉴 불명") 

            # 최종 추천 문장 생성
            address_snippet = address.split('(')[0].strip()
            
            base_message = f"▪️ **{name}**: {address_snippet}에 있고, 카테고리는 {category}이야."
            
            menu_info = ""
            # 메뉴 스니펫이 있고, 불명확한 값이 아닐 때만 메뉴 정보 추가
            if menu_snippet and menu_snippet not in ["대표 메뉴 불명", "메뉴 정보 없음"]:
                menu_info = f" {menu_snippet} 등의 메뉴를 팔고 있어!"

            recommendation_messages.append(base_message + menu_info)
            
        except Exception as e:
            # 파싱에 실패하면 메타데이터 사용
            name = doc.metadata.get("name", f"식당 {idx}")
            address_snippet = doc.metadata.get("address", "주소 불명").split('(')[0].strip()
            category_meta = doc.metadata.get("category", "불명")
            menu_meta = doc.metadata.get("menu", "불명")
            recommendation_messages.append(
                f"▪️ {name}: {address_snippet}에 있어! (카테고리: {category_meta}) (메뉴: {menu_meta})"
            )
            
    # 4. 최종 메시지 조합
    recommendation_list_str = "\n".join(recommendation_messages)
    
    final_message = (
        f"그러면 **{menu_name}** 을(를) 먹으러 갈 만한 식당 3곳을 추천해 줄게! \n"
        f"{recommendation_list_str}\n\n"
        f"다른 행운의 맛집도 추천해줄까?"
    )
    
    return final_message

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