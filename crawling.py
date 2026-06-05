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
# [핵심 교정] 파이썬 패키지 내부 충돌을 방지하기 위해 모듈을 깨끗하게 통째로 가져옵니다.
import playwright_stealth
from openai import AsyncOpenAI

# 1. OpenAI 비동기 클라이언트 초기화
openai_client = AsyncOpenAI(api_key=os.environ.get("OPENAI_API_KEY", "YOUR_LOCAL_API_KEY"))

async def generate_naver_titles_llm(data):
    """
    GPT-4o-mini를 활용하여 네이버 쇼핑 가이드에 맞춘 고정된 상품명 3개를 생성합니다.
    """
    departure_context = f"- 지정 출발공항: {data['departure_airport']}" if data['departure_airport'] != "없음" else "- 지정 출발공항: 정보 없음 (기본 출발지 가이드 적용)"

    prompt = f"""
당신은 네이버 쇼핑 검색 최적화(SEO) 기준에 맞춰 여행 상품명을 정제하고 재창조하는 마케팅 자동화 전문가입니다.
제공된 정형 데이터를 바탕으로 가이드라인을 완벽히 준수하는 새로운 상품명 3개를 생성하세요.

[입력 데이터]
- 기준 상품명: {data['pure_title']}
- 여행 지역: {data['region']}
- 기간: {data['duration']}
{departure_context}
- 핵심 설명: {data['description']}
- 추출 키워드: {data['hashtags']}

[네이버 쇼핑 상품명 가이드라인]
1. 글자 수: 공백 포함 최소 25자 ~ 최대 35자 사이로 구성한다. (40자 절대 초과 금지)
2. 중복 제거: 상품명 내부에서 동일한 단어(ex: 방콕, 여행, 패키지 등)가 2회 이상 중복 나열되는 것을 절대 금지한다.
3. 정제성: '신상품', '세이브', '특가', '대박', '★' 같은 홍보성 문구나 특수문자는 절대 포함하지 않는다.
4. 필수 요소: [지정 출발공항]이 존재할 경우 반드시 상품명 맨 앞에 배치하고, [지역명], [여행기간], [핵심 셀링포인트 1~2개]의 단어 조합이어야 한다.
5. 포맷: 문장이 아닌 명사형 키워드의 깔끔한 띄어쓰기 조합으로 구성한다.

반드시 아래 JSON 포맷으로만 응답하세요. 다른 설명은 생략합니다.
{{
  "option_1": "[대구출발] 방콕 파타야 5일 5성호텔 패키지",
  "option_2": "방콕 파타야 여행 5일 노옵션 디너크루즈",
  "option_3": "가족휴양 추천 방콕 파타야 5일 타이마사지"
}}
"""
    try:
        response = await openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a helpful assistant that outputs JSON."},
                {"role": "user", "content": prompt}
            ],
            response_format={"type": "json_object"},
            temperature=0,
            seed=42
        )
        
        result_json = json.loads(response.choices[0].message.content)
        return (
            result_json.get("option_1", "").strip(),
            result_json.get("option_2", "").strip(),
            result_json.get("option_3", "").strip()
        )
    except Exception as e:
        print(f"❌ LLM 상품명 생성 중 에러 발생: {e}")
        return f"[Error] {data['pure_title']}", f"[Error] {data['region']}", f"[Error] {data['pure_title']}"


