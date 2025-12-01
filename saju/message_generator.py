from typing import List, Tuple, Dict
from collections import Counter

# 과다 오행의 상극 오행 반환: 상극 관계(木극土, 火극金, 土극水, 金극木, 水극火)
def get_counter_oheng(oheng: str) -> str: 	
    if oheng == '목(木)': return '금(金)'
    if oheng == '화(火)': return '수(水)'
    if oheng == '토(土)': return '목(木)'
    if oheng == '금(金)': return '화(火)'
    if oheng == '수(水)': return '토(土)'
    return ""

# 오행 리스트를 문자열로 변환 예) ['목(木)', '화(火)'] -> '목(木)과 화(火)'
def _get_oheng_string_list(oheng_list: List[str]) -> str:
    if not oheng_list: return ""
    if len(oheng_list) == 1: return oheng_list[0]
    return f"{', '.join(oheng_list[:-1])}와 {oheng_list[-1]}"

# 추천 오행을 Counter에 업데이트
def _update_oheng_counter(oheng_counter: Counter, ohengs: List[str]):
    for oheng in ohengs:
        oheng_counter[oheng] += 1
def define_oheng_messages(
    lacking: List[str], 
    strong: List[str], 
    oheng_type: str,
    final_oheng_scores: Dict[str, float] # 추가된 인수
) -> Tuple[str, str, Dict[str, int], List[str], List[str]]:
    analysis_headline = ""
    advice_parts = [] 
    recommended_oheng_counter = Counter()
    
    # 제어 오행 (과도 오행의 상극 오행)을 담을 리스트 
    control_ohengs: List[str] = []
    
    # 제목 생성 로직
    if oheng_type == "균형형":
        # 균형형의 제목은 아래 메시지 생성 로직에서 동적으로 결정됩니다.
        analysis_headline = "" 
    else: # 무형, 치우침형
        # 제목을 부족/과다 기운 기준으로 다시 생성
        lacking_str = _get_oheng_string_list(lacking)
        strong_str = _get_oheng_string_list(strong)
        
        if lacking and strong:
            analysis_headline = f"{strong_str} 기운이 강하고, {lacking_str} 기운이 부족해요!"
        elif lacking:
            analysis_headline = f"{lacking_str} 기운이 부족한 하루예요!"
        else:
            analysis_headline = f"{strong_str} 기운이 강한 하루예요!"

    # 추천 메시지 생성
    if oheng_type == "균형형":
        
        # 5개의 오행 수치의 평균 (100 / 5 = 20)
        HENG_AVERAGE = 20.0 
        
        lacking_name = lacking[0]  # 가장 낮은 오행 
        strong_name = strong[0]    # 가장 높은 오행
            
        diff_lacking = abs(final_oheng_scores.get(lacking_name, 0) - HENG_AVERAGE) 
        diff_strong = abs(final_oheng_scores.get(strong_name, 0) - HENG_AVERAGE) 
            
        advice_parts.append(f"오늘은 오행이 조화를 이루어, 평온한 기운이 감도는 날입니다.")

        # 부족 오행이 더 두드러진 경우 (평균에서 더 멀리 떨어짐) -> 보충 전략
        if diff_lacking >= diff_strong:
                
                analysis_headline = f"오행이 안정된 하루, {lacking_name} 기운이 가장 약해요." 
                
                advice_parts.append(
                    f"다만 {lacking_name} 기운이 조금 약하게 나타나, 이 기운의 색과 음식으로 균형을 맞추면 하루가 더욱 순조롭게 흘러갈 거예요."
                )
                
                _update_oheng_counter(recommended_oheng_counter, [lacking_name])
                control_ohengs.append(lacking_name)
                
        # 강한 오행이 더 두드러진 경우 (평균에서 더 멀리 떨어짐) -> 억제 전략
        else: 
                control_name = get_counter_oheng(strong_name) # 강한 오행의 상극 
                
                analysis_headline = f"오행이 안정된 하루, {strong_name} 기운이 살짝 강해요." 
                
                advice_parts.append(
                    f"다만 {strong_name} 기운이 조금 강하게 작용해, 상극 오행인 {control_name} 기운의 색과 음식으로 균형을 맞추면 하루가 더욱 순조롭게 흘러갈 거예요."
                )
                _update_oheng_counter(recommended_oheng_counter, [control_name])
                control_ohengs.append(control_name)
    
    # 무형/치우침형: 부족 오행 보충 + 과다 오행 상극 억제
    elif oheng_type == "무형" or oheng_type == "치우침형":
        
        if lacking:
            lacking_str = _get_oheng_string_list(lacking)
            advice_parts.append(f"부족한 {lacking_str} 기운을 보충해 에너지를 채워주세요.")
            _update_oheng_counter(recommended_oheng_counter, lacking)
        
        if strong:
            strong_str = _get_oheng_string_list(strong)
            
            control_ohengs = [get_counter_oheng(o) for o in strong]
            control_str = _get_oheng_string_list(control_ohengs)
            
            advice_parts.append(f"강한 {strong_str} 기운은 상극 오행인 {control_str} 기운으로 눌러 조화를 이루면 좋아요!")
            _update_oheng_counter(recommended_oheng_counter, control_ohengs)
        
        
        # 기운 편차 크다고 시작하는 문장
        if len(advice_parts) > 0:
            advice_parts.insert(0, f"오늘은 기운의 편차가 커서 에너지의 흐름이 불안정할 수 있습니다.")
        
    # 최종 추천 메시지 문자열 생성: 문장별로 띄어쓰기를 추가하여 자연스럽게 연결
    advice_message = " ".join(advice_parts)
    
    # strong_ohengs는 strong 리스트와 동일
    return analysis_headline, advice_message, dict(recommended_oheng_counter), control_ohengs, strong