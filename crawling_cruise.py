import asyncio
import hashlib
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from playwright.async_api import async_playwright

async def run_crawler():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={'width': 1280, 'height': 1024},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )
        page = await context.new_page()

        # 수집할 URL 리스트를 여기에 추가하세요
        url_list = [
"https://puzzle.hanatour.com/package/major-products?rprsProdCds=MJ11080&cityNm=%EC%9D%B4%EC%8A%A4%ED%84%B4%ED%81%AC%EB%A3%A8%EC%A6%88"
        ]

        all_products = []

        for current_url in url_list:
            try:
                await page.goto(current_url, wait_until="domcontentloaded", timeout=60000)
                
                try:
                    await page.wait_for_selector("a.js_show", timeout=10000)
                    region_name = (await page.inner_text("a.js_show")).strip()
                except:
                    region_name = "지역명 미상"

                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                await asyncio.sleep(2)

                try:
                    final_items = await page.query_selector_all(".prod_list_wrap ul.type > li")
                    for item in final_items:
                        try:
                            main_info = await item.query_selector(":scope > .inr.right")
                            img_check = await item.query_selector(":scope > .inr.img")
                            
                            if not main_info or not img_check:
                                continue

                            # 1. 상품명 추출
                            title_el = await main_info.query_selector(".item_title")
                            title = (await title_el.inner_text()).strip() if title_el else "제목 없음"

                            # 2. 가격 추출
                            price_el = await main_info.query_selector(".price")
                            price_raw = await price_el.inner_text() if price_el else "0"
                            price = "".join(filter(str.isdigit, price_raw))

                            # 3. 평점 및 리뷰 수 추출 (추가된 부분)
                            star_el = await main_info.query_selector(".icn.star")
                            if star_el:
                                # 전체 텍스트(예: "4.8(100)")를 가져온 후 전처리
                                star_text = await star_el.inner_text()
                                # 평점: 숫자와 소수점만 추출 (예: 4.8)
                                rating = star_text.split('(')[0].strip()
                                # 리뷰 수: 괄호 안의 숫자만 추출 (예: 100)
                                review_count_el = await star_el.query_selector("em")
                                review_count = await review_count_el.inner_text() if review_count_el else "0"
                                review_count = "".join(filter(str.isdigit, review_count))
                            else:
                                rating = "0"
                                review_count = "0"

                            # 4. 이미지 URL 추출
                            img_el = await img_check.query_selector("img")
                            img_url = await img_el.get_attribute("src") if img_el else ""
                            if img_url and img_url.startswith("//"): 
                                img_url = "https:" + img_url

                            # 5. 고유 ID 생성
                            product_id = hashlib.md5(title.encode()).hexdigest()[:8]

                            # 6. URL 조합
                            final_url = f"{current_url}&pID={product_id}"

                            all_products.append({
                                "ID": product_id,
                                "지역": region_name,
                                "상품명": title,
                                "가격": int(price) if price else 0,
                                "평점": float(rating) if rating else 0.0,
                                "리뷰수": int(review_count) if review_count else 0,
                                "이미지URL": img_url,
                                "URL": final_url
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

        # 스프레드시트 적재
        if all_products:
            print("\n🚀 스프레드시트 업데이트 시작...")
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

                # 스프레드시트 컬럼 순서 업데이트
                df = pd.DataFrame(all_products)
                column_order = ["지역", "상품명", "가격", "평점", "리뷰수", "이미지URL", "URL", "ID"]
                df = df[column_order]
                
                # 물리적 삭제 없이 모든 행(지역별 중복 포함) 적재
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