async def run_crawler():
    print("🌐 구글 API 인증 및 스프레드시트 연결 중...")
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    
    json_raw = os.environ.get("GOOGLE_JSON_RAW")
    
    try:
        if json_raw:
            service_account_info = json.loads(json_raw)
            creds = Credentials.from_service_account_info(service_account_info, scopes=scopes)
        else:
            creds = Credentials.from_service_account_file('secrets.json', scopes=scopes)
            
        gc = gspread.authorize(creds)
    except Exception as auth_error:
        print(f"❌ 구글 API 인증 실패: {auth_error}")
        return

    # ------------------ URL 및 메타데이터 로드부 ------------------
    print("🌐 스프레드시트에서 URL, 지역, 출발공항 리스트를 불러오는 중...")
    source_spreadsheet_id = "1mH51VHs4y0FgClkUBvZgw7oY3Yv7gQBA_a3um9uhX0I"
    try:
        source_doc = gc.open_by_key(source_spreadsheet_id)
        source_sheet = source_doc.worksheet("상품리스트")
        
        all_rows = source_sheet.get_all_values()
        header = all_rows[0]
        data_rows = all_rows[1:]
        
        target_tasks = []
        for row in data_rows:
            if len(row) >= 1 and row[0].startswith("http"):
                url = row[0].strip()
                region = row[1].strip() if len(row) > 1 and row[1].strip() else "지역명 미상"
                airport = row[2].strip() if len(row) > 2 and row[2].strip() else "없음"
                
                target_tasks.append({
                    "url": url,
                    "sheet_region": region,
                    "sheet_airport": airport
                })
                
        print(f"✅ 총 {len(target_tasks)}개의 유효 타겟 상품 라인을 확보했습니다.")
    except Exception as e:
        print(f"❌ URL 리스트를 가공하는 중 에러 발생: {e}")
        return

    # ------------------ 크롤링 및 LLM 변환 실행부 ------------------
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={'width': 1280, 'height': 1024},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )
        page = await context.new_page()
        
        # [핵심 교정] 비동기 환경 전용 봇 차단 우회 API를 절대 경로로 오차 없이 직접 지정합니다.
        await playwright_stealth.stealth_async(page)

        all_products = []

        for task in target_tasks:
            current_url = task["url"]
            target_region = task["sheet_region"]
            target_airport = task["sheet_airport"]
            
            try:
                print(f"🔄 {target_region} (출발: {target_airport}) 페이지 로딩 중...")
                await page.goto(current_url, wait_until="networkidle", timeout=60000)
                
                try:
                    await page.wait_for_selector(".prod_list_wrap", timeout=15000)
                    print("   ↳ 📦 상품 목록 레이아웃 감지 성공. 스크롤을 시작합니다.")
                except Exception as layout_error:
                    print(f"   ⚠️ 상품 목록 레이아웃을 찾지 못했습니다 (차단 혹은 비어있음): {layout_error}")
                    continue

                # ====================================================================
                # 대량 지연 로딩 상품을 위한 무한 스크롤 루프
                # ====================================================================
                print("⏳ 대량 인피니트 스크롤 동적 데이터 로딩을 시작합니다...")
                last_height = await page.evaluate("document.body.scrollHeight")
                scroll_count = 0
                max_scrolls = 40  

                while scroll_count < max_scrolls:
                    await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    await asyncio.sleep(2.5)
                    
                    new_height = await page.evaluate("document.body.scrollHeight")
                    
                    if new_height == last_height:
                        await page.evaluate("window.scrollTo(0, document.body.scrollHeight - 600)")
                        await asyncio.sleep(1.0)
                        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                        
                        if new_height == await page.evaluate("document.body.scrollHeight"):
                            print("   ↳ ✅ 해당 페이지의 모든 상품 로딩을 완료했습니다.")
                            break
                            
                    last_height = new_height
                    scroll_count += 1
                    if scroll_count % 5 == 0:
                        print(f"   .. 현재 {scroll_count}회차 스크롤 다운 수행 중 ..")
                
                # 스크롤 종료 직후 데이터 동적 배치 버퍼 여유 마진 2초 확보
                await page.wait_for_timeout(2000)
                # ====================================================================

                try:
                    final_items = await page.query_selector_all(".prod_list_wrap ul.type > li")
                    print(f"📦 최종 타겟 엘리먼트 {len(final_items)}개 감지. 데이터 전처리 및 LLM 치환 시작...")
                    
                    for item in final_items:
                        try:
                            main_info = await item.query_selector(":scope > .inr.right")
                            img_check = await item.query_selector(":scope > .inr.img")
                            
                            if not main_info or not img_check:
                                continue

                            # 1. 원본 풀 타이틀 가져오기
                            title_el = await main_info.query_selector(".item_title")
                            full_title = (await title_el.inner_text()).strip() if title_el else "제목 없음"

                            # 2. 가변형 접두어 제거 및 타이틀 해시태그 분리
                            pure_title_body = re.sub(r'\[.*?\]', '', full_title).strip()
                            
                            if "#" in pure_title_body:
                                parts = pure_title_body.split("#")
                                pure_title = parts[0].strip()
                                title_hashtags = sorted([p.strip() for p in parts[1:] if p.strip()])
                            else:
                                pure_title = pure_title_body
                                title_hashtags = []

                            # 3. 하단 UI 해시태그 그룹 추가 수집
                            hash_span_els = await main_info.query_selector_all(".hash_group span")
                            ui_hashtags = [(await h.inner_text()).replace("#", "").strip() for h in hash_span_els]
                            all_hashtags = sorted(list(set(title_hashtags + ui_hashtags)))

                            # 4. 본문 요약 설명 추출
                            desc_el = await main_info.query_selector(".item_text.stit")
                            product_desc = (await desc_el.inner_text()).strip() if desc_el else ""

                            # 5. 정확한 여행 기간 추출
                            duration_el = await main_info.query_selector("span.icn.cal")
                            duration_text = (await duration_el.inner_text()).strip() if duration_el else ""
                            duration = duration_text.replace("여행기간", "").strip()

                            # 6. 가격 및 기타 메타데이터 추출
                            price_el = await main_info.query_selector(".price")
                            price_raw = await price_el.inner_text() if price_el else "0"
                            price = "".join(filter(str.isdigit, price_raw))

                            img_el = await img_check.query_selector("img")
                            img_url = await img_el.get_attribute("src") if img_el else ""
                            if img_url and img_url.startswith("//"): 
                                img_url = "https:" + img_url

                            product_id = hashlib.md5(pure_title.encode()).hexdigest()[:8]
                            
                            ai_input_data = {
                                "pure_title": pure_title,
                                "region": target_region,          
                                "departure_airport": target_airport, 
                                "duration": duration,
                                "description": product_desc,
                                "hashtags": ", ".join(all_hashtags)
                            }
                            t1, t2, t3 = await generate_naver_titles_llm(ai_input_data)

                            all_products.append({
                                "ID": product_id,
                                "상품명": pure_title,
                                "가격": int(price) if price else 0,
                                "URL": current_url,
                                "이미지URL": img_url,
                                "지정지역": target_region,
                                "출발공항": target_airport,
                                "네이버_상품명_1": t1,
                                "네이버_상품명_2": t2,
                                "네이버_상품명_3": t3
                            })
                            
                            await asyncio.sleep(0.5)

                        except Exception as e:
                            print(f"개별 상품 파싱 에러: {e}")
                            continue
                except Exception as e:
                    print(f"파싱 리스트 획득 에러: {e}")

                print(f"✅ {target_region} (출발지: {target_airport}) 완료 ({len(all_products)}개 누적 완료)")
                await asyncio.sleep(1)

            except Exception as e:
                print(f"❌ {current_url} 접속 에러: {e}")
                continue

        # ------------------ 구글 시트 적재부 ------------------
        if all_products:
            print("\n🚀 결과 스프레드시트 업데이트 시작...")
            target_spreadsheet_ids = [
                "1mH51VHs4y0FgClkUBvZgw7oY3Yv7gQBA_a3um9uhX0I",
                "1JgWk9PYT6LG_1GnPdpVY0mZavcHXDWRSrzdE0lVmjj4",
                "1Hoq0N88mestsHXbIOjwue3OctXf7dvKkx99eieYFhAY",
                "1BK4xUHQFrLjLTn6vE0jSuwqMvSU7ZMKIV-nPvmySPx8"
            ]
            worksheet_name = "github"

            try:
                df = pd.DataFrame(all_products)
                column_order = ["ID", "상품명", "가격", "URL", "이미지URL", "지정지역", "출발공항", "네이버_상품명_1", "네이버_상품명_2", "네이버_상품명_3"]
                df = df[column_order]
                data_to_upload = [df.columns.values.tolist()] + df.values.tolist()

                for spreadsheet_id in target_spreadsheet_ids:
                    try:
                        doc = gc.open_by_key(spreadsheet_id)
                        sheet = doc.worksheet(worksheet_name)
                        sheet.clear()
                        # gspread 최신 v6 인자 순서 완벽 준수
                        sheet.update(values=data_to_upload, range_name='A1')
                        print(f"✅ 성공: [{doc.title}] 업데이트 완료")
                    except Exception as sheet_error:
                        print(f"⚠️ {spreadsheet_id} 업데이트 실패: {sheet_error}")

            except Exception as e:
                print(f"❌ 구글 시트 결과 적재 에러: {e}")
        
        await browser.close()

if __name__ == "__main__":
    asyncio.run(run_crawler())
