import asyncio
import json
import os
import re
from openai import AsyncOpenAI

# ==========================================
# 1. 초기화 및 환경 설정
# ==========================================
# OpenAI 비동기 클라이언트 설정 (API 키는 환경 변수에서 참조)
openai_client = AsyncOpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

# 회차 내 중복 호출 방지를 위한 실시간 런타임 메모리 캐시 딕셔너리
# 🌟 [교정] 이제 pure_title이 아닌 고유 product_id를 Key로 사용하여 획일화를 방지합니다.
runtime_titles_dict = {}

# (가정) 기존 구글 시트에 이미 적재된 상품들의 캐시 딕셔너리 (필요시 호출부에서 채워짐)
existing_titles_dict = {}


# ==========================================
# 2. LLM 타이틀 생성 함수 (프롬프트/옵션 최적화)
# ==========================================
async def generate_naver_titles_llm(data):
    """
    GPT-4o-mini를 활용하여 4가지 콘셉트별로 3개씩, 총 12개의 마케팅 최적화 상품명을 생성합니다.
    """
    # 출발공항 유무에 따른 동적 프롬프트 콘텍스트 구성
    if data.get('departure_airport') and data['departure_airport'] != "없음":
        departure_context = f"- 지정 출발공항: {data['departure_airport']} (반드시 상품명 맨 앞에 '{data['departure_airport']}' 형식으로 고정 배치할 것)"
    else:
        departure_context = "- 지정 출발공항: 없음 (★주의: 상품명 맨 앞에 '[기본출발]', '[기본출발지]', '[출발지없음]' 등 어떠한 출발 관련 문구도 절대 넣지 말고, 곧바로 '지역명'부터 시작할 것)"

    prompt = f"""
당신은 네이버 쇼핑 검색 최적화(SEO) 및 소비자 심리를 꿰뚫는 초일류 퍼포먼스 마케팅 카피라이팅 전문가입니다.
제공된 여행 상품 데이터를 바탕으로, 가이드라인을 완벽히 준수하는 4가지 서로 다른 마케팅 콘셉트의 상품명을 각각 3개씩(총 12개) 생성하세요.

[입력 데이터]
- 원본 상품명: {data['full_title']}
- 기준 상품명: {data['pure_title']}
- 여행 지역: {data['region']}
- 기간: {data['duration']}
{departure_context}
- 핵심 설명: {data['description']}
- 추출 키워드: {data['hashtags']}

[❌ 전 콘셉트 공통 절대 금지 가이드라인]
1. 글자 수: 모든 상품명은 공백 포함 최소 30자 ~ 최대 45자 사이로 구성한다. (50자 절대 초과 금지)  # 🌟 병목 유발하던 공간 압박 해결
2. 중복 제거: 단일 상품명 내부에서 동일한 단어(ex: 방콕, 여행, 패키지 등)가 2회 이상 중복 나열되는 것을 절대 금지한다.
3. 정제성: '신상품', '세이브', '특가', '대박', '★' 같은 홍보성 문구나 특수문자는 절대 포함하지 않는다.
4. 출발지 조건 규칙: [지정 출발공항]이 '없음'일 경우 '기본출발' 등을 임의로 조작하지 말고 무조건 곧바로 지역명/브랜드명으로 시작한다.

[🎯 콘셉트별 상세 생성 규칙]
■ 콘셉트 A (정석 SEO형 - 3개): 감성적 수식어를 배제하고, 검색량이 높은 실용적 핵심 키워드(지역명+타겟+핵심조건) 위주의 명사 나열 조합.
■ 콘셉트 B (타겟/상황형 - 3개): 소비자가 떠나는 이유와 타겟을 전면 강조. (ex: 부모님 효도, 아이동반, 여름휴가 등 타겟 키워드 1개 이상 융합)
■ 콘셉트 C (혜택/USP형 - 3개): 소비자가 직관적으로 이득을 느끼는 프리미엄 혜택 명사화 강조. (ex: 5성호텔, 자유시간, 전일정식사 등 융합)
■ 콘셉트 D (감성/트렌디형 - 3개): 인스타/릴스 감성의 카피라이팅 가미. (ex: 요즘뜨는, 인생샷, 감성숙소 등 트렌디 단어 자연스럽게 융합)

⚠️ [철저한 차별화 보장 규칙]
제공된 세부 특성(#2030전용, #우리끼리여행, #소도시여행, #슬리핑버스 등)과 원본 상품명에 포함된 마케팅 태그를 카피라이팅에 적극 반영하세요. 
모든 상품마다 완전히 다른 마케팅 카피가 창조되어야 하며, 이전 상품과 똑같은 단어 조합을 무지성으로 반복 출력하는 것을 절대 금지합니다.
"""
    
    # 구조화된 출력을 위한 JSON 스키마 정의
    json_schema_format = {
        "type": "json_schema",
        "json_schema": {
            "name": "naver_twelve_titles_schema",
            "strict": True,
            "schema": {
                "type": "object",
                "properties": {
                    "A_1": {"type": "string"}, "A_2": {"type": "string"}, "A_3": {"type": "string"},
                    "B_1": {"type": "string"}, "B_2": {"type": "string"}, "B_3": {"type": "string"},
                    "C_1": {"type": "string"}, "C_2": {"type": "string"}, "C_3": {"type": "string"},
                    "D_1": {"type": "string"}, "D_2": {"type": "string"}, "D_3": {"type": "string"}
                },
                "required": [
                    "A_1", "A_2", "A_3", "B_1", "B_2", "B_3", 
                    "C_1", "C_2", "C_3", "D_1", "D_2", "D_3"
                ],
                "additionalProperties": False
            }
        }
    }

    try:
        response = await openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a helpful assistant that outputs compliant JSON based on the provided schema."},
                {"role": "user", "content": prompt}
            ],
            response_format=json_schema_format,
            temperature=0.4,  # 🌟 획일화된 응답을 깨부수고 미세한 원본 차이를 반영하기 위해 0.4로 조절
            seed=42
        )
        
        res_json = json.loads(response.choices[0].message.content)
        return (
            res_json.get("A_1", "").strip(), res_json.get("A_2", "").strip(), res_json.get("A_3", "").strip(),
            res_json.get("B_1", "").strip(), res_json.get("B_2", "").strip(), res_json.get("B_3", "").strip(),
            res_json.get("C_1", "").strip(), res_json.get("C_2", "").strip(), res_json.get("C_3", "").strip(),
            res_json.get("D_1", "").strip(), res_json.get("D_2", "").strip(), res_json.get("D_3", "").strip()
        )
    except Exception as e:
        print(f"❌ LLM 12개 상품명 생성 중 에러 발생: {e}")
        err_t = f"[Error] {data.get('pure_title', 'Unknown')}"
        return tuple([err_t] * 12)


