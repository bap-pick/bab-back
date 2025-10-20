from typing import Dict, List

# 임계값 정의 
THRESHOLD_MUHANG: float = 5.0      # 무某行 기준: 5.0% 미만
THRESHOLD_BALANCE_LOW: float = 15.0  # 균형 하한선
THRESHOLD_BALANCE_HIGH: float = 25.0 # 균형 상한선 (20% ± 5%)
THRESHOLD_STDDEV_BALANCE: float = 10.0 # 전체 강/약 판별 시 활용 가능

# 사용자 사주 오행 유형 분류 로직
def classify_and_determine_recommendation(
    oheng_scores: Dict[str, float]
) -> Dict[str, str | List[str]]:

    # 5개 오행 비율을 리스트로 변환
    sorted_oheng = sorted(oheng_scores.items(), key=lambda item: item[1])
    
    oheng_names: List[str] = [item[0] for item in sorted_oheng] # 낮은 순 오행 이름
    oheng_values: List[float] = [item[1] for item in sorted_oheng]
    
    result = {}
    oheng_type = ""

    # 1. 무某行형 판별 (가장 낮은 오행이 무형 기준 미만인지)
    if oheng_values[0] < THRESHOLD_MUHANG:
        oheng_type = "무형"
    
    # 2. 균형형 판별 (모든 오행이 균형 범위 내인지)
    elif all(THRESHOLD_BALANCE_LOW <= v <= THRESHOLD_BALANCE_HIGH for v in oheng_values):
        oheng_type = "균형형"
    
    # 3. 그 외는 치우침형으로 분류
    else:
        oheng_type = "치우침형"
    
    lacking_oheng: List[str] = []
    strong_oheng: List[str] = []
    
    if oheng_type == "균형형":
        lacking_oheng = []
        strong_oheng = oheng_names[-1:] # 가장 높은 오행 1개만 제어 대상으로 지정
    
    elif oheng_type == "치우침형":
        lacking_oheng = [name for name, value in sorted_oheng if value < THRESHOLD_BALANCE_LOW][:2]
        all_strong_oheng = [name for name, value in sorted_oheng if value > THRESHOLD_BALANCE_HIGH]
        
        strong_oheng = all_strong_oheng[-2:]
        
        # 예외 처리: 25.0%를 넘는 오행이 하나도 없다면, 가장 높은 1개만 제어 오행으로 지정 
        if not strong_oheng:
            strong_oheng = oheng_names[-1:] 
            
    else: # 무형
        # 가장 낮은 2개를 보충 오행으로 설정
        lacking_oheng = oheng_names[:2] 
        # 가장 높은 오행 1개를 제어 오행으로 추가
        strong_oheng = oheng_names[-1:]
    
    result["oheng_type"] = oheng_type
    result["primary_supplement_oheng"] = lacking_oheng
    result["secondary_control_oheng"] = strong_oheng
    
    return result