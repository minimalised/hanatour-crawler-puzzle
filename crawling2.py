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

# -------------------------------------------------------------
# [사후 검증] 네이버 SEO 사후 검증 함수 (글자 수 기준: 30자 ~ 45자)
# -------------------------------------------------------------
def validate_naver_title(title):
    """네이버 쇼핑 상품명 가이드라인 만족 여부 검증"""
    if not title:
        return False
    # 글자 수 검증 조건 (공백 포함 30자 이상 ~ 45자 이하)
    if not (30 <= len(title) <= 45):
        return False
    # 단어 중복 검증 (띄어쓰기 기준 동일 단어 2회 이상 등장 금지)
    words = title.split()
    if len(words) != len(set(words)):
        return False
    # 금지 키워드 및 특수문자 검증
    forbidden = ["특가", "대박", "신상품", "세이브", "★", "▼", "▲", "◆"]
    if any(f_word in title for f_word in forbidden):
        return False
    return True

# -------------------------------------------------------------
# [프롬프트] 2번 버전용 배치 프롬프트 생성기 (KeyError 완전 방어)
# -------------------------------------------------------------
def make_batch_prompt(data):
    # dict.get()을 사용하여 key가 없을 때의 크래시를 원천 차단합니다.
    airport = data.get('departure_airport', "없음")
    if airport != "없음":
        departure_context = f"- 지정 출발공항: {airport} (반드시 상품명 맨 앞에 '{airport}' 형식으로 고정 배치할 것)"
    else:
        departure_context = "- 지정 출발공항: 없음 (★주의: 상품명 맨 앞에 '[기본출발]', '[전국출발]' 등 어떠한 출발 관련 문구도 절대 넣지 말고, 곧바로 '지역명'부터 시작할 것)"

    return f"""당신은 네이버 쇼핑 검색 최적화(SEO) 기준에 맞춰 여행 상품명을 정제하고 재창조하는 마케팅 자동화 전문가입니다.
제공된 정형 데이터를 바탕으로 가이드라인을 완벽히 준수하는 서로 다른 스타일의 새로운 상품명 5개를 생성하세요.

[입력 데이터]
- 기준 상품명: {data.get('full_title', '제목없음')}
- 여행 지역: {data.get('region', '지역명 미상')}
- 기간: {data.get('duration', '기간 미상')}
{departure_context}
- 핵심 설명: {data.get('description', '')}
- 추출 키워드: {data.get('hashtags', '')}

[네이버 쇼핑 상품명 가이드라인]
1. 글자 수: 공백 포함 최소 30자 ~ 최대 45자 사이로 풍성하고 유연하게 구성한다. (30자 미만, 45자 초과 절대 금지)
2. 중복 제거: 상품명 내부에서 동일한 단어(ex: 방콕, 여행, 패키지 등)가 2회 이상 중복 나열되는 것을 절대 금지한다.
3. 정제성: '신상품', '세이브', '특가', '대박', '★' 같은 홍보성 문구나 특수문자는 절대 포함하지 않는다.
4. 출발지 조건 규칙: 
   - [지정 출발공항]이 존재할 경우: 반드시 상품명 맨 앞에 대괄호 형태로 배치한다. (예: [대구출발], [부산출발])
   - [지정 출발공항]이 '없음'일 경우: '기본출발', '전국출발' 같은 문구를 임의로 조작해서 넣지 말고 무조건 곧바로 지역명/브랜드명으로 상품명을 시작한다.
5. 포맷: 문장이 아닌 명사형 키워드의 깔끔한 띄어쓰기 조합으로 구성한다.

반드시 아래 JSON 포맷으로만 응답하세요. 다른 설명은 생략합니다.
{{
  "option_1": "상품명_1",
  "option_2": "상품명_2",
  "option_3": "상품명_3",
  "option_4": "상품명_4",
  "option_5": "상품명_5"
}}"""

