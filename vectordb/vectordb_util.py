import chromadb
from langchain_chroma import Chroma
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_core.documents import Document
from typing import List, Dict, Any, Optional
import json
from core.db import SessionLocal
from core.models import Restaurant
from core.config import CHROMA_HOST, CHROMA_PORT
from sqlalchemy.orm import Session, joinedload

# ChromaDB 컬렉션 설정
COLLECTION_NAME_OHAENG = "ohaeng_rules_knowledge_base"
COLLECTION_NAME_RESTAURANTS = "restaurants_knowledge_base"
COLLECTION_NAME_REASONS = "ohaeng_reasons_knowledge_base" 

# 임베딩 모델 설정
EMBEDDING_MODEL_NAME = "nlpai-lab/KURE-v1" 
embeddings = HuggingFaceEmbeddings(
    model_name=EMBEDDING_MODEL_NAME,
    model_kwargs={'device': 'cpu'}
)

# ChromaDB 연결/컬렉션 로드
def get_chroma_client_and_collection(
    collection_name: str, 
    use_langchain_chroma: bool = False
) -> tuple[chromadb.HttpClient, Any] | tuple[None, None]:
    try:
        # ChromaDB 클라이언트 연결 - 도커 컨테이너에 접속
        client = chromadb.HttpClient(host=CHROMA_HOST, port=CHROMA_PORT)
        
        if use_langchain_chroma:
            # LangChain Chroma 헬퍼 (add_documents 사용 시 필요)
            collection_obj = Chroma(
                client=client,
                collection_name=collection_name,
                embedding_function=embeddings
            )
        else:
            # 일반 ChromaDB 컬렉션 객체 (get, delete, count 사용 시 효율적)
            collection_obj = client.get_collection(name=collection_name)
            
        return client, collection_obj
            
    except Exception as e:
        print(f"ChromaDB 연결/컬렉션 로드 실패: {e}")
        return None, None
    
# MySQL에서 특정 ID의 식당과 메뉴 조회 후 Document 객체 생성
def fetch_and_create_document(restaurant_id: int, db: Session) -> Optional[Document]:
    try:
        restaurant_record = db.query(Restaurant).options(
            joinedload(Restaurant.menus)
        ).filter(Restaurant.id == restaurant_id).one_or_none()
        
        if not restaurant_record:
            return None

        menu_names = [menu.menu_name for menu in restaurant_record.menus if menu.menu_name]
        combined_menus = ", ".join(menu_names) if menu_names else "메뉴 정보 없음"
        
        content = (
            f"식당 이름: {restaurant_record.name}. 카테고리: {restaurant_record.category}. 주소: {restaurant_record.address}. "
            f"메뉴: {combined_menus}."
        )
        
        doc = Document(
            page_content=content,
            metadata={
                "restaurant_id": restaurant_record.id,
                "name": restaurant_record.name,
                "category": restaurant_record.category,
                "address": restaurant_record.address,
                "source": "restaurant_db_restored"
            }
        )
        return doc
        
    except Exception as e:
        print(f"DB 조회 오류: {e}")
        return None

# 특정 ID의 식당 데이터를 ChromaDB에서 삭제 후 재저장
def restore_restaurant_data(target_id: int):    
    db: Optional[Session] = None
    
    try:
        # ChromaDB 클라이언트 연결 및 LangChain Chroma 로드
        print(f"ChromaDB 클라이언트 연결 시작")
        
        client, vectorstore_restaurants = get_chroma_client_and_collection(
            COLLECTION_NAME_RESTAURANTS, # 식당 데이터가 저장된 컬렉션
            use_langchain_chroma=True # vectorstore_restaurants는 LangChain Chroma 객체이므로 True
        )
        if not client: return

        pre_op_count = vectorstore_restaurants._collection.count()
        print(f"식당 컬렉션 로드 완료 (현재 데이터 수: {pre_op_count}개)")
        
        # 1. ChromaDB에서 해당 ID 데이터 삭제
        vectorstore_restaurants._collection.delete(
            where={"restaurant_id": target_id}
        )
        
        post_delete_count = vectorstore_restaurants._collection.count()
        deleted_count = pre_op_count - post_delete_count
        print(f"ID {target_id} 데이터 삭제 완료 ({deleted_count}건 삭제됨)")
        
        # 2. MySQL DB에서 데이터 조회 및 Document 생성
        
        #  MySQL DB 세션 생성 및 할당
        db: Session = SessionLocal() 
        document_to_restore = fetch_and_create_document(target_id, db)
        
        if not document_to_restore:
            print(f" MySQL DB에서 ID {target_id} 데이터를 찾지 못했으므로 중단")
            return 
        
        documents_to_restore: List[Document] = [document_to_restore]
        
        # 3. 임베딩 후 ChromaDB에 데이터 재저장        
        vectorstore_restaurants.add_documents(documents=documents_to_restore)
        
        final_count = vectorstore_restaurants._collection.count()
        inserted_count = final_count - post_delete_count
        print(f"재저장 완료: {inserted_count}개 문서 저장됨. (현재 데이터 수: {final_count}개)")
        
        # 4. 결과 확인
        print(f"저장된 데이터")
        target_data: Dict[str, List[Any]] = vectorstore_restaurants._collection.get(
            where={"restaurant_id": target_id}, 
            include=["documents", "metadatas"]
        )
        
        if target_data['documents']:
            doc = target_data['documents'][0]
            metadata = target_data['metadatas'][0]
            
            print(f"  - 이름: {metadata.get('name', 'N/A')}")
            print(f"  - 카테고리: {metadata.get('category', 'N/A')}")
            print(f"  - 문서 내용 일부: {doc[:150]}...") 
        else:
            print(f"재저장된 ID {target_id} 문서를 찾을 수 없음")
            
    except Exception as e:
        print(f"오류 발생: {e}")
    finally:
        # 세션 객체가 생성되었는지 확인 후 닫음
        if db:
            db.close()


