import asyncio
import hashlib
import datetime
import re
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from playwright.async_api import async_playwright

# ==========================================
# [추가] 네이버 쇼핑 최적화 키워드 가공 함수
# ==========================================
def generate_naver_title(title, region_name):
    """
    원본 상품명과 지역명을 기반으로 네이버 검색 최적화 상품명을 생성합니다.
    """
    # 1. 시즌 키워드 자동 계산 (현재 월 기준 3개월 차트)
    now = datetime.datetime.now()
    m1 = now.month
    m2 = 12 if m1 == 11 else (m1 + 1) % 12
    m3 = 12 if m2 == 11 else (m2 + 1) % 12
    m2 = 12 if m2 == 0 else m2
    m3 = 12 if m3 == 0 else m3
    season_tag = f"[{m1}월/{m2}월/{m3}월출발]"

    # 2. 원본 상품명 텍스트 기반 속성 필터링 (핵심 셀링포인트 추출)
    attributes = []
    if any(x in title for x in ["노쇼핑", "쇼핑없음", "쇼핑 0회"]):
        attributes.append("노쇼핑")
    if any(x in title for x in ["노옵션", "옵션없음"]):
        attributes.append("노옵션")
    if any(x in title for x in ["대한항공", "아시아나", "국적기"]):
        attributes.append("국적기탑승")
    if any(x in title for x in ["5성", "특급", "일급"]):
        attributes.append("특급호텔")
    
    prefix = f"[{'/'.join(attributes)}]" if attributes else "[인기패키지]"

    # 3. TPO / 타겟 키워드 추출
    tpo = "가족여행추천" # 기본값
    if any(x in title for x in ["효도", "부모님", "온천", "품격"]):
        tpo = "부모님 효도여행"
    elif any(x in title for x in ["아동", "소아", "소인", "워터파크", "가족"]):
        tpo = "아이동반 가족여행"
    elif any(x in title for x in ["자유", "에어텔", "세미"]):
        tpo = "자유일정포함"

    # 4. 일정(박수) 추출 (예: 4일, 5일, 3박4일 등)
    duration_match = re.search(r'\d+일|\d+박\d+일', title)
    duration = f" {duration_match.group(0)}" if duration_match else ""

    # 5. 대표 키워드 및 카탈로그 회피형 구조 조합
    # 구조: [시즌] [속성] 타겟TPO + 지역명 + 패키지여행 + 일정
    clean_region = region_name.replace("지역명 미상", "").strip()
    main_keyword = f"{clean_region} 패키지여행" if clean_region else "해외 패키지여행"
    
    naver_title = f"{season_tag} {prefix} {tpo} {main_keyword}{duration}"
    
    # 공백 정돈 및 네이버 권장 글자 수(50자 내외) 제한
    clean_title = " ".join(naver_title.split())
    return clean_title[:50].strip()


