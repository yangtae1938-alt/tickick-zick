import re
from urllib.parse import quote
import numpy as np
import pandas as pd
import requests
import streamlit as st
import yfinance as yf

st.set_page_config(page_title="찍찍 급등 전 레이더", page_icon="🐹", layout="wide")
st.markdown("""
<style>
.block-container{padding-top:1rem;max-width:1200px}
[data-testid="stMetric"]{background:rgba(128,128,128,.08);padding:.65rem;border-radius:.75rem}
</style>
""", unsafe_allow_html=True)

st.title("🐹 찍찍 급등 전 레이더")
st.caption("미국 소형주 · 거래량 선행 신호 · SEC 공시 탐색 · 희석 위험 예비 스캔")
st.warning("MVP/시제품입니다. 시세는 Yahoo Finance를 통해 제공되며 지연·누락될 수 있습니다. SEC 키워드 탐색은 법률적 판정이 아닙니다. 점수는 급등 확률이 아니며 투자 권유가 아닙니다.")

DEFAULT = "SOUN, BBAI, KULR, LUNR, RGTI, QNRX, CLDI, ALBT, FGI, PLAG, VCIG, WHLR, OCGN"
with st.sidebar:
    st.header("스캔 설정")
    ticker_text = st.text_area("감시 티커 (쉼표 또는 줄바꿈)", DEFAULT, height=150)
    min_price = st.number_input("최저 주가 ($)", 0.01, 1000.0, 0.50, 0.10)
    max_price = st.number_input("최고 주가 ($)", 0.10, 10000.0, 10.0, 0.50)
    max_cap_m = st.number_input("최대 시가총액 ($M)", 1, 1000000, 300, 25)
    max_float_m = st.number_input("최대 유통주식 (M; 미확인은 보류)", 0.1, 10000.0, 10.0, 0.5)
    min_dollar_vol_m = st.number_input("최소 20일 평균 거래대금 ($M)", 0.0, 10000.0, 0.5, 0.1)
    include_unknown_float = st.checkbox("유통주식 수 미확인 종목도 표시", True)
    run = st.button("🔎 지금 스캔", type="primary", use_container_width=True)
    st.caption("기본 목록은 예시 감시목록입니다. 전체 미국 종목 자동 발굴에는 별도 종목 universe 데이터 공급자가 필요합니다.")

SEC_UA = {"User-Agent": "TickTickSpikeScanner contact admin@example.com", "Accept-Encoding": "gzip, deflate"}

@st.cache_data(ttl=900, show_spinner=False)
def get_sec_ticker_map():
    url = "https://www.sec.gov/files/company_tickers.json"
    r = requests.get(url, headers=SEC_UA, timeout=20)
    r.raise_for_status()
    data = r.json()
    return {str(v["ticker"]).upper(): str(v["cik_str"]).zfill(10) for v in data.values()}

@st.cache_data(ttl=600, show_spinner=False)
def get_sec_recent(cik):
    url = f"https://data.sec.gov/submissions/CIK{cik}.json"
    r = requests.get(url, headers=SEC_UA, timeout=20)
    r.raise_for_status()
    recent = r.json().get("filings", {}).get("recent", {})
    rows = []
    n = len(recent.get("form", []))
    for i in range(min(n, 40)):
        rows.append({
            "date": recent.get("filingDate", [""])[i],
            "form": recent.get("form", [""])[i],
            "accession": recent.get("accessionNumber", [""])[i],
            "primary": recent.get("primaryDocument", [""])[i],
            "description": recent.get("primaryDocDescription", [""])[i] if i < len(recent.get("primaryDocDescription", [])) else ""
        })
    return rows

def sec_url(cik, accession, primary):
    return f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession.replace('-', '')}/{quote(primary)}"

