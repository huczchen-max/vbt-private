"""Multi-scale divergence screen (v0.3, 2026-09-23).

Eric: "compile a list of stocks with these types of patterns on a weekly, daily,
hourly scale" — the IOVA shape (price flat in the lower part of a long range while
RSI makes higher highs) and its mirror at a top.

States (same definitions as base_study_wide v0.7 / H22, evaluated at the LAST bar
of each scale, for every R in R_LIST where a flat base of LMIN..LMAX bars is open):
  strict  DIVUP / DIVDN exactly as backtested (pivot-based RSI swing highs)
  broad   price flat (|26-bar price slope| <= BROAD_PX_SLOPE %/bar) in the lower
          (upper) half of the band, RSI > 50 (< 50) and the 26-bar RSI slope
          rising (falling) faster than BROAD_RSI_SLOPE pts/bar — no pivot needed
  COMP / ANTI are reported too so the list can be read against the known states.
H22 verdict: neither state carried an edge in the backtest; this screen exists for
visual inspection and labeling, not as a trading signal.

Scales: weekly (W-FRI, last week may be partial), daily (trading days), hourly
(regular session 1h bars from intraday_fetch.py). LMIN/LMAX are in BARS at every
scale (26-156 weeks / trading days / hours). Liquidity: median close >= $3 and
median $volume per bar >= MIN_DVOL[scale].
v0.2 changes (after run #12 found only 16 hourly bases): (1) the band widths are
scaled to the bar size — R_SCALE[scale] = 1 + (R_weekly - 1) / sqrt(bars per week)
(daily 1.22/1.45/1.89, hourly 1.09/1.18/1.35) so "flat" means the same thing
relative to normal bar-to-bar movement at every scale; (2) a flat window LONGER
than LMAX is no longer excluded (the backtest excluded it) but truncated to the
last LMAX bars and flagged base_capped=True; (3) warrants/preferreds/units/rights
(-WS, -WT, -P-, -U, -R) are dropped; (4) a shape score ranks the lists.

Usage (two passes inside the 'screen' workflow mode):
  python div_screen.py --prices eodhd_cache/eod_us.parquet --universe eodhd_cache/universe.csv \
         --out private/div_screen --scales weekly,daily --needed-out private/div_screen/intraday_needed.txt
  python intraday_fetch.py --needed private/div_screen/intraday_needed.txt
  python div_screen.py ... --intraday eodhd_cache/intraday_1h.parquet --scales weekly,daily,hourly
Outputs: div_screen.csv (one row per ticker x scale x R with an open base),
div_screen.json (deduped lists), div_screen.md (tables), gallery pages
<scale>_<up|dn>_<n>.png with price + RSI panels, and (v0.3) div_series.json —
the bar series (dates, closes, RSI14, base band, RSI pivot indices) for every
listed divergence plus reference tickers (IOVA weekly) — feeds the interactive
review page (VBT/div-screen artifact) where Eric labels the charts.
"""
import argparse, json, math, os, sys, warnings
import numpy as np, pandas as pd
warnings.filterwarnings("ignore", category=RuntimeWarning)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from base_study_wide import (weekly, rsi, pivot_highs_arr, divergence_at, composite_at, slope26, tightness, extra_feats,
                             R_LIST, LMIN, LMAX, FLAT, MIN_PRICE, DIV_K, DIV_MARGIN, DIV_PX_TOL)

MIN_DVOL = {"weekly": 5e6, "daily": 1e6, "hourly": 1.5e5}     # median $volume per bar
BARS_PER_WEEK = {"weekly": 1, "daily": 5, "hourly": 32.5}
R_SCALE = {sc: [round(1 + (R - 1) / math.sqrt(b), 2) for R in R_LIST] for sc, b in BARS_PER_WEEK.items()}   # weekly 1.5/2/3 -> daily 1.22/1.45/1.89 -> hourly 1.09/1.18/1.35
import re
EXCLUDE_RE = re.compile(r"-(WS|WSA|WSB|WT|W|U|R|RT)$|-P-|-P[A-Z]?$")   # warrants, units, rights, preferreds
BROAD_RSI_SLOPE = 0.3      # RSI pts per bar over 26 bars (~8 pts)
BROAD_PX_SLOPE = 0.2       # % of price per bar over 26 bars (~5%) = "flat"
N_PER_SET, PER_PAGE, COLS = 18, 9, 3
TEAL, SLATE, ORANGE, INK, MUTED = "#0F766E", "#64748B", "#C2410C", "#1E293B", "#94A3B8"

