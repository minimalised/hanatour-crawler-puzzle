import os
import json
import asyncio
import hashlib
import re
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from playwright.async_api import async_playwright
from openai import AsyncOpenAI

# 1. OpenAI 비동기 클라이언트 초기화
openai_client = AsyncOpenAI(api_key=os.environ.get("OPENAI_API_KEY", "YOUR_LOCAL_API_KEY"))

def clean_title(title, region):
    """
    제목 가드레일: 공백 포함 무조건 15자 이하로 제어합니다.
    """
    title = title.strip()
    title = re.sub(r'\s+', ' ', title) # 중복 공백 제거
    if len(title) > 15:
        title = title[:15].strip()
    if not title:
        title = f"{region[:5]} 추천 패키지"[:15]
    return title

def clean_description(desc, region, duration):
    """
    설명 가드레일: 공백 포함 무조건 30자 이상 ~ 40자 이하로 완벽히 제어합니다.
    글자 수가 부족할 경우 자연스러운 마케팅 꼬리표 문구를 활용해 채워넣습니다.
    """
    desc = desc.strip()
    desc = re.sub(r'\s+', ' ', desc) # 중복 공백 제거
    
    # 1. 40자 초과 시 문장 기호 기준으로 1차 축소 후 자르기
    if len(desc) > 40:
        sentences = re.split(r'[,.!?]', desc)
        temp_desc = ""
        for s in sentences:
            s_strip = s.strip()
            if not s_strip:
                continue
            if len(temp_desc) + len(s_strip) + 1 <= 40:
                temp_desc = (temp_desc + " " + s_strip).strip()
            else:
                break
        if 30 <= len(temp_desc) <= 40:
            desc = temp_desc
        else:
            desc = desc[:40].strip()

    # 2. 30자 미만 시 단계별 명품 마케팅 패딩 문구 추가
    if len(desc) < 30:
        paddings = [
            "지금 바로 상세한 여행 일정을 확인해보세요.",
            "놓치면 후회할 특별하고 알찬 혜택 제공.",
            "가족 연인과 함께 떠나는 완벽한 힐링 여행.",
            "실속 가득한 구성을 지금 확인해보세요.",
            "최저가 보장 혜택으로 지금 예약하세요."
        ]
        for pad in paddings:
            combined = f"{desc} {pad}".strip()
            if 30 <= len(combined) <= 40:
                desc = combined
                break
            elif len(combined) < 30:
                desc = combined  # 글자 수가 더 필요할 경우 계속 합산 시도
            else:
                # 40자를 넘는다면 딱 맞는 조각만 슬라이싱하여 접합
                needed_chars = 37 - len(desc) # 여유 버퍼를 두고 자름
                if needed_chars > 5:
                    desc = f"{desc} {pad[:needed_chars]}...".strip()[:40]
                break

    # 3. 최종 안전장치 검증
    if len(desc) > 40:
        desc = desc[:40].strip()
    if len(desc) < 30:
        # 최종 극단적인 대안 패딩 (공백 메우기)
        desc = desc.ljust(30, "!")
        
    return desc

