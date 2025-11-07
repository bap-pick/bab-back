from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload
from typing import List, Optional
from pydantic import BaseModel
from datetime import time
from core.firebase_auth import verify_firebase_token
from core.db import get_db
from core.models import Restaurant, RestaurantFacility

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