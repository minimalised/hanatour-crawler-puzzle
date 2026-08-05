import os
import re
import json
import gspread
from urllib.parse import urlparse, urlunparse, parse_qs, urlencode
from google.oauth2.service_account import Credentials

# 1. Secrets에서 구글 계정 키 및 시트 ID 가져오기
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
google_json_str = os.environ["GOOGLE_JSON_RAW"]
service_account_info = json.loads(google_json_str)

credentials = Credentials.from_service_account_info(service_account_info, scopes=SCOPES)
gc = gspread.authorize(credentials)

# 스프레드시트 열기
spreadsheet_id = os.environ["SPREADSHEET_ID"]
doc = gc.open_by_key(spreadsheet_id)

# 2. 원본 시트('호텔상품리스트') 데이터 가져오기
source_sheet = doc.worksheet('호텔상품리스트')
all_rows = source_sheet.get_all_values()

if not all_rows:
    print("데이터가 없습니다.")
    exit(0)

# 3. 지정된 열 가져오기, B열 괄호 제거, F열 도메인 변경 및 utm 파라미터 제거, K열 조건 처리
extracted_data = []

# 대괄호 및 소괄호 [, ], (, ) 제거용 정규표현식
bracket_pattern = re.compile(r'[\[\]\(\)]')

# 도메인 변경 및 utm 파라미터 제거 함수
def clean_and_replace_url(url, new_domain="https://unique.hanatour.com"):
    if not url or not url.startswith("http"):
        return url
    
    parsed_url = urlparse(url)
    target_parsed = urlparse(new_domain)
    
    # 쿼리 파라미터 분해
    query_params = parse_qs(parsed_url.query, keep_blank_values=True)
    
    # 'utm_'으로 시작하는 파라미터 제거
    filtered_params = {
        k: v for k, v in query_params.items() 
        if not k.startswith("utm_")
    }
    
    # 쿼리 문자열 재구성
    new_query = urlencode(filtered_params, doseq=True)
    
    # scheme(https), netloc(unique.hanatour.com) 및 정돈된 query 적용 후 재조합
    updated_url = urlunparse((
        target_parsed.scheme,
        target_parsed.netloc,
        parsed_url.path,
        parsed_url.params,
        new_query,
        parsed_url.fragment
    ))
    return updated_url

for idx, row in enumerate(all_rows):
    def get_val(i):
        return row[i] if i < len(row) else ''

    col_a = get_val(0)  # A열: id
    col_b = get_val(1)  # B열: 상품명
    col_c = get_val(2)  # C열: 가격
    col_d = get_val(3)  # D열: 혜택가격
    col_f = get_val(5)  # F열: 링크
    col_h = get_val(7)  # H열: 이미지링크
    col_k = get_val(10) # K열: 분류/카테고리

    # 1행(헤더)은 조건 검사 없이 그대로 추가
    if idx == 0:
        extracted_data.append([col_a, col_b, col_c, col_d, col_f, col_h])
        continue

    # K열이 '국내숙박'인 경우 불러오지 않고 스킵 (공백 제거 후 비교)
    if col_k.strip() == '국내숙박':
        continue

    # B열 상품명에서 [, ], (, ) 제거
    cleaned_b = bracket_pattern.sub('', col_b)

    # F열 도메인 변경 및 utm 파라미터 제거
    updated_f = clean_and_replace_url(col_f)

    extracted_data.append([col_a, cleaned_b, col_c, col_d, updated_f, col_h])

# 4. Target 시트('호텔github')에 데이터 반영
try:
    target_sheet = doc.worksheet('호텔github')
except gspread.exceptions.WorksheetNotFound:
    target_sheet = doc.add_worksheet(title='호텔github', rows="1000", cols="10")

# 기존 내용 덮어쓰기
target_sheet.clear()
target_sheet.update('A1', extracted_data)

print(f"총 {len(extracted_data)}행 데이터 업데이트 완료!")