# ------------------------------------------------------------ bars
def daily_bars(g):
    df = g.set_index(pd.to_datetime(g["date"])).sort_index()
    px = df["adj_close"] if "adj_close" in df else df["close"]
    return pd.concat([px.rename("close"), (df["close"] * df["volume"]).rename("dvol")], axis=1).dropna(subset=["close"])

def hourly_bars(g):
    df = g.set_index(pd.DatetimeIndex(pd.to_datetime(g["dt"], utc=True)).tz_convert("America/New_York")).sort_index()
    return pd.concat([df["close"].astype(float).rename("close"), (df["close"] * df["volume"]).astype(float).rename("dvol")], axis=1).dropna(subset=["close"])

def open_window_len(v, R, cap):
    """Bars in the longest window ending at the last bar with max/min <= R (scan stops at cap)."""
    e = len(v) - 1; hi = lo = v[e]; s = e
    while s > 0 and e - s + 1 < cap:
        x = v[s - 1]; nhi, nlo = max(hi, x), min(lo, x)
        if nlo <= 0 or nhi / nlo > R: break
        hi, lo = nhi, nlo; s -= 1
    return e - s + 1

# ------------------------------------------------------------ evaluation at the last bar
def evaluate(ticker, scale, w):
    c = w["close"]; v = c.values.astype(float); n = len(v)
    if n < LMIN + 20 or np.nanmin(v) <= 0: return []
    rs = rsi(c); r_ = rs.values; m13 = c.rolling(13).mean().values; m26 = c.rolling(26).mean().values
    retv = c.pct_change().values; dv = w["dvol"].values.astype(float)
    off = max(0, n - LMAX - 60); rhighs = [i + off for i in pivot_highs_arr(r_[off:], DIV_K)]; e = n - 1; rows = []   # pivots only where a base can be
    rsl = slope26(r_, e); psl = slope26(v / v[e] * 100, e)
    for R in R_SCALE[scale]:
        L0 = open_window_len(v, R, LMAX + 1); capped = L0 > LMAX; L = min(L0, LMAX)
        if L < LMIN: continue
        s = e - L + 1; seg = v[s:e + 1]
        if np.median(seg) < MIN_PRICE or np.median(dv[s:e + 1]) < MIN_DVOL[scale]: continue
        hi, lo = seg.max(), seg.min()
        if hi <= lo: continue
        k, _ = np.polyfit(np.arange(L), seg, 1); drift = k * (L - 1) / (hi - lo)
        if not (abs(drift) <= FLAT): continue
        ck, pos = composite_at(v, m13, m26, r_, s, e)
        dk, dd = divergence_at(v, r_, rhighs, s, e)
        ph = [i for i in rhighs if s <= i <= e - DIV_K]
        n_rise = n_fall = 0
        for j in range(len(ph) - 1, 0, -1):
            a, b = ph[j - 1], ph[j]
            if r_[b] >= r_[a] + DIV_MARGIN and v[b] <= v[a] * (1 + DIV_PX_TOL): n_rise += 1
            else: break
        for j in range(len(ph) - 1, 0, -1):
            a, b = ph[j - 1], ph[j]
            if r_[b] <= r_[a] - DIV_MARGIN and v[b] >= v[a] * (1 - DIV_PX_TOL): n_fall += 1
            else: break
        broad_up = bool(pos <= 0.5 and r_[e] > 50 and not np.isnan(rsl) and rsl > BROAD_RSI_SLOPE and abs(psl) <= BROAD_PX_SLOPE)
        broad_dn = bool(pos >= 0.5 and r_[e] < 50 and not np.isnan(rsl) and rsl < -BROAD_RSI_SLOPE and abs(psl) <= BROAD_PX_SLOPE)
        div_dir = "UP" if dk == "DIVUP" else "DN" if dk == "DIVDN" else "UP" if broad_up else "DN" if broad_dn else ""
        grade = "strict" if dk else ("broad" if div_dir else "")
        pre = v[max(0, s - 104):s]
        gap = (dd["rsi_h2"] - dd["rsi_h1"]) if dd else 0.0
        if div_dir == "UP":   score = n_rise + max(0.0, gap) / 10 + (0.5 - pos) + max(0.0, rsl if not np.isnan(rsl) else 0) - abs(psl if not np.isnan(psl) else 0)
        elif div_dir == "DN": score = n_fall + max(0.0, -gap) / 10 + (pos - 0.5) + max(0.0, -rsl if not np.isnan(rsl) else 0) - abs(psl if not np.isnan(psl) else 0)
        else: score = np.nan
        row = dict(ticker=ticker, scale=scale, R=R, state=(ck or dk or ""), div_dir=div_dir, div_grade=grade, score=round(float(score), 2) if div_dir else np.nan,
                   base_len=int(L), base_capped=bool(capped), start=str(c.index[s])[:16], asof=str(c.index[e])[:16], close=round(float(v[e]), 2),
                   base_hi=round(float(hi), 2), base_lo=round(float(lo), 2), range_ratio=round(float(hi / lo), 2), drift=round(float(drift), 2),
                   prior_dd=round(float(lo / pre.max() - 1), 2) if len(pre) > 20 else np.nan,
                   pos=round(float(pos), 2), rsi=round(float(r_[e]), 1), ma13_gt_26=bool(m13[e] > m26[e]) if not np.isnan(m26[e]) else None,
                   rsi_slope26=round(float(rsl), 2) if not np.isnan(rsl) else np.nan, px_slope26=round(float(psl), 2) if not np.isnan(psl) else np.nan,
                   n_rise=n_rise, n_fall=n_fall, n_rsi_pivots=len(ph), med_dvol=round(float(np.median(dv[s:e + 1])), 0),
                   ph_idx=json.dumps([int(i - s) for i in ph[-4:]]), s_idx=int(s), **dd, **tightness(seg))
        row.update(extra_feats(seg, dv[s:e + 1], retv[s:e + 1], row["mad_med"], None))
        rows.append(row)
    return rows

