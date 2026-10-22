from datetime import datetime, timedelta, timezone
import requests
import pandas as pd
import streamlit as st

# -----------------------------------------------------------------------------
# 1. 페이지 기본 설정 및 파스텔 보라색 테마 커스텀 CSS 적용
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="박스오피스 대시보드",
    page_icon="🎬",
    layout="wide"
)

# 보라색 파스텔톤 커스텀 CSS 스타일링
st.markdown("""
    <style>
    /* 메인 포인트 색상 (파스텔 라벤더) */
    :root {
        --primary-color: #9C27B0;
    }
    
    /* 탭 헤더 및 강조 포인트 보라색 스타일 */
    .stTabs [data-baseweb="tab-list"] button[aria-selected="true"] {
        color: #7B1FA2 !important;
        border-bottom-color: #9C27B0 !important;
        font-weight: bold;
    }
    
    /* 정보 상자(info) 파스텔 보라 배경 */
    .stAlert {
        background-color: #F3E5F5 !important;
        color: #4A148C !important;
        border: 1px solid #E1BEE7 !important;
    }
    
    /* 카드 지표(metric) 파스텔 배경 및 테두리 */
    div[data-testid="stMetric"] {
        background-color: #F8F5FC;
        padding: 15px;
        border-radius: 12px;
        border: 1px solid #E1BEE7;
        box-shadow: 0 2px 4px rgba(156, 39, 176, 0.05);
    }
    </style>
""", unsafe_allow_html=True)

st.title("🎬 KOBIS 박스오피스 대시보드")
st.caption("영화진흥위원회(KOBIS) Open API를 활용하여 일별·주간 박스오피스 및 영화별 추이를 제공합니다.")


# -----------------------------------------------------------------------------
# 2. 날짜 및 인증키 공통 준비
# -----------------------------------------------------------------------------
# (1) 한국 표준시(KST: UTC+9) 기준 계산
kst = timezone(timedelta(hours=9))
now_kst = datetime.now(timezone.utc).astimezone(kst)
yesterday_kst = (now_kst - timedelta(days=1)).date()

# (2) Streamlit Secrets에서 API 인증키 검증
if "KOBIS_KEY" not in st.secrets or not st.secrets["KOBIS_KEY"]:
    st.error("🚨 API 인증키(KOBIS_KEY)가 설정되지 않았습니다.")
    st.markdown("""
    **🔑 KOBIS_KEY 설정 가이드:**
    - **Streamlit Cloud**: App Settings -> Secrets 메뉴에서 `KOBIS_KEY = "발급받은_인증키"` 입력 후 Save
    - **로컬 실행**: `.streamlit/secrets.toml` 파일에 `KOBIS_KEY = "발급받은_인증키"` 작성
    """)
    st.stop()

api_key = st.secrets["KOBIS_KEY"]


# -----------------------------------------------------------------------------
# 3. 공통 함수 정의 (API 데이터 요청 및 가공)
# -----------------------------------------------------------------------------
@st.cache_data(ttl=3600)  # 1시간 동안 API 응답 캐싱
def fetch_box_office(target_dt, week_gb=None):
    # KOBIS API를 호출하여 박스오피스 데이터를 가져오는 함수
    if week_gb:
        url = "https://www.kobis.or.kr/kobisopenapi/webservice/rest/boxoffice/searchWeeklyBoxOfficeList.json"
        params = {"key": api_key, "targetDt": target_dt, "weekGb": week_gb}
        list_key = "weeklyBoxOfficeList"
    else:
        url = "https://www.kobis.or.kr/kobisopenapi/webservice/rest/boxoffice/searchDailyBoxOfficeList.json"
        params = {"key": api_key, "targetDt": target_dt}
        list_key = "dailyBoxOfficeList"

    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        if "faultInfo" in data:
            return None, f"API 오류: {data['faultInfo'].get('message', '인증 실패')}"
            
        box_office_result = data.get("boxOfficeResult", {})
        daily_list = box_office_result.get(list_key, [])
        
        if not daily_list:
            return None, "해당 날짜의 데이터가 비어 있습니다."
            
        df = pd.DataFrame(daily_list)
        
        # 숫자형 변환
        num_cols = ["rank", "rankInten", "audiCnt", "audiAcc", "scrnCnt", "showCnt"]
        for col in num_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)
                
        df = df.sort_values("rank")
        return df, None

    except requests.exceptions.RequestException as e:
        return None, f"통신 에러가 발생했습니다: {e}"