# -------------------------------------------------------------
# [1단계 데이터 수집] 1번 버전의 안정적인 추출 방식을 그대로 유지
# -------------------------------------------------------------
async def process_single_product_raw(item, target_region, target_airport, current_url):
    try:
        main_info = await item.query_selector(":scope > .inr.right")
        img_check = await item.query_selector(":scope > .inr.img")
        if not main_info or not img_check: return None

        title_el = await main_info.query_selector(".item_title")
        full_title = (await title_el.inner_text()).strip() if title_el else "제목 없음"

        # 💡 [출발지 자동 보정] 하나투어의 URL과 원본 제목을 분석해 출발 공항을 강제로 맵핑합니다.
        if target_airport == "없음" or not target_airport:
            if "[청주출발]" in full_title or "depCityCd=CJJ" in current_url:
                target_airport = "[청주출발]"
            elif "[제주출발]" in full_title or "depCityCd=CJU" in current_url:
                target_airport = "[제주출발]"
            elif "[부산출발]" in full_title or "depCityCd=PUS" in current_url:
                target_airport = "[부산출발]"
            elif "[대구출발]" in full_title or "depCityCd=TAE" in current_url:
                target_airport = "[대구출발]"

        price_el = await main_info.query_selector(".price")
        price_raw = await price_el.inner_text() if price_el else "0"
        price = "".join(filter(str.isdigit, price_raw))

        unique_str = f"{full_title}_{price}"
        product_id = hashlib.md5(unique_str.encode()).hexdigest()[:8]

        if "#" in full_title:
            parts = full_title.split("#")
            title_hashtags = sorted([p.strip() for p in parts[1:] if p.strip()])
        else:
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
            data_src = await img_el.get_attribute("data-src")
            src = await img_el.get_attribute("src")
            potential_url = data_src if data_src else src
            if potential_url and "bg_alpha" not in potential_url:
                img_url = potential_url.strip()

        if img_url and img_url.startswith("//"): 
            img_url = "https:" + img_url

        # 💡 수집된 원본 데이터에 배치용 Key 이름을 완벽하게 매칭시켜 반환합니다.
        return {
            "ID": product_id,
            "원본상품명": full_title,
            "가격": int(price) if price else 0,
            "URL": current_url,
            "이미지URL": img_url,
            "지정지역": target_region,
            "출발공항": target_airport,
            
            # 아래 Key들이 make_batch_prompt로 그대로 유입되므로 이름을 철저하게 맞춰줍니다.
            "full_title": full_title,
            "region": target_region,
            "departure_airport": target_airport,
            "duration": duration,
            "description": product_desc,
            "hashtags": ", ".join(all_hashtags)
        }
    except Exception as e:
        print(f"⚠️ 개별 상품 추출 중 오류 패스: {e}")
        return None

