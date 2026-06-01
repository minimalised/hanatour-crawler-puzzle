import asyncio
import hashlib
import datetime
import re
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from playwright.async_api import async_playwright

# ==========================================
# [최종완성] 중복 단어 제거 및 단어 단위 세이프 커팅 적용 함수
# ==========================================
def generate_naver_title(title, region_name):
    """
    하나투어의 해시태그(#)와 특전 정보를 완벽히 분석하여 
    중복 키워드를 제거하고, 지정된 글자 수 한도 내에서 단어 깨짐 없이 깔끔하게 마감하는 함수
    """
    # 1. 원본 대괄호 등급 태그 추출 및 보존 (예: [신상품][세이브], [2030전용])
    grade_tags = re.findall(r'\[.*?\]', title)
    grade_prefix = "".join(grade_tags) if grade_tags else "[인기추천]"
    
    # 2. 본문 타이틀과 해시태그 분리
    parts = title.split('#')
    title_body = parts[0].strip()
    hashtags = [h.strip() for h in parts[1:] if h.strip()]
    
    # 등급 태그가 타이틀 본문에 중복으로 남아있다면 정돈
    for gt in grade_tags:
        title_body = title_body.replace(gt, "")
    title_body = title_body.strip()
    
    hash_str = " ".join(hashtags)
    
    # 3. 마케팅 접두어 풀(Pool) 구성
    marketing_tag = "[실시간예약]"
    if "신상품" in grade_prefix:
        marketing_tag = "[신상공개]"
    elif "세이브" in grade_prefix or "특가" in hash_str or "가격" in hash_str:
        marketing_tag = "[단독특가]"
    elif "스마트" in grade_prefix or "가성비" in hash_str:
        marketing_tag = "[실속추천]"
    elif "프리미엄" in grade_prefix or "초특급" in hash_str:
        marketing_tag = "[품격인증]"

    # 4. 해시태그 기반의 정교한 타겟(TPO) 필터링
    tpo_keyword = "해외여행"
    if any(x in hash_str for x in ["효도", "부모님", "조부모"]):
        tpo_keyword = "부모님 효도관광"
    elif any(x in grade_prefix or x in hash_str for x in ["2030", "필름감성", "도파민", "SNS"]):
        tpo_keyword = "2030 청춘여행"
    elif any(x in hash_str for x in ["가족", "아동", "소아", "손주", "워터파크"]):
        tpo_keyword = "가족여행 추천"
    elif any(x in hash_str for x in ["휴양", "호캉스", "올인크루시브", "힐링"]):
        tpo_keyword = "힐링 휴양여행"

    # 5. 핵심 혜택 및 유니크 키워드 스크리닝 (상위 노출 길목 확보)
    selling_points = []
    if any(x in hash_str for x in ["노쇼핑", "NO쇼핑", "쇼핑없음"]):
        selling_points.append("노쇼핑")
    if any(x in hash_str for x in ["노옵션", "NO옵션", "옵션없음"]):
        selling_points.append("노옵션")
    if any(x in hash_str for x in ["5성", "초특급"]) and "5성호텔" not in hash_str:
        selling_points.append("5성급호텔")
    if any(x in hash_str for x in ["마사지", "지압", "스파"]):
        selling_points.append("1일1마사지")
    if any(x in hash_str for x in ["자유", "세미", "에어텔"]):
        selling_points.append("자유일정포함")
    if any(x in hash_str for x in ["크루즈", "요트"]) and "디너크루즈" not in hash_str:
        selling_points.append("요트크루즈")
        
    # 만약 매칭된 상위 혜택이 부족하면 실제 해시태그 중 유니크한 6자 이하 명사 추출
    while len(selling_points) < 2 and hashtags:
        candidate = hashtags.pop(0)
        if len(candidate) <= 6 and candidate not in selling_points and "추천" not in candidate:
            selling_points.append(candidate)
            
    selling_prefix = f"[{'/'.join(selling_points)}]" if selling_points else "[추천패키지]"

    # 6. 세부 랜드마크 코스 추출을 통한 중복 파괴
    unique_spot = ""
    spots_pool = [
        "담넌사두억", "위험한기찻길", "니모섬", "아유타야", "왓아룬", "진리의성전", "농눅빌리지",
        "디너크루즈", "마하나콘", "후아힌", "시밀란", "카오락", "팡아만", "피피섬", "끄라비", 
        "치앙라이", "치앙다오", "몬쨈", "도이인타논", "도이수텝", "르메르디앙"
    ]
    for spot in spots_pool:
        if spot in hash_str or spot in title_body:
            unique_spot = f"{spot} 중심코스 "
            break

    # 7. 카테고리/지역명 자동 맵핑 및 예외 보정
    clean_region = region_name.replace("지역名 미상", "").replace("지역명 미상", "").strip()
    if not clean_region:
        if "푸껫" in title_body: clean_region = "푸켓"
        elif "치앙마이" in title_body: clean_region = "치앙마이"
        elif "카오락" in title_body: clean_region = "카오락"
        else: clean_region = "방콕 패키지"

    # 8. 구조 1차 조립
    raw_naver_title = f"{marketing_tag} {grade_prefix} {selling_prefix} {tpo_keyword} {clean_region} {unique_spot}{title_body}"
    
    # 🌟 [보완 포인트 1] 순서를 유지하면서 중복 텍스트/단어 완벽 제거
    words = raw_naver_title.split()
    unique_words = list(dict.fromkeys(words))
    clean_title = " ".join(unique_words)
    
    # 🌟 [보완 포인트 2] 단어 단위로 세이프 커팅 (최대 75자 제한)
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

                            # 🌟 고도화된 네이버 최적화 상품명 변환 엔진 연동
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
