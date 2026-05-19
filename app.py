import streamlit as st
import requests
from bs4 import BeautifulSoup
import pandas as pd
from pykrx import stock
from datetime import datetime
import logging
import sys

# UTF-8 인코딩 설정
if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

# 로깅 설정
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 1. 웹 페이지 기본 레이아웃 설정
st.set_page_config(page_title="TIMA 스타일 주도주 모니터링", layout="wide")

# 티마 감성의 상단 바 디자인
st.markdown("""
    <div style="background-color: #f1f8f6; padding: 15px; border-radius: 10px; margin-bottom: 25px;">
        <h2 style="color: #00a884; margin: 0; display: inline-block;">🎯 TIMA 스타일</h2>
        <span style="color: #777; margin-left: 15px; font-weight: bold;">Premium 테마 모니터링</span>
        <span style="float: right; color: #555;""" + datetime.today().strftime('%m-%d %H:%M') + """</span>
    </div>
""", unsafe_allow_html=True)

# -----------------------------------------------------------------
# 유틸리티 함수
# -----------------------------------------------------------------
def safe_float(value, default=0.0):
    """안전하게 float으로 변환"""
    try:
        return float(str(value).replace('%', '').replace('+', '').strip())
    except (ValueError, AttributeError):
        return default

def safe_int(value, default=0):
    """안전하게 int로 변환"""
    try:
        clean_value = str(value).replace(',', '').strip()
        return int(clean_value) if clean_value.isdigit() else default
    except (ValueError, AttributeError):
        return default

def is_positive_change(change_str):
    """등락률이 양수인지 판단 (손실분 포함)"""
    try:
        change_value = safe_float(change_str)
        return change_value >= 0
    except:
        return "-" not in str(change_str)

def get_change_color(is_positive):
    """한국 증시 관례에 따른 색상 반환 (상승=빨강, 하락=파랑)"""
    return "#c60c30" if is_positive else "#004687"  # Red=up, Blue=down

# -----------------------------------------------------------------
# 데이터 수집 함수 (네이버 테마 및 KRX 거래대금 결합)
# -----------------------------------------------------------------
@st.cache_data(ttl=60)  # 1분마다 자동 갱신
def get_tima_theme_data():
    """티마 스타일 테마 데이터 수집"""
    try:
        logger.info("테마 데이터 수집 시작...")
        
        # 1. 네이버에서 방일 테마 순위 가져오기
        url = "https://finance.naver.com/sise/theme.naver"
        headers = {"User-Agent": "Mozilla/5.0"}
        
        try:
            res = requests.get(url, headers=headers, timeout=10)
            res.raise_for_status()
        except requests.RequestException as e:
            logger.error(f"네이버 테마 페이지 요청 실패: {e}")
            return {}
        
        soup = BeautifulSoup(res.text, "html.parser")
        
        theme_list = []
        table = soup.find("table", {"class": "type_1"})
        
        if table:
            rows = table.find_all("tr")
            for row in rows:
                try:
                    cols = row.find_all("td")
                    if len(cols) >= 3:
                        link_tag = cols[0].find("a")
                        if not link_tag:
                            continue
                        
                        link = link_tag.get("href", "")
                        theme_id = link.split("theme_no=")[-1] if "theme_no=" in link else ""
                        
                        if not theme_id:
                            continue
                        
                        name = cols[0].text.strip()
                        change_pct = safe_float(cols[1].text.strip())
                        
                        theme_list.append({
                            "id": theme_id,
                            "name": name,
                            "change": change_pct
                        })
                except (IndexError, AttributeError) as e:
                    logger.debug(f"테마 행 파싱 실패: {e}")
                    continue
        
        if not theme_list:
            logger.warning("파싱된 테마 데이터가 없습니다")
            return {}
        
        # 상위 등락률 높은 4개 테마만 선정
        top_themes = sorted(theme_list, key=lambda x: x['change'], reverse=True)[:4]
        logger.info(f"상위 4개 테마 선정: {[t['name'] for t in top_themes]}")
        
        # 2. 거래대금 매칭을 위한 pykrx 최신 데이터 로드 (배치 처리)
        vol_dict = {}
        try:
            today_str = datetime.today().strftime("%Y%m%d")
            try:
                df_vol = stock.get_market_price_change_by_ticker(today_str, today_str, "ALL")
                logger.info(f"방일({today_str}) 거래량 데이터 로드 성공")
            except Exception as e:
                logger.warning(f"방일 데이터 로드 실패, 최근 영업일 데이터 사용: {e}")
                latest_day = stock.get_nearest_business_day_in_a_week()
                df_vol = stock.get_market_price_change_by_ticker(latest_day, latest_day, "ALL")
            
            df_vol = df_vol.reset_index()
            
            # 종목명 매핑 (배치 처리로 최적화)
            if '종목코드' in df_vol.columns:
                df_vol['종목명'] = df_vol['종목코드'].apply(
                    lambda x: stock.get_market_ticker_name(x)
                )
            
            # 거래대금 딕셔너리 생성
            if '거래대금' in df_vol.columns and '종목명' in df_vol.columns:
                vol_dict = df_vol.set_index('종목명')['거래대금'].to_dict()
            
            logger.info(f"거래대금 데이터: {len(vol_dict)}개 종목")
        except Exception as e:
            logger.warning(f"거래대금 데이터 로드 실패: {e}")
            vol_dict = {}
        
        # 3. 각 테마별 상세 종목 4개씩 파싱
        final_data = {}
        for t in top_themes:
            try:
                t_url = f"https://finance.naver.com/sise/theme_detail.naver?theme_no={t['id']}"
                
                try:
                    t_res = requests.get(t_url, headers=headers, timeout=10)
                    t_res.raise_for_status()
                except requests.RequestException as e:
                    logger.error(f"테마 상세 페이지 요청 실패 ({t['name']}): {e}")
                    continue
                
                t_soup = BeautifulSoup(t_res.text, "html.parser")
                
                stocks_in_theme = []
                t_table = t_soup.find("table", {"class": "type_5"})
                
                if t_table:
                    t_rows = t_table.find_all("tr")
                    for tr in t_rows:
                        try:
                            tds = tr.find_all("td", {"class": "name"})
                            if not tds:
                                continue
                            
                            s_name = tds[0].text.strip()
                            tr_tds = tr.find_all("td")
                            
                            if len(tr_tds) < 3:
                                continue
                            
                            # 주가 및 등락률 안전 파싱
                            curr_price_str = tr_tds[1].text.strip().replace(',', '')
                            curr_price = safe_int(curr_price_str)
                            
                            s_change = tr_tds[2].text.strip().replace('\n', '').replace('\t', '')
                            
                            # 거래대금 (없으면 0)
                            raw_vol = vol_dict.get(s_name, 0)
                            vol_billion = raw_vol / 100000000 if raw_vol else 0
                            
                            stocks_in_theme.append({
                                "name": s_name,
                                "price": curr_price,
                                "change": s_change,
                                "vol": vol_billion
                            })
                        except (IndexError, ValueError, AttributeError) as e:
                            logger.debug(f"종목 파싱 실패: {e}")
                            continue
                
                # 테마 내에서 상위 4개만 카트
                final_data[t['name']] = {
                    "theme_change": t['change'],
                    "stocks": stocks_in_theme[:4]
                }
                logger.info(f"테마 '{t['name']}' - {len(stocks_in_theme[:4])}개 종목 수집")
                
            except Exception as e:
                logger.error(f"테마 데이터 수집 실패 ({t['name']}): {e}")
                continue
        
        logger.info("테마 데이터 수집 완료")
        return final_data
        
    except Exception as e:
        logger.error(f"전체 데이터 수집 중 예상 외 오류: {e}")
        return {}

