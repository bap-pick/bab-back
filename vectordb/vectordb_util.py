import chromadb
import os
import onnxruntime
import numpy as np
from transformers import AutoTokenizer
from langchain_chroma import Chroma
from langchain_core.documents import Document
from typing import List, Dict, Any, Optional
from core.db import SessionLocal
from core.models import Restaurant
from core.config import CHROMA_HOST, CHROMA_PORT
from sqlalchemy.orm import Session, joinedload

# ChromaDB 컬렉션 설정
COLLECTION_NAME_OHAENG = "ohaeng_rules_knowledge_base"
COLLECTION_NAME_RESTAURANTS = "restaurants_knowledge_base"
COLLECTION_NAME_MENUS = "menu_ohaeng_assignments"

# 임베딩 모델 설정
ONNX_MODEL_DIR = "/app/kure-v1-onnx"
embeddings: Optional['QuantizedEmbeddings'] = None

# ChromaDB 클라이언트 설정
chroma_client: Optional[chromadb.HttpClient] = None

# 양자화 모델 로드
class QuantizedEmbeddings:
    def __init__(self, model_dir: str):
        onnx_path = os.path.join(model_dir, "quantized_model.onnx")
        
        if not os.path.exists(onnx_path):
            raise FileNotFoundError(f"[ERROR] ONNX 모델이 없습니다: {onnx_path}. 'convert_to_onnx.py'를 실행했는지 확인하세요.")

        print(f"[INFO] 저장된 ONNX 모델 로딩 중: {onnx_path}")
        # 1. ONNX Runtime 세션 로드
        self.session = onnxruntime.InferenceSession(onnx_path)
        # 2. 토크나이저 로드 (Hugging Face transformers 사용)
        self.tokenizer = AutoTokenizer.from_pretrained(model_dir)
        print("ONNX 모델 및 토크나이저 로드 완료.")

    # 단일 텍스트 임베딩 생성
    def embed_query(self, text: str) -> List[float]:
        inputs = self.tokenizer(
            text, 
            padding=True, 
            truncation=True, 
            return_tensors="np"
        )
        
        input_feed = {
            'input_ids': inputs['input_ids'],
            'attention_mask': inputs['attention_mask'],
        }
        
        outputs = self.session.run(
            output_names=['last_hidden_state'], 
            input_feed=input_feed
        )
        
        last_hidden_state = outputs[0]
        
        # 평균 풀링 (Mean Pooling)
        input_mask_expanded = inputs['attention_mask'][:, :, np.newaxis].astype(last_hidden_state.dtype)
        sum_embeddings = (last_hidden_state * input_mask_expanded).sum(axis=1)
        sum_mask = input_mask_expanded.sum(axis=1).clip(min=1e-9)
        sentence_embedding = sum_embeddings / sum_mask
        
        # L2 정규화
        norm = np.linalg.norm(sentence_embedding, axis=1, keepdims=True)
        return (sentence_embedding / norm)[0].tolist()

    # 문서 목록 임베딩 생성
    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        inputs = self.tokenizer(
            texts, 
            padding=True, 
            truncation=True, 
            return_tensors="np"
        )
        
        input_feed = {
            'input_ids': inputs['input_ids'],
            'attention_mask': inputs['attention_mask'],
        }
        
        outputs = self.session.run(
            output_names=['last_hidden_state'], 
            input_feed=input_feed
        )
        
        last_hidden_state = outputs[0]
        
        # 평균 풀링
        input_mask_expanded = inputs['attention_mask'][:, :, np.newaxis].astype(last_hidden_state.dtype)
        sum_embeddings = (last_hidden_state * input_mask_expanded).sum(axis=1)
        sum_mask = input_mask_expanded.sum(axis=1).clip(min=1e-9)
        sentence_embedding = sum_embeddings / sum_mask
        
        # L2 정규화 및 반환
        norm = np.linalg.norm(sentence_embedding, axis=1, keepdims=True)
        return (sentence_embedding / norm).tolist()
    
# 양자화된 모델 로드 (지연 로딩)
def get_embeddings() -> 'QuantizedEmbeddings':
    global embeddings
    if embeddings is None:
        embeddings = QuantizedEmbeddings(
            model_dir=ONNX_MODEL_DIR, # ONNX 경로 사용
        )
        # 로드 성공 확인을 위해 테스트 임베딩 실행
        try:
            test_embedding = embeddings.embed_query('테스트')
            print(f"생성된 벡터 차원: {len(test_embedding)}")
        except Exception as e:
            print(f"임베딩 테스트 실패: {e}. ONNX 모델이 올바른지 확인하세요.")

    return embeddings

# 지연 로드(Lazy Load) 방식으로 ChromaDB 클라이언트 연결
def get_chroma_client() -> chromadb.HttpClient:
    global chroma_client
    if chroma_client is None:
        print(f"ChromaDB 클라이언트 연결 시작 ({CHROMA_HOST}:{CHROMA_PORT})...")
        try:
            chroma_client = chromadb.HttpClient(host=CHROMA_HOST, port=CHROMA_PORT)
            print("ChromaDB 클라이언트 연결 성공.")
        except Exception as e:
            # Render 타임아웃 시 초기화 실패하도록 예외 발생
            raise RuntimeError(f"ChromaDB 서버 연결 실패: {e}")
            
    return chroma_client

def get_chroma_client_and_collection(
    collection_name: str, 
    use_langchain_chroma: bool = False
) -> tuple[chromadb.HttpClient, Any] | tuple[None, None]:
    try:
        # ChromaDB 클라이언트 연결 - 도커 컨테이너에 접속
        client = get_chroma_client()
        
        if use_langchain_chroma:
            # LangChain Chroma 헬퍼 (add_documents 사용 시 필요)
            collection_obj = Chroma(
                client=client,
                collection_name=collection_name,
                embedding_function=get_embeddings()
            )
            return client, collection_obj
            
        else:
            # 기본 Chroma 컬렉션 객체를 반환
            return client, client.get_collection(name=collection_name)
            
    except Exception as e:
        print(f"ChromaDB 연결/컬렉션 로드 실패: {e}")
        return None, None # 오류 발생 시 두 개의 None 반환
    
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
            include=['metadatas', 'documents', 'embeddings'] 
        )
        
        doc_count = len(results.get('ids', [])) # 실제 조회하는 문서의 개수
        if doc_count == 0:
            print(f"{collection_name} 컬렉션에 문서가 없음")
            return
        
        
        # 문서별로 일부 내용과 임베딩 정보 출력
        for i in range(doc_count):
            print(f"\n문서 {i+1} / {doc_count} (ID: {results['ids'][i]})")
            print("메타데이터:", results['metadatas'][i])
            print("문서 내용:", results['documents'][i][:150] + "...")
            embedding = results['embeddings'][i] if 'embeddings' in results else None
            if embedding is not None:
                # NumPy → 리스트 변환
                if hasattr(embedding, 'tolist'):
                    embedding_list = embedding.tolist()
                else:
                    embedding_list = embedding
                print(f"임베딩 길이: {len(embedding_list)}")  # 차원 확인
        
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
        COLLECTION_NAME_MENUS,
        COLLECTION_NAME_OHAENG,
    ]
    
    # 각 컬렉션에 대해 원본 데이터 출력 함수 호출
    for col_name in COLLECTIONS_TO_CHECK:
        display_raw_collection_data(chroma_client, col_name, limit=50)
        
        
if __name__ == "__main__":
    client = get_chroma_client()