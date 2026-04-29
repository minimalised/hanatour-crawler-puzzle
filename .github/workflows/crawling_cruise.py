import asyncio
import hashlib
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from playwright.async_api import async_playwright

async def run_cruise_crawler():
    async with async_playwright() as p:
        # 브라우저 실행 (GitHub Actions 환경 최적화)
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={'width': 1280, 'height': 1024},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )
        page = await context.new_page()

        # 수집할 URL 리스트 (프로모션 페이지 및 검색 결과 페이지 혼합 가능)
        url_list = [
            "https://puzzle.hanatour.com/promotion/plan/PM00690233AA",
"https://puzzle.hanatour.com/promotion/plan/PM00682317A5",
"https://puzzle.hanatour.com/promotion/plan/PM006674499A",
"https://puzzle.hanatour.com/promotion/plan/PM00667583D5",
"https://puzzle.hanatour.com/promotion/plan/PM0066857B4C",
"https://puzzle.hanatour.com/promotion/plan/PM0066858D10",
"https://puzzle.hanatour.com/package/major-products?rprsProdCds=MHH1138,MHA1029,MHE1094,MHW1088,MHH1139,MEW1255,MEE1104", # 프로모션 타입
            # "여기에 다른 검색 결과 URL을 추가하세요", # 검색 결과 타입
        ]

        all_products = []

        for current_url in url_list:
            try:
                print(f"🌐 페이지 접속 중: {current_url}")
                # 네트워크가 안정될 때까지 대기
                await page.goto(current_url, wait_until="networkidle", timeout=60000)
                
                # 1. 지역명 추출 (두 가지 페이지 타입 대응)
                # 프로모션 페이지의 활성화된 탭 OR 검색 결과 페이지의 상단 지역명
                try:
                    region_name = await page.inner_text(".promo_menu.on span, strong.tit a.js_show")
                    region_name = region_name.strip()
                except:
                    region_name = "기타 크루즈"

                # 2. 상품 카드 요소 추출 (두 가지 페이지 타입 대응)
                # .card-wrap (프로모션) 또는 .prod_list_wrap 내 li (검색결과)
                product_cards = await page.query_selector_all(".card-wrap, .prod_list_wrap ul.type > li")
                
                for card in product_cards:
                    try:
                        # 3. 상품명 추출
                        # .text-group .eps2 (프로모션) 또는 .item_title (검색결과)
                        title_el = await card.query_selector(".text-group .eps2, .item_title")
                        if not title_el: continue
                        title = (await title_el.inner_text()).strip()

                        # 4. 가격 추출 (숫자만 추출하므로 .price 클래스 공통 대응)
                        price_el = await card.query_selector(".price")
                        price_raw = await price_el.inner_text() if price_el else "0"
                        price = "".join(filter(str.isdigit, price_raw))

                        # 5. 이미지 URL 추출 (Lazy 로딩 대응)
                        # .img-group img (프로모션) 또는 .inr.img img (검색결과)
                        img_el = await card.query_selector(".img-group img, .inr.img img")
                        img_url = ""
                        if img_el:
                            img_url = await img_el.get_attribute("src") or await img_el.get_attribute("data-src")
                        
                        if img_url and img_url.startswith("//"):
                            img_url = "https:" + img_url

                        # 6. 고유 ID 및 URL 조합
                        product_id = hashlib.md5(title.encode()).hexdigest()[:8]
                        # 네이버 쇼핑 등 외부 활용을 위해 pID 파라미터 강제 부여
                        final_url = f"{current_url}{'&' if '?' in current_url else '?'}pID={product_id}"

                        all_products.append({
                            "지역": region_name,
                            "상품명": title,
                            "가격": int(price) if price else 0,
                            "이미지URL": img_url,
                            "URL": final_url,
                            "ID": product_id,
                            "상품유형": "크루즈"
                        })
                    except Exception as e:
                        print(f"⚠️ 개별 상품 파싱 에러: {e}")
                        continue

                print(f"✅ {region_name} 수집 완료: {len(product_cards)}개")
                await asyncio.sleep(1)

            except Exception as e:
                print(f"❌ {current_url} 접속 에러: {e}")
                continue

        # 7. 구글 스프레드시트 적재
        if all_products:
            print(f"\n🚀 총 {len(all_products)}개 데이터 시트 적재 시작...")
            target_spreadsheet_ids = [
                "1mH51VHs4y0FgClkUBvZgw7oY3Yv7gQBA_a3um9uhX0I",
                "1JgWk9PYT6LG_1GnPdpVY0mZavcHXDWRSrzdE0lVmjj4",
                "1Hoq0N88mestsHXbIOjwue3OctXf7dvKkx99eieYFhAY",
                "1BK4xUHQFrLjLTn6vE0jSuwqMvSU7ZMKIV-nPvmySPx8"
            ]
            worksheet_name = "github_cruise"

            try:
                scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
                creds = Credentials.from_service_account_file('secrets.json', scopes=scopes)
                gc = gspread.authorize(creds)

                df = pd.DataFrame(all_products)
                column_order = ["지역", "상품명", "가격", "이미지URL", "URL", "ID", "상품유형"]
                df = df[column_order]
                data_to_upload = [df.columns.values.tolist()] + df.values.tolist()

                for spreadsheet_id in target_spreadsheet_ids:
                    try:
                        doc = gc.open_by_key(spreadsheet_id)
                        # 시트가 없으면 자동 생성
                        try:
                            sheet = doc.worksheet(worksheet_name)
                        except gspread.exceptions.WorksheetNotFound:
                            sheet = doc.add_worksheet(title=worksheet_name, rows="1000", cols="10")
                        
                        sheet.clear()
                        sheet.update(data_to_upload)
                        print(f"✅ [{doc.title}] 업데이트 성공")
                    except Exception as e:
                        print(f"⚠️ 시트 업데이트 실패 ({spreadsheet_id}): {e}")

            except Exception as e:
                print(f"❌ 구글 시트 처리 중 에러: {e}")
        
        await browser.close()

if __name__ == "__main__":
    asyncio.run(run_cruise_crawler())
