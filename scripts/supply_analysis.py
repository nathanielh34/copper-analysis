"""
Supply drivers for the Drivers tab (called from drivers_analysis.py).

Mine disruptions: event study.
  For each major disruption in data/mine_disruptions.json, measure copper's
  return around the day the news broke. "Abnormal" return = copper's return
  minus what the stock market (SPY) that day would predict, using a market
  model estimated on the year before the event (days -260 to -21).
  Windows: day 0, days 0..+5, days 0..+20 (trading days), plus days -5..-1.
  Significance: a t-test across events and a placebo test that draws the same
  number of random dates many times.

Treatment charges: regressions on the copper concentrate TC.
  Spot: copper's return between consecutive Fastmarkets TC observations vs the
  change in the TC over the same dates (data/treatment_charges.json).
  Benchmark: copper's calendar-year return vs the change in the annual
  benchmark TC.
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.api as sm
from scipy import stats

ROOT = Path(__file__).resolve().parent.parent
WINDOWS = [("pre", -5, -1, "Days −5 to −1 (before)"), ("d0", 0, 0, "Day 0"),
           ("d5", 0, 5, "Days 0 to +5"), ("d20", 0, 20, "Days 0 to +20")]
PATH = (-10, 20)


def r(x, d=4):
    return None if x is None or not np.isfinite(x) else round(float(x), d)


def _ols(y, x):
    X = sm.add_constant(pd.Series(x, name="x"))
    res = sm.OLS(pd.Series(y), X).fit()
    ci = res.conf_int(0.05)
    return res, {
        "alpha": r(res.params["const"]), "beta": r(res.params["x"]), "se": r(res.bse["x"]),
        "t": r(res.tvalues["x"], 3), "p": r(res.pvalues["x"], 5),
        "ciLow": r(ci.loc["x", 0]), "ciHigh": r(ci.loc["x", 1]),
        "r2": r(res.rsquared), "n": int(res.nobs), "corr": r(np.corrcoef(x, y)[0, 1]),
    }


# ---------------------------------------------------------------- event study
def event_study(px):
    events = json.loads((ROOT / "data" / "mine_disruptions.json").read_text())["events"]
    d = px[["COPPER", "SPY"]].dropna()
    ret = d.pct_change().dropna() * 100
    dates = ret.index
    cu, mk = ret["COPPER"].values, ret["SPY"].values

    def ar_series(i):
        """Abnormal returns around position i using a market model fitted on [i-260, i-21]."""
        lo, hi = i - 260, i - 21
        if lo < 0:
            return None, None
        b, a = np.polyfit(mk[lo:hi], cu[lo:hi], 1)
        return cu - (a + b * mk), (a, b)

    rows, paths = [], []
    for ev in events:
        t = pd.Timestamp(ev["date"])
        if dates.tz is not None:
            t = t.tz_localize(dates.tz)
        i = int(dates.searchsorted(t))
        if i >= len(dates):
            continue
        ar, mm = ar_series(i)
        if ar is None:
            continue
        row = {**{k: ev[k] for k in ["date", "mine", "country", "type", "share", "what", "source"]},
               "day0": dates[i].strftime("%Y-%m-%d"), "beta": r(mm[1], 3)}
        for key, a, b, _ in WINDOWS:
            if i + b >= len(dates) or i + a < 0:
                row[key] = row[key + "Raw"] = None
                continue
            row[key] = r(ar[i + a:i + b + 1].sum(), 3)
            row[key + "Raw"] = r((np.prod(1 + cu[i + a:i + b + 1] / 100) - 1) * 100, 3)
        # cumulative abnormal return path, 0 at the close before day 0
        path = []
        for k in range(PATH[0], PATH[1] + 1):
            j = i + k
            if j < 0 or j >= len(dates):
                path.append(None)
            elif k < 0:
                path.append(r(-ar[j + 1:i].sum(), 3))
            else:
                path.append(r(ar[i:j + 1].sum(), 3))
        row["path"] = path
        rows.append(row)
        paths.append(path)

    # Placebo: the same number of random days, many times (with each day's own market model)
    rng = np.random.default_rng(7)
    valid = np.arange(260, len(dates) - 21)
    # one market model per random day is slow; use a rolling-free approximation:
    # pre-compute abnormal returns with a single full-sample beta for the placebo
    b_all, a_all = np.polyfit(mk, cu, 1)
    ar_all = cu - (a_all + b_all * mk)
    csum = np.concatenate([[0], np.cumsum(ar_all)])

    summary = {}
    for key, a, b, label in WINDOWS:
        vals = np.array([x[key] for x in rows if x[key] is not None], dtype=float)
        raw = np.array([x[key + "Raw"] for x in rows if x[key + "Raw"] is not None], dtype=float)
        n = len(vals)
        if n < 2:
            summary[key] = {"label": label, "n": n}
            continue
        t_stat, p_t = stats.ttest_1samp(vals, 0.0)
        draws = rng.choice(valid, size=(5000, n))
        plac = (csum[draws + b + 1] - csum[draws + a]).mean(axis=1)
        p_plac = float((np.abs(plac) >= abs(vals.mean())).mean())
        summary[key] = {
            "label": label, "n": n, "mean": r(vals.mean(), 3), "median": r(np.median(vals), 3),
            "rawMean": r(raw.mean(), 3), "sd": r(vals.std(ddof=1), 3),
            "t": r(t_stat, 3), "p": r(p_t, 5), "pPlacebo": r(p_plac, 4),
            "posShare": r((vals > 0).mean(), 3),
            "placeboSd": r(plac.std(), 3),
        }

    # Average path across events
    P = np.array([[np.nan if v is None else v for v in p] for p in paths], dtype=float)
    avg_path = [[k, r(np.nanmean(P[:, idx]), 3), int(np.sum(~np.isnan(P[:, idx])))]
                for idx, k in enumerate(range(PATH[0], PATH[1] + 1))]

    # Bigger disruptions, bigger moves? CAR(0..+5) vs the mine's share of world supply
    sz = [(x["share"], x["d5"]) for x in rows if x["d5"] is not None]
    size_reg = _ols([v for _, v in sz], [s for s, _ in sz])[1] if len(sz) >= 4 else None

    s5 = summary.get("d5", {})
    sig = s5.get("p") is not None and s5["p"] < 0.05
    return {
        "kind": "event",
        "title": "Mine disruptions",
        "question": "When a big mine is hit by a strike, accident or shutdown, does copper rise?",
        "method": "Event study on daily COMEX copper (HG=F). Abnormal return = copper's return minus the return a market model "
                  "(copper on SPY, fitted over trading days −260 to −21) predicts. Windows are in trading days from the day the news broke.",
        "events": rows,
        "summary": summary,
        "avgPath": avg_path,
        "sizeReg": size_reg,
        "status": "Significant" if sig else "Not significant",
        "result": (f"Avg. abnormal return days 0 to +5: {s5['mean']:+.2f}% (n={s5['n']}, p={s5['p']:.3f})"
                   if s5.get("mean") is not None else "Not enough events"),
    }


# ---------------------------------------------------------------- treatment charges
def treatment_charges(px):
    data = json.loads((ROOT / "data" / "treatment_charges.json").read_text())
    cu = px["COPPER"].dropna()
    tz = cu.index.tz

    def price_on(day):
        t = pd.Timestamp(day)
        if tz is not None:
            t = t.tz_localize(tz)
        s = cu.loc[:t]
        return float(s.iloc[-1]) if len(s) else np.nan

    spot = sorted(data["spot"], key=lambda x: x["date"])
    obs = [{"date": s["date"], "tc": s["tc"], "copper": r(price_on(s["date"]), 4), "source": s["source"]} for s in spot]
    pairs = []
    for a, b in zip(obs, obs[1:]):
        days = (pd.Timestamp(b["date"]) - pd.Timestamp(a["date"])).days
        ret = (b["copper"] / a["copper"] - 1) * 100
        pairs.append({"from": a["date"], "to": b["date"], "days": days,
                      "dTc": r(b["tc"] - a["tc"], 2), "ret": r(ret, 3)})
    _, spot_reg = _ols([p["ret"] for p in pairs], [p["dTc"] for p in pairs])
    short = [p for p in pairs if p["days"] <= 45]  # intervals of about a month or less
    short_reg = _ols([p["ret"] for p in short], [p["dTc"] for p in short])[1] if len(short) >= 6 else None
    level_corr = r(np.corrcoef([o["tc"] for o in obs], [o["copper"] for o in obs])[0, 1], 3)

    # Annual benchmark vs copper's calendar-year return (current year: year to date)
    ye = cu.resample("YE").last()
    bm = sorted(data["benchmark"], key=lambda x: x["year"])
    yrs = []
    for prev, cur in zip(bm, bm[1:]):
        y = cur["year"]
        try:
            end = ye[ye.index.year == y].iloc[0]
            start = ye[ye.index.year == y - 1].iloc[0]
        except IndexError:
            continue
        yrs.append({"year": y, "tc": cur["tc"], "dTc": r(cur["tc"] - prev["tc"], 2),
                    "ret": r((end / start - 1) * 100, 2), "ytd": y == pd.Timestamp.now().year,
                    "avgPrice": r(float(cu[cu.index.year == y].mean()), 3)})
    _, bm_reg = _ols([y["ret"] for y in yrs], [y["dTc"] for y in yrs])
    bm_level_corr = r(np.corrcoef([y["tc"] for y in yrs], [y["avgPrice"] for y in yrs])[0, 1], 3)

    sig = spot_reg["p"] < 0.05
    return {
        "kind": "tc",
        "title": "Treatment charges",
        "question": "Treatment charges fall when mine supply is tight (smelters compete for scarce concentrate). Does copper rise when TCs fall?",
        "method": "Spot: OLS of copper's % return between consecutive Fastmarkets TC index readings on the change in the TC ($/t) over the same dates. "
                  "Benchmark: OLS of copper's calendar-year return on the change in the annual benchmark TC.",
        "spot": obs, "pairs": pairs, "spotReg": spot_reg, "shortReg": short_reg, "levelCorr": level_corr,
        "benchmark": [{"year": b["year"], "tc": b["tc"], "source": b["source"]} for b in bm],
        "years": yrs, "bmReg": bm_reg, "bmLevelCorr": bm_level_corr,
        "status": "Significant" if sig else "Not significant",
        "result": f"Spot: {spot_reg['beta']:+.3f}% copper per +$1/t TC, R² {spot_reg['r2']:.2f}, p={spot_reg['p']:.3f}; "
                  f"TC vs price correlation {level_corr:+.2f}",
    }