async def run_crawler():
    # 1. 구글 스프레드시트에서 URL 리스트 가져오기
    print("🌐 스프레드시트에서 URL 리스트를 불러오는 중...")
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_file('secrets.json', scopes=scopes)
    gc = gspread.authorize(creds)
    
    source_spreadsheet_id = "1mH51VHs4y0FgClkUBvZgw7oY3Yv7gQBA_a3um9uhX0I"
    try:
        source_doc = gc.open_by_key(source_spreadsheet_id)
        source_sheet = source_doc.worksheet("상품리스트")
        raw_urls = source_sheet.col_values(1)
        url_list = [url for url in raw_urls if url.startswith("http")]
        print(f"✅ 총 {len(url_list)}개의 URL을 확보했습니다.")
    except Exception as e:
        print(f"❌ URL 리스트를 가져오는 중 에러 발생: {e}")
        return

    # 2. Playwright 크롤링 시작
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={'width': 1280, 'height': 1024},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )
        page = await context.new_page()

        all_products = []

        for current_url in url_list:
            try:
                await page.goto(current_url, wait_until="domcontentloaded", timeout=60000)
                
                try:
                    await page.wait_for_selector("a.js_show", timeout=10000)
                    region_name = (await page.inner_text("a.js_show")).strip()
                except:
                    region_name = "지역명 미상"

                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                await asyncio.sleep(2)

                try:
                    final_items = await page.query_selector_all(".prod_list_wrap ul.type > li")
                    for item in final_items:
                        try:
                            main_info = await item.query_selector(":scope > .inr.right")
                            img_check = await item.query_selector(":scope > .inr.img")
                            
                            if not main_info or not img_check:
                                continue

                            # 1. 상품명 추출
                            title_el = await main_info.query_selector(".item_title")
                            title = (await title_el.inner_text()).strip() if title_el else "제목 없음"

                            # 2. 가격 추출
                            price_el = await main_info.query_selector(".price")
                            price_raw = await price_el.inner_text() if price_el else "0"
                            price = "".join(filter(str.isdigit, price_raw))

                            # 3. 평점 및 리뷰 수 추출
                            star_el = await main_info.query_selector(".icn.star")
                            if star_el:
                                star_text = await star_el.inner_text()
                                rating = star_text.split('(')[0].strip()
                                review_count_el = await star_el.query_selector("em")
                                review_count = await review_count_el.inner_text() if review_count_el else "0"
                                review_count = "".join(filter(str.isdigit, review_count))
                            else:
                                rating = "0"
                                review_count = "0"

                            # 4. 이미지 URL 추출
                            img_el = await img_check.query_selector("img")
                            img_url = await img_el.get_attribute("src") if img_el else ""
                            if img_url and img_url.startswith("//"): 
                                img_url = "https:" + img_url

                            # 5. 고유 ID 생성
                            product_id = hashlib.md5(title.encode()).hexdigest()[:8]

                            # 6. URL 조합
                            final_url = f"{current_url}"

                            # 🌟 [보완 핵심] 네이버 쇼핑 전용 상품명 가공 레이어 실행
                            naver_title = generate_naver_title(title, region_name)

                            all_products.append({
                                "ID": product_id,
                                "지역": region_name,
                                "상품명": title,
                                "네이버_상품명": naver_title,  # 새로운 파싱 데이터 추가
                                "가격": int(price) if price else 0,
                                "평점": float(rating) if rating else 0.0,
                                "리뷰수": int(review_count) if review_count else 0,
                                "이미지URL": img_url,
                                "URL": final_url
                            })
                        except Exception as e:
                            print(f"개별 상품 파싱 에러: {e}")
                            continue
                except Exception as e:
                    print(f"파싱 리스트 획득 에러: {e}")

                print(f"✅ {region_name} 완료 ({len(all_products)}개 누적)")
                await asyncio.sleep(1)

            except Exception as e:
                print(f"❌ {current_url} 접속 에러: {e}")
                continue

        # 3. 결과 데이터를 다시 스프레드시트에 적재
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
                # 🌟 컬럼 순서에 '네이버_상품명' 반영
                column_order = ["지역", "상품명", "네이버_상품명", "가격", "평점", "리뷰수", "이미지URL", "URL", "ID"]
                df = df[column_order]
                data_to_upload = [df.columns.values.tolist()] + df.values.tolist()

                for spreadsheet_id in target_spreadsheet_ids:
                    try:
                        doc = gc.open_by_key(spreadsheet_id)
                        sheet = doc.worksheet(worksheet_name)
                        sheet.clear()
                        sheet.update(data_to_upload)
                        print(f"✅ 성공: [{doc.title}] 업데이트 완료")
                    except Exception as sheet_error:
                        print(f"⚠️ {spreadsheet_id} 업데이트 실패: {sheet_error}")

            except Exception as e:
                print(f"❌ 구글 시트 결과 적재 에러: {e}")
        
        await browser.close()

if __name__ == "__main__":
    asyncio.run(run_crawler())