# 여러 식당 데이터를 ChromaDB에서 일괄 삭제 (target_ids [123, 432] 여러 id 리스트)
def delete_restaurant_data_batch(target_ids: List[int]):
    # ChromaDB 클라이언트 연결 및 LangChain Chroma 로드
    print(f"ChromaDB 클라이언트 연결 시작")
    client, collection = get_chroma_client_and_collection(
        COLLECTION_NAME_RESTAURANTS, 
        use_langchain_chroma=False
    )
    if not client: return
    
    pre_op_count = collection.count()
    print(f"식당 컬렉션 로드 완료 (현재 데이터 수: {pre_op_count}개)")
        
    # 삭제
    # restaurant_id의 값이 target_ids 리스트에 'in' 하는 문서를 삭제
    delete_filter: Dict[str, Any] = {
        "restaurant_id": {
            "$in": target_ids
        }
    }
    collection.delete(where=delete_filter)
        
    # 결과 확인
    post_delete_count = collection.count()
    deleted_count = pre_op_count - post_delete_count
    
    print(f"\n 일괄 삭제 완료: {deleted_count}개를 삭제 (총 데이터 수: {post_delete_count}개)")


# 특정 ID의 식당 문서 조회
def check_restaurant_document(target_id: int):
    # 1. ChromaDB 클라이언트 연결 및 컬렉션 로드
    print(f"ChromaDB 클라이언트 연결 시작")
    client, collection = get_chroma_client_and_collection(
        COLLECTION_NAME_RESTAURANTS, 
        use_langchain_chroma=False
    )
    if not client: return 
    
    # 3. 필터 설정
    check_filter: Dict[str, Any] = {
        "restaurant_id": target_id
    }
        
    # 4. 문서 조회
    existing_documents = collection.get(
        where=check_filter,
        include=["metadatas", "documents"]
    )
        
    found_ids = existing_documents.get('ids', [])
    found_count = len(found_ids)
        
    # 5. 결과 출력
    if found_count > 0:
        print(f"총 {found_count}건의 문서 발견")
            
        # 조회된 각 문서를 반복하며 출력
        for i in range(found_count):
            metadata = existing_documents['metadatas'][i]
            document_content = existing_documents['documents'][i]
                
            print(f"\n문서 번호: {i + 1} / {found_count} (문서 ID: {found_ids[i]})") 
                
            # 메타데이터 출력
            print("문서 메타데이터")
            for key, value in metadata.items():
                print(f"    - {key}: {value}")
                
            # 문서 내용 출력
            print("문서 내용 (Document Content)")
            print(document_content)
                
    else:
        print(f"식당 ID {target_id}에 해당하는 문서를 찾지 못함")


# 컬렉션의 원본 데이터 일부 조회
def display_raw_collection_data(chroma_client: chromadb.HttpClient, collection_name: str, limit: int):
    try:
        collection = chroma_client.get_collection(name=collection_name)

        results = collection.get(
            limit=limit,
            include=['metadatas', 'documents'] 
        )
        
        doc_count = len(results.get('ids', [])) # 실제 조회하는 문서의 개수
        if doc_count == 0:
            print(f"{collection_name} 컬렉션에 문서가 없음")
            return
        
        print(json.dumps(results, indent=2, ensure_ascii=False))
        
        if collection.count() > limit:
            print(f"\n {collection_name} 컬렉션에는 총 {collection.count()}개의 문서가 있으며, {limit}개만 출력함")
            
    except Exception as e:
        print(f"{collection_name} 컬렉션 출력 중 오류 발생: {e}")

# 모든 컬렉션의 데이터 확인
def check_all_collections():
    print(f"ChromaDB 연결 시작")
    
    try:
        chroma_client = chromadb.HttpClient(host=CHROMA_HOST, port=CHROMA_PORT)
    except Exception as e:
        print(f"ChromaDB 서버 연결 실패: {e}")
        return

    COLLECTIONS_TO_CHECK = [
        COLLECTION_NAME_RESTAURANTS,
        COLLECTION_NAME_REASONS,
    ]
    
    # 각 컬렉션에 대해 원본 데이터 출력 함수 호출
    for col_name in COLLECTIONS_TO_CHECK:
        display_raw_collection_data(chroma_client, col_name, limit=50)
        
        
if __name__ == "__main__":
    #restore_restaurant_data(1498)
    #delete_restaurant_data_batch(TARGET_RESTAURANT_IDS)
    #check_restaurant_document(14)
    check_all_collections()