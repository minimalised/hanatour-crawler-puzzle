import gspread
from google.oauth2.service_account import Credentials
from playwright.sync_api import sync_playwright
from playwright_stealth import stealth_sync
import time

def run_hotel_crawling():
    # 1. 구글 시트 연결 (키 파일명은 환경에 맞게 수정)
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_file("secrets.json", scopes=scopes)
    client = gspread.authorize(creds)
    
    spreadsheet = client.open("호텔상품리스트")
    worksheet = spreadsheet.get_worksheet(0)
    
    # 헤더 제외한 전체 행 가져오기
    all_rows = worksheet.get_all_values()
    data_rows = all_rows[1:] # 2행부터

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True) # Actions 환경이므로 True
        context = browser.new_context(viewport={'width': 1920, 'height': 1080})
        page = context.new_page()
        stealth_sync(page) # 봇 탐지 방지 적용

        for i, row in enumerate(data_rows, start=2):
            url = row[0].strip()   # A열: URL
            region = row[1].strip() # B열: 지역명
            
            if not url or "http" not in url:
                continue

            print(f">>> [{region}] 크롤링 시도: {url}")
            
            try:
                page.goto(url, wait_until="domcontentloaded")
                # 메인 데이터 요소가 나타날 때까지 대기
                page.wait_for_selector(".item_title", timeout=15000)
                time.sleep(3) # 동적 렌더링 완료 대기

                # --- 데이터 추출 (제공된 HTML 매칭) ---
                # 1. 호텔명 (상단 메인)
                hotel_name = page.locator(".item_title").first.inner_text().strip()
                
                # 2. 가격 (상단 1박 요금 최저가)
                # .price_group 안의 .price가 여러개일 수 있으나 요약 영역의 것을 가져옴
                price_text = page.locator(".ly_wrap .price").first.inner_text()
                price = price_text.replace("원~", "").replace(",", "").strip()

                # 3. 이미지 URL (상단 메인 이미지 첫 번째)
                image_url = page.locator(".htl_photo img").first.get_attribute("src")

                # 4. 평점 (별점 옆 숫자 4.4 등)
                rating = page.locator(".score_htl_wrap .star").first.inner_text().strip()

                # 5. 후기 개수 (숫자만 추출)
                review_raw = page.locator(".score_htl_wrap em").first.inner_text()
                review_count = "".join(filter(str.isdigit, review_raw))

                print(f"성공: {hotel_name} | {price}원 | {rating}점")

                # --- 시트 업데이트 (C열~H열) ---
                # 상품명(C), 가격(D), 이미지(E), 현재링크(F), 평점(G), 후기(H)
                worksheet.update(f"C{i}:H{i}", [[hotel_name, price, image_url, url, rating, review_count]])

            except Exception as e:
                print(f"실패 [{url}]: {e}")
                continue

        browser.close()

if __name__ == "__main__":
    run_hotel_crawling()
