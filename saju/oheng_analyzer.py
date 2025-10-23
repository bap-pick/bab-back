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
    
    # A. 균형형: 가장 강한 오행 1개 억제
    if oheng_type == "균형형":
        lacking_oheng = []
        strong_oheng = oheng_names[-1:] 
    # B. 치우침형: 가장 부족한 오행 2개 보충, 가장 강한 오행 1개 억제
    elif oheng_type == "치우침형":
        lacking_oheng = oheng_names[:2] 
        strong_oheng = oheng_names[-1:]
    # C. 무형: 가장 부족한 오행 1개 보충, 가장 강한 오행 2개 억제
    else:
        lacking_oheng = oheng_names[:1] 
        strong_oheng = oheng_names[-2:]
    
    result["oheng_type"] = oheng_type
    result["primary_supplement_oheng"] = lacking_oheng
    result["secondary_control_oheng"] = strong_oheng
    
    return result