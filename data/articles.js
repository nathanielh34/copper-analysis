// News Strength Index log.
// One entry per article. score: +1 (bullish for copper), -1 (bearish for copper), 0 (neutral).
// Scoring rules are listed on the "Strength Index" tab: keep them fixed.
// The site computes the running total automatically.
window.ARTICLES = [
  // Example entry (delete or replace):
  {
    date: "2026-11-11",
    source: "WSJ",
    headline: "Example: replace with a real headline",
    category: "Supply",
    score: 0,
    note: "Template row. Scores: +1 / 0 / -1"
  }
];
