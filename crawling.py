import os
import json
import asyncio
import hashlib
import datetime
import re
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from playwright.async_api import async_playwright
from openai import AsyncOpenAI

openai_client = AsyncOpenAI(api_key=os.environ.get("OPENAI_API_KEY", "YOUR_LOCAL_API_KEY"))

# [대개조] 상품 10개 묶음을 한 번에 받아내는 매시브 JSON 스키마 세팅
massive_json_schema = {
    "type": "json_schema",
    "json_schema": {
        "name": "massive_travel_titles_schema",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "results": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "ID": {"type": "string"},
                            "A_1": {"type": "string"}, "A_2": {"type": "string"}, "A_3": {"type": "string"},
                            "B_1": {"type": "string"}, "B_2": {"type": "string"}, "B_3": {"type": "string"},
                            "C_1": {"type": "string"}, "C_2": {"type": "string"}, "C_3": {"type": "string"},
                            "D_1": {"type": "string"}, "D_2": {"type": "string"}, "D_3": {"type": "string"}
                        },
                        "required": [
                            "ID", "A_1", "A_2", "A_3", "B_1", "B_2", "B_3", 
                            "C_1", "C_2", "C_3", "D_1", "D_2", "D_3"
                        ],
                        "additionalProperties": False
                    }
                }
            },
            "required": ["results"],
            "additionalProperties": False
        }
    }
}

async def generate_massive_titles_llm(products_chunk):
    """
    [완전 가속] 리스트로 들어온 복수의 상품 세트를 단 한 번의 LLM 호출로 '통연산' 융합 처리합니다.
    """
    input_data_str = ""
    for idx, p in enumerate(products_chunk, start=1):
        dep_airport = p['출발공항']
        dep_context = f"지정 출발공항: {dep_airport} (맨 앞에 '{dep_airport}' 고정)" if dep_airport != "없음" else "지정 출발공항: 없음 (★[기본출발] 등 문구 절대 금지, 곧바로 지역명 시작)"
        
        input_data_str += f"""
[상품 번호 {idx}]
- ID: {p['ID']}
- 원본 상품명: {p['원본상품명']}
- 여행 지역: {p['지정지역']}
- 기간: {p['duration']}
- {dep_context}
- 핵심 설명: {p['description']}
- 추출 키워드: {p['hashtags']}
--------------------------------------
"""

    prompt = f"""
당신은 네이버 쇼핑 검색 최적화(SEO) 및 소비자 심리를 꿰뚫는 초일류 퍼포먼스 마케팅 카피라이팅 전문가입니다.
제공된 [{len(products_chunk)}개]의 여행 상품 리스트를 분석하여, 각 상품 ID별로 가이드라인을 완벽히 준수하는 4가지 콘셉트의 상품명을 각각 3개씩(총 12개씩) 한 번에 생성하세요.

[💎 중요: 상품 등급별 고유 수식어 반영 규칙 - 전 상품 공통]
각 상품의 '원본 상품명'에 포함된 등급([세이브], [스탠다드], [프리미엄])을 파악하여 아래 수식어를 무조건 붙여 가격 차이를 명확히 하세요.
1. [세이브] 포함: 상품명 내부/맨 뒤에 실속, 알뜰, 합리적 가격 등의 경제성 수식어 필수 (ex: 가성비추천, 실속패키지)
2. [스탠다드] 포함: 상품명 내부/맨 뒤에 핵심일정, 알찬구성, 베스트셀러 등의 탄탄한 구성 수식어 필수 (ex: 알찬구성, 핵심일정포함)
3. [프리미엄] 포함: 상품명 내부/맨 뒤에 노쇼핑, 노팁, 노옵션, 5성호텔 등 프리미엄 혜택 수식어 필수 (ex: 노쇼핑노팁, 전일정오성급)

[❌ 전 콘셉트 공통 절대 금지 가이드라인]
1. 글자 수: 모든 상품명은 공백 포함 최소 30자 ~ 최대 45자 사이로 구성한다. (50자 절대 초과 금지)
2. 중복 제거: 단일 상품명 내부에서 동일한 단어(ex: 방콕, 여행, 패키지 등)가 2회 이상 중복 나열되는 것을 절대 금지한다.
3. 정제성: '신상품', '세이브', '특가' 같은 단어 자체나 특수문자는 절대 포함하지 않는다.
4. 결과물 간 상호 중복 엄금: 한 상품 ID 내에서 생성되는 12개의 결과물은 단 한 줄도 조사나 어순만 바꾼 수준으로 겹쳐서는 안 된다. 완전히 다른 조합을 가질 것.

[제공된 대량 상품 데이터 리스트]
{input_data_str}
"""

    try:
        response = await openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a helpful assistant that outputs batch compliant JSON based on the provided schema."},
                {"role": "user", "content": prompt}
            ],
            response_format=massive_json_schema,
            temperature=0.4
        )
        res_json = json.loads(response.choices[0].message.content)
        return res_json.get("results", [])
    except Exception as e:
        print(f"❌ 대량 통연산 중 에러 발생: {e}")
        return []

