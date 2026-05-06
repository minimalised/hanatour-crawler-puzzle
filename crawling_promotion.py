import asyncio
import hashlib
import pandas as pd
import gspread
import re
from google.oauth2.service_account import Credentials
from playwright.async_api import async_playwright

async def run_promotion_crawler():
    async with async_playwright() as p:
        # 1. 브라우저 설정 및 실행
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={'width': 1280, 'height': 2000},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )

        # [수정] 수집하고자 하는 URL 리스트를 이곳에 추가하세요
        target_urls = [
            "https://puzzle.hanatour.com/promotion/plan/PM0069CD3D4B",
            "https://puzzle.hanatour.com/promotion/plan/PM0067C86FE5",
            "https://puzzle.hanatour.com/promotion/plan/PM00667C3E4E",
            "https://puzzle.hanatour.com/promotion/plan/PM0000114930"
        ]
        
        all_products = []

        # 2. URL 리스트 순회 시작
        for target_url in target_urls:
            page = await context.new_page()
            try:
                print(f"🌐 페이지 접속 시도: {target_url}")
                
                # 네트워크 대기 시간 조절 및 접속
                await page.goto(target_url, wait_until="domcontentloaded", timeout=90000)
                
                # 주요 요소 로드 대기 (최대 15초)
                try:
                    await page.wait_for_selector(".card-wrap", timeout=15000)
                except:
                    print(f"⚠️ {target_url}: 상품 카드가 즉시 로드되지 않아 스크롤을 진행합니다.")

                # 페이지별 메인 타이틀 추출
                main_title = "프로모션"
                title_el = await page.query_selector(".tit_area .tit, .title_group .tit, h3.tit")
                if title_el:
                    main_title = (await title_el.inner_text()).strip()

                # 탭 메뉴 확인
                tab_buttons = await page.query_selector_all(".promo_tabmenu_base .promo_menu")
                loop_targets = tab_buttons if tab_buttons and len(tab_buttons) > 0 else [None]

                for btn in loop_targets:
                    tab_name = ""
                    if btn:
                        tab_name = (await btn.inner_text()).strip()
                        class_attr = await btn.get_attribute("class")
                        # 탭이 비활성 상태면 클릭
                        if "on" not in (class_attr or ""):
                            await btn.click()
                            await asyncio.sleep(2.5) 

                    # 무한 스크롤 대응 (데이터 렌더링 유도)
                    for _ in range(4):
                        await page.mouse.wheel(0, 2000)
                        await asyncio.sleep(1.0)

                    # 상품 섹션 탐색
                    product_sections = await page.query_selector_all("div[componenttype='pr-product-list'], .card-list-wrap")
                    
                    tab_count = 0
                    for section in product_sections:
                        # 관련 상품 섹션 제외
                        is_related = await section.evaluate("node => !!node.closest('.related')")
                        if is_related: continue

                        cards = await section.query_selector_all(".card-wrap")
                        for card in cards:
                            if not await card.is_visible(): continue
                            try:
                                # 상품명 추출
                                name_el = await card.query_selector(".text-group .eps2")
                                if not name_el: continue
                                title = " ".join((await name_el.text_content()).split())

                                # 가격 추출
                                price_el = await card.query_selector(".price strong")
                                price_val = 0
                                if price_el:
                                    price_text = await price_el.text_content()
                                    price_digits = "".join(re.findall(r'\d+', price_text))
                                    price_val = int(price_digits) if price_digits else 0

                                # 이미지 URL 추출
                                img_el = await card.query_selector(".img-group img")
                                img_url = ""
                                if img_el:
                                    img_url = await img_el.get_attribute("src") or await img_el.get_attribute("data-src")
                                if img_url:
                                    img_url = img_url.strip()
                                    if img_url.startswith("//"): img_url = "https:" + img_url

                                # 데이터 누적
                                all_products.append({
                                    "지역": f"{main_title} > {tab_name}" if tab_name else main_title,
                                    "상품명": title,
                                    "가격": price_val,
                                    "이미지URL": img_url,
                                    "URL": target_url,
                                    # ID 중복 방지를 위해 URL과 타이틀 조합
                                    "ID": hashlib.md5((target_url + title).encode()).hexdigest()[:8],
                                    "상품유형": "유류할증프로모션"
                                })
                                tab_count += 1
                            except Exception:
                                continue
                    
                    print(f"   └ [{tab_name if tab_name else '기본'}]: {tab_count}개 수집 완료")

            except Exception as e:
                print(f"❌ {target_url} 처리 중 오류 발생: {e}")
            finally:
                await page.close() # 페이지 탭 닫기

        # 3. 구글 시트 적재
        if all_products:
            df = pd.DataFrame(all_products).drop_duplicates(['ID'])
            print(f"\n🚀 총 {len(df)}개 유니크 데이터 적재 시작...")
            
            target_ids = [
                "1mH51VHs4y0FgClkUBvZgw7oY3Yv7gQBA_a3um9uhX0I",
                "1JgWk9PYT6LG_1GnPdpVY0mZavcHXDWRSrzdE0lVmjj4",
                "1Hoq0N88mestsHXbIOjwue3OctXf7dvKkx99eieYFhAY",
                "1BK4xUHQFrLjLTn6vE0jSuwqMvSU7ZMKIV-nPvmySPx8"
            ]
            
            try:
                creds = Credentials.from_service_account_file(
                    'secrets.json', 
                    scopes=["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
                )
                gc = gspread.authorize(creds)
                
                # 헤더 포함 데이터 리스트 변환
                data_to_upload = [df.columns.values.tolist()] + df.values.tolist()

                for sid in target_ids:
                    try:
                        doc = gc.open_by_key(sid)
                        try:
                            sheet = doc.worksheet("github_promotion")
                        except:
                            sheet = doc.add_worksheet(title="github_promotion", rows="1000", cols="10")
                        
                        sheet.clear()
                        sheet.update(range_name='A1', values=data_to_upload)
                        print(f"✅ [{doc.title}] 업데이트 성공")
                    except Exception as e:
                        print(f"⚠️ 시트 업데이트 실패 ({sid}): {e}")
            except Exception as e:
                print(f"❌ 구글 인증 에러: {e}")
        else:
            print("❗ 수집된 데이터가 없어 적재를 중단합니다.")
        
        await browser.close()

if __name__ == "__main__":
    asyncio.run(run_promotion_crawler())