async def generate_naver_powerlink_copy_llm(data):
    """
    GPT-4o-mini를 활용하여 네이버 파워링크 규격에 100% 일치하는 
    제목 15개와 설명문구 4개를 구조화된 출력(Structured Outputs)으로 생성합니다.
    """
    prompt = f"""
당신은 대한민국 최고 수준의 퍼포먼스 마케팅 에이전시 소속 검색광고(SA) 전문가입니다.
제공된 '하나투어 여행 상품 데이터'를 철저히 분석하여, 네이버 파워링크 검색광고 규격 및 아래 조건에 100% 일치하는 카피를 작성하십시오.

[입력 데이터]
- 원본 상품명: {data['full_title']}  
- 여행 지역: {data['region']}
- 기간/일정: {data['duration']}
- 핵심 설명: {data['description']}
- 추출 키워드: {data['hashtags']}

[작성 조건 - 필독 및 엄수]

1. 광고 제목 (개수: 정확히 15개)
   - 글자 수 제한: 공백 포함 무조건 '15자 이하' (절대 초과 금지)
   - 작성 스타일: 주요 지역을 중심으로 간단명료하게 작성하세요. 
     '~한 어디어디 여행', '~한 어디어디 패키지' 형태로 지역명과 핵심 혜택 속성이 한눈에 인지되도록 심플하게 뽑아야 합니다.
   - 예시 스타일: 
     '실속가득 방콕 5일 여행', '전일정5성 방콕파타야 패키지', '노쇼핑 방콕 파타야 여행', '갓성비 태국 방콕 패키지'

2. 설명 문구 (개수: 정확히 4개)
   - 글자 수 제한: 공백 포함 무조건 '30자 이상 ~ 40자 이하' (29자 이하 또는 41자 이상은 절대 반려되므로 필수 대역 엄수)
   - 필수 포함 요소: 입력 데이터를 철저히 융합하여 [지역, 핵심 명소, 여행 일정(ex: 4박5일, 5일 등), 패키지 형태(ex: 노쇼핑, 세이브, 프리미엄)]를 자연스럽고 찰진 한 줄의 문장 속에 모두 녹여내야 합니다.
   - 예시 스타일: 
     '방콕 파타야 5일 세이브 패키지! 산호섬 투어와 디너크루즈 포함.' (정확히 39자)

[출력 포맷]
반드시 지정된 JSON Schema 형식을 지킨 데이터로만 응답하세요. 다른 부연 설명은 절대 생략하십시오.
"""

    json_schema_format = {
        "type": "json_schema",
        "json_schema": {
            "name": "powerlink_copy_schema",
            "strict": True,
            "schema": {
                "type": "object",
                "properties": {
                    "titles": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Exactly 15 titles, each strictly 15 characters or fewer including spaces."
                    },
                    "descriptions": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Exactly 4 description sentences, each strictly between 30 and 40 characters including spaces."
                    }
                },
                "required": ["titles", "descriptions"],
                "additionalProperties": False
            }
        }
    }

    max_retries = 3
    current_temp = 0.5
    
    for attempt in range(1, max_retries + 1):
        try:
            response = await openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "You are a helpful assistant that outputs compliant JSON based on the provided schema."},
                    {"role": "user", "content": prompt}
                ],
                response_format=json_schema_format,
                temperature=current_temp
            )
            
            res_json = json.loads(response.choices[0].message.content)
            
            # 1차 파이썬 가드레일: 제목 15자 보정 및 패딩
            titles = [clean_title(t, data['region']) for t in res_json.get("titles", [])[:15]]
            while len(titles) < 15:
                titles.append(clean_title("", data['region']))

            # 2차 파이썬 가드레일: 설명문구 30자 이상 40자 이하 정밀 제어
            descriptions = []
            for d in res_json.get("descriptions", [])[:4]:
                descriptions.append(clean_description(d, data['region'], data['duration']))
                
            while len(descriptions) < 4:
                descriptions.append(clean_description("", data['region'], data['duration']))

            return titles, descriptions
            
        except Exception as e:
            if attempt == max_retries:
                break
            current_temp += 0.15

    # 실패 시 최후방 보루 디폴트 카피 자동 생성
    default_titles = [clean_title("", data['region'])] * 15
    default_descs = [clean_description(f"{data['region']} 추천 패키지", data['region'], data['duration'])] * 4
    return default_titles, default_descs


