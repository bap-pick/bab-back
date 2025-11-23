from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func
from typing import List, Optional
from pydantic import BaseModel
from datetime import time
from core.firebase_auth import verify_firebase_token
from core.db import get_db
from core.models import Restaurant, RestaurantFacility, Reviews
from core.geo import calculate_distance

router = APIRouter(prefix="/restaurants", tags=["restaurants"])

class MenuBase(BaseModel):
    id: int
    menu_name: Optional[str] = None
    menu_price: Optional[int] = None 
    
    class Config:
        from_attributes = True
        
class OpeningHourBase(BaseModel):
    day: Optional[str]
    open_time: Optional[time]
    close_time: Optional[time]
    break_start: Optional[time]
    break_end: Optional[time]
    last_order: Optional[time]
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

# 현재 위치 근처 식당 5개 조회 (1km 이내 리뷰 많은 순 정렬)
@router.get(
    "/nearby",
    dependencies=[Depends(verify_firebase_token)]    
)
def get_nearby_restaurants(
    lat: float = Query(..., description="현재 위도"),
    lon: float = Query(..., description="현재 경도"),
    limit: Optional[int] = Query(None, description="가져올 식당 개수 제한"),
    db: Session = Depends(get_db)
):
    query = db.query(
        Restaurant,
        Reviews.rating.label('rating'),
        (func.coalesce(Reviews.visitor_reviews, 0) + func.coalesce(Reviews.blog_reviews, 0)).label('review_count')
    ).outerjoin(Reviews, Restaurant.id == Reviews.restaurant_id)
    
    results = query.all()

    nearby_with_distance = []
    for restaurant, rating_value, count_value in results:
        # DB에 위도/경도 데이터가 없는 식당은 제외
        if restaurant.latitude is None or restaurant.longitude is None:
            continue
        
        # 사용자가 설정한 위치와 식당 위치 간 거리 계산
        distance_km = calculate_distance(lat, lon, restaurant.latitude, restaurant.longitude)
        
        # 1km 이내 식당만 필터링
        if distance_km > 1.0: 
            continue
            
        final_rating = float(rating_value) if rating_value is not None else 0.0
        final_review_count = count_value if count_value is not None else 0
        
        # km 거리를 m단위로 변환
        distance_m = int(round(distance_km * 1000))
        
        restaurant_data = {
            "id": restaurant.id,
            "name": restaurant.name,
            "category": restaurant.category,
            "address": restaurant.address,
            "image": restaurant.image,
            "latitude": restaurant.latitude, 
            "longitude": restaurant.longitude,
            "rating": final_rating,
            "review_count": final_review_count,
            "distance_km": round(distance_km, 2),
            "distance_m": distance_m
        }
        
        nearby_with_distance.append(restaurant_data)

    # 거리순 정렬
    # nearby_with_distance.sort(key=lambda x: x["distance_km"])
    
    # 리뷰 수(review_count) 내림차순 정렬
    nearby_with_distance.sort(key=lambda x: x["review_count"], reverse=True)

    # limit 지정
    if limit:
        nearby_with_distance = nearby_with_distance[:limit]

    return {
        "count": len(nearby_with_distance),
        "restaurants": nearby_with_distance
    }
    