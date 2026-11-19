// Drivers tab: table with click-to-expand regression analysis per driver.
(function () {
  const A = (window.DRIVER_ANALYSIS && window.DRIVER_ANALYSIS.drivers) || {};
  const $ = (s) => document.querySelector(s);
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const n2 = (v, d = 2) => (v == null ? "—" : Number(v).toFixed(d));
  const pFmt = (p) => (p == null ? "—" : p < 0.0001 ? "< 0.0001" : p.toFixed(4));
  // ---------------- time frame (switch at the top of the tab) ----------------
  const BASE = ["5Y monthly", "10Y monthly", "1Y weekly"];
  const FRAMES = [...BASE, "Average"];
  let TF = "5Y monthly";
  try { const saved = localStorage.getItem("driverFrame"); if (FRAMES.includes(saved)) TF = saved; } catch (e) {}
  // Driver analysis for the chosen time frame (falls back to the top-level 5Y monthly fields)
  const pick = (a) => (a && a.frames && a.frames[TF] ? { ...a, ...a.frames[TF] } : a);
  const mean = (xs) => { const v = xs.filter((x) => x != null && isFinite(x)); return v.length ? v.reduce((s, x) => s + x, 0) / v.length : null; };
  // Average of the regression statistics across the three time frames
  function averaged(a) {
    const fs = BASE.map((k) => a.frames && a.frames[k]).filter(Boolean);
    if (!fs.length) return null;
    const ann = (f) => f.coef.alpha.est * (f.per === "week" ? 52 : 12);
    const sig = fs.filter((f) => f.coef.beta.p < 0.05).length;
    const out = {
      fs, sig,
      beta: mean(fs.map((f) => f.coef.beta.est)), betaP: mean(fs.map((f) => f.coef.beta.p)),
      r2: mean(fs.map((f) => f.r2)), adjR2: mean(fs.map((f) => f.adjR2)), corr: mean(fs.map((f) => f.corr)),
      alphaAnn: mean(fs.map(ann)), alphaP: mean(fs.map((f) => f.coef.alpha.p)),
      dw: mean(fs.map((f) => f.durbinWatson)), bp: mean(fs.map((f) => f.breuschPaganP)), jb: mean(fs.map((f) => f.jarqueBeraP)),
      betaMin: Math.min(...fs.map((f) => f.coef.beta.est)), betaMax: Math.max(...fs.map((f) => f.coef.beta.est)),
    };
    out.status = sig >= 2 ? "Significant" : "Not significant";
    out.result = `Average: beta ${out.beta.toFixed(2)}, R² ${out.r2.toFixed(2)}, significant in ${sig} of ${fs.length}`;
    return out;
  }
  const benchName = (a) => esc(a.bench || "S&P 500");
  const sigPill = (p) => (p == null ? "" : p < 0.05 ? '<span class="pill good">Significant at 5%</span>' : '<span class="pill bad">Not significant</span>');
  const statusPill = (s) => {
    const c = { Significant: "good", "Not significant": "bad", Testing: "mid" }[s] || "";
    return `<span class="pill ${c}">${esc(s)}</span>`;
  };

  // ---------------- SVG chart helpers ----------------
  const W = 520, H = 340, P = { l: 56, r: 16, t: 14, b: 46 };
  function nice(min, max) { const pad = (max - min) * 0.08 || 1; return [min - pad, max + pad]; }
  function ticks(min, max, n = 5) {
    const step = Math.pow(10, Math.floor(Math.log10((max - min) / n)));
    const s = [1, 2, 2.5, 5, 10].map((m) => m * step).find((st) => (max - min) / st <= n) || step * 10;
    const out = []; for (let v = Math.ceil(min / s) * s; v <= max + 1e-9; v += s) out.push(+v.toFixed(10)); return out;
  }
  function frame(xr, yr, xl, yl, xFmt = (v) => v, yFmt = (v) => v) {
    const sx = (v) => P.l + ((v - xr[0]) / (xr[1] - xr[0])) * (W - P.l - P.r);
    const sy = (v) => P.t + (1 - (v - yr[0]) / (yr[1] - yr[0])) * (H - P.t - P.b);
    let g = "";
    ticks(...yr).forEach((t) => { g += `<line x1="${P.l}" x2="${W - P.r}" y1="${sy(t)}" y2="${sy(t)}" stroke="#f1e9de"/><text x="${P.l - 8}" y="${sy(t) + 4}" text-anchor="end" class="ax">${yFmt(t)}</text>`; });
    if (xl !== null) ticks(...xr).forEach((t) => { g += `<line y1="${P.t}" y2="${H - P.b}" x1="${sx(t)}" x2="${sx(t)}" stroke="#f1e9de"/><text x="${sx(t)}" y="${H - P.b + 16}" text-anchor="middle" class="ax">${xFmt(t)}</text>`; });
    if (xl) g += `<text x="${(P.l + W - P.r) / 2}" y="${H - 6}" text-anchor="middle" class="axl">${esc(xl)}</text>`;
    g += `<text transform="translate(14 ${(P.t + H - P.b) / 2}) rotate(-90)" text-anchor="middle" class="axl">${esc(yl)}</text>`;
    return { sx, sy, g };
  }
  const svg = (inner, title) => `<figure class="plot"><figcaption>${title}</figcaption><svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(title)}">${inner}</svg></figure>`;

  function scatterPlot(a) {
    const xs = a.points.map((p) => p[1]), ys = a.points.map((p) => p[2]);
    const xr = nice(Math.min(...xs), Math.max(...xs)), yr = nice(Math.min(...ys), Math.max(...ys));
    const isRate = (a.kind === "rate" || a.kind === "level");
    const { sx, sy, g } = frame(xr, yr, a.xLabel, a.yLabel, (v) => (isRate ? (v > 0 ? "+" : "") + v : v + "%"), (v) => v + "%");
    const al = a.coef.alpha.est, b = a.coef.beta.est;
    let s = g;
    if (xr[0] < 0 && xr[1] > 0) s += `<line x1="${sx(0)}" x2="${sx(0)}" y1="${P.t}" y2="${H - P.b}" stroke="#d8c8b6"/>`;
    if (yr[0] < 0 && yr[1] > 0) s += `<line x1="${P.l}" x2="${W - P.r}" y1="${sy(0)}" y2="${sy(0)}" stroke="#d8c8b6"/>`;
    s += a.points.map((p) => `<circle cx="${sx(p[1])}" cy="${sy(p[2])}" r="4.5" class="dot"><title>${p[0]}: ${isRate ? `${esc(a.short2 || "10Y yield")} ${p[1] > 0 ? "+" : ""}${n2(p[1])} ${esc(a.unit || "pp")}` : `${benchName(a)} ${n2(p[1])}%`}, copper ${n2(p[2])}%</title></circle>`).join("");
    s += `<line x1="${sx(xr[0])}" y1="${sy(al + b * xr[0])}" x2="${sx(xr[1])}" y2="${sy(al + b * xr[1])}" class="fit"/>`;
    s += `<text x="${W - P.r - 6}" y="${P.t + 16}" text-anchor="end" class="eq">ŷ = ${n2(al)} ${b < 0 ? "−" : "+"} ${n2(Math.abs(b))}x &nbsp; R² = ${n2(a.r2)}</text>`;
    return svg(s, isRate ? `Regression: copper ${a.adj || "monthly"} return vs change in ${esc(a.short2 || "10-year yield")}` : `Regression: copper vs ${benchName(a)} ${a.adj || "monthly"} returns`);
  }

  function residualPlot(a) {
    const xs = a.points.map((p) => p[3]), es = a.points.map((p) => p[4]);
    const m = Math.max(...es.map(Math.abs));
    const xr = nice(Math.min(...xs), Math.max(...xs)), yr = [-m * 1.12, m * 1.12];
    const { sx, sy, g } = frame(xr, yr, "Fitted copper return, %", "Residual, % points", (v) => v + "%", (v) => v);
    const sd = a.residStd;
    let s = g + `<rect x="${P.l}" width="${W - P.l - P.r}" y="${sy(sd)}" height="${sy(-sd) - sy(sd)}" fill="rgba(176,97,47,.06)"/>`;
    s += `<line x1="${P.l}" x2="${W - P.r}" y1="${sy(0)}" y2="${sy(0)}" class="fit"/>`;
    s += a.points.map((p) => `<circle cx="${sx(p[3])}" cy="${sy(p[4])}" r="4.5" class="dot ${Math.abs(p[4]) > 2 * sd ? "out" : ""}"><title>${p[0]}: fitted ${n2(p[3])}%, residual ${n2(p[4])}</title></circle>`).join("");
    return svg(s, "Residuals vs fitted values (shaded band = ±1 std. error)");
  }

  function timePlot(rows, title, yl, opts = {}) {
    const vals = rows.map((r) => r[1]);
    const lo = Math.min(...vals, opts.ref ?? Infinity, 0), hi = Math.max(...vals, opts.ref ?? -Infinity);
    const yr = opts.symmetric ? [-Math.max(...vals.map(Math.abs)) * 1.1, Math.max(...vals.map(Math.abs)) * 1.1] : nice(lo, hi);
    const n = rows.length, xr = [0, n - 1];
    const { sx, sy, g } = frame(xr, yr, null, yl, null, (v) => v);
    let s = g;
    const step = Math.max(1, Math.round(n / 6));
    rows.forEach((r, i) => { if (i % step === 0) s += `<text x="${sx(i)}" y="${H - P.b + 16}" text-anchor="middle" class="ax">${r[0]}</text>`; });
    if (opts.ref != null) s += `<line x1="${P.l}" x2="${W - P.r}" y1="${sy(opts.ref)}" y2="${sy(opts.ref)}" stroke="#ab9a88" stroke-dasharray="4 4"/><text x="${W - P.r}" y="${sy(opts.ref) - 5}" text-anchor="end" class="ax">${opts.refLabel || ""}</text>`;
    if (opts.bars) {
      const bw = Math.max(2, (W - P.l - P.r) / n - 2);
      s += `<line x1="${P.l}" x2="${W - P.r}" y1="${sy(0)}" y2="${sy(0)}" stroke="#ab9a88"/>`;
      s += rows.map((r, i) => `<rect x="${sx(i) - bw / 2}" width="${bw}" y="${Math.min(sy(0), sy(r[1]))}" height="${Math.abs(sy(r[1]) - sy(0))}" fill="${r[1] >= 0 ? "#1a7f4b" : "#c0392b"}" opacity=".75"><title>${r[0]}: ${n2(r[1])}</title></rect>`).join("");
    } else {
      s += `<polyline fill="none" stroke="#6b3418" stroke-width="2" points="${rows.map((r, i) => `${sx(i)},${sy(r[1])}`).join(" ")}"/>`;
      s += rows.map((r, i) => `<circle cx="${sx(i)}" cy="${sy(r[1])}" r="6" fill="transparent"><title>${r[0]}: ${n2(r[1])}</title></circle>`).join("");
    }
    return svg(s, title);
  }

  // ---------------- detail panel ----------------
  // ---------------- supply drivers (event study, treatment charges) ----------------
  const pct = (v, d = 2) => (v == null ? "—" : (v > 0 ? "+" : "") + Number(v).toFixed(d) + "%");
  const sgn = (v, d = 2) => (v == null ? "—" : (v > 0 ? "+" : "") + Number(v).toFixed(d));
  const tfNote = `<p class="small note">This driver isn't a return regression, so the time-frame switch above doesn't change it.</p>`;
  const dcard = (l, v, sub = "") => `<div class="dstat"><div class="l">${l}</div><div class="v">${v}</div><div class="s">${sub}</div></div>`;
  const money = (v) => (v == null ? "—" : (v < 0 ? "−$" : "$") + Math.abs(v).toFixed(2));
  const dnum = (s) => new Date(s + "T00:00:00Z").getTime();

  function eventDetail(a) {
    const S = a.summary, s0 = S.d0 || {}, s5 = S.d5 || {}, s20 = S.d20 || {}, sp = S.pre || {};
    const sigTxt = (s) => (s.p == null ? "" : s.p < 0.05 ? "statistically significant" : "not statistically significant");
    // average path + each event's path
    const ks = a.avgPath.map((p) => p[0]);
    const all = a.events.flatMap((e) => e.path.filter((v) => v != null));
    const m = Math.max(4, ...all.map(Math.abs)) * 1.05;
    const fr = frame([ks[0], ks[ks.length - 1]], [-m, m], "Trading days from the news (day 0)", "Cumulative abnormal return, %", (v) => v, (v) => v + "%");
    let s = fr.g + `<line x1="${fr.sx(0)}" x2="${fr.sx(0)}" y1="${P.t}" y2="${H - P.b}" stroke="#d8c8b6" stroke-dasharray="4 4"/>`;
    s += `<line x1="${P.l}" x2="${W - P.r}" y1="${fr.sy(0)}" y2="${fr.sy(0)}" stroke="#ab9a88"/>`;
    a.events.forEach((e) => {
      const pts = e.path.map((v, i) => (v == null ? null : `${fr.sx(ks[i])},${fr.sy(v)}`)).filter(Boolean).join(" ");
      s += `<polyline fill="none" stroke="#b0612f" stroke-opacity=".22" stroke-width="1.2" points="${pts}"><title>${esc(e.mine)} ${e.date}</title></polyline>`;
    });
    s += `<polyline fill="none" stroke="#6b3418" stroke-width="3" points="${a.avgPath.map((p) => `${fr.sx(p[0])},${fr.sy(p[1])}`).join(" ")}"/>`;
    s += a.avgPath.map((p) => `<circle cx="${fr.sx(p[0])}" cy="${fr.sy(p[1])}" r="5" fill="transparent"><title>Day ${p[0]}: average ${pct(p[1])} (${p[2]} events)</title></circle>`).join("");
    const pathPlot = svg(s, "Copper's abnormal return around each disruption (thin) and the average (thick)");

    // size vs 5-day reaction
    const ev5 = a.events.filter((e) => e.d5 != null);
    const xs = ev5.map((e) => e.share), ys = ev5.map((e) => e.d5);
    const xr = [0, Math.max(...xs) * 1.15], ym = Math.max(...ys.map(Math.abs)) * 1.2;
    const f2 = frame(xr, [-ym, ym], "Mine's share of world mine supply, %", "Abnormal return, days 0 to +5", (v) => v + "%", (v) => v + "%");
    let s2 = f2.g + `<line x1="${P.l}" x2="${W - P.r}" y1="${f2.sy(0)}" y2="${f2.sy(0)}" stroke="#ab9a88"/>`;
    s2 += ev5.map((e) => `<circle cx="${f2.sx(e.share)}" cy="${f2.sy(e.d5)}" r="5" class="dot"><title>${esc(e.mine)} (${e.date}): ${pct(e.d5)}</title></circle><text x="${f2.sx(e.share) + 7}" y="${f2.sy(e.d5) + 4}" class="ax">${esc(e.mine)}</text>`).join("");
    const sr = a.sizeReg;
    if (sr) s2 += `<line x1="${f2.sx(xr[0])}" y1="${f2.sy(sr.alpha + sr.beta * xr[0])}" x2="${f2.sx(xr[1])}" y2="${f2.sy(sr.alpha + sr.beta * xr[1])}" class="fit"/><text x="${W - P.r - 6}" y="${P.t + 16}" text-anchor="end" class="eq">slope ${sgn(sr.beta)} pp per 1% of supply · p = ${pFmt(sr.p)}</text>`;
    const sizePlot = svg(s2, "Do bigger disruptions move copper more?");

    const winRows = ["pre", "d0", "d5", "d20"].map((k) => S[k]).filter((v) => v && v.n).map((v) =>
      `<tr><td>${esc(v.label)}</td><td class="num">${v.n}</td><td class="num"><b>${pct(v.mean)}</b></td><td class="num">${pct(v.median)}</td><td class="num">${pct(v.rawMean)}</td><td class="num">${Math.round(v.posShare * 100)}%</td><td class="num">${n2(v.t)}</td><td class="num">${pFmt(v.p)}</td><td class="num">${pFmt(v.pPlacebo)}</td></tr>`).join("");
    const evRows = a.events.slice().reverse().map((e) => `<tr><td>${esc(e.date)}</td><td><b>${esc(e.mine)}</b><br><span class="muted small">${esc(e.country)} · ${esc(e.type)}</span></td><td class="num">${n2(e.share, 1)}%</td><td class="num">${pct(e.d0)}</td><td class="num">${pct(e.d5)}</td><td class="num">${e.d20 == null ? '<span class="muted small">not yet</span>' : pct(e.d20)}</td><td class="num">${pct(e.d5Raw)}</td><td class="small">${esc(e.what)} <a href="${esc(e.source)}" target="_blank" rel="noopener">source</a></td></tr>`).join("");

    return `<div class="dpanel">
      ${tfNote}
      <div class="dhead"><div><h3>${esc(a.title)}</h3><p class="muted">${esc(a.question)}</p></div>
        <div class="muted small">${a.events.length} events · event study<br>${esc(a.method)}</div></div>
      <div class="dstats">
        ${dcard("Day 0", pct(s0.mean), `avg. abnormal return · p = ${pFmt(s0.p)}`)}
        ${dcard("Days 0 to +5", pct(s5.mean), `p = ${pFmt(s5.p)} · placebo p = ${pFmt(s5.pPlacebo)}`)}
        ${dcard("Days 0 to +20", pct(s20.mean), `p = ${pFmt(s20.p)} · n = ${s20.n || 0}`)}
        ${dcard("Copper up (0 to +5)", s5.posShare == null ? "—" : Math.round(s5.posShare * 100) + "%", `of ${s5.n} events`)}
        ${dcard("Days −5 to −1", pct(sp.mean), "before the news")}
        ${dcard("Size effect", sr ? sgn(sr.beta) + " pp" : "—", sr ? `per 1% of world supply · p = ${pFmt(sr.p)}` : "")}
      </div>
      <ul class="interp">
        <li><b>Day 0 ${pct(s0.mean)}:</b> on the day the news broke, copper did ${(s0.mean || 0) >= 0 ? "better" : "worse"} than the stock market predicted, by ${n2(Math.abs(s0.mean || 0))} percentage points on average (${sigTxt(s0)}, p = ${pFmt(s0.p)}).</li>
        <li><b>First week ${pct(s5.mean)}:</b> over days 0 to +5 the average abnormal return was ${pct(s5.mean)}, with copper up in ${Math.round((s5.posShare || 0) * 100)}% of events. This is ${sigTxt(s5)}. The placebo test (the same number of random days drawn 5,000 times) gives p = ${pFmt(s5.pPlacebo)}.</li>
        <li><b>First month ${pct(s20.mean)}:</b> ${s20.mean != null && s5.mean != null && Math.abs(s20.mean) < Math.abs(s5.mean) ? "the effect fades over the following weeks, which fits a short-lived price reaction rather than a lasting shift." : "a month out the effect is about as big or bigger, though other news piles up over 20 days, so this window is noisier."}</li>
        <li><b>Before the news ${pct(sp.mean)}:</b> ${Math.abs(sp.mean || 0) > Math.abs(s0.mean || 0) ? "copper moved noticeably in the days before, so some events (strike votes, failed talks) were partly priced in early." : "little movement beforehand, so most of these disruptions were genuine surprises."}</li>
        <li><b>Keep in mind:</b> with ${a.events.length} events, one big market day can swing the average. El Teniente (Aug 1, 2025) came right after copper's tariff crash, and the two Grasberg dates overlap. Strikes are often announced in advance, while accidents are true surprises.</li>
      </ul>
      <div class="plots">${pathPlot}${sizePlot}</div>
      <h4>Average reaction by window</h4>
      <div class="tablewrap"><table>
        <thead><tr><th>Window</th><th class="num">Events</th><th class="num">Avg. abnormal</th><th class="num">Median</th><th class="num">Avg. raw return</th><th class="num">Copper up</th><th class="num">t</th><th class="num">p (t-test)</th><th class="num">p (placebo)</th></tr></thead>
        <tbody>${winRows}</tbody></table></div>
      <h4>The events</h4>
      <div class="tablewrap"><table>
        <thead><tr><th>Date</th><th>Mine</th><th class="num">Share of supply</th><th class="num">Day 0</th><th class="num">Days 0 to +5</th><th class="num">Days 0 to +20</th><th class="num">Raw 0 to +5</th><th>What happened</th></tr></thead>
        <tbody>${evRows}</tbody></table></div>
      <p class="muted small">Abnormal returns are shown; "raw" is copper's actual return. Add events to <a href="https://github.com/nathanielh34/copper-analysis/edit/main/data/mine_disruptions.json" target="_blank" rel="noopener">data/mine_disruptions.json</a> and they're included on the next data run.</p>
      <div class="next"><h4>What this suggests adding next</h4><ul>
        <li><b>Split by type:</b> compare surprise accidents (Grasberg, El Teniente, Kamoa-Kakula) with announced strikes. Surprises should move the price more.</li>
        <li><b>Link to the strength index:</b> these dates should show up as "Supply disruption" headlines. Check they're scored +1.</li>
        <li><b>Add disruption ends</b> (strike settled, mine restarts) as a separate set. Copper should dip when supply comes back.</li>
      </ul></div>
    </div>`;
  }

  function tcDetail(a) {
    const sr = a.spotReg, br = a.bmReg, sh = a.shortReg;
    // TC over time: spot points and annual benchmark steps
    const t0 = dnum(a.spot[0].date) - 400 * 864e5, t1 = dnum(a.spot[a.spot.length - 1].date) + 30 * 864e5;
    const bmIn = a.benchmark.filter((b) => dnum(b.year + "-12-31") >= t0);
    const tcs = [...a.spot.map((p) => p.tc), ...bmIn.map((b) => b.tc)];
    const yr = nice(Math.min(...tcs), Math.max(...tcs));
    const f1 = frame([t0, t1], yr, null, "$ per tonne", null, (v) => "$" + v);
    let s = f1.g + `<line x1="${P.l}" x2="${W - P.r}" y1="${f1.sy(0)}" y2="${f1.sy(0)}" stroke="#ab9a88"/>`;
    for (let y = new Date(t0).getUTCFullYear() + 1; dnum(y + "-01-01") < t1; y++) s += `<text x="${f1.sx(dnum(y + "-01-01"))}" y="${H - P.b + 16}" text-anchor="middle" class="ax">${y}</text>`;
    bmIn.forEach((b) => {
      const x0 = f1.sx(Math.max(t0, dnum(b.year + "-01-01"))), x1 = f1.sx(Math.min(t1, dnum(b.year + "-12-31")));
      s += `<line x1="${x0}" x2="${x1}" y1="${f1.sy(b.tc)}" y2="${f1.sy(b.tc)}" stroke="#1f6f8b" stroke-width="2.5" stroke-dasharray="6 3"><title>${b.year} benchmark: $${b.tc}</title></line>`;
    });
    s += `<polyline fill="none" stroke="#6b3418" stroke-width="2" points="${a.spot.map((p) => `${f1.sx(dnum(p.date))},${f1.sy(p.tc)}`).join(" ")}"/>`;
    s += a.spot.map((p) => `<circle cx="${f1.sx(dnum(p.date))}" cy="${f1.sy(p.tc)}" r="3.5" fill="#6b3418"><title>${p.date}: spot TC $${n2(p.tc)}/t, copper $${n2(p.copper)}/lb</title></circle>`).join("");
    s += `<text x="${W - P.r - 4}" y="${P.t + 14}" text-anchor="end" class="ax">── spot (Fastmarkets) &nbsp; - - annual benchmark</text>`;
    const tcPlot = svg(s, "Copper concentrate treatment charges");

    // copper price vs TC level
    const cx = a.spot.map((p) => p.tc), cy = a.spot.map((p) => p.copper);
    const f3 = frame(nice(Math.min(...cx), Math.max(...cx)), nice(Math.min(...cy), Math.max(...cy)), "Spot TC, $ per tonne", "Copper, $ per lb", (v) => "$" + v, (v) => "$" + v);
    let s3 = f3.g + a.spot.map((p) => `<circle cx="${f3.sx(p.tc)}" cy="${f3.sy(p.copper)}" r="4.5" class="dot"><title>${p.date}: TC $${n2(p.tc)}, copper $${n2(p.copper)}</title></circle>`).join("");
    s3 += `<text x="${W - P.r - 6}" y="${P.t + 16}" text-anchor="end" class="eq">correlation ${sgn(a.levelCorr)}</text>`;
    const levelPlot = svg(s3, "Copper price vs treatment charge level");

    // regression: copper return vs TC change between readings
    const px_ = a.pairs.map((p) => p.dTc), py_ = a.pairs.map((p) => p.ret);
    const xr2 = nice(Math.min(...px_), Math.max(...px_)), yr2 = nice(Math.min(...py_), Math.max(...py_));
    const f2 = frame(xr2, yr2, "Change in spot TC between readings, $/t", "Copper return over the same dates, %", (v) => v, (v) => v + "%");
    let s2 = f2.g;
    if (xr2[0] < 0 && xr2[1] > 0) s2 += `<line x1="${f2.sx(0)}" x2="${f2.sx(0)}" y1="${P.t}" y2="${H - P.b}" stroke="#d8c8b6"/>`;
    if (yr2[0] < 0 && yr2[1] > 0) s2 += `<line x1="${P.l}" x2="${W - P.r}" y1="${f2.sy(0)}" y2="${f2.sy(0)}" stroke="#d8c8b6"/>`;
    s2 += a.pairs.map((p) => `<circle cx="${f2.sx(p.dTc)}" cy="${f2.sy(p.ret)}" r="${p.days > 45 ? 6 : 4}" class="dot ${p.days > 45 ? "out" : ""}"><title>${p.from} → ${p.to} (${p.days} days): TC ${sgn(p.dTc)}, copper ${pct(p.ret)}</title></circle>`).join("");
    s2 += `<line x1="${f2.sx(xr2[0])}" y1="${f2.sy(sr.alpha + sr.beta * xr2[0])}" x2="${f2.sx(xr2[1])}" y2="${f2.sy(sr.alpha + sr.beta * xr2[1])}" class="fit"/>`;
    s2 += `<text x="${W - P.r - 6}" y="${P.t + 16}" text-anchor="end" class="eq">ŷ = ${n2(sr.alpha)} ${sr.beta < 0 ? "−" : "+"} ${n2(Math.abs(sr.beta), 3)}x &nbsp; R² = ${n2(sr.r2)}</text>`;
    const regPlot = svg(s2, "Regression: copper return vs change in spot TC (red = gap over 45 days)");

    // benchmark years
    const yrsRows = a.years.map((y) => `<tr><td>${y.year}${y.ytd ? " <span class='muted small'>(to date)</span>" : ""}</td><td class="num">$${n2(y.tc)}</td><td class="num">${sgn(y.dTc)}</td><td class="num">${pct(y.ret, 1)}</td><td class="num">$${n2(y.avgPrice)}</td></tr>`).join("");
    const regRow = (label, x) => x ? `<tr><td>${label}</td><td class="num">${x.n}</td><td class="num">${n2(x.beta, 4)}</td><td class="num">${n2(x.ciLow, 3)} to ${n2(x.ciHigh, 3)}</td><td class="num">${n2(x.r2, 3)}</td><td class="num">${n2(x.corr, 3)}</td><td class="num">${pFmt(x.p)}</td><td>${x.p < 0.05 ? '<span class="pill good">Significant</span>' : '<span class="pill bad">Not significant</span>'}</td></tr>` : "";
    const first = a.spot[0].date, last = a.spot[a.spot.length - 1].date;

    return `<div class="dpanel">
      ${tfNote}
      <div class="dhead"><div><h3>${esc(a.title)}</h3><p class="muted">${esc(a.question)}</p></div>
        <div class="muted small">${a.spot.length} spot readings, ${esc(first)} to ${esc(last)} · ${a.benchmark.length} annual benchmarks<br>${esc(a.method)}</div></div>
      <div class="dstats">
        ${dcard("Spot TC now", money(a.spot[a.spot.length - 1].tc), "per tonne (negative = smelters pay miners)")}
        ${dcard("TC vs copper price", sgn(a.levelCorr), "correlation of levels")}
        ${dcard("Spot sensitivity", sgn(sr.beta * 10, 2) + "%", `copper per +$10/t TC · p = ${pFmt(sr.p)}`)}
        ${dcard("Spot R²", n2(sr.r2), `n = ${sr.n} intervals`)}
        ${dcard("Benchmark sensitivity", sgn(br.beta * 10, 2) + "%", `copper's year per +$10/t · p = ${pFmt(br.p)}`)}
        ${dcard(`${a.benchmark[a.benchmark.length - 1].year} benchmark`, money(a.benchmark[a.benchmark.length - 1].tc), "annual contract TC")}
      </div>
      <ul class="interp">
        <li><b>${a.levelCorr < 0 ? "Levels move opposite, as expected" : "Levels don't move opposite"}:</b> the correlation between the spot TC and the copper price is ${sgn(a.levelCorr)}. ${a.levelCorr < -0.5 ? "As concentrate got scarcer and TCs collapsed into negative territory, copper climbed to records. That's the supply-tightness story." : a.levelCorr < 0 ? "Lower TCs went with higher copper prices, but loosely." : "Surprisingly, TCs and copper did not move opposite in this sample."}</li>
        <li><b>Changes are a weaker signal:</b> regressing copper's return on the change in the TC between readings gives ${sgn(sr.beta * 10, 2)}% per +$10/t (R² ${n2(sr.r2)}, p = ${pFmt(sr.p)}). ${sr.p < 0.05 ? "That's significant: when TCs fell between readings, copper tended to rise." : "That's not significant: over weeks or months, TC changes don't line up reliably with copper moves. Both trend together over years, but short-term copper is driven by other things (the dollar, stocks, tariffs)."}${sh ? ` Using only gaps of 45 days or less (n = ${sh.n}): ${sgn(sh.beta * 10, 2)}% per +$10/t, p = ${pFmt(sh.p)}.` : ""}</li>
        <li><b>Annual benchmark:</b> across ${br.n} years, copper's calendar-year return vs the change in the benchmark gives ${sgn(br.beta * 10, 2)}% per +$10/t (p = ${pFmt(br.p)}). With only ${br.n} data points, this can't be significant unless the link is very strong.</li>
        <li><b>Keep in mind:</b> TCs and copper prices are both results of the same thing (how tight mine supply is), so this shows they move together, not that one causes the other. The spot series has gaps (nothing before Aug 2023, and almost nothing from Oct 2024 to Sep 2025), and Fastmarkets changed the index weighting on Sep 4, 2026.</li>
      </ul>
      <div class="plots">${tcPlot}${levelPlot}</div>
      <div class="plots">${regPlot}<div>
        <h4>Annual benchmark vs copper</h4>
        <div class="tablewrap"><table><thead><tr><th>Year</th><th class="num">Benchmark TC</th><th class="num">Change</th><th class="num">Copper return</th><th class="num">Avg. price</th></tr></thead><tbody>${yrsRows}</tbody></table></div>
      </div></div>
      <h4>Regression output</h4>
      <div class="tablewrap"><table>
        <thead><tr><th>Model</th><th class="num">n</th><th class="num">Slope (% per $1/t)</th><th class="num">95% CI</th><th class="num">R²</th><th class="num">Correlation</th><th class="num">p-value</th><th></th></tr></thead>
        <tbody>${regRow("Spot: all intervals", sr)}${regRow("Spot: gaps ≤ 45 days", sh)}${regRow("Annual benchmark", br)}</tbody></table></div>
      <p class="muted small">Spot values are the Fastmarkets copper concentrates TC index, cif Asia Pacific, as quoted in Fastmarkets articles. Add new readings to <a href="https://github.com/nathanielh34/copper-analysis/edit/main/data/treatment_charges.json" target="_blank" rel="noopener">data/treatment_charges.json</a> to fill the gaps.</p>
      <div class="next"><h4>What this suggests adding next</h4><ul>
        <li><b>Fill the gaps:</b> a full weekly TC series (Fastmarkets, SMM or Platts) would allow a proper monthly regression alongside the other drivers.</li>
        <li><b>Lead-lag test:</b> check whether TC changes <i>predict</i> next month's copper return. Concentrate tightness shows up at smelters before it reaches refined metal.</li>
        <li><b>Combine with disruptions:</b> the big TC drops followed Cobre Panama (Nov 2023) and Grasberg (Sep 2025). Both drivers measure the same mine-supply squeeze.</li>
      </ul></div>
    </div>`;
  }

  function averageDetail(a) {
    const v = averaged(a), isRate = (a.kind === "rate" || a.kind === "level"), bn = benchName(a);
    const card = (l, val, sub = "") => `<div class="dstat"><div class="l">${l}</div><div class="v">${val}</div><div class="s">${sub}</div></div>`;
    const bLabel = isRate ? (a.sensLabel || "Sensitivity") : "Beta";
    const agree = v.sig === v.fs.length ? "in every time frame" : v.sig === 0 ? "in none of the time frames" : `in ${v.sig} of ${v.fs.length} time frames`;
    const sameSign = v.fs.every((f) => Math.sign(f.coef.beta.est) === Math.sign(v.fs[0].coef.beta.est));
    const row = (f) => `<tr><td>${esc(f.frame)}</td><td class="num">${f.n}</td><td class="num">${n2(f.coef.beta.est, 3)}</td><td class="num">${pFmt(f.coef.beta.p)}</td><td class="num">${n2(f.r2, 3)}</td><td class="num">${n2(f.adjR2, 3)}</td><td class="num">${n2(f.corr, 3)}</td><td class="num">${n2(f.coef.alpha.est * (f.per === "week" ? 52 : 12), 1)}%</td><td class="num">${n2(f.durbinWatson)}</td><td>${f.coef.beta.p < 0.05 ? '<span class="pill good">Significant</span>' : '<span class="pill bad">Not significant</span>'}</td></tr>`;
    // small grouped bar chart: beta and R² by time frame
    const bars = (key, label, get, fmt) => {
      const vals = [...v.fs.map(get), key === "beta" ? v.beta : v.r2];
      const names = [...v.fs.map((f) => f.frame), "Average"];
      const m = Math.max(...vals.map(Math.abs)) * 1.15 || 1, lo = Math.min(0, ...vals) < 0 ? -m : 0;
      const { sx, sy, g } = frame([0, names.length], [lo, m], null, label, null, (t) => fmt(t));
      const bw = (W - P.l - P.r) / names.length * 0.55;
      let s = g + `<line x1="${P.l}" x2="${W - P.r}" y1="${sy(0)}" y2="${sy(0)}" stroke="#ab9a88"/>`;
      names.forEach((nm, i) => {
        const x = sx(i + 0.5), y = sy(vals[i]);
        s += `<rect x="${x - bw / 2}" width="${bw}" y="${Math.min(y, sy(0))}" height="${Math.abs(y - sy(0))}" fill="${nm === "Average" ? "#6b3418" : "#b0612f"}" opacity="${nm === "Average" ? 1 : 0.55}"><title>${nm}: ${n2(vals[i], 3)}</title></rect>`;
        s += `<text x="${x}" y="${vals[i] >= 0 ? y - 6 : y + 14}" text-anchor="middle" class="ax">${n2(vals[i])}</text>`;
        s += `<text x="${x}" y="${H - P.b + 16}" text-anchor="middle" class="ax">${nm}</text>`;
      });
      return svg(s, `${label} by time frame`);
    };
    return `
      <div class="dpanel">
        <div class="dhead">
          <div><h3>${esc(a.title)}</h3><p class="muted">${esc(a.question)}</p></div>
          <div class="muted small">Average of the 5Y monthly, 10Y monthly and 1Y weekly regressions<br>Each time frame counts equally.</div>
        </div>
        <div class="dstats">
          ${card(`Average ${bLabel.toLowerCase()}`, n2(v.beta) + (isRate ? "%" : ""), `range ${n2(v.betaMin)} to ${n2(v.betaMax)}`)}
          ${card("Average R²", n2(v.r2), `avg. adj. R² ${n2(v.adjR2)}`)}
          ${card("Average correlation", n2(v.corr), `Copper vs ${bn}`)}
          ${card(isRate ? "Avg. intercept (annual)" : "Avg. alpha (annual)", n2(v.alphaAnn, 1) + "%", `avg. p = ${pFmt(v.alphaP)}`)}
          ${card(`Average ${isRate ? "sensitivity" : "beta"} p-value`, pFmt(v.betaP), "see note below")}
          ${card("Significant at 5%", `${v.sig} of ${v.fs.length}`, "time frames")}
        </div>
        <ul class="interp">
          <li><b>Consistency:</b> the relationship is statistically significant ${agree}${sameSign ? `, and the ${isRate ? "sensitivity" : "beta"} has the same sign (${v.beta >= 0 ? "positive" : "negative"}) every time` : `${v.sig ? ", but" : ", and"} the sign of the ${isRate ? "sensitivity" : "beta"} flips between time frames, so the direction isn't reliable`}.</li>
          <li><b>Average ${isRate ? "sensitivity" : "beta"} ${n2(v.beta)}:</b> ${isRate ? `across the three samples, a +1 ${esc(a.unit || "pp")} change in the ${esc(a.short2 || "driver")} lined up with about ${n2(Math.abs(v.beta))}% ${v.beta >= 0 ? "higher" : "lower"} copper returns` : `across the three samples, a 1% move in the ${bn} lined up with about a ${n2(v.beta)}% move in copper`}. The time frames range from ${n2(v.betaMin)} to ${n2(v.betaMax)}.</li>
          <li><b>Average R² ${n2(v.r2)}:</b> the ${bn} explains about ${Math.round(v.r2 * 100)}% of copper's moves on average across the three time frames.</li>
          <li><b>${isRate ? "The intercept" : "Alpha"} is annualized before averaging</b> (monthly × 12, weekly × 52) so the weekly and monthly numbers are comparable.</li>
          <li><b>Read the average p-value with care:</b> averaging p-values isn't a formal test. "Significant in ${v.sig} of ${v.fs.length}" is the better summary, and the three samples overlap (the last year is in all of them), so they aren't independent checks.</li>
        </ul>
        <div class="plots">
          ${bars("beta", isRate ? "Sensitivity" : "Beta", (f) => f.coef.beta.est, (t) => +t.toFixed(2))}
          ${bars("r2", "R²", (f) => f.r2, (t) => +t.toFixed(2))}
        </div>
        <h4>Side by side</h4>
        <div class="tablewrap"><table>
          <thead><tr><th>Time frame</th><th class="num">n</th><th class="num">${isRate ? "Sensitivity" : "Beta"}</th><th class="num">p-value</th><th class="num">R²</th><th class="num">Adj. R²</th><th class="num">Correlation</th><th class="num">${isRate ? "Intercept" : "Alpha"} (annual)</th><th class="num">Durbin-Watson</th><th></th></tr></thead>
          <tbody>${v.fs.map(row).join("")}
            <tr class="avgrow"><td><b>Average</b></td><td class="num">—</td><td class="num"><b>${n2(v.beta, 3)}</b></td><td class="num">${pFmt(v.betaP)}</td><td class="num"><b>${n2(v.r2, 3)}</b></td><td class="num">${n2(v.adjR2, 3)}</td><td class="num">${n2(v.corr, 3)}</td><td class="num">${n2(v.alphaAnn, 1)}%</td><td class="num">${n2(v.dw)}</td><td>${statusPill(v.status)}</td></tr>
          </tbody></table></div>
        <p class="muted small">Switch to a single time frame above for that regression's scatter plot, residuals, rolling beta and full diagnostics.</p>
      </div>`;
  }

  function detail(a) {
    if (a.kind === "event") return eventDetail(a);
    if (a.kind === "tc") return tcDetail(a);
    if (TF === "Average" && a.frames) return averageDetail(a);
    a = pick(a);
    const b = a.coef.beta, al = a.coef.alpha, bn = benchName(a);
    const per = a.per || "month", adj = a.adj || "monthly";
    const annAlpha = al.est * (per === "week" ? 52 : 12);
    const card = (l, v, sub = "") => `<div class="dstat"><div class="l">${l}</div><div class="v">${v}</div><div class="s">${sub}</div></div>`;
    const flag = (ok, good, bad) => (ok ? `<span class="pill good">${good}</span>` : `<span class="pill mid">${bad}</span>`);
    const interp = [
      `<b>Beta ${n2(b.est)}:</b> over ${esc(a.period)}, when the ${bn} rose 1% in a ${per}, copper rose about ${n2(b.est)}% on average. ` +
        (b.ciHigh < 0 ? `The 95% range (${n2(b.ciLow)} to ${n2(b.ciHigh)}) is entirely below zero, so copper tends to move <b>opposite</b> to the ${bn}.` :
         b.ciLow > 1 ? `Copper moves <b>more than 1-for-1</b> with the ${bn} (the 95% range is entirely above 1).` :
         b.ciHigh < 1 ? `Copper moves <b>less than 1-for-1</b> with the ${bn} (the 95% range is entirely below 1).` :
         `The 95% range (${n2(b.ciLow)} to ${n2(b.ciHigh)}) includes 1, so we can't rule out that copper moves 1-for-1 with the ${bn}.`),
      `<b>R² ${n2(a.r2)}:</b> the ${bn} explains about <b>${Math.round(a.r2 * 100)}%</b> of copper's ${per}-to-${per} moves. The other <b>${Math.round((1 - a.r2) * 100)}%</b> is what copper-specific drivers (mine supply, China demand, inventories, the strength index) need to explain.`,
      `<b>Correlation ${n2(a.corr)}:</b> ${Math.abs(a.corr) >= 0.7 ? "a strong" : Math.abs(a.corr) >= 0.4 ? "a moderate" : "a weak"} positive relationship (correlation is the square root of R² in a one-variable regression).`,
      `<b>Alpha ${n2(al.est)}% per ${per}</b> (about ${n2(annAlpha, 1)}% a year): ${al.p < 0.05 ? "statistically significant, so copper earned returns beyond what its exposure to this driver explains." : `not statistically significant (p = ${pFmt(al.p)}), so there's no evidence copper did better or worse than this driver predicts.`}`,
    ];
    const isRate = (a.kind === "rate" || a.kind === "level");
    const dir = (v) => (v >= 0 ? "positive" : "negative");
    interp[2] = `<b>Correlation ${n2(a.corr)}:</b> ${Math.abs(a.corr) >= 0.7 ? "a strong" : Math.abs(a.corr) >= 0.4 ? "a moderate" : "a weak"} ${dir(a.corr)} relationship (in a one-variable regression, R² is the correlation squared).`;
    if (isRate) {
      const step = a.step ?? 0.25, unit = a.unit || "pp", what = a.short2 || "10-year yield";
      const q = b.est * step;
      interp[0] = `<b>Sensitivity ${n2(b.est)}:</b> over ${esc(a.period)}, for each 1 ${esc(a.unitLong === "percentage point" ? "percentage point (100 basis points)" : a.unitLong || "percentage point (100 basis points)")} rise in the ${esc(what)} in a ${per}, copper returned about <b>${n2(Math.abs(b.est))}%</b> ${b.est >= 0 ? "more" : "less"} on average. A +${step} ${unit}${step > 1 ? "s" : ""} ${per} works out to about ${n2(q)}%. ` +
        (b.p < 0.05 ? `The 95% range (${n2(b.ciLow)} to ${n2(b.ciHigh)}) excludes zero, so the effect is statistically significant.` : `The 95% range (${n2(b.ciLow)} to ${n2(b.ciHigh)}) includes zero, so we can't rule out that rates have no effect.`);
      interp[1] = `<b>R² ${n2(a.r2)}:</b> changes in the ${esc(what)} explain about <b>${Math.round(a.r2 * 100)}%</b> of copper's ${per}-to-${per} moves on their own.`;
      interp[3] = `<b>Intercept ${n2(al.est)}% per ${per}:</b> copper's average ${adj} return in a ${per} when the ${esc(what)} didn't change${al.p < 0.05 ? " (statistically significant)." : ` (not significant, p = ${pFmt(al.p)}). Unlike alpha in the stock regressions, this isn't a measure of outperformance.`}`;
      interp.push(`<b>Keep in mind:</b> ${a.caveat || "rates and stocks often move together. Some of this relationship may be the stock market in disguise, so the real test is a multiple regression with both the S&amp;P 500 and yield changes."}`);
    }
    return `
      <div class="dpanel">
        ${a.short ? `<p class="small note">Only ${a.n} ${per}s of history are available for this driver, so the ${esc(a.frame)} sample is shorter than the others.</p>` : ""}
        <div class="dhead">
          <div><h3>${esc(a.title)}</h3><p class="muted">${esc(a.question)}</p></div>
          <div class="muted small">${esc(a.period)} · n = ${a.n} ${per}s<br>${esc(a.method)}</div>
        </div>
        <div class="dstats">
          ${isRate ? card(a.sensLabel || "Rate sensitivity", n2(b.est) + "%", `Copper return per +1 ${esc(a.unit || "pp")} · 95% CI ${n2(b.ciLow)} to ${n2(b.ciHigh)}`) : card(`${esc(a.frame || "5Y monthly")} beta`, n2(b.est), `95% CI ${n2(b.ciLow)} to ${n2(b.ciHigh)}`)}
          ${card("R²", n2(a.r2), `adj. R² ${n2(a.adjR2)}`)}
          ${card("Correlation", n2(a.corr), `Copper vs ${bn}`)}
          ${card(isRate ? `Intercept (${adj})` : `Alpha (${adj})`, n2(al.est) + "%", `p = ${pFmt(al.p)}`)}
          ${card(isRate ? "Sensitivity p-value" : "Beta p-value", pFmt(b.p), isRate ? "H₀: no effect" : "H₀: beta = 0")}
          ${isRate ? card(a.levelLabel || "10Y yield now", n2(a.yieldNow) + (a.levelSuffix ?? "%"), "latest close") : card("Beta ≠ 1 test", `p = ${pFmt(a.betaVsOne.p)}`, "H₀: beta = 1")}
        </div>
        <div class="equation">Copper return = <b>${n2(al.est, 3)}</b> ${b.est < 0 ? "−" : "+"} <b>${n2(Math.abs(b.est), 3)}</b> × ${isRate ? `change in ${esc(a.short2 || "10Y yield")} (${esc(a.unit || "pp")})` : bn + " return"} + ε</div>
        <ul class="interp">${interp.map((t) => `<li>${t}</li>`).join("")}</ul>

        <div class="plots">${scatterPlot(a)}${residualPlot(a)}</div>
        <div class="plots">
          ${timePlot(a.points.map((p) => [p[0], p[4]]), `Residuals over time (unexplained copper return each ${per})`, "Residual", { bars: true, symmetric: true })}
          ${a.rollingBeta && a.rollingBeta.length ? (isRate
            ? timePlot(a.rollingBeta, a.rollTitle || "Rolling sensitivity (is it stable?)", `% per +1 ${a.unit || "pp"}`, { ref: 0, refLabel: "0 = no effect" })
            : timePlot(a.rollingBeta, a.rollTitle || "Rolling beta (how stable is beta?)", "Beta", { ref: 1, refLabel: "beta = 1 (moves with market)" })) : ""}
        </div>

        <div class="dtables">
          <div>
            <h4>Regression output</h4>
            <div class="tablewrap"><table>
              <thead><tr><th></th><th class="num">Coef.</th><th class="num">Std. err.</th><th class="num">t</th><th class="num">p-value</th><th class="num">95% CI</th></tr></thead>
              <tbody>
                <tr><td>${isRate ? "Intercept" : "Alpha (intercept)"}</td><td class="num">${n2(al.est, 4)}</td><td class="num">${n2(al.se, 4)}</td><td class="num">${n2(al.t)}</td><td class="num">${pFmt(al.p)}</td><td class="num">${n2(al.ciLow, 3)} to ${n2(al.ciHigh, 3)}</td></tr>
                <tr><td>${isRate ? `Δ ${esc(a.short2 || "10Y yield")} (${esc(a.unit || "pp")})` : `Beta (${bn})`}</td><td class="num">${n2(b.est, 4)}</td><td class="num">${n2(b.se, 4)}</td><td class="num">${n2(b.t)}</td><td class="num">${pFmt(b.p)}</td><td class="num">${n2(b.ciLow, 3)} to ${n2(b.ciHigh, 3)}</td></tr>
              </tbody></table></div>
            <p class="muted small">n = ${a.n} · R² = ${n2(a.r2, 4)} · Adj. R² = ${n2(a.adjR2, 4)} · F = ${n2(a.fStat)} (p ${pFmt(a.fP)}) · Residual std. error = ${n2(a.residStd)}% ${sigPill(b.p)}</p>
          </div>
          <div>
            <h4>Diagnostics (are the regression's assumptions OK?)</h4>
            <div class="tablewrap"><table>
              <thead><tr><th>Test</th><th class="num">Value</th><th>Reading</th></tr></thead>
              <tbody>
                <tr><td>Durbin-Watson<br><span class="muted small">residuals independent ${per} to ${per}?</span></td><td class="num">${n2(a.durbinWatson)}</td><td>${flag(a.durbinWatson > 1.5 && a.durbinWatson < 2.5, "No autocorrelation", "Possible autocorrelation")}</td></tr>
                <tr><td>Breusch-Pagan<br><span class="muted small">constant residual spread?</span></td><td class="num">p ${pFmt(a.breuschPaganP)}</td><td>${flag(a.breuschPaganP > 0.05, "Constant variance", "Heteroskedasticity")}</td></tr>
                <tr><td>Jarque-Bera<br><span class="muted small">residuals normally distributed?</span></td><td class="num">p ${pFmt(a.jarqueBeraP)}</td><td>${flag(a.jarqueBeraP > 0.05, "Looks normal", "Fat tails / skew")}</td></tr>
                <tr><td>Skew / kurtosis</td><td class="num">${n2(a.skew)} / ${n2(a.kurtosis)}</td><td class="muted small">normal = 0 / 3</td></tr>
              </tbody></table></div>
          </div>
        </div>

        <div class="next">
          <h4>What this suggests adding next</h4>
          <ul>
            ${isRate ? (a.next ? a.next.map((t) => `<li>${t}</li>`).join("") : `<li><b>Control for the market.</b> Run copper on the S&amp;P 500 <i>and</i> yield changes together. If the yield coefficient stays significant, rates matter for copper beyond their effect on stocks in general.</li>
            <li><b>Try copper's residuals from the S&amp;P 500 regression</b> as the left-hand variable: that asks whether rates explain the copper-specific part of its moves.</li>
            <li><b>Real vs nominal:</b> split the 10-year yield into inflation expectations and real yield (TIPS) to see which part matters.</li>`)
            : `<li><b>Use this as the baseline.</b> The ${Math.round((1 - a.r2) * 100)}% of variation the market doesn't explain is what each copper-specific driver must account for. Test the next drivers on copper's <i>residuals</i> (or add them as extra variables) so you aren't re-measuring the market.</li>
            <li><b>Multiple regression:</b> add the US dollar, China stocks, oil and the strength index alongside the ${bn} and watch whether adjusted R² rises.</li>`}
            ${a.breuschPaganP != null && a.breuschPaganP <= 0.05 ? "<li><b>Robust standard errors</b> (HC1): the Breusch-Pagan test flags changing variance, so p-values should be recomputed with robust errors.</li>" : ""}
            ${a.jarqueBeraP != null && a.jarqueBeraP <= 0.05 ? `<li><b>Check the outliers</b> (red dots in the residual plot): find which ${per}s they are and whether a news event explains them. That's a direct link to your strength index.</li>` : "<li><b>Look at the largest residuals</b> and match them to news events; that links this baseline to your strength index.</li>"}
            <li><b>Rolling ${isRate ? "sensitivity" : "beta"}</b> (${esc(a.rollLabel || "36-month")} window) shows whether the relationship is stable; if it shifts a lot, use a shorter window when projecting.</li>
          </ul>
        </div>
      </div>`;
  }

  // ---------------- table ----------------
  window.renderDrivers = function (drivers, tableEl, filtersEl, frameEl) {
    let filter = "All";
    // "Monthly return (5Y)" -> "Weekly return (1Y)" etc. for drivers with an analysis
    const frameMeasure = (m) => TF === "Average" ? m.replace(/^Monthly /, "").replace(/^./, (c) => c.toUpperCase()).replace("(5Y)", "(average of 3 time frames)")
      : m.replace(/^Monthly/, TF.endsWith("weekly") ? "Weekly" : "Monthly").replace("(5Y)", `(${TF.split(" ")[0]})`);
    const statusOf = (d) => {
      const raw = A[d.driver];
      if (raw && TF === "Average" && raw.frames) { const v = averaged(raw); return { status: v.status, result: v.result }; }
      const a = pick(raw); return a ? { status: a.status, result: a.result } : d;
    };
    const open = new Set(Object.keys(A).slice(0, 1)); // first analysed driver starts open
    function draw() {
      const rows = filter === "All" ? drivers : drivers.filter((d) => d.category === filter);
      tableEl.innerHTML = `<thead><tr><th></th><th>Category</th><th>Driver</th><th>Measure</th><th>Source</th><th>Status</th><th>Result</th></tr></thead><tbody>` +
        rows.map((d) => {
          const a = A[d.driver], isOpen = a && open.has(d.driver);
          return `<tr class="${a ? "clickable" : ""} ${isOpen ? "open" : ""}" data-d="${esc(d.driver)}">
              <td class="chev">${a ? (isOpen ? "▾" : "▸") : ""}</td><td>${esc(d.category)}</td><td><b>${esc(d.driver)}</b>${a ? ' <span class="pill blue">Analysis</span>' : ""}</td>
              <td>${esc(a ? frameMeasure(d.measure) : d.measure)}</td><td>${esc(d.source)}</td><td>${statusPill(statusOf(d).status)}</td><td>${esc(statusOf(d).result)}</td></tr>` +
            (isOpen ? `<tr class="drow"><td colspan="7">${detail(a)}</td></tr>` : "");
        }).join("") + "</tbody>";
      tableEl.querySelectorAll("tr.clickable").forEach((tr) => (tr.onclick = () => {
        const k = tr.dataset.d; open.has(k) ? open.delete(k) : open.add(k); draw();
      }));
    }
    const cats = ["All", ...new Set(drivers.map((d) => d.category))];
    const drawFilters = () => {
      filtersEl.innerHTML = cats.map((c) => `<button class="${c === filter ? "on" : ""}">${esc(c)}</button>`).join("");
      filtersEl.querySelectorAll("button").forEach((b, i) => (b.onclick = () => { filter = cats[i]; drawFilters(); draw(); }));
    };
    const drawFrames = () => {
      if (!frameEl) return;
      frameEl.innerHTML = `<span class="tf-label">Time frame</span>` + FRAMES.map((f) => `<button class="${f === TF ? "on" : ""}">${esc(f)}</button>`).join("");
      frameEl.querySelectorAll("button").forEach((b, i) => (b.onclick = () => {
        TF = FRAMES[i];
        try { localStorage.setItem("driverFrame", TF); } catch (e) {}
        drawFrames(); draw();
      }));
    };
    drawFrames(); drawFilters(); draw();
  };
})();
