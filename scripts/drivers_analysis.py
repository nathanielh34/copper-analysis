"""
Driver analyses for the Drivers tab (runs on GitHub with the market-data job).

Copper = COMEX copper futures, continuous front month (Yahoo ticker HG=F).

Return drivers (one per entry in BENCHMARKS):
  - S&P 500 (SPY), AI stocks (AIQ), semiconductors (SMH), electrification (GRID), China large caps (FXI), US dollar index (DX-Y.NYB), crude oil (CL=F)
  - 5-year monthly beta of copper vs the driver, 60 completed months
  - Linear regression  copper_return = alpha + beta * driver_return + error
Level drivers (RATES): 10-year Treasury yield and the news strength index,
  copper return vs the monthly change in the level.
Plus diagnostics, residuals, and correlations at a few horizons.

ETF prices are dividend-adjusted. Writes data/drivers_results.js.
Run locally with:  pip install yfinance pandas statsmodels && python scripts/drivers_analysis.py
"""
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.api as sm
from statsmodels.stats.diagnostic import het_breuschpagan
from statsmodels.stats.stattools import durbin_watson, jarque_bera

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "drivers_results.js"
ASSET = "HG=F"  # COMEX copper futures, continuous front month


def r(x, d=4):
    return None if x is None or not np.isfinite(x) else round(float(x), d)


def monthly_returns(prices):
    """Prices -> % monthly returns from month-end closes, completed months only."""
    m = prices.resample("ME").last()
    today = pd.Timestamp.now(tz=m.index.tz) if m.index.tz is not None else pd.Timestamp.now()
    if m.index[-1].year == today.year and m.index[-1].month == today.month:
        m = m.iloc[:-1]  # drop the month still in progress
    return m.pct_change().dropna() * 100


def regress(y, x):
    X = sm.add_constant(x.rename("market"))
    res = sm.OLS(y, X).fit()
    ci = res.conf_int(0.05)
    bp = het_breuschpagan(res.resid, X)
    jb = jarque_bera(res.resid)
    coef = {}
    for name, label in [("const", "alpha"), ("market", "beta")]:
        coef[label] = {"est": r(res.params[name]), "se": r(res.bse[name]), "t": r(res.tvalues[name], 3),
                       "p": r(res.pvalues[name], 5), "ciLow": r(ci.loc[name, 0]), "ciHigh": r(ci.loc[name, 1])}
    # Is beta different from 1 (i.e., more/less volatile than the market)?
    t1 = (res.params["market"] - 1) / res.bse["market"]
    from scipy import stats
    p1 = 2 * stats.t.sf(abs(t1), res.df_resid)
    return res, {
        "coef": coef,
        "betaVsOne": {"t": r(t1, 3), "p": r(p1, 5)},
        "n": int(res.nobs), "r2": r(res.rsquared), "adjR2": r(res.rsquared_adj),
        "corr": r(np.corrcoef(x, y)[0, 1]),
        "fStat": r(res.fvalue, 3), "fP": r(res.f_pvalue, 6),
        "residStd": r(np.sqrt(res.mse_resid)),
        "durbinWatson": r(durbin_watson(res.resid), 3),
        "jarqueBeraP": r(jb[1], 5), "skew": r(jb[2], 3), "kurtosis": r(jb[3], 3),
        "breuschPaganP": r(bp[1], 5),
        "xMean": r(x.mean()), "yMean": r(y.mean()), "xStd": r(x.std()), "yStd": r(y.std()),
    }


def load_prices():
    import yfinance as yf
    tickers = [ASSET] + [b["ticker"] for b in BENCHMARKS + RATES if b["ticker"] != "STRENGTH"]
    px = yf.download(tickers, start="2005-01-01", interval="1d", auto_adjust=True, progress=False)["Close"]
    px = px.rename(columns={ASSET: "COPPER"})
    # Our own news strength index (built by scripts/strength_index.py), aligned to trading days
    csv = ROOT / "data" / "strength_daily.csv"
    if csv.exists():
        si = pd.read_csv(csv, parse_dates=["date"]).set_index("date")["index"]
        if px.index.tz is not None:
            si.index = si.index.tz_localize(px.index.tz)
        px["STRENGTH"] = si.reindex(px.index, method="ffill")
    return px


