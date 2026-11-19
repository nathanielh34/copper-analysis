"""
Fetch inventory and positioning data for the Drivers tab (runs on GitHub with the market-data job).

  data/lme_stocks.csv     date, stocks   LME copper warehouse stocks, tonnes (daily)
                          Source: Westmetall's table of official LME data.
  data/cftc_copper.csv    date, oi, mm_long, mm_short, pm_long, pm_short, sd_long, sd_short
                          CFTC Disaggregated Commitments of Traders, futures only,
                          COMEX copper (contract code 085692), weekly (Tuesday positions).
                          Source: CFTC public reporting API, with the yearly history files as a fallback.

If a download fails the existing file is kept, so the analysis always has data.
Run locally with:  pip install pandas lxml requests && python scripts/fetch_supply_data.py
"""
import io
import zipfile
from datetime import date
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parent.parent
LME_OUT = ROOT / "data" / "lme_stocks.csv"
CFTC_OUT = ROOT / "data" / "cftc_copper.csv"
UA = {"User-Agent": "Mozilla/5.0 (copper-analysis research project; github.com/nathanielh34/copper-analysis)"}
COPPER_CODE = "085692"


# ---------------------------------------------------------------- LME stocks
def fetch_lme():
    url = "https://www.westmetall.com/en/markdaten.php?action=table&field=LME_Cu_cash"
    html = requests.get(url, headers=UA, timeout=60).text
    tables = pd.read_html(io.StringIO(html), thousands=",", decimal=".")
    rows = []
    for t in tables:
        cols = [str(c).lower() for c in (t.columns.get_level_values(-1) if isinstance(t.columns, pd.MultiIndex) else t.columns)]
        t.columns = cols
        dcol = next((c for c in cols if "date" in c), cols[0])
        scol = next((c for c in cols if "stock" in c), None)
        if scol is None:
            continue
        for d, s in zip(t[dcol], t[scol]):
            dt = pd.to_datetime(str(d).replace(".", ""), format="%d %B %Y", errors="coerce")
            v = pd.to_numeric(str(s).replace(",", ""), errors="coerce")
            if pd.notna(dt) and pd.notna(v):
                rows.append((dt.date(), float(v)))
    df = pd.DataFrame(rows, columns=["date", "stocks"]).drop_duplicates("date").sort_values("date")
    if len(df) < 500:
        raise RuntimeError(f"only {len(df)} LME rows parsed")
    return df


# ---------------------------------------------------------------- CFTC positioning
FIELDS = {"open_interest_all": "oi", "m_money_positions_long_all": "mm_long", "m_money_positions_short_all": "mm_short",
          "prod_merc_positions_long_all": "pm_long", "prod_merc_positions_short_all": "pm_short",
          "swap_positions_long_all": "sd_long", "swap__positions_short_all": "sd_short"}


def fetch_cftc_api():
    url = "https://publicreporting.cftc.gov/resource/72hh-3qpy.json"
    params = {"$where": f"cftc_contract_market_code='{COPPER_CODE}'", "$limit": 5000,
              "$order": "report_date_as_yyyy_mm_dd"}
    data = requests.get(url, params=params, headers=UA, timeout=90).json()
    df = pd.DataFrame(data)
    out = pd.DataFrame({"date": pd.to_datetime(df["report_date_as_yyyy_mm_dd"]).dt.date})
    for src, dst in FIELDS.items():
        col = src if src in df.columns else src.replace("__", "_")
        out[dst] = pd.to_numeric(df[col], errors="coerce")
    return out


def fetch_cftc_files():
    """Fallback: CFTC yearly history files (2006-2016 bundle, then one file per year)."""
    frames = []
    urls = ["https://www.cftc.gov/files/dea/history/fut_disagg_txt_hist_2006_2016.zip"] + \
           [f"https://www.cftc.gov/files/dea/history/fut_disagg_txt_{y}.zip" for y in range(2017, date.today().year + 1)]
    for u in urls:
        try:
            z = zipfile.ZipFile(io.BytesIO(requests.get(u, headers=UA, timeout=120).content))
            df = pd.read_csv(z.open(z.namelist()[0]), low_memory=False)
        except Exception as e:
            print("  CFTC file failed:", u, e)
            continue
        df.columns = [c.strip().lower() for c in df.columns]
        df = df[df["cftc_contract_market_code"].astype(str).str.strip().str.zfill(6) == COPPER_CODE]
        dcol = next(c for c in df.columns if c.startswith("report_date_as_yyyy"))
        out = pd.DataFrame({"date": pd.to_datetime(df[dcol]).dt.date})
        for src, dst in FIELDS.items():
            col = src if src in df.columns else src.replace("__", "_")
            out[dst] = pd.to_numeric(df[col], errors="coerce")
        frames.append(out)
    return pd.concat(frames)


def fetch_cftc():
    try:
        df = fetch_cftc_api()
    except Exception as e:
        print("  CFTC API failed, using history files:", e)
        df = fetch_cftc_files()
    df = df.dropna(subset=["oi", "mm_long", "mm_short"]).drop_duplicates("date").sort_values("date")
    if len(df) < 300:
        raise RuntimeError(f"only {len(df)} CFTC rows")
    return df


def main():
    for name, fn, out in [("LME stocks", fetch_lme, LME_OUT), ("CFTC positioning", fetch_cftc, CFTC_OUT)]:
        try:
            df = fn()
            df.to_csv(out, index=False)
            print(f"{name}: {len(df)} rows, {df['date'].iloc[0]} to {df['date'].iloc[-1]}")
        except Exception as e:
            print(f"{name} download failed (keeping the existing file):", e)


if __name__ == "__main__":
    main()