def technical_score(hist):
    if hist is None or hist.empty or len(hist) < 8:
        return 0, ["일봉 데이터 부족"], {}
    h = hist.dropna(subset=["Close", "Volume"]).copy()
    close, vol = h["Close"].astype(float), h["Volume"].astype(float)
    if len(h) < 8:
        return 0, ["유효 데이터 부족"], {}
    p = float(close.iloc[-1])
    avg_vol = float(vol.iloc[-21:-1].mean()) if len(vol) > 2 else 0
    rvol = float(vol.iloc[-1] / avg_vol) if avg_vol > 0 else np.nan
    avg_dollar = float((close.iloc[-21:-1] * vol.iloc[-21:-1]).mean()) if len(h) > 2 else np.nan
    ret5 = float(p / close.iloc[-6] - 1) if len(close) >= 6 and close.iloc[-6] else 0
    rng5 = float((h["High"].tail(5).max() - h["Low"].tail(5).min()) / p) if p else 1
    high20 = float(h["High"].tail(20).max())
    dist_high = float(p / high20 - 1) if high20 else 0
    day_range = float(h["High"].iloc[-1] - h["Low"].iloc[-1])
    clv = float((p - h["Low"].iloc[-1]) / day_range) if day_range > 0 else 0.5
    score, signals = 0, []
    if np.isfinite(rvol) and rvol >= 1.5:
        score += 8; signals.append(f"일 거래량 RVOL {rvol:.2f}x")
    if np.isfinite(rvol) and rvol >= 2.5:
        score += 5; signals.append("거래량 급증")
    if -0.08 <= ret5 <= 0.12 and rng5 <= 0.22:
        score += 8; signals.append("최근 5일 가격 압축/횡보")
    if clv >= 0.75:
        score += 5; signals.append("당일 범위 상단 마감")
    if -0.06 <= dist_high <= 0.01:
        score += 5; signals.append("20일 고점 접근")
    if ret5 > 0.25:
        score -= 5; signals.append("이미 급등했을 가능성")
    return max(0, min(30, score)), signals or ["뚜렷한 선행 신호 없음"], {
        "price": p, "rvol": rvol, "avg_dollar": avg_dollar, "ret5": ret5,
        "range5": rng5, "dist_high": dist_high, "clv": clv
    }

def filing_flags(rows):
    risk, tags, links = 0, [], []
    for x in rows[:30]:
        form, date = x["form"], x["date"]
        desc, primary = x["description"], x["primary"]
        low = (form + " " + desc + " " + primary).lower()
        if form in ("S-1", "S-1/A", "S-3", "S-3/A", "F-1", "F-1/A", "F-3", "F-3/A", "424B3", "424B5"):
            risk = max(risk, 12)
            tags.append(f"{form} 등록/증권 문서 제출 ({date})")
        if form in ("8-K", "6-K", "424B5", "424B3") and any(k in low for k in ("offering", "purchase agreement", "equity line", "at the market", "convertible", "warrant", "securities purchase")):
            risk = max(risk, 15)
            tags.append(f"{form} 자금조달 관련 키워드 ({date})")
        if form == "EFFECT":
            tags.append(f"EFFECT 제출 ({date}) — 관련 등록 문서와 효력 범위 확인 필요")
        if x["accession"] and primary:
            links.append({
                "date": date, "form": form, "description": desc or primary,
                "url": sec_url(x.get("cik", ""), x["accession"], primary),
                "accession": x["accession"]
            })
    return risk, list(dict.fromkeys(tags)), links[:12]

