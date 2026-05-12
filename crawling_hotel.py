import gspread
from google.oauth2.service_account import Credentials
from playwright.sync_api import sync_playwright
import playwright_stealth
import hashlib
import time

def run_hotel_crawling():
    # 1. 구글 시트 인증 설정
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_file("secrets.json", scopes=scopes)
    client = gspread.authorize(creds)
    
    # ---------------------------------------------------------
    # 2. 시트 및 탭 설정
    MASTER_SHEET_ID = "1mH51VHs4y0FgClkUBvZgw7oY3Yv7gQBA_a3um9uhX0I"
    READ_TAB_NAME = "호텔상품리스트"
    WRITE_TAB_NAME = "github_hotel"
    
    TARGET_SHEET_IDS = [
        "1mH51VHs4y0FgClkUBvZgw7oY3Yv7gQBA_a3um9uhX0I",
        "1JgWk9PYT6LG_1GnPdpVY0mZavcHXDWRSrzdE0lVmjj4",
        "1Hoq0N88mestsHXbIOjwue3OctXf7dvKkx99eieYFhAY",
        "1BK4xUHQFrLjLTn6vE0jSuwqMvSU7ZMKIV-nPvmySPx8"
    ]
    # ---------------------------------------------------------

    # 마스터 시트 데이터 로드
    try:
        master_spreadsheet = client.open_by_key(MASTER_SHEET_ID)
        master_worksheet = master_spreadsheet.worksheet(READ_TAB_NAME)
        all_rows = master_worksheet.get_all_values()
        data_rows = all_rows[1:] 
    except Exception as e:
        print(f"FAILED_TO_LOAD_MASTER: {e}")
        return

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={'width': 1920, 'height': 1080})
        page = context.new_page()
        
        # [CRITICAL] AttributeError 해결을 위한 직접 호출 방식
        # 모듈 내의 wrapper가 아닌 실제 stealth 함수를 직접 사용
        from playwright_stealth.stealth import stealth_sync
        stealth_sync(page)

        for i, row in enumerate(data_rows, start=2):
            if not row or len(row) < 1: continue
            
            url = row[0].strip()
            region = row[1].strip() if len(row) > 1 else "지역미정"
            
            if not url or "http" not in url:
                continue

            print(f"PROCESSING: [{region}] {url}")
            
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=30000)
                page.wait_for_selector(".item_title", timeout=15000)
                time.sleep(3)

                # 데이터 추출
                hotel_name = page.locator(".item_title").first.inner_text().strip()
                price_text = page.locator(".ly_wrap .price").first.inner_text()
                price = price_text.replace("원~", "").replace(",", "").strip()
                image_url = page.locator(".htl_photo img").first.get_attribute("src")
                rating = page.locator(".score_htl_wrap .star").first.inner_text().strip()
                review_raw = page.locator(".score_htl_wrap em").first.inner_text()
                review_count = "".join(filter(str.isdigit, review_raw))
                product_id = hashlib.md5(hotel_name.encode()).hexdigest()[:8]

                extracted_data = [[hotel_name, price, image_url, url, rating, review_count, product_id]]

                # 타겟 시트 적재
                for t_id in TARGET_SHEET_IDS:
                    if not t_id or "입력" in t_id: continue
                    try:
                        target_ws = client.open_by_key(t_id).worksheet(WRITE_TAB_NAME)
                        target_ws.update(f"C{i}:I{i}", extracted_data)
                    except Exception as e:
                        print(f"SHEET_UPDATE_ERROR (ID:{t_id}): {e}")

            except Exception as e:
                print(f"CRAWLING_ERROR [{url}]: {e}")
                continue

        browser.close()

if __name__ == "__main__":
    run_hotel_crawling()