async def scrape_single_product_elements(item, target_region, target_airport, current_url):
    try:
        main_info = await item.query_selector(":scope > .inr.right")
        img_check = await item.query_selector(":scope > .inr.img")
        if not main_info or not img_check: return None

        title_el = await main_info.query_selector(".item_title")
        full_title = (await title_el.inner_text()).strip() if title_el else "제목 없음"

        price_el = await main_info.query_selector(".price")
        price_raw = await price_el.inner_text() if price_el else "0"
        price = "".join(filter(str.isdigit, price_raw))

        unique_str = f"{full_title}_{price}"
        product_id = hashlib.md5(unique_str.encode()).hexdigest()[:8]

        pure_title_body = re.sub(r'\[.*?\]', '', full_title).strip()
        if "#" in pure_title_body:
            parts = pure_title_body.split("#")
            pure_title = parts[0].strip()
            title_hashtags = sorted([p.strip() for p in parts[1:] if p.strip()])
        else:
            pure_title = pure_title_body
            title_hashtags = []

        hash_span_els = await main_info.query_selector_all(".hash_group span")
        ui_hashtags = [(await h.inner_text()).replace("#", "").strip() for h in hash_span_els]
        all_hashtags = sorted(list(set(title_hashtags + ui_hashtags)))

        desc_el = await main_info.query_selector(".item_text.stit")
        product_desc = (await desc_el.inner_text()).strip() if desc_el else ""

        duration_el = await main_info.query_selector("span.icn.cal")
        duration_text = (await duration_el.inner_text()).strip() if duration_el else ""
        duration = duration_text.replace("여행기간", "").strip()

        img_url = ""
        img_el = await img_check.query_selector("img")
        if img_el:
            potential_url = await img_el.get_attribute("data-src") or await img_el.get_attribute("src")
            if potential_url and "bg_alpha" not in potential_url:
                img_url = potential_url.strip()
            else:
                for im in await img_check.query_selector_all("img"):
                    target = await im.get_attribute("data-src") or await im.get_attribute("src")
                    if target and "bg_alpha" not in target:
                        img_url = target.strip()
                        break

        if img_url and img_url.startswith("//"): img_url = "https:" + img_url

        return {
            "ID": product_id, "원본상품명": full_title, "정제상품명": pure_title, "가격": int(price) if price else 0,
            "URL": current_url, "이미지URL": img_url, "지정지역": target_region, "출발공항": target_airport,
            "duration": duration, "description": product_desc, "hashtags": ", ".join(all_hashtags)
        }
    except Exception as element_error:
        print(f"⚠️ 개별 자식 엘리먼트 파싱 내부 에러: {element_error}")
        return None