# Each benchmark gets the same regression, charts and diagnostics on the Drivers tab.
BENCHMARKS = [
    {"driver": "S&P 500 returns", "ticker": "SPY", "short": "S&P 500", "long": "SPY (S&P 500 ETF)",
     "question": "How much does copper move with the overall stock market (a proxy for global growth)?"},
    {"driver": "AI stocks", "ticker": "AIQ", "short": "AI stocks", "long": "AIQ (Global X Artificial Intelligence & Technology ETF)",
     "question": "AI data centers need a lot of copper (power, cooling, grid links). Does copper move with AI stocks?"},
    {"driver": "Semiconductor stocks", "ticker": "SMH", "short": "semiconductors", "long": "SMH (VanEck Semiconductor ETF)",
     "question": "Chipmakers like Nvidia are the most direct read on AI data-center spending. Does copper move with semiconductor stocks?"},
    {"driver": "Electrification", "ticker": "GRID", "short": "grid infrastructure", "long": "GRID (First Trust Nasdaq Clean Edge Smart Grid Infrastructure ETF)",
     "question": "Power grids, EVs and renewables are copper-heavy. Does copper move with the companies building the grid?"},
    {"driver": "China stocks", "ticker": "FXI", "short": "China large caps", "long": "FXI (iShares China Large-Cap ETF)",
     "question": "China uses about half the world's copper. Does copper move with Chinese stocks?"},
    {"driver": "US dollar", "ticker": "DX-Y.NYB", "short": "US dollar index", "long": "the US dollar index (DXY)",
     "question": "Copper is priced in dollars. Does copper fall when the dollar strengthens?"},
    {"driver": "Crude oil", "ticker": "CL=F", "short": "crude oil", "long": "WTI crude oil futures (CL=F)",
     "question": "Do copper and oil move together as commodities (shared demand, inflation, mining energy costs)?"},
]


def market_driver(px_all, bench):
    t = bench["ticker"]
    px = px_all[["COPPER", t]].dropna()

    # --- Main model: 5-year monthly (60 completed months)
    mret = monthly_returns(px).tail(60)
    res, stats_ = regress(mret["COPPER"], mret[t])
    points = [[d.strftime("%Y-%m"), r(x, 3), r(y, 3), r(f, 3), r(e, 3)]
              for d, x, y, f, e in zip(mret.index, mret[t], mret["COPPER"], res.fittedvalues, res.resid)]

    # --- Rolling 36-month beta (full history) to show how beta changes over time
    all_m = monthly_returns(px)
    cov = all_m["COPPER"].rolling(36).cov(all_m[t])
    var = all_m[t].rolling(36).var()
    rolling = [[d.strftime("%Y-%m"), r(b, 3)] for d, b in (cov / var).dropna().items()]

    # --- Correlation / beta at other horizons for comparison
    d = px.pct_change().dropna()
    w = px.resample("W-FRI").last().pct_change().dropna()
    def cb(df, n):
        df = df.tail(n)
        return {"corr": r(df["COPPER"].corr(df[t]), 3), "beta": r(df["COPPER"].cov(df[t]) / df[t].var(), 3), "n": len(df)}
    horizons = {"1Y daily": cb(d, 252), "3Y weekly": cb(w, 156), "5Y monthly": cb(all_m, 60), "Since 2005 monthly": cb(all_m, len(all_m))}

    return {
        "title": bench["driver"],
        "question": bench["question"],
        "method": f"OLS regression of copper's monthly return on {bench['long']} monthly return, last 60 completed months.",
        "period": f"{mret.index[0].strftime('%b %Y')} to {mret.index[-1].strftime('%b %Y')}",
        "bench": bench["short"],
        "xLabel": f"{bench['short']} ({t}) monthly return, %",
        "yLabel": "Copper monthly return, %",
        **stats_,
        "points": points,          # [month, x, y, fitted, residual]
        "rollingBeta": rolling,    # [month, beta]
        "horizons": horizons,
        "status": "Significant" if stats_["coef"]["beta"]["p"] < 0.05 else "Not significant",
        "result": f"5Y monthly beta {stats_['coef']['beta']['est']:.2f}, R² {stats_['r2']:.2f}, "
                  + ("p<0.001" if stats_['coef']['beta']['p'] < 0.001 else f"p={stats_['coef']['beta']['p']:.3f}"),
    }