def scan_ticker(ticker, cik_map, settings):
    out = {"ticker": ticker, "score": 0, "tech": 0, "risk": 0, "signals": [], "warnings": [], "sec_links": []}
    try:
        obj = yf.Ticker(ticker)
        hist = obj.history(period="3mo", interval="1d", auto_adjust=False, actions=True)
        if hist is None or hist.empty:
            out["warnings"].append("시세 데이터 없음")
            return out
        tech, signals, m = technical_score(hist)
        try:
            info = obj.get_info()
        except Exception:
            info = {}
        price = m.get("price", np.nan)
        cap = info.get("marketCap")
        float_sh = info.get("floatShares")
        os_sh = info.get("sharesOutstanding")
        dollar = m.get("avg_dollar")
        out.update({
            "price": price, "market_cap": cap, "float_shares": float_sh,
            "shares_outstanding": os_sh, "avg_dollar": dollar, "rvol": m.get("rvol"),
            "ret5": m.get("ret5"), "tech": tech, "signals": signals,
        })
        if not (settings["min_price"] <= price <= settings["max_price"]):
            out["warnings"].append("주가 필터 밖")
        if cap and cap > settings["max_cap_m"] * 1_000_000:
            out["warnings"].append("시가총액 필터 밖")
        if float_sh and float_sh > settings["max_float_m"] * 1_000_000:
            out["warnings"].append("유통주식 필터 밖")
        elif not float_sh:
            out["warnings"].append("Free Float 미확인")
        if dollar and dollar < settings["min_dollar_vol_m"] * 1_000_000:
            out["warnings"].append("거래대금 필터 밖")
        cik = cik_map.get(ticker)
        if cik:
            rows = get_sec_recent(cik)
            for row in rows:
                row["cik"] = cik
            risk, tags, links = filing_flags(rows)
            out["risk"] = risk
            out["sec_flags"] = tags
            out["sec_links"] = links
            out["cik"] = cik
        else:
            out["sec_flags"] = ["SEC 티커 매핑 미확인"]
            out["warnings"].append("CIK 매핑 미확인")
        out["score"] = max(0, min(100, 70 + tech - out["risk"]))
        # A high total score is not enough if key screening constraints fail.
        if any(x in out["warnings"] for x in ("주가 필터 밖", "시가총액 필터 밖", "유통주식 필터 밖", "거래대금 필터 밖")):
            out["eligible"] = False
        elif not float_sh and not settings["include_unknown_float"]:
            out["eligible"] = False
        else:
            out["eligible"] = True
    except Exception as e:
        out["warnings"].append(f"수집 오류: {str(e)[:180]}")
    return out

settings = {
    "min_price": min_price, "max_price": max_price, "max_cap_m": max_cap_m,
    "max_float_m": max_float_m, "min_dollar_vol_m": min_dollar_vol_m,
    "include_unknown_float": include_unknown_float
}
tickers = list(dict.fromkeys(re.findall(r"[A-Za-z][A-Za-z0-9.\-]*", ticker_text.upper())))
if run:
    if not tickers:
        st.error("티커를 하나 이상 입력하세요.")
    elif min_price > max_price:
        st.error("최저 주가는 최고 주가보다 낮아야 합니다.")
    else:
        results = []
        with st.spinner(f"{len(tickers)}개 티커의 시세와 SEC 제출 이력을 확인 중…"):
            try:
                cik_map = get_sec_ticker_map()
            except Exception as e:
                cik_map = {}
                st.error(f"SEC 티커 목록을 가져오지 못했습니다: {e}")
            progress = st.progress(0)
            for i, ticker in enumerate(tickers):
                results.append(scan_ticker(ticker, cik_map, settings))
                progress.progress((i + 1) / len(tickers))
        st.session_state["scan_results"] = results
        st.session_state["scan_time"] = pd.Timestamp.now(tz="UTC").strftime("%Y-%m-%d %H:%M UTC")

