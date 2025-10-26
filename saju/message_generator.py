from typing import List, Tuple, Dict, Any
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
        
# 오행 유형에 따라 추천 메시지 생성
def define_oheng_messages(lacking: List[str], strong: List[str], oheng_type: str) -> Tuple[str, str, Dict[str, int]]:
    analysis_headline = ""
    advice_parts = [] 
    recommended_oheng_counter = Counter()
    
    # 제목 생성
    if oheng_type == "균형형":
        analysis_headline = f"오행이 안정된 하루, {strong[0]} 기운이 살짝 강해요."
    elif oheng_type == "무형":
        analysis_headline = f"{_get_oheng_string_list(lacking)} 기운이 거의 없는 무형이에요!"
    else: # 치우침형
        lacking_str = _get_oheng_string_list(lacking)
        strong_str = _get_oheng_string_list(strong)
        analysis_headline = f"{strong_str} 기운이 강하고, {lacking_str} 기운이 부족해요!"

    # 추천 메시지 생성
    if oheng_type == "균형형":
        advice_parts.append(f"오늘은 오행이 조화를 이루어, 평온한 기운이 감도는 날입니다.")
        
        strong_str = _get_oheng_string_list(strong)
        control_name = get_counter_oheng(strong_str)
            
        advice_parts.append(
            f"다만 {strong_str} 기운이 조금 강하게 작용하니, 상극 오행인 {control_name} 기운의 색과 음식으로 균형을 맞추면 하루가 더욱 순조롭게 흘러갈 거예요."
        )
        
        _update_oheng_counter(recommended_oheng_counter, [control_name])
    elif oheng_type == "무형" :
        lacking_str = _get_oheng_string_list(lacking)
        lacking_name1 = lacking[0]

        advice_parts.append(f"오늘은 {lacking_name1} 기운이 거의 느껴지지 않아 에너지의 흐름이 다소 불안정할 수 있습니다.")
        advice_parts.append(f"따라서 부족한 {lacking_name1} 기운을 음식이나 색을 통해 채워주고, ")
        
        strong1, strong2 = strong 
        control1 = get_counter_oheng(strong1)
        control2 = get_counter_oheng(strong2)
        advice_parts.append(f"과도한 {strong1} 기운과 {strong2} 기운은 상극 오행인 {control1} 기운과 {control2} 기운으로 살짝 눌러 조화를 이루어 보세요.")
    
        _update_oheng_counter(recommended_oheng_counter, [lacking_name1])
        _update_oheng_counter(recommended_oheng_counter, [control1, control2])
    else:
        advice_parts.append(f"오늘은 일부 오행이 과하고 일부는 부족해 기운의 균형이 흐트러져 있습니다.")
        
        strong_str = _get_oheng_string_list(strong)
        control_name = get_counter_oheng(strong_str)
        
        advice_parts.append(f"따라서 과도한 {strong_str} 기운은 상극 오행인 {control_name} 기운으로 다스리고, ");
                            
        lacking_str = _get_oheng_string_list(lacking)
        lacking_name1 = lacking[0]
        lacking_name2 = lacking[1]

        advice_parts.append(f"부족한 {lacking_name1} 기운과 {lacking_name2} 기운을 보충하여 균형을 되찾아보세요.")
        
        _update_oheng_counter(recommended_oheng_counter, [control_name])
        _update_oheng_counter(recommended_oheng_counter, [lacking_name1, lacking_name2])
        
    # 최종 추천 메시지 문자열 생성: 문장별로 띄어쓰기를 추가하여 자연스럽게 연결
    advice_message = " ".join(advice_parts)
    
    return analysis_headline, advice_message, dict(recommended_oheng_counter)