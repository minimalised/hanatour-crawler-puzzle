import asyncio
import hashlib
import pandas as pd
import gspread
import re
from google.oauth2.service_account import Credentials
from playwright.async_api import async_playwright

async def run_cruise_crawler():
    # 1. 구글 스프레드시트에서 URL 리스트 가져오기
    print("🌐 [프로모션크루즈상품리스트] 시트에서 URL을 불러오는 중...")
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_file('secrets.json', scopes=scopes)
    gc = gspread.authorize(creds)
    
    source_spreadsheet_id = "1mH51VHs4y0FgClkUBvZgw7oY3Yv7gQBA_a3um9uhX0I"
    try:
        source_doc = gc.open_by_key(source_spreadsheet_id)
        source_sheet = source_doc.worksheet("프로모션크루즈상품리스트")
        raw_urls = source_sheet.col_values(1)
        # http로 시작하는 유효한 URL만 추출
        url_list = [url.strip() for url in raw_urls if url.strip().startswith("http")]
        print(f"✅ 총 {len(url_list)}개의 프로모션 크루즈 URL을 확보했습니다.")
    except Exception as e:
        print(f"❌ URL 리스트 로드 중 에러 발생: {e}")
        return

    # 2. Playwright 설정 및 실행
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={'width': 1280, 'height': 2000},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )
        page = await context.new_page()

        all_products = []

        # 3. URL 리스트 순회
        for current_url in url_list:
            try:
                print(f"🌐 페이지 접속 중: {current_url}")
                await page.goto(current_url, wait_until="networkidle", timeout=60000)
                
                main_title = "크루즈 기획전"
                title_el = await page.query_selector(".tit_area .tit, .title_group .tit, h3.tit")
                if title_el:
                    main_title = (await title_el.inner_text()).strip()
                else:
                    img_tit_el = await page.query_selector(".key_visual img")
                    if img_tit_el:
                        main_title = await img_tit_el.get_attribute("alt") or "크루즈 기획전"

                tab_buttons = await page.query_selector_all(".promo_tabmenu_base .promo_menu")
                loop_targets = tab_buttons if tab_buttons and len(tab_buttons) > 0 else [None]

                for btn in loop_targets:
                    tab_name = ""
                    if btn:
                        tab_name = (await btn.inner_text()).strip()
                        class_attr = await btn.get_attribute("class")
                        if "on" not in (class_attr or ""):
                            await btn.click()
                            await asyncio.sleep(1.5)
                            try: await page.wait_for_load_state("networkidle", timeout=5000)
                            except: pass

                    for _ in range(3):
                        await page.mouse.wheel(0, 1500)
                        await asyncio.sleep(0.7)

                    product_sections = await page.query_selector_all("div[componenttype='pr-product-list'], .card-list-wrap")
                    
                    page_count = 0
                    for section in product_sections:
                        is_related = await section.evaluate("node => !!node.closest('.related')")
                        if is_related: continue

                        cards = await section.query_selector_all(".card-wrap")
                        for card in cards:
                            if not await card.is_visible(): continue

                            try:
                                title_el = await card.query_selector(".text-group .eps2")
                                if not title_el: continue
                                title = " ".join((await title_el.text_content()).split())

                                price_el = await card.query_selector(".price strong")
                                if not price_el: continue
                                price_text = await price_el.text_content()
                                price = "".join(re.findall(r'\d+', price_text))
                                if not price: continue

                                img_el = await card.query_selector(".img-group img")
                                img_url = ""
                                if img_el:
                                    img_url = await img_el.get_attribute("src") or await img_el.get_attribute("data-src")
                                if img_url and img_url.startswith("//"):
                                    img_url = "https:" + img_url

                                display_region = f"{main_title} > {tab_name}" if tab_name else main_title

                                all_products.append({
                                    "지역": display_region,
                                    "상품명": title,
                                    "가격": int(price),
                                    "이미지URL": img_url,
                                    "URL": current_url,
                                    "ID": hashlib.md5(title.encode()).hexdigest()[:8],
                                    "상품유형": "크루즈"
                                })
                                page_count += 1
                            except:
                                continue
                    
                    print(f"    └ [{tab_name if tab_name else '기본 섹션'}]: {page_count}개 상품 수집")

            except Exception as e:
                print(f"❌ {current_url} 처리 실패: {e}")

        # 4. 데이터 적재
        if all_products:
            print(f"\n🚀 총 {len(all_products)}개 데이터 적재 시작...")
            target_ids = [
                "1mH51VHs4y0FgClkUBvZgw7oY3Yv7gQBA_a3um9uhX0I",
                "1JgWk9PYT6LG_1GnPdpVY0mZavcHXDWRSrzdE0lVmjj4",
                "1Hoq0N88mestsHXbIOjwue3OctXf7dvKkx99eieYFhAY",
                "1BK4xUHQFrLjLTn6vE0jSuwqMvSU7ZMKIV-nPvmySPx8"
            ]
            
            df = pd.DataFrame(all_products).drop_duplicates(['ID'])
            data_to_upload = [df.columns.values.tolist()] + df.values.tolist()

            for sid in target_ids:
                try:
                    doc = gc.open_by_key(sid)
                    try:
                        sheet = doc.worksheet("github_promotion_cruise")
                    except gspread.exceptions.WorksheetNotFound:
                        # 시트가 없을 경우 생성
                        sheet = doc.add_worksheet(title="github_promotion_cruise", rows="1000", cols="10")
                    
                    sheet.clear()
                    sheet.update(range_name='A1', values=data_to_upload)
                    print(f"✅ [{doc.title}] 업데이트 성공")
                except Exception as e:
                    print(f"⚠️ 시트 업데이트 실패 ({sid}): {e}")
        else:
            print("❗ 수집된 데이터가 없어 적재를 중단합니다.")
        
        await browser.close()

if __name__ == "__main__":
    asyncio.run(run_cruise_crawler())
