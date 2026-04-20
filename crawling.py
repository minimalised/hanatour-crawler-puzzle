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
"https://www.hanatour.com/package/major-products?cntryCd=TH&cityCd=BKK&depCityCd=JCN&cityNm=%EB%B0%A9%EC%BD%95",
"https://www.hanatour.com/package/major-products?cntryCd=TH&cityCd=PYX&depCityCd=JCN&cityNm=%ED%8C%8C%ED%83%80%EC%95%BC",
"https://www.hanatour.com/package/major-products?cntryCd=TH&cityCd=BKK&depCityCd=JCN&cityNm=%EB%B0%A9%EC%BD%95",
"https://www.hanatour.com/package/major-products?cntryCd=TH&cityCd=PYX&depCityCd=JCN&cityNm=%ED%8C%8C%ED%83%80%EC%95%BC",
"https://www.hanatour.com/package/major-products?cntryCd=TH&cityCd=HKT&depCityCd=JCN&cityNm=%ED%91%B8%EA%BB%AB",
"https://www.hanatour.com/package/major-products?cntryCd=TH&cityCd=CNX&depCityCd=JCN&cityNm=%EC%B9%98%EC%95%99%EB%A7%88%EC%9D%B4",
"https://www.hanatour.com/package/major-products?cntryCd=TH&cityCd=AUB&depCityCd=JCN&cityNm=%EC%95%84%EC%9C%A0%ED%83%80%EC%95%BC",
"https://www.hanatour.com/package/major-products?cntryCd=TH&cityCd=P78&depCityCd=JCN&cityNm=%EC%B9%B8%EC%B0%A8%EB%82%98%EB%B6%80%EB%A6%AC",
"https://www.hanatour.com/package/major-products?cntryCd=TH&cityCd=USM&depCityCd=JCN&cityNm=%EC%BD%94%EC%82%AC%EB%AC%B4%EC%9D%B4",
"https://www.hanatour.com/package/major-products?cityCd=SIN&cntryNm=%EC%8B%B1%EA%B0%80%ED%8F%AC%EB%A5%B4",
"https://www.hanatour.com/package/major-products?cntryCd=MV&cntryNm=%EB%AA%B0%EB%94%94%EB%B8%8C",
"https://www.hanatour.com/package/major-products?cntryCd=PH&cityCd=KLO&depCityCd=JCN&cityNm=%EB%B3%B4%EB%9D%BC%EC%B9%B4%EC%9D%B4",
"https://www.hanatour.com/package/major-products?cntryCd=PH&cityCd=CEB&depCityCd=JCN&cityNm=%EC%84%B8%EB%B6%80",
"https://www.hanatour.com/package/major-products?cntryCd=PH&cityCd=TAG&depCityCd=JCN&cityNm=%EB%B3%B4%ED%99%80",
"https://www.hanatour.com/package/major-products?cntryCd=PH&cityCd=MNL&depCityCd=JCN&cityNm=%EB%A7%88%EB%8B%90%EB%9D%BC",
"https://www.hanatour.com/package/major-products?cntryCd=PH&cityCd=CRK&depCityCd=JCN&cityNm=%ED%81%B4%EB%9D%BD",
"https://www.hanatour.com/package/major-products?cntryCd=VN&cityCd=DAD&depCityCd=JCN&cityNm=%EB%8B%A4%EB%82%AD",
"https://www.hanatour.com/package/major-products?cntryCd=VN&cityCd=NHA&depCityCd=JCN&cityNm=%EB%82%98%ED%8A%B8%EB%9E%91",
"https://www.hanatour.com/package/major-products?cntryCd=VN&cityCd=DLI&depCityCd=JCN&cityNm=%EB%8B%AC%EB%9E%8F",
"https://www.hanatour.com/package/major-products?cntryCd=VN&cityCd=PQC&depCityCd=JCN&cityNm=%ED%91%B8%EA%BE%B8%EC%98%A5",
"https://www.hanatour.com/package/major-products?cntryCd=VN&cityCd=HAN&depCityCd=JCN&cityNm=%ED%95%98%EB%85%B8%EC%9D%B4%2F%ED%95%98%EB%A1%B1%EB%B2%A0%EC%9D%B4",
"https://www.hanatour.com/package/major-products?cntryCd=VN&cityCd=SGN&depCityCd=JCN&cityNm=%ED%98%B8%EC%B9%98%EB%AF%BC",
"https://www.hanatour.com/package/major-products?cntryCd=VN&cityCd=B42&depCityCd=JCN&cityNm=%EB%AC%B4%EC%9D%B4%EB%84%A4",
"https://www.hanatour.com/package/major-products?cntryCd=VN&cityCd=BC1&depCityCd=JCN&cityNm=%EC%82%AC%ED%8C%8C",
"https://www.hanatour.com/package/major-products?cntryCd=VN&cityCd=VDHHUI&depCityCd=JCN&cityNm=%ED%9B%84%EC%97%90%2F%EB%8F%99%ED%97%88%EC%9D%B4",
"https://www.hanatour.com/package/major-products?cntryCd=MY&cityCd=BKI&depCityCd=JCN&cityNm=%EC%BD%94%ED%83%80%ED%82%A4%EB%82%98%EB%B0%9C%EB%A3%A8",
"https://www.hanatour.com/package/major-products?cntryCd=MY&cityCd=KUL&depCityCd=JCN&cityNm=%EC%BF%A0%EC%95%8C%EB%9D%BC%EB%A3%B8%ED%94%84%EB%A5%B4",
"https://www.hanatour.com/package/major-products?cntryCd=BN&cityCd=BWN&depCityCd=JCN&cityNm=%EB%B8%8C%EB%A3%A8%EB%82%98%EC%9D%B4",
"https://www.hanatour.com/package/major-products?cntryCd=ID&cityCd=DPS&depCityCd=JCN&cityNm=%EB%B0%9C%EB%A6%AC",
"https://www.hanatour.com/package/major-products?cntryCd=ID&cityCd=BTH&depCityCd=JCN&cityNm=%EB%B0%94%ED%83%90",
"https://www.hanatour.com/package/major-products?cntryCd=ID&cityCd=MDC&depCityCd=JCN&cityNm=%EB%A7%88%EB%82%98%EB%8F%84",
"https://www.hanatour.com/package/major-products?cntryCd=LA&cityCd=AX6&depCityCd=JCN&cityNm=%EB%B0%A9%EB%B9%84%EC%97%A5",
"https://www.hanatour.com/package/major-products?cntryCd=LA&cityCd=LPQ&depCityCd=JCN&cityNm=%EB%A3%A8%EC%95%99%ED%94%84%EB%9D%BC%EB%B0%A9",
"https://www.hanatour.com/package/major-products?cntryCd=LA&cityCd=VTE&depCityCd=JCN&cityNm=%EB%B9%84%EC%97%94%ED%8B%B0%EC%95%88",
"https://www.hanatour.com/package/major-products?cntryCd=KH&cityCd=SAI&depCityCd=JCN&cityNm=%EC%95%99%EC%BD%94%EB%A5%B4%EC%99%80%ED%8A%B8",
"https://www.hanatour.com/package/major-products?cntryCd=TW&cityCd=TPE&depCityCd=JCNAF9&cityNm=%ED%83%80%EC%9D%B4%EB%B2%A0%EC%9D%B4",
"https://www.hanatour.com/package/major-products?cntryCd=TW&cityCd=RMQ&depCityCd=JCNAF9&cityNm=%ED%83%80%EC%9D%B4%EC%A4%91",
"https://www.hanatour.com/package/major-products?cntryCd=TW&cityCd=KHH&depCityCd=JCNAF9&cityNm=%EA%B0%80%EC%98%A4%EC%8A%9D",
"https://www.hanatour.com/package/major-products?cntryCd=TW&cityCd=TNN&depCityCd=JCNAF9&cityNm=%ED%83%80%EC%9D%B4%EB%82%9C",
"https://www.hanatour.com/package/major-products?cntryCd=IN&cntryNm=%EC%9D%B8%EB%8F%84",
"https://www.hanatour.com/package/major-products?cntryCd=NP&cntryNm=%EB%84%A4%ED%8C%94",
"https://www.hanatour.com/package/major-products?cntryCd=LK&cntryNm=%EC%8A%A4%EB%A6%AC%EB%9E%91%EC%B9%B4",
"https://www.hanatour.com/package/major-products?cntryCd=JP&cityCd=TYO&depCityCd=JCNAF9&cityNm=%EB%8F%84%EC%BF%84",
"https://www.hanatour.com/package/major-products?cntryCd=JP&cityCd=FSZ&depCityCd=JCN&cityNm=%EC%8B%9C%EC%A6%88%EC%98%A4%EC%B9%B4",
"https://www.hanatour.com/package/major-products?cntryCd=JP&cityCd=HKO&depCityCd=JCN&cityNm=%ED%95%98%EC%BD%94%EB%84%A4%2F%ED%9B%84%EC%A7%80%EC%82%B0",
"https://www.hanatour.com/package/major-products?cntryCd=JP&cityCd=YOKP81P97&depCityCd=JCN&cityNm=%EC%9A%94%EC%BD%94%ED%95%98%EB%A7%88",
"https://www.hanatour.com/package/major-products?cntryCd=JP&cityCd=OSA&depCityCd=JCNAF9&cityNm=%EC%98%A4%EC%82%AC%EC%B9%B4",
"https://www.hanatour.com/package/major-products?cntryCd=JP&cityCd=UKY&depCityCd=JCNAF9&cityNm=%EA%B5%90%ED%86%A0",
"https://www.hanatour.com/package/major-products?cntryCd=JP&cityCd=UKB&depCityCd=JCNAF9&cityNm=%EA%B3%A0%EB%B2%A0",
"https://www.hanatour.com/package/major-products?cntryCd=JP&cityCd=QKYSHM&depCityCd=JCN&cityNm=%EC%99%80%EC%B9%B4%EC%95%BC%EC%B9%B4",
"https://www.hanatour.com/package/major-products?cntryCd=JP&cityCd=FUK&depCityCd=JCN&cityNm=%ED%9B%84%EC%BF%A0%EC%98%A4%EC%B9%B4",
"https://www.hanatour.com/package/major-products?cntryCd=JP&cityCd=BPU&depCityCd=JCN&cityNm=%EB%B2%B3%EB%B6%80%2F%EC%9C%A0%ED%9B%84%EC%9D%B8",
"https://www.hanatour.com/package/major-products?cntryCd=JP&cityCd=HSG&depCityCd=JCN&cityNm=%EC%82%AC%EA%B0%80",
"https://www.hanatour.com/package/major-products?cntryCd=JP&cityCd=OIT&depCityCd=JCN&cityNm=%EC%98%A4%EC%9D%B4%ED%83%80",
"https://www.hanatour.com/package/major-products?cntryCd=JP&cityCd=KMJ&depCityCd=JCN&cityNm=%EA%B5%AC%EB%A7%88%EB%AA%A8%ED%86%A0",
"https://www.hanatour.com/package/major-products?cntryCd=JP&cityCd=KOJ&depCityCd=JCN&cityNm=%EA%B0%80%EA%B3%A0%EC%8B%9C%EB%A7%88",
"https://www.hanatour.com/package/major-products?cntryCd=JP&cityCd=KKJ&depCityCd=JCN&cityNm=%EA%B8%B0%ED%83%80%ED%81%90%EC%8A%88",
"https://www.hanatour.com/package/major-products?cntryCd=JP&cityCd=SPK&depCityCd=JCN&cityNm=%EC%82%BF%ED%8F%AC%EB%A1%9C",
"https://www.hanatour.com/package/major-products?cntryCd=JP&cityCd=HS9&depCityCd=JCN&cityNm=%ED%9B%84%EB%9D%BC%EB%85%B8%2F%EB%B9%84%EC%97%90%EC%9D%B4",
"https://www.hanatour.com/package/major-products?cntryCd=JP&cityCd=AKJ&depCityCd=JCN&cityNm=%EC%95%84%EC%82%AC%ED%9E%88%EC%B9%B4%EC%99%80",
"https://www.hanatour.com/package/major-products?cntryCd=JP&cityCd=993&depCityCd=JCN&cityNm=%EB%85%B8%EB%B3%B4%EB%A6%B0%EB%B2%A0%EC%B8%A0",
"https://www.hanatour.com/package/major-products?cntryCd=JP&cityCd=HKD&depCityCd=JCN&cityNm=%ED%95%98%EC%BD%94%EB%8B%A4%ED%85%8C",
"https://www.hanatour.com/package/major-products?cntryCd=JP&cityCd=F59TAK&depCityCd=JCN&cityNm=%EB%8B%A4%B9%EC%B9%B4%EB%A7%88%EC%B8%A0",
"https://www.hanatour.com/package/major-products?cntryCd=JP&cityCd=MYJ&depCityCd=JCN&cityNm=%EB%A7%88%EC%B8%A0%EC%95%BC%EB%A7%88",
"https://www.hanatour.com/package/major-products?cntryCd=JP&cityCd=TKS&depCityCd=JCN&cityNm=%EB%8F%84%EC%BF%A0%EC%8B%9C%EB%A7%88",
"https://www.hanatour.com/package/major-products?cntryCd=JP&cityCd=TTJ&depCityCd=JCN&cityNm=%EB%8F%97%ED%86%A0%EB%A6%AC",
"https://www.hanatour.com/package/major-products?cntryCd=JP&cityCd=YGJ&depCityCd=JCN&cityNm=%EC%9A%94%EB%82%98%EA%B3%A0",
"https://www.hanatour.com/package/major-products?cntryCd=JP&cityCd=HIJ&depCityCd=JCN&cityNm=%ED%9E%88%EB%A1%9C%EC%8B%9C%EB%A7%88",
"https://www.hanatour.com/package/major-products?cntryCd=JP&cityCd=OKJ&depCityCd=JCN&cityNm=%EC%98%A4%EC%B9%B4%EC%95%BC%EB%A7%88",
"https://www.hanatour.com/package/major-products?cntryCd=JP&cityCd=TSJ&depCityCd=PUS&cityNm=%EB%8C%80%EB%A7%88%EB%8F%84",
"https://www.hanatour.com/package/major-products?cntryCd=JP&cityCd=OKA&depCityCd=JCN&cityNm=%EC%98%A4%ED%82%A4%EB%82%98%EC%99%80",
"https://www.hanatour.com/package/major-products?cntryCd=JP&cityCd=MMY&depCityCd=JCN&cityNm=%EB%AF%B8%EC%95%BC%EC%BD%94%EC%A7%80%EB%A7%88",
"https://www.hanatour.com/package/major-products?cntryCd=JP&cityCd=ISG&depCityCd=JCN&cityNm=%EC%9D%B4%EC%8B%9C%EA%B0%80%ED%82%A4",
"https://www.hanatour.com/package/major-products?cntryCd=JP&cityCd=TOY&depCityCd=JCNAF9&cityNm=%EC%95%8C%ED%8E%9C%EB%A3%A8%ED%8A%B8",
"https://www.hanatour.com/package/major-products?cntryCd=JP&cityCd=NGO&depCityCd=JCNAF9&cityNm=%EB%82%98%EA%B3%A0%EC%95%BC",
"https://www.hanatour.com/package/major-products?cntryCd=JP&cityCd=B19&depCityCd=JCNAF9&cityNm=%EB%8B%A4%B9%EC%B9%B4%EC%95%BC%EB%A7%88",
"https://www.hanatour.com/package/major-products?cntryCd=JP&cityCd=KMQ&depCityCd=JCNAF9&cityNm=%EB%82%98%EA%B3%A0%EC%95%BC",
"https://www.hanatour.com/package/major-products?cntryCd=JP&cityCd=KIJ&depCityCd=JCN&cityNm=%EB%8B%88%EA%B0%80%ED%83%80",
"https://www.hanatour.com/package/major-products?cntryCd=JP&cityCd=AOJ&depCityCd=JCN&cityNm=%EC%95%84%EC%98%A4%EB%AA%A8%EB%A6%AC",
"https://www.hanatour.com/package/major-products?cntryCd=JP&cityCd=AXTSDJ&depCityCd=JCN&cityNm=%EC%95%84%ED%82%A4%ED%83%80%2F%EC%84%BC%EB%8B%A4%EC%9D%B4",
"https://www.hanatour.com/package/major-products?cntryCd=GB&depCityCd=JCN&cntryNm=%EC%98%81%EA%B5%AD",
"https://www.hanatour.com/package/major-products?cntryCd=CH&depCityCd=JCN&cntryNm=%EC%8A%A4%EC%9C%84%EC%8A%A4",
"https://www.hanatour.com/package/major-products?cntryCd=IT&depCityCd=JCN&cntryNm=%EC%9D%B4%ED%83%88%EB%A6%AC%EC%95%84",
"https://www.hanatour.com/package/major-products?cntryCd=FR&depCityCd=JCN&cntryNm=%ED%94%84%EB%9E%91%EC%8A%A4",
"https://www.hanatour.com/package/major-products?cityCd=NCE&depCityCd=JCN&cntryNm=%EB%82%A8%ED%94%84%EB%9E%91%EC%8A%A4",
"https://www.hanatour.com/package/major-products?cityCd=G21&depCityCd=JCN&cntryNm=%EC%8B%9C%EC%B9%A0%EB%A6%AC%EC%95%84",
"https://www.hanatour.com/package/major-products?cntryCd=DE&depCityCd=JCN&cntryNm=%EB%8F%85%EC%9D%BC",
"https://www.hanatour.com/package/major-products?cntryCd=IE&depCityCd=JCN&cntryNm=%EC%95%84%EC%9D%BC%EB%9E%9C%EB%93%9C",
"https://www.hanatour.com/package/major-products?cntryCd=NL&depCityCd=JCN&cntryNm=%EB%84%A4%EB%8D%9C%EB%9E%80%EB%93%9C",
"https://www.hanatour.com/package/major-products?cntryCd=BE&depCityCd=JCN&cntryNm=%EB%B2%A8%EA%B8%B0%EC%97%90",
"https://www.hanatour.com/package/major-products?cntryCd=AT&depCityCd=JCN&cntryNm=%EC%98%A4%EC%8A%A4%ED%8A%B8%EB%A6%AC%EC%95%84",
"https://www.hanatour.com/package/major-products?cntryCd=CZ&depCityCd=JCN&cntryNm=%EC%B2%B4%EC%BD%94",
"https://www.hanatour.com/package/major-products?cntryCd=HU&depCityCd=JCN&cntryNm=%ED%97%9D%EA%B0%80%EB%A6%AC",
"https://www.hanatour.com/package/major-products?cntryCd=HR&depCityCd=JCN&cntryNm=%ED%81%AC%EB%A1%9C%EC%95%84%ED%8B%B0%EC%95%84",
"https://www.hanatour.com/package/major-products?cntryCd=SI&depCityCd=JCN&cntryNm=%EC%8A%AC%EB%A1%9C%EB%B2%A0%EB%8B%88%EC%95%84",
"https://www.hanatour.com/package/major-products?cntryCd=ES&depCityCd=JCN&cntryNm=%EC%8A%A4%ED%8E%98%EC%9D%B8",
"https://www.hanatour.com/package/major-products?cntryCd=PT&depCityCd=JCN&cntryNm=%ED%8F%AC%EB%A5%B4%ED%88%AC%EA%B0%88",
"https://www.hanatour.com/package/major-products?cntryCd=MA&depCityCd=JCN&cntryNm=%EB%AA%A8%EB%A1%9C%EC%BD%94",
"https://www.hanatour.com/package/major-products?cntryCd=TR&depCityCd=JCN&cntryNm=%ED%8A%80%EB%A5%B4%ED%82%A4%EC%98%88",
"https://www.hanatour.com/package/major-products?cntryCd=GR&depCityCd=JCN&cntryNm=%EA%B7%B8%EB%A6%AC%EC%8A%A4",
"https://www.hanatour.com/package/major-products?cntryCd=EG&depCityCd=JCN&cntryNm=%EC%9D%B4%EC%A7%91%ED%8A%B8",
"https://www.hanatour.com/package/major-products?areaCd=EK&cityCdNm=%EC%BD%94%EC%B9%B4%EC%84%9C%EC%8A%A4",
"https://www.hanatour.com/package/major-products?cityCd=DXB&depCityCd=JCN&cityNm=%EB%91%90%EB%B0%94%EC%9D%B4",
"https://www.hanatour.com/package/major-products?cntryCd=JO&depCityCd=JCN&cntryNm=%EC%9A%94%EB%A5%B4%EB%8B%A8",
"https://www.hanatour.com/package/major-products?cntryCd=SA&depCityCd=JCN&cntryNm=%EC%82%AC%EC%9A%B0%EB%94%94%EC%95%84%EB%9D%BC%EB%B9%84%EC%95%84",
"https://www.hanatour.com/package/major-products?cntryCd=OM&depCityCd=JCN&cntryNm=%EC%98%A4%EB%A7%8C",
"https://www.hanatour.com/package/major-products?cntryCd=TN&depCityCd=JCN&cntryNm=%ED%8A%80%EB%8B%88%EC%A7%80",
"https://www.hanatour.com/package/major-products?cntryCd=NO&depCityCd=JCN&cntryNm=%EB%85%B8%EB%A5%B4%EC%9B%A8%EC%9D%B4",
"https://www.hanatour.com/package/major-products?cntryCd=FI&depCityCd=JCN&cntryNm=%ED%95%80%EB%9E%80%EB%93%9C",
"https://www.hanatour.com/package/major-products?cntryCd=DK&depCityCd=JCN&cntryNm=%EB%8D%B4%EB%A7%88%ED%81%AC",
"https://www.hanatour.com/package/major-products?cntryCd=SE&depCityCd=JCN&cntryNm=%EC%8A%A4%EC%9B%A8%EB%8D%B4",
"https://www.hanatour.com/package/major-products?cntryCd=EE&depCityCd=JCN&cntryNm=%EC%97%90%EC%8A%A4%ED%86%A0%EB%8B%88%EC%95%84",
"https://www.hanatour.com/package/major-products?cntryCd=IS&depCityCd=JCN&cntryNm=%EC%95%84%EC%9D%B4%EC%8A%AC%EB%9E%80%EB%93%9C",
"https://www.hanatour.com/package/major-products?cntryCd=KE&depCityCd=JCN&cntryNm=%EC%BC%80%EB%83%90",
"https://www.hanatour.com/package/major-products?cntryCd=ZA&depCityCd=JCN&cntryNm=%EB%82%A8%EC%95%84%EA%B3%B5",
"https://www.hanatour.com/package/major-products?cntryCd=TZ&depCityCd=JCN&cntryNm=%ED%83%84%EC%9E%90%EB%8B%88%EC%95%84",
"https://www.hanatour.com/package/major-products?cntryCd=MN&cntryNm=%EB%AA%BD%EA%B3%A8",
"https://www.hanatour.com/package/major-products?cntryCd=HK&cityCd=HKG&depCityCd=JCN&cityNm=%ED%99%8D%EC%BD%A9",
"https://www.hanatour.com/package/major-products?cntryCd=MO&cityCd=MFM&depCityCd=JCN&cityNm=%EB%A7%88%EC%B9%B4%EC%98%A4",
"https://www.hanatour.com/package/major-products?cntryCd=CN&cityCd=BW9&depCityCd=JCN&cityNm=%EB%82%B4%EB%AA%BD%EA%B3%A0",
"https://www.hanatour.com/package/major-products?cntryCd=HK&cityCd=SZX&depCityCd=JCN&cityNm=%EC%8B%AC%EC%B2%9C",
"https://www.hanatour.com/package/major-products?cntryCd=UZ&cntryNm=%EC%9A%B0%EC%A6%88%EB%B2%A0%ED%82%A4%EC%8A%A4%ED%83%84",
"https://www.hanatour.com/package/major-products?cntryCd=KZ&cntryNm=%EC%B9%B4%EC%9E%90%ED%9D%90%EC%8A%A4%ED%83%84",
"https://www.hanatour.com/package/major-products?cntryCd=KG&cntryNm=%ED%82%A4%EB%A5%B4%EA%B8%B0%EC%8A%A4%EC%8A%A4%ED%83%84",
"https://www.hanatour.com/package/major-products?cntryCd=CN&cityCd=DYG&depCityCd=JCN&cityNm=%EC%9E%A5%EA%B0%80%EA%B3%84",
"https://www.hanatour.com/package/major-products?cntryCd=CN&cityCd=SHA&depCityCd=JCNAF9&cityNm=%EC%83%81%ED%95%B4",
"https://www.hanatour.com/package/major-products?cntryCd=CN&cityCd=B26&depCityCd=JCNCJJ&cityNm=%EB%B0%B1%EB%91%90%EC%82%B0",
"https://www.hanatour.com/package/major-products?cntryCd=CN&cityCd=TXN&depCityCd=JCN&cityNm=%ED%99%A9%EC%82%B0",
"https://www.hanatour.com/package/major-products?cntryCd=CN&cityCd=BJS&depCityCd=JCN&cityNm=%EB%B6%81%EA%B2%BD",
"https://www.hanatour.com/package/major-products?cntryCd=CN&cityCd=CTU&depCityCd=JCN&cityNm=%EC%82%AC%EC%B2%9C%EC%84%B1",
"https://www.hanatour.com/package/major-products?cntryCd=CN&cityCd=KWE&depCityCd=JCN&cityNm=%EA%B7%80%EC%A3%BC%EC%84%B1",
"https://www.hanatour.com/package/major-products?cntryCd=CN&cityCd=LXA&depCityCd=JCN&cityNm=%ED%8B%B0%EB%B2%B3",
"https://www.hanatour.com/package/major-products?cntryCd=CN&cityCd=CKG&depCityCd=JCN&cityNm=%EC%B6%A9%EC%B9%AD",
"https://www.hanatour.com/package/major-products?cntryCd=CN&cityCd=HRB&depCityCd=JCN&cityNm=%ED%95%98%EC%96%BC%EB%B9%88",
"https://www.hanatour.com/package/major-products?cntryCd=CN&cityCd=SIA&depCityCd=JCN&cityNm=%EC%84%9C%EC%95%88",
"https://www.hanatour.com/package/major-products?cntryCd=CN&cityCd=DLC&depCityCd=JCN&cityNm=%EB%8C%80%EB%A0%A8",
"https://www.hanatour.com/package/major-products?cntryCd=CN&cityCd=BY7&depCityCd=JCNCJJ&cityNm=%ED%83%9C%ED%95%AD%EC%82%B0",
"https://www.hanatour.com/package/major-products?cntryCd=CN&cityCd=TAOTNAWEH&depCityCd=JCN&cityNm=%EC%82%B0%EB%8F%99%EC%84%B1",
"https://www.hanatour.com/package/major-products?cntryCd=CN&cityCd=KMG&depCityCd=JCN&cityNm=%EA%B3%A4%EB%AA%85",
"https://www.hanatour.com/package/major-products?cntryCd=CN&cityCd=XMN&depCityCd=JCN&cityNm=%EC%83%A4%EB%A8%BC",
"https://www.hanatour.com/package/major-products?cntryCd=CN&cityCd=LJG&depCityCd=JCN&cityNm=%EC%97%90%EA%B0%95",
"https://www.hanatour.com/package/major-products?cntryCd=CN&cityCd=SYX&depCityCd=JCN&cityNm=%ED%95%98%EC%9D%B4%EB%82%9C",
"https://www.hanatour.com/package/major-products?cntryCd=CN&cityCd=KWL&depCityCd=JCN&cityNm=%EA%B3%84%EB%A6%BC",
"https://www.hanatour.com/package/major-products?cntryCd=CN&cityCd=P45&depCityCd=JCN&cityNm=%EC%B2%9C%EC%A0%80%EC%9A%B0",
"https://www.hanatour.com/package/major-products?cntryCd=CN&cityCd=FOC&depCityCd=JCN&cityNm=%ED%91%B8%EC%A0%80%EC%9A%B0",
"https://www.hanatour.com/package/major-products?cntryCd=CN&cityCd=WUH&depCityCd=JCN&cityNm=%EB%AC%B4%ED%95%9C",
"https://www.hanatour.com/package/major-products?cntryCd=GU&cityCd=GUM&cityNm=%EA%B4%8C",
"https://www.hanatour.com/package/major-products?cntryCd=MP&cityCd=SPN&cityNm=%EC%82%AC%EC%9D%B4%ED%8C%90",
"https://www.hanatour.com/package/major-products?cntryCd=AU&cntryNm=%ED%98%B8%EC%A3%BC",
"https://www.hanatour.com/package/major-products?cntryCd=NZ&cntryNm=%EB%89%B4%EC%A7%88%EB%9E%9C%EB%93%9C",
"https://www.hanatour.com/package/major-products?areaCd=HH&cityNm=%ED%95%98%EC%99%80%EC%9D%B4",
"https://www.hanatour.com/package/major-products?cntryCd=US&areaCd=HW&cityNm=%EB%AF%B8%EA%B5%AD%EC%84%9C%EB%B6%80",
"https://www.hanatour.com/package/major-products?cntryCd=US&areaCd=HE&cityNm=%EB%AF%B8%EA%B5%AD%EB%8F%99%EB%B6%80",
"https://www.hanatour.com/package/major-products?cntryCd=US&catgProdAttrCd=p01&cityCd=DFWATLHOUMSY&cityNm=%EB%AF%B8%EA%B5%AD%EC%A4%91%EB%82%A8%EB%B6%80",
"https://www.hanatour.com/package/major-products?areaCd=HC&cntryNm=%EC%BA%90%EB%82%98%EB%8B%A4",
"https://www.hanatour.com/package/major-products?areaCd=SS&cityNm=%EC%A4%91%EB%82%A8%EB%AF%B8"
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
                scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
                creds = Credentials.from_service_account_file('secrets.json', scopes=scopes)
                gc = gspread.authorize(creds)
                
                spreadsheet_id = "1mH51VHs4y0FgClkUBvZgw7oY3Yv7gQBA_a3um9uhX0I" 
                worksheet_name = "github" 

                doc = gc.open_by_key(spreadsheet_id)
                sheet = doc.worksheet(worksheet_name)

                # 1. 데이터프레임 변환
                df = pd.DataFrame(all_products)
                
                # 2. 기존 데이터 완전 삭제 (포맷 제외 내용만 삭제)
                sheet.clear()
                
                # 3. 헤더와 데이터를 리스트로 변환하여 A1부터 한 번에 업데이트
                # 리스트의 첫 번째 요소는 컬럼명(헤더), 그 뒤로 데이터가 붙습니다.
                data_to_upload = [df.columns.values.tolist()] + df.values.tolist()
                
                # sheet.update() 사용 (범위를 지정하지 않으면 A1부터 자동으로 채워짐)
                sheet.update(data_to_upload)
                
                print(f"\n🎉 성공! 기존 데이터를 삭제하고 총 {len(df)}개의 새 데이터를 '{worksheet_name}' 시트에 갱신했습니다.")
            
            except Exception as e:
                print(f"❌ 시트 저장 에러: {e}")
        
        await browser.close()

if __name__ == "__main__":
    asyncio.run(run_crawler())
