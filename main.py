from datetime import datetime, timedelta, timezone
import requests
import pandas as pd
import streamlit as st

# -----------------------------------------------------------------------------
# 1. 페이지 기본 설정 및 제목 표시
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="일별 박스오피스",
    page_icon="🎬",
    layout="wide"
)

st.title("🎬 일별 박스오피스 조회")
st.caption("영화진흥위원회(KOBIS) Open API를 활용하여 날짜별 박스오피스 데이터를 보여줍니다.")


# -----------------------------------------------------------------------------
# 2. 날짜 선택 및 인증키 준비
# -----------------------------------------------------------------------------
# (1) 배포 서버의 시계와 상관없이 '한국 표준시(KST: UTC+9)' 기준 '어제' 날짜 계산 (최대 선택 가능 날짜)
kst = timezone(timedelta(hours=9))
now_kst = datetime.now(timezone.utc).astimezone(kst)
yesterday_kst = (now_kst - timedelta(days=1)).date()

# (2) 달력 UI 제공 (선택 가능한 최대 날짜는 어제까지로 제한)
selected_date = st.date_input(
    "📅 조회할 날짜를 선택하세요",
    value=yesterday_kst,
    max_value=yesterday_kst
)

# API 요청에 맞게 YYYYMMDD 포맷 변환 (예: 20261020)
target_dt = selected_date.strftime("%Y%m%d")
formatted_date = selected_date.strftime("%Y년 %m월 %d일")

st.info(f"선택한 날짜: **{formatted_date}**")

# (3) Streamlit Secrets에서 API 인증키 검증 및 불러오기
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
# 3. KOBIS API 데이터 요청
# -----------------------------------------------------------------------------
url = "https://www.kobis.or.kr/kobisopenapi/webservice/rest/boxoffice/searchDailyBoxOfficeList.json"
params = {
    "key": api_key,
    "targetDt": target_dt
}

try:
    response = requests.get(url, params=params, timeout=10)
    response.raise_for_status()
    data = response.json()
    
except requests.exceptions.RequestException as e:
    st.error("🚨 KOBIS API 서버와의 통신 중 에러가 발생했습니다.")
    st.caption(f"상세 에러 내용: {e}")
    st.markdown("""
    **확인해 주세요:**
    - 인터넷 연결 상태를 확인해 주세요.
    - KOBIS API 서비스 점검 중인지 확인해 주세요.
    """)
    st.stop()


# -----------------------------------------------------------------------------
# 4. API 응답 검증 및 예외 처리
# -----------------------------------------------------------------------------
# (1) KOBIS 특이사항: 인증키 오류 등의 예외 발생 시 faultInfo 반환
if "faultInfo" in data:
    fault = data["faultInfo"]
    st.error(f"🚨 API 오류 발생: [{fault.get('errorCode', 'UNKNOWN')}] {fault.get('message', '인증 에러가 발생했습니다.')}")
    st.markdown("""
    **확인해 주세요:**
    - Secrets에 등록된 `KOBIS_KEY` 값에 오타나 공백이 없는지 확인해 주세요.
    - 영화진흥위원회 개발자 센터에서 키 발급 및 활성화 상태를 확인해 주세요.
    """)
    st.stop()

# (2) boxOfficeResult 내부 결과 검증 및 데이터 존재 여부 확인
box_office_result = data.get("boxOfficeResult", {})
daily_list = box_office_result.get("dailyBoxOfficeList", [])

if not daily_list:
    st.warning("⚠️ 그날은 아직 집계 전입니다.")
    st.markdown("""
    **확인해 주세요:**
    - 해당 날짜의 데이터가 아직 집계되지 않았거나 업데이트 전일 수 있습니다.
    - 다른 날짜를 선택하여 다시 조회해 보세요.
    """)
    st.stop()


# -----------------------------------------------------------------------------
# 5. 데이터 가공 및 요구사항 적용 (Pandas DataFrame)
# -----------------------------------------------------------------------------
df = pd.DataFrame(daily_list)

# 숫자 컬럼 변환 (문자열 -> 숫자)
num_cols = ["rank", "rankInten", "audiCnt", "audiAcc", "scrnCnt", "showCnt"]
for col in num_cols:
    if col in df.columns:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

# 순위 오름차순 정렬
df = df.sort_values("rank")

# --- 요구사항 1: 누적관객 100만 명(1,000,000명) 이상 영화명에 트로피 이모지(🏆) 추가 ---
def format_movie_name(row):
    name = row["movieNm"]
    if row["audiAcc"] >= 1_000_000:
        return f"🏆 {name}"
    return name

df["movieNm_formatted"] = df.apply(format_movie_name, axis=1)

# --- 요구사항 2: 순위 증감(rankInten)에 따라 빨간 위 화살표 / 파란 아래 화살표 표기 ---
def format_rank_change(inten):
    inten = int(inten)
    if inten > 0:
        return f"🔺 +{inten}"  # 순위 상승 (빨간 위 화살표)
    elif inten < 0:
        return f"🔷 -{abs(inten)}"  # 순위 하강 (파란 아래 화살표)
    return "-"  # 변동 없음

df["rankChange"] = df["rankInten"].apply(format_rank_change)


# -----------------------------------------------------------------------------
# 6. 대시보드 화면 구성
# -----------------------------------------------------------------------------

# --- [시각화 1] 1위 영화 주요 지표 카드 (st.metric) ---
top_movie = df.iloc[0]

st.subheader(f"🥇 1위 영화: {top_movie['movieNm_formatted']}")

col1, col2, col3 = st.columns(3)
with col1:
    st.metric(
        label="당일 관객수",
        value=f"{int(top_movie['audiCnt']):,} 명",
        delta=top_movie["rankChange"]
    )
with col2:
    st.metric(
        label="누적 관객수",
        value=f"{int(top_movie['audiAcc']):,} 명"
    )
with col3:
    st.metric(
        label="스크린 수",
        value=f"{int(top_movie['scrnCnt']):,} 개"
    )

st.markdown("---")

# --- [시각화 2] 관객수 상위 5편 막대그래프 (st.bar_chart) ---
st.subheader("📊 관객수 상위 5개 영화")

top5_df = df.head(5).copy()
chart_data = top5_df[["movieNm", "audiCnt"]].set_index("movieNm")
chart_data.columns = ["관객수"]

st.bar_chart(chart_data)

st.markdown("---")

# --- [시각화 3] 전체 박스오피스 상세 표 (st.dataframe) ---
st.subheader("📋 전체 박스오피스 순위표")

display_df = df[[
    "rank", 
    "rankChange",
    "movieNm_formatted", 
    "openDt", 
    "audiCnt", 
    "audiAcc", 
    "scrnCnt"
]].copy()

display_df.columns = [
    "순위", 
    "순위 증감",
    "영화명", 
    "개봉일", 
    "관객수(명)", 
    "누적관객수(명)", 
    "스크린수(개)"
]

st.dataframe(
    display_df,
    use_container_width=True,
    hide_index=True,
    column_config={
        "순위": st.column_config.NumberColumn(format="%d"),
        "관객수(명)": st.column_config.NumberColumn(format="%'d"),
        "누적관객수(명)": st.column_config.NumberColumn(format="%'d"),
        "스크린수(개)": st.column_config.NumberColumn(format="%'d")
    }
)