# Level drivers: copper return regressed on the monthly CHANGE in a level (a yield or an index)
RATES = [
    {"driver": "10-year Treasury yield", "ticker": "^TNX", "short": "10Y Treasury yield", "long": "the 10-year Treasury yield (^TNX)",
     "question": "Does copper rise or fall when long-term interest rates move?",
     "unit": "pp", "unitLong": "percentage point", "step": 0.25, "levelSuffix": "%",
     "xLabel": "Change in 10-year Treasury yield, percentage points", "short2": "10Y yield",
     "levelLabel": "10Y yield now", "sensLabel": "Rate sensitivity", "rollTitle": "Rolling 36-month rate sensitivity (is it stable?)",
     "caveat": "Yields often rise when the economy is strong, which is also when copper demand is strong. Some of this relationship may be growth in disguise, so the real test is a multiple regression with the S&amp;P 500 or China stocks alongside yield changes. Higher rates also raise the cost of holding inventory.",
     "next": ["<b>Control for growth.</b> Run copper on the S&amp;P 500 <i>and</i> yield changes together. If the yield coefficient stays significant, rates matter for copper beyond their link to the economy.",
              "<b>Add the dollar:</b> rate moves often move the dollar too. Put both in one regression to see which one copper actually responds to.",
              "<b>Real vs nominal:</b> split the 10-year yield into inflation expectations and real yield (TIPS). Copper is often treated as an inflation hedge, so the inflation part may matter more."]},
    {"driver": "Strength Index", "ticker": "STRENGTH", "short": "Strength Index", "long": "the news strength index (this site)",
     "question": "Do months with more bullish copper headlines line up with better copper returns?",
     "unit": "pt", "unitLong": "index point", "step": None, "levelSuffix": "",
     "xLabel": "Change in strength index, points", "short2": "strength index",
     "levelLabel": "Index now", "sensLabel": "Index sensitivity", "rollTitle": "Rolling 36-month index sensitivity (is it stable?)",
     "caveat": "This is a same-month relationship, so it shows whether headlines and prices move together, not whether the index predicts. Much copper news reports moves that already happened (\"copper jumps on China data\"). The Strength Index tab tests prediction: the index at month end vs next month's return.",
     "next": ["<b>Check the misses:</b> open the months with the largest residuals on the Strength Index tab (click the chart) and see whether the headlines were scored correctly; fix them with overrides or by editing the rules.",
              "<b>Add the dollar and China:</b> regress copper on the index together with the dollar and China stocks to see if headlines explain anything beyond the macro drivers.",
              "<b>Tune the half-life</b> in data/scoring_rules.json (e.g. 7 vs 30 days) and compare R²."]},
]


def month_end_changes(levels):
    """Yield levels -> monthly change in percentage points, completed months only."""
    m = levels.resample("ME").last()
    today = pd.Timestamp.now(tz=m.index.tz) if m.index.tz is not None else pd.Timestamp.now()
    if m.index[-1].year == today.year and m.index[-1].month == today.month:
        m = m.iloc[:-1]
    return m


