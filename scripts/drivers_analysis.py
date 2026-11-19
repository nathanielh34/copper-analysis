"""
Driver analyses for the Drivers tab (runs on GitHub with the market-data job).

Copper = COMEX copper futures, continuous front month (Yahoo ticker HG=F).

Return drivers (one per entry in BENCHMARKS):
  - S&P 500 (SPY), AI stocks (AIQ), semiconductors (SMH), electrification (GRID), China large caps (FXI), US dollar index (DX-Y.NYB), crude oil (CL=F)
  - Linear regression  copper_return = alpha + beta * driver_return + error
  - Three time frames: 5Y monthly (60 months), 10Y monthly (120 months), 1Y weekly (52 weeks)
Level drivers (RATES): 10-year Treasury yield and the news strength index,
  copper return vs the change in the level.
Plus diagnostics, residuals and rolling betas for each time frame.
Supply drivers (mine-disruption event study, treatment charges) come from supply_analysis.py.

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
    local = {"STRENGTH", "LME_STOCKS", "MM_NET"}  # series built from our own data files, not Yahoo
    tickers = [ASSET] + [b["ticker"] for b in BENCHMARKS + RATES if b["ticker"] not in local]
    px = yf.download(tickers, start="2005-01-01", interval="1d", auto_adjust=True, progress=False)["Close"]
    px = px.rename(columns={ASSET: "COPPER"})
    # Our own news strength index (built by scripts/strength_index.py), aligned to trading days
    csv = ROOT / "data" / "strength_daily.csv"
    if csv.exists():
        si = pd.read_csv(csv, parse_dates=["date"]).set_index("date")["index"]
        if px.index.tz is not None:
            si.index = si.index.tz_localize(px.index.tz)
        px["STRENGTH"] = si.reindex(px.index, method="ffill")
    # LME copper stocks (tonnes) and CFTC managed-money net long (% of open interest),
    # from scripts/fetch_supply_data.py, carried forward onto trading days
    def add(col, csv, fn):
        if not csv.exists():
            return
        d = pd.read_csv(csv, parse_dates=["date"]).set_index("date").sort_index()
        ser = fn(d)
        if px.index.tz is not None:
            ser.index = ser.index.tz_localize(px.index.tz)
        px[col] = ser.reindex(px.index.union(ser.index)).ffill().reindex(px.index)
    add("LME_STOCKS", ROOT / "data" / "lme_stocks.csv", lambda d: d["stocks"])
    add("MM_NET", ROOT / "data" / "cftc_copper.csv", lambda d: (d["mm_long"] - d["mm_short"]) / d["oi"] * 100)
    return px


def _drop_current(m, freq):
    """Drop the period still in progress (current month or current week)."""
    if m.empty:
        return m
    today = pd.Timestamp.now(tz=m.index.tz) if m.index.tz is not None else pd.Timestamp.now()
    last = m.index[-1]
    if freq == "ME" and last.year == today.year and last.month == today.month:
        return m.iloc[:-1]
    if freq == "W-FRI" and last.normalize() >= today.normalize():
        return m.iloc[:-1]  # this week's Friday close hasn't happened yet
    return m


def period_closes(px, freq):
    return _drop_current(px.resample(freq).last(), freq)


# The three time frames shown on the Drivers tab (switchable at the top of the tab).
FRAMES = [
    # key, resample rule, periods used, rolling window, labels
    {"key": "5Y monthly", "freq": "ME", "n": 60, "roll": 36, "per": "month", "adj": "monthly", "rollLabel": "36-month", "fmt": "%Y-%m"},
    {"key": "10Y monthly", "freq": "ME", "n": 120, "roll": 36, "per": "month", "adj": "monthly", "rollLabel": "36-month", "fmt": "%Y-%m"},
    {"key": "1Y weekly", "freq": "W-FRI", "n": 52, "roll": 26, "per": "week", "adj": "weekly", "rollLabel": "26-week", "fmt": "%Y-%m-%d"},
]


def build_frame(all_p, t, fr, method, xLabel, result_fn, roll_title):
    """all_p: DataFrame with COPPER (% return) and driver column t for every completed period."""
    sample = all_p.tail(fr["n"])
    res, stats_ = regress(sample["COPPER"], sample[t])
    points = [[d.strftime(fr["fmt"]), r(x, 3), r(y, 3), r(f, 3), r(e, 3)]
              for d, x, y, f, e in zip(sample.index, sample[t], sample["COPPER"], res.fittedvalues, res.resid)]
    cov = all_p["COPPER"].rolling(fr["roll"]).cov(all_p[t])
    var = all_p[t].rolling(fr["roll"]).var()
    roll = (cov / var).dropna()
    if fr["freq"] == "W-FRI":
        roll = roll.tail(156)  # last 3 years of weekly rolling betas
    b = stats_["coef"]["beta"]
    short = len(sample) < fr["n"]
    return {
        "frame": fr["key"], "per": fr["per"], "adj": fr["adj"], "rollLabel": fr["rollLabel"],
        "method": method + f", last {len(sample)} completed {fr['per']}s.",
        "period": f"{sample.index[0].strftime('%b %Y')} to {sample.index[-1].strftime('%b %Y')}",
        "short": short,
        "xLabel": xLabel,
        "yLabel": f"Copper {fr['adj']} return, %",
        **stats_,
        "points": points,
        "rollingBeta": [[d.strftime(fr["fmt"]), r(v, 3)] for d, v in roll.items()],
        "rollTitle": roll_title,
        "status": "Significant" if b["p"] < 0.05 else "Not significant",
        "result": f"{fr['key']}: " + result_fn(stats_),
    }


def pfmt(p):
    return "p<0.001" if p < 0.001 else f"p={p:.3f}"


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
    frames = {}
    for fr in FRAMES:
        all_p = period_closes(px, fr["freq"]).pct_change().dropna() * 100
        frames[fr["key"]] = build_frame(
            all_p, t, fr,
            method=f"OLS regression of copper's {fr['adj']} return on {bench['long']} {fr['adj']} return",
            xLabel=f"{bench['short']} ({t}) {fr['adj']} return, %",
            result_fn=lambda st: f"beta {st['coef']['beta']['est']:.2f}, R² {st['r2']:.2f}, {pfmt(st['coef']['beta']['p'])}",
            roll_title=f"Rolling {fr['rollLabel']} beta (how stable is beta?)")
    main = frames["5Y monthly"]
    return {"title": bench["driver"], "question": bench["question"], "bench": bench["short"],
            "frames": frames, **main}


# Level drivers: copper return regressed on the monthly CHANGE in a level (a yield or an index)
RATES = [
    {"driver": "10-year Treasury yield", "ticker": "^TNX", "short": "10Y Treasury yield", "long": "the 10-year Treasury yield (^TNX)",
     "question": "Does copper rise or fall when long-term interest rates move?",
     "unit": "pp", "unitLong": "percentage point", "step": 0.25, "levelSuffix": "%",
     "xLabel": "Change in 10-year Treasury yield, percentage points", "short2": "10Y yield",
     "levelLabel": "10Y yield now", "sensLabel": "Rate sensitivity",
     "caveat": "Yields often rise when the economy is strong, which is also when copper demand is strong. Some of this relationship may be growth in disguise, so the real test is a multiple regression with the S&amp;P 500 or China stocks alongside yield changes. Higher rates also raise the cost of holding inventory.",
     "next": ["<b>Control for growth.</b> Run copper on the S&amp;P 500 <i>and</i> yield changes together. If the yield coefficient stays significant, rates matter for copper beyond their link to the economy.",
              "<b>Add the dollar:</b> rate moves often move the dollar too. Put both in one regression to see which one copper actually responds to.",
              "<b>Real vs nominal:</b> split the 10-year yield into inflation expectations and real yield (TIPS). Copper is often treated as an inflation hedge, so the inflation part may matter more."]},
    {"driver": "Exchange inventories", "ticker": "LME_STOCKS", "short": "LME copper stocks", "long": "LME copper warehouse stocks",
     "question": "Copper in exchange warehouses is the market's buffer. Does copper fall when stocks build and rise when they're drawn down?",
     "unit": "%", "unitLong": "percent", "step": 10, "levelSuffix": " t", "levelDigits": 0, "pct": True,
     "xLabel": "Change in LME copper stocks, %", "short2": "LME stocks",
     "levelLabel": "LME stocks now", "sensLabel": "Stock sensitivity",
     "caveat": "Since early 2025 the threat of US tariffs pulled huge amounts of copper into COMEX warehouses in the US and out of the LME, so LME stocks partly reflect where metal is stored, not how much exists. A full picture adds COMEX and Shanghai (SHFE) stocks. Stocks are also a result of prices (high prices pull metal out of warehouses), so this shows they move together, not which causes which.",
     "next": ["<b>Add COMEX and SHFE stocks</b> to get total visible inventory, so metal moving between exchanges doesn't look like a draw or a build.",
              "<b>Days of consumption:</b> divide stocks by world demand. 200,000 t meant more in 2010 than it does today.",
              "<b>Lead-lag test:</b> do stock draws <i>predict</i> next month's copper return, or just move with it?"]},
    {"driver": "Speculative positioning", "ticker": "MM_NET", "short": "managed-money net long", "long": "managed-money net long position in COMEX copper (CFTC)",
     "question": "Do hedge funds and other speculators drive copper? Does copper rise when they add to net long positions?",
     "unit": "pp", "unitLong": "percentage point of open interest", "step": 5, "levelSuffix": "% of OI", "levelDigits": 1,
     "xLabel": "Change in managed-money net long, % of open interest", "short2": "speculator net long",
     "levelLabel": "Net long now", "sensLabel": "Positioning sensitivity",
     "caveat": "Funds buy when prices are rising (trend following), so a strong same-period link is expected even if speculators don't cause the moves. The CFTC report shows positions as of Tuesday and is published Friday. This uses COMEX only; LME positioning (Commitments of Traders on the LME) is separate.",
     "next": ["<b>Does positioning predict?</b> Regress next week's or month's copper return on this week's change in positioning. That separates trend-following from price impact.",
              "<b>Crowding:</b> test whether extreme net long or net short levels (e.g. top or bottom 10%) come before reversals.",
              "<b>Add producers:</b> compare managed money with producer/merchant hedging (also in data/cftc_copper.csv)."]},
    {"driver": "Strength Index", "ticker": "STRENGTH", "short": "Strength Index", "long": "the news strength index (this site)",
     "question": "Do months with more bullish copper headlines line up with better copper returns?",
     "unit": "pt", "unitLong": "index point", "step": None, "levelSuffix": "",
     "xLabel": "Change in strength index, points", "short2": "strength index",
     "levelLabel": "Index now", "sensLabel": "Index sensitivity",
     "caveat": "This is a same-month relationship, so it shows whether headlines and prices move together, not whether the index predicts. Much copper news reports moves that already happened (\"copper jumps on China data\"). The Strength Index tab tests prediction: the index at month end vs next month's return.",
     "next": ["<b>Check the misses:</b> open the months with the largest residuals on the Strength Index tab (click the chart) and see whether the headlines were scored correctly; fix them with overrides or by editing the rules.",
              "<b>Add the dollar and China:</b> regress copper on the index together with the dollar and China stocks to see if headlines explain anything beyond the macro drivers.",
              "<b>Tune the half-life</b> in data/scoring_rules.json (e.g. 7 vs 30 days) and compare R²."]},
]


def rate_driver(px_all, rate):
    t = rate["ticker"]
    px = px_all[["COPPER", t]].dropna()
    frames = {}
    for fr in FRAMES:
        c = period_closes(px, fr["freq"])
        chg = c[t].pct_change() * 100 if rate.get("pct") else c[t].diff()  # % change for stocks, else change in level
        all_p = pd.DataFrame({"COPPER": c["COPPER"].pct_change() * 100, t: chg}).dropna()
        f = build_frame(
            all_p, t, fr,
            method=(f"OLS regression of copper's {fr['adj']} return on the {fr['adj']} percent change in {rate['long']}" if rate.get("pct")
                    else f"OLS regression of copper's {fr['adj']} return on the {fr['adj']} change in {rate['long']}, in {rate['unitLong']}s"),
            xLabel=rate["xLabel"].replace("Change in", f"{fr['adj'].capitalize()} change in"),
            result_fn=lambda st: f"{st['coef']['beta']['est']:+.2f}% copper per +1{'%' if rate['unit'] == '%' else ' ' + rate['unit']} {rate['short2']}, R² {st['r2']:.2f}, {pfmt(st['coef']['beta']['p'])}",
            roll_title=f"Rolling {fr['rollLabel']} {rate['short2']} sensitivity (is it stable?)")
        step = rate.get("step")
        if step is None:  # pick a typical move for the readout
            sd = float(all_p[t].tail(fr["n"]).std())
            step = max(1, int(round(sd / 5.0)) * 5) if sd >= 5 else max(1, int(round(sd)))
        f["step"] = step
        frames[fr["key"]] = f
    main = frames["5Y monthly"]
    return {
        "kind": "level",
        **{k: rate[k] for k in ["unit", "unitLong", "levelSuffix", "levelLabel", "sensLabel", "caveat", "next", "short2"]},
        "levelDigits": rate.get("levelDigits", 2),
        "title": rate["driver"],
        "question": rate["question"],
        "bench": rate["short"],
        "yieldNow": r(px[t].iloc[-1], 3),
        "frames": frames,
        **main,
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
    # Supply drivers: mine-disruption event study and treatment charges (scripts/supply_analysis.py)
    import supply_analysis
    for name, fn in [("Mine disruptions", supply_analysis.event_study), ("Treatment charges", supply_analysis.treatment_charges)]:
        try:
            out["drivers"][name] = fn(px)
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
