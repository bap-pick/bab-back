from datetime import time, datetime
from typing import Optional, Dict
from saju.saju_data import get_time_ju_data, get_time_ju_data2, get_ten_star, get_jijangan

# 일간과 출생 시각을 통해 시주 계산
def get_time_pillar(day_sky: str, birth_time: Optional[time]) -> Dict[str, Optional[str]]:
    # birth_time이 None일 경우 처리
    if birth_time is None:
        return {'time_sky': None, 'time_ground': None}

    # 1. 시지 인덱스 결정: 출생 시각을 12시진으로 매핑
    time_ju_data = get_time_ju_data() 
    time_index = None

    for index, time_range in time_ju_data.items():
        start_time, end_time = time_range[0], time_range[1]
        
        # 자시(子時, 23:30 ~ 01:29) 처리: 밤 11시 이후 or 새벽 1시 30분 미만
        # start_time이 end_time보다 큰 경우 (날짜 경계)
        if start_time > end_time: 
            # 출생 시각이 23:30 이후 이거나, 01:29 이전인 경우
            if birth_time >= start_time or birth_time <= end_time:
                time_index = index
                break
        # 일반적인 시진 범위 처리 (start_time <= birth_time <= end_time)
        elif start_time <= birth_time <= end_time:
            time_index = index
            break
            
    if time_index is None:
        # 시진 범위에 매핑되지 않은 경우 (오류 또는 데이터 누락)
        return {'time_sky': None, 'time_ground': None}


    # 2. 시간(時干) 및 시지(時支) 결정: 일간과 시지 인덱스에 따른 규칙 적용
    time_ju_data_2 = get_time_ju_data2()
    
    # 데이터 구조: time_ju_data_2[일간][시지_인덱스] = [천간, 지지]
    if day_sky in time_ju_data_2 and time_index in time_ju_data_2[day_sky]:
        pillar_data = time_ju_data_2[day_sky][time_index]
        return {'time_sky': pillar_data[0], 'time_ground': pillar_data[1]}
    
    # 데이터가 없는 경우
    return {'time_sky': None, 'time_ground': None} 


# 사주 팔자를 통해 오행 점수 (가중치) 계산
def calculate_oheng_score(saju_pillars: Dict[str, Optional[str]]) -> Dict[str, float]:
    print(f"DEBUG SAJU PILLARS: {saju_pillars}") 
    
    day_sky = saju_pillars.get('day_sky')
    if not day_sky:
        return {
            "oheng_wood": 0.0, "oheng_fire": 0.0, "oheng_earth": 0.0,
            "oheng_metal": 0.0, "oheng_water": 0.0
        }

    # 1. 오행 데이터 로드
    ten_star_data = get_ten_star().get(day_sky)
    jijangan_data = get_jijangan()

    oheng_scores = {
        "oheng_wood": 0.0, "oheng_fire": 0.0, "oheng_earth": 0.0,
        "oheng_metal": 0.0, "oheng_water": 0.0
    }
    
    if not ten_star_data or not jijangan_data:
        return oheng_scores 
        
    # 2. 오행 점수 합산 함수
    def add_oheng_score(oheng_str: str, score: float):
        if oheng_str == '목':
            oheng_scores["oheng_wood"] += score
        elif oheng_str == '화':
            oheng_scores["oheng_fire"] += score
        elif oheng_str == '토':
            oheng_scores["oheng_earth"] += score
        elif oheng_str == '금':
            oheng_scores["oheng_metal"] += score
        elif oheng_str == '수':
            oheng_scores["oheng_water"] += score

    # 3. 가중치 기준 설정 (총 100점 기준)
    # 천간(현상)보다 지지(근본적 기운)를 중심으로 보기 때문에 천간 30: 지지 70 비율로 설정
    # 계절의 기운이 사주 강약 판단의 핵심이기 때문에, 월지에 큰 가중치 부여
    TOTAL_SCORE = 100.0
    SKY_SCORE_TOTAL = TOTAL_SCORE * 0.3  # 천간 총 30점
    GROUND_SCORE_TOTAL = TOTAL_SCORE * 0.7 # 지지 총 70점
    MONTH_BONUS = 0.3                     # 월지 30% 추가 보정 비율

    # 천간 4자에 균등 분배할 기본 점수
    sky_base_score = SKY_SCORE_TOTAL / 4.0

    # 지지 4자에 균등 분배할 기본 점수 (보정 전)
    ground_base_score = GROUND_SCORE_TOTAL / 4.0 

    # 4. 천간 점수 계산 (30점 분배)
    for sky_key in ['year_sky', 'month_sky', 'day_sky', 'time_sky']:
        sky = saju_pillars.get(sky_key)
        if sky:
            oheng_info = ten_star_data.get(sky)
            if oheng_info:
                oheng = oheng_info[1]
                add_oheng_score(oheng, sky_base_score)


    # 5. 지지 + 지장간 점수 계산 (70점 분배 및 월지 보정)
    for ground_key in ['year_ground', 'month_ground', 'day_ground', 'time_ground']:
        ground = saju_pillars.get(ground_key)
        if not ground or ground not in jijangan_data:
            continue

        # 해당 지지(地支)에 할당할 총 점수
        current_ground_total_score = ground_base_score
        
        # 월지 보정: 월지(month_ground)일 경우 30% 추가 가중치 부여
        if ground_key == 'month_ground':
            current_ground_total_score *= (1.0 + MONTH_BONUS)

        # 해당 지지의 지장간 비율 총합 계산
        total_rate_sum = sum(float(hd.get("rate", 0)) for hd in jijangan_data[ground].values() if hd)
        
        if total_rate_sum == 0:
            continue

        for hidden_data in jijangan_data[ground].values():
            if hidden_data:
                oheng = hidden_data.get("fiveCircle")
                rate = float(hidden_data.get("rate", 0))

                if oheng and rate > 0:
                    # 지장간의 비율에 따라 해당 지지의 총 점수를 각 오행에 분배
                    score_to_add = current_ground_total_score * (rate / total_rate_sum)
                    add_oheng_score(oheng, score_to_add)

    # 6. 최종 비율 변환
    # 월지 가중치로 100점을 초과할 수 있으므로, 총점으로 다시 나누어 최종 비율 변환
    final_total_score = sum(oheng_scores.values())

    if final_total_score > 0:
        oheng_percentages = {
            key: round((score / final_total_score) * 100, 1)
            for key, score in oheng_scores.items()
        }
    else:
        oheng_percentages = {key: 0.0 for key in oheng_scores}

    return oheng_percentages