# ==========================================
# 3. 개별 상품 파이프라인 처리 함수
# ==========================================
async def process_single_product(raw_product_data):
    """
    단일 상품 데이터를 받아 정제, 고유 ID 식별, 캐시 검사 후 필요 시 LLM을 호출하여 최종 적재 데이터를 반환합니다.
    """
    # 1) 기초 데이터 바인딩
    product_id = raw_product_data.get("product_id")    # 예: 고유 해시값
    full_title = raw_product_data.get("full_title")    # 예: [한정특가][2030전용] 하노이/사파 5일 #또래여행...
    pure_title = raw_product_data.get("pure_title")    # 예: 하노이/사파 5일
    target_region = raw_product_data.get("region", "사파")
    target_airport = raw_product_data.get("departure_airport", "부산")
    duration = raw_product_data.get("duration", "5일")
    product_desc = raw_product_data.get("description", "하노이 사파 패키지 여행")
    all_hashtags = raw_product_data.get("hashtags", [])

    # 2) 🌟 [최종 해결] 중복 및 복사 버그 전면 차단 캐싱 필터 레이어
    if product_id in existing_titles_dict:
        # [1계층 캐시] 이미 예전 수집 단계에서 구글 시트에 저장된 적이 있는 ID라면 그대로 재사용
        titles = existing_titles_dict[product_id]
        print(f"📁 [시트 캐시] 기존 구글 시트에 존재하는 상품 ID 재사용: {product_id}")
        
    elif product_id in runtime_titles_dict:
        # [2계층 캐시] 이번 프로그램이 켜진 도중(실시간 런타임) 이미 한 번 연산한 고유 ID일 경우 메모리 캐시 사용
        titles = runtime_titles_dict[product_id]
        print(f"♻️ [비용 절감] 동일 회차 내 완전히 똑같은 상품 고유 ID 발견 ➡️ 캐시 재사용: {full_title}")
        
    else:
        # [3계층 신규 생성] 기존 시트에도 없고, 이번 회차에 처음 보는 고유한 원본 상품명 구조인 경우 GPT 호출!
        print(f"✨ [신규 상품 발견] LLM 12대 타이틀 통합 최초 생성: {full_title}")
        
        ai_input_data = {
            "pure_title": pure_title,
            "full_title": full_title,
            "region": target_region,          
            "departure_airport": target_airport, 
            "duration": duration,
            "description": product_desc,
            "hashtags": all_hashtags
        }
        
        # GPT 호출하여 12개 타이틀 획득
        titles = await generate_naver_titles_llm(ai_input_data)
        
        # 🌟 중요: 다음번에 정제명이 아닌 이 '고유 ID'를 만났을 때만 복사하도록 캐시 키 저장 규칙 교정
        runtime_titles_dict[product_id] = titles

    # 3) 최종 저장용 데이터 딕셔너리 빌드업 후 반환
    final_row = {
        "product_id": product_id,
        "full_title": full_title,
        "pure_title": pure_title,
        "price": raw_product_data.get("price", 0),
        "url": raw_product_data.get("url", ""),
        "img": raw_product_data.get("img", ""),
        # 생성된 12대 타이틀 언패킹 매핑
        "A_1": titles[0], "A_2": titles[1], "A_3": titles[2],
        "B_1": titles[3], "B_2": titles[4], "B_3": titles[5],
        "C_1": titles[6], "C_2": titles[7], "C_3": titles[8],
        "D_1": titles[9], "D_2": titles[10], "D_3": titles[11]
    }
    return final_row


