from fastapi import APIRouter, Depends, HTTPException, Query, Body
from sqlalchemy.orm import Session
from typing import List
from pydantic import BaseModel, Field
from datetime import datetime, date, time
from core.firebase_auth import verify_firebase_token
from core.db import get_db
from core.models import Reservation, Restaurant, User 

router = APIRouter(prefix="/reservations", tags=["reservations"])

# 예약 요청을 위한 Pydantic 모델
class ReservationCreate(BaseModel):
    restaurant_id: int = Field(..., description="식당 ID") 
    reservation_date: date = Field(..., description="예약 날짜 (YYYY-MM-DD)") 
    reservation_time: time = Field(..., description="예약 시간 (HH:MM:SS)") 
    # ⭐️ 변경: people_count를 Integer 타입으로 변경합니다.
    people_count: int = Field(..., description="예약 인원 수")

# 예약 응답을 위한 Pydantic 모델
class ReservationDisplay(BaseModel):
    id: int
    restaurant_id: int
    # ⭐️ 변경: user_id를 Integer 타입으로 변경합니다.
    user_id: int
    reservation_date: date # 👈 DB와 일치하는 date 타입
    reservation_time: time
    # ⭐️ 변경: people_count를 Integer 타입으로 변경합니다.
    people_count: int
    # ⭐️ 추가: created_at 필드를 DateTime 타입으로 추가합니다.
    created_at: datetime 
    
    # 조회를 위해 식당 이름도 함께 반환
    restaurant_name: str 
    
    class Config:
        from_attributes = True


# 1. 예약 생성 API
@router.post("/create", response_model=ReservationDisplay)
def create_reservation(
    reservation: ReservationCreate,
    db: Session = Depends(get_db),
    uid: str = Depends(verify_firebase_token)
):
    user = db.query(User).filter(User.firebase_uid == uid).first()
    if not user:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다.")

    # 식당 ID 유효성 검사
    restaurant = db.query(Restaurant).filter(Restaurant.id == reservation.restaurant_id).first()
    if not restaurant:
        raise HTTPException(status_code=404, detail="Restaurant not found")
        
    db_reservation = Reservation(
        user_id= user.id,
        restaurant_id=reservation.restaurant_id,
        reservation_date=reservation.reservation_date, 
        reservation_time=reservation.reservation_time,
        people_count=reservation.people_count
    )
    
    db.add(db_reservation)
    db.commit()
    db.refresh(db_reservation)

    # 응답 모델 생성
    return ReservationDisplay(
        **db_reservation.__dict__,
        restaurant_name=restaurant.name
    )


# 2. 내 예약 목록 조회 API
# 2. 내 예약 목록 조회 API
@router.get("/", response_model=List[ReservationDisplay])
def get_user_reservations(
    # ⭐️ 변경: 특정 날짜를 필터링하기 위한 선택적 쿼리 파라미터 추가
    target_date: date = Query(None, description="조회할 특정 예약 날짜 (YYYY-MM-DD, 선택 사항)"),
    db: Session = Depends(get_db),
    uid: str = Depends(verify_firebase_token)
):
    """현재 사용자의 모든 예약 목록을 조회합니다. target_date를 제공하면 해당 날짜의 예약만 조회합니다."""
    
    # DB user_id를 가져옵니다.
    user = db.query(User).filter(User.firebase_uid == uid).first()
    if not user:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다.")

    # 기본 쿼리 설정
    query = db.query(Reservation, Restaurant.name).join(
        Restaurant, Reservation.restaurant_id == Restaurant.id
    ).filter(
        Reservation.user_id == user.id # DB user_id로 필터링
    )

    # ⭐️ 추가: target_date가 제공된 경우 필터링 조건 추가
    if target_date:
        query = query.filter(Reservation.reservation_date == target_date)
    
    # 정렬 및 결과 조회
    reservations_with_name = query.order_by(
        Reservation.reservation_date.desc(), 
        Reservation.reservation_time.desc()
    ).all() # 최신순 정렬

    results = []
    for reservation, restaurant_name in reservations_with_name:
        results.append(ReservationDisplay(
            **reservation.__dict__,
            restaurant_name=restaurant_name
        ))
        
    return results

# 3. 예약 수정 API
@router.put("/{reservation_id}", response_model=ReservationDisplay)
def update_reservation(
    reservation_id: int,
    reservation_update: ReservationCreate,
    uid: str = Depends(verify_firebase_token),
    db: Session = Depends(get_db)
):
    user = db.query(User).filter(User.firebase_uid == uid).first()
    if not user:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다.")    
    
    db_reservation = db.query(Reservation).filter(
        Reservation.id == reservation_id,
        Reservation.user_id == user.id # DB user_id로 소유권 확인
    ).first()

    if not db_reservation:
        raise HTTPException(status_code=404, detail="Reservation not found or not owned by user")
    
    # 식당 ID 유효성 검사
    restaurant = db.query(Restaurant).filter(Restaurant.id == reservation_update.restaurant_id).first()
    if not restaurant:
        raise HTTPException(status_code=404, detail="Restaurant not found")
    
    db_reservation.restaurant_id = reservation_update.restaurant_id
    db_reservation.reservation_date = reservation_update.reservation_date
    db_reservation.reservation_time = reservation_update.reservation_time
    db_reservation.people_count = reservation_update.people_count 
    
    db.commit()
    db.refresh(db_reservation)
    
    return ReservationDisplay(
        **db_reservation.__dict__,
        restaurant_name=restaurant.name
    )

# 4. 예약 삭제 API
@router.delete("/{reservation_id}", status_code=204)
def delete_reservation(
    reservation_id: int,
    uid: str = Depends(verify_firebase_token),
    db: Session = Depends(get_db)
):
    user = db.query(User).filter(User.firebase_uid == uid).first()
    if not user:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다.")    
    
    
    #db_user_id = get_db_user_id(firebase_uid, db)
    
    db_reservation = db.query(Reservation).filter(
        Reservation.id == reservation_id,
        Reservation.user_id ==user.id # DB user_id로 소유권 확인
    ).first()
    
    if not db_reservation:
        raise HTTPException(status_code=404, detail="Reservation not found or not owned by user")
    
    db.delete(db_reservation)
    db.commit()
    return {"ok": True}