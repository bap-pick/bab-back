import google.genai as genai
from google.genai import types
from core.config import GEMMA_API_KEY
from core.models import ChatMessage
from sqlalchemy.orm import Session
from api.saju import _get_oheng_analysis_data
from saju.message_generator import define_oheng_messages


client = genai.Client(api_key=GEMMA_API_KEY)
model_name = "gemma-3-4b-it"


async def get_initial_chat_message(uid: str, db: Session) -> str:
    """
    유저정보 기반 첫 메세지
    """
    # 사주 데이터 불러오기
    lacking_oheng, strong_oheng, oheng_type, oheng_scores = await _get_oheng_analysis_data(uid, db)
    
    # 메시지 생성 로직 
    headline, advice,  recommended_ohengs_weights= define_oheng_messages(lacking_oheng, strong_oheng, oheng_type)
    
    # 첫 메시지 완성
    first_message = (
        "오늘의 운세에 맞춰 행운의 맛집을 추천해드리는 '밥픽'입니다! 🍀\n\n"
        f"오늘 당신의 오행 타입은 '{oheng_type}'이에요.\n"
        f"✨ {headline}\n"
        f"💡 {advice}"
    )
    return first_message
    


MAX_MESSAGES = 10  # 최근 10개만 기억

def build_conversation_history(db: Session, chatroom_id: int) -> str:
    """최근 대화 10개 불러와서 문자열로 변환"""
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
        conversation_history += f"{role}: {msg.content}\n"
    return conversation_history


def generate_llm_response(conversation_history: str, user_message: str) -> str:
    """LLM 호출 + 응답 반환"""
    prompt = (
        "너는 음식 추천 전용 챗봇이야. "
        "사용자의 질문이 음식, 맛집, 요리, 재료, 식단, 음식문화 등과 관련된 경우에만 답해. "
        "그 외의 주제는 언급하지 말고, "
        "답변할 때는 항상 음식 추천으로 자연스럽게 전환해줘. "
        "모든 답변은 존댓말을 써. "
        "사용자가 메뉴를 선택하면, 그 메뉴를 파는 식당을 3개 추천해줘. "
        "추천할 때는 식당 이름, 인기 메뉴, 거리 정도를 간단하게 안내해. "
        "항상 메뉴 추천 → 사용자 선택 → 식당 추천 순서로 대화를 이어가. "
        "지금부터 사용자의 질문이 들어올 거야.\n\n"
        f"{conversation_history}"
        f"사용자 질문: {user_message}"
    )

    response = client.models.generate_content(
        model=model_name,
        contents=[prompt],
        config=types.GenerateContentConfig(temperature=0.7)
    )

    return response.text.strip() if response.text else "응답 없음"
