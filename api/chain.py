import re
import random 
from enum import Enum
from typing import Tuple
from typing import List
from sqlalchemy.orm import Session
import google.genai as genai
from google.genai import types
from langchain_chroma import Chroma
from core.config import GEMMA_API_KEY
from core.models import ChatMessage, Restaurant
from core.geo import calculate_distance
from vectordb.vectordb_util import get_embeddings, get_chroma_client, COLLECTION_NAME_RESTAURANTS

client = genai.Client(api_key=GEMMA_API_KEY)
model_name = "gemma-3-4b-it"

embeddings = get_embeddings()
chroma_client = get_chroma_client()

# ===============================
#  음식 데이터 정의
#   - 오행별 음식
#   - 음식 속성 태그
#   - 음식 설명(이유)
# ===============================
# 오행별 음식 목록
OHAENG_FOOD_LISTS = {
    '목(木)': [
        "샐러드", "육회비빔밥", "쌈밥", "산채비빔밥",
        "미역국", "부추전",
        "요거트", "포케", "키토김밥", "미역국", "샌드위치"
    ],
    '화(火)': [
        "떡볶이", "로제떡볶이", "김치찌개", "부대찌개",
        "짬뽕", "제육볶음", "닭갈비",
        "불고기", "양념치킨", "닭강정",
        "피자", "파스타",
        "마파두부", "고추잡채", "오징어볶음",
        "라볶이", "비빔국수",
        "불닭", "마라탕", "마라샹궈", "핫도그"
    ],
    '토(土)': [
        "설렁탕", "곰탕", "삼계탕", "순두부찌개",
        "된장찌개", "감자탕",  "스테이크",
        "감자전", "고구마맛탕",
        "오므라이스", "카레라이스",
        "함박스테이크", "돈까스",
        "햄버거", "샌드위치",
        "김밥", "짜장면", "라면",
        "우동", "리조또",
        "베이글", "쿠키", "호떡",
        "치즈케이크", "브라우니", "참치김밥", "뼈해장국"
    ],
    '금(金)': [
        "후라이드치킨", "간장치킨",
        "순대국", "도가니탕",
        "두부조림", "두부구이",
        "계란찜", "계란국",
        "어묵탕", "소머리국밥",
        "콩나물국밥",
        "흰죽",
        "닭죽", "유린기",
        "백숙", "닭가슴살", "순두부"
    ],
    '수(水)': [
        "초밥", "회덮밥",
        "물회", "해물탕",
        "해물찜", "해물파스타",
        "오징어덮밥",
        "간장게장", "새우장",
        "굴국밥", "조개국",
        "미역국",
        "우동", "라멘",
        "물만두", "훠궈", "육회비빔밥",
        "냉면", "메밀소바", "묵사발"
    ]
}

# 음식별 속성 태그
FOOD_TAGS = {
    "국물": [
        "미역국", "설렁탕", "곰탕", "삼계탕", "순두부찌개", "된장찌개", 
        "감자탕", "김치찌개", "부대찌개", "순대국", "도가니탕", 
        "어묵탕", "소머리국밥", "콩나물국밥", "물회", "해물탕", 
        "굴국밥", "조개국", "우동", "라면", "짬뽕", "뼈해장국", "훠궈"
    ],
    
    "면": [
        "우동", "라면", "짬뽕", "짜장면", "파스타", "해물파스타",
        "비빔국수", "라볶이", "라면"
    ],
    
    "매운": [
        "떡볶이", "로제떡볶이", "김치찌개", "부대찌개", "짬뽕",
        "제육볶음", "닭갈비", "양념치킨", "마파두부", "고추잡채",
        "오징어볶음", "라볶이", "비빔국수", "마라샹궈", "마라탕", "불닭"
    ],
    
    "시원한": [
        "물회", "초밥", "회덮밥", "냉면", "샐러드", "포케",
        "육회비빔밥", "산채비빔밥", "요거트"
    ],
    
    "따뜻한": [
        "설렁탕", "곰탕", "삼계탕", "순두부찌개", "된장찌개",
        "감자탕", "김치찌개", "부대찌개", "우동", "라면"
    ],
    
    "가벼운": [
        "샐러드", "쌈밥", "샌드위치", "김밥", "초밥", "요거트",
        "포케", "키토김밥", "베이글"
    ],
    
    "든든한": [
        "설렁탕", "곰탕", "삼계탕", "돈까스", "함박스테이크",
        "햄버거", "김밥", "비빔밥", "오므라이스", "카레라이스"
    ],
    
    "밥": [
        "육회비빔밥", "쌈밥", "산채비빔밥", "오므라이스", "카레라이스",
        "김밥", "참치김밥", "회덮밥", "오징어덮밥", "소머리국밥",
        "콩나물국밥", "굴국밥", "리조또"
    ],
    
    "튀김": [
        "후라이드치킨", "간장치킨", "양념치킨", "닭강정",
        "돈까스", "생선까스", "감자전", "부추전"
    ],
    
    "느끼한": [
        "크림파스타", "로제파스타", "까르보나라",
        "리조또", "치즈돈까스", "함박스테이크",
    ],
    
    "해장": [
        "콩나물국밥", "북엇국", "해장국", "선지해장국",
        "뼈해장국", "라면", "짬뽕", "순두부찌개"
    ],
}

