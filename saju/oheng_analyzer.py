from typing import Dict, List

# 임계값 정의 
THRESHOLD_MUHANG: float = 5.0 # 무형 기준: 5.0% 미만
THRESHOLD_MAX_MIN_DIFF: float = 10.0 # 최대-최소 사이가 10.0% 이하라면 균형형

# 사용자 사주 오행 유형 분류 로직
def classify_and_determine_recommendation(
    oheng_scores: Dict[str, float]
) -> Dict[str, str | List[str]]:
    sorted_oheng = sorted(oheng_scores.items(), key=lambda item: item[1]) 
    
    oheng_names: List[str] = [item[0] for item in sorted_oheng]
    oheng_values: List[float] = [item[1] for item in sorted_oheng]
    
    result = {}
    oheng_type = ""

    ## 오행 유형 분류
    max_diff = oheng_values[-1] - oheng_values[0] # 오행 수치 최대-최소 차이 계산

    # A. 무형 판별: 특정 오행의 수치가 5.0% 이하라면
    if oheng_values[0] < THRESHOLD_MUHANG:
        oheng_type = "무형"
    # B. 균형형 판별 (최대-최소 차이 기준)
    elif max_diff <= THRESHOLD_MAX_MIN_DIFF:
        oheng_type = "균형형"
    # C. 그 외는 치우침형으로 분류
    else:
        oheng_type = "치우침형"
    
    
    ## 보충 오행, 억제 오행 선정
    lacking_oheng: List[str] = []
    strong_oheng: List[str] = []
    
    # 오행 수치 최소값과 최대값 추출
    min_value = oheng_values[0] # 가장 낮은 오행 수치
    max_value = oheng_values[-1] # 가장 높은 오행 수치
    
    # 1. 부족 오행 선정: 최소값과 동일한 모든 오행을 부족 오행으로 선정
    for i in range(len(oheng_values)):
        if oheng_values[i] == min_value:
            lacking_oheng.append(oheng_names[i])
            
    # 2. 과다 오행 선정: 최대값과 동일한 모든 오행을 과다 오행으로 선정
    for i in range(len(oheng_values) - 1, -1, -1):
        if oheng_values[i] == max_value:
            strong_oheng.append(oheng_names[i])
            
    result["oheng_type"] = oheng_type
    result["primary_supplement_oheng"] = lacking_oheng
    result["secondary_control_oheng"] = strong_oheng
    
    return result