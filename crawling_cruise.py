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
            viewport={'width': 1280, 'height': 2000}, # 높이를 키워 로딩 최적화
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
                # 네트워크 유휴 상태까지 대기
                await page.goto(current_url, wait_until="networkidle", timeout=60000)
                
                # 1. 페이지 제목(메인 지역명) 추출
                try:
                    main_title = await page.inner_text(".tit_area .tit, .title_group .tit, h3.tit, .key_visual img")
                    main_title = main_title.strip() if main_title else "크루즈 기획전"
                except:
                    main_title = "크루즈 기획전"

                # 2. 탭 메뉴 존재 여부 확인 (있으면 모든 탭 순회)
                tab_buttons = await page.query_selector_all(".promo_tabmenu_base .promo_menu")
                loop_targets = tab_buttons if tab_buttons else [None]

                for btn in loop_targets:
                    tab_name = ""
                    if btn:
                        tab_name = (await btn.inner_text()).strip()
                        await btn.click()
                        await asyncio.sleep(2) # 탭 클릭 후 렌더링 시간 확보

                    # 3. 동적 로딩 대응: 페이지를 아래로 스크롤하며 모든 섹션 로드
                    for _ in range(3):
                        await page.mouse.wheel(0, 1500)
                        await asyncio.sleep(0.5)

                    # 4. 상품 카드 수집 (실제 상품 리스트 섹션 내의 카드만 타겟팅)
                    # 하단 '관련 기획전'(.related) 섹션의 카드는 제외
                    product_sections = await page.query_selector_all("div[componenttype='pr-product-list']")
                    
                    page_count = 0
                    for section in product_sections:
                        cards = await section.query_selector_all(".card-wrap")
                        
                        for card in cards:
                            if not await card.is_visible(): continue

                            try:
                                # 상품명 (공백 제거 로직 강화)
                                title_el = await card.query_selector(".text-group .eps2")
                                if not title_el: continue
                                title = " ".join((await title_el.text_content()).split())

                                # 가격 (숫자만 추출)
                                price_el = await card.query_selector(".price strong")
                                if not price_el: continue
                                price = "".join(re.findall(r'\d+', await price_el.text_content()))
                                if not price: continue

                                # 이미지 (lazy loading 대응)
                                img_el = await card.query_selector(".img-group img")
                                img_url = ""
                                if img_el:
                                    img_url = await img_el.get_attribute("src") or await img_el.get_attribute("data-src")
                                if img_url and img_url.startswith("//"):
                                    img_url = "https:" + img_url

                                # 지역명 구성 (메인제목 + 탭이름)
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
                    
                    print(f"  └ [{tab_name if tab_name else '기본 섹션'}]: {page_count}개 상품 수집")

            except Exception as e:
                print(f"❌ {current_url} 처리 실패: {e}")

        # 5. 데이터 적재 (구글 시트)
        if all_products:
            print(f"\n🚀 총 {len(all_products)}개 상품 데이터 업로드 중...")
            # 스프레드시트 업데이트 로직 (기존 코드와 동일)
            # ... 생략 ...

        await browser.close()