# -------------------------------------------------------------
# 메인 실행 함수 (Batch API 아키텍처 안정화 버전)
# -------------------------------------------------------------
async def run_crawler():
    print("🌐 구글 API 인증 및 스프레드시트 연결 중...")
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    json_raw = os.environ.get("GOOGLE_JSON_RAW")
    
    try:
        if json_raw:
            creds = Credentials.from_service_account_info(json.loads(json_raw), scopes=scopes)
        else:
            creds = Credentials.from_service_account_file('secrets.json', scopes=scopes)
        gc = gspread.authorize(creds)
    except Exception as auth_error:
        print(f"❌ 구글 API 인증 실패: {auth_error}"); return

    source_spreadsheet_id = os.environ.get("SOURCE_SPREADSHEET_ID")
    if not source_spreadsheet_id:
        print("❌ 에러: 환경 변수 'SOURCE_SPREADSHEET_ID'가 설정되어 있지 않습니다.")
        return
    
    try:
        source_doc = gc.open_by_key(source_spreadsheet_id)
        source_sheet = source_doc.worksheet("상품리스트2")
    except Exception as e:
        print(f"❌ 소스 스프레드시트 로드 실패: {e}")
        return

    all_rows = source_sheet.get_all_values()
    data_rows = all_rows[1:]
    
    target_tasks = []
    for row in data_rows:
        if len(row) >= 1:
            url_clean = row[0].strip()  
            if url_clean.startswith("http"):
                target_tasks.append({
                    "url": url_clean,
                    "sheet_region": row[1].strip() if len(row) > 1 and row[1].strip() else "지역명 미상",
                    "sheet_airport": row[2].strip() if len(row) > 2 and row[2].strip() else "없음"
                })
                
    print(f"✅ 총 {len(target_tasks)}개의 유효 타겟 상품 라인을 확보했습니다.")

    # 캐싱 데이터 로드
    existing_titles_dict = {}
    try:
        github_sheet = source_doc.worksheet("github2")
        for r in github_sheet.get_all_records():
            pid = str(r.get("ID", "")).strip()
            if pid:
                t_opts = [str(r.get(f"네이버_상품명_{i}", "")).strip() for i in range(1, 6)]
                if not any(t_opts):
                    continue
                existing_titles_dict[pid] = t_opts
        print(f"✅ 기수집된 기존 상품 {len(existing_titles_dict)}개를 메모리에 캐싱했습니다. (공란 제외 완료)")
    except Exception:
        print("⚠️ 기존 github2 캐시가 없거나 비어있습니다. 전수 조사로 진행합니다.")

    # 1단계: Playwright 크롤링 시작
    raw_products = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={'width': 1280, 'height': 1024},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )
        page = await context.new_page()

        for task in target_tasks:
            current_url = task["url"]
            target_region = task["sheet_region"]
            target_airport = task["sheet_airport"]
            
            try:
                print(f"🔄 {target_region} (출발: {target_airport}) 페이지 로딩 중...")
                # 💡 [타임아웃 원인 해결] 하나투어의 무한 백그라운드 요청을 무시하기 위해 무조건 domcontentloaded로 진입합니다.
                await page.goto(current_url, wait_until="domcontentloaded", timeout=40000)
                
                try:
                    await page.wait_for_selector(".option_wrap.result .count em", timeout=12000)
                except Exception:
                    pass

                total_count = 20  
                try:
                    count_element = await page.query_selector(".option_wrap.result .count em")
                    if count_element:
                        count_text = (await count_element.inner_text()).strip()
                        if count_text.isdigit():
                            total_count = int(count_text)
                            print(f"   ↳ 🎯 총 상품 수 동기화 성공: [{total_count}개]")
                except Exception as e:
                    print(f"   ⚠️ 총 상품 수 추출 실패 (기본 20개 모드로 작동): {e}")

                needed_scrolls = (total_count - 1) // 20 if total_count > 20 else 0
                
                if needed_scrolls > 0:
                    print(f"   ↳ ⏳ 전수 노출을 위해 정확히 {needed_scrolls}번만 스마트 스크롤을 내립니다.")
                    for scroll_step in range(1, needed_scrolls + 1):
                        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                        await asyncio.sleep(2.0)
                        
                        await page.evaluate("window.scrollTo(0, document.body.scrollHeight - 300)")
                        await asyncio.sleep(0.3)
                        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                        
                        current_items = await page.query_selector_all(".prod_list_wrap ul.type > li")
                        if len(current_items) >= total_count:
                            break

                await asyncio.sleep(1.0)

                final_items = await page.query_selector_all(".prod_list_wrap ul.type > li")
                print(f"📦 [확인] 최종 수집된 타겟 엘리먼트 총 {len(final_items)}개! 조건부 병렬 처리를 시작합니다.")
                
                sc_tasks = [process_single_product_raw(item, target_region, target_airport, current_url) for item in final_items]
                batch_results = await asyncio.gather(*sc_tasks)
                raw_products.extend([res for res in batch_results if res is not None])
                
            except Exception as e:
                print(f"❌ {current_url} 크롤링 에러: {e}")
        await browser.close()

    if not raw_products:
        print("ℹ️ 수집된 상품이 없습니다."); return

    # 2단계: OpenAI Batch 요청 파일(.jsonl) 생성
    print(f"📦 총 {len(raw_products)}개 상품 중 신규 상품 LLM 배치 파일 생성 중...")
    batch_input_filename = "openai_batch_tasks.jsonl"
    
    runtime_cache_check = {}
    has_new_request = False

    with open(batch_input_filename, "w", encoding="utf-8") as f:
        for p in raw_products:
            p_id = p["ID"]
            orig_title = p["원본상품명"]
            
            if p_id in existing_titles_dict or orig_title in runtime_cache_check:
                continue
                
            runtime_cache_check[orig_title] = p_id
            has_new_request = True
            
            task_json = {
                "custom_id": f"task_{p_id}",
                "method": "POST",
                "url": "/v1/chat/completions",
                "body": {
                    "model": "gpt-4o-mini",
                    "messages": [
                        {"role": "system", "content": "You are a helpful assistant that outputs JSON."},
                        {"role": "user", "content": make_batch_prompt(p)} # p 내부에 매칭 완료!
                    ],
                    "response_format": {"type": "json_object"},
                    "temperature": 0.2
                }
            }
            f.write(json.dumps(task_json, ensure_ascii=False) + "\n")

    # 3단계: OpenAI Batch 전송 및 완료 대기
    llm_results = {}
    if has_new_request:
        print("🚀 OpenAI Batch 서버로 일괄 요청 업로드 중 (비용 50% 할인 모드)...")
        batch_file = await openai_client.files.create(file=open(batch_input_filename, "rb"), purpose="batch")
        batch_job = await openai_client.batches.create(
            input_file_id=batch_file.id,
            endpoint="/v1/chat/completions",
            completion_window="24h"
        )
        
        job_id = batch_job.id
        print(f"⏳ 배치 작업 시작됨 (ID: {job_id}). 완료 상태를 모니터링합니다...")
        
        while True:
            status_check = await openai_client.batches.retrieve(job_id)
            if status_check.status == "completed":
                print("✅ OpenAI Batch 처리 완료! 결과 다운로드 중...")
                file_response = await openai_client.files.content(status_check.output_file_id)
                response_text = file_response.text
                
                for line in response_text.strip().split("\n"):
                    if not line: continue
                    res_data = json.loads(line)
                    c_id = res_data["custom_id"].replace("task_", "")
                    
                    try:
                        content_raw = res_data["response"]["body"]["choices"][0]["message"]["content"]
                        res_json = json.loads(content_raw)
                        
                        options = [res_json.get(f"option_{i}", "").strip() for i in range(1, 6)]
                        validated_options = [opt if validate_naver_title(opt) else f"[⚠️가이드미달] {opt}" for opt in options]
                        
                        llm_results[c_id] = validated_options
                    except Exception:
                        llm_results[c_id] = ["[Error]"] * 5
                    if len(llm_results) % 10 == 0:
                         await asyncio.sleep(0.1)
                break
            elif status_check.status in ["failed", "cancelled", "expired"]:
                print(f"❌ OpenAI Batch 작업 실패 혹은 취소됨: {status_check.status}")
                break
            else:
                # 대량 처리 모니터링 대기 주기 (15초)
                await asyncio.sleep(15)
    else:
        print("♻️ 모든 상품이 이미 기수집되어 캐시를 사용합니다. LLM을 호출하지 않습니다.")

    # 4단계: 최종 데이터 조립 및 구글 시트 반영
    final_table = []
    for p in raw_products:
        p_id = p["ID"]
        orig_title = p["원본상품명"]
        
        if p_id in llm_results:
            t_list = llm_results[p_id]
        elif orig_title in runtime_cache_check and runtime_cache_check[orig_title] in llm_results:
            t_list = llm_results[runtime_cache_check[orig_title]]
        elif p_id in existing_titles_dict:
            t_list = existing_titles_dict[p_id]
            while len(t_list) < 5: t_list.append("")
        else:
            t_list = ["[미생성]"] * 5

        final_table.append({
            "ID": p_id,
            "원본상품명": orig_title,
            "가격": p["가격"],
            "URL": p["URL"],
            "이미지URL": p["이미지URL"],
            "지정지역": p["지정지역"],
            "출발공항": p["출발공항"],
            "네이버_상품명_1": t_list[0],
            "네이버_상품명_2": t_list[1],
            "네이버_상품명_3": t_list[2],
            "네이버_상품명_4": t_list[3],
            "네이버_상품명_5": t_list[4]
        })

    if final_table:
        df = pd.DataFrame(final_table)
        column_order = ["ID", "원본상품명", "가격", "URL", "이미지URL", "지정지역", "출발공항", 
                        "네이버_상품명_1", "네이버_상품명_2", "네이버_상품명_3", "네이버_상품명_4", "네이버_상품명_5"]
        df = df[column_order]
        
        target_spreadsheet_id = os.environ.get("TARGET_SPREADSHEET_ID", source_spreadsheet_id)
        try:
            doc = gc.open_by_key(target_spreadsheet_id)
            sheet = doc.worksheet("github2")
            sheet.clear()
            
            # 💡 [gspread 최신스펙] 에러가 유발되던 이전 문법을 최신 표준인 인자 2개 구조로 완벽히 리팩토링했습니다.
            sheet.update('A1', [df.columns.values.tolist()] + df.values.tolist())
            print(f"✅ 구글 시트 github2 반영 완료 (30~45자 가이드 5옵션 버전)")
        except Exception as e:
            print(f"❌ 시트 반영 실패: {e}")

if __name__ == "__main__":
    asyncio.run(run_crawler())