# 음식 설명
FOOD_OHENG_REASONS = {
    # 목(木) - 신선한 채소, 생것
    "샐러드": "신선한 채소가 주재료",
    "육회비빔밥": "생고기와 채소를 날것으로 먹어",
    "쌈밥": "신선한 쌈 채소로 싸먹어",
    "산채비빔밥": "산나물과 채소가 가득",
    "미역국": "미역이라는 해조류가 주재료",
    "부추전": "부추라는 채소를 부쳐서",
    "요거트": "발효 유제품으로 가벼워",
    "포케": "신선한 생선과 채소를 날것으로",
    "키토김밥": "채소가 많이 들어가",
    "샌드위치": "빵에 신선한 채소를 넣어",
    
    # 화(火) - 매운맛, 자극적
    "떡볶이": "고추장으로 맵고 자극적이야",
    "로제떡볶이": "매콤한 로제 소스로",
    "김치찌개": "김치가 들어가 얼큰하고 매워",
    "부대찌개": "고추가루로 얼큰하게",
    "짬뽕": "고추기름으로 맵고 뜨거워",
    "제육볶음": "고추장으로 매콤하게 볶아",
    "닭갈비": "고추장 양념으로 매콤해",
    "불고기": "불에 구워서 따끈해",
    "양념치킨": "매콤달콤한 양념이 발라져",
    "닭강정": "매콤한 소스가 입맛을 자극해",
    "피자": "오븐에서 뜨겁게 구워",
    "파스타": "뜨겁게 볶아서 만들어",
    "마파두부": "고추기름으로 엄청 매워",
    "고추잡채": "고추와 야채를 볶아",
    "오징어볶음": "고추장으로 매콤하게",
    "라볶이": "라면에 떡을 넣어 매콤해",
    "비빔국수": "고추장으로 새콤매콤해",
    "핫도그": "뜨겁게 튀겨서",
    "마라탕": "향신료와 고추기름으로 열과 자극이 강해",
    "마라샹궈": "기름과 향신료로 볶아 화 기운이 강해",

    # 토(土) - 곡물, 달콤, 안정감
    "뼈해장국": "돼지 등뼈를 오래 고아내 진하고 든든해",
    "설렁탕": "사골을 오래 끓여 뿌옇고 든든해",
    "곰탕": "곰처럼 든든하게 고기를 끓여",
    "삼계탕": "닭과 찹쌀, 대추로 든든해",
    "순두부찌개": "두부가 들어가 부드럽고 든든해",
    "된장찌개": "된장이 주재료라 구수하고 든든해",
    "감자탕": "감자가 가득 들어가 든든해",
    "감자전": "감자를 갈아 부쳐서",
    "고구마맛탕": "고구마를 튀겨 달콤해",
    "오므라이스": "밥을 계란으로 감싸 든든해",
    "카레라이스": "카레와 밥으로 든든해",
    "함박스테이크": "다진 고기로 만들어 든든해",
    "돈까스": "고기를 튀겨 든든하고 바삭해",
    "햄버거": "빵과 패티로 든든해",
    "김밥": "밥과 재료를 김으로 말아 든든해",
    "짜장면": "춘장 소스로 달콤하고 면발이 든든해",
    "라면": "면발로 든든하고 얼큰해",
    "우동": "굵은 면발로 든든해",
    "리조또": "쌀을 크림으로 끓여 부드럽고 든든해",
    "베이글": "빵으로 만들어 든든해",
    "쿠키": "밀가루와 설탕으로 달콤해",
    "호떡": "밀가루 반죽에 흑설탕을 넣어 달콤해",
    "치즈케이크": "크림치즈로 부드럽고 달콤해",
    "브라우니": "초콜릿으로 달콤하고 진해",
    "참치김밥": "밥과 참치로 든든해",
    
    # 금(金) - 흰색, 담백, 바삭
    "후라이드치킨": "튀겨서 바삭하고 담백해",
    "간장치킨": "간장으로 담백하게 양념해",
    "순대국": "순대와 내장으로 깊은 맛이 나",
    "도가니탕": "도가니를 오래 끓여 담백해",
    "두부조림": "두부로 만들어 담백해",
    "두부구이": "두부를 구워 담백해",
    "계란찜": "계란으로 만들어 부드럽고 담백해",
    "계란국": "계란을 풀어 담백해",
    "어묵탕": "어묵을 끓여 담백해",
    "소머리국밥": "소머리로 깊고 담백한 맛",
    "콩나물국밥": "콩나물로 시원하고 담백해",
    "생선까스": "생선을 튀겨 담백하고 바삭해",
    "흰죽": "쌀로 끓여 담백하고 부드러워",
    "닭죽": "닭과 쌀로 끓여 담백해",
    "유린기": "닭고기를 튀겨 담백하고 새콤해",
    
    # 수(水) - 시원한, 해산물, 차가운
    "초밥": "생선을 날것으로 차갑게 먹어",
    "회덮밥": "신선한 회를 얹어 시원해",
    "물회": "차가운 육수에 회를 넣어 시원해",
    "해물탕": "해산물을 끓여 시원한 국물이 나",
    "해물찜": "해산물을 쪄서 만들어",
    "해물파스타": "해산물이 들어가",
    "오징어덮밥": "오징어를 볶아 얹어",
    "간장게장": "게를 간장에 재워 짭조름해",
    "새우장": "새우를 간장에 재워",
    "굴국밥": "굴을 넣어 시원한 국물",
    "조개국": "조개를 넣어 시원해",
    "물만두": "만두를 끓는 물에 삶아",
    "훠궈": "끓는 육수에 재료를 넣어",
    "냉면": "차갑고 물기가 많아 수 기운이 강해",
}

