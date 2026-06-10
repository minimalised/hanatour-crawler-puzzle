import os
import json
import asyncio
import re
import hashlib
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from playwright.async_api import async_playwright
from openai import AsyncOpenAI

# OpenAI 및 구글 시트 기본 설정
openai_client = AsyncOpenAI(api_key=os.environ.get("OPENAI_API_KEY", "YOUR_LOCAL_API_KEY"))
SPREADSHEET_ID = "1mH51VHs4y0FgClkUBvZgw7oY3Yv7gQBA_a3um9uhX0I"

# 전 영역 공통 타겟 콘셉트 리스트 구조 정의
CONCEPTS = ['A', 'B', 'C', 'D']
NUMS = [1, 2, 3]
TITLE_COLUMNS = [f"{c}_{n}" for c in CONCEPTS for n in NUMS]  # A_1, A_2 ... D_3 총 12개


# ==========================================
# [함수 1] 구글 시트 연동 인스턴스 생성
# ==========================================
def get_gspread_client():
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    json_raw = os.environ.get("GOOGLE_JSON_RAW")
    if json_raw:
        return gspread.authorize(Credentials.from_service_account_info(json.loads(json_raw), scopes=scopes))
    return gspread.authorize(Credentials.from_service_account_file('secrets.json', scopes=scopes))


