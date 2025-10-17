from typing import List, Tuple

# 오행 유형별 추천 메시지 생성 로직
def get_counter_oheng(oheng: str) -> str:    
    # 상극 관계: 木극土, 火극金, 土극水, 金극木, 水극火
    if oheng == '목': return '금'
    if oheng == '화': return '수'
    if oheng == '토': return '목'
    if oheng == '금': return '화'
    if oheng == '수': return '토'
    return ""

def define_oheng_messages(lacking: List[str], strong: List[str], oheng_type: str) -> Tuple[str, str]:
    analysis_headline = ""
        
    if oheng_type == "균형형":
        analysis_headline = "오행이 안정적인 균형형"
    elif oheng_type == "무형":
        analysis_headline = f"{lacking[0]} 기운이 거의 없는 무형"
    else: # 치우침형
        analysis_headline = f"{lacking[0]} 기운이 부족하고 {strong[0]} 기운이 강해요!"

    advice_message = ""
    
    if oheng_type == "균형형":
        # 추후 일진 운세 추가 예정
        advice_message = "안정적인 기운을 유지하며, 오늘은 기분 전환이 될 만한 음식으로 활력을 더해보세요!"
    elif oheng_type == "무형":
        lacking_name = lacking[0]
        lacking_name2 = lacking[1]
        advice_message += f"{lacking_name} 기운이 0에 가까워요. 따라서 {lacking_name} 기운을 채우면 좋아요. {lacking_name} 기운의 음식을 찾아보세요! 그리고 {lacking_name2} 기운도 부족한 편이에요! 따라서 {lacking_name2} 기운도 보충해주면 더 좋아요!"
    else:
        # 1순위: 부족 오행 보충 조언
        lacking_name = lacking[0]
        advice_message += f"{lacking_name} 기운을 채우면 좋아요. {lacking_name} 기운의 음식을 찾아보세요!"
        
        # 2순위: 강한 오행 제어 조언
        if strong:
            strong_name = strong[0]
            control_name = get_counter_oheng(strong_name) # 상극 오행
            advice_message += f" 또한 과다한 {strong_name} 기운을 제어하면 좋아요. {control_name} 기운의 음식으로 {strong_name} 기운을 억제하여 균형을 맞춰보세요!"

    return analysis_headline, advice_message