# ===============================
# 음식 분류/조회 유틸 함수
# ===============================
# 해당 음식의 오행 찾기
def get_food_oheng(food_name: str) -> str:
    for oheng, foods in OHAENG_FOOD_LISTS.items():
        if food_name in foods:
            return oheng
    return "알 수 없음"

# 해당 음식이 그 오행에 속하는 이유
def get_food_reason(food_name: str) -> str:
    return FOOD_OHENG_REASONS.get(food_name, "그 오행의 특징을 가지고 있어")

# 조건과 오행에 맞는 음식 필터링
def get_foods_by_condition(
    condition: str,
    oheng_list: List[str],
    exclude_foods: List[str] = None
) -> List[str]:
    """
    Args:
        condition: "국물", "면", "매운" 등
        oheng_list: 추천해야 할 오행 리스트
        exclude_foods: 제외할 음식 리스트
    """
    exclude_foods = exclude_foods or []
    
    # 1. 조건에 맞는 음식 가져오기
    condition_foods = set(FOOD_TAGS.get(condition, []))
    
    # 2. 오행에 맞는 음식 가져오기
    oheng_foods = set()
    for oheng in oheng_list:
        oheng_foods.update(OHAENG_FOOD_LISTS.get(oheng, []))
    
    # 3. 교집합 (조건 + 오행 둘 다 만족)
    matched_foods_by_intersection = condition_foods & oheng_foods
    
    # 4. 결과 리스트 초기화
    result_list = list(matched_foods_by_intersection)
    
    # 5. 추천할 음식이 3개 미만일 경우, '조건만 만족하는 음식'으로 채우기
    if len(result_list) < 3:
        
        # '조건만 만족'하지만 '오행 조건은 충족하지 못함' 또는 '오행 정보가 없음' 음식
        supplementary_foods = condition_foods - matched_foods_by_intersection
        
        # 제외 목록에 없는 음식만 필터링
        supplements_to_add = [
            f for f in supplementary_foods 
            if f not in result_list and f not in exclude_foods
        ]
        
        # 무작위로 섞어서 추가할 음식을 고르게 선택
        random.shuffle(supplements_to_add)
        
        # 필요한 개수만큼 추가 (총 3개가 되도록)
        needed_count = 3 - len(result_list)
        result_list.extend(supplements_to_add[:needed_count])
    
    # 6. 최종 제외 목록 제거
    result = [f for f in result_list if f not in exclude_foods]
    
    return result