if "scan_results" in st.session_state:
    results = st.session_state["scan_results"]
    st.caption(f"마지막 스캔: {st.session_state.get('scan_time','—')} · 입력 {len(results)}개")
    eligible = [x for x in results if x.get("eligible", False)]
    eligible.sort(key=lambda x: (x.get("score", 0), x.get("tech", 0)), reverse=True)
    c1, c2, c3 = st.columns(3)
    c1.metric("스캔 종목", len(results))
    c2.metric("필터 통과", len(eligible))
    c3.metric("SEC/시세 확인 오류", sum(bool(x.get("warnings")) and any("오류" in w or "없음" in w for w in x["warnings"]) for x in results))
    tab1, tab2, tab3 = st.tabs(["📡 후보 레이더", "📄 SEC / 희석 위험", "🧪 방법론·한계"])
    with tab1:
        rows = []
        for x in eligible:
            rows.append({
                "티커": x["ticker"], "점수(예비)": x.get("score"),
                "가격": round(x.get("price", np.nan), 4) if pd.notna(x.get("price", np.nan)) else None,
                "RVOL": round(x.get("rvol", np.nan), 2) if pd.notna(x.get("rvol", np.nan)) else None,
                "평균 거래대금($M)": round(x.get("avg_dollar", np.nan)/1e6, 3) if pd.notna(x.get("avg_dollar", np.nan)) else None,
                "시총($M)": round(x.get("market_cap")/1e6, 2) if x.get("market_cap") else None,
                "Float(M)": round(x.get("float_shares")/1e6, 3) if x.get("float_shares") else None,
                "기술 신호 점수": x.get("tech"), "SEC 위험 키워드 감점": x.get("risk"),
                "신호": " · ".join(x.get("signals", []))
            })
        if rows:
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
            st.download_button("후보 CSV 다운로드", pd.DataFrame(rows).to_csv(index=False).encode("utf-8-sig"), "tickick_candidates.csv", "text/csv")
        else:
            st.info("필터를 통과한 후보가 없습니다. 조건을 완화하거나 티커 목록을 확인하세요.")
        with st.expander("필터에서 제외된 종목 / 데이터 오류"):
            for x in results:
                if not x.get("eligible", False):
                    st.write(f"**{x['ticker']}** — " + ("; ".join(x.get("warnings", [])) or "필터 제외"))
    with tab2:
        for x in results:
            with st.expander(f"{x['ticker']} · 예비 위험 감점 {x.get('risk',0)}점"):
                st.write("**SEC CIK:**", x.get("cik", "미확인"))
                st.write("**신호:**", " · ".join(x.get("signals", [])))
                st.write("**위험 키워드:**", " · ".join(x.get("sec_flags", ["확인 결과 없음"])) or "감지된 키워드 없음")
                st.write("**경고:**", " · ".join(x.get("warnings", [])) or "추가 경고 없음")
                if x.get("sec_links"):
                    st.dataframe(pd.DataFrame(x["sec_links"])[["date","form","description","accession","url"]], use_container_width=True, hide_index=True, column_config={"url": st.column_config.LinkColumn("SEC 원문")})
                st.caption("SEC 문서 유형/키워드 탐지일 뿐, EFFECT 상태·계약상 매도 가능 수량·ATM 가동 여부를 확정 판정하지 않습니다. 관련 원문을 직접 확인해야 합니다.")
    with tab3:
        st.markdown("""
**현재 구현된 기능**
- 입력한 티커의 일봉 가격·거래량 데이터 수집
- 간단한 거래량/가격 압축/고점 접근 지표
- 시가총액·가격·평균 거래대금·공급자 제공 Float 기준 필터
- SEC CIK 매핑과 최근 제출 문서 링크
- 등록 서류/자금조달 키워드에 대한 예비 위험 플래그
- 후보 CSV 다운로드

**아직 구현되지 않은 기능**
- 전 미국 종목 universe의 완전 자동 검색
- 실시간 1분/5분봉 RVOL 및 웹푸시
- SEC 계약 원문에서 ATM·PIPE·ELOC·CB·워런트 수량/조건을 정확히 구조화
- 역병합 이벤트 DB 및 분할조정 검증
- 과거 급등/실패 사례의 시점별 백테스트

**해석 주의**
- 기본 점수는 MVP 정렬용 휴리스틱이며 급등 확률이 아닙니다.
- Float가 미확인인 경우 저유통으로 간주하지 않습니다.
- SEC 키워드 플래그는 희석 확정 판정이 아닙니다.
- 데이터 누락, 지연, API 제한이 있을 수 있습니다.
""")
else:
    st.info("왼쪽에서 감시 티커와 필터를 설정한 뒤 **지금 스캔**을 눌러 시작하세요.")
    st.markdown("### 시작하기")
    st.code("pip install -r requirements.txt\nstreamlit run app.py", language="bash")
