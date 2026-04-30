import asyncio
import hashlib
import pandas as pd
import gspread
import re
from google.oauth2.service_account import Credentials
from playwright.async_api import async_playwright

async def run_cruise_crawler():
    async with async_playwright() as p:
        # 브라우저 실행 (GitHub Actions 및 일반 환경 최적화)
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={'width': 1280, 'height': 1024},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )
        page = await context.new_page()

        # 수집할 URL 리스트
        url_list = [
            "https://puzzle.hanatour.com/promotion/plan/PM00690233AA",
            "https://puzzle.hanatour.com/promotion/plan/PM00682317A5",
            "https://puzzle.hanatour.com/promotion/plan/PM006674499A",
            "https://puzzle.hanatour.com/promotion/plan/PM00667583D5",
            "https://puzzle.hanatour.com/promotion/plan/PM0066857B4C",
            "https://puzzle.hanatour.com/promotion/plan/PM0066858D10",
            "https://puzzle.hanatour.com/package/major-products?rprsProdCds=MHH1138,MHA1029,MHE1094,MHW1088,MHH1139,MEW1255,MEE1104"
        ]

        all_products = []

        for current_url in url_list:
            try:
                print(f"🌐 페이지 접속 중: {current_url}")
                await page.goto(current_url, wait_until="networkidle", timeout=60000)
                
                # 1. 지역명 추출 (페이지 상단 탭 또는 타이틀)
                try:
                    region_name = await page.inner_text(".promo_menu.on span, strong.tit a.js_show, .tit_area .tit")
                    region_name = region_name.strip()
                except:
                    region_name = "기타 크루즈"

                # 2. 모든 유형의 상품 카드(.card-wrap) 추출
                product_cards = await page.query_selector_all(".card-wrap")
                
                count = 0
                for card in product_cards:
                    try:
                        # [핵심] 3. 가격 태그 내부의 strong 존재 여부로 배너와 상품 구분
                        price_el = await card.query_selector(".price strong")
                        if not price_el:
                            continue # 가격 숫자가 없는 배너는 건너뜀

                        price_raw = await price_el.inner_text()
                        price = "".join(filter(str.isdigit, price_raw))
                        
                        if not price or int(price) == 0:
                            continue # 가격이 0원인 요소도 건너뜀

                        # 4. 상품명 추출
                        title_el = await card.query_selector(".text-group .eps2")
                        if not title_el: continue
                        title = (await title_el.inner_text()).strip()
                        # 줄바꿈 및 불필요한 공백 제거
                        title = re.sub(r'\s+', ' ', title)

                        # 5. 이미지 URL 추출
                        img_el = await card.query_selector(".img-group img")
                        img_url = ""
                        if img_el:
                            img_url = await img_el.get_attribute("src") or await img_el.get_attribute("data-src")
                        
                        if img_url and img_url.startswith("//"):
                            img_url = "https:" + img_url

                        # 6. 고유 ID 생성 (URL 결합 없음)
                        product_id = hashlib.md5(title.encode()).hexdigest()[:8]

                        all_products.append({
                            "지역": region_name,
                            "상품명": title,
                            "가격": int(price),
                            "이미지URL": img_url,
                            "URL": current_url, # pID 제거됨
                            "ID": product_id,
                            "상품유형": "크루즈"
                        })
                        count += 1

                    except Exception as e:
                        continue

                print(f"✅ {region_name} 수집 완료: {count}개 상품 (배너 제외)")
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