# 메시지에서 언급된 음식 추출 
def extract_mentioned_foods_from_message(message_content: str) -> List[str]:
    mentioned = []
    
    # 메시지 정규화 (공백 제거)
    normalized_content = message_content.replace(" ", "").replace("\n", "")
    
    # OHAENG_FOOD_LISTS의 모든 음식을 체크
    for oheng, foods in OHAENG_FOOD_LISTS.items():
        for food in foods:
            # 음식명도 정규화해서 비교
            normalized_food = food.replace(" ", "")
            if normalized_food in normalized_content:
                mentioned.append(food)
    
    return list(set(mentioned))  # 중복 제거

# 현재 채팅방에서 봇이 추천한 음식 목록 추출
def get_all_recommended_foods(db: Session, room_id: int) -> List[str]:
    messages = (
        db.query(ChatMessage)
        .filter(
            ChatMessage.room_id == room_id,
            ChatMessage.role == "assistant",
            ChatMessage.message_type == "text"
        )
        .order_by(ChatMessage.timestamp.desc())
        .limit(20)  # 최근 20개만 (너무 많으면 느려짐)
        .all()
    )
    
    all_foods = set()
    
    for msg in messages:
        # 메시지에서 음식명 추출
        foods = extract_mentioned_foods_from_message(msg.content)
        all_foods.update(foods)
    
    print(f"[DEBUG] Room {room_id}에서 추출된 음식: {list(all_foods)}")
    
    return list(all_foods)

# ===============================
# 대화 히스토리 & 의도 분석
# ===============================

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
        # 숨겨진 초기메세지 llm에게 공개 x
        if msg.message_type == "hidden_initial":
            continue
        
        # 역할 명시 (user/assistant 구분)
        if msg.role == "user":
            prefix = "사용자:"
        elif msg.role == "assistant":
            prefix = "밥풀이:"
        else:
            prefix = ""
        
        conversation_history += f"{prefix} {msg.content}\n"

    return conversation_history


# 메시지 의도 분류
class UserIntent(Enum):
    WANT_RECOMMENDATION = "recommendation"  # 메뉴 추천 원함
    SELECT_MENU = "select"  # 메뉴 선택
    ASK_REASON = "reason"  # 이유 질문
    ASK_CONDITION = "condition"  # 조건부 추천 (매운거, 국물 등)
    GENERAL_CHAT = "chat"  # 일반 대화
    POSITIVE_RESPONSE = "positive"  # 긍정 응답 (응, 그래, ㅇㅇ)

