import time
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload
from typing import List, Optional
from pydantic import BaseModel
from datetime import time as DtTime
from core.firebase_auth import verify_firebase_token
from core.db import get_db
from core.models import Restaurant, RestaurantFacility, Reviews
from services.restaurant_service import RestaurantLocationService
from services.restaurant_cache_service import RestaurantCacheService

router = APIRouter(prefix="/restaurants", tags=["restaurants"])

class MenuBase(BaseModel):
    id: int
    menu_name: Optional[str] = None
    menu_price: Optional[int] = None 
    
    class Config:
        from_attributes = True
        
class OpeningHourBase(BaseModel):
    day: Optional[str]
    open_time: Optional[DtTime]
    close_time: Optional[DtTime]
    break_start: Optional[DtTime]
    break_end: Optional[DtTime]
    last_order: Optional[DtTime]
    is_closed: bool

    class Config:
        from_attributes = True

class FacilityBase(BaseModel):
    id: int
    name: Optional[str]

    class Config:
        from_attributes = True

class ReviewBase(BaseModel):
    id: int
    rating: Optional[float] = None
    visitor_reviews: int
    blog_reviews: int

    class Config:
        from_attributes = True
        
class RestaurantDetail(BaseModel):
    id: int
    name: str
    category: str
    address: Optional[str]
    phone: Optional[str]
    image: Optional[str] = None

    latitude: Optional[float] = None
    longitude: Optional[float] = None
    
    menus: List[MenuBase] 
    hours: List[OpeningHourBase]
    facilities: List[FacilityBase]
    reviews: List[ReviewBase]

    class Config:
        from_attributes = True
        
class RestaurantSearchItem(BaseModel):
    id: int
    name: str
    category: str
    address: Optional[str]
    rating: Optional[float] = None

    class Config:
        from_attributes = True

class RestaurantSearchResult(BaseModel):
    count: int
    restaurants: List[RestaurantSearchItem]
    
# 식당 상세 정보 조회 API
@router.get(
    "/detail/{restaurant_id}",
    response_model=RestaurantDetail,
    dependencies=[Depends(verify_firebase_token)] 
)
def get_restaurant_detail(
    restaurant_id: int, 
    db: Session = Depends(get_db),
):
    # 1. ID를 기반으로 식당 정보 조회
    restaurant = db.query(Restaurant).options(
        joinedload(Restaurant.menus),           
        joinedload(Restaurant.hours),
        joinedload(Restaurant.reviews),         
        joinedload(Restaurant.facility_associations).joinedload(RestaurantFacility.facility),
    ).filter(Restaurant.id == restaurant_id).first()
    
    # 2. 결과 처리
    if not restaurant:
        # 데이터가 없으면 404 에러 반환
        raise HTTPException(status_code=404, detail=f"Restaurant with ID {restaurant_id} not found")
    
    return restaurant

# 현재 위치 근처 식당 조회 (1km 이내 리뷰 많은 순 정렬)
@router.get("/nearby")
def get_nearby_restaurants(
    lat: float = Query(..., description="현재 위도"),
    lon: float = Query(..., description="현재 경도"),
    limit: Optional[int] = Query(5, description="가져올 식당 개수"),
    db: Session = Depends(get_db)
):    
    start_time = time.time()
    
    # 1. Redis에서 1km 이내 식당 필터링
    location_service = RestaurantLocationService()
    
    redis_start = time.time()
    distance_map = location_service.get_nearby_ids_with_distance(
        longitude=lon,
        latitude=lat,
        radius_km=1.0,
    )
    redis_time = time.time() - redis_start
    
    if not distance_map:
        print("1km 이내 식당 없음")
        return {"count": 0, "restaurants": []}
    
    restaurant_ids = list(distance_map.keys())
    print(f"Redis 조회: {len(restaurant_ids)}개 식당 (1km 이내)")
    
    # 2. Redis 캐시에서 식당 상세 정보 조회
    summary_service = RestaurantCacheService() # 캐시 서비스 인스턴스
    db_start = time.time()
    
    # Redis Hash에서 식당 ID 목록의 요약 정보를 한 번에 가져옴
    summaries = summary_service.get_summaries_by_ids(restaurant_ids)
    
    db_time = time.time() - db_start
    
    # 3. 데이터 결합 및 정렬
    restaurants_data = []
    
    for r_id, summary in summaries.items():
        # Redis GeoSet에서 가져온 거리
        distance_km = distance_map.get(r_id, 0)
        
        restaurants_data.append({
            "id": r_id,
            "name": summary["name"],
            "category": summary["category"], 
            "address": summary["address"],
            "image": summary["image"],
            "latitude": summary["latitude"], 
            "longitude": summary["longitude"],
            "rating": summary["rating"],
            "review_count": summary["review_count"],
            "distance_km": round(distance_km, 2),
            "distance_m": int(distance_km * 1000)
        })
    
    # 리뷰 많은 순 정렬
    restaurants_data.sort(key=lambda x: x["review_count"], reverse=True)
    
    # limit 적용
    if limit:
        restaurants_data = restaurants_data[:limit]
    
    total_time = time.time() - start_time
    
    print(f"Redis Geo: {redis_time:.4f}초, Redis Hash: {db_time:.4f}초, 총: {total_time:.4f}초")
    
    return {
        "count": len(restaurants_data),
        "restaurants": restaurants_data
    }

# 식당 검색 API
@router.get(
    "/search",
    response_model=RestaurantSearchResult,
    dependencies=[Depends(verify_firebase_token)]
)
def search_restaurants(
    keyword: str = Query(..., min_length=1, description="검색 키워드 (식당명 또는 카테고리)"),
    limit: int = Query(10, gt=0, description="최대 반환 개수"),
    db: Session = Depends(get_db)
):
    search_term = f"%{keyword}%"
    
    query = db.query(
        Restaurant,
        Reviews.rating.label('rating')
    ).outerjoin(Reviews, Restaurant.id == Reviews.restaurant_id).filter(
        (Restaurant.name.ilike(search_term)) | (Restaurant.category.ilike(search_term))
    ).limit(limit)

    results = query.all()
    
    restaurants_data = []
    for restaurant, rating_value in results:
        final_rating = float(rating_value) if rating_value is not None else None
        
        restaurants_data.append(RestaurantSearchItem(
            id=restaurant.id,
            name=restaurant.name,
            category=restaurant.category,
            address=restaurant.address,
            rating=final_rating
        ))
        
    return {
        "count": len(restaurants_data),
        "restaurants": restaurants_data
    }