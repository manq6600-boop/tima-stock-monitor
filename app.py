import streamlit as st
import requests
from bs4 import BeautifulSoup
import pandas as pd
import FinanceDataReader as fdr
from datetime import datetime, timedelta

st.set_page_config(page_title="TIMA 스타일 주도주 모니터링", layout="wide")

st.markdown("""
<div style="background-color: #f1f8f6; padding: 15px; border-radius: 10px; margin-bottom: 25px;">
<h2 style="color: #00a884; margin: 0; display: inline-block;">티마 (TIMA) Style</h2>
<span style="color: #777; margin-left: 15px; font-weight: bold;">Premium 테마 모니터링</span>
<span style="float: right; color: #555;">""" + datetime.today().strftime('%m-%d %H:%M') + """</span>
</div>
""", unsafe_allow_html=True)

def get_latest_business_day():
    d = datetime.today()
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d.strftime("%Y-%m-%d")

@st.cache_data(ttl=60)
def get_vol_dict():
    try:
        date = get_latest_business_day()
        df = fdr.StockListing('KRX')
        vol_dict = {}
        if 'Name' in df.columns and 'Volume' in df.columns and 'Close' in df.columns:
            df['거래대금'] = df['Volume'] * df['Close']
            vol_dict = df.set_index('Name')['거래대금'].to_dict()
        return vol_dict
    except:
        return {}

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

    top_themes = sorted(theme_list, key=lambda x: x['change'], reverse=True)[:4]
    vol_dict = get_vol_dict()

    final_data = {}
    for t in top_themes:
        t_url = f"https://finance.naver.com/sise/theme_detail.naver?theme_no={t['id']}"
        t_res = requests.get(t_url, headers=headers)
        t_soup = BeautifulSoup(t_res.text, "html.parser")

        stocks_in_theme = []
        t_table = t_soup.find("table", {"class": "type_5"})
        if t_table:
            for tr in t_table.find_all("tr"):
                tds = tr.find_all("td", {"class": "name"})
                if tds:
                    s_name = tds[0].text.strip()
                    tr_tds = tr.find_all("td")
                    try:
                        curr_price = tr_tds[1].text.strip().replace(',', '')
                        s_change = tr_tds[2].text.strip().replace('\n', '').replace('\t', '')
                        raw_vol = vol_dict.get(s_name, 0)
                        vol_billion = raw_vol / 100000000
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

try:
    data = get_tima_theme_data()
    if not data:
        st.info("⏰ 아직 장 개시 전이거나 데이터를 불러올 수 없습니다. 평일 09:00~15:30에 실시간 반영됩니다.")
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
                        price_display = f"{s['price']:,}" if isinstance(s['price'], int) else s['price']
                        st.markdown(f"""
<div style="display: flex; justify-content: space-between; align-items: center; padding: 6px 0; border-bottom: 1px solid #f0f0f0;">
<div>
<div style="font-weight: bold; font-size: 13px; color:#333;">{s['name']}</div>
<div style="font-size: 11px; color: #777;">{price_display} 원</div>
</div>
<div style="text-align: right;">
<div style="font-weight: bold; color: {color}; font-size: 13px;">{s['change'].strip()}</div>
<div style="font-size: 10px; color: #999;">{s['vol']:,.0f}억</div>
</div>
</div>
""", unsafe_allow_html=True)
except Exception as e:
    st.error(f"❌ 오류: {e}")