# 메시지 의도 감지
def detect_user_intent_improved(
    user_message: str,
    conversation_history: str,
    current_recommended_foods: List[str]
) -> Tuple[UserIntent, dict]:
    msg = user_message.lower().strip()
    
    # 1. 긍정 응답
    positive_patterns = ["응", "ㅇㅇ", "ㅇ", "그래", "좋아", "ok", "okay", "네", "예", "ㅎㅇ", "ㄱㄱ"]
    if msg in positive_patterns:
        if current_recommended_foods:
            return UserIntent.WANT_RECOMMENDATION, {}
        else:
            return UserIntent.WANT_RECOMMENDATION, {}
    
    # 2. 메뉴 선택 패턴
    select_patterns = [
        r'([가-힣]{2,})\s*(먹을래|먹자|할게|하자|좋다|좋네|선택|골랐어|결정)',
        r'([가-힣]{2,})로?\s*먹으러\s*갈?\s*(식당|맛집)',
    ]
    for pattern in select_patterns:
        match = re.search(pattern, user_message)
        if match:
            menu_name = match.group(1).strip()
            for oheng, foods in OHAENG_FOOD_LISTS.items():
                for food in foods:
                    if normalize_text(food) in normalize_text(menu_name) or \
                        normalize_text(menu_name) in normalize_text(food):
                            return UserIntent.SELECT_MENU, {"menu": food}
    
    # 3. 이유/설명 질문
    reason_keywords = ["왜", "이유", "어떻게", "효능", "효과", "뭐가"]
    if any(kw in msg for kw in reason_keywords):
        for oheng, foods in OHAENG_FOOD_LISTS.items():
            for food in foods:
                if normalize_text(food) in normalize_text(user_message):
                    return UserIntent.ASK_REASON, {"menu": food}
        return UserIntent.ASK_REASON, {}
    
    # 4. 메뉴 추천 조건 감지
    condition_keywords = {
        "국물": ["국물", "국", "탕", "찌개", "국밥", "물 있는", "물있는"],
        "면": ["면", "국수", "파스타", "라면", "우동", "짬뽕", "짜장"],
        "매운": ["매운", "매콤", "얼큰", "맵", "불"],
        "자극적인": ["자극", "자극적인", "땡기는", "확 당기는"],
        "시원한": ["시원", "차가운", "냉", "시원한"],
        "따뜻한": ["따뜻", "뜨거운", "따끈", "뜨끈", "뜨끈한", "개운한", "얼큰한"],
        "가벼운": ["가벼운", "담백", "산뜻", "가볍", "담백한", "심심한", "깔끔한"],
        "든든한": ["든든", "배부른", "포만감", "든든한"],
        "밥": ["밥", "라이스", "비빔밥", "덮밥"],
        "튀김": ["튀김", "튀긴", "바삭", "치킨", "까스"],
        "느끼한": ["느끼한", "크리미한", "느끼", "기름진", "꾸덕한", "묵직한", "버터리한", "치즈", "치즈 많은", "헤비한"],
        "해장": ["해장", "속풀", "속 푸는", "숙취", "술먹고", "전날 술", "얼큰한 국", "개운한 국"]
    }
    
    detected_conditions = []
    for condition, keywords in condition_keywords.items():
        if any(kw in msg for kw in keywords):
            detected_conditions.append(condition)
    
    if detected_conditions:
        # 여러 조건이면 첫 번째 것 사용
        return UserIntent.ASK_CONDITION, {"condition": detected_conditions[0]}
    
    # 5. 부정/거부 표현
    negative_keywords = ["별로", "싫", "다른", "아니", "안", "노", "그닥"]
    if any(kw in msg for kw in negative_keywords):
        return UserIntent.WANT_RECOMMENDATION, {}
    
    # 6. 새 메뉴 추천 요청
    recommendation_keywords = [
        "추천", "골라", "뭐 먹", "뭘 먹", "먹을거", "먹을 거",
        "또", "다시", "더"
    ]
    if any(kw in msg for kw in recommendation_keywords):
        return UserIntent.WANT_RECOMMENDATION, {}
    
    # 7. 기본값: 일반 대화
    return UserIntent.GENERAL_CHAT, {}


# ===============================
# 추천 프롬프트
# ===============================
# 메뉴 추천 전용 프롬포트
def generate_recommendation_prompt(
    lacking_oheng: List[str],
    control_oheng: List[str],
    strong_oheng: List[str],
    current_recommended_foods: List[str],
    available_foods_text: str,
    condition: str = None
) -> str:    
    condition_text = ""
    if condition:
        condition_text = f"\n 사용자 조건: '{condition}' 음식을 원함"
    
    return f"""너는 오행 기반 음식 추천 전문가야. 사용자에게 **정확히 3개의 메뉴**를 추천해.

📊 사용자 오행 상태:
• 부족한 오행: {', '.join(lacking_oheng)} → 이 오행 음식으로 보충 필요
• 강한 오행: {', '.join(strong_oheng)} → 너무 강해서 억제 필요
• 조절 오행: {', '.join(control_oheng)} → 강한 오행을 억제하는 오행
{condition_text}

🚫 이미 추천한 음식 (절대 다시 추천 금지):
{', '.join(current_recommended_foods) if current_recommended_foods else "없음"}

✅ 추천 가능한 음식:
{available_foods_text}

📋 응답 규칙:
1. 정확히 3개 메뉴만 추천
2. 이미 추천한 음식은 절대 제외
3. 부족한 오행({', '.join(lacking_oheng)}) 음식 우선
4. 조절 오행({', '.join(control_oheng)}) 음식 포함
5. 반말 사용, 친근하게

응답 형식:
"오늘은 [메뉴1], [메뉴2], [메뉴3] 어때? 이 중에서 골라봐!"

지금 바로 추천해:"""


