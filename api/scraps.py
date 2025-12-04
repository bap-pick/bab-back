from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime
from pydantic import BaseModel
from core.db import get_db
from core.firebase_auth import verify_firebase_token
from core.models import User, Scrap, Restaurant, Collection

router = APIRouter(prefix="/scraps", tags=["scraps"])

class ScrapCreate(BaseModel):
    restaurant_id: int
    collection_id: int | None = None

class CollectionCreate(BaseModel):
    name: str

class CollectionResponse(BaseModel):
    id: int
    name: str
    image_url: str | None = None
    created_at: datetime
    has_scraps: bool


# 스크랩 추가
@router.post("/create")
def create_scrap(
    scrap_data: ScrapCreate,
    db: Session = Depends(get_db),
    uid: str = Depends(verify_firebase_token)
):
    restaurant_id = scrap_data.restaurant_id
    collection_id = scrap_data.collection_id
    
    user = db.query(User).filter(User.firebase_uid == uid).first()
    if not user:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다.")

    existing_scrap = db.query(Scrap).filter(
        Scrap.user_id == user.id,
        Scrap.restaurant_id == restaurant_id
    ).first()

    if existing_scrap:
        return {"message": "이미 스크랩된 식당입니다.", 
                "scrap": {"user_id": user.id, "restaurant_id": restaurant_id, "created_at": existing_scrap.created_at, "collection_id": existing_scrap.collection_id}}

    new_scrap = Scrap(user_id=user.id, restaurant_id=restaurant_id, collection_id=collection_id, created_at=datetime.utcnow())
    db.add(new_scrap)
    db.commit()
    db.refresh(new_scrap)

    return {
        "message": "스크랩 성공",
        "scrap": {
            "user_id": user.id,
            "restaurant_id": restaurant_id,
            "collection_id": new_scrap.collection_id,
            "created_at": new_scrap.created_at
        }
    }

# 스크랩 목록 조회: 식당의 id, 이름, 카테고리 반환
@router.get("/me")
def get_my_scraps(
    collection_id: int | None = None,
    db: Session = Depends(get_db),
    uid: str = Depends(verify_firebase_token)
):
    user = db.query(User).filter(User.firebase_uid == uid).first()
    if not user:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다.")

    query = db.query(Scrap).filter(Scrap.user_id == user.id)

    if collection_id is not None:
        query = query.filter(Scrap.collection_id == collection_id)
        
    scraps = query.order_by(Scrap.created_at.desc()).all()
    restaurant_ids = [s.restaurant_id for s in scraps]
    restaurants = db.query(Restaurant).filter(Restaurant.id.in_(restaurant_ids)).all()
    restaurant_map = {r.id: r for r in restaurants}
            
    response_list = []
    for scrap in scraps:
        restaurant = restaurant_map.get(scrap.restaurant_id)
        if restaurant:
            response_list.append({
                "id": restaurant.id,
                "name": restaurant.name,
                "category": restaurant.category,
                "address": restaurant.address, 
                "image": restaurant.image,
                "is_scrapped": True
            })

    return response_list

# 스크랩 삭제
@router.delete("/{restaurant_id}")
def delete_scrap(
    restaurant_id: int,
    db: Session = Depends(get_db),
    uid: str = Depends(verify_firebase_token)
):
    user = db.query(User).filter(User.firebase_uid == uid).first()
    if not user:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다.")

    scrap = db.query(Scrap).filter(
        Scrap.user_id == user.id,
        Scrap.restaurant_id == restaurant_id
    ).first()
    if not scrap:
        raise HTTPException(status_code=404, detail="스크랩 정보를 찾을 수 없습니다.")

    db.delete(scrap)
    db.commit()
    return {"message": "스크랩 취소 성공", "restaurant_id": restaurant_id}

