from datetime import datetime, timedelta, timezone
import requests
import pandas as pd
import streamlit as st

# -----------------------------------------------------------------------------
# 1. 페이지 기본 설정 및 제목 표시
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="어제 일별 박스오피스",
    page_icon="🎬",
    layout="wide"
)

st.title("🎬 어제일자 일별 박스오피스")
st.caption("영화진흥위원회(KOBIS) Open API를 활용하여 한국 시간 기준 어제의 박스오피스 데이터를 보여줍니다.")


# -----------------------------------------------------------------------------
# 2. 날짜 및 인증키 준비
# -----------------------------------------------------------------------------
# (1) 배포 서버의 시계와 상관없이 '한국 표준시(KST: UTC+9)' 기준 '어제' 날짜 계산
kst = timezone(timedelta(hours=9))
now_kst = datetime.now(timezone.utc).astimezone(kst)
yesterday_kst = now_kst - timedelta(days=1)
target_dt = yesterday_kst.strftime("%Y%m%d")  # YYYYMMDD 포맷 (예: 20261020)
formatted_date = yesterday_kst.strftime("%Y년 %m월 %d일")

st.info(f"📅 조회 기준일: **{formatted_date}** (어제 기준)")

# (2) Streamlit Secrets에서 API 인증키 불러오기 (.streamlit/secrets.toml 또는 Cloud Secrets 설정)
if "KOBIS_KEY" not in st.secrets or not st.secrets["KOBIS_KEY"]:
    st.error("🚨 API 인증키(KOBIS_KEY)가 설정되지 않았습니다.")
    st.markdown("""
    **해결 방법:**
    1. **로컬 실행 시**: 프로젝트 폴더 안 `.streamlit/secrets.toml` 파일에 `KOBIS_KEY = "발급받은키"` 를 추가해 주세요.
    2. **Streamlit Cloud 배포 시**: App Settings -> Secrets 메뉴에서 `KOBIS_KEY = "발급받은키"` 를 등록해 주세요.
    """)
    st.stop()  # 키가 없으면 아래 로직을 실행하지 않고 중단

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
    # API 서버에 GET 요청 보내기 (타임아웃 10초 설정)
    response = requests.get(url, params=params, timeout=10)
    response.raise_for_status()  # HTTP status code 오류 체크 (4xx, 5xx)
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
# (1) KOBIS 특이사항: 인증키 오류 등의 예외 발생 시 상태코드 200과 함께 faultInfo 객체가 반환됨
if "faultInfo" in data:
    fault = data["faultInfo"]
    st.error(f"🚨 API 오류 발생: [{fault.get('errorCode', 'UNKNOWN')}] {fault.get('message', '인증 에러가 발생했습니다.')}")
    st.markdown("""
    **확인해 주세요:**
    - `secrets`에 입력한 `KOBIS_KEY`가 올바른지 확인해 주세요.
    - 영화진흥위원회 개발자 센터에서 키 발급 및 활성화 상태를 확인해 주세요.
    """)
    st.stop()

# (2) boxOfficeResult 내부 결과 검증 및 데이터 존재 여부 확인
box_office_result = data.get("boxOfficeResult", {})
daily_list = box_office_result.get("dailyBoxOfficeList", [])

if not daily_list:
    st.warning("⚠️ 해당 날짜의 박스오피스 데이터가 비어 있습니다.")
    st.markdown("""
    **확인해 주세요:**
    - 아직 집계가 완료되지 않은 시점이거나 데이터 업데이트 전일 수 있습니다.
    - 날짜 지정 조건(`targetDt`)을 확인해 주세요.
    """)
    st.stop()


# -----------------------------------------------------------------------------
# 5. 데이터 가공 (Pandas DataFrame)
# -----------------------------------------------------------------------------
# API 응답 결과는 모든 숫자가 문자열로 반환되므로 숫자형 변환 필수
df = pd.DataFrame(daily_list)

# 필요한 숫자 컬럼 변환
num_cols = ["rank", "rankInten", "audiCnt", "audiAcc", "scrnCnt", "showCnt"]
for col in num_cols:
    if col in df.columns:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

# 순위 오름차순 정렬
df = df.sort_values("rank")


# -----------------------------------------------------------------------------
# 6. 대시보드 화면 구성
# -----------------------------------------------------------------------------

# --- [시각화 1] 1위 영화 주요 지표 카드 (st.metric) ---
top_movie = df.iloc[0]

# 순위 변동 텍스트/표시 구성
rank_inten = int(top_movie["rankInten"])
if rank_inten > 0:
    rank_delta = f"▲ {rank_inten}"
elif rank_inten < 0:
    rank_delta = f"▼ {abs(rank_inten)}"
else:
    rank_delta = "변동 없음"

st.subheader(f"🥇 1위 영화: {top_movie['movieNm']}")

col1, col2, col3 = st.columns(3)
with col1:
    st.metric(
        label="어제 관객수",
        value=f"{int(top_movie['audiCnt']):,} 명",
        delta=rank_delta
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
# Streamlit 막대그래프 x축/y축 설정을 위해 필요한 컬럼만 추출 및 인덱스 지정
chart_data = top5_df[["movieNm", "audiCnt"]].set_index("movieNm")
chart_data.columns = ["관객수"]

st.bar_chart(chart_data)

st.markdown("---")

# --- [시각화 3] 전체 박스오피스 상세 표 (st.dataframe) ---
st.subheader("📋 전체 박스오피스 순위표")

# 표에 출력할 컬럼 선택 및 보기 좋은 이름으로 변경
display_df = df[[
    "rank", 
    "movieNm", 
    "openDt", 
    "audiCnt", 
    "audiAcc", 
    "scrnCnt"
]].copy()

display_df.columns = [
    "순위", 
    "영화명", 
    "개봉일", 
    "관객수(명)", 
    "누적관객수(명)", 
    "스크린수(개)"
]

# 데이터프레임 스타일링 (천 단위 쉼표 추가)
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