def rate_driver(px_all, rate):
    t = rate["ticker"]
    px = px_all[["COPPER", t]].dropna()
    m = month_end_changes(px)
    all_m = pd.DataFrame({"COPPER": m["COPPER"].pct_change() * 100, t: m[t].diff()}).dropna()
    mret = all_m.tail(60)
    res, stats_ = regress(mret["COPPER"], mret[t])
    points = [[d.strftime("%Y-%m"), r(x, 3), r(y, 3), r(f, 3), r(e, 3)]
              for d, x, y, f, e in zip(mret.index, mret[t], mret["COPPER"], res.fittedvalues, res.resid)]

    # Rolling 36-month sensitivity
    cov = all_m["COPPER"].rolling(36).cov(all_m[t])
    var = all_m[t].rolling(36).var()
    rolling = [[d.strftime("%Y-%m"), r(b, 3)] for d, b in (cov / var).dropna().items()]

    # Other horizons: copper % return vs change in the level
    def pair(df):
        return pd.DataFrame({"COPPER": df["COPPER"].pct_change() * 100, t: df[t].diff()}).dropna()
    d = pair(px)
    w = pair(px.resample("W-FRI").last())
    def cb(df, n):
        df = df.tail(n)
        return {"corr": r(df["COPPER"].corr(df[t]), 3), "beta": r(df["COPPER"].cov(df[t]) / df[t].var(), 3), "n": len(df)}
    horizons = {"1Y daily": cb(d, 252), "3Y weekly": cb(w, 156), "5Y monthly": cb(all_m, 60), "Since 2005 monthly": cb(all_m, len(all_m))}

    b = stats_["coef"]["beta"]
    if rate.get("step") is None:  # pick a typical monthly move for the readout
        sd = float(mret[t].std())
        rate = {**rate, "step": max(1, int(round(sd / 5.0)) * 5) if sd >= 5 else max(1, int(round(sd)))}
    return {
        "kind": "level",
        **{k: rate[k] for k in ["unit", "unitLong", "step", "levelSuffix", "levelLabel", "sensLabel", "rollTitle", "caveat", "next", "short2"]},
        "title": rate["driver"],
        "question": rate["question"],
        "method": f"OLS regression of copper's monthly return on the monthly change in {rate['long']}, in {rate['unitLong']}s, last 60 completed months.",
        "period": f"{mret.index[0].strftime('%b %Y')} to {mret.index[-1].strftime('%b %Y')}",
        "bench": rate["short"],
        "xLabel": rate["xLabel"],
        "yLabel": "Copper monthly return, %",
        "yieldNow": r(px[t].iloc[-1], 3),
        **stats_,
        "points": points,
        "rollingBeta": rolling,
        "horizons": horizons,
        "status": "Significant" if b["p"] < 0.05 else "Not significant",
        "result": f"{b['est']:+.2f}% copper per +1 {rate['unit']} {rate['short2']}, R² {stats_['r2']:.2f}, "
                  + ("p<0.001" if b["p"] < 0.001 else f"p={b['p']:.3f}"),
    }


def previous_results():
    try:
        txt = OUT.read_text(encoding="utf-8")
        return json.loads(txt.split("=", 1)[1].strip().rstrip(";"))["drivers"]
    except Exception:
        return {}


def main():
    prev = previous_results()
    out = {"updated": datetime.now(timezone.utc).isoformat(timespec="minutes"), "drivers": {}}
    try:
        px = load_prices()
    except Exception as e:
        print("Price download failed:", e)
        return  # keep the previous results
    for bench in BENCHMARKS:
        name = bench["driver"]
        try:
            out["drivers"][name] = market_driver(px, bench)
            print(f"{name} driver OK:", out["drivers"][name]["result"])
        except Exception as e:
            print(f"{name} driver failed:", e)
            if name in prev:
                out["drivers"][name] = prev[name]  # keep the previous result for this driver
    for rate in RATES:
        name = rate["driver"]
        try:
            out["drivers"][name] = rate_driver(px, rate)
            print(f"{name} driver OK:", out["drivers"][name]["result"])
        except Exception as e:
            print(f"{name} driver failed:", e)
            if name in prev:
                out["drivers"][name] = prev[name]
    if not out["drivers"]:
        return
    OUT.write_text("// Generated by scripts/drivers_analysis.py. Do not edit by hand.\nwindow.DRIVER_ANALYSIS = "
                   + json.dumps(out, separators=(",", ":")) + ";\n", encoding="utf-8")


if __name__ == "__main__":
    main()