# 스크랩 상태 확인
@router.get("/{restaurant_id}")
def get_scrap_status(
    restaurant_id: int,
    db: Session = Depends(get_db),
    uid: str = Depends(verify_firebase_token)
):
    user = db.query(User).filter(User.firebase_uid == uid).first()
    if not user:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다.")

    scrap = db.query(Scrap).filter(
        Scrap.user_id == user.id,
        Scrap.restaurant_id == restaurant_id
    ).first()

    return {"is_scrapped": bool(scrap)}

# 컬렉션 생성
@router.post("/collections", response_model=CollectionResponse, tags=["collections"])
def create_user_collection(
    collection_data: CollectionCreate,
    db: Session = Depends(get_db),
    uid: str = Depends(verify_firebase_token)
):
    user = db.query(User).filter(User.firebase_uid == uid).first()
    if not user:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다.")

    existing_collection = db.query(Collection).filter(
        Collection.user_id == user.id,
        Collection.name == collection_data.name
    ).first()
    if existing_collection:
        raise HTTPException(status_code=409, detail="동일한 이름의 컬렉션이 이미 존재합니다.")

    new_collection = Collection(
        user_id=user.id,
        name=collection_data.name,
        created_at=datetime.utcnow()
    )
    
    db.add(new_collection)
    db.commit()
    db.refresh(new_collection)

    return CollectionResponse(
        id=new_collection.id,
        name=new_collection.name,
        image_url=None, # 새로 생성된 컬렉션은 대표 이미지가 없음
        created_at=new_collection.created_at,
        has_scraps=False
    )
    
# 컬렉션 목록 조회
@router.get("/collections/me", response_model=list[CollectionResponse], tags=["collections"])
def get_my_collections(
    db: Session = Depends(get_db),
    uid: str = Depends(verify_firebase_token)
):
    user = db.query(User).filter(User.firebase_uid == uid).first()
    if not user:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다.")

    collections = db.query(Collection)\
        .filter(Collection.user_id == user.id)\
        .order_by(Collection.created_at.desc())\
        .all()
    
    response_list = []

    for collection in collections:
        collection_image_url = None
        
        scrap_count = db.query(Scrap).filter(Scrap.collection_id == collection.id).count()
        has_scraps = scrap_count > 0
        
        latest_scrap = None
        if has_scraps:
            latest_scrap = db.query(Scrap)\
                .filter(Scrap.collection_id == collection.id)\
                .order_by(Scrap.created_at.desc())\
                .first()

        if latest_scrap and latest_scrap.restaurant:
            image_field = latest_scrap.restaurant.image
            
            if image_field and isinstance(image_field, str):
                images = [url.strip() for url in image_field.split(',') if url.strip()]
                if images:
                    collection_image_url = images[0]

            if has_scraps and collection_image_url is None:
                collection_image_url = ""
                
        response_list.append(CollectionResponse(
            id=collection.id,
            name=collection.name,
            image_url=collection_image_url,
            created_at=collection.created_at,
            has_scraps=has_scraps
        ))
        
    return response_list

# 컬렉션 삭제
@router.delete("/collections/{collection_id}", tags=["collections"])
def delete_user_collection(
    collection_id: int,
    db: Session = Depends(get_db),
    uid: str = Depends(verify_firebase_token)
):
    user = db.query(User).filter(User.firebase_uid == uid).first()
    if not user:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다.")

    # 1. 컬렉션 조회 및 권한 확인
    collection = db.query(Collection).filter(
        Collection.id == collection_id,
        Collection.user_id == user.id
    ).first()

    if not collection:
        raise HTTPException(status_code=404, detail="컬렉션을 찾을 수 없거나 삭제 권한이 없습니다.")

    # 2. 해당 컬렉션에 포함된 스크랩들의 collection_id를 NULL로 업데이트
    db.query(Scrap).filter(
        Scrap.collection_id == collection_id,
        Scrap.user_id == user.id
    ).update({Scrap.collection_id: None})

    # 3. 컬렉션 삭제
    db.delete(collection)
    db.commit()

    return {"message": "컬렉션 삭제 성공", "collection_id": collection_id}