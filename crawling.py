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
# [함수 2] 💡 신규 추가: 단일 상품 LLM 타이틀 생성기
# ==========================================
async def generate_naver_titles_llm(row_dict):
    """
    GPT-4o-mini를 활용하여 상품의 공항, 금액(등급)을 반영한 독창적인 네이버 SEO 상품명 3개를 생성합니다.
    """
    # 출발공항 동적 콘텍스트
    departure_context = f"- 지정 출발공항: {row_dict['출발공항']}" if row_dict['출발공항'] != "없음" else "- 지정 출발공항: 없음"
    
    # 금액대별 등급 콘텍스트 자동 분기 (획일화 방지 핵심 로직)
    price_val = row_dict.get('가격', 0)
    if price_val >= 1500000:
        grade_context = f"- 상품 등급: 프리미엄 고가 라인 ({price_val:,}원) -> '품격', '노팁/노옵션', '5성급 호텔' 등 고급화 전략 소구 필수"
    elif price_val <= 800000:
        grade_context = f"- 상품 등급: 세이브/실속 가성비 라인 ({price_val:,}원) -> '가성비', '실속', '합리적' 등 금액적 메리트 소구 필수"
    else:
        grade_context = f"- 상품 등급: 스탠다드 표준 라인 ({price_val:,}원) -> 균형 잡힌 실용적 혜택 소구"

    prompt = f"""
당신은 네이버 쇼핑 검색 최적화(SEO) 기준에 맞춰 여행 상품명을 정제하고 재창조하는 마케팅 자동화 전문가입니다.
제공된 정형 데이터를 바탕으로 가이드라인을 완벽히 준수하는 새로운 상품명 3개를 생성하세요.

[입력 데이터]
- 원본 상품명: {row_dict['상품명']}
- 여행 지역: {row_dict['지역']}
{departure_context}
{grade_context}

[네이버 쇼핑 상품명 가이드라인]
1. 글자 수: 공백 포함 최소 35자 ~ 최대 45자 사이로 구성한다. (50자 절대 초과 금지)
2. 중복 제거: 상품명 내부에서 동일한 단어(ex: 방콕, 여행, 패키지 등)가 2회 이상 중복 나열되는 것을 절대 금지한다.
3. 정제성: '신상품', '특가', '대박', '★' 같은 홍보성 성격의 특수문자는 절대 포함하지 않는다.
4. 출발지 조건 규칙: 
   - [지정 출발공항]이 존재할 경우: 반드시 상품명 맨 앞에 대괄호 형태로 배치한다. (예: [대구출발], [부산출발])
   - [지정 출발공항]이 '없음'일 경우: 무조건 곧바로 지역명/브랜드명으로 상품명을 시작한다.
5. 포맷: 문장이 아닌 명사형 키워드의 깔끔한 띄어쓰기 조합으로 구성한다.

⚠️ [철저한 차별화 보장 규칙]
동일한 지역의 상품이더라도 금액(등급)이나 출발공항이 다르면 세일즈 포인트가 완전히 달라야 합니다. 
기존 상품들과 똑같은 단어 조합을 무지성으로 반복 출력하는 것을 절대 금지하며, 등급 콘텍스트에 맞춰 완전히 독립적이고 독창적인 문구를 창조하세요.

반드시 아래 JSON 포맷으로만 응답하세요. 다른 설명은 생략합니다.
{{
  "option_1": "생성 문구 1",
  "option_2": "생성 문구 2",
  "option_3": "생성 문구 3"
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
            temperature=0.5  # 💡 중복 생성을 깨부수기 위해 다양성 옵션 상향 조정
        )
        result_json = json.loads(response.choices[0].message.content)
        return (
            result_json.get("option_1", "").strip(),
            result_json.get("option_2", "").strip(),
            result_json.get("option_3", "").strip()
        )
    except Exception as e:
        print(f"❌ LLM 상품명 생성 중 에러 발생: {e}")
        return "[Error]", "[Error]", "[Error]"


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
    # 💡 5.5단계: 신규 추가된 LLM 타이틀 조합 연산 레이어
    # -------------------------------------------------------------
    print(f"\n🚀 [추가 단계] 고유 상품 {len(df_final)}개 대상 LLM 마케팅 타이틀 조합 시작...")
    
    # 신규 타이틀을 적재할 빈 컬럼 생성
    df_final["네이버_상품명_1"] = ""
    df_final["네이버_상품명_2"] = ""
    df_final["네이버_상품명_3"] = ""

    # 전수 데이터를 안전하게 순회하며 LLM 타이틀 장착
    for idx, row in df_final.iterrows():
        row_dict = row.to_dict()
        print(f"   [LLM 연산] {row_dict['상품명']} ({row_dict['출발공항']}출발 / {row_dict['가격']:,}원) 제목 조합 중...")
        
        t1, t2, t3 = await generate_naver_titles_llm(row_dict)
        
        df_final.at[idx, "네이버_상품명_1"] = t1
        df_final.at[idx, "네이버_상품명_2"] = t2
        df_final.at[idx, "네이버_상품명_3"] = t3
        
        # API 부하 분산 및 분당 제한(RPM) 방지 안전망
        await asyncio.sleep(0.1)

    # -------------------------------------------------------------
    # 6. 지정된 단일 구글 스프레드시트 적재 (Overwrite)
    # -------------------------------------------------------------
    print(f"\n💾 [6단계] 최종 데이터 적재 준비 (총 {len(df_final)}개 상품)...")
    
    # 💡 컬럼 순서에 LLM 생성 제목 추가 반영
    column_order = ["ID", "상품명", "가격", "URL", "이미지URL", "지역", "출발공항", "네이버_상품명_1", "네이버_상품명_2", "네이버_상품명_3"]
    df_final = df_final[column_order].fillna("")

    data_to_upload = [df_final.columns.values.tolist()] + df_final.values.tolist()

    target_s_id = os.environ.get("TARGET_SPREADSHEET_ID")
    worksheet_name = "github"

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

    print("\n🎉 고유 ID 기반 10대 마스터 데이터 최신화 파이프라인이 정상 종료되었습니다!")


if __name__ == "__main__":
    asyncio.run(run_pipeline())
