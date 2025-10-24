from langchain_chroma import Chroma
from langchain_core.documents import Document
from .prepare_restaurant_docs import create_restaurant_documents 
from .vectordb_util import (
    get_chroma_client_and_collection,
    COLLECTION_NAME_OHAENG, 
    COLLECTION_NAME_RESTAURANTS, 
    embeddings
)

# 오행 규칙 데이터 정의
OHAENG_RULES = [
    ("木", 
    "식재료: 신맛(레몬, 식초, 매실), 녹색 채소, 나물, 샐러드, 쌈밥, 허브류, 발아된 콩나물/숙주 등\n"
    "조리 방식: 데치기, 생식, 찌기 등 가벼운 방식\n"
    "컨셉: 헬스, 비건, 자연주의, 튀김이나 강한 양념 없는 음식\n"
    "예시 메뉴: 비빔밥, 채소 샐러드, 나물 반찬\n"
    "식당 유형: 건강식 전문점, 샐러드바, 비건 카페\n"
    "설명: 木 기운은 성장, 활력, 가벼움과 관련. 신선하고 가벼운 음식일수록 木 점수가 높음."),
    
    ("火", 
    "식재료: 붉은색 식재료(고추, 토마토), 매운맛(고춧가루, 칠리), 커피, 카카오, 닭고기, 양고기\n"
    "조리 방식: 직화 구이, 튀김, 바비큐, 열을 동반한 강한 양념\n"
    "컨셉: 활기찬 분위기, 포차, 펍, 불맛 중심 요리\n"
    "예시 메뉴: 닭볶음탕, 양념 치킨, 바비큐, 매운 볶음 요리\n"
    "설명: 火 기운은 에너지, 열정, 활동성을 상징. 매운맛과 붉은 음식이 火 점수를 높임."),
    
    ("土", 
    "식재료: 단맛, 구수한 맛(곡물, 콩), 밥, 면, 밀가루, 감자, 고구마, 육류(소, 돼지)\n"
    "조리 방식: 오래 끓이기, 찜, 곰탕, 걸쭉한 국물 요리\n"
    "컨셉: 안정감 있는 한정식, 백반집, 분식집\n"
    "예시 메뉴: 곰탕, 찜 요리, 돈까스, 백반 세트\n"
    "설명: 土 기운은 안정, 균형, 소화와 관련. 든든하고 포만감을 주는 음식일수록 土 점수가 높음."),
    
    ("金", 
    "식재료: 흰색 식재료(흰살 생선, 두부), 매운맛(마늘, 양파, 겨자), 맑은 육수, 순대, 칼국수, 발효 김치\n"
    "조리 방식: 찌기, 맑은 탕, 발효 조리\n"
    "컨셉: 단정하고 깔끔한 요리, 모던한 한식집, 국물 중심\n"
    "예시 메뉴: 순대국, 칼국수, 맑은 생선탕\n"
    "설명: 金 기운은 정리, 질서, 단정함과 관련. 깔끔하고 맑은 요리가 金 점수를 높임."),
    
    ("水", 
    "식재료: 짠맛(소금, 간장, 젓갈), 검은색 식재료(해조류, 검은콩), 모든 해산물, 국물 요리, 물회, 해산물 요리, 술\n"
    "조리 방식: 찌개, 조림, 해산물 요리\n"
    "컨셉: 깊고 어두운 느낌, 횟집, 찌개 전문점, 이자카야\n"
    "설명: 水 기운은 유연함, 깊이, 회복과 관련. 바다 식재료, 국물 요리, 짠맛이 水 점수를 높임."),
]

# 벡터 DB 초기화 및 오행 규칙 데이터, 식당 데이터 저장
def initialize_knowledge_base():    
    # 클라이언트와 컬렉션 객체 로드
    client, vectorstore_ohaeng = get_chroma_client_and_collection(
        COLLECTION_NAME_OHAENG, 
        use_langchain_chroma=True
    )
    if not client: return None, None
        
    # 오행 규칙 데이터 저장
    ohaeng_documents = [
        Document(
            page_content=content,
            metadata={"ohaeng_type": ohaeng}
        )
        for ohaeng, content in OHAENG_RULES
    ]
    
    vectorstore_ohaeng = Chroma.from_documents(
        documents=ohaeng_documents,
        embedding=embeddings,
        collection_name=COLLECTION_NAME_OHAENG,
        client=client
    )
    print(f"오행 규칙 {COLLECTION_NAME_OHAENG} 컬렉션에 저장 완료")

    # B. 식당 데이터 저장: create_restaurant_documents() 함수를 호출해 Document 가져오기
    restaurant_documents = create_restaurant_documents() 
    
    if not restaurant_documents:
        return None, vectorstore_ohaeng
        
    vectorstore_restaurants = Chroma.from_documents(
        documents=restaurant_documents,
        embedding=embeddings,
        collection_name=COLLECTION_NAME_RESTAURANTS,
        client=client
    )
    print(f"식당 데이터 {COLLECTION_NAME_RESTAURANTS} 컬렉션에 저장 완료")

    # 두 벡터 저장소 객체 반환
    return vectorstore_restaurants, vectorstore_ohaeng

# 5. 스크립트 실행
#if __name__ == "__main__":
#    try:
#        restaurant_vs, ohaeng_vs = initialize_knowledge_base()
#        
#        # 테스트 쿼리 (오행 규칙)
#        query_ohaeng = "튀김과 양념이 강한 음식은 어떤 기운인가요?"
#        docs_ohaeng = ohaeng_vs.similarity_search(query_ohaeng, k=1)
#        print(f"쿼리: {query_ohaeng}")
#        print(f"결과 (기운): {docs_ohaeng[0].metadata.get('ohaeng_type', 'N/A')}")
#
#        # 테스트 쿼리 (식당)
#        if restaurant_vs:
#            query_restaurant = "매콤한 짬뽕과 짜장면이 있는 곳 알려줘"
#            docs_restaurant = restaurant_vs.similarity_search(query_restaurant, k=1)
#            print(f"쿼리: {query_restaurant}")
#            print(f"가장 유사한 식당: {docs_restaurant[0].metadata.get('name', 'N/A')}")
#            print(f"내용 일부: {docs_restaurant[0].page_content[:40]}...")
#            
#    except Exception as e:
#        print(f"오류 발생: {e}")