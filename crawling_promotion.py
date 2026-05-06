import asyncio
import hashlib
import pandas as pd
import gspread
import re
from google.oauth2.service_account import Credentials
from playwright.async_api import async_playwright

async def run_promotion_crawler():
    async with async_playwright() as p:
        # 브라우저 실행
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={'width': 1280, 'height': 2000},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )
        page = await context.new_page()

        # 대상 URL (유류할증 프로모션)
        target_url = "https://puzzle.hanatour.com/promotion/plan/PM0069CD3D4B"
        all_products = []

        try:
            print(f"🌐 페이지 접속 중: {target_url}")
            await page.goto(target_url, wait_until="networkidle", timeout=60000)
            
            # 1. 페이지 제목 추출
            main_title = "유류할증 프로모션"
            title_el = await page.query_selector(".tit_area .tit, .title_group .tit, h3.tit")
            if title_el:
                main_title = (await title_el.inner_text()).strip()

            # 2. 탭 메뉴 찾기
            tab_buttons = await page.query_selector_all(".promo_tabmenu_base .promo_menu")
            loop_targets = tab_buttons if tab_buttons and len(tab_buttons) > 0 else [None]

            for btn in loop_targets:
                tab_name = ""
                if btn:
                    tab_name = (await btn.inner_text()).strip()
                    class_attr = await btn.get_attribute("class")
                    if "on" not in (class_attr or ""):
                        await btn.click()
                        await asyncio.sleep(2) # 탭 클릭 후 렌더링 대기
                        try: await page.wait_for_load_state("networkidle", timeout=5000)
                        except: pass

                # 3. 상품 로딩을 위한 스크롤
                for _ in range(3):
                    await page.mouse.wheel(0, 2000)
                    await asyncio.sleep(0.8)

                # 4. 상품 데이터 수집
                product_sections = await page.query_selector_all("div[componenttype='pr-product-list'], .card-list-wrap")
                
                tab_count = 0
                for section in product_sections:
                    # 관련 기획전 섹션 제외
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
                                "가격": int(price) if price else 0,
                                "이미지URL": img_url,
                                "URL": target_url,
                                "ID": hashlib.md5(title.encode()).hexdigest()[:8],
                                "상품유형": "유류할증프로모션"
                            })
                            tab_count += 1
                        except Exception:
                            continue
                
                print(f"   └ [{tab_name if tab_name else '기본'}]: {tab_count}개 상품 발견")

        except Exception as e:
            print(f"❌ 처리 중 오류 발생: {e}")

        # 5. 구글 시트 데이터 적재
        if all_products:
            print(f"\n🚀 총 {len(all_products)}개 데이터(중복포함) 수집 완료. 적재 시작...")
            
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

                df = pd.DataFrame(all_products).drop_duplicates(['ID']) # ID 기준 중복 제거
                data_to_upload = [df.columns.values.tolist()] + df.values.tolist()

                for sid in target_ids:
                    try:
                        doc = gc.open_by_key(sid)
                        # 워크시트 이름 설정 (없으면 생성)
                        sheet_name = "github_promotion" 
                        try:
                            sheet = doc.worksheet(sheet_name)
                        except gspread.exceptions.WorksheetNotFound:
                            sheet = doc.add_worksheet(title=sheet_name, rows="1000", cols="10")
                        
                        sheet.clear()
                        sheet.update(range_name='A1', values=data_to_upload)
                        print(f"✅ [{doc.title}] 시트 업데이트 성공")
                    except Exception as e:
                        print(f"⚠️ 시트 실패 ({sid}): {e}")
            except Exception as e:
                print(f"❌ 구글 API 인증 에러: {e}")
        
        await browser.close()

if __name__ == "__main__":
    asyncio.run(run_promotion_crawler())