def process_box_office_df(df):
    """데이터프레임 가공 (100만 관객 트로피 & 순위 증감 화살표)"""
    # 100만 관객 이상 트로피 표기
    def format_movie_name(row):
        name = row["movieNm"]
        if row["audiAcc"] >= 1_000_000:
            return f"🏆 {name}"
        return name

    # 순위 증감 화살표
    def format_rank_change(inten):
        inten = int(inten)
        if inten > 0:
            return f"🔺 +{inten}"
        elif inten < 0:
            return f"🔷 -{abs(inten)}"
        return "-"

    df["movieNm_formatted"] = df.apply(format_movie_name, axis=1)
    df["rankChange"] = df["rankInten"].apply(format_rank_change)
    return df


# -----------------------------------------------------------------------------
# 4. 메인 화면 - 탭(Tabs) 구성
# -----------------------------------------------------------------------------
tab1, tab2 = st.tabs(["📅 일별 박스오피스", "🗓️ 주간/주말 박스오피스"])


# =============================================================================
# TAB 1: 일별 박스오피스 (추이 그래프 포함)
# =============================================================================
with tab1:
    col_date, _ = st.columns([1, 2])
    with col_date:
        selected_date = st.date_input(
            "📅 조회할 날짜를 선택하세요",
            value=yesterday_kst,
            max_value=yesterday_kst,
            key="tab1_date"
        )

    target_dt = selected_date.strftime("%Y%m%d")
    df_daily, err_msg = fetch_box_office(target_dt)

    if err_msg or df_daily is None:
        st.warning(f"⚠️ {err_msg if err_msg else '그날은 아직 집계 전입니다.'}")
    else:
        df_daily = process_box_office_df(df_daily)

        # 1위 영화 지표 카드
        top_movie = df_daily.iloc[0]
        st.subheader(f"🥇 1위 영화: {top_movie['movieNm_formatted']}")

        col1, col2, col3 = st.columns(3)
        col1.metric("당일 관객수", f"{int(top_movie['audiCnt']):,} 명", delta=top_movie["rankChange"])
        col2.metric("누적 관객수", f"{int(top_movie['audiAcc']):,} 명")
        col3.metric("스크린 수", f"{int(top_movie['scrnCnt']):,} 개")

        st.markdown("---")

        # 당일 관객수 상위 5개 영화 막대그래프 (파스텔 보라색 적용: #B39DDB)
        st.subheader("📊 관객수 상위 5개 영화")
        top5_df = df_daily.head(5).copy()
        chart_data = top5_df[["movieNm", "audiCnt"]].set_index("movieNm")
        chart_data.columns = ["관객수"]
        st.bar_chart(chart_data, color="#B39DDB")

        st.markdown("---")

        # 선택 영화의 최근 7일간 관객수 추이 그래프 (파스텔 연보라색 적용: #9FA8DA)
        st.subheader("📈 선택 영화의 최근 7일 관객수 추이")
        movie_list = df_daily["movieNm"].tolist()
        selected_movie = st.selectbox("추이를 확인할 영화를 선택하세요", movie_list)

        if selected_movie:
            trend_data = []
            for i in range(6, -1, -1):
                past_date = selected_date - timedelta(days=i)
                past_dt_str = past_date.strftime("%Y%m%d")
                df_past, _ = fetch