async def scrape_single_product_elements(item, target_region, target_airport, current_url, idx):
    """
    기존에 100% 검증되었던 단일 상품 엘리먼트 순수 크롤링 코드를 그대로 유지합니다.
    """
    try:
        main_info = await item.query_selector(":scope > .inr.right")
        img_check = await item.query_selector(":scope > .inr.img")
        
        if not main_info or not img_check:
            return None

        title_el = await main_info.query_selector(".item_title")
        full_title = (await title_el.inner_text()).strip() if title_el else "제목 없음"

        price_el = await main_info.query_selector(".price")
        price_raw = await price_el.inner_text() if price_el else "0"
        price = "".join(filter(str.isdigit, price_raw))

        # 고유 ID 생성 (제목+가격+주소+순번)
        unique_str = f"{full_title}_{price}_{current_url}_{idx}"
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

        return {
            "ID": product_id,
            "원본상품명": full_title,
            "정제상품명": pure_title,
            "가격": int(price) if price else 0,
            "URL": current_url,
            "지정지역": target_region,
            "출발공항": target_airport,
            "duration": duration,
            "description": product_desc,
            "hashtags": ", ".join(all_hashtags)
        }
    except Exception as e:
        print(f"⚠️ 개별 상품 파싱 실패 패스: {e}")
        return None


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

    # SOURCE LOAD: [상품랜딩리스트] 시트에서 정보 로딩
    source_spreadsheet_id = os.environ.get("SOURCE_SPREADSHEET_ID")
    try:
        source_doc = gc.open_by_key(source_spreadsheet_id)
        source_sheet = source_doc.worksheet("상품랜딩리스트")
        all_rows = source_sheet.get_all_values()
        target_tasks = []
        for row in all_rows[1:]:
            if len(row) >= 1 and row[0].startswith("http"):
                target_tasks.append({
                    "url": row[0].strip(),
                    "sheet_region": row[1].strip() if len(row) > 1 and row[1].strip() else "지역명 미상",
                    "sheet_airport": row[2].strip() if len(row) > 2 and row[2].strip() else "없음"
                })
        print(f"✅ 총 {len(target_tasks)}개의 타겟 URL 작업을 확보했습니다.")
    except Exception as e:
        print(f"❌ URL 리스트 가공 에러 ('상품랜딩리스트' 시트가 소스 파일에 있는지 확인하세요): {e}")
        return

    # TARGET LOAD: [제목설명문구] 시트 준비 및 캐싱
    target_spreadsheet_id = os.environ.get("TARGET_SPREADSHEET_ID")
    worksheet_name = "제목설명문구"
    existing_titles_dict = {}
    
    try:
        target_doc = gc.open_by_key(target_spreadsheet_id)
        try:
            target_sheet = target_doc.worksheet(worksheet_name)
            existing_data = target_sheet.get_all_records()
            for r in existing_data:
                if r.get("ID"):
                    # 캐시 보존: 제목 15개, 설명 4개 저장
                    existing_titles_dict[str(r["ID"])] = (
                        [r.get(f"제목_{i}", "") for i in range(1, 16)],
                        [r.get(f"설명_{i}", "") for i in range(1, 5)]
                    )
            print(f"✅ 기존 적재 캐시 데이터 {len(existing_titles_dict)}개를 로드했습니다.")
        except gspread.exceptions.WorksheetNotFound:
            print(f"[System] '{worksheet_name}' 시트가 없어 신규 생성합니다.")
            target_sheet = target_doc.add_worksheet(title=worksheet_name, rows="1000", cols="25")
    except Exception as cache_error:
        print(f"⚠️ 타겟 시트 접근 오류: {cache_error}")
        return

    # =======================================================================
    # 🌟 [1단계] 고속 웹 크롤링 스테이지 (기존 코드 완벽 복구 및 렌더링 동적 대기 보완)
    # =======================================================================
    print("\n⚡ [STAGE 1] 고속 웹 스크래핑을 시작합니다...")
    raw_scraped_list = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={'width': 1920, 'height': 1080}, # FHD 뷰포트로 데스크톱 레이아웃 강제 고정
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )
        page = await context.new_page()

        for idx, task in enumerate(target_tasks, start=1):
            current_url = task["url"]
            target_region = task["sheet_region"]
            target_airport = task["sheet_airport"]
            
            try:
                print(f"🔄 [{idx}/{len(target_tasks)}] {target_region} 기획전 스크래핑 중...")
                await page.goto(current_url, wait_until="load", timeout=30000)
                
                # [동적 대기 핵심] 우분투 환경에서 API 속도 지연 대응용 wait_for_selector 적용
                try:
                    await page.wait_for_selector(".prod_list_wrap ul.type > li", timeout=12000)
                    print("   ↳ 상품 목록 화면 렌더링 감지 성공!")
                except Exception as wait_err:
                    print(f"   ⚠️ 상품 목록 렌더링 지연 감지 (우회 스크롤 개시)")

                try:
                    await page.wait_for_selector(".option_wrap.result .count em", timeout=5000)
                except:
                    pass

                total_count = 20
                count_element = await page.query_selector(".option_wrap.result .count em")
                if count_element:
                    count_text = (await count_element.inner_text()).strip()
                    if count_text.isdigit():
                        total_count = int(count_text)

                needed_scrolls = (total_count - 1) // 20 if total_count > 20 else 0
                for _ in range(needed_scrolls):
                    await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    await asyncio.sleep(1.2)
                    await page.evaluate("window.scrollTo(0, document.body.scrollHeight - 300)")
                    await asyncio.sleep(0.2)
                    await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")

                # 검증된 순수 query_selector_all 방식으로 엘리먼트 획득
                final_items = await page.query_selector_all(".prod_list_wrap ul.type > li")
                print(f"   ↳ 실제 획득 상품 수: {len(final_items)}개")
                
                # 비동기 병렬 엘리먼트 파싱
                tasks = [
                    scrape_single_product_elements(item, target_region, target_airport, current_url, i)
                    for i, item in enumerate(final_items)
                ]
                batch_results = await asyncio.gather(*tasks)
                
                for res in batch_results:
                    if res:
                        raw_scraped_list.append(res)
                        
            except Exception as e:
                print(f"❌ URL 패스 에러: {current_url} -> {e}")
                continue
                
        await browser.close()

    print(f"📦 [STAGE 1 완료] 총 {len(raw_scraped_list)}개의 상품 데이터를 확보했습니다.")

    # =======================================================================
    # 🌟 [2단계 & 3단계] 파워링크 카피 라이팅 최적화 스테이지
    # =======================================================================
    if not raw_scraped_list:
        print("❌ 수집된 상품 데이터가 없습니다.")
        return

    print("\n🤖 [STAGE 2 & 3] 기존 시트 교차 필터링 및 파워링크용 LLM 카피 연산을 시작합니다...")
    
    final_synced_products = []
    runtime_titles_dict = {}
    
    # URL 기준 중복 처리
    df_raw = pd.DataFrame(raw_scraped_list)
    df_raw = df_raw.drop_duplicates(subset=["원본상품명", "가격"], keep="first")
    clean_scraped_list = df_raw.to_dict(orient="records")

    for current_item in clean_scraped_list:
        p_id = current_item["ID"]
        f_title = current_item["원본상품명"]
        price = current_item["가격"]

        is_cached = False
        titles, descriptions = None, None

        # 1차 구글시트 캐시 확인
        if p_id in existing_titles_dict:
            titles, descriptions = existing_titles_dict[p_id]
            if titles and descriptions and all(str(t).strip() for t in titles):
                is_cached = True

        # 2차 런타임 캐시 확인
        if not is_cached and p_id in runtime_titles_dict:
            titles, descriptions = runtime_titles_dict[p_id]
            is_cached = True

        # 신규 데이터일 때만 파워링크용 GPT 호출
        if not is_cached or titles is None:
            print(f"✨ [파워링크 카피 생성] {f_title} ({price}원)")
            ai_input_data = {
                "full_title": f_title,
                "region": current_item["지정지역"],
                "duration": current_item["duration"],
                "description": current_item["description"],
                "hashtags": current_item["hashtags"]
            }
            
            titles, descriptions = await generate_naver_powerlink_copy_llm(ai_input_data)
            runtime_titles_dict[p_id] = (titles, descriptions)
            await asyncio.sleep(0.1)

        # 결과 조립 및 딕셔너리 빌드
        row_dict = {
            "ID": p_id, "원본상품명": f_title, "정제상품명": current_item["정제상품명"],
            "가격": price, "URL": current_item["URL"],
            "지정지역": current_item["지정지역"], "출발공항": current_item["출발공항"]
        }
        for i in range(15):
            row_dict[f"제목_{i+1}"] = titles[i]
        for i in range(4):
            row_dict[f"설명_{i+1}"] = descriptions[i]
            
        final_synced_products.append(row_dict)

    # =======================================================================
    # 🌟 [4단계] 구글 마스터 시트 원샷 통적재 (할당량 제한 429 에러 100% 방지)
    # =======================================================================
    if final_synced_products:
        print("\n🚀 [STAGE 4] 구글 '제목설명문구' 시트 원샷 동기화 적재 시작...")
        try:
            df_final = pd.DataFrame(final_synced_products)
            
            # 컬럼 정렬 순서 정의
            column_order = ["ID", "원본상품명", "정제상품명", "가격", "URL", "지정지역", "출발공항"] + \
                           [f"제목_{i}" for i in range(1, 16)] + \
                           [f"설명_{i}" for i in range(1, 5)]
            df_final = df_final[column_order]
            
            data_to_upload = [df_final.columns.values.tolist()] + df_final.values.tolist()

            target_sheet.clear()
            target_sheet.update(values=data_to_upload, range_name='A1')
            print(f"🎯 [동기화 완료] 총 {len(df_final)}개의 상품 파워링크 데이터 적재 성공!")

        except Exception as e:
            print(f"❌ 구글 시트 마스터 적재 치명적 오류: {e}")

if __name__ == "__main__":
    async_loop = asyncio.get_event_loop()
    async_loop.run_until_complete(run_crawler())
