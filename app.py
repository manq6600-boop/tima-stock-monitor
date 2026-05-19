import streamlit as st
import requests
from bs4 import BeautifulSoup
import pandas as pd
from pykrx import stock
from datetime import datetime

# 1. 페이지 제목 및 기본 레이아웃 설정
st.set_page_config(page_title="TIMA 스타일 주도주 모니터링", layout="wide")

# 티마 감성의 민트색 상단 바 디자인
st.markdown("""
    <div style="background-color: #f1f8f6; padding: 15px; border-radius: 10px; margin-bottom: 25px;">
        <h2 style="color: #00a884; margin: 0; display: inline-block;">티마 (TIMA) Style</h2>
        <span style="color: #777; margin-left: 15px; font-weight: bold;">Premium 테마 모니터링</span>
        <span style="float: right; color: #555;">""" + datetime.today().strftime('%m-%d %H:%M') + """</span>
    </div>
""", unsafe_allow_html=True)

# 2. 데이터 수집 함수 (네이버 테마 및 KRX 거래대금 결합)
@st.cache_data(ttl=60)
def get_tima_theme_data():
    url = "https://finance.naver.com/sise/theme.naver"
    headers = {"User-Agent": "Mozilla/5.0"}
    res = requests.get(url, headers=headers)
    soup = BeautifulSoup(res.text, "html.parser")
    
    theme_list = []
    table = soup.find("table", {"class": "type_1"})
    if table:
        rows = table.find_all("tr")
        for row in rows:
            cols = row.find_all("td")
            if len(cols) >= 3:
                link = cols[0].find("a")["href"] if cols[0].find("a") else ""
                theme_id = link.split("theme_no=")[-1] if link else ""
                name = cols[0].text.strip()
                try:
                    change_pct = float(cols[1].text.strip().replace('%', '').replace('+', ''))
                    if theme_id:
                        theme_list.append({"id": theme_id, "name": name, "change": change_pct})
                except:
                    continue
    
    if not theme_list:
        return None
        
    # 상승률 높은 상위 4개 테마 선정
    top_themes = sorted(theme_list, key=lambda x: x['change'], reverse=True)[:4]
    
    # 거래대금을 긁어오기 위한 pykrx 설정
    today_str = datetime.today().strftime("%Y%m%d")
    try:
        df_vol = stock.get_market_price_change_by_ticker(today_str, today_str, "ALL")
    except:
        # 주말이거나 새벽일 경우 가장 최신 영업일 데이터 백업 사용
        latest_day = stock.get_nearest_business_day_in_a_week()
        df_vol = stock.get_market_price_change_by_ticker(latest_day, latest_day, "ALL")
    
    df_vol = df_vol.reset_index()
    df_vol['종목명'] = df_vol['종목코드'].apply(lambda x: stock.get_market_ticker_name(x))
    vol_dict = df_vol.set_index('종목명')['거래대금'].to_dict()

    final_data = {}
    for t in top_themes:
        t_url = f"https://finance.naver.com/sise/theme_detail.naver?theme_no={t['id']}"
        t_res = requests.get(t_url, headers=headers)
        t_soup = BeautifulSoup(t_res.text, "html.parser")
        
        stocks_in_theme = []
        t_table = t_soup.find("table", {"class": "type_5"})
        if t_table:
            t_rows = t_table.find_all("tr")
            for tr in t_rows:
                tds = tr.find_all("td", {"class": "name"})
                if tds:
                    s_name = tds[0].text.strip()
                    tr_tds = tr.find_all("td")
                    try:
                        curr_price = tr_tds[1].text.strip().replace(',', '')
                        s_change = tr_tds[2].text.strip().replace('\n', '').replace('\t', '')
                        raw_vol = vol_dict.get(s_name, 0)
                        vol_billion = raw_vol / 100000000  # 억 단위 변환
                        
                        stocks_in_theme.append({
                            "name": s_name,
                            "price": int(curr_price) if curr_price.isdigit() else curr_price,
                            "change": s_change,
                            "vol": vol_billion
                        })
                    except:
                        continue
        
        final_data[t['name']] = {
            "theme_change": t['change'],
            "stocks": stocks_in_theme[:4]
        }
        
    return final_data

# 3. 화면 UI 그리기 (에러 방지 처리 완료)
try:
    data = get_tima_theme_data()
    
    # 데이터가 아예 비어있을 때 (새벽, 장 개시 전) 안내문 노출
    if data is None or len(data) == 0:
        st.info("⏰ 아직 장 개시 전이거나 데이터를 불러올 수 없습니다. 평일 주식 시장(09:00~15:30)에 실시간으로 반영됩니다.")
    else:
        theme_names = list(data.keys())
        row1_col1, row1_col2 = st.columns(2)
        row2_col1, row2_col2 = st.columns(2)
        grid_positions = [row1_col1, row1_col2, row2_col1, row2_col2]
        
        for idx, name in enumerate(theme_names):
            if idx >= len(grid_positions): break
            with grid_positions[idx]:
                theme_info = data[name]
                st.markdown(f"""
                    <div style="background-color: #2b5f54; padding: 8px 15px; border-radius: 5px 5px 0 0; color: white; display: flex; justify-content: space-between; align-items: center;">
                        <span style="font-weight: bold; font-size: 14px;">📌 {name}</span>
                        <span style="background-color: #e6f4ea; color: #0f9d58; padding: 2px 8px; border-radius: 4px; font-weight: bold;">+{theme_info['theme_change']}%</span>
                    </div>
                """, unsafe_allow_html=True)
                
                with st.container(border=True):
                    for s in theme_info['stocks']:
                        color = "#d93025" if "-" not in str(s['change']) else "#1967d2"
                        st.markdown(f"""
                            <div style="display: flex; justify-content: space-between; align-items: center; padding: 6px 0; border-bottom: 1px solid #f0f0f0;">
                                <div>
                                    <div style="font-weight: bold; font-size: 13px; color:#333;">{s['name']}</div>
                                    <div style="font-size: 11px; color: #777;">{s['price']:,} 원</div>
                                </div>
                                <div style="text-align: right;">
                                    <div style="font-weight: bold; color: {color}; font-size: 13px;">{s['change'].strip()}</div>
                                    <div style="font-size: 10px; color: #999;">{s['vol']:,.0f}억</div>
                                </div>
                            </div>
                        """, unsafe_allow_html=True)
except Exception as e:
    st.info("⏰ 현재 주식 장외 시간입니다. 평일 오전 9시 정각부터 실시간 테마와 주도주가 카드 형태로 업데이트됩니다!")