async def run_crawler():
    print("🌐 구글 API 인증 및 스프레드시트 연결 중...")
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    json_raw = os.environ.get("GOOGLE_JSON_RAW")
    
    try:
        creds = Credentials.from_service_account_info(json.loads(json_raw), scopes=scopes) if json_raw else Credentials.from_service_account_file('secrets.json', scopes=scopes)
        gc = gspread.authorize(creds)
    except Exception as e:
        print(f"❌ 구글 인증 실패: {e}"); return

    # SOURCE LOAD
    source_spreadsheet_id = os.environ.get("SOURCE_SPREADSHEET_ID")
    try:
        source_sheet = gc.open_by_key(source_spreadsheet_id).worksheet("상품리스트")
        target_tasks = [{"url": r[0].strip(), "sheet_region": r[1].strip() if len(r) > 1 and r[1].strip() else "지역명 미상", "sheet_airport": r[2].strip() if len(r) > 2 and r[2].strip() else "없음"} for r in source_sheet.get_all_values()[1:] if len(r) >= 1 and r[0].startswith("http")]
        print(f"✅ 총 {len(target_tasks)}개의 타겟 URL 주소를 확보했습니다.")
    except Exception as e:
        print(f"❌ URL 리스트 가공 에러: {e}"); return

    # 마스터 캐시 LOAD
    target_spreadsheet_id = os.environ.get("TARGET_SPREADSHEET_ID")
    worksheet_name = "github"
    existing_titles_dict = {}
    try:
        github_sheet = gc.open_by_key(target_spreadsheet_id).worksheet(worksheet_name)
        for r in github_sheet.get_all_records():
            if r.get("ID"):
                # 캐시 칼럼 바인딩 구조를 A_정석_1, 2, 3 순서에 일치시킴
                existing_titles_dict[str(r["ID"])] = [
                    r.get("A_정석_1", ""), r.get("A_정석_2", ""), r.get("A_정석_3", ""),
                    r.get("B_타겟_1", ""), r.get("B_타겟_2", ""), r.get("B_타겟_3", ""),
                    r.get("C_혜택_1", ""), r.get("C_혜택_2", ""), r.get("C_혜택_3", ""),
                    r.get("D_감성_1", ""), r.get("D_감성_2", ""), r.get("D_감성_3", "")
                ]
        print(f"✅ 기수집 마스터 캐시 데이터 {len(existing_titles_dict)}개 로드 완료.")
    except:
        print("⚠️ 기존 시트 로드 패스 (시트가 비어있거나 최초 실행일 수 있음).")

    # =======================================================================
    # 🌟 [STAGE 1] 고속 웹 크롤링 스테이지 (전수조사)
    # =======================================================================
    print("\n⚡ [STAGE 1] 전체 URL 대상 고속 웹 스크래핑 개시...")
    raw_scraped_list = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={'width': 1280, 'height': 1024}, 
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )
        page = await context.new_page()

        for idx, task in enumerate(target_tasks, start=1):
            try:
                print(f"🔄 [{idx}/{len(target_tasks)}] {task['sheet_region']} 스크래핑 진행 중...")
                await page.goto(task["url"], wait_until="domcontentloaded", timeout=25000)
                
                # 🛡️ [안정성 강화] 상품 개수가 렌더링될 때까지 최대 10초 명시적 대기
                try:
                    await page.wait_for_selector(".option_wrap.result .count em", timeout=10000)
                except Exception:
                    pass

                total_count = 20
                count_element = await page.query_selector(".option_wrap.result .count em")
                if count_element and (await count_element.inner_text()).strip().isdigit():
                    total_count = int((await count_element.inner_text()).strip())
                    print(f"   ↳ 🎯 총 상품 수 동기화: [{total_count}개]")

                needed_scrolls = (total_count - 1) // 20 if total_count > 20 else 0
                if needed_scrolls > 0:
                    for _ in range(needed_scrolls):
                        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                        await asyncio.sleep(1.2)
                        # 🔄 [보완] 레이지 로드 컴포넌트 트리거를 위한 흔들기 스크롤
                        await page.evaluate("window.scrollTo(0, document.body.scrollHeight - 300)")
                        await asyncio.sleep(0.2)
                        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                
                # ⏳ 스크롤 완료 후 DOM 트리가 완전히 안착될 수 있도록 최종 대기 시간 부여
                await asyncio.sleep(1.5)

                final_items = await page.query_selector_all(".prod_list_wrap ul.type > li")
                print(f"   ↳ 📦 타겟 엘리먼트 {len(final_items)}개 파싱 단계 진입.")
                
                batch_results = await asyncio.gather(*[
                    scrape_single_product_elements(item, task["sheet_region"], task["sheet_airport"], task["url"]) 
                    for item in final_items
                ])
                
                raw_scraped_list.extend([res for res in batch_results if res])
            except Exception as e:
                print(f"❌ [{task['sheet_region']}] 스크래핑 도중 에러 패스: {e}")
        await browser.close()

    # =======================================================================
    # 🌟 [STAGE 2] 진짜 상품 내용 단위 중복 필터링 (순수 ID 기준)
    # =======================================================================
    print("\n🧹 [STAGE 2] 상품 고유 내용물(ID) 기준 중복 필터링 작동...")
    df_raw = pd.DataFrame(raw_scraped_list)
    if df_raw.empty:
        print("❌ [치명적] 웹에서 수집된 데이터 행이 0개입니다. 크롤링 선택자나 페이지 로딩 상태를 점검해야 합니다.")
        return
        
    df_raw = df_raw.drop_duplicates(subset=["ID"], keep="first")
    clean_scraped_list = df_raw.to_dict(orient="records")
    print(f"🧹 중복 제거 완료 ➡️ 최종 [{len(clean_scraped_list)}개] 고유 상품 확정.")

    # =======================================================================
    # 🌟 [STAGE 3] 대량 상품 '10개씩 통연산' 병렬 레이어 구역
    # =======================================================================
    print("\n🤖 [STAGE 3] 신규/누락 상품 대상 10개 세트 통연산 LLM을 가동합니다...")
    
    needed_llm_products = []
    final_synced_products_dict = {}

    for item in clean_scraped_list:
        p_id = item["ID"]
        if p_id in existing_titles_dict and all(str(t).strip() for t in existing_titles_dict[p_id]):
            t = existing_titles_dict[p_id]
            # 정확한 시트 컬럼 맵으로 복구하여 언팩 연산 최적화
            final_synced_products_dict[p_id] = {
                **item,
                "A_정석_1": t[0], "A_정석_2": t[1], "A_정석_3": t[2],
                "B_타겟_1": t[3], "B_타겟_2": t[4], "B_타겟_3": t[5],
                "C_혜택_1": t[6], "C_혜택_2": t[7], "C_혜택_3": t[8],
                "D_감성_1": t[9], "D_감성_2": t[10], "D_감성_3": t[11]
            }
        else:
            needed_llm_products.append(item)

    print(f"📊 전수 [{len(clean_scraped_list)}개] 중 캐시 유지 상품: [{len(final_synced_products_dict)}개] | 실시간 GPT 통연산 필요 상품: [{len(needed_llm_products)}개]")

    chunk_size = 10
    chunks = [needed_llm_products[i:i + chunk_size] for i in range(0, len(needed_llm_products), chunk_size)]
    
    async def process_chunk(chunk):
        llm_results = await generate_massive_titles_llm(chunk)
        res_dict = {r["ID"]: r for r in llm_results if "ID" in r}
        
        local_synced = []
        for item in chunk:
            p_id = item["ID"]
            r = res_dict.get(p_id, {})
            local_synced.append({
                **item,
                "A_정석_1": r.get("A_1", f"[Err] {item['원본상품명'][:10]}"), "A_정석_2": r.get("A_2", ""), "A_정석_3": r.get("A_3", ""),
                "B_타겟_1": r.get("B_1", ""), "B_타겟_2": r.get("B_2", ""), "B_타겟_3": r.get("B_3", ""),
                "C_혜택_1": r.get("C_1", ""), "C_혜택_2": r.get("C_2", ""), "C_혜택_3": r.get("C_3", ""),
                "D_감성_1": r.get("D_1", ""), "D_감성_2": r.get("D_2", ""), "D_감성_3": r.get("D_3", "")
            })
        return local_synced

    if chunks:
        print(f"🚀 총 {len(chunks)}개의 연산 대형 청크 세트 동시 돌입.")
        llm_batch_results = await asyncio.gather(*[process_chunk(c) for c in chunks])
        for batch in llm_batch_results:
            for item in batch:
                final_synced_products_dict[item["ID"]] = item

    # =======================================================================
    # 🌟 [4단계] 구글 마스터 시트 원샷 대동기화 적재
    # =======================================================================
    if final_synced_products_dict:
        print("\n🚀 [STAGE 4] 구글 마스터 시트 동기화 업데이트 시작...")
        try:
            df_final = pd.DataFrame(list(final_synced_products_dict.values()))
            column_order = ["ID", "원본상품명", "정제상품명", "가격", "URL", "이미지URL", "지정지역", "출발공항", "A_정석_1", "A_정석_2", "A_정석_3", "B_타겟_1", "B_타겟_2", "B_타겟_3", "C_혜택_1", "C_혜택_2", "C_혜택_3", "D_감성_1", "D_감성_2", "D_감성_3"]
            df_final = df_final[column_order]
            
            data_to_upload = [df_final.columns.values.tolist()] + df_final.values.tolist()
            github_sheet.clear()
            github_sheet.update(values=data_to_upload, range_name='A1')
            print(f"🎯 [최종 대동기화 성공] 동기화 완료! (총 {len(df_final)}개 고유 라인 적재 완료)")
        except Exception as e:
            print(f"❌ 구글 시트 적재 오류: {e}")

if __name__ == "__main__":
    asyncio.run(run_crawler())
