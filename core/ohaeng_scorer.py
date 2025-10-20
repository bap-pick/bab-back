# [core/ohaeng_scorer.py] - LLM 클린 초기화 버전

import os
import json
from dotenv import load_dotenv

# Pydantic v2 권장사항 반영: pydantic에서 직접 import
from pydantic import BaseModel, Field
from langchain_core.prompts import ChatPromptTemplate
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.runnables import RunnablePassthrough

# 벡터 DB (Chroma) 및 임베딩 로드에 필요한 모듈
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_chroma import Chroma
# from google import genai # <--- 이제 필요 없으므로 제거

# 환경 변수 로드
load_dotenv()

# --- A. LLM 출력 형식 정의 (Pydantic 스키마) ---
class OhaengScore(BaseModel):
    """식당 메뉴와 컨셉의 오행별 점수 (0~5점)"""
    ohaeng_wood: int = Field(description="木 기운 점수 (0-5점, 신맛/채소/활력 기준)")
    ohaeng_fire: int = Field(description="火 기운 점수 (0-5점, 쓴맛/붉은색/직화/열정 기준)")
    ohaeng_earth: int = Field(description="土 기운 점수 (0-5점, 단맛/곡물/육류/안정 기준)")
    ohaeng_metal: int = Field(description="金 기운 점수 (0-5점, 매운맛/흰색/발효/정화 기준)")
    ohaeng_water: int = Field(description="水 기운 점수 (0-5점, 짠맛/흑색/해산물/국물 기준)")

# google_client 객체 생성 코드 제거

# --- B. LLM 및 Retriever 설정 ---
# 1. LLM 초기화 (최신 라이브러리가 오류를 해결했는지 확인하기 위한 가장 단순한 초기화)
LLM = ChatGoogleGenerativeAI(
    model="gemma-3-4b-it", 
    temperature=0
) 
EMBEDDING_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
VECTOR_DB_PATH = "chroma_db"
VECTOR_DB_COLLECTION_NAME = "ohaeng_rules_knowledge_base"

def get_ohaeng_retriever():
    """ChromaDB에서 오행 규칙을 검색할 Retriever 객체를 로드"""
    embeddings = HuggingFaceEmbeddings(
        model_name=EMBEDDING_MODEL_NAME, 
        model_kwargs={'device': 'cpu'}
    )
    vectorstore = Chroma( 
        persist_directory=VECTOR_DB_PATH, 
        embedding_function=embeddings,
        collection_name=VECTOR_DB_COLLECTION_NAME
    )
    return vectorstore.as_retriever(search_kwargs={"k": 2})


# --- C. RAG 프롬프트 및 LLM 정의 ---

# 1. 프롬프트 템플릿 정의 (RAG 체인과 별도로 정의)
SYSTEM_PROMPT = ChatPromptTemplate.from_messages([
    ("system", (
        "당신은 사주 오행과 음식의 연관성을 평가하는 전문가입니다. "
        "아래 '오행 규칙'을 참조하여, '식당 정보'를 면밀히 분석하고 오행별로 0~5점 사이의 점수를 평가해 주세요. "
        "응답은 반드시 Pydantic 스키마가 요구하는 정확한 JSON 형식(쉼표, 따옴표 등)을 따라야 합니다.\n\n"
        "오행 규칙: \n--- START ---\n{context}\n--- END ---\n"
        "출력 형식: {schema}"
    )),
    ("human", "다음 식당 정보의 오행별 점수를 평가해 주세요. (점수 총합은 15점을 넘지 않도록 균형을 맞춰주세요): {restaurant_info}")
])

# 2. LLM에 Structured Output 적용
structured_llm = LLM.with_structured_output(schema=OhaengScore)


# --- D. 외부 호출 함수 (RAG Chain 수동 실행) ---
def score_restaurant(category: str, menu_summary: str) -> dict:
    """
    외부에서 식당 카테고리와 메뉴를 받아 오행 점수를 계산하는 메인 함수.
    """
    
    retriever = get_ohaeng_retriever()
    restaurant_info = f"식당 카테고리는 '{category}'이며, 주요 메뉴는 '{menu_summary}'입니다."
    
    try:
        # 1. 식당 정보와 유사한 오행 규칙 검색
        retrieved_docs = retriever.invoke(restaurant_info)
        
        # 2. 검색된 문서를 하나의 문자열로 결합
        context = "\n".join([doc.page_content for doc in retrieved_docs])
        
        # 3. 프롬프트에 모든 변수(Context, Schema, Info)를 할당
        formatted_prompt = SYSTEM_PROMPT.format_messages(
            context=context,
            schema=json.dumps(OhaengScore.model_json_schema(), ensure_ascii=False),
            restaurant_info=restaurant_info
        )
        
        # 4. LLM 호출 및 Pydantic 객체 반환
        score_object = structured_llm.invoke(formatted_prompt)
        
        # Pydantic 객체를 딕셔너리로 변환하여 반환
        return score_object.dict()

    except Exception as e:
        print(f"RAG Chain 실행 중 오류 발생: {e}")
        # 오류 시 모든 점수를 0으로 반환
        return {
            "ohaeng_wood": 0, "ohaeng_fire": 0, 
            "ohaeng_earth": 0, "ohaeng_metal": 0, 
            "ohaeng_water": 0
        }

# --- E. 테스트 실행 (스크립트 개별 실행 시) ---
if __name__ == "__main__":
    
    print("--- 2단계: Gemma RAG Chain 테스트 시작 (최종 클린 버전) ---")

    # 테스트 1: 복합적인 메뉴 (해장국, 순대, 육류)
    test_category_1 = "해장국"
    test_menu_1 = "뼈해장국, 모듬순대, 감자탕"
    print(f"\n--- 테스트 1: {test_category_1} ({test_menu_1}) ---")
    score_1 = score_restaurant(test_category_1, test_menu_1)
    print("점수 결과:", score_1)
    
    # 테스트 2: 단순하고 강렬한 메뉴 (화/목)
    test_category_2 = "샐러드 & 그릴"
    test_menu_2 = "매실 드레싱을 곁들인 닭가슴살 샐러드와 직화 스테이크"
    print(f"\n--- 테스트 2: {test_category_2} ({test_menu_2}) ---")
    score_2 = score_restaurant(test_category_2, test_menu_2)
    print("점수 결과:", score_2)
    
    print("\n--- 테스트 완료 ---")