# -----------------------------------------------------------------
# 화면 ���리기 (티마 UI 레이아웃 구현)
# -----------------------------------------------------------------
try:
    data = get_tima_theme_data()
    
    if not data:
        st.error("⚠️ 데이터를 가져올 수 없습니다. 다음 중 하나의 원인일 수 있습니다:\n"
                 "- 장 시간이 아님 (평일 09:00 ~ 15:30)\n"
                 "- 네트워크 연결 문제\n"
                 "- 웹사이트 변경으로 인한 파싱 실패\n"
                 "\n새로고침(F5)을 시도하거나 잠시 후 다시 속합해주세요.")
    else:
        # 2x2 격자(Grid) 구조 생성
        theme_names = list(data.keys())
        
        # 행1 (테마 1, 테마 2)
        row1_col1, row1_col2 = st.columns(2)
        # 행2 (테마 3, 테마 4)
        row2_col1, row2_col2 = st.columns(2)
        
        grid_positions = [row1_col1, row1_col2, row2_col1, row2_col2]
        
        for idx, name in enumerate(theme_names):
            with grid_positions[idx]:
                theme_info = data[name]
                theme_change = theme_info['theme_change']
                is_theme_positive = theme_change >= 0
                theme_color = get_change_color(is_theme_positive)
                
                # 테마 헤더 박스
                st.markdown(f"""
                    <div style="background-color: #2b5f54; padding: 8px 15px; border-radius: 5px 5px 0 0; color: white; display: flex; justify-content: space-between; align-items: center;">
                        <span style="font-weight: bold; font-size: 16px;">📌 {name}</span>
                        <span style="background-color: #e6f4ea; color: {theme_color}; padding: 2px 8px; border-radius: 4px; font-weight: bold;">
                            {'+' if is_theme_positive else ''}{theme_change:.2f}%
                        </span>
                    </div>
                """, unsafe_allow_html=True)
                
                # 테마 내부 종목 박스
                if theme_info['stocks']:
                    with st.container(border=True):
                        for s in theme_info['stocks']:
                            # 등락률 색상 설정 (한국 증시 관례)
                            is_positive = is_positive_change(s['change'])
                            color = get_change_color(is_positive)
                            
                            st.markdown(f"""
                                <div style="display: flex; justify-content: space-between; align-items: center; padding: 8px 0; border-bottom: 1px solid #f0f0f0;">
                                    <div style="flex: 1;">
                                        <div style="font-weight: bold; font-size: 14px; color:#333;">{s['name']}</div>
                                        <div style="font-size: 12px; color: #777;">{s['price']:,} 원</div>
                                    </div>
                                    <div style="text-align: right; min-width: 90px;">
                                        <div style="font-weight: bold; color: {color}; font-size: 14px;">{s['change'].strip()}</div>
                                        <div style="font-size: 11px; color: #999;">{s['vol']:,.0f}억</div>
                                    </div>
                                </div>
                            """, unsafe_allow_html=True)
                else:
                    st.warning(f"'{name}' 테마의 종목 데이터를 불러올 수 없습니다.")
        
except Exception as e:
    logger.error(f"화면 렌더링 중 오류: {e}")
    st.error(f"❌ 예상 외의 오류가 발생했습니다: {str(e)}\n\n"
             f"관리자에게 문의하거나 페이지를 새로고침해주세요.")
