"""
Fetch copper market data and copper headlines for the "Copper Watch" tab.

Copper price = COMEX copper futures, front month rolled continuously (Yahoo ticker HG=F),
in US dollars per pound. The series jumps slightly on roll dates; that is normal for futures.

Runs automatically on GitHub (see .github/workflows/update-market.yml) and
writes data/market.js. You can also run it yourself:
    pip install yfinance pandas
    python scripts/fetch_market.py

If any piece fails (a feed is down, Yahoo hiccups), the previous data for
that piece is kept so the site never goes blank.
"""
import json
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "market.js"
TZ = "America/New_York"
UA = {"User-Agent": "Mozilla/5.0 (copper-analysis; +https://github.com/nathanielh34/copper-analysis)"}
ASSET = "HG=F"        # COMEX copper futures (continuous front month)
PEERS = ["SPY", "COPX"]  # S&P 500 ETF and Global X Copper Miners ETF

NEWS_FEEDS = [
    # (label, url)
    ("Copper price", "https://news.google.com/rss/search?q=" + urllib.parse.quote('"copper prices" OR "copper price" OR "LME copper" OR "Comex copper" when:7d') + "&hl=en-US&gl=US&ceid=US:en"),
    ("Mines & supply", "https://news.google.com/rss/search?q=" + urllib.parse.quote('copper mine OR Codelco OR "Escondida" OR "Grasberg" OR "Kamoa-Kakula" OR "Cobre Panama" when:7d') + "&hl=en-US&gl=US&ceid=US:en"),
    ("China & demand", "https://news.google.com/rss/search?q=" + urllib.parse.quote('copper China demand OR "copper demand" OR "copper imports" OR "copper smelter" when:7d') + "&hl=en-US&gl=US&ceid=US:en"),
    ("Policy & tariffs", "https://news.google.com/rss/search?q=" + urllib.parse.quote('copper tariff OR "critical minerals" copper OR "copper export" when:7d') + "&hl=en-US&gl=US&ceid=US:en"),
    ("Mining.com", "https://www.mining.com/commodity/copper/feed/"),
]


# ---------------------------------------------------------------- helpers
def load_previous():
    if not OUT.exists():
        return {}
    m = re.search(r"window\.MARKET\s*=\s*(\{.*\})\s*;", OUT.read_text(encoding="utf-8"), re.S)
    try:
        return json.loads(m.group(1)) if m else {}
    except Exception:
        return {}


def r2(x, d=2):
    return None if x is None or x != x else round(float(x), d)


def pct(a, b):
    return None if not a or not b else round((a / b - 1) * 100, 2)


