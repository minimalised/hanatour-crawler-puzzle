async def generate_naver_titles_llm(row_dict):
    """
    GPT-4o-mini를 활용하여 상품의 공항, 금액(등급), 세부 정보를 반영한 
    4가지 마케팅 콘셉트별 3개씩(총 12개)의 네이버 SEO 상품명을 생성합니다.
    """
    # 1) 출발공항 동적 콘텍스트 구성
    if row_dict.get('출발공항') and row_dict['출발공항'] != "없음":
        departure_context = f"- 지정 출발공항: {row_dict['출발공항']} (반드시 상품명 맨 앞에 '[{row_dict['출발공항']}출발]' 형식으로 고정 배치할 것)"
    else:
        departure_context = "- 지정 출발공항: 없음 (★주의: 상품명 맨 앞에 '[기본출발]', '[출발지없음]' 등 어떠한 출발 관련 문구도 절대 넣지 말고, 곧바로 '지역명'부터 시작할 것)"

    # 2) 마케터용 동적 프롬프트 빌드업
    prompt = f"""
당신은 네이버 쇼핑 검색 최적화(SEO) 및 소비자 심리를 꿰뚫는 초일류 퍼포먼스 마케팅 카피라이팅 전문가입니다.
제공된 여행 상품 데이터를 바탕으로, 가이드라인을 완벽히 준수하는 4가지 서로 다른 마케팅 콘셉트의 상품명을 각각 3개씩(총 12개) 생성하세요.

[💎 중요: 상품 등급별 키워드 의무 반영 규칙]
입력 데이터의 '원본 상품명'에 포함된 상품 등급별 괄호 문구를 파악하여, 생성되는 모든 상품명(A~D 전 콘셉트 공통)에 아래 키워드를 반드시 자연스럽게 녹여내세요.
1. 원본 상품명에 '[세이브]'가 포함된 경우: 
   - '세이브'라는 단어 자체는 쓰지 말고, 대신 [실속], [가성비추천], [합리적], [부담없는] 등 경제성과 실속을 전면 강조하는 명사 키워드를 조합하세요.
2. 원본 상품명에 '[스탠다드]'가 포함된 경우:
   - '스탠다드'라는 단어 대신 [핵심일정], [완벽구성], [알찬여행], [밸런스추천] 등 일정의 탄탄함과 균형 잡힌 구성을 강조하는 키워드를 조합하세요.
3. 원본 상품명에 '[프리미엄]'이 포함된 경우:
   - '프리미엄'이라는 단어 대신 [노쇼핑], [노팁], [노옵션], [자유시간포함], [전일정5성숙소] 등 소비자가 피로감을 느끼지 않고 가장 편안하고 고급스러운 혜택성 키워드를 전면에 배치하세요.

[⚠️ 데이터 특징 및 상품 간 차별화 지침]
현재 등록하려는 상품들은 지역명이 매우 유사합니다. 
위의 등급별 가이드라인과 더불어 [원본 상품명] 내부에 포함된 고유 힌트 및 [핵심 설명], [출발공항 정보]를 분석하여 해당 상품만의 고유 특징을 상품명에 녹여내어 다른 행의 상품들과 확실하게 차별화되도록 만드세요.

[입력 데이터]
- 원본 상품명: {row_dict['상품명']}  
- 여행 지역: {row_dict['지역']}
- 가격: {row_dict['가격']:,}원
{departure_context}

[❌ 전 콘셉트 공통 절대 금지 가이드라인]
1. 글자 수: 모든 상품명은 공백 포함 최소 35자 ~ 최대 45자 사이로 구성한다. (50자 절대 초과 금지)
2. 중복 제거: 단일 상품명 내부에서 동일한 단어(ex: 방콕, 여행, 패키지 등)가 2회 이상 중복 나열되는 것을 절대 금지한다.
3. 정제성: '신상품', '세이브', '특가', '대박', '★' 같은 홍보성 문구나 특수문자는 절대 포함하지 않는다.
4. 출발지 조건 규칙: [지정 출발공항]이 '없음'일 경우 '기본출발' 등을 임의로 조작하지 말고 무조건 곧바로 지역명/브랜드명으로 시작한다.
5. 결과물 간 상호 중복 엄금: 생성되는 12개의 상품명은 조사나 어순만 바꾼 수준이 아니라 완전히 다른 키워드 조합을 가져야 한다.

[🎯 콘셉트별 상세 생성 규칙]
■ 콘셉트 A (정석 SEO형 - 3개): 핵심 키워드 위주의 명사 나열 조합. (3개 간 키워드 배치 순서를 다르게 뒤섞을 것)
■ 콘셉트 B (타겟/상황형 - 3개): 타겟 키워드를 3개가 각각 다르게 선택 (부모님 효도, 아이동반, 부부여행 등)
■ 콘셉트 C (혜택/USP형 - 3개): 소비자가 직관적으로 이득을 느끼는 등급별 프리미엄/실속 혜택 명사화 강조.
■ 콘셉트 D (감성/트렌디형 - 3개): 요즘뜨는, 인생샷, 감성숙소 등 감성 단어가 겹치지 않게 분산.
"""
    
    # 3) 12개 아웃풋 규격을 강제하는 JSON 스키마 선언
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

    max_retries = 3
    current_temp = 0.5  # 💡 12개 간의 상호 중복을 확실하게 깨부수기 위해 시작 온도를 0.5로 상향 조정
    
    # 4) 중복 검증을 위한 동적 루프 실행
    for attempt in range(1, max_retries + 1):
        try:
            response = await openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "You are a helpful assistant that outputs compliant JSON based on the provided schema."},
                    {"role": "user", "content": prompt}
                ],
                response_format=json_schema_format,
                temperature=current_temp,
                seed=42 if attempt == 1 else None  # 첫 시도 실패 시 시드를 풀어 창의성 확보
            )
            
            res_json = json.loads(response.choices[0].message.content)
            
            # 스키마 순서대로 12개 추출
            titles_list = [
                res_json.get(f"{concept}_{i}", "").strip() 
                for concept in ['A', 'B', 'C', 'D'] 
                for i in [1, 2, 3]
            ]
            
            # 12개 타이틀이 내부적으로 서로 중복이 없는지 유니크 검사
            unique_titles = set(titles_list)
            if len(unique_titles) == 12:
                return tuple(titles_list)
            
            # 내부 중복 발견 시 미세하게 온도를 올려 다음 루프에서 재생성 유도
            print(f"⚠️ [재시도] 12개 중 중복 검출되어 재수행합니다. (시도 {attempt}/{max_retries})")
            current_temp += 0.15
            
        except Exception as e:
            if attempt == max_retries:
                print(f"❌ LLM 최종 실패 에러 원인: {e}")
                break

    # 5) 방어 코드 (에러 발생 시 슬라이싱 처리)
    err_t = f"[Error] {row_dict['상품명'][:15]}"
    if 'titles_list' not in locals() or len(titles_list) < 12:
        titles_list = [err_t] * 12
    return tuple(titles_list)
