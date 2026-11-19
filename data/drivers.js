// Candidate drivers. Update status and result as you test each one.
// status: "Not tested", "Testing", "Significant", "Not significant"
// Drivers with the same name as an entry in scripts/drivers_analysis.py get a click-to-open regression.
window.DRIVERS = [
  { category: "Macro", driver: "S&P 500 returns", measure: "Monthly return (5Y)", source: "yfinance (SPY)", status: "Not tested", result: "" },
  { category: "Macro", driver: "US dollar", measure: "Monthly % change in DXY (5Y)", source: "yfinance (DX-Y.NYB)", status: "Not tested", result: "" },
  { category: "Macro", driver: "10-year Treasury yield", measure: "Monthly change in yield, pp (5Y)", source: "yfinance (^TNX)", status: "Not tested", result: "" },
  { category: "Demand", driver: "AI stocks", measure: "Monthly return (5Y)", source: "yfinance (AIQ)", status: "Not tested", result: "" },
  { category: "Demand", driver: "Semiconductor stocks", measure: "Monthly return (5Y)", source: "yfinance (SMH)", status: "Not tested", result: "" },
  { category: "Demand", driver: "China stocks", measure: "Monthly return (5Y)", source: "yfinance (FXI)", status: "Not tested", result: "" },
  { category: "Demand", driver: "Electrification", measure: "Monthly return of grid-infrastructure stocks (5Y)", source: "yfinance (GRID)", status: "Not tested", result: "" },
  { category: "Commodities", driver: "Crude oil", measure: "Monthly return (5Y)", source: "yfinance (CL=F)", status: "Not tested", result: "" },
  { category: "Supply", driver: "Mine disruptions", measure: "Strike / outage event dates (Chile, Peru, DRC)", source: "News, company reports", status: "Not tested", result: "" },
  { category: "Supply", driver: "Treatment charges", measure: "Spot TC/RC level and change", source: "Industry reports, news", status: "Not tested", result: "" },
  { category: "Inventories", driver: "Exchange inventories", measure: "LME + COMEX + SHFE stocks, monthly change", source: "LME, CME, SHFE", status: "Not tested", result: "" },
  { category: "Positioning", driver: "Speculative positioning", measure: "CFTC managed-money net length", source: "CFTC Commitments of Traders", status: "Not tested", result: "" },
  { category: "News", driver: "Strength Index", measure: "Monthly change in decayed headline score (5Y)", source: "Google News headlines, scored on this site", status: "Not tested", result: "" }
];