# 조건부 음식 추천 프롬포트
def generate_condition_prompt_improved(
    condition: str,
    lacking_oheng: List[str],
    control_oheng: List[str],
    current_recommended_foods: List[str],
) -> str:
    # 조건에 맞는 음식 필터링
    all_oheng = list(set(lacking_oheng + control_oheng))
    filtered_foods = get_foods_by_condition(
        condition=condition,
        oheng_list=all_oheng,
        exclude_foods=current_recommended_foods
    )
    
    print(f"[DEBUG] 조건='{condition}', 오행={all_oheng}")
    print(f"[DEBUG] 필터링된 음식: {filtered_foods}")
    
    if not filtered_foods:
        return f"""사용자가 '{condition}' 음식을 원하는데, 조건에 맞는 음식이 없어.

이렇게 답변해:
"'{condition}' 조건에 딱 맞는 음식은 없지만, 대신 [대체메뉴1], [대체메뉴2], [대체메뉴3] 어때?"

반말로 짧게 답변:"""
    
    # 최대 10개까지만
    filtered_foods = list(filtered_foods)[:10]
    
    return f"""'{condition}' 조건에 맞는 메뉴 **정확히 3개**를 추천해.

📊 오행 상태:
• 부족: {', '.join(lacking_oheng)}
• 조절: {', '.join(control_oheng)}

✅ 추천 가능한 '{condition}' 음식 (이 중에서만 골라):
{', '.join(filtered_foods)}

⚠️ 필수 규칙:
1. **위 목록에 있는 음식만** 선택 (절대 다른 음식 금지)
2. 정확히 3개
3. 이미 추천한 음식 제외
4. 반말 사용

응답 형식:
"{condition} 음식으로 [메뉴1], [메뉴2], [메뉴3] 어때?"

지금 바로 추천:"""


# 메뉴 추천 이유 설명 프롬포트
def generate_reason_prompt_short(
    menu_name: str,
    lacking_oheng: List[str],
    strong_oheng: List[str],
) -> str:
    # 이 음식이 어떤 오행인지 미리 파악
    food_oheng = get_food_oheng(menu_name)
    food_reason = get_food_reason(menu_name)
    
    # 이 음식이 어떤 역할인지 판단
    role = ""
    if food_oheng in lacking_oheng:
        role = f"부족한 {food_oheng} 기운을 보충"
    else:
        # 상극 관계 확인
        oheng_suppression = {
            "수(水)": "화(火)",
            "화(火)": "금(金)", 
            "금(金)": "목(木)",
            "목(木)": "토(土)",
            "토(土)": "수(水)"
        }
        
        suppressed = oheng_suppression.get(food_oheng, "")
        if suppressed in strong_oheng:
            role = f"강한 {suppressed} 기운을 억제"
        else:
            role = f"{food_oheng} 기운 제공"
    
    return f"""'{menu_name}' 추천 이유를 **정확히 3문장**으로 설명해.

🎯 음식 정보:
• 오행: {food_oheng}
• 이유: {food_reason}
• 역할: {role}

📊 사용자 오행:
• 부족: {', '.join(lacking_oheng)}
• 강함: {', '.join(strong_oheng)}

📋 응답 형식 (정확히 이대로):
"{menu_name}은(는) {food_oheng} 기운 음식이야. {food_reason}. 너는 [{role}가] 필요해서 추천했어."

⚠️ 필수:
- 반말만 사용
- 정확히 3문장
- 따옴표 사용 금지
- 위 정보 외 추가 설명 금지
- 추가 메뉴 추천 금지

예시:
"샐러드는 목 기운 음식이야. 신선한 채소가 주재료거든. 너는 부족한 목 기운을 보충이 필요해서 추천했어."

"초밥은 수 기운 음식이야. 생선을 날것으로 차갑게 먹어서 그래. 너는 강한 화 기운을 억제가 필요해서 추천했어."

지금 설명:"""


