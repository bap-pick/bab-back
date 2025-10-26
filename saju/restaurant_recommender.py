from typing import List, Dict, Any
from langchain_chroma import Chroma
import re 
from vectordb.vectordb_util import (
    get_chroma_client_and_collection,
    COLLECTION_NAME_RESTAURANTS,
    COLLECTION_NAME_REASONS,
    embeddings
)

# 오행 이름에서 괄호 안의 한자 추출 (예: '목(木)' -> '木')
def simplify_ohaeng_name(full_name: str) -> str:
    match = re.search(r'\((.)\)', full_name)
    return match.group(1) if match else full_name


# 가중치가 가장 높은 오행을 보충하는 식당 반환
def get_top_restaurants_by_oheng(
    oheng_weights: Dict[str, int],  # 오행 이름 가중치 딕셔너리 (예: {'목(木)': 2, '수(水)': 1})
    top_k: int = 5
) -> List[Dict[str, Any]]:
    if not oheng_weights:
        print("경고: 추천 오행 가중치가 비어 있습니다.")
        return []
        
    try:
        # 1. ChromaDB 클라이언트 연결 및 LangChain Chroma 객체 생성
        chroma_client, _ = get_chroma_client_and_collection(
            collection_name=COLLECTION_NAME_RESTAURANTS, 
            use_langchain_chroma=False 
        )
        
        if not chroma_client:
            print("오류: ChromaDB 클라이언트 연결 실패")
            return []
        
        # Reasons 컬렉션 (식당별 오행 및 이유 검색)
        vectorstore_restaurants = Chroma(
            client=chroma_client,
            collection_name=COLLECTION_NAME_RESTAURANTS,
            embedding_function=embeddings
        )
        
        # Restaurants 컬렉션 (식당 상세 정보 조회)
        vectorstore_reasons_client=Chroma(
            client=chroma_client,
            collection_name=COLLECTION_NAME_REASONS,
            embedding_function=embeddings
        )
        
    except Exception as e:
        print(f"오류: ChromaDB 초기화 실패: {e}")
        return []
        
    
    # 2. 가중치가 가장 높은 오행 찾기 (동점일 경우 모두 포함)
    max_weight = max(oheng_weights.values()) if oheng_weights else 0
    top_ohengs: Dict[str, int] = {
        oheng: weight for oheng, weight in oheng_weights.items() if weight == max_weight
    }

    if not top_ohengs:
        print("경고: 유효한 오행 가중치가 없습니다.")
        return []

    print(f"최대 가중치 오행 검색 시작: {top_ohengs} (가중치: {max_weight})")
    
    # 3. COLLECTION_NAME_REASONS에서 가중치가 가장 높은 오행에 대해 'ohaeng_rank': 1인 문서 검색
    priority_restaurants: Dict[str, Dict[str, Any]] = {}
    
    for oheng_full, weight in top_ohengs.items():
        oheng_simple = simplify_ohaeng_name(oheng_full) # 예: '목(木)' -> '木'
        
        try:
            # ChromaDB의 get()을 사용하여 메타데이터 필터링
            reason_data = vectorstore_reasons_client.get(
                where={
                    "$and": [
                        {"ohaeng_type": oheng_simple}, 
                        {"ohaeng_rank": 1} # 1순위 오행 매칭만 찾습니다.
                    ]
                },
                limit=1000,
                include=['metadatas']
            )
            
            if reason_data and reason_data.get('metadatas'):
                for metadata in reason_data['metadatas']:
                    rest_id = str(metadata.get("restaurant_id"))
                    
                    if not rest_id: continue
                    
                    if rest_id not in priority_restaurants:
                        priority_restaurants[rest_id] = {
                            "id": rest_id,
                            "name": metadata.get("name", "N/A"),
                            "recommended_oheng": oheng_full, # 풀 네임 저장 (예: '목(木)')
                            "recommendation_reason": metadata.get("reason_text", "추천 이유 없음")
                        }

        except Exception as e:
            print(f"오류: ChromaDB 이유 컬렉션 검색 오류 (오행: {oheng_full}): {e}")
            continue
            
    if not priority_restaurants:
        print("경고: 1순위 오행에 매칭되는 식당을 찾지 못했습니다.")
        return []
    
    # 4. 상위 N개 식당을 ID 기준 정렬
    sorted_rest_list = sorted(
        priority_restaurants.values(), 
        key=lambda x: (x["id"]), 
        reverse=True
    )
    
    top_restaurants_data = sorted_rest_list[:top_k]
    # 상세 정보 조회에 사용할 ID 목록
    top_rest_ids = [rest['id'] for rest in top_restaurants_data] 

    # 5. COLLECTION_NAME_RESTAURANTS에서 상세 정보 조회
    final_restaurants: List[Dict[str, Any]] = []
    detail_info_map: Dict[str, Dict[str, Any]] = {}
    
    if top_rest_ids:
        try:
            # restaurant_id를 기반으로 상세 정보 조회
            detail_results = vectorstore_restaurants.get(
                where={
                    "restaurant_id": {"$in": [int(rid) for rid in top_rest_ids]} 
                },
                limit=len(top_rest_ids),
                include=['metadatas']
            )

            # 상세 정보를 딕셔너리로 변환하여 빠른 접근을 준비
            detail_info_map = {
                str(m.get('restaurant_id')): m for m in detail_results.get('metadatas', [])
            }

        except Exception as e:
            print(f"오류: ChromaDB 상세 정보 조회 오류: {e}")
            
    
    # 6. 최종 포맷으로 정보 결합 및 출력
    for rest_data in top_restaurants_data:
        rest_id = rest_data['id']
        detail = detail_info_map.get(rest_id, {})
        
        final_restaurants.append({
            "id": rest_id,
            "name": rest_data["name"], 
            "recommended_oheng": rest_data["recommended_oheng"],
            "recommendation_reason": rest_data["recommendation_reason"],
            "address": detail.get("address", "주소 정보 없음"),
            "category": detail.get("category", "카테고리 정보 없음"),
        })
    
    return final_restaurants