# ---------------------------------------------------------------- prices
def fetch_prices():
    import yfinance as yf

    daily = yf.Ticker(ASSET).history(period="max", interval="1d", auto_adjust=False)
    daily = daily.dropna(subset=["Close"])
    if daily.empty:
        raise RuntimeError("no daily data")

    intraday = yf.Ticker(ASSET).history(period="60d", interval="15m", auto_adjust=False).dropna(subset=["Close"])
    spy_d = yf.Ticker("SPY").history(start="2000-01-01", interval="1d", auto_adjust=False).dropna(subset=["Close"])
    spy_i = yf.Ticker("SPY").history(period="60d", interval="15m", auto_adjust=False).dropna(subset=["Close"])
    comp = yf.download([ASSET] + PEERS, period="6y", interval="1d", auto_adjust=True, progress=False)["Close"]
    comp = comp.rename(columns={ASSET: "Copper"}).ffill().dropna()  # futures and stocks trade on slightly different days

    # Daily bars: "YYYY-MM-DD" times
    d_rows = [[ts.strftime("%Y-%m-%d"), r2(r.Open, 4), r2(r.High, 4), r2(r.Low, 4), r2(r.Close, 4), int(r.Volume)]
              for ts, r in daily.iterrows()]

    # Intraday bars: shift New York wall-clock time to fake-UTC epoch seconds so the chart shows ET
    def fake_utc(index):
        return [int((ts - pd.Timestamp("1970-01-01")).total_seconds()) for ts in index.tz_convert(TZ).tz_localize(None)]

    i_rows = []
    if not intraday.empty:
        for t, (_, r) in zip(fake_utc(intraday.index), intraday.iterrows()):
            i_rows.append([t, r2(r.Open, 4), r2(r.High, 4), r2(r.Low, 4), r2(r.Close, 4), int(r.Volume)])

    # S&P 500 (SPY) closes for the comparison overlay
    spy_daily = [[ts.strftime("%Y-%m-%d"), r2(c)] for ts, c in spy_d["Close"].items()]
    spy_intraday = [[t, r2(c)] for t, c in zip(fake_utc(spy_i.index), spy_i["Close"])] if not spy_i.empty else []

    last = daily.iloc[-1]
    prev = daily.iloc[-2]
    yr = daily.loc[daily.index >= daily.index[-1] - pd.Timedelta(days=365)]
    hi_i, lo_i = yr["High"].idxmax(), yr["Low"].idxmin()

    # Live-ish quote from intraday if today's bar exists there
    price = float(intraday["Close"].iloc[-1]) if not intraday.empty else float(last.Close)
    if not intraday.empty and intraday.index[-1].date() != daily.index[-1].date():
        price = float(last.Close)  # intraday feed is behind; use the daily close
    as_of = (intraday.index[-1] if not intraday.empty else daily.index[-1]).tz_convert(TZ).strftime("%Y-%m-%d %H:%M")

    quote = {
        "price": r2(price, 4),
        "prevClose": r2(prev.Close, 4),
        "change": r2(price - prev.Close, 4),
        "changePct": pct(price, prev.Close),
        "open": r2(last.Open, 4), "dayHigh": r2(last.High, 4), "dayLow": r2(last.Low, 4),
        "volume": int(last.Volume),
        "avgVolume3m": int(daily["Volume"].tail(63).mean()),
        "high52": r2(yr["High"].max(), 4), "high52Date": hi_i.strftime("%Y-%m-%d"),
        "low52": r2(yr["Low"].min(), 4), "low52Date": lo_i.strftime("%Y-%m-%d"),
        "asOf": as_of,
    }

    # Performance table (price return for copper, total return for the ETFs)
    perf = {}
    end = comp.index[-1]
    windows = {"1M": pd.DateOffset(months=1), "3M": pd.DateOffset(months=3), "6M": pd.DateOffset(months=6),
               "YTD": None, "1Y": pd.DateOffset(years=1), "3Y": pd.DateOffset(years=3), "5Y": pd.DateOffset(years=5)}
    for t in ["Copper"] + PEERS:
        s = comp[t]
        row = {}
        for k, off in windows.items():
            start = pd.Timestamp(year=end.year, month=1, day=1, tz=end.tz) - pd.Timedelta(days=1) if off is None else end - off
            base = s[s.index <= start]
            row[k] = pct(s.iloc[-1], base.iloc[-1]) if len(base) else None
        perf[t] = row

    # 1-year beta of copper vs SPY (daily returns)
    rets = comp[["Copper", "SPY"]].pct_change().dropna()
    rets = rets[rets.index >= end - pd.DateOffset(years=1)]
    beta = r2(rets["Copper"].cov(rets["SPY"]) / rets["SPY"].var())

    return {"daily": d_rows, "intraday": i_rows, "spyDaily": spy_daily, "spyIntraday": spy_intraday, "quote": quote, "performance": perf, "beta1y": beta}


# ---------------------------------------------------------------- news
def fetch_feed(label, url, limit=15):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=20) as resp:
        root = ET.fromstring(resp.read())
    items = []
    for it in root.iter("item"):
        title = (it.findtext("title") or "").strip()
        link = (it.findtext("link") or "").strip()
        src_el = it.find("source")
        source = src_el.text.strip() if src_el is not None and src_el.text else label
        # Google News titles end with " - Source"; drop the duplicate
        if src_el is not None and title.endswith(" - " + source):
            title = title[: -len(" - " + source)]
        try:
            published = parsedate_to_datetime(it.findtext("pubDate")).astimezone(timezone.utc).isoformat()
        except Exception:
            published = None
        if title and link:
            items.append({"title": title, "link": link, "source": source, "published": published, "topic": label})
        if len(items) >= limit:
            break
    return items


def fetch_news():
    items, seen = [], set()
    for label, url in NEWS_FEEDS:
        try:
            for n in fetch_feed(label, url):
                key = re.sub(r"\W+", "", n["title"].lower())[:80]
                if key not in seen:
                    seen.add(key)
                    items.append(n)
        except Exception as e:
            print(f"  news feed failed ({label}): {e}")
    items.sort(key=lambda n: n["published"] or "", reverse=True)
    if not items:
        raise RuntimeError("no news fetched")
    return items[:40]


# ---------------------------------------------------------------- main
def main():
    data = load_previous()
    try:
        data.update(fetch_prices())
        print(f"Prices OK: {len(data['daily'])} daily bars, {len(data['intraday'])} intraday bars")
    except Exception as e:
        print(f"Price fetch failed, keeping previous: {e}")
    try:
        data["news"] = fetch_news()
        print(f"News OK: {len(data['news'])} headlines")
    except Exception as e:
        print(f"News fetch failed, keeping previous: {e}")
    data["updated"] = datetime.now(timezone.utc).isoformat(timespec="minutes")
    OUT.write_text("// Generated by scripts/fetch_market.py. Do not edit by hand.\nwindow.MARKET = "
                   + json.dumps(data, separators=(",", ":")) + ";\n", encoding="utf-8")


if __name__ == "__main__":
    main()