# ==========================================
# 4. 메인 실행 및 테스트 오케스트레이션 함수
# ==========================================
async def run_crawler():
    """
    크롤러 메인 컨트롤러 시뮬레이션
    """
    print("🚀 하나투어 상품 수집 및 마케팅 LLM 타이틀 조합 자동화 엔진을 시작합니다.")
    
    # 사용자가 제시한 하노이/사파 상품 3종 실전 시뮬레이션 샘플 데이터
    sample_scraped_products = [
        {
            "product_id": "474dc84c",
            "full_title": "[한정특가][2030전용] 하노이/사파 5일 #또래여행 #슬리핑버스 #슬리핑기차1박 #판시판모험",
            "pure_title": "하노이/사파 5일",
            "price": 1369900,
            "url": "https://puzzle.hanatour.com/...",
            "img": "https://image.hanatour.com/...",
            "region": "사파",
            "departure_airport": "부산",
            "duration": "5일",
            "description": "2030 또래끼리 떠나는 판시판 모험과 슬리핑버스 트레킹 여행",
            "hashtags": ["2030전용", "또래여행", "슬리핑버스", "판시판모험"]
        },
        {
            "product_id": "b871163e",
            "full_title": "하노이/사파 5일 #우리끼리여행",
            "pure_title": "하노이/사파 5일",
            "price": 1519900,
            "url": "https://puzzle.hanatour.com/...",
            "img": "https://image.hanatour.com/...",
            "region": "사파",
            "departure_airport": "부산",
            "duration": "5일",
            "description": "우리 가족, 우리 일행끼리만 프라이빗하게 즐기는 소도시 자연 만끽 힐링 여행",
            "hashtags": ["우리끼리여행", "단독투어", "자연만끽"]
        },
        {
            "product_id": "fd97e3d3",
            "full_title": "[부산출발]하노이/사파 5일 #소도시여행 #자연만끽 #힐링여행",
            "pure_title": "하노이/사파 5일",
            "price": 659900,
            "url": "https://puzzle.hanatour.com/...",
            "img": "https://image.hanatour.com/...",
            "region": "사파",
            "departure_airport": "부산",
            "duration": "5일",
            "description": "부산에서 곧바로 출발하여 가성비 있게 즐기는 하노이 사파 힐링 패키지",
            "hashtags": ["소도시여행", "자연만끽", "힐링여행", "부산출발"]
        }
    ]

    final_results = []
    
    # 301개 대량 연산 시 비동기 루프로 순차 처리하는 흐름 구현
    for raw_data in sample_scraped_products:
        processed_row = await process_single_product(raw_data)
        final_results.append(processed_row)
        
    print("\n📊 [최종 적재 결과 미리보기]")
    print(json.dumps(final_results, indent=2, ensure_ascii=False))


# 🌟 파이썬 파일의 문법적 무결성을 보장하는 마지막 실행 트리거 진입점
if __name__ == "__main__":
    asyncio.run(run_crawler())