# ===============================
# LLM 호출 및 후처리
# ===============================
# 메시지 의도에 따라 적절한 프롬프트로 LLM 호출
def generate_llm_response_with_intent(
    intent: UserIntent,
    intent_data: dict,
    conversation_history: str,
    user_message: str,
    lacking_oheng: List[str],
    strong_oheng: List[str],
    control_oheng: List[str],
    current_recommended_foods: List[str] = None,
) -> str:
    # 추천 가능한 음식 목록
    available_foods_by_oheng = {}
    for oheng in lacking_oheng + control_oheng:
        all_foods = OHAENG_FOOD_LISTS.get(oheng, [])
        if current_recommended_foods:
            available = [f for f in all_foods if f not in current_recommended_foods]
        else:
            available = all_foods
        if available:
            available_foods_by_oheng[oheng] = available
    
    available_foods_text = ""
    if available_foods_by_oheng:
        for oheng, foods in available_foods_by_oheng.items():
            sample_foods = random.sample(foods, min(5, len(foods)))
            available_foods_text += f"• {oheng}: {', '.join(sample_foods)}\n"
    
    # 의도별 프롬프트 선택
    if intent == UserIntent.WANT_RECOMMENDATION or intent == UserIntent.POSITIVE_RESPONSE:
        prompt = generate_recommendation_prompt(
            lacking_oheng,
            control_oheng,
            strong_oheng,
            current_recommended_foods or [],
            available_foods_text
        )
    
    elif intent == UserIntent.ASK_REASON:
        menu = intent_data.get("menu", "")
        # 이유 설명 프롬프트 사용
        prompt = generate_reason_prompt_short(
            menu if menu else "추천한 메뉴",
            lacking_oheng,
            strong_oheng,
        )
    
    elif intent == UserIntent.ASK_CONDITION:
        condition = intent_data.get("condition", "")
        # 조건부 추천 프롬프트 사용
        prompt = generate_condition_prompt_improved(
            condition,
            lacking_oheng,
            control_oheng,
            current_recommended_foods or [],
        )
    
    else:  # GENERAL_CHAT
        # 일반 대화는 기존 방식 유지하되 짧게
        prompt = f"""간단히 대답해줘. 반말 사용.

대화 기록:
{conversation_history[-200:]}

사용자: {user_message}

짧게 답변:"""
    
    # LLM 호출
    try:
        response = client.models.generate_content(
            model=model_name,
            contents=[prompt],
            config=types.GenerateContentConfig(
                temperature=0.7,
                top_p=0.9,
                top_k=40,
                max_output_tokens=300 if intent == UserIntent.ASK_REASON else 500,  # 이유는 더 짧게
            )
        )
        output = response.text.strip()

        # 후처리: 따옴표 제거
        output = output.strip('"').strip("'")
        output = output.replace('"""', '').replace("'''", '')

        # 후처리: 존댓말 제거
        output = output.replace("입니다", "이야")
        output = output.replace("습니다", "어")
        output = output.replace("해요", "해")
        output = output.replace("이에요", "이야")
        output = output.replace("예요", "야")
        
        # 후처리
        if output == user_message:
            return "미안, 잘 못 알아들었어 😅 다시 말해줄래?"
        
        return output
        
    except Exception as e:
        print(f"LLM 호출 오류: {e}")
        return "잠깐 오류났어 😅 다시 한번 말해줄래?"

# SELECT 조건 (메뉴 최종 결정)
def post_process_select_intent(llm_output: str, user_message: str) -> str: 
    # 이미 태그가 있으면 그대로 반환
    if '[MENU_SELECTED:' in llm_output:
        return llm_output
    
    # SELECT 패턴 체크
    select_patterns = [
        (r'([가-힣]{2,})\s*먹을래', '먹을래'),
        (r'([가-힣]{2,})\s*먹자', '먹자'),
        (r'([가-힣]{2,})\s*할게', '할게'),
        (r'([가-힣]{2,})\s*좋다', '좋다'),
        (r'([가-힣]{2,})\s*좋네', '좋네'),
        (r'([가-힣]{2,})\s*선택', '선택'),
        (r'([가-힣]{2,})로?\s*골랐어', '골랐어'),
        (r'([가-힣]{2,})로?\s*결정', '결정'),
        (r'([가-힣]{2,})?\s*먹으러 갈\s*식당 알려줘', '식당 알려줘'),
        (r'([가-힣]{2,})?\s*먹으러 갈\s*식당 추천해줘', '식당 추천해줘'),
        (r'([가-힣]{2,})?\s*맛집 알려줘', '맛집 알려줘'),
        (r'([가-힣]{2,})?\s*맛집 추천해줘', '맛집 추천해줘'),
    ]
    
    for pattern, _ in select_patterns:
        match = re.search(pattern, user_message)
        if match:
            menu_name = match.group(1).strip()
            
            # OHAENG_FOOD_LISTS에 있는 음식인지 확인
            is_valid_food = False
            for oheng, foods in OHAENG_FOOD_LISTS.items():
                for food in foods:
                    # 정규화해서 비교
                    if food.replace(" ", "") in menu_name.replace(" ", "") or \
                        menu_name.replace(" ", "") in food.replace(" ", ""):
                        is_valid_food = True
                        menu_name = food  # 정확한 메뉴명으로 교체
                        break
                if is_valid_food:
                    break
            
            if is_valid_food:
                print(f"✅ SELECT 후처리 감지: {menu_name}")
                return f"[MENU_SELECTED:{menu_name}]"
    
    return llm_output



