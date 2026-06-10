import os
import json
import asyncio
import re
import hashlib
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from playwright.async_api import async_playwright

SPREADSHEET_ID = "1mH51VHs4y0FgClkUBvZgw7oY3Yv7gQBA_a3um9uhX0I"

# ==========================================
# [함수 1] 구글 시트 연동 인스턴스 생성
# ==========================================
def get_gspread_client():
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    json_raw = os.environ.get("GOOGLE_JSON_RAW")
    if json_raw:
        return gspread.authorize(Credentials.from_service_account_info(json.loads(json_raw), scopes=scopes))
    return gspread.authorize(Credentials.from_service_account_file('secrets.json', scopes=scopes))


# ==========================================
# [함수 2] 메인 크롤러 및 데이터 파이프라인 엔진
# ==========================================
async def run_pipeline():
    gc = get_gspread_client()
    doc = gc.open_by_key(SPREADSHEET_ID)
    
    # -------------------------------------------------------------
    # 1. 구글 스프레드시트에서 타겟 URL 리스트 가져오기
    # -------------------------------------------------------------
    print("📥 [1단계] 타겟 상품리스트 URL 로드 중...")
    target_rows = doc.worksheet("상품리스트").get_all_values()[1:] # 헤더 제외
    target_tasks = []
    for r in target_rows:
        if r and r[0].startswith("http"):
            target_tasks.append({
                "url": r[0].strip(), 
                "region": r[1].strip(), 
                "airport": r[2].strip() if len(r) > 2 else "없음"
            })
            
    print(f"✅ 총 {len(target_tasks)}개의 크롤링 타겟 URL을 확보했습니다.")

    # -------------------------------------------------------------
    # 2. URL 리스트 순회 및 전수 크롤링 (Playwright)
    # -------------------------------------------------------------
    print("\n🕵️ [2단계] 전수 크롤링 및 실시간 스크롤 로딩 시작...")
    crawled_raw_products = []
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={'width': 1280, 'height': 1024},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )
        page = await context.new_page()

        for task in target_tasks:
            try:
                print(f"🔄 로딩 중: {task['region']} ({task['airport']})")
                await page.goto(task['url'], wait_until="domcontentloaded", timeout=30000)
                
                # 총 상품 갯수 동기화 및 스마트 스크롤 로딩
                total_count = 20
                try:
                    await page.wait_for_selector(".option_wrap.result .count em", timeout=5000)
                    count_el = await page.query_selector(".option_wrap.result .count em")
                    if count_el:
                        total_count = int("".join(filter(str.isdigit, await count_el.inner_text())))
                except: pass

                needed_scrolls = (total_count - 1) // 20
                for _ in range(needed_scrolls):
                    await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    await asyncio.sleep(1.5)

                # 페이지 내 엘리먼트 수집
                items = await page.query_selector_all(".prod_list_wrap ul.type > li")
                for item in items:
                    main_info = await item.query_selector(":scope > .inr.right")
                    img_check = await item.query_selector(":scope > .inr.img")
                    if not main_info: continue
                    
                    # 상품명 추출
                    title_el = await main_info.query_selector(".item_title")
                    full_title = (await title_el.inner_text()).strip() if title_el else "제목 없음"
                    
                    # 가격 추출
                    price_el = await main_info.query_selector(".price")
                    price_raw = await price_el.inner_text() if price_el else "0"
                    price = int("".join(filter(str.isdigit, price_raw))) if any(c.isdigit() for c in price_raw) else 0
                    
                    # 이미지 URL 추출 (bg_alpha 방어벽 적용)
                    img_url = ""
                    if img_check:
                        img_el = await img_check.query_selector("img")
                        if img_el:
                            data_src = await img_el.get_attribute("data-src")
                            src = await img_el.get_attribute("src")
                            potential_url = data_src if data_src else src
                            
                            if potential_url and "bg_alpha" not in potential_url:
                                img_url = potential_url.strip()
                            else:
                                all_imgs = await img_check.query_selector_all("img")
                                for im in all_imgs:
                                    i_src = await im.get_attribute("src")
                                    i_data = await im.get_attribute("data-src")
                                    target = i_data if i_data else i_src
                                    if target and "bg_alpha" not in target:
                                        img_url = target.strip()
                                        break
                    if img_url and img_url.startswith("//"): 
                        img_url = "https:" + img_url

                    # 💡 [ID 생성 규칙 가이드라인] 상품명 + 가격 + 출발공항 조합으로 유일한 고유 ID 키 정의
                    unique_str = f"{full_title}_{price}_{task['airport']}"
                    product_id = hashlib.md5(unique_str.encode('utf-8')).hexdigest()[:8]

                    # 수집 데이터 적재
                    crawled_raw_products.append({
                        "ID": product_id,
                        "상품명": full_title,
                        "가격": price,
                        "URL": task['url'],
                        "이미지URL": img_url,
                        "지역": task['region'],
                        "출발공항": task['airport']
                    })
            except Exception as e:
                print(f"⚠️ URL 패스 예외 발생 ({task['url']}): {e}")
                continue
        await browser.close()

    # 데이터프레임 변환
    df_new = pd.DataFrame(crawled_raw_products)
    print(f"✅ 크롤링 전수 완료: 현재 웹상에 살아있는 상품 총 {len(df_new)}개 수집됨.")

    # -------------------------------------------------------------
    # 3~5. 데이터 대조 연산 (추가 / 유지 / 삭제 자동 처리)
    # -------------------------------------------------------------
    print("\n📊 [3~5단계] 최신화 연산 진행 (중복 제거 및 삭제 처리)...")
    
    # 웹 사이트 자체 화면에 간혹 중복 노출되는 데이터 ID 기준으로 완전히 제거
    df_new = df_new.drop_duplicates(subset=["ID"])

    # 💡 최신 데이터프레임(df_new)이 곧 정답입니다.
    # 기존 시트에 있다 하더라도 df_new에 없다면 하나투어에서 삭제된 상품이므로 
    # 별도의 복잡한 merge 없이 df_new 자체를 최종 적재 데이터로 사용하면 3, 4, 5번 규칙이 완벽하게 성립됩니다.
    # (동일 상품명이 있으면 기존 컬럼 구성을 그대로 유지한 채 덮어씌워지며, 삭제된 상품은 목록에서 자동 탈락)
    df_final = df_new.copy()

    # -------------------------------------------------------------
    # 6. 최종 4개 구글 스프레드시트 전수 적재 (Overwrite)
    # -------------------------------------------------------------
    print(f"\n💾 [6단계] 최종 데이터 적재 준비 (총 {len(df_final)}개 상품)...")
    
    # 순서 보장 및 포맷화
    column_order = ["ID", "상품명", "가격", "URL", "이미지URL", "지역", "출발공항"]
    df_final = df_final[column_order].fillna("")

    # 업로드 전용 이중 리스트 변환
    data_to_upload = [df_final.columns.values.tolist()] + df_final.values.tolist()

    # 적재 대상 구글 스프레드시트 고유 키값 목록
    target_spreadsheet_ids = [
        "1mH51VHs4y0FgClkUBvZgw7oY3Yv7gQBA_a3um9uhX0I",
        "1JgWk9PYT6LG_1GnPdpVY0mZavcHXDWRSrzdE0lVmjj4",
        "1Hoq0N88mestsHXbIOjwue3OctXf7dvKkx99eieYFhAY",
        "1BK4xUHQFrLjLTn6vE0jSuwqMvSU7ZMKIV-nPvmySPx8"
    ]

    for s_id in target_spreadsheet_ids:
        try:
            target_doc = gc.open_by_key(s_id)
            sheet = target_doc.worksheet("github")
            sheet.clear()  # 기존 찌꺼기 완벽 제거
            sheet.update(values=data_to_upload, range_name='A1')
            print(f"✅ 적재 성공: [{target_doc.title}] 동기화 완료")
        except Exception as e:
            print(f"⚠️ 시트 업데이트 실패 ({s_id}): {e}")

    print("\n🎉 고유 ID 기반 7대 핵심 데이터 동기화 파이프라인이 정상 종료되었습니다!")


if __name__ == "__main__":
    asyncio.run(run_pipeline())
