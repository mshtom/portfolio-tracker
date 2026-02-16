import streamlit as st
import pandas as pd
import os
from datetime import datetime, timedelta
from pykrx import stock

# ---------------------------------------------------------------------------
# 설정
# ---------------------------------------------------------------------------
PORTFOLIO_PATH = os.path.join(os.path.dirname(__file__), "data", "portfolio.csv")
CSV_COLUMNS = ["종목명", "티커", "구매단가", "보유수량"]

st.set_page_config(page_title="연금 ETF 포트폴리오 트래커", page_icon="📊", layout="wide")

st.markdown(
    """
    <style>
    .metric-card {
        background: #f8f9fa;
        border-radius: 12px;
        padding: 20px 24px;
        text-align: center;
        border: 1px solid #e9ecef;
    }
    .metric-card h3 {
        margin: 0 0 4px 0;
        font-size: 14px;
        color: #868e96;
        font-weight: 500;
    }
    .metric-card p {
        margin: 0;
        font-size: 24px;
        font-weight: 700;
    }
    .positive { color: #e03131; }
    .negative { color: #1971c2; }
    .neutral  { color: #343a40; }
    </style>
    """,
    unsafe_allow_html=True,
)


# ---------------------------------------------------------------------------
# 유틸리티 함수
# ---------------------------------------------------------------------------
def load_portfolio() -> pd.DataFrame:
    """portfolio.csv를 읽어 DataFrame으로 반환한다. 파일이 없으면 빈 DataFrame."""
    if os.path.exists(PORTFOLIO_PATH):
        df = pd.read_csv(PORTFOLIO_PATH, encoding="utf-8-sig", dtype={"티커": str})
        return df
    return pd.DataFrame(columns=CSV_COLUMNS)


def save_portfolio(df: pd.DataFrame) -> None:
    """DataFrame을 portfolio.csv로 저장한다."""
    os.makedirs(os.path.dirname(PORTFOLIO_PATH), exist_ok=True)
    df.to_csv(PORTFOLIO_PATH, index=False, encoding="utf-8-sig")


def lookup_ticker_name(ticker: str) -> str | None:
    """pykrx로 티커에 해당하는 종목명을 조회한다."""
    try:
        name = stock.get_etf_ticker_name(ticker)
        if name:
            return name
        name = stock.get_market_ticker_name(ticker)
        return name if name else None
    except Exception:
        return None


def _nearest_trading_date() -> str:
    """가장 최근 거래일(YYYYMMDD)을 반환한다."""
    today = datetime.now()
    for offset in range(7):
        date_str = (today - timedelta(days=offset)).strftime("%Y%m%d")
        ohlcv = stock.get_etf_ohlcv_by_date(date_str, date_str, "069500")
        if not ohlcv.empty:
            return date_str
    return today.strftime("%Y%m%d")


def get_current_price(ticker: str) -> int | None:
    """pykrx로 현재가(종가)를 조회한다."""
    try:
        date_str = _nearest_trading_date()
        df = stock.get_etf_ohlcv_by_date(date_str, date_str, ticker)
        if not df.empty:
            return int(df.iloc[-1]["종가"])
        df = stock.get_market_ohlcv(date_str, date_str, ticker)
        if not df.empty:
            return int(df.iloc[-1]["종가"])
    except Exception:
        pass
    return None


def fmt_krw(value: int | float) -> str:
    """원화 포맷: ₩1,234,567"""
    return f"₩{int(value):,}"


def fmt_rate(value: float) -> str:
    """수익률 포맷: +12.34% / -5.67%"""
    sign = "+" if value >= 0 else ""
    return f"{sign}{value:.2f}%"


# ---------------------------------------------------------------------------
# 사이드바 – 종목 입력
# ---------------------------------------------------------------------------
st.sidebar.title("종목 추가")

ticker_input = st.sidebar.text_input("ETF 티커 코드", placeholder="예: 069500")

if ticker_input:
    resolved_name = lookup_ticker_name(ticker_input)
    if resolved_name:
        st.sidebar.success(f"종목명: **{resolved_name}**")
    else:
        st.sidebar.error("종목명을 찾을 수 없습니다. 티커를 확인해주세요.")

buy_price = st.sidebar.number_input("구매 단가 (원)", min_value=0, step=1, format="%d")
quantity = st.sidebar.number_input("보유 수량 (주)", min_value=0, step=1, format="%d")

