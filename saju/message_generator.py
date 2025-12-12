import random
from typing import List, Tuple, Dict
from collections import Counter

OHENG_ATTRIBUTES = {
    '목(木)': {'food': '채소류, 신맛 음식'},
    '화(火)': {'food': '매운맛, 쓴맛 음식'},
    '토(土)': {'food': '곡물류, 단맛 음식'},
    '금(金)': {'food': '육류, 바삭한 음식'},
    '수(水)': {'food': '해산물, 짠맛 음식'},
}

CLOSING_MESSAGES = [
    "마음속까지 따뜻해지는 평온한 하루를 보낼 거예요!",
    "긍정적인 에너지가 온몸에 가득 찰 거예요!",
    "오늘이야말로 행운의 주인공이 되는 날이 될 거예요!",
    "평온한 하루가 될 거예요!",
    "순조로운 하루를 보낼 거예요!",
]

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

# 오행별 음식 정보를 포맷팅하여 반환
def _get_formatted_food_string(oheng_name: str) -> str:
    food_list_str = OHENG_ATTRIBUTES.get(oheng_name, {}).get('food', '')
    
    if not food_list_str:
        return "관련 음식"
    
    foods = [f.strip() for f in food_list_str.split(',') if f.strip()]
    
    if len(foods) > 2:
        foods = foods[:2]
        
    return '·'.join(foods)

def define_oheng_messages(
    lacking: List[str], 
    strong: List[str], 
    oheng_type: str,
    final_oheng_scores: Dict[str, float]
) -> Tuple[str, str, Dict[str, int], List[str], List[str]]:
    analysis_headline = ""
    advice_parts = [] 
    recommended_oheng_counter = Counter()
    control_ohengs: List[str] = []
    
    # 제목 생성 로직
    if oheng_type == "균형형":
        analysis_headline = "" 
    else: 
        lacking_str = _get_oheng_string_list(lacking)
        strong_str = _get_oheng_string_list(strong)
        
        if lacking and strong:
            analysis_headline = f"{strong_str} 기운이 강하고, {lacking_str} 기운이 부족한 하루예요!"
        elif lacking:
            analysis_headline = f"{lacking_str} 기운이 부족한 하루예요!"
        else:
            analysis_headline = f"{strong_str} 기운이 강한 하루예요!"

    # 추천 메시지 생성
    advice_parts = [] # 문장 분리된 조언을 담을 리스트

    if oheng_type == "균형형":
        
        HENG_AVERAGE = 20.0 
        lacking_name = lacking[0] 
        strong_name = strong[0] 
        diff_lacking = abs(final_oheng_scores.get(lacking_name, 0) - HENG_AVERAGE) 
        diff_strong = abs(final_oheng_scores.get(strong_name, 0) - HENG_AVERAGE) 
        
        random_closing = random.choice(CLOSING_MESSAGES) # 랜덤 메시지 선택

        if diff_lacking >= diff_strong:
            # 부족 오행이 더 두드러진 경우 (보충 전략)
            lacking_food_str = _get_formatted_food_string(lacking_name)
            analysis_headline = f"오행이 안정된 하루, {lacking_name} 기운이 가장 약해요." 
            
            # 균형형의 보충 조언
            advice_parts.append(
                f"다만 {lacking_name} 기운은 {lacking_food_str}으로 보충해 보세요! "
            )
            advice_parts.append(random_closing)

            _update_oheng_counter(recommended_oheng_counter, [lacking_name])
            control_ohengs.append(lacking_name)
            
        else: 
            # 강한 오행이 더 두드러진 경우 (억제 전략)
            control_name = get_counter_oheng(strong_name) 
            control_food_str = _get_formatted_food_string(control_name)
            
            analysis_headline = f"오행이 안정된 하루, {strong_name} 기운이 살짝 강해요." 
            
            # 균형형의 억제 조언
            advice_parts.append(
                f"다만 {strong_name} 기운이 조금 강해, 상극인 {control_name} 기운의 색과 음식({control_food_str})으로 눌러 균형을 맞추면 "
            )
            advice_parts.append(random_closing)

            _update_oheng_counter(recommended_oheng_counter, [control_name])
            control_ohengs.append(control_name)

    # 무형/치우침형: 부족 오행 보충 + 과다 오행 상극 억제
    if oheng_type == "무형" or oheng_type == "치우침형":
        
        random_closing = random.choice(CLOSING_MESSAGES)
        
        # 1. 제어 오행 목록을 먼저 계산
        if strong:
            control_ohengs = [get_counter_oheng(o) for o in strong]
            
        # 2. 부족 오행과 제어 오행이 '단일' 오행으로 겹치는지 확인
        is_oheng_overlapped = (
            len(lacking) == 1 and 
            len(strong) == 1 and 
            lacking[0] == control_ohengs[0]
        )
            
        if is_oheng_overlapped:
            # 겹치는 경우: 한 문장으로 통합
            oheng_name = lacking[0] 
            strong_name = strong[0] 
            food_str = _get_formatted_food_string(oheng_name)

            # 통합 메시지 생성
            combined_advice = (
                f"오늘은 {food_str}을 추천해요! {food_str}으로 강한 {strong_name} 기운을 누르고 부족한 {oheng_name} 기운을 채우면 "
            )
            advice_parts.append(combined_advice + random_closing)
            
            _update_oheng_counter(recommended_oheng_counter, [oheng_name])

        else:
            # 겹치지 않는 경우
            
            lacking_advice = ""
            strong_advice = ""
            
            # a. 부족 오행 조언 생성 (첫 번째 문장)
            if lacking:
                lacking_str = _get_oheng_string_list(lacking)
                
                if len(lacking) == 1:
                    lacking_food_str = _get_formatted_food_string(lacking[0])
                    lacking_advice = f"부족한 {lacking_str} 기운은 {lacking_food_str}으로 보충하면 좋아요!"
                else:
                    lacking_advice = f"부족한 {lacking_str} 기운을 보충하면 좋아요!"
                    
                _update_oheng_counter(recommended_oheng_counter, lacking)
            
            # b. 강한 오행 조언 생성 (두 번째 문장)
            if strong:
                strong_str = _get_oheng_string_list(strong)
                control_str = _get_oheng_string_list(control_ohengs)
                
                if len(control_ohengs) == 1 and len(strong) == 1:
                    control_food_str = _get_formatted_food_string(control_ohengs[0])
                    strong_advice = f"강한 {strong_str} 기운은 상극인 {control_str} 기운을 더해주는 {control_food_str}으로 눌러 균형을 맞추면 "
                else:
                    strong_advice = f"강한 {strong_str} 기운은 상극 오행인 {control_str} 기운으로 눌러 균형을 맞추면 "
                    
                _update_oheng_counter(recommended_oheng_counter, control_ohengs)
                
                # 두 번째 문장에 랜덤 메시지를 붙여 완료
                strong_advice += random_closing

            # 조언 문장을 합침
            if lacking_advice:
                advice_parts.append(lacking_advice)
            if strong_advice:
                advice_parts.append(strong_advice)

    # 제목 생성
    lacking_str = _get_oheng_string_list(lacking)
    strong_str = _get_oheng_string_list(strong)
            
    if lacking and strong:
        analysis_headline = f"{strong_str} 기운이 강하고, {lacking_str} 기운이 부족한 하루예요!"
    elif lacking:
        analysis_headline = f"{lacking_str} 기운이 부족한 하루예요!"
    else:
        analysis_headline = f"{strong_str} 기운이 강한 하루예요!"
    
    advice_message = " ".join(advice_parts)

    return analysis_headline, advice_message, dict(recommended_oheng_counter), control_ohengs, strong