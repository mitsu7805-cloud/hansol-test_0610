import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime, timedelta
from openai import OpenAI

# 국내 주요 주식 10개 (티커: 종목명)
STOCKS = {
    "005930.KS": "삼성전자",
    "000660.KS": "SK하이닉스",
    "005380.KS": "현대차",
    "035420.KS": "NAVER",
    "051910.KS": "LG화학",
    "006400.KS": "삼성SDI",
    "035720.KS": "카카오",
    "068270.KS": "셀트리온",
    "105560.KS": "KB금융",
    "055550.KS": "신한지주",
}

st.set_page_config(
    page_title="국내 주식 대시보드",
    page_icon="📈",
    layout="wide",
)

# 세션 상태 초기화
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []

st.title("📈 국내 주요 주식 대시보드")
st.caption("yfinance 기반 · KOSPI 주요 10종목")

# 사이드바 설정
st.sidebar.header("⚙️ 설정")

# API Key 입력
st.sidebar.subheader("🤖 AI 챗봇 설정")
api_key = st.sidebar.text_input("OpenAI API Key", type="password", placeholder="sk-...")
period_options = {"1개월": "1mo", "3개월": "3mo", "6개월": "6mo", "1년": "1y", "2년": "2y"}
selected_period_label = st.sidebar.selectbox("조회 기간", list(period_options.keys()), index=2)
period = period_options[selected_period_label]

selected_names = st.sidebar.multiselect(
    "종목 선택",
    options=list(STOCKS.values()),
    default=list(STOCKS.values()),
)
selected_tickers = [t for t, n in STOCKS.items() if n in selected_names]

# 데이터 로드
@st.cache_data(ttl=300)
def load_data(tickers: list, period: str):
    raw = yf.download(tickers, period=period, auto_adjust=True, progress=False)
    return raw

if not selected_tickers:
    st.warning("사이드바에서 종목을 하나 이상 선택하세요.")
    st.stop()

with st.spinner("데이터 수집 중..."):
    data = load_data(selected_tickers, period)

close = data["Close"] if len(selected_tickers) > 1 else data[["Close"]].rename(columns={"Close": selected_tickers[0]})

# ── 요약 카드 ──────────────────────────────────────────────────────────────
st.subheader("현재가 요약")
cols = st.columns(len(selected_tickers))
for col, ticker in zip(cols, selected_tickers):
    name = STOCKS[ticker]
    series = close[ticker].dropna()
    if series.empty:
        col.metric(name, "N/A")
        continue
    current = series.iloc[-1]
    prev = series.iloc[-2] if len(series) > 1 else current
    delta = current - prev
    delta_pct = delta / prev * 100
    col.metric(
        label=name,
        value=f"{current:,.0f}원",
        delta=f"{delta_pct:+.2f}%",
    )

st.divider()

# ── 주가 추이 차트 ──────────────────────────────────────────────────────────
st.subheader("📊 주가 추이 (정규화 · 기준일=100)")
norm = close.div(close.iloc[0]) * 100
fig_line = px.line(
    norm,
    labels={"value": "지수 (기준=100)", "variable": "종목"},
    color_discrete_sequence=px.colors.qualitative.Set2,
)
fig_line.update_layout(
    legend=dict(orientation="h", y=-0.2),
    hovermode="x unified",
    height=420,
)
# 범례 이름을 한글로 변경
for trace in fig_line.data:
    trace.name = STOCKS.get(trace.name, trace.name)
st.plotly_chart(fig_line, use_container_width=True)

st.divider()

# ── 수익률 비교 바 차트 ──────────────────────────────────────────────────────
st.subheader("📊 기간 수익률 비교")
returns = ((close.iloc[-1] - close.iloc[0]) / close.iloc[0] * 100).rename("수익률(%)")
returns.index = [STOCKS.get(t, t) for t in returns.index]
returns = returns.sort_values(ascending=False)

colors = ["#e74c3c" if v < 0 else "#2ecc71" for v in returns]
fig_bar = go.Figure(go.Bar(
    x=returns.index,
    y=returns.values,
    marker_color=colors,
    text=[f"{v:.1f}%" for v in returns.values],
    textposition="outside",
))
fig_bar.update_layout(
    yaxis_title="수익률 (%)",
    xaxis_title="",
    height=380,
    showlegend=False,
)
st.plotly_chart(fig_bar, use_container_width=True)

st.divider()

# ── 거래량 히트맵 ──────────────────────────────────────────────────────────
st.subheader("📊 월별 평균 거래량 히트맵")
volume = data["Volume"] if len(selected_tickers) > 1 else data[["Volume"]].rename(columns={"Volume": selected_tickers[0]})
volume.columns = [STOCKS.get(t, t) for t in volume.columns]
vol_monthly = volume.resample("ME").mean()
vol_monthly.index = vol_monthly.index.strftime("%Y-%m")