if st.sidebar.button("종목 추가", use_container_width=True):
    if not ticker_input:
        st.sidebar.warning("티커 코드를 입력해주세요.")
    elif buy_price <= 0:
        st.sidebar.warning("구매 단가를 입력해주세요.")
    elif quantity <= 0:
        st.sidebar.warning("보유 수량을 입력해주세요.")
    else:
        name = lookup_ticker_name(ticker_input)
        if name is None:
            st.sidebar.error("유효하지 않은 티커입니다.")
        else:
            df = load_portfolio()
            new_row = pd.DataFrame(
                [{"종목명": name, "티커": ticker_input, "구매단가": int(buy_price), "보유수량": int(quantity)}]
            )
            df = pd.concat([df, new_row], ignore_index=True)
            save_portfolio(df)
            st.sidebar.success(f"**{name}** 종목이 추가되었습니다.")
            st.rerun()

st.sidebar.divider()

if st.sidebar.button("시세 새로고침", use_container_width=True):
    st.cache_data.clear()
    st.rerun()

# ---------------------------------------------------------------------------
# 메인 화면
# ---------------------------------------------------------------------------
st.title("연금 ETF 포트폴리오 트래커")

portfolio = load_portfolio()

if portfolio.empty:
    st.info("등록된 종목이 없습니다. 사이드바에서 종목을 추가해주세요.")
    st.stop()

# 현재가 조회 및 수익률 계산
rows: list[dict] = []
errors: list[str] = []

progress = st.progress(0, text="시세 조회 중...")
total = len(portfolio)

for idx, row in portfolio.iterrows():
    progress.progress((idx + 1) / total, text=f"시세 조회 중... ({idx + 1}/{total})")
    ticker = str(row["티커"])
    price = get_current_price(ticker)
    if price is None:
        errors.append(f"{row['종목명']}({ticker})")
        price = 0

    buy_total = int(row["구매단가"]) * int(row["보유수량"])
    eval_total = price * int(row["보유수량"])
    rate = ((eval_total - buy_total) / buy_total * 100) if buy_total > 0 else 0.0

    rows.append(
        {
            "종목명": row["종목명"],
            "티커": ticker,
            "구매단가": int(row["구매단가"]),
            "현재가": price,
            "보유수량": int(row["보유수량"]),
            "매수금액": buy_total,
            "평가액": eval_total,
            "수익률": rate,
        }
    )

progress.empty()

if errors:
    st.warning(f"다음 종목의 시세를 조회하지 못했습니다: {', '.join(errors)}")

result = pd.DataFrame(rows)

# 표 표시
display = result.copy()
display["구매단가"] = display["구매단가"].apply(fmt_krw)
display["현재가"] = display["현재가"].apply(fmt_krw)
display["매수금액"] = display["매수금액"].apply(fmt_krw)
display["평가액"] = display["평가액"].apply(fmt_krw)
display["보유수량"] = display["보유수량"].apply(lambda x: f"{x:,}주")
display["수익률"] = display["수익률"].apply(fmt_rate)

st.dataframe(
    display,
    use_container_width=True,
    hide_index=True,
    column_config={
        "종목명": st.column_config.TextColumn("종목명", width="medium"),
        "티커": st.column_config.TextColumn("티커", width="small"),
    },
)

# 요약 카드
total_invested = int(result["매수금액"].sum())
total_eval = int(result["평가액"].sum())
total_profit = total_eval - total_invested
total_rate = (total_profit / total_invested * 100) if total_invested > 0 else 0.0

rate_class = "positive" if total_rate > 0 else ("negative" if total_rate < 0 else "neutral")
profit_class = rate_class

st.markdown("---")

c1, c2, c3, c4 = st.columns(4)

with c1:
    st.markdown(
        f'<div class="metric-card"><h3>총 투자금</h3><p class="neutral">{fmt_krw(total_invested)}</p></div>',
        unsafe_allow_html=True,
    )
with c2:
    st.markdown(
        f'<div class="metric-card"><h3>현재 평가액</h3><p class="neutral">{fmt_krw(total_eval)}</p></div>',
        unsafe_allow_html=True,
    )
with c3:
    st.markdown(
        f'<div class="metric-card"><h3>총 수익금</h3><p class="{profit_class}">{fmt_krw(total_profit)}</p></div>',
        unsafe_allow_html=True,
    )
with c4:
    st.markdown(
        f'<div class="metric-card"><h3>총 수익률</h3><p class="{rate_class}">{fmt_rate(total_rate)}</p></div>',
        unsafe_allow_html=True,
    )