# ------------------------------------------------------------ gallery (price + RSI)
def render(rows, W, scale, out, label):
    import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt; from matplotlib import gridspec
    rows = rows.reset_index(drop=True); pages = math.ceil(len(rows) / PER_PAGE); files = []
    for p in range(pages):
        chunk = rows.iloc[p * PER_PAGE:(p + 1) * PER_PAGE]; nrow = math.ceil(len(chunk) / COLS)
        fig = plt.figure(figsize=(4.8 * COLS, 3.9 * nrow)); outer = gridspec.GridSpec(nrow, COLS, figure=fig, hspace=0.55, wspace=0.25, top=(0.82 if nrow == 1 else 0.93), bottom=(0.12 if nrow == 1 else 0.05))
        for i, (_, r) in enumerate(chunk.iterrows()):
            inner = gridspec.GridSpecFromSubplotSpec(2, 1, subplot_spec=outer[i], height_ratios=[3, 1.3], hspace=0.06)
            axp = fig.add_subplot(inner[0]); axr = fig.add_subplot(inner[1], sharex=axp)
            try:
                w = W[(r.ticker, scale)]; c = w["close"].values.astype(float); rs = rsi(w["close"]).values
                e = len(c) - 1; s = int(r.s_idx); i0 = max(0, s - 26); x = np.arange(i0, e + 1)
                axp.plot(x, c[i0:e + 1], color=INK, lw=1.0); axp.axhspan(r.base_lo, r.base_hi, color=SLATE, alpha=0.10); axp.axvspan(s, e, color=SLATE, alpha=0.10)
                axp.set_yscale("log"); axp.yaxis.set_major_locator(matplotlib.ticker.LogLocator(base=10, subs=(1.0, 2.0, 5.0), numticks=8)); axp.yaxis.set_minor_formatter(matplotlib.ticker.NullFormatter()); axp.yaxis.set_major_formatter(matplotlib.ticker.ScalarFormatter())
                axr.plot(x, rs[i0:e + 1], color=TEAL if r.div_dir == "UP" else ORANGE, lw=1.0); axr.axhline(50, color=MUTED, lw=0.7); axr.set_ylim(10, 90); axr.set_yticks([30, 50, 70])
                for j in json.loads(r.ph_idx):
                    axr.plot([s + j], [rs[s + j]], marker="o", ms=3.5, color=INK, mec=INK, mfc="white")
                    axp.plot([s + j], [c[s + j]], marker="v", ms=4, color=MUTED)
                idx = w.index[i0:e + 1]; ticks = np.linspace(i0, e, 4).astype(int)
                fmt = "%Y-%m" if scale != "hourly" else "%m-%d %H:%M"
                axr.set_xticks(ticks); axr.set_xticklabels([pd.Timestamp(idx[t - i0]).tz_convert("America/New_York").strftime(fmt) if scale == "hourly" else pd.Timestamp(idx[t - i0]).strftime(fmt) for t in ticks], fontsize=6.5)
                plt.setp(axp.get_xticklabels(), visible=False)
                gap = f"RSI highs {r.rsi_h1:.0f}→{r.rsi_h2:.0f}" if pd.notna(r.get("rsi_h1", np.nan)) else "no RSI pivots"
                axp.set_title(f"{r.ticker}  {scale} {r.div_grade} {r.div_dir}  R{r.R}  base {r.base_len}{'+' if r.base_capped else ''} bars  close {r.close}  score {r.score:.1f}\n"
                              f"pos {r.pos:.2f}  RSI {r.rsi:.0f}  slope26 {r.rsi_slope26:+.2f}/bar  {gap}  rises {r.n_rise} falls {r.n_fall}",
                              fontsize=7.5, color=INK, loc="left")
            except Exception as ex:
                axp.set_title(f"{r.ticker}: {type(ex).__name__}: {str(ex)[:60]}", fontsize=7)
            for ax in (axp, axr):
                ax.grid(alpha=0.15); ax.tick_params(labelsize=6.5, colors=SLATE)
                for sp in ax.spines.values(): sp.set_color("#E2E8F0")
        fig.suptitle(f"{label} — page {p + 1}/{pages}   (grey = open base; markers = RSI swing highs used)", fontsize=10, color=TEAL, x=0.01, ha="left", y=0.995)
        f = f"{out}/{scale}_{label.split()[0].lower()}_{p + 1}.png"; fig.savefig(f, dpi=105, bbox_inches="tight"); plt.close(fig); files.append(f)
    return files

