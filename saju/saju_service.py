from sqlalchemy.orm import Session
from datetime import date, time, timedelta, datetime
from typing import Optional, Dict
from sqlalchemy import desc
from fastapi import HTTPException

from core.models import User, Manse 
from saju.saju_calculator import get_time_pillar, calculate_oheng_score

# Manse 테이블에서 자시, 절입 시간 보정
def _get_manse_record(
    db: Session, 
    birth_date: date, 
    birth_time: Optional[time], 
    birth_calendar: str
) -> Optional[Manse]:
    
    # 1. 자시(子時) 처리: 23:30 이후 출생이면 사주상 다음 날의 일주로 간주 (일주 보정)
    search_date = birth_date
    if birth_time and birth_time >= time(23, 30):
        search_date += timedelta(days=1)
    
    # 2. 만세력 레코드 조회
    if birth_calendar == "solar":
        manse_record = db.query(Manse).filter(Manse.solarDate == search_date).first()
    
    # 음력/윤달 분기 처리
    elif birth_calendar.startswith("lunar"):
        
        # 'lunar_leap'일 경우 is_leap_month = 1 (True), 아니면 0 (False)
        is_leap_month = 1 if birth_calendar == "lunar_leap" else 0
        
        manse_record = db.query(Manse).filter(
            Manse.lunarDate == search_date,
            # DB의 leapMonth 필드를 is_leap_month 변수 값으로 필터링
            Manse.leapMonth == is_leap_month 
        ).first()
        
    else:
        return None
    
    if not manse_record:
        return None

    # 3. 절입 시간(seasonStartTime) 처리 (월주/년주 보정)
    if manse_record.seasonStartTime and birth_time:
        
        # 실제 출생 시각
        birth_datetime_user = datetime.combine(birth_date, birth_time)
        season_datetime = manse_record.seasonStartTime
        
        # 실제 출생 시각이 절입 시각보다 빠른 경우 (이전 절기의 월주/년주 사용)
        if birth_datetime_user < season_datetime:
            
            # 현재 레코드의 solarDate보다 작으면서, 가장 최신인 레코드 (직전 절기)를 찾음
            previous_manse_record = db.query(Manse).filter(
                Manse.solarDate < manse_record.solarDate
            ).order_by(desc(Manse.solarDate)).first()
            
            if previous_manse_record:
                # 이전 절기의 월주와 년주를 현재 사주에 적용
                manse_record.yearSky = previous_manse_record.yearSky
                manse_record.yearGround = previous_manse_record.yearGround
                manse_record.monthSky = previous_manse_record.monthSky
                manse_record.monthGround = previous_manse_record.monthGround
            
    return manse_record

# 사주 오행 계산 및 저장
async def calculate_saju_and_save(
    user: User,
    db: Session
) -> Dict[str, float]:
    
    birth_date = user.birth_date
    birth_time = user.birth_time
    birth_calendar = user.birth_calendar
    
    if not all([birth_date, birth_calendar]):
        raise HTTPException(status_code=400, detail="사주 계산에 필요한 생년월일 정보가 부족합니다.")
    
    # 1. 만세력 데이터 조회 및 보정 (삼주 확보)
    manse_record = _get_manse_record(db, birth_date, birth_time, birth_calendar)
    
    if not manse_record:
        raise HTTPException(status_code=404, detail="만세력 데이터베이스에서 해당 기록을 찾을 수 없어 사주 계산을 완료할 수 없습니다.")
    
    # 2. 시주 계산 (사주팔자 완성)
    time_pillar = get_time_pillar(manse_record.daySky, birth_time)
    
    # 사주팔자 기둥 구성
    saju_pillars = {
        'year_sky': manse_record.yearSky, 'year_ground': manse_record.yearGround,
        'month_sky': manse_record.monthSky, 'month_ground': manse_record.monthGround,
        'day_sky': manse_record.daySky, 'day_ground': manse_record.dayGround,
        'time_sky': time_pillar.get('time_sky') if time_pillar else None, 
        'time_ground': time_pillar.get('time_ground') if time_pillar else None,
    }

    # 3. 오행 비율 계산
    oheng_percentages = calculate_oheng_score(saju_pillars)

    # 4. Users 테이블에 오행 정보 업데이트 및 저장
    user.oheng_wood = oheng_percentages.get("oheng_wood")
    user.oheng_fire = oheng_percentages.get("oheng_fire")
    user.oheng_earth = oheng_percentages.get("oheng_earth")
    user.oheng_metal = oheng_percentages.get("oheng_metal")
    user.oheng_water = oheng_percentages.get("oheng_water")
    
    db.commit()
    db.refresh(user)
    
    return oheng_percentages