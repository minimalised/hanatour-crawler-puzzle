import asyncio
import hashlib
import datetime
import re
import random
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from playwright.async_api import async_playwright

# ==========================================
# [최종완성] 상위 80개 스냅샷 기반 자연스러운 변조 엔진 함수
# ==========================================
def generate_naver_title(title, region_name):
    """
    기계적인 단어 대량 나열을 전면 배제하고, 실전 상위 80개 상품처럼 
    자연스러운 샌드위치 믹스(앞단 교통/시즌 + 원본 바디 + 뒷단 타겟/혜택) 가공을 수행하는 함수
    """
    # 1. 원본 대괄호 등급 태그 및 해시태그 분리
    grade_tags = re.findall(r'\[.*?\]', title)
    grade_prefix = "".join(grade_tags) if grade_tags else ""
    
    parts = title.split('#')
    title_body = parts[0].strip()
    hashtags = [h.strip() for h in parts[1:] if h.strip()]
    
    # 원본 바디에서 대괄호 중복 제거하여 자연스러운 핵심 본문 확보
    for gt in grade_tags:
        title_body = title_body.replace(gt, "")
    title_body = " ".join(title_body.split()).strip()
    
    hash_str = " ".join(hashtags)
    combined_text = f"{title_body} {hash_str}"

    # 2. [실전 80개 반영] 자연스러운 출발지 및 국적기/교통 특전 추출
    departure = ""
    departures = ["부산출발", "대구출발", "청주출발", "무안출발", "인천출발"]
    for dep in departures:
        if dep in combined_text:
            departure = dep
            break
            
    transport = ""
    if "대한항공" in combined_text: transport = "대한항공"
    elif "아시아나" in combined_text: transport = "아시아나"
    elif "크루즈" in combined_text or "요트" in combined_text: transport = "크루즈"
    elif "선박" in combined_text or "배타고" in combined_text: transport = "배타고"

    # 3. [인위적인 느낌 제거] 무작위 1개만 매칭되는 시즌 및 방학 키워드 풀
    season_pool = []
    now = datetime.datetime.now()
    if now.month in [5, 6, 7, 8]:
        season_pool = ["여름휴가", "추석여행", "여름방학", "7월출발", "8월여행"]
    elif now.month in [9, 10, 11]:
        season_pool = ["추석연휴", "단풍여행", "겨울휴가", "주말특가"]
    else:
        season_pool = ["인기상품", "실시간예약", "추천여행지"]
    chosen_season = random.choice(season_pool)

    # 4. [실전 80개 반영] 자연스러운 명사 나열형 타겟(TPO) 확장 풀
    target_pool = []
    if any(x in combined_text for x in ["효도", "부모님", "조부모", "환갑", "칠순"]):
        target_pool = ["부모님 효도여행", "가족휴양", "환갑여행추천"]
    elif any(x in combined_text or x in grade_prefix for x in ["2030", "필름", "청춘", "또래"]):
        target_pool = ["2030 청춘여행", "세미패키지", "자유일정포함"]
    elif any(x in combined_text for x in ["가족", "아동", "소아", "손주", "엄마랑", "키즈"]):
        target_pool = ["가족여행", "엄마랑여행", "가족휴양추천"]
    else:
        target_pool = ["패키지여행", "해외여행코스", "추천자유일정"]
    chosen_target = random.choice(target_pool)

    # 5. 해시태그 풀에서 진짜 핵심 알짜 특전 1개만 무작위 솎아내기
    benefit = ""
    benefits_pool = []
    if "노쇼핑" in combined_text or "NO쇼핑" in combined_text: benefits_pool.append("노쇼핑")
    if "노옵션" in combined_text or "NO옵션" in combined_text: benefits_pool.append("노옵션")
    if "5성" in combined_text or "초특급" in combined_text or "특급" in combined_text: benefits_pool.append("특급호텔")
    if "마사지" in combined_text or "스파" in combined_text: benefits_pool.append("1일1마사지")
    if "홈쇼핑" in combined_text: benefits_pool.append("홈쇼핑히트")
    
    if benefits_pool:
        benefit = random.choice(benefits_pool)
    elif hashtags:
        # 조건에 걸리는 마케팅 키워드가 없으면 원본의 유니크 해시태그 중 가독성 좋은 단어 1개 매칭
        short_tags = [h for h in hashtags if len(h) <= 5 and "추천" not in h]
        if short_tags: benefit = random.choice(short_tags)

    # 6. [샌드위치 구조식 조립] 기계적 나열을 타파하는 완성도 높은 변조 컴포징
    front_parts = [departure, transport, chosen_season]
    front_text = " ".join([f for f in front_parts if f]).strip()
    
    back_parts = [chosen_target, benefit]
    back_text = " ".join([b for b in back_parts if b]).strip()
    
    # 최종 결합 (앞단 조합어 + 원본 타이틀 본문 + 뒷단 마케팅어)
    final_raw_title = f"{front_text} {title_body} {back_text}"
    
    # 7. 단어 중복 필터링 및 단어 깨짐 현상 없는 세이프 커팅 (최대 75자 한도)
    words = final_raw_title.split()
    unique_words = list(dict.fromkeys(words))  # 순서 보존 단어 중복 제거
    clean_title = " ".join(unique_words)
    
    max_length = 75
    if len(clean_title) > max_length:
        truncated = clean_title[:max_length]
        last_space = truncated.rfind(" ")
        if last_space != -1:
            clean_title = truncated[:last_space].strip()
            
    return clean_title.strip()


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

                            # 🌟 상위 80개 매칭 기반 자연스러운 믹싱 솔루션 구동
                            naver_title = generate_naver_title(title, region_name)

                            all_products.append({
                                "ID": product_id,
                                "지역": region_name,
                                "상품명": title,
                                "네이버_상품명": naver_title,
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
            worksheet_name = "github_detail"

            try:
                df = pd.DataFrame(all_products)
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
