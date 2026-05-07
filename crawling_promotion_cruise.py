import asyncio
import hashlib
import pandas as pd
import gspread
import re
from google.oauth2.service_account import Credentials
from playwright.async_api import async_playwright

async def run_cruise_crawler():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={'width': 1280, 'height': 2000},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )
        page = await context.new_page()

        url_list = [
            "https://puzzle.hanatour.com/promotion/plan/PM00690233AA",
            "https://puzzle.hanatour.com/promotion/plan/PM00682317A5",
            "https://puzzle.hanatour.com/promotion/plan/PM006674499A",
            "https://puzzle.hanatour.com/promotion/plan/PM00667583D5",
            "https://puzzle.hanatour.com/promotion/plan/PM0066857B4C",
            "https://puzzle.hanatour.com/promotion/plan/PM0066858D10"
        ]

        all_products = []

        for current_url in url_list:
            try:
                print(f"🌐 페이지 접속 중: {current_url}")
                await page.goto(current_url, wait_until="networkidle", timeout=60000)
                
                # 1. 페이지 제목 추출 보완 (이미지 alt 속성 대응)
                main_title = "크루즈 기획전"
                title_el = await page.query_selector(".tit_area .tit, .title_group .tit, h3.tit")
                if title_el:
                    main_title = (await title_el.inner_text()).strip()
                else:
                    img_tit_el = await page.query_selector(".key_visual img")
                    if img_tit_el:
                        main_title = await img_tit_el.get_attribute("alt") or "크루즈 기획전"

                # 2. 탭 메뉴 순회
                tab_buttons = await page.query_selector_all(".promo_tabmenu_base .promo_menu")
                loop_targets = tab_buttons if tab_buttons and len(tab_buttons) > 0 else [None]

                for btn in loop_targets:
                    tab_name = ""
                    if btn:
                        tab_name = (await btn.inner_text()).strip()
                        # 'on' 클래스가 이미 붙어있지 않은 경우에만 클릭
                        class_attr = await btn.get_attribute("class")
                        if "on" not in (class_attr or ""):
                            await btn.click()
                            await asyncio.sleep(1.5) # 기본 렌더링 대기
                            # 네트워크가 조용해질 때까지 추가 대기 (선택 사항)
                            try: await page.wait_for_load_state("networkidle", timeout=5000)
                            except: pass

                    # 3. 스크롤 로딩
                    for _ in range(3):
                        await page.mouse.wheel(0, 1500)
                        await asyncio.sleep(0.7)

                    # 4. 상품 카드 수집 (선택자 범용성 강화)
                    # 실제 상품 리스트 섹션들만 선택
                    product_sections = await page.query_selector_all("div[componenttype='pr-product-list'], .card-list-wrap")
                    
                    page_count = 0
                    for section in product_sections:
                        # '관련 기획전' 섹션 안에 있는 섹션은 건너뛰기
                        is_related = await section.evaluate("node => !!node.closest('.related')")
                        if is_related: continue

                        cards = await section.query_selector_all(".card-wrap")
                        for card in cards:
                            if not await card.is_visible(): continue

                            try:
                                # 상품명
                                title_el = await card.query_selector(".text-group .eps2")
                                if not title_el: continue
                                title = " ".join((await title_el.text_content()).split())

                                # 가격
                                price_el = await card.query_selector(".price strong")
                                if not price_el: continue
                                price_text = await price_el.text_content()
                                price = "".join(re.findall(r'\d+', price_text))
                                if not price: continue

                                # 이미지
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
                    
                    print(f"   └ [{tab_name if tab_name else '기본 섹션'}]: {page_count}개 상품 수집")

            except Exception as e:
                print(f"❌ {current_url} 처리 실패: {e}")

        # 5. 데이터 적재
        if all_products:
            print(f"\n🚀 총 {len(all_products)}개 데이터 적재 시작...")
            target_ids = [
                "1mH51VHs4y0FgClkUBvZgw7oY3Yv7gQBA_a3um9uhX0I",
                "1JgWk9PYT6LG_1GnPdpVY0mZavcHXDWRSrzdE0lVmjj4",
                "1Hoq0N88mestsHXbIOjwue3OctXf7dvKkx99eieYFhAY",
                "1BK4xUHQFrLjLTn6vE0jSuwqMvSU7ZMKIV-nPvmySPx8"
            ]
            
            try:
                scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
                creds = Credentials.from_service_account_file('secrets.json', scopes=scopes)
                gc = gspread.authorize(creds)

                df = pd.DataFrame(all_products).drop_duplicates(['ID']) # 중복 제거
                data_to_upload = [df.columns.values.tolist()] + df.values.tolist()

                for sid in target_ids:
                    try:
                        doc = gc.open_by_key(sid)
                        try:
                            sheet = doc.worksheet("github_promotion_cruise")
                        except gspread.exceptions.WorksheetNotFound:
                            sheet = doc.add_worksheet(title="github_cruise", rows="1000", cols="10")
                        
                        sheet.clear()
                        # 최신 gspread 업데이트 방식 대응
                        sheet.update(range_name='A1', values=data_to_upload)
                        print(f"✅ [{doc.title}] 업데이트 성공")
                    except Exception as e:
                        print(f"⚠️ 시트 실패 ({sid}): {e}")
            except Exception as e:
                print(f"❌ 구글 시트 에러: {e}")
        
        await browser.close()

if __name__ == "__main__":
    asyncio.run(run_cruise_crawler())