# ==========================================
# [함수 2] ⚡ 완료: 4대 콘셉트 x 3개 (총 12개) 배치 LLM 타이틀 생성기
# ==========================================
async def generate_naver_titles_batch_llm(products_list):
    """
    5개의 상품 데이터를 한 번에 묶어서 하나의 프롬프트로 gpt-4o-mini에 던지고,
    각 상품마다 4가지 콘셉트별 3개씩(총 12개)의 마케팅 타이틀을 무결한 JSON 형태로 반환받습니다.
    """
    input_items_text = ""
    for p in products_list:
        departure = f"지정 출발공항: {p['출발공항']} (반드시 상품명 맨 앞에 '[{p['출발공항']}출발]' 형식으로 고정 배치할 것)" if p['출발공항'] != "없음" else "지정 출발공항: 없음 (★주의: 상품명 맨 앞에 어떠한 출발 관련 문구도 절대 넣지 말고 곧바로 지역명부터 시작할 것)"
        
        input_items_text += f"""
        - ID: {p['ID']}
          원본 상품명: {p['상품명']}
          여행 지역: {p['지역']}
          {departure}
        --------------------------------------"""

    prompt = f"""
당신은 네이버 쇼핑 검색 최적화(SEO) 및 소비자 심리를 꿰뚫는 초일류 퍼포먼스 마케팅 카피라이팅 전문가입니다.
제공된 여러 개의 여행 상품 데이터 목록을 보고, 가이드라인을 완벽히 준수하는 4가지 서로 다른 마케팅 콘셉트의 상품명을 각각 3개씩(총 12개) 생성하여 매핑하세요.

[💎 중요: 상품 등급별 키워드 의무 반영 규칙]
입력 데이터의 '원본 상품명'에 포함된 상품 등급별 괄호 문구를 파악하여, 생성되는 모든 상품명(A~D 전 콘셉트 공통)에 아래 키워드를 반드시 자연스럽게 녹여내세요.
1. 원본 상품명에 '[세이브]'가 포함된 경우: 
   - '세이브'라는 단어 자체는 쓰지 말고, 대신 [실속], [가성비추천], [합리적], [부담없는] 등 경제성과 실속을 전면 강조하는 명사 키워드를 조합하세요.
2. 원본 상품명에 '[스탠다드]'가 포함된 경우:
   - '스탠다드'라는 단어 대신 [핵심일정], [완벽구성], [알찬여행], [밸런스추천] 등 일정의 탄탄함และ 균형 잡힌 구성을 강조하는 키워드를 조합하세요.
3. 원본 상품명에 '[프리미엄]'이 포함된 경우:
   - '프리미엄'이라는 단어 대신 [노쇼핑], [노팁], [노옵션], [자유시간포함], [전일정5성숙소] 등 소비자가 피로감을 느끼지 않고 가장 편안하고 고급스러운 혜택성 키워드를 전면에 배치하세요.

[⚠️ 데이터 특징 및 상품 간 차별화 지침]
현재 등록하려는 상품들은 지역명이 매우 유사합니다. 
위의 등급별 가이드라인과 더불어 각 상품의 [원본 상품명] 내부에 포함된 고유 힌트 및 [여행 지역] 정보를 분석하여 해당 상품만의 고유 특징을 상품명에 녹여내어 다른 행의 상품들과 확실하게 차별화되도록 만드세요.

[입력 상품 목록]
{input_items_text}

[❌ 전 콘셉트 공통 절대 금지 가이드라인]
1. 글자 수: 모든 상품명은 공백 포함 최소 30자 ~ 최대 45자 사이로 구성한다. (50자 절대 초과 금지)
2. 중복 제거: 단일 상품명 내부에서 동일한 단어(ex: 방콕, 여행, 패키지 등)가 2회 이상 중복 나열되는 것을 절대 금지한다.
3. 정제성: '신상품', '세이브', '특가', '대박', '★' 같은 홍보성 문구나 특수문자는 절대 포함하지 않는다.
4. 출발지 조건 규칙: [지정 출발공항]이 '없음'일 경우 '기본출발' 등을 임의로 조작하지 말고 무조건 곧바로 지역명/브랜드명으로 시작한다.
5. 결과물 간 상호 중복 엄금: 한 상품 내에서 생성되는 12개의 상품명은 조사나 어순만 바꾼 수준이 아니라 완전히 다른 키워드 조합을 가져야 한다.

[🎯 콘셉트별 상세 생성 규칙]
■ 콘셉트 A (정석 SEO형 - 3개): 핵심 키워드 위주의 명사 나열 조합. (3개 간 키워드 배치 순서를 다르게 뒤섞을 것)
■ 콘셉트 B (타겟/상황형 - 3개): 타겟 키워드를 3개가 각각 다르게 선택 (부모님 효도, 아이동반, 부부여행 등)
■ 콘셉트 C (혜택/USP형 - 3개): 소비자가 직관적으로 이득을 느끼는 등급별 프리미엄/실속 혜택 명사화 강조.
■ 콘셉트 D (감성/트렌디형 - 3개): 요즘뜨는, 인생샷, 감성숙소 등 감성 단어가 겹치지 않게 분산.

반드시 요청한 모든 상품 ID가 완벽히 포함된 구조화된 JSON 오브젝트 포맷으로만 응답하세요.
"""
    
    # 5개 상품 세트의 동적 ID 프로퍼티 스키마 빌드업
    properties_schema = {}
    for p in products_list:
        properties_schema[p['ID']] = {
            "type": "object",
            "properties": {col: {"type": "string"} for col in TITLE_COLUMNS},
            "required": TITLE_COLUMNS,
            "additionalProperties": False
        }

    json_schema_format = {
        "type": "json_schema",
        "json_schema": {
            "name": "naver_twelve_titles_batch_schema",
            "strict": True,
            "schema": {
                "type": "object",
                "properties": properties_schema,
                "required": [p['ID'] for p in products_list],
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
            temperature=0.5
        )
        return json.loads(response.choices[0].message.content)
    except Exception as e:
        print(f"❌ LLM 배치 타이틀 생성 중 에러 발생: {e}")
        return {}


# ==========================================
# [함수 3] 메인 크롤러 및 데이터 파이프라인 엔진
# ==========================================
async def run_pipeline():
    gc = get_gspread_client()
    doc = gc.open_by_key(SPREADSHEET_ID)
    
    # -------------------------------------------------------------
    # 1. 구글 스프레드시트에서 타겟 URL 리스트 가져오기
    # -------------------------------------------------------------
    print("📥 [1단계] 타겟 상품리스트 URL 로드 중...")
    target_rows = doc.worksheet("상품리스트").get_all_values()[1:]
    target_tasks = []
    for r in target_rows:
        if r and r[0].startswith("http"):
            raw_airport = r[2].strip() if len(r) > 2 else ""
            airport_val = raw_airport if raw_airport != "" else "없음"

            target_tasks.append({
                "url": r[0].strip(), 
                "region": r[1].strip(), 
                "airport": airport_val
            })
            
    print(f"✅ 총 {len(target_tasks)}개의 크롤링 타겟 URL을 확보했습니다.")

    # -------------------------------------------------------------
    # 2. URL 리스트 순회 및 전수 크롤링 (Playwright)
    # -------------------------------------------------------------
    print("\n🕵️ [2단계] 전수 크롤링 및 실시간 스크롤 로딩 시작...")
    crawled_raw_products = []
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={'width': 1280, 'height': 1024},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )
        page = await context.new_page()

        for task in target_tasks:
            try:
                print(f"🔄 로딩 중: {task['region']} ({task['airport']})")
                await page.goto(task['url'], wait_until="domcontentloaded", timeout=30000)
                
                total_count = 20
                try:
                    await page.wait_for_selector(".option_wrap.result .count em", timeout=5000)
                    count_el = await page.query_selector(".option_wrap.result .count em")
                    if count_el:
                        total_count = int("".join(filter(str.isdigit, await count_el.inner_text())))
                except: pass

                needed_scrolls = (total_count - 1) // 20
                for _ in range(needed_scrolls):
                    await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    await asyncio.sleep(1.5)

                items = await page.query_selector_all(".prod_list_wrap ul.type > li")
                for item in items:
                    main_info = await item.query_selector(":scope > .inr.right")
                    img_check = await item.query_selector(":scope > .inr.img")
                    if not main_info: continue
                    
                    title_el = await main_info.query_selector(".item_title")
                    full_title = (await title_el.inner_text()).strip() if title_el else "제목 없음"
                    
                    price_el = await main_info.query_selector(".price")
                    price_raw = await price_el.inner_text() if price_el else "0"
                    price = int("".join(filter(str.isdigit, price_raw))) if any(c.isdigit() for c in price_raw) else 0
                    
                    img_url = ""
                    if img_check:
                        img_el = await img_check.query_selector("img")
                        if img_el:
                            data_src = await img_el.get_attribute("data-src")
                            src = await img_el.get_attribute("src")
                            potential_url = data_src if data_src else src
                            
                            if potential_url and "bg_alpha" not in potential_url:
                                img_url = potential_url.strip()
                            else:
                                all_imgs = await img_check.query_selector_all("img")
                                for im in all_imgs:
                                    i_src = await im.get_attribute("src")
                                    i_data = await im.get_attribute("data-src")
                                    target = i_data if i_data else i_src
                                    if target and "bg_alpha" not in target:
                                        img_url = target.strip()
                                        break
                    if img_url and img_url.startswith("//"): 
                        img_url = "https:" + img_url

                    # ID 생성 규칙 (상품명 + 가격 + 출발공항)
                    unique_str = f"{full_title}_{price}_{task['airport']}"
                    product_id = hashlib.md5(unique_str.encode('utf-8')).hexdigest()[:8]

                    crawled_raw_products.append({
                        "ID": product_id,
                        "상품명": full_title,
                        "가격": price,
                        "URL": task['url'],
                        "이미지URL": img_url,
                        "지역": task['region'],
                        "출발공항": task['airport']
                    })
            except Exception as e:
                print(f"⚠️ URL 패스 예외 발생 ({task['url']}): {e}")
                continue
        await browser.close()

    df_new = pd.DataFrame(crawled_raw_products)
    print(f"✅ 크롤링 전수 완료: 현재 웹상에 살아있는 상품 총 {len(df_new)}개 수집됨.")

    # -------------------------------------------------------------
    # 3~5. 데이터 대조 연산 (중복 제거 및 최신 마스터셋 확정)
    # -------------------------------------------------------------
    print("\n📊 [3~5단계] 최신화 연산 진행 (중복 제거 및 마스터 정제)...")
    df_final = df_new.drop_duplicates(subset=["ID"]).copy()

    # -------------------------------------------------------------
    # 💡 5.5단계: [초고속 레이어] 스마트 증분 매핑 및 배치 12대 타이틀 연산
    # -------------------------------------------------------------
    target_s_id = os.environ.get("TARGET_SPREADSHEET_ID")
    worksheet_name = "github"
    
    # 신규 타이틀 12개 빈 컬럼 일괄 확장 생성
    for col in TITLE_COLUMNS:
        df_final[col] = ""

    # ⏳ [전략 1] 스마트 증분 업데이트: 기존 시트에 12개 컬럼이 완벽히 연산된 데이터 재활용
    if target_s_id:
        try:
            target_doc = gc.open_by_key(target_s_id)
            old_records = target_doc.worksheet(worksheet_name).get_all_records()
            if old_records:
                df_old = pd.DataFrame(old_records)
                # 12개 마스터 컬럼이 기존 시트에 완벽히 존재하는지 체크
                if all(col in df_old.columns for col in ["ID"] + TITLE_COLUMNS):
                    df_old_titles = df_old[["ID"] + TITLE_COLUMNS].drop_duplicates(subset=["ID"])
                    
                    df_final = pd.merge(
                        df_final.drop(columns=TITLE_COLUMNS, errors='ignore'), 
                        df_old_titles, 
                        on="ID", 
                        how="left"
                    ).fillna("")
                    print("✅ [스마트 증분] 기존 적재된 12대 콘셉트 타이틀 매핑 성공 및 LLM 차단 보전 완료.")
        except Exception as e:
            print(f"ℹ️ 기존 적재 시트 대조 패스 (신규 적재 혹은 시트 데이터 양식 상이): {e}")

    # ⚡ [전략 2] 배치 처리: 12개 타이틀 중 첫 컬럼(A_1)이 비어 있는 신규 행만 추출하여 5개씩 바인딩 연산
    is_new_product = (df_final["A_1"] == "") | (df_final["A_1"].isna())
    df_need_llm = df_final[is_new_product].copy()
    
    print(f"🚀 [배치 연산] 총 {len(df_final)}개 상품 중 12대 타이틀 신규 생성 상품: {len(df_need_llm)}개")

    if len(df_need_llm) > 0:
        batch_size = 5
        records_to_llm = df_need_llm.to_dict(orient="records")
        
        for i in range(0, len(records_to_llm), batch_size):
            chunk = records_to_llm[i:i+batch_size]
            print(f"   [LLM 12대 대량 연산] {i+1}번째 ~ {i+len(chunk)}번째 상품 묶음 컨셉 타이틀 자동 생성 중...")
            
            # 5개 상품 일괄 동시 요청 (A_1~D_3 총 12개 리턴)
            batch_result = await generate_naver_titles_batch_llm(chunk)
            
            # 받아온 묶음 JSON 데이터를 데이터프레임 매핑 로직에 할당
            for product in chunk:
                p_id = product["ID"]
                if p_id in batch_result:
                    res = batch_result[p_id]
                    idx = df_final[df_final["ID"] == p_id].index[0]
                    # 12개 컬럼 루프 매핑
                    for col in TITLE_COLUMNS:
                        df_final.at[idx, col] = res.get(col, "[Error]").strip()
            
            await asyncio.sleep(0.1)

    # -------------------------------------------------------------
    # 6. 지정된 단일 구글 스프레드시트 적재 (Overwrite)
    # -------------------------------------------------------------
    print(f"\n💾 [6단계] 최종 데이터 적재 준비 (총 {len(df_final)}개 상품)...")
    
    # 12개 전체 컬럼 배치 순서 설정
    column_order = ["ID", "상품명", "가격", "URL", "이미지URL", "지역", "출발공항"] + TITLE_COLUMNS
    df_final = df_final[column_order].fillna("")

    data_to_upload = [df_final.columns.values.tolist()] + df_final.values.tolist()

    if target_s_id:
        try:
            target_doc = gc.open_by_key(target_s_id)
            sheet = target_doc.worksheet(worksheet_name)
            sheet.clear()  
            sheet.update(values=data_to_upload, range_name='A1')
            print(f"🚀 [적재 완료] Secrets 타겟 시트 [{target_doc.title}] 동기화 성공!")
        except Exception as e:
            print(f"❌ 시트 적재 실패 (ID: {target_s_id}): {e}")
    else:
        print("⚠️ [경고] TARGET_SPREADSHEET_ID 환경 변수가 설정되지 않아 구글 시트에 적재하지 못했습니다.")

    print("\n🎉 고유 ID 기반 마스터 19대 컬럼 데이터 최신화 파이프라인이 정상 종료되었습니다!")


if __name__ == "__main__":
    asyncio.run(run_pipeline())
