import gspread
from google.oauth2.service_account import Credentials
from playwright.sync_api import sync_playwright
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

    try:
        master_spreadsheet = client.open_by_key(MASTER_SHEET_ID)
        master_worksheet = master_spreadsheet.worksheet(READ_TAB_NAME)
        all_rows = master_worksheet.get_all_values()
        data_rows = all_rows[1:] 
    except Exception as e:
        print(f"MASTER_LOAD_ERROR: {e}")
        return

    with sync_playwright() as p:
        # 브라우저 실행 시 봇 탐지 회피를 위한 인자 추가
        browser = p.chromium.launch(headless=True, args=["--disable-blink-features=AutomationControlled"])
        context = browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )
        page = context.new_page()

        for i, row in enumerate(data_rows, start=2):
            if not row or len(row) < 1: continue
            url = row[0].strip()
            region = row[1].strip() if len(row) > 1 else "지역미정"
            if not url or "http" not in url: continue

            print(f"[{region}] 작업 시작: {url}")
            
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=30000)
                page.wait_for_selector(".item_title", timeout=15000)
                time.sleep(3)

                hotel_name = page.locator(".item_title").first.inner_text().strip()
                price_text = page.locator(".ly_wrap .price").first.inner_text()
                price = price_text.replace("원~", "").replace(",", "").strip()
                image_url = page.locator(".htl_photo img").first.get_attribute("src")
                rating = page.locator(".score_htl_wrap .star").first.inner_text().strip()
                review_raw = page.locator(".score_htl_wrap em").first.inner_text()
                review_count = "".join(filter(str.isdigit, review_raw))
                product_id = hashlib.md5(hotel_name.encode()).hexdigest()[:8]

                extracted_data = [[hotel_name, price, image_url, url, rating, review_count, product_id]]

                for t_id in TARGET_SHEET_IDS:
                    try:
                        target_ws = client.open_by_key(t_id).worksheet(WRITE_TAB_NAME)
                        target_ws.update(f"C{i}:I{i}", extracted_data)
                    except Exception as e:
                        print(f"UPDATE_ERROR ({t_id}): {e}")

            except Exception as e:
                print(f"SKIP [{url}]: {e}")
                continue

        browser.close()

if __name__ == "__main__":
    run_hotel_crawling()
