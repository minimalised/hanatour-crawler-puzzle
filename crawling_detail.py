import asyncio
import hashlib
import datetime
import re
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from playwright.async_api import async_playwright

# ==========================================
# [최종완성] 상위 80개 패턴 분석 기반 SEO 최적화 함수
# ==========================================
def generate_naver_title(title, region_name):
    """
    네이버 쇼핑 상위 노출 80개 상품의 공통 패턴인 
    [출발지 선점 + 명사형 나열 + 타겟 다각화 + 중복 키워드 제거 + 단어 단위 세이프 커팅]을 적용한 최상위 SEO 함수
    """
    # 1. 원본 대괄호 등급 태그 추출 및 보존
    grade_tags = re.findall(r'\[.*?\]', title)
    grade_prefix = "".join(grade_tags) if grade_tags else ""
    
    # 2. 본문 타이틀과 해시태그 분리 및 결합 텍스트 준비
    parts = title.split('#')
    title_body = parts[0].strip()
    hashtags = [h.strip() for h in parts[1:] if h.strip()]
    
    for gt in grade_tags:
        title_body = title_body.replace(gt, "")
    title_body = title_body.strip()
    
    hash_str = " ".join(hashtags)
    combined_text = f"{title_body} {hash_str}"

    # 3. [상위 80개 데이터 반영] 출발지 키워드 자동 스크리닝
    departure = ""
    departures = ["부산출발", "대구출발", "청주출발", "무안출발", "인천출발"]
    for dep in departures:
        if dep in combined_text:
            departure = f"{dep} "
            break

    # 4. [상위 80개 데이터 반영] 시즌성 연휴 및 방학 키워드 자동 매핑
    season_tag = ""
    now = datetime.datetime.now()
    if now.month in [5, 6, 7, 8]:
        season_tag = "여름휴가 추석연휴 여름방학 "
    elif now.month in [9, 10, 11]:
        season_tag = "단풍여행 겨울휴가 추석연휴 "
    else:
        season_tag = "해외여행추천 연휴여행 "

    # 5. [상위 80개 데이터 반영] 조사를 완전히 뺀 명사형 롱테일 타겟 확장
    target_tag = "해외여행 패키지투어"
    if any(x in combined_text for x in ["효도", "부모님", "조부모", "환갑", "칠순"]):
        target_tag = "부모님 효도여행 환갑여행 칠순여행 추천"
    elif any(x in combined_text or x in grade_prefix for x in ["2030", "필름", "청춘", "혼자"]):
        target_tag = "2030청춘여행 대학생세미패키지 혼자여행"
    elif any(x in combined_text for x in ["가족", "아동", "소아", "손주", "엄마랑"]):
        target_tag = "가족해외여행 엄마랑여행 패키지 추천"
    elif any(x in combined_text for x in ["자유", "세미", "에어텔", "호캉스"]):
        target_tag = "세미패키지 자유일정포함 호캉스"

    # 6. 해시태그 기반 핵심 쇼핑 키워드 2개 추출
    selling_points = []
    if "노쇼핑" in combined_text or "NO쇼핑" in combined_text: selling_points.append("노쇼핑")
    if "노옵션" in combined_text or "NO옵션" in combined_text: selling_points.append("노팁노옵션")
    if "5성" in combined_text or "초특급" in combined_text: selling_points.append("특급호텔숙박")
    if "마사지" in combined_text or "스파" in combined_text: selling_points.append("1일1마사지")
    if "크루즈" in combined_text or "요트" in combined_text: selling_points.append("크루즈투어")
    if "홈쇼핑" in combined_text: selling_points.append("홈쇼핑히트")
    
    while len(selling_points) < 2 and hashtags:
        candidate = hashtags.pop(0)
        if len(candidate) <= 6 and candidate not in selling_points and "추천" not in candidate:
            selling_points.append(candidate)
    
    benefit_tag = " ".join(selling_points) if selling_points else "출발확정인기상품"

    # 7. 유니크 랜드마크 코스 추출 (중복 상품 묶임 파괴용 쐐기)
    unique_spot = ""
    spots_pool = [
        "담넌사두억", "위험한기찻길", "니모섬", "아유타야", "왓아룬", "진리의성전", "농눅빌리지",
        "디너크루즈", "마하나콘", "후아힌", "시밀란", "카오락", "팡아만", "피피섬", "끄라비", 
        "치앙라이", "치앙다오", "몬쨈", "도이인타논", "도이수텝", "북해도", "삿포로", "오사카",
        "오타루", "노보리베츠", "발칸", "체코", "부다페스트", "크로아티아", "프라하", "센토사",
        "시드니", "유후인", "시모노세키", "마카오", "홍콩", "세부", "보홀", "대마도", "카파도키아"
    ]
    for spot in spots_pool:
        if spot in combined_text:
            unique_spot = f"{spot}관광코스 "
            break

    # 8. 지역명 기본 매핑 및 예외 보정
    clean_region = region_name.replace("지역名 미상", "").replace("지역명 미상", "").strip()
    if not clean_region:
        if "푸껫" in combined_text or "푸켓" in combined_text: clean_region = "푸켓"
        elif "치앙마이" in combined_text: clean_region = "치앙마이"
        elif "북해도" in combined_text or "삿포로" in combined_text: clean_region = "일본 북해도"
        elif "오사카" in combined_text: clean_region = "일본 오사카"
        else: clean_region = "동남아"

    # 9. 명사 위주의 징검다리식 배열 구조 생성
    raw_naver_title = f"{departure}{season_tag}{target_tag} {benefit_tag} {clean_region} {unique_spot}{title_body}"
    
    # 🌟 [보완 포인트 1] 순서 유지하며 단어 중복 제거 (dict.fromkeys 사용)
    words = raw_naver_title.split()
    unique_words = list(dict.fromkeys(words))
    clean_title = " ".join(unique_words)
    
    # 🌟 [보완 포인트 2] 단어 단위 세이프 커팅 (최대 75자 제한)
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

                            # 🌟 최종 업그레이드된 SEO 변환 로직 연동
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