fig_heat = px.imshow(
    vol_monthly.T,
    color_continuous_scale="Blues",
    labels=dict(color="평균 거래량"),
    aspect="auto",
)
fig_heat.update_layout(height=320)
st.plotly_chart(fig_heat, use_container_width=True)

st.divider()

# ── 개별 캔들스틱 ──────────────────────────────────────────────────────────
st.subheader("🕯️ 개별 종목 캔들스틱")
candle_name = st.selectbox("종목 선택", selected_names)
candle_ticker = [t for t, n in STOCKS.items() if n == candle_name][0]

ohlc = data[["Open", "High", "Low", "Close"]].xs(candle_ticker, axis=1, level=1) if len(selected_tickers) > 1 else data[["Open", "High", "Low", "Close"]]
ohlc = ohlc.dropna()

fig_candle = go.Figure(go.Candlestick(
    x=ohlc.index,
    open=ohlc["Open"],
    high=ohlc["High"],
    low=ohlc["Low"],
    close=ohlc["Close"],
    increasing_line_color="#e74c3c",
    decreasing_line_color="#2980b9",
    name=candle_name,
))
fig_candle.update_layout(
    title=f"{candle_name} 캔들스틱 차트",
    yaxis_title="주가 (원)",
    xaxis_rangeslider_visible=True,
    height=480,
)
st.plotly_chart(fig_candle, use_container_width=True)

st.divider()

# ── 원본 데이터 테이블 ────────────────────────────────────────────────────
with st.expander("📋 원본 종가 데이터 보기"):
    display = close.copy()
    display.columns = [STOCKS.get(t, t) for t in display.columns]
    display.index = display.index.strftime("%Y-%m-%d")
    st.dataframe(display.style.format("{:,.0f}"), use_container_width=True)

st.caption(f"데이터 출처: Yahoo Finance · 마지막 업데이트: {datetime.now().strftime('%Y-%m-%d %H:%M')}")

st.divider()

# ── AI 챗봇 ──────────────────────────────────────────────────────────────────
st.subheader("🤖 AI 주식 분석 챗봇")

if not api_key:
    st.info("사이드바에 OpenAI API Key를 입력하면 챗봇을 사용할 수 있습니다.")
else:
    # 주식 데이터 요약 생성 (시스템 프롬프트용 컨텍스트)
    def build_stock_context():
        lines = [f"오늘 날짜: {datetime.now().strftime('%Y-%m-%d')}",
                 f"조회 기간: {selected_period_label}", ""]
        lines.append("=== 현재가 및 기간 수익률 ===")
        for ticker in selected_tickers:
            name = STOCKS[ticker]
            series = close[ticker].dropna()
            if series.empty:
                continue
            cur = series.iloc[-1]
            prev = series.iloc[-2] if len(series) > 1 else cur
            day_chg = (cur - prev) / prev * 100
            total_chg = (series.iloc[-1] - series.iloc[0]) / series.iloc[0] * 100
            lines.append(f"- {name}({ticker}): 현재가 {cur:,.0f}원 | 전일대비 {day_chg:+.2f}% | 기간수익률 {total_chg:+.2f}%")

        lines.append("")
        lines.append("=== 기간 수익률 순위 ===")
        sorted_returns = returns.sort_values(ascending=False)
        for i, (name, val) in enumerate(sorted_returns.items(), 1):
            lines.append(f"{i}위. {name}: {val:+.2f}%")

        return "\n".join(lines)

    SYSTEM_PROMPT = f"""당신은 주식 분석 전문가 AI입니다.
아래 실시간 수집된 국내 주요 주식 데이터를 바탕으로 사용자 질문에 답하세요.
데이터 범위를 벗어나는 질문은 데이터 한계를 솔직히 밝히고 일반적인 투자 관점에서 답하세요.
답변은 핵심 위주로 간결하게 작성하되, 수치를 근거로 활용하세요.

{build_stock_context()}
"""

    def ask_gpt(user_message: str) -> str:
        client = OpenAI(api_key=api_key)
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        for msg in st.session_state.chat_history:
            messages.append(msg)
        messages.append({"role": "user", "content": user_message})

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            temperature=0.7,
        )
        return response.choices[0].message.content

    # 대화 기록 출력
    for msg in st.session_state.chat_history:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    # 입력창
    if prompt := st.chat_input("주식에 대해 질문하세요. 예) 가장 수익률 높은 종목은?"):
        st.session_state.chat_history.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        with st.chat_message("assistant"):
            with st.spinner("분석 중..."):
                try:
                    answer = ask_gpt(prompt)
                    st.markdown(answer)
                    st.session_state.chat_history.append({"role": "assistant", "content": answer})
                except Exception as e:
                    err = f"오류 발생: {e}"
                    st.error(err)

    if st.session_state.chat_history:
        if st.button("대화 초기화"):
            st.session_state.chat_history = []
            st.rerun()
