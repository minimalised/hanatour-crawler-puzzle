import os
import json
import asyncio
import hashlib
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from playwright.async_api import async_playwright

async def run_crawler():
    print("🌐 구글 API 인증 및 스프레드시트 연결 중...")
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    
    # [최신 표준 안정화] 환경 변수에서 JSON 텍스트를 직접 읽어 메모리에서 바로 인증 (물리 파일 생성 X)
    json_raw = os.environ.get("GOOGLE_JSON_RAW")
    
    try:
        if json_raw:
            # GitHub Actions 환경: 환경 변수를 딕셔너리로 파싱하여 직접 인증
            service_account_info = json.loads(json_raw)
            creds = Credentials.from_service_account_info(service_account_info, scopes=scopes)
        else:
            # 로컬 개발 환경: 기존처럼 프로젝트 내 secrets.json 파일 참조
            creds = Credentials.from_service_account_file('secrets.json', scopes=scopes)
            
        gc = gspread.authorize(creds)
    except Exception as auth_error:
        print(f"❌ 구글 API 인증 실패: {auth_error}")
        return
    
    source_spreadsheet_id = "1mH51VHs4y0FgClkUBvZgw7oY3Yv7gQBA_a3um9uhX0I"
    source_sheet_name = "지방출발리스트"
    target_sheet_name = "github_local"
    
    # ------------------ URL 로드부 ------------------
    print(f"🌐 스프레드시트에서 {source_sheet_name} URL 리스트를 불러오는 중...")
    try:
        source_doc = gc.open_by_key(source_spreadsheet_id)
        source_sheet = source_doc.worksheet(source_sheet_name)
        raw_urls = source_sheet.col_values(1)  
        
        url_list = [url for url in raw_urls if url.startswith("http")]
        print(f"✅ 총 {len(url_list)}개의 URL을 확보했습니다.")
    except Exception as e:
        print(f"❌ URL 리스트를 가져오는 중 에러 발생 (시트명: {source_sheet_name}): {e}")
        return

    # ------------------ 크롤링 실행부 ------------------
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={'width': 1280, 'height': 1024},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )
        page = await context.new_page()

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

                            title_el = await main_info.query_selector(".item_title")
                            title = (await title_el.inner_text()).strip() if title_el else "제목 없음"

                            price_el = await main_info.query_selector(".price")
                            price_raw = await price_el.inner_text() if price_el else "0"
                            price = "".join(filter(str.isdigit, price_raw))

                            star_el = await main_info.query_selector(".icn.star")
                            if star_el:
                                star_text = await star_el.inner_text()
                                rating = star_text.split('(')[0].strip()
                                review_count_el = await star_el.query_selector("em")
                                review_count = await review_count_el.inner_text() if review_count_el else "0"
                                review_count = "".join(filter(str.isdigit, review_count))
                            else:
                                rating = "0"
                                review_count = "0"

                            img_el = await img_check.query_selector("img")
                            img_url = await img_el.get_attribute("src") if img_el else ""
                            if img_url and img_url.startswith("//"): 
                                img_url = "https:" + img_url

                            product_id = hashlib.md5(title.encode()).hexdigest()[:8]
                            final_url = f"{current_url}"

                            all_products.append({
                                "ID": product_id,
                                "상품명": title,
                                "가격": int(price) if price else 0,
                                "URL": final_url,
                                "이미지URL": img_url,
                                "지역": region_name,
                                "리뷰수": int(review_count) if review_count else 0,
                                "평점": float(rating) if rating else 0.0,
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

        # ------------------ 구글 시트 적재부 ------------------
        if all_products:
            print(f"\n🚀 결과 스프레드시트 업데이트 시작 (대상 시트: {target_sheet_name})...")
            target_spreadsheet_ids = [
                "1mH51VHs4y0FgClkUBvZgw7oY3Yv7gQBA_a3um9uhX0I",
                "1JgWk9PYT6LG_1GnPdpVY0mZavcHXDWRSrzdE0lVmjj4",
                "1Hoq0N88mestsHXbIOjwue3OctXf7dvKkx99eieYFhAY",
                "1BK4xUHQFrLjLTn6vE0jSuwqMvSU7ZMKIV-nPvmySPx8"
            ]

            try:
                df = pd.DataFrame(all_products)
                column_order = ["ID", "상품명", "가격", "URL", "이미지URL", "지역", "리뷰수", "평점"]
                df = df[column_order]
                data_to_upload = [df.columns.values.tolist()] + df.values.tolist()

                for spreadsheet_id in target_spreadsheet_ids:
                    try:
                        doc = gc.open_by_key(spreadsheet_id)
                        
                        try:
                            sheet = doc.worksheet(target_sheet_name)
                        except gspread.exceptions.WorksheetNotFound:
                            print(f"ℹ️ {doc.title}에 '{target_sheet_name}' 시트가 없어 새로 생성합니다.")
                            sheet = doc.add_worksheet(title=target_sheet_name, rows="100", cols="10")
                        
                        sheet.clear()
                        
                        # [최신 표준 안정화] 최신 버전에 맞춰 range_name과 values 명시적 파라미터 적용
                        sheet.update(range_name='A1', values=data_to_upload)
                        print(f"✅ 성공: [{doc.title}] '{target_sheet_name}' 업데이트 완료")
                    except Exception as sheet_error:
                        print(f"⚠️ {spreadsheet_id} 업데이트 실패: {sheet_error}")

            except Exception as e:
                print(f"❌ 구글 시트 결과 적재 에러: {e}")
        
        await browser.close()

if __name__ == "__main__":
    asyncio.run(run_crawler())
