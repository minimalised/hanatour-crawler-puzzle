import os
import json
import asyncio
import hashlib
import gspread
from google.oauth2.service_account import Credentials
from playwright.async_api import async_playwright

async def run_hotel_crawling():
    json_raw = os.environ.get("GOOGLE_JSON_RAW")
    
    if json_raw:
        with open("secrets.json", "w", encoding="utf-8") as f:
            f.write(json_raw)

    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_file("secrets.json", scopes=scopes)
    gc = gspread.authorize(creds)

    MASTER_SHEET_ID = "1mH51VHs4y0FgClkUBvZgw7oY3Yv7gQBA_a3um9uhX0I"
    READ_TAB_NAME = "호텔상품리스트"
    WRITE_TAB_NAME = "github_hotel"
    
    TARGET_SHEET_IDS = [
        "1mH51VHs4y0FgClkUBvZgw7oY3Yv7gQBA_a3um9uhX0I",
        "1JgWk9PYT6LG_1GnPdpVY0mZavcHXDWRSrzdE0lVmjj4",
        "1Hoq0N88mestsHXbIOjwue3OctXf7dvKkx99eieYFhAY",
        "1BK4xUHQFrLjLTn6vE0jSuwqMvSU7ZMKIV-nPvmySPx8"
    ]

    try:
        master_sheet = gc.open_by_key(MASTER_SHEET_ID).worksheet(READ_TAB_NAME)
        data_rows = master_sheet.get_all_values()[1:]
    except Exception as e:
        print(f"❌ 마스터 시트 로드 실패: {e}")
        if json_raw and os.path.exists("secrets.json"):
            os.remove("secrets.json")
        return

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )
        page = await context.new_page()

        for i, row in enumerate(data_rows, start=2):
            if not row or len(row) < 1: continue
            url = row[0].strip()
            region = row[1].strip() if len(row) > 1 else "지역미정"
            if not url or "http" not in url: continue

            print(f">>> [{region}] 크롤링 중: {url}")
            
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=40000)
                await page.wait_for_selector(".item_title", timeout=15000)
                await asyncio.sleep(3)

                hotel_name = (await page.locator(".item_title").first.inner_text()).strip()
                
                price_text = await page.locator(".ly_wrap .price").first.inner_text()
                price_raw = "".join(filter(str.isdigit, price_text))
                price = int(price_raw) if price_raw else 0
                
                img_el = page.locator(".htl_photo img").first
                image_url = await img_el.get_attribute("src")
                
                rating_raw = (await page.locator(".score_htl_wrap .star").first.inner_text()).strip()
                rating = float(rating_raw) if rating_raw else 0.0
                
                review_text = await page.locator(".score_htl_wrap em").first.inner_text()
                review_raw = "".join(filter(str.isdigit, review_text))
                review_count = int(review_raw) if review_raw else 0
                
                product_id = hashlib.md5(hotel_name.encode()).hexdigest()[:8]

                extracted_data = [[product_id, hotel_name, price, url, image_url, region, review_count, rating]]

                for t_id in TARGET_SHEET_IDS:
                    try:
                        doc = gc.open_by_key(t_id)
                        try:
                            target_ws = doc.worksheet(WRITE_TAB_NAME)
                        except gspread.exceptions.WorksheetNotFound:
                            target_ws = doc.add_worksheet(title=WRITE_TAB_NAME, rows="1000", cols="20")
                            print(f"    💡 [{doc.title}]에 '{WRITE_TAB_NAME}' 탭 생성 완료")
                        
                        target_ws.update(f"A{i}:H{i}", extracted_data, value_input_option="USER_ENTERED")
                    except Exception as e:
                        print(f"    ⚠️ 업데이트 에러 (ID: {t_id}): {e}")

                print(f"    ✅ 완료: {hotel_name}")

            except Exception as e:
                print(f"    ❌ 실패 [{url}]: {e}")
                continue

        await browser.close()

    if json_raw and os.path.exists("secrets.json"):
        os.remove("secrets.json")

if __name__ == "__main__":
    asyncio.run(run_hotel_crawling())