# ===============================
# 식당 검색 (Chroma + DB)
# ===============================
# 식당 목록이 없는 경우 답변
def build_no_result(menu_name: str):
    NO_RESULT_TEMPLATE = {
        "message": "아쉽게도 **{menu_name}** 메뉴를 파는 식당을 주변 2km 내에서 찾지 못했어.😢\n\n다른 메뉴를 추천해줄까?",
        "restaurants": [],
        "count": 0
    }
    data = NO_RESULT_TEMPLATE.copy()
    data["message"] = data["message"].format(menu_name=menu_name)
    return data


# 공백 제거, 소문자 변환, 특수문자 기본 처리
def normalize_text(text: str) -> str:
    if not text:
        return ""
    return (
        text.replace(" ", "")
            .replace(",", "")
            .replace("-", "")
            .replace("_", "")
            .lower()
    )


# 식당 검색 및 추천 (사용자가 선택한 메뉴와 유사도 검색 + 사용자가 선택한 위치 2km 이내)
def search_and_recommend_restaurants(menu_name: str, db: Session, lat: float=None, lon: float = None):
    # 0. 좌표 없으면 추천 불가
    if lat is None or lon is None:
        print("[ERROR] search_and_recommend_restaurants: lat/lon is None")
        return {
            "initial_message": f"'{menu_name}' 메뉴를 추천하려면 위치 정보가 필요해!",
            "restaurants": [],
            "final_message": "다른 메뉴도 추천해줄까?",
            "count": 0
        }

    # 1. 검색 쿼리 정의
    query_text = menu_name

    # 2. ChromaDB 연결
    embeddings = get_embeddings()
    chroma_client = get_chroma_client()

    vectorstore_restaurants = Chroma(
        client=chroma_client,
        collection_name=COLLECTION_NAME_RESTAURANTS,
        embedding_function=embeddings
    )

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
        # return {
        #     "initial_message": f"아쉽게도 **{menu_name}** 메뉴를 파는 식당을 찾지 못했어.",
        #     "restaurants": [],
        #     "final_message": "다른 메뉴도 추천해줄까?",
        #     "count": 0
        # }

    # 새로운 필터링 로직
    # 4. 메뉴명 기반 필터링 (content나 metadata에 메뉴명이 있는지 확인)
    restaurant_ids = []
    # chroma_results_map = {}
    chroma_map = {}

    menu_norm = menu_name.replace(" ", "").lower()  # 공백 제거, 소문자 변환

    for doc in restaurant_docs:
        rid = doc.metadata.get("restaurant_id")
        if not rid:
            continue

        # 중복 체크
        # if restaurant_id in restaurant_ids_from_chroma:
        #     continue
        content_norm = doc.page_content.replace(" ", "").lower()
        meta_norm = doc.metadata.get("menu", "").replace(" ", "").lower()

        if menu_norm in content_norm or menu_norm in meta_norm:
            if rid not in restaurant_ids:
                restaurant_ids.append(rid)
                chroma_map[rid] = doc

    if not restaurant_ids:
        return build_no_result(menu_name)

    # DB에서 식당 정보 로드
    db_list = db.query(Restaurant).filter(Restaurant.id.in_(restaurant_ids)).all()
    db_map = {r.id: r for r in db_list}

    # 5. 거리 필터링
    final_candidates = []
    # temp_restaurants_with_distance = []
    MAX_DIST = 2.0

    for rid, doc in chroma_map.items():
        restaurant = db_map.get(rid)
        if not restaurant:
            continue

        rest_lat = getattr(restaurant, "latitude", None)
        rest_lon = getattr(restaurant, "longitude", None)
        if rest_lat is None or rest_lon is None:
            continue

        distance_km = calculate_distance(lat, lon, rest_lat, rest_lon)
        if distance_km > MAX_DIST:
            continue

        distance_m = int(round(distance_km * 1000))

        processed_image_url = None
        if restaurant.image:
            imgs = restaurant.image.split(',')
            first = imgs[0].strip()
            if first.startswith(("'", '"')) and first.endswith(("'", '"')):
                first = first[1:-1]
            if first:
                processed_image_url = first

        final_candidates.append({
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
        })

    final_candidates.sort(key=lambda x: x["distance_km"])
    recommended = final_candidates[:3]

    if recommended:
        return {
            "initial_message": f"그러면 **{menu_name}** 먹으러 갈 식당 추천해줄게! 😋",
            "restaurants": recommended,
            "final_message": "다른 행운의 맛집도 추천해줄까?",
            "count": len(recommended)
        }

    return build_no_result(menu_name)