# Copper Analysis (Fools Gold Analysis)

A small website for the copper price-driver project: the plan, candidate drivers, the news strength index, the projection log and findings. It is a copy of the XAR defense site, re-pointed at copper.

The copper price is the continuous front-month COMEX copper futures contract (Yahoo Finance ticker `HG=F`), in US dollars per pound. Because it rolls from one contract to the next, the series can jump slightly on roll dates.

## Viewing it

- **Locally:** double-click `index.html`. It works without a server.
- **Online:** turn on GitHub Pages (Settings → Pages → Deploy from branch → `main` / root). The site will be at `https://nathanielh34.github.io/copper-analysis/`.

## Updating it

All content lives in `data/`. Edit a file, save, refresh.

| File | What it holds |
|---|---|
| `data/projections.js` | One entry per projection, including the futures price that day. Fill in `actual` after the target date; error, direction hit-rate and range hit-rate are calculated for you. |
| `data/drivers.js` | Candidate drivers and their test status (`Not tested`, `Testing`, `Significant`, `Not significant`). |
| `data/findings.js` | Findings journal (`Confirmed`, `Testing`, `Rejected`, `Idea`). |
| `data/scoring_rules.json` | Keyword rules for the strength index. Scores are by **price impact**: a mine strike is +1 (less supply), a new mine or an inventory build is −1. |
| `data/score_overrides.json` | Hand-corrected scores for individual headlines. |

Each `.js` file is a JavaScript list. Copy an existing entry, paste it below, and change the values. Keep the commas between entries.

## Structure

```
index.html        page layout and plan text
assets/style.css  styling
assets/app.js     tables, sorting, filters, projection stats
assets/watch.js   Copper Watch tab (chart, stats, headlines)
assets/drivers.js Drivers tab regressions
assets/strength.js Strength Index tab
scripts/          data jobs run by GitHub Actions
data/             your data and generated data
```

## Automatic data (GitHub Actions)

- **Update copper market data** (`.github/workflows/update-market.yml`) runs about every 2 hours on weekdays. It fetches copper prices and headlines (`scripts/fetch_market.py`), updates the strength index with the last few weeks of headlines (`scripts/strength_index.py`), and reruns the driver regressions (`scripts/drivers_analysis.py`: S&P 500, China stocks, US dollar, crude oil, 10-year yield, strength index).
- **Strength index backfill** (`.github/workflows/strength-backfill.yml`) collects about 5 years of past copper headlines week by week. Run it once from the **Actions** tab; it takes a few hours and resumes where it left off if it stops early.
- To refresh right away: **Actions** tab → pick the workflow → **Run workflow**.
- Because these jobs commit to the repo, run `git pull` before you start editing.
- Charts use TradingView Lightweight Charts (Apache 2.0, see `assets/vendor/`).

## Running the phase-1 analysis yourself

```
pip install -r requirements.txt
python analysis/01_market_factor.py
```

This downloads weekly copper, S&P 500, US dollar index and 10-year yield data, runs the macro-factor regression, saves `analysis/output/market_factor.md`, and updates `data/results.js` so the site shows the results.
