import gspread
from google.oauth2.service_account import Credentials
from playwright.sync_api import sync_playwright
# 최신 버전의 라이브러리에서 발생하던 임포트 에러를 해결하기 위한 방식입니다.
import playwright_stealth
import hashlib
import time

def run_hotel_crawling():
    # 1. 구글 시트 인증 설정
    # 서비스 계정 키 파일 이름이 'secrets.json'인지 확인해 주세요.
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_file("secrets.json", scopes=scopes)
    client = gspread.authorize(creds)
    
    # ---------------------------------------------------------
    # 2. 시트 및 탭 설정
    # URL 리스트를 가져올 마스터 스프레드시트 ID
    MASTER_SHEET_ID = "1mH51VHs4y0FgClkUBvZgw7oY3Yv7gQBA_a3um9uhX0I"
    
    # URL 리스트를 불러올 탭 이름
    READ_TAB_NAME = "호텔상품리스트"
    # 크롤링 후 데이터를 적재할 탭 이름
    WRITE_TAB_NAME = "github_hotel"
    
    # 결과를 동일하게 적재할 모든 타겟 스프레드시트 ID 리스트
    TARGET_SHEET_IDS = [
        "1mH51VHs4y0FgClkUBvZgw7oY3Yv7gQBA_a3um9uhX0I",
        "1JgWk9PYT6LG_1GnPdpVY0mZavcHXDWRSrzdE0lVmjj4",
        "1Hoq0N88mestsHXbIOjwue3OctXf7dvKkx99eieYFhAY",
        "1BK4xUHQFrLjLTn6vE0jSuwqMvSU7ZMKIV-nPvmySPx8"
    ]
    # ---------------------------------------------------------

    # 마스터 시트에서 크롤링할 URL 리스트 읽기
    try:
        master_spreadsheet = client.open_by_key(MASTER_SHEET_ID)
        master_worksheet = master_spreadsheet.worksheet(READ_TAB_NAME)
        all_rows = master_worksheet.get_all_values()
        data_rows = all_rows[1:] # 첫 행(헤더) 제외
    except Exception as e:
        print(f"❌ 마스터 시트({READ_TAB_NAME}) 로드 실패: {e}")
        return

    with sync_playwright() as p:
        # 브라우저 실행
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={'width': 1920, 'height': 1080})
        page = context.new_page()
        
        # 봇 탐지 우회 설정 (함수 호출 방식 수정됨)
        playwright_stealth.stealth_sync(page)

        for i, row in enumerate(data_rows, start=2):
            if not row or len(row) < 1: continue
            
            url = row[0].strip()   # A열: URL
            region = row[1].strip() if len(row) > 1 else "지역미정" # B열: 지역명
            
            if not url or "http" not in url:
                continue

            print(f">>> [{region}] 크롤링 중: {url}")
            
            try:
                page.goto(url, wait_until="domcontentloaded")
                # 페이지 내 주요 요소가 나타날 때까지 대기
                page.wait_for_selector(".item_title", timeout=15000)
                time.sleep(3) # 추가 렌더링 대기 시간

                # --- 데이터 추출 (상세 페이지 기준) ---
                hotel_name = page.locator(".item_title").first.inner_text().strip()
                
                # 가격 정보 추출 및 숫자화
                price_text = page.locator(".ly_wrap .price").first.inner_text()
                price = price_text.replace("원~", "").replace(",", "").strip()
                
                # 이미지 URL
                image_url = page.locator(".htl_photo img").first.get_attribute("src")
                
                # 평점 점수
                rating = page.locator(".score_htl_wrap .star").first.inner_text().strip()
                
                # 리뷰 수 추출 (숫자만 필터링)
                review_raw = page.locator(".score_htl_wrap em").first.inner_text()
                review_count = "".join(filter(str.isdigit, review_raw))
                
                # 데이터 식별을 위한 고유 8자리 ID 생성
                product_id = hashlib.md5(hotel_name.encode()).hexdigest()[:8]

                # 적재할 데이터 리스트 (C열부터 I열까지 총 7개 항목)
                extracted_data = [[hotel_name, price, image_url, url, rating, review_count, product_id]]
                print(f"   ✅ 추출 성공: {hotel_name}")

                # --- 지정된 모든 타겟 시트에 동일 내용 적재 ---
                for t_id in TARGET_SHEET_IDS:
                    if not t_id or "입력" in t_id: continue
                    try:
                        target_worksheet = client.open_by_key(t_id).worksheet(WRITE_TAB_NAME)
                        # C열(3)부터 I열(9)까지 업데이트
                        target_worksheet.update(f"C{i}:I{i}", extracted_data)
                    except Exception as sheet_err:
                        print(f"      ⚠️ 시트 업데이트 실패(ID: {t_id}, 탭: {WRITE_TAB_NAME}): {sheet_err}")

            except Exception as e:
                print(f"   ❌ 크롤링 실패 [{url}]: {e}")
                continue

        browser.close()

if __name__ == "__main__":
    run_hotel_crawling()
