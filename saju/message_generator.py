from typing import List, Tuple, Dict
import re

# 오행 유형별 추천 메시지 생성 로직
def _get_simple_oheng_name(full_name: str) -> str:
    """'목(木)' -> '목' 으로 변환"""
    match = re.match(r"([가-힣]+)\(", full_name)
    return match.group(1) if match else full_name

def get_counter_oheng(oheng: str) -> str: 	
    """오행의 상극 오행을 반환 (입력: '목(木)', 출력: '금(金)')"""
    simple_name = _get_simple_oheng_name(oheng)
    
    # 상극 관계: 木극土, 火극金, 土극水, 金극木, 水극火
    # 반환 값은 다시 풀네임으로 통일하여 메시지 생성에 사용
    if simple_name == '목': return '금(金)'
    if simple_name == '화': return '수(水)'
    if simple_name == '토': return '목(木)'
    if simple_name == '금': return '화(火)'
    if simple_name == '수': return '토(土)'
    return ""

def _get_oheng_string_list(oheng_list: List[str]) -> str:
    """오행 리스트를 읽기 쉬운 문자열로 변환합니다. 예: ['목(木)', '화(火)'] -> '목(木)과 화(火)'"""
    if not oheng_list: return ""
    if len(oheng_list) == 1: return oheng_list[0]
    return f"{', '.join(oheng_list[:-1])}와 {oheng_list[-1]}"

def define_oheng_messages(lacking: List[str], strong: List[str], oheng_type: str) -> Tuple[str, str]:
    
    analysis_headline = ""
    advice_parts = [] # 조언 문장을 분리하여 저장할 리스트
    
    # --- 1. 헤드라인 생성 ---
    
    if oheng_type == "균형형":
        # 균형형은 가장 강해진 1개 오행만 strong에 포함됨
        analysis_headline = f"오행이 안정적인 균형형! 오늘은 {strong[0]} 기운 관리에 신경 쓰세요."
    elif oheng_type == "무형":
        # 무형은 2개 부족, 1개 강함으로 확정 (oheng_analyzer.py 수정 기준)
        analysis_headline = f"{_get_oheng_string_list(lacking)} 기운이 거의 없는 무형이에요!"
    else: # 치우침형
        # 부족/강함 모두 포함하여 역동적인 헤드라인 생성
        lacking_str = _get_oheng_string_list(lacking)
        strong_str = _get_oheng_string_list(strong)
        analysis_headline = f"타고난 {lacking_str} 기운이 부족하고, 오늘 {strong_str} 기운이 강하게 작용합니다."
        

    # --- 2. 상세 조언 생성 ---
    
    # A. 보충 오행 조언 (치우침형, 무형)
    if lacking:
        lacking_str = _get_oheng_string_list(lacking)
        
        # 1순위 부족 오행에 대한 조언
        lacking_name1 = lacking[0]
        advice_parts.append(
            f"현재 가장 시급한 것은 {lacking_name1} 기운 보충입니다. {lacking_name1} 기운을 채워주는 음식과 활동을 찾아 하루를 시작하세요!"
        )
        
        # 2순위 부족 오행에 대한 추가 조언
        if len(lacking) > 1:
            lacking_name2 = lacking[1]
            advice_parts.append(
                f"또한 {lacking_name2} 기운도 부족한 편입니다. {lacking_name1} 기운과 함께 {lacking_name2} 기운도 보충해주면 훨씬 안정적인 하루를 보낼 수 있어요."
            )

    # B. 제어 오행 조언 (균형형, 무형, 치우침형 - 모두 매일 변동 가능성 있음)
    if strong:
        strong_str = _get_oheng_string_list(strong)
        
        prefix = "\n 한편, " if lacking else ""
        
        # 강한 오행 제어에 대한 공통 메시지
        control_advice = f"{prefix}{strong_str} 기운이 과도한 편입니다. 이 기운이 지나치면 불필요한 마찰이나 실수를 유발할 수 있습니다."
        
        # 각 강한 오행에 대한 구체적인 제어 음식 조언
        individual_controls = []
        for oheng in strong:
            control_name = get_counter_oheng(oheng)
            if control_name:
                individual_controls.append(f"{control_name} 기운의 음식으로 {oheng} 기운을 억제해보세요.")

        if individual_controls:
            control_advice += f" 균형 유지를 위해 {', '.join(individual_controls)} "

        advice_parts.append(control_advice)
        
    # C. 균형형 특화 메시지 (보충/제어 메시지가 부족할 경우)
    if oheng_type == "균형형":
        # 균형형은 B에서 이미 제어 조언을 했으므로, 추가적인 격려 메시지
        advice_parts.append(
            f"타고난 오행의 균형이 좋으니, 오늘 일진의 영향을 가장 받은 {strong[0]} 기운만 잘 다스리면 만사 순조로운 하루가 될 것입니다."
        )
        
    # 최종 advice 문자열 생성: 문장별로 띄어쓰기를 추가하여 자연스럽게 연결
    advice_message = " ".join(advice_parts)
    
    return analysis_headline, advice_message