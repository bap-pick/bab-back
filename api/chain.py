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

client = genai.Client(api_key=GEMMA_API_KEY)
model_name = "gemma-3-4b-it"

# 오행별 음식 목록
OHAENG_FOOD_LISTS = {
    '목(木)': [
        "미네스트로네", "토마토파스타", "케밥", "또르띠야", "고추잡채", "시저샐러드", 
        "청경채볶음", "비빔밥", "치아씨푸딩", "시푸드샐러드", "루꼴라피자", "스무디볼", 
        "아보카도샐러드", "요거트볼", "그릭샐러드", "오트밀", "그래놀라", "연어샐러드", 
        "야채김밥", "시금치리조또"
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
    final_message = lacking_advice + control_advice
    return final_message


# 첫 메시지 생성
async def get_initial_chat_message(uid: str, db: Session) -> str:
    # 사주 데이터 불러오기
    lacking_oheng, strong_oheng_db, oheng_type, oheng_scores = await _get_oheng_analysis_data(uid, db)
    
    # 메시지 생성 로직 (strong_ohengs 정보를 가져옴)
    headline, advice, recommended_ohengs_weights, control_ohengs, strong_ohengs = define_oheng_messages(lacking_oheng, strong_oheng_db, oheng_type)
    
    detailed_advice = generate_concise_advice(
        lacking_oheng=lacking_oheng, 
        strong_oheng=strong_ohengs, 
        control_oheng=control_ohengs 
    )
    
    # 첫 메시지 완성
    first_message = (
        "안녕! 나는 오늘의 운세에 맞춰 행운의 맛집을 추천해주는 '밥풀이'야🍀\n\n"
        f"{detailed_advice}"
    )
    return first_message

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

# llm 호출 및 응답 반환
def generate_llm_response(conversation_history: str, user_message: str) -> str:
    prompt = (
        "너는 오늘의 운세와 오행 기운에 맞춰 음식을 추천해주는 챗봇 '밥풀이'야. "
        "너의 목표는 사용자의 운세에 부족한 오행 기운을 채워줄 수 있는 음식을 추천하는 거야. "
        "항상 반말로 대화해. "
        "첫 인사(예: '안녕! 나는 오늘의 운세에 맞춰 행운의 맛집을 추천해주는 밥풀이야!')는 이미 보냈으니까 절대 다시 하지 마. "
        
        "[대화 규칙]"
        "1. 사용자가 음식과 관련 없는 질문이나 감정 표현을 하면 "
        "  (예: 피곤해, 귀찮아, 씻기 싫다, 심심하다, 졸리다, 외로워, 공부하기 싫어, 등), "
        "  감정에는 짧게 공감하되, 자세한 대화나 설명은 하지 마. "
        "  운세에 맞춰 너가 추천할 오행 기운에 대한 이야기만 하며 대화를 메뉴 추천으로 돌려야 해. "
        "  이 상황에서는 절대로 음식 이름, 메뉴 목록, 식당에 대한 언급을 하지 마. 무조건 반말로 해"

        "2. 사용자가 '다른 메뉴', '다른 거', '별로야', '싫어', '바꿔줘' 같은 말을 하면 "
        "  그건 이전 추천을 거부한 거야. 이전에 추천한 메뉴는 절대 다시 언급하지 말고, LLM의 지식 기반을 활용하여 3가지의 완전히 새로운 메뉴를 생성해야 해."
        "  그럴 땐 딱 한 문장으로 이렇게 말해: "
        "  '그러면 [음식명1], [음식명2], [음식명3] 중 하나는 어때?' "
        "  운세나 오행 언급 없이 음식 이름만 제시해. "

        "3. 사용자가 특정 메뉴를 선택하면, "
        "  그 메뉴를 제공하는 식당 3곳을 간단히 추천해. "
        "  식당 이름, 거리, 대표 메뉴만 알려줘. 오행 이야기는 하지 마. 무조건 반말로 해"

        "대화 전체에서 반말 유지, 문장은 간결하고 따뜻하게. "
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

    return response.text.strip() if response.text else "응답 없음"