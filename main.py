import asyncio
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from playwright.async_api import async_playwright

async def run_crawler():
    async with async_playwright() as p:
        # 1. 브라우저 실행 (서버/자동화 환경을 위해 headless=True)
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={'width': 1280, 'height': 1024},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )
        page = await context.new_page()

        # 수집할 URL 리스트
        url_list = [
            "https://ydt.hanatour.com/package/major-products?cntryCd=TH&cityCd=BKK&depCityCd=JCN&cityNm=%EB%B0%A9%EC%BD%95",
            "https://ydt.hanatour.com/package/major-products?cntryCd=TH&cityCd=PYX&depCityCd=JCN&cityNm=%ED%8C%8C%ED%83%80%EC%95%BC"
            
        ]

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

                # 목표 상품 개수 추출
                try:
                    await page.wait_for_selector("span.count em", timeout=10000)
                    total_text = await page.inner_text("span.count em")
                    target_total = int("".join(filter(str.isdigit, total_text)))
                except:
                    print(f"⚠️ {region_name} 수집 건너뜀 (상품 수 확인 불가)")
                    continue

                print(f"📊 [{region_name}] 수집 중 (목표: {target_total}개)")

                # 스크롤 로딩
                last_count = 0
                retry_count = 0
                while True:
                    items = await page.query_selector_all(".prod_list_wrap ul.type > li")
                    current_count = len(items)
                    if current_count >= target_total: break
                    
                    await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    await asyncio.sleep(2)

                    if current_count == last_count:
                        retry_count += 1
                        await page.mouse.wheel(0, -500)
                        await asyncio.sleep(1)
                        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                        if retry_count >= 3: break
                    else:
                        retry_count = 0
                    last_count = current_count

                # 데이터 파싱
                final_items = await page.query_selector_all(".prod_list_wrap ul.type > li")
                for item in final_items:
                    try:
                        title_el = await item.query_selector(".item_title.eps3")
                        title = await title_el.inner_text() if title_el else "제목 없음"

                        price_el = await item.query_selector(".price")
                        price_raw = await price_el.inner_text() if price_el else "0"
                        price = "".join(filter(str.isdigit, price_raw))

                        img_el = await item.query_selector(".inr.img img")
                        img_url = await img_el.get_attribute("src") if img_el else ""
                        if img_url and img_url.startswith("//"): img_url = "https:" + img_url

                        all_products.append({
                            "지역": region_name,
                            "상품명": title.strip(),
                            "가격": int(price) if price else 0,
                            "이미지URL": img_url,
                            "URL": current_url
                        })
                    except: continue

                print(f"✅ {region_name} 완료 ({len(final_items)}개)")
                await asyncio.sleep(5)

            except Exception as e:
                print(f"❌ {current_url} 에러: {e}")
                continue

        # --------------------------------------------------
        # 구글 스프레드시트 적재 (수정된 섹션)
        # --------------------------------------------------
        if all_products:
            print("\n🚀 스프레드시트 업데이트 시작...")
            try:
                # 1. 인증 설정 (파일 이름은 secrets.json 고정)
                scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
                creds = Credentials.from_service_account_file('secrets.json', scopes=scopes)
                gc = gspread.authorize(creds)
                
                # 2. 본인의 시트 정보 입력 (매우 중요!)
                # 주소창에서 /d/ 뒤의 값을 복사해 넣으세요.
                spreadsheet_id = "1mH51VHs4y0FgClkUBvZgw7oY3Yv7gQBA_a3um9uhX0I" 
                # 데이터를 넣을 탭 이름을 입력하세요 (예: 'db' 또는 'Sheet1')
                worksheet_name = "github" 

                doc = gc.open_by_key(spreadsheet_id)
                sheet = doc.worksheet(worksheet_name)

                # 3. 데이터 준비 및 업로드
                df = pd.DataFrame(all_products)
                
                # 기존 내용 삭제
                sheet.clear()
                # 헤더와 데이터 함께 전송
                sheet.update([df.columns.values.tolist()] + df.values.tolist())
                
                print(f"\n🎉 성공! 총 {len(df)}개 데이터를 '{worksheet_name}' 시트에 저장했습니다.")
            
            except Exception as e:
                print(f"❌ 시트 저장 에러: {e}")
        
        await browser.close()

if __name__ == "__main__":
    asyncio.run(run_crawler())
