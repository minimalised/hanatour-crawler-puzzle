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

# 총 5개 콘셉트 x 3개씩 = 총 15개 타이틀 마스터 컬럼 정의
CONCEPTS = ['A', 'B', 'C', 'D', 'E']
NUMS = [1, 2, 3]
TITLE_COLUMNS = [f"{c}_{n}" for c in CONCEPTS for n in NUMS]  # A_1 ~ E_3 총 15개


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
# [함수 2] ⚡ 최종 디테일 업그레이드: 35~45자 완전 보장 및 버그 원천 차단 생성기
# ==========================================
async def generate_naver_titles_llm(p, semaphore):
    """
    단일 상품 1개에 완벽히 몰입하여, 네이버 SEO 가이드라인에 맞춘 
    공백 포함 35자~45자 사이의 묵직한 명사구 타이틀 15개를 생성합니다.
    """
    async with semaphore:
        departure = f"[{p['출발공항']}출발]" if p['출발공항'] != "없음" else ""
        
        # 상품 등급 파악 및 마케터 관점의 동적 소구 가이드 트리거
        price_grade = "세이브" if "[세이브]" in p['상품명'] else ("스탠다드" if "[스탠다드]" in p['상품명'] else ("프리미엄" if "[프리미엄]" in p['상품명'] else "일반"))
        
        grade_rule = ""
        if price_grade == "세이브":
            grade_rule = "- 현재 상품 등급: [세이브] -> '세이브' 단어는 영문/한글 모두 사용 금지. 대신 [실속형], [가성비추천], [합리적플랜], [부담없는플랜] 중 하나를 반드시 문맥에 녹여 가성비를 극대화할 것."
        elif price_grade == "스탠다드":
            grade_rule = "- 현재 상품 등급: [스탠다드] -> '스탠다드' 단어는 영문/한글 모두 사용 금지. 대신 [핵심일정], [완벽구성], [알찬여행], [밸런스추천] 중 하나를 반드시 문맥에 녹여 알찬 스펙을 강조할 것."
        elif price_grade == "프리미엄":
            grade_rule = "- 현재 상품 등급: [프리미엄] -> '프리미엄' 단어는 영문/한글 모두 사용 금지. 대신 [노쇼핑], [노팁], [노옵션], [자유시간포함], [전일정5성숙소] 중 최소 1~2개 이상을 전면에 노출하여 프리미엄 혜택을 강조할 것."

        prompt = f"""
당신은 네이버 쇼핑 검색 최적화(SEO) 및 소비자 심리를 꿰뚫는 초일류 퍼포먼스 마케팅 카피라이팅 전문가입니다.
제공된 단 하나의 여행 상품 데이터를 바탕으로, 가이드라인을 완벽히 준수하는 5가지 서로 다른 마케팅 콘셉트의 상품명을 각각 3개씩(총 15개) 생성하세요.

[입력 상품 데이터]
- 상품 식별 ID: {p['ID']}
- 원본 상품명: {p['상품명']}
- 여행 지역: {p['지역']}
- 가격/금액: {p['가격']:,}원
- 필수 출발지 문구: {departure} (이 문구가 존재할 경우 반드시 최종 상품명 가장 맨 앞에 강제 위치해야 함)
{grade_rule}

[규정 1: 글자 수 강제 확보 가이드라인]
모든 상품명은 반드시 '공백을 포함하여 최소 35자 ~ 최대 45자 사이'의 묵직한 길이로 꽉 채워 출력하세요. (50자 절대 초과 금지)
지나치게 짧게 단어를 아끼지 말고, 아래의 5단계 구조를 결합하여 안정적인 길이를 확보하세요.
- 결합 공식: [출발지(있는 경우)] + [지역명 및 일정 정보] + [등급 치환 키워드] + [원본 상품명 속 핵심 혜택/USP 단어 2개 이상 가공 결합] + [콘셉트별 타겟 및 소구 수식어 명사 조합]
- 이상적인 예시: "[인천출발] 방콕 파타야 5일 핵심일정 산호섬투어 디너크루즈포함 부모님 효도여행 추천"

[규정 2: 전 콘셉트 공통 금지 가이드라인]
1. 하한선 규제: 공백 포함 35자 미만으로 짧게 대충 끊어 내뱉는 행위를 절대 금지한다. 무조건 35자~45자 사이의 풍성한 키워드로 가득 채울 것.
2. 시스템 접두사 출력 금지: 최종 출력물 상품명 텍스트 내부에 "주의:", "경고:", "가이드:" 등 시스템 지시어 성격의 접두사나 안내용 특수문자를 삽입하는 것을 절대 금지한다. 상품명은 오직 순수한 쇼핑 상품명으로만 시작해야 한다.
3. 유연한 중복 제약: 지역명 및 필수 결합 명사, 조사를 제외한 일반 단어의 무의미하고 연속적인 기계적 반복만 금지한다. 단어를 지나치게 검열하느라 문장 길이를 축소시키지 말 것.
4. 해시태그 날것 노출 금지: '#' 기호나 해시태그 형태를 그대로 노출하지 말고 마케팅 조사와 결합해 명사구로 가공할 것. (ex: #디너크루즈 -> 디너크루즈포함)
5. 정제성: 원본 상품명에 들어있는 '신상품', '특가', '대박', '✨', '★' 같은 홍보성 성격의 특수문자나 단어는 필터링하여 제거한다.
6. 결과물 간 상호 중복 엄금: 생성되는 15개의 상품명은 완전히 다른 키워드 조합과 배열을 가져야 한다.

[🎯 콘셉트별 상세 생성 규칙]
■ 콘셉트 A (정석 SEO형 - 3개): 핵심 조건 및 투어 코스 위주의 실용적 명사 나열 조합. (3개 간 키워드 배치 순서를 다르게 뒤섞을 것)
■ 콘셉트 B (타겟/상황형 - 3개): 타겟 키워드를 3개가 각각 다르게 선택 (부모님 효도여행추천, 아이동반 가족여행, 부부기념 소중한여행 등)
■ 콘셉트 C (혜택/USP형 - 3개): 소비자가 직관적으로 이득을 느끼는 등급별 핵심 혜택(전일정식사포함, 자유시간확보, 특식제공 등) 강조.
■ 콘셉트 D (감성/트렌디형 - 3개): 요즘뜨는핫플, 인생샷명소 탐방, 감성힐링스팟투어 등 감성 단어가 겹치지 않게 분산.
■ 콘셉트 E (기본 대안형 - 3개): 원본 상품명의 핵심 지역과 일정을 완전히 보존하되, 가이드라인 길이에 맞게 명사 배열을 깔끔하게 확장한 대안 조합.

반드시 아래 규격의 JSON 오브젝트 포맷으로만 응답하세요. 다른 설명은 전면 금지합니다.
{{
  "A_1": "...", "A_2": "...", "A_3": "...",
  "B_1": "...", "B_2": "...", "B_3": "...",
  "C_1": "...", "C_2": "...", "C_3": "...",
  "D_1": "...", "D_2": "...", "D_3": "...",
  "E_1": "...", "E_2": "...", "E_3": "..."
}}
"""
        json_schema_format = {
            "type": "json_schema",
            "json_schema": {
                "name": "naver_fifteen_titles_single_schema",
                "strict": True,
                "schema": {
                    "type": "object",
                    "properties": {col: {"type": "string"} for col in TITLE_COLUMNS},
                    "required": TITLE_COLUMNS,
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
                temperature=0.65  # 어휘적 자율성과 다양성을 위해 온도를 소폭 상향 조정
            )
            return p['ID'], json.loads(response.choices[0].message.content)
        except Exception as e:
            print(f"❌ LLM 타이틀 생성 중 에러 발생 (ID: {p['ID']}): {e}")
            return p['ID'], {}


# ==========================================
# [함수 3] 메인 크롤러 및 데이터 파이프라인 엔진
# ==========================================
async def run_pipeline():
    gc = get_gspread_client()
    doc = gc.open_by_key(SPREADSHEET_ID)
    
    # 1. 구글 스프레드시트에서 타겟 URL 리스트 가져오기
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

    # 2. URL 리스트 순회 및 전수 크롤링 (Playwright)
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

    # 3~5. 데이터 대조 연산 (중복 제거 및 최신 마스터셋 확정)
    print("\n📊 [3~5단계] 최신화 연산 진행 (중복 제거 및 마스터 정제)...")
    df_final = df_new.drop_duplicates(subset=["ID"]).copy()

    # 💡 5.5단계: [초고속 병렬 레이어] 스마트 증분 매핑 및 비동기 개별 연산
    target_s_id = os.environ.get("TARGET_SPREADSHEET_ID")
    worksheet_name = "github"
    
    for col in TITLE_COLUMNS:
        df_final[col] = ""

    # ⏳ [전략 1] 스마트 증분 업데이트: 기존 시트 재활용
    if target_s_id:
        try:
            target_doc = gc.open_by_key(target_s_id)
            old_records = target_doc.worksheet(worksheet_name).get_all_records()
            if old_records:
                df_old = pd.DataFrame(old_records)
                if all(col in df_old.columns for col in ["ID"] + TITLE_COLUMNS):
                    df_old_titles = df_old[["ID"] + TITLE_COLUMNS].drop_duplicates(subset=["ID"])
                    
                    df_final = pd.merge(
                        df_final.drop(columns=TITLE_COLUMNS, errors='ignore'), 
                        df_old_titles, 
                        on="ID", 
                        how="left"
                    ).fillna("")
                    print("✅ [스마트 증분] 기존 적재된 15대 콘셉트 타이틀 매핑 성공 및 LLM 차단 보전 완료.")
        except Exception as e:
            print(f"ℹ️ 기존 적재 시트 대조 패스: {e}")

    # ⚡ [전략 2] 1:1 개별 비동기 병렬 처리: 타이틀이 비어 있는 신규 행만 추출
    is_new_product = (df_final["A_1"] == "") | (df_final["A_1"].isna())
    df_need_llm = df_final[is_new_product].copy()
    
    print(f"🚀 [초고속 1:1 병렬 연산] 총 {len(df_final)}개 상품 중 신규 연산 대상 상품: {len(df_need_llm)}개")

    if len(df_need_llm) > 0:
        records_to_llm = df_need_llm.to_dict(orient="records")
        
        # 동시 호출 제한 세마포어 (동시 가동 한도 유지)
        sem = asyncio.Semaphore(15)
        tasks = [generate_naver_titles_llm(p, sem) for p in records_to_llm]
        
        print(f"🔗 총 {len(tasks)}개의 상품을 각각 개별 독립 프롬프트로 분할하여 OpenAI 서버로 동시 발송합니다...")
        
        llm_results = await asyncio.gather(*tasks)
        
        print("📥 모든 독립 연산 응답 수신 완료! 데이터프레임 매핑을 시작합니다.")
        
        for p_id, res in llm_results:
            if not res:
                continue
            idx = df_final[df_final["ID"] == p_id].index[0]
            for col in TITLE_COLUMNS:
                df_final.at[idx, col] = res.get(col, "[Error]").strip()

    # 6. 지정된 단일 구글 스프레드시트 적재 (Overwrite)
    print(f"\n💾 [6단계] 최종 데이터 적재 준비 (총 {len(df_final)}개 상품)...")
    
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

    print("\n🎉 고유 ID 기반 마스터 22대 컬럼 데이터 최신화 파이프라인이 정상 종료되었습니다!")


if __name__ == "__main__":
    asyncio.run(run_pipeline())