# ------------------------------------------------------------ series export (v0.3)
def export_series(dv, W, out, asof, scales, reference=("IOVA",), n_ctx=26):
    """Compact JSON of the bars behind every listed divergence (base + n_ctx bars of context) for the review page."""
    def fmt(idx, scale):
        return [(pd.Timestamp(x).strftime("%Y-%m-%dT%H:%M") if scale == "hourly" else pd.Timestamp(x).strftime("%Y-%m-%d")) for x in idx]
    items = []
    for _, r in dv.iterrows():
        key = (r.ticker, r.scale)
        if key not in W: continue
        w = W[key]; c = w["close"].values.astype(float); rs = rsi(w["close"]).values; e = len(c) - 1; s = int(r.s_idx); i0 = max(0, s - n_ctx)
        piv = [int(j) + (s - i0) for j in json.loads(r.ph_idx)]
        items.append(dict(id=f"{r.ticker}|{r.scale}", ticker=r.ticker, scale=r.scale, dir=r.div_dir, grade=r.div_grade, score=float(r.score), state=r.state, R=float(r.R),
                          base_len=int(r.base_len), capped=bool(r.base_capped), pos=float(r.pos), rsi=float(r.rsi),
                          rsi_h1=(None if pd.isna(r.get("rsi_h1", np.nan)) else float(r.rsi_h1)), rsi_h2=(None if pd.isna(r.get("rsi_h2", np.nan)) else float(r.rsi_h2)),
                          n_rise=int(r.n_rise), n_fall=int(r.n_fall), slope=(None if pd.isna(r.rsi_slope26) else float(r.rsi_slope26)), px_slope=(None if pd.isna(r.px_slope26) else float(r.px_slope26)),
                          prior_dd=(None if pd.isna(r.prior_dd) else float(r.prior_dd)), dvol=float(r.med_dvol), close=float(r.close), lo=float(r.base_lo), hi=float(r.base_hi),
                          s=int(s - i0), t=fmt(w.index[i0:e + 1], r.scale), c=[round(float(x), 4) for x in c[i0:e + 1]], r=[(None if np.isnan(x) else round(float(x), 1)) for x in rs[i0:e + 1]], piv=piv))
    ref = {}
    for tk in reference:
        for sc in scales:
            if (tk, sc) in W:
                w = W[(tk, sc)]; c = w["close"].values.astype(float); rs = rsi(w["close"]).values; i0 = max(0, len(c) - (LMAX + n_ctx))
                ref[f"{tk}|{sc}"] = dict(ticker=tk, scale=sc, t=fmt(w.index[i0:], sc), c=[round(float(x), 4) for x in c[i0:]], r=[(None if np.isnan(x) else round(float(x), 1)) for x in rs[i0:]])
    json.dump(dict(asof=str(asof), scales=scales, n=len(items), items=items, reference=ref, params=dict(R=R_SCALE, LMIN=LMIN, LMAX=LMAX, DIV=dict(K=DIV_K, MARGIN=globals()["DIV_MARGIN"], PX_TOL=globals()["DIV_PX_TOL"]))),
              open(f"{out}/div_series.json", "w"), separators=(",", ":"), default=str)
    return len(items)

