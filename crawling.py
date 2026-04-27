import asyncio
import hashlib
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from playwright.async_api import async_playwright

async def run_crawler():
    async with async_playwright() as p:
        # 1. 브라우저 실행
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={'width': 1280, 'height': 1024},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )
        page = await context.new_page()

        # 수집할 URL 리스트 (필요시 채워넣으세요)
        url_list = []

        all_products = []

        for current_url in url_list:
            try:
                await page.goto(current_url, wait_until="domcontentloaded", timeout=60000)
                
                # 지역명 추출
                try:
                    await page.wait_for_selector("a.js_show", timeout=10000)
                    region_name = (await page.inner_text("a.js_show")).strip()
                except:
                    region_name = "지역명 미상"

                # 스크롤 로딩
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                await asyncio.sleep(2)

                # --- 데이터 파싱 영역 ---
                try:
                    final_items = await page.query_selector_all(".prod_list_wrap ul.type > li")
                    for item in final_items:
                        try:
                            main_info = await item.query_selector(":scope > .inr.right")
                            img_check = await item.query_selector(":scope > .inr.img")
                            
                            if not main_info or not img_check:
                                continue

                            # 1. 상품명 추출 (해시태그 포함 전체 텍스트)
                            title_el = await main_info.query_selector(".item_title")
                            title = (await title_el.inner_text()).strip() if title_el else "제목 없음"

                            # 2. 가격 추출 (숫자만)
                            price_el = await main_info.query_selector(".price")
                            price_raw = await price_el.inner_text() if price_el else "0"
                            price = "".join(filter(str.isdigit, price_raw))

                            # 3. 이미지 URL 추출 (ID 생성의 보조 키로 활용)
                            img_el = await img_check.query_selector("img")
                            img_url = await img_el.get_attribute("src") if img_el else ""
                            if img_url and img_url.startswith("//"): 
                                img_url = "https:" + img_url

                            # 4. 고유 ID 생성 (가격 제외)
                            # 상품명 전체 + 이미지 파일명을 조합해 해싱 (가격이 변해도 ID 고정)
                            img_filename = img_url.split('/')[-1].split('?')[0] # 쿼리스트링 제외 파일명만
                            unique_key = f"{title}_{img_filename}"
                            product_id = hashlib.md5(unique_key.encode()).hexdigest()[:10]

                            all_products.append({
                                "ID": product_id,
                                "지역": region_name,
                                "상품명": title,
                                "가격": int(price) if price else 0,
                                "이미지URL": img_url,
                                "URL": current_url
                            })
                        except Exception as e:
                            print(f"개별 상품 파싱 에러: {e}")
                            continue
                except Exception as e:
                    print(f"파싱 리스트 획득 에러: {e}")

                print(f"✅ {region_name} 완료 ({len(all_products)}개 누적)")
                await asyncio.sleep(1)

            except Exception as e:
                print(f"❌ {current_url} 접속 에러: {e}")
                continue

        # --------------------------------------------------
        # 구글 스프레드시트 적재
        # --------------------------------------------------
        if all_products:
            print("\n🚀 스프레드시트 업데이트 시작...")
            target_spreadsheet_ids = [
                "1mH51VHs4y0FgClkUBvZgw7oY3Yv7gQBA_a3um9uhX0I",
                "1JgWk9PYT6LG_1GnPdpVY0mZavcHXDWRSrzdE0lVmjj4",
                "1Hoq0N88mestsHXbIOjwue3OctXf7dvKkx99eieYFhAY",
                "1BK4xUHQFrLjLTn6vE0jSuwqMvSU7ZMKIV-nPvmySPx8"
            ]
            worksheet_name = "github"

            try:
                scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
                creds = Credentials.from_service_account_file('secrets.json', scopes=scopes)
                gc = gspread.authorize(creds)

                df = pd.DataFrame(all_products)
                # 컬럼 순서 재배치 (지역, 상품명, 가격, 이미지URL, URL, ID)
                column_order = ["지역", "상품명", "가격", "이미지URL", "URL", "ID"]
                df = df[column_order]
                data_to_upload = [df.columns.values.tolist()] + df.values.tolist()

                for spreadsheet_id in target_spreadsheet_ids:
                    try:
                        doc = gc.open_by_key(spreadsheet_id)
                        sheet = doc.worksheet(worksheet_name)
                        sheet.clear()
                        sheet.update(data_to_upload)
                        print(f"✅ 성공: [{doc.title}] 업데이트 완료")
                    except Exception as sheet_error:
                        print(f"⚠️ {spreadsheet_id} 업데이트 실패: {sheet_error}")

            except Exception as e:
                print(f"❌ 구글 시트 처리 에러: {e}")
        
        await browser.close()

if __name__ == "__main__":
    asyncio.run(run_crawler())
