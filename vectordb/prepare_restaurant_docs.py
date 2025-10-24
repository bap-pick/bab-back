from langchain_core.documents import Document
from typing import List
from sqlalchemy.orm import Session, joinedload

from core.db import SessionLocal
from core.models import Restaurant

# 식당 및 메뉴 정보를 가져와 LangChain Document로 결합
def create_restaurant_documents() -> List[Document]:
    # 1. DB 세션 생성: FastAPI Depends 환경이 아니므로 get_db()를 가져오는 대신 SessionLocal을 직접 사용
    db: Session = SessionLocal()
    documents: List[Document] = []
    
    try:
        # 2. 모든 식당과 메뉴 정보를 한 번에 가져오기
        # joinedload을 사용해, 식당 모델 로드 시 menus 관계(해당 식당의 모든 메뉴)를 JOIN으로 즉시 함께 로드
        restaurants = db.query(Restaurant).options(
            joinedload(Restaurant.menus)
        ).all()
        
        if not restaurants:
            print("데이터베이스에 식당 정보 없음")
            return []

        # 3. 식당별 메뉴 정보를 결합하고 Document 생성
        for rest in restaurants:
            # rest.menus을 통해 이미 로드된 메뉴 리스트를 사용
            menu_names = [menu.menu_name for menu in rest.menus if menu.menu_name]
            combined_menus = ", ".join(menu_names) if menu_names else "메뉴 정보 없음"

            # 4. 임베딩할 최종 텍스트 (page_content) 구성
            content = (
                f"식당 이름: {rest.name}. 카테고리: {rest.category}. 주소: {rest.address}. "
                f"메뉴: {combined_menus}."
            )

            # 5. LangChain Document 객체 생성
            metadata = {
                "restaurant_id": rest.id,
                "name": rest.name,
                "category": rest.category,
                "address": rest.address,
            }
            
            document = Document(page_content=content, metadata=metadata)
            documents.append(document)

    except Exception as e:
        print(f"DB 로드 혹은 쿼리에서 오류 발생: {e}")
        return []
    finally:
        if 'db' in locals() and db: # 세션 객체가 생성되었는지 확인 후 닫음
            db.close() 

    print(f"{len(documents)}개의 식당 데이터 Document 생성 완료")
    return documents

#if __name__ == "__main__":
#    fetched_documents = create_restaurant_documents()