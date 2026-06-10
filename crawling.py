import os
import json
import asyncio
import re
import hashlib
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from playwright.async_api import async_playwright
from openai import AsyncOpenAI  # 💡 LLM 추가를 위한 클라이언트 로드

# OpenAI 및 구글 시트 기본 설정
openai_client = AsyncOpenAI(api_key=os.environ.get("OPENAI_API_KEY", "YOUR_LOCAL_API_KEY"))
SPREADSHEET_ID = "1mH51VHs4y0FgClkUBvZgw7oY3Yv7gQBA_a3um9uhX0I"


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
# [함수 2] ⚡ 최적화: 다중 상품(배치) LLM 타이틀 생성기
# ==========================================
async def generate_naver_titles_batch_llm(products_list):
    """
    5개의 상품 데이터를 한 번에 묶어서 하나의 프롬프트로 gpt-4o-mini에 던지고,
    요청한 모든 ID가 포함된 JSON 오브젝트 포맷으로 한 번에 반환받아 속도를 극대화합니다.
    """
    input_items_text = ""
    for p in products_list:
        departure = f"출발공항: {p['출발공항']}" if p['출발공항'] != "없음" else "출발공항: 없음"
        price_grade = "프리미엄 고가 라인" if p['가격'] >= 1500000 else ("세이브 가성비 라인" if p['가격'] <= 800000 else "스탠다드 표준 라인")
        
        input_items_text += f"""
        - ID: {p['ID']}
          상품명: {p['상품명']}
          지역: {p['지역']}
          {departure}
          등급: {price_grade} ({p['가격']:,}원)
        --------------------------------------"""

    prompt = f"""
당신은 네이버 쇼핑 검색 최적화(SEO) 기준에 맞춰 여행 상품명을 정제하고 재창조하는 마케팅 자동화 전문가입니다.
아래 제공된 여러 개의 여행 상품 데이터 목록을 보고, 가이드라인을 완벽히 준수하는 새로운 상품명 3개씩을 각각의 [ID]에 맞춰 생성하세요.

[입력 상품 목록]
{input_items_text}

[네이버 쇼핑 상품명 가이드라인]
1. ★ 글자 수 제약 ★: 모든 상품명은 반드시 '공백을 포함하여 최소 35자 ~ 최대 45자 사이'로 풍성하게 구성한다. (50자를 절대 초과해서는 안 됨)
2. 중복 제거: 상품명 내부에서 동일한 단어(ex: 방콕, 여행, 패키지 등)가 2회 이상 중복 나열되는 것을 절대 금지한다.
3. 정제성: '신상품', '특가', '대박', '★' 같은 홍보성 성격의 특수문자는 절대 포함하지 않는다.
4. 출발지 조건 규칙: 
   - [지정 출발공항]이 존재할 경우: 반드시 상품명 맨 앞에 대괄호 형태로 배치한다. (예: [대구출발], [부산출발])
   - [지정 출발공항]이 '없음'일 경우: 무조건 곧바로 지역명/브랜드명으로 상품명을 시작한다.
5. 포맷: 문장이 아닌 명사형 키워드의 깔끔한 띄어쓰기 조합으로 구성한다. 
   ※ 35자 이상의 길이를 안정적으로 채우기 위해 [지역 + 주요 타겟/시즌 + 일정 + 핵심 혜택/소구점 키워드]를 다양하고 풍부하게 조합하여 가득 채울 것.

⚠️ [철저한 차별화 보장 규칙]
동일한 지역의 상품이더라도 금액(등급)이나 출발공항이 다르면 세일즈 포인트가 완전히 달라야 합니다. 
기존 상품들과 똑같은 단어 조합을 무지성으로 반복 출력하는 것을 절대 금지하며, 등급 콘텍스트에 맞춰 완전히 독립적이고 독창적인 문구를 창조하세요.

반드시 요청한 모든 ID가 누락 없이 포함된 아래 JSON 포맷으로만 응답하세요. 다른 설명은 전면 금지합니다.
{{
  "상품_ID_1": {{
    "option_1": "생성 문구 1",
    "option_2": "생성 문구 2",
    "option_3": "생성 문구 3"
  }},
  "상품_ID_2": {{
    "option_1": "생성 문구 1",
    "option_2": "생성 문구 2",
    "option_3": "생성 문구 3"
  }}
}}
"""
    try:
        response = await openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a helpful assistant that outputs JSON according to the requested format."},
                {"role": "user", "content": prompt}
            ],
            response_format={"type": "json_object"},
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
    # 💡 5.5단계: [초고속 레이어] 스마트 증분 매핑 및 배치 LLM 연산
    # -------------------------------------------------------------
    target_s_id = os.environ.get("TARGET_SPREADSHEET_ID")
    worksheet_name = "github"
    
    # 신규 타이틀 기본 컬럼 생성
    df_final["네이버_상품명_1"] = ""
    df_final["네이버_상품명_2"] = ""
    df_final["네이버_상품명_3"] = ""

    # ⏳ [전략 1] 스마트 증분 업데이트: 기존 시트에 이미 연산된 내역이 있다면 LLM 생략 및 재활용
    if target_s_id:
        try:
            target_doc = gc.open_by_key(target_s_id)
            old_records = target_doc.worksheet(worksheet_name).get_all_records()
            if old_records:
                df_old = pd.DataFrame(old_records)
                if all(col in df_old.columns for col in ["ID", "네이버_상품명_1", "네이버_상품명_2", "네이버_상품명_3"]):
                    df_old_titles = df_old[["ID", "네이버_상품명_1", "네이버_상품명_2", "네이버_상품명_3"]].drop_duplicates(subset=["ID"])
                    
                    # 기존 타이틀 필드를 기존 df_final 결합용으로 맵 결합 (Left Join)
                    df_final = pd.merge(
                        df_final.drop(columns=["네이버_상품명_1", "네이버_상품명_2", "네이버_상품명_3"], errors='ignore'), 
                        df_old_titles, 
                        on="ID", 
                        how="left"
                    ).fillna("")
                    print("✅ [스마트 증분] 기존에 적재되었던 상품명 타이틀 데이터를 마스터셋에 매핑했습니다.")
        except Exception as e:
            print(f"ℹ️ 기존 적재 시트 대조 패스 (신규 적재 혹은 시트가 비어있음): {e}")

    # ⚡ [전략 2] 배치 처리: 여전히 비어 있는 진짜 "신규 상품"만 발라내서 5개씩 묶어 초고속 연산
    is_new_product = (df_final["네이버_상품명_1"] == "") | (df_final["네이버_상품명_1"].isna())
    df_need_llm = df_final[is_new_product].copy()
    
    print(f"🚀 [배치 연산] 총 {len(df_final)}개 상품 중 신규 연산 대상 상품: {len(df_need_llm)}개")

    if len(df_need_llm) > 0:
        batch_size = 5
        records_to_llm = df_need_llm.to_dict(orient="records")
        
        for i in range(0, len(records_to_llm), batch_size):
            chunk = records_to_llm[i:i+batch_size]
            print(f"   [LLM 배치 연산] {i+1}번째 ~ {i+len(chunk)}번째 신규 상품 묶음 타이틀 생성 중...")
            
            # 5개 상품 일괄 동시 요청
            batch_result = await generate_naver_titles_batch_llm(chunk)
            
            # 결과를 원본 데이터프레임(df_final)에 ID 기준으로 고속 업데이트
            for product in chunk:
                p_id = product["ID"]
                if p_id in batch_result:
                    res = batch_result[p_id]
                    idx = df_final[df_final["ID"] == p_id].index[0]
                    df_final.at[idx, "네이버_상품명_1"] = res.get("option_1", "[Error]").strip()
                    df_final.at[idx, "네이버_상품명_2"] = res.get("option_2", "[Error]").strip()
                    df_final.at[idx, "네이버_상품명_3"] = res.get("option_3", "[Error]").strip()
            
            # 분당 API 호출수(RPM) 제한 안전망 최소 마진
            await asyncio.sleep(0.1)

    # -------------------------------------------------------------
    # 6. 지정된 단일 구글 스프레드시트 적재 (Overwrite)
    # -------------------------------------------------------------
    print(f"\n💾 [6단계] 최종 데이터 적재 준비 (총 {len(df_final)}개 상품)...")
    
    column_order = ["ID", "상품명", "가격", "URL", "이미지URL", "지역", "출발공항", "네이버_상품명_1", "네이버_상품명_2", "네이버_상품명_3"]
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

    print("\n🎉 고유 ID 기반 마스터 데이터 최신화 파이프라인이 최적화 모드로 정상 종료되었습니다!")


if __name__ == "__main__":
    asyncio.run(run_pipeline())
