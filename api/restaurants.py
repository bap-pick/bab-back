from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func
from typing import List, Optional
from pydantic import BaseModel
from datetime import time
from core.firebase_auth import verify_firebase_token
from core.db import get_db
from core.models import Restaurant, RestaurantFacility, Reviews

router = APIRouter(prefix="/restaurants", tags=["restaurants"])

from pydantic import BaseModel
from typing import Optional, List

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
    
    menus: List[MenuBase] 
    hours: List[OpeningHourBase]
    facilities: List[FacilityBase]
    reviews: List[ReviewBase]

    class Config:
        from_attributes = True
        
# 식당 캐러셜 카드용 일부 내용만 
class RestaurantSummary(BaseModel):
    id: int
    name: str
    category: str
    address: Optional[str]
    image: Optional[str] = None
    
    rating: float = 0.0
    review_count: int = 0

    class Config:
        from_attributes = True
                
                
# 식당 상세 정보 및 메뉴 조회 API
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

# 식당 목록 가져오기 (홈 화면의 식당 캐러셜 카드용 - 일부 정보만)
@router.get(
    "/summaries",
    response_model=List[RestaurantSummary],
    dependencies=[Depends(verify_firebase_token)] 
)
def get_restaurant_summaries(
    # 예) /restaurants/summaries?ids=1&ids=5&ids=8
    ids: List[int] = Query(..., description="조회할 식당 ID 목록"), 
    db: Session = Depends(get_db),
):
    # 식당 정보 조회: 방문자 리뷰와 블로그 리뷰를 합산해 review_count로 반환
    query = db.query(
        Restaurant,
        Reviews.rating.label('rating'),
        (func.coalesce(Reviews.visitor_reviews, 0) + func.coalesce(Reviews.blog_reviews, 0)).label('review_count')
    ).outerjoin(Reviews, Restaurant.id == Reviews.restaurant_id).filter(Restaurant.id.in_(ids))
    
    results = query.all()
    
    summaries = []
    for restaurant, rating_value, count_value in results:        
        final_rating = float(rating_value) if rating_value is not None else 0.0
        final_review_count = count_value if count_value is not None else 0
        
        # Pydantic 모델(RestaurantSummary)에 데이터를 매핑하여 객체 생성
        summary = RestaurantSummary(
            id=restaurant.id,
            name=restaurant.name,
            category=restaurant.category,
            address=restaurant.address,
            image=restaurant.image,
            rating=final_rating,
            review_count=final_review_count
        )
        summaries.append(summary)

    return summaries