# ------------------------------------------------------------ main
def dedup(df):
    """One row per ticker per scale: strict before broad, then by shape score (consecutive RSI highs, RSI gap, band position, RSI slope, price flatness)."""
    if not len(df): return df
    d = df.copy(); d["g"] = d.div_grade.map({"strict": 0, "broad": 1})
    return d.sort_values(["g", "score", "R"], ascending=[True, False, True]).drop_duplicates(["ticker", "scale"]).drop(columns=["g"])

def md_table(d, scale, direction):
    cols = ["ticker", "R", "div_grade", "score", "state", "base_len", "base_capped", "close", "pos", "rsi", "rsi_h1", "rsi_h2", "n_rise" if direction == "UP" else "n_fall", "rsi_slope26", "px_slope26", "med_dvol"]
    if not len(d): return "_none_\n"
    hdr = "| " + " | ".join(cols) + " |\n|" + "---|" * len(cols) + "\n"
    body = ""
    for _, r in d.iterrows():
        vals = []
        for c in cols:
            x = r.get(c, "")
            vals.append("" if (isinstance(x, float) and np.isnan(x)) else (f"{x/1e6:.1f}M" if c == "med_dvol" else str(x)))
        body += "| " + " | ".join(vals) + " |\n"
    return hdr + body

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--prices", required=True); ap.add_argument("--universe", default=None); ap.add_argument("--intraday", default=None)
    ap.add_argument("--out", default="div_screen"); ap.add_argument("--scales", default="weekly,daily"); ap.add_argument("--needed-out", default=None)
    ap.add_argument("--needed-max", type=int, default=4000); ap.add_argument("--max", type=int, default=0); ap.add_argument("--no-gallery", action="store_true")
    ap.add_argument("--div-margin", type=float, default=None, help="override DIV_MARGIN (RSI pts between swing highs; backtest used 3)")
    ap.add_argument("--no-series", action="store_true", help="skip div_series.json (the review-page data)")
    ap.add_argument("--reference", default="IOVA", help="comma-separated reference tickers to include in div_series.json")
    ap.add_argument("--px-tol", type=float, default=None, help="override DIV_PX_TOL (price tolerance between the swing highs; backtest used 0.05)")
    a = ap.parse_args(); os.makedirs(a.out, exist_ok=True); scales = a.scales.split(",")
    import base_study_wide as bsw
    if a.div_margin is not None: bsw.DIV_MARGIN = a.div_margin
    if a.px_tol is not None: bsw.DIV_PX_TOL = a.px_tol
    globals()["DIV_MARGIN"], globals()["DIV_PX_TOL"] = bsw.DIV_MARGIN, bsw.DIV_PX_TOL
    px = pd.read_parquet(a.prices) if a.prices.endswith(".parquet") else pd.read_csv(a.prices)
    listed = None
    if a.universe:
        u = pd.read_csv(a.universe, keep_default_na=False, dtype={"ticker": str}); listed = set(u[u.delisted.astype(str).str.lower() != "true"].ticker)
    asof = pd.to_datetime(px["date"]).max()
    W = {}; rows = []
    groups = list(px.groupby("ticker")); n_t = 0
    for t, g in groups:
        if listed is not None and t not in listed: continue
        if EXCLUDE_RE.search(t): continue
        if pd.to_datetime(g["date"]).max() < asof - pd.Timedelta(days=5): continue     # stale = not trading
        n_t += 1
        if a.max and n_t > a.max: break
        if "weekly" in scales:
            w = weekly(g); W[(t, "weekly")] = w; rows += evaluate(t, "weekly", w)
        if "daily" in scales:
            d = daily_bars(g); W[(t, "daily")] = d; rows += evaluate(t, "daily", d)
        if n_t % 1000 == 0: print(f"  {n_t} tickers, {len(rows)} open-base rows", flush=True)
    print(f"EOD scales done: {n_t} listed tickers, {len(rows)} rows", flush=True)
    if "hourly" in scales and a.intraday and os.path.exists(a.intraday):
        iq = pd.read_parquet(a.intraday); nh = 0
        for t, g in iq.groupby("ticker"):
            if listed is not None and t not in listed: continue
            if EXCLUDE_RE.search(t): continue
            h = hourly_bars(g); W[(t, "hourly")] = h; rows += evaluate(t, "hourly", h); nh += 1
        print(f"hourly done: {nh} tickers with intraday bars; total rows {len(rows)}", flush=True)
    df = pd.DataFrame(rows)
    if not len(df):
        print("no open bases found"); df.to_csv(f"{a.out}/div_screen.csv", index=False); return
    df.to_csv(f"{a.out}/div_screen.csv", index=False)
    # ---- who needs intraday bars: any open base on weekly or daily, divergences first, then COMP/ANTI, then $volume
    if a.needed_out:
        d = df[df.scale.isin(["weekly", "daily"])].copy()
        d["prio"] = np.where(d.div_grade == "strict", 0, np.where(d.div_grade == "broad", 1, np.where(d.state != "", 2, 3)))
        need = d.sort_values(["prio", "med_dvol"], ascending=[True, False]).drop_duplicates("ticker")
        need = need.head(a.needed_max)
        with open(a.needed_out, "w") as f: f.write("\n".join(need.ticker.tolist()) + "\n")
        print(f"intraday needed: {len(need)} tickers (of {d.ticker.nunique()} with an open weekly/daily base) -> {a.needed_out}")
    # ---- lists + markdown
    dv = dedup(df[df.div_dir != ""]); lists = {}; md = [f"# Divergence screen — as of {str(asof.date())} (weekly bar may be a partial week)\n",
        "H22 backtest verdict: neither state carried an edge; this is a visual-inspection list, not a signal. strict = pivot-based DIVUP/DIVDN as backtested; broad = flat price + RSI trending through 50 (no pivot required).\n"]
    for sc in scales:
        lists[sc] = {}
        for dd, name in (("UP", "Bottom: price flat/low, RSI rising (IOVA shape)"), ("DN", "Top: price flat/high, RSI fading")):
            d = dv[(dv.scale == sc) & (dv.div_dir == dd)]
            lists[sc][dd] = dict(strict=sorted(d[d.div_grade == "strict"].ticker.tolist()), broad=sorted(d[d.div_grade == "broad"].ticker.tolist()))
            md.append(f"\n## {sc} — {name}  (strict {len(lists[sc][dd]['strict'])}, broad {len(lists[sc][dd]['broad'])})\n\n" + md_table(d, sc, dd))
        st = df[(df.scale == sc)]
        lists[sc]["counts"] = dict(open_base_rows=int(len(st)), tickers=int(st.ticker.nunique()), COMP=int((st.state == "COMP").sum()), ANTI=int((st.state == "ANTI").sum()),
                                   DIVUP=int((st.state == "DIVUP").sum()), DIVDN=int((st.state == "DIVDN").sum()), asof=str(st["asof"].max()) if len(st) else None)
    json.dump(dict(asof=str(asof.date()), scales=scales, lists=lists, params=dict(R=R_SCALE, LMIN=LMIN, LMAX=LMAX, FLAT=FLAT, MIN_PRICE=MIN_PRICE, MIN_DVOL=MIN_DVOL,
              DIV=dict(K=DIV_K, MARGIN=globals()["DIV_MARGIN"], PX_TOL=globals()["DIV_PX_TOL"]), BROAD=dict(rsi_slope=BROAD_RSI_SLOPE, px_slope=BROAD_PX_SLOPE))),
              open(f"{a.out}/div_screen.json", "w"), indent=1, default=str)
    open(f"{a.out}/div_screen.md", "w").write("\n".join(md))
    if not a.no_series:
        print("series exported:", export_series(dv, W, a.out, asof.date(), scales, reference=tuple(x for x in a.reference.split(",") if x)))
    print(json.dumps({sc: lists[sc]["counts"] for sc in scales}, indent=1))
    for sc in scales: print(sc, "UP strict", lists[sc]["UP"]["strict"], "broad", lists[sc]["UP"]["broad"][:30]); print(sc, "DN strict", lists[sc]["DN"]["strict"], "broad", lists[sc]["DN"]["broad"][:30])
    if a.no_gallery: return
    for sc in scales:
        for dd, label in (("UP", "Bottom divergence"), ("DN", "Top divergence")):
            d = dv[(dv.scale == sc) & (dv.div_dir == dd)].head(N_PER_SET)
            if len(d): print(sc, dd, "->", render(d, W, sc, a.out, f"{label} — {sc}"))

if __name__ == "__main__":
    main()
