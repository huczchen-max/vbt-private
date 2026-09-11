"""Long-base pattern study — wide universe (v0.2, 2026-09-11).

Pattern (Eric): extended base (A) -> slow grind (B) -> range break (C), any
timescale, deep prior drawdown NOT required. Questions: how long does B last,
and is the break direction predictable BEFORE it happens (lead features)?

Definition (weekly bars, adjusted close):
  window(e) = longest window ending at e with max(close)/min(close) <= R
  BASE      = window(b-1), length >= LMIN, flat (linear drift <= FLAT x band)
  BREAK b   = bar b blows the range; UP if close > base max, DOWN if < base min
  CONFIRM   = CONFIRM_WK later still beyond the edge, else FAKEOUT
  phase B   = weeks from base low (UP) / base high (DOWN) to the break
  LEAD      = features at e-8 / e-13 using only data to that bar (no lookahead)
Inputs: EODHD parquet cache (eodhd_fetch.py) or the legacy prices.csv.
Outputs (in --out dir): base_events.csv, base_live.csv (bases open NOW),
  base_summary.json, printed summary. Control = SPY (and SMH if present).
"""
import argparse, json, sys
import numpy as np, pandas as pd

R_LIST = [1.5, 2.0]; LMIN = 26; CONFIRM_WK = 4; FWD = [13, 26]; FLAT = 0.4
MIN_PRICE = 3.0            # median close over the base
MIN_WK_DOLLAR_VOL = 5e6    # median weekly $ volume over the base (~$1M/day)
BENCH = ("SPY", "SMH", "QQQ")

# ------------------------------------------------------------ helpers
def weekly(df):
    df = df.set_index(pd.to_datetime(df["date"])).sort_index()
    px = df["adj_close"] if "adj_close" in df else df["close"]
    dv = (df["close"] * df["volume"]).rename("dvol")
    w = pd.concat([px.rename("close"), dv], axis=1).resample("W-FRI").agg({"close": "last", "dvol": "sum"}).dropna(subset=["close"])
    return w

def rsi(c, n=14):
    d = c.diff(); up = d.clip(lower=0); dn = -d.clip(upper=0)
    ru = up.ewm(alpha=1/n, adjust=False).mean(); rd = dn.ewm(alpha=1/n, adjust=False).mean()
    return 100 - 100 / (1 + ru / rd.replace(0, np.nan))

def pivot_lows(c, k=4):
    v = c.values; return [i for i in range(k, len(v) - k) if v[i] == v[i-k:i+k+1].min()]

def longest_window_len(v, R):
    n = len(v); L = np.zeros(n, dtype=int); s = 0
    for e in range(n):
        while s <= e and v[s:e+1].max() / v[s:e+1].min() > R:
            s += 1
        L[e] = e - s + 1
    return L

def lead_features(c, ma13, ma26, rs, plows, s, t, tag):
    """Causal features at bar t for a base starting at s."""
    bt = c.iloc[s:t+1]; bhi, blo = bt.max(), bt.min(); f = {}
    f[f"pos_{tag}"] = round(float((c.iloc[t] - blo) / (bhi - blo)), 2) if bhi > blo else np.nan
    f[f"ma_{tag}"] = bool(ma13.iloc[t] > ma26.iloc[t]) if not np.isnan(ma26.iloc[t]) else None
    f[f"slope_{tag}"] = round(float(ma13.iloc[t] / ma13.iloc[t-13] - 1), 3) if t >= 13 and not np.isnan(ma13.iloc[t-13]) else np.nan
    f[f"rsi_{tag}"] = round(float(rs.iloc[t]), 1)
    pl = [i for i in plows if s + (t - s)//2 <= i <= t - 4]
    f[f"hl_{tag}"] = sum(1 for a, z in zip(pl, pl[1:]) if c.iloc[z] > c.iloc[a])
    f[f"wk_since_low_{tag}"] = int(t - (int(bt.values.argmin()) + s))
    return f

# ------------------------------------------------------------ detector
def detect(ticker, w, benches, R, delisted=False, live_only=False):
    c = w["close"]; n = len(c); v = c.values.astype(float)
    if n < LMIN + 5 or np.nanmin(v) <= 0:
        return [], None
    L = longest_window_len(v, R)
    ma13 = c.rolling(13).mean(); ma26 = c.rolling(26).mean(); ma200 = c.rolling(200, min_periods=100).mean()
    rs = rsi(c); ret = c.pct_change(); plows = sorted(pivot_lows(c))
    events = []; last_break = -1

    def base_ok(s, e):
        base = c.iloc[s:e+1]
        if base.median() < MIN_PRICE or w["dvol"].iloc[s:e+1].median() < MIN_WK_DOLLAR_VOL:
            return None
        hi, lo = base.max(), base.min()
        x = np.arange(len(base)); k, _ = np.polyfit(x, base.values, 1)
        drift = k * (len(base) - 1) / (hi - lo) if hi > lo else np.nan
        if not (abs(drift) <= FLAT):
            return None
        return base, hi, lo, drift

    # ---- live base (no break yet) at the last bar
    live = None
    e = n - 1
    if L[e] >= LMIN:
        s = e - L[e] + 1; ok = base_ok(s, e)
        if ok:
            base, hi, lo, drift = ok
            pre = c.iloc[max(0, s-104):s]
            live = dict(ticker=ticker, R=R, start=str(c.index[s].date()), asof=str(c.index[e].date()),
                        base_len=int(e - s + 1), close=round(float(c.iloc[e]), 2), base_hi=round(float(hi), 2), base_lo=round(float(lo), 2),
                        range_ratio=round(float(hi/lo), 2), drift=round(float(drift), 2),
                        prior_dd=round(float(lo / pre.max() - 1), 2) if len(pre) > 20 else np.nan,
                        above_ma200=bool(c.iloc[e] > ma200.iloc[e]) if not np.isnan(ma200.iloc[e]) else None,
                        **lead_features(c, ma13, ma26, rs, plows, s, e, "now"))
    if live_only:
        return [], live

    for b in range(1, n):
        if not (L[b-1] >= LMIN and L[b] < L[b-1]):
            continue
        s = b - L[b-1]; e = b - 1
        if s <= last_break:
            continue
        ok = base_ok(s, e)
        if not ok:
            continue
        base, hi, lo, drift = ok; cb = c.iloc[b]
        if cb > hi: d = "UP"
        elif cb < lo: d = "DOWN"
        else: continue
        last_break = b
        conf = None
        if b + CONFIRM_WK < n:
            cc = c.iloc[b + CONFIRM_WK]; conf = bool(cc > hi) if d == "UP" else bool(cc < lo)
        elif delisted and d == "DOWN":
            conf = True                                   # went to zero / delisted inside the window
        pre = c.iloc[max(0, s-104):s]
        low_i = int(base.values.argmin()) + s; high_i = int(base.values.argmax()) + s
        row = dict(ticker=ticker, R=R, start=str(c.index[s].date()), end=str(c.index[e].date()),
                   break_date=str(c.index[b].date()), year=int(c.index[b].year), base_len=int(e - s + 1), dir=d, confirmed=conf,
                   delisted=bool(delisted), break_close=round(float(cb), 2), base_hi=round(float(hi), 2), base_lo=round(float(lo), 2),
                   range_ratio=round(float(hi/lo), 2), drift=round(float(drift), 2),
                   pos_in_band=round(float((c.iloc[e] - lo) / (hi - lo)), 2) if hi > lo else np.nan,
                   rsi_end=round(float(rs.iloc[e]), 1),
                   vol_contraction=round(float(ret.iloc[e-12:e+1].std() / ret.iloc[s:s+13].std()), 2) if e - s >= 26 and ret.iloc[s:s+13].std() > 0 else np.nan,
                   prior_dd=round(float(lo / pre.max() - 1), 2) if len(pre) > 20 else np.nan,
                   above_ma200=bool(c.iloc[e] > ma200.iloc[e]) if not np.isnan(ma200.iloc[e]) else None,
                   phaseB_weeks=int(b - low_i) if d == "UP" else int(b - high_i),
                   break_bar_pct=round(float(cb / c.iloc[e] - 1) * 100, 1))
        for LEAD in (8, 13):
            t = e - LEAD
            if t - s >= 13:
                row.update(lead_features(c, ma13, ma26, rs, plows, s, t, f"L{LEAD}"))
        for f in FWD:
            if b + f < n:
                r = c.iloc[b + f] / cb - 1; row[f"ret{f}"] = round(float(r) * 100, 1); row[f"trunc{f}"] = False
            elif delisted and n - 1 > b:
                r = c.iloc[-1] / cb - 1; row[f"ret{f}"] = round(float(r) * 100, 1); row[f"trunc{f}"] = True
            else:
                row[f"ret{f}"] = np.nan; row[f"trunc{f}"] = None; continue
            end_i = min(b + f, n - 1)
            for bn, bs in benches.items():
                if c.index[b] in bs.index and c.index[end_i] in bs.index:
                    row[f"exc{f}_{bn}"] = round(float(r - (bs.loc[c.index[end_i]] / bs.loc[c.index[b]] - 1)) * 100, 1)
            seg = c.iloc[b:end_i+1]
            row[f"mae{f}"] = round(float(seg.min() / cb - 1) * 100, 1) if d == "UP" else round(float(seg.max() / cb - 1) * 100, 1)
        events.append(row)
    return events, live

# ------------------------------------------------------------ summary
def q(s): return {k: (None if pd.isna(v) else round(float(v), 1)) for k, v in s.quantile([.25, .5, .75]).items()} if len(s) else {}
def share(g, col):
    return {str(k): dict(up_share=round(float(h["up"].mean()), 2), n=int(len(h)), ret26_med=(None if h["ret26"].isna().all() else round(float(h["ret26"].median()), 1)))
            for k, h in g.groupby(col, observed=True, dropna=False)}

def summarize(df, bench_name):
    out = {}
    for R, g0 in df.groupby("R"):
        g = g0[g0.confirmed == True].copy(); g["up"] = (g["dir"] == "UP").astype(int)
        exc = f"exc26_{bench_name}"
        sec = dict(events=int(len(g0)), confirmed=int(len(g)), fakeout_rate={d: round(float((h.confirmed == False).mean()), 2) for d, h in g0[g0.confirmed.notna()].groupby("dir")},
                   by_dir={})
        for d, h in g.groupby("dir"):
            sec["by_dir"][d] = dict(n=int(len(h)), base_len_q=q(h.base_len), phaseB_weeks_q=q(h.phaseB_weeks),
                                   ret13_med=round(float(h.ret13.median()), 1), ret26_med=round(float(h.ret26.median()), 1),
                                   exc26_med=(round(float(h[exc].median()), 1) if exc in h else None),
                                   win26=round(float((h.ret26 > 0).mean()), 2), mae26_med=round(float(h.mae26.median()), 1),
                                   truncated=int(h.get("trunc26", pd.Series(dtype=bool)).fillna(False).sum()))
        sec["base_rate_up"] = round(float(g.up.mean()), 2) if len(g) else None
        for LEAD in ("L8", "L13"):
            if f"pos_{LEAD}" not in g: continue
            h = g.dropna(subset=[f"pos_{LEAD}"]).copy()
            h["posbin"] = pd.cut(h[f"pos_{LEAD}"], [-.01, .33, .66, 1.01], labels=["low", "mid", "top"])
            h["rsibin"] = pd.cut(h[f"rsi_{LEAD}"], [0, 45, 55, 100], labels=["<45", "45-55", ">55"])
            comp = h[(h[f"pos_{LEAD}"] > 0.5) & (h[f"ma_{LEAD}"] == True)]
            anti = h[(h[f"pos_{LEAD}"] < 0.5) & (h[f"ma_{LEAD}"] == False)]
            sec[f"lead_{LEAD}"] = dict(n=int(len(h)), pos_bin=share(h, "posbin"), rsi_bin=share(h, "rsibin"), ma13_gt_ma26=share(h, f"ma_{LEAD}"),
                                       composite_upperhalf_and_ma=dict(n=int(len(comp)), up_share=round(float(comp.up.mean()), 2) if len(comp) else None,
                                                                       ret26_med=round(float(comp.ret26.median()), 1) if len(comp) else None),
                                       anti_lowerhalf_and_no_ma=dict(n=int(len(anti)), up_share=round(float(anti.up.mean()), 2) if len(anti) else None))
        g["dd_bucket"] = pd.cut(g.prior_dd, [-1.01, -0.5, -0.3, 0.5], labels=["deep<=-50%", "-30..-50%", "shallow>-30%"])
        sec["by_prior_dd"] = share(g, "dd_bucket"); sec["by_year"] = share(g, "year")
        sec["by_delisted"] = share(g, "delisted")
        out[f"R{R}"] = sec
    return out

# ------------------------------------------------------------ main
def load(path):
    if path.endswith(".parquet"):
        px = pd.read_parquet(path)
    else:
        px = pd.read_csv(path)
        if "adj_close" not in px: px["adj_close"] = px["close"]
    return px

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--prices", required=True); ap.add_argument("--universe", default=None)
    ap.add_argument("--out", default="."); ap.add_argument("--max", type=int, default=0)
    a = ap.parse_args()
    px = load(a.prices)
    delisted = {}
    if a.universe:
        u = pd.read_csv(a.universe); delisted = dict(zip(u.ticker, u.delisted.astype(bool)))
    W = {}
    for t, g in px.groupby("ticker"):
        W[t] = weekly(g)
    benches = {b: W[b]["close"] for b in BENCH if b in W}
    bench_name = "SPY" if "SPY" in benches else (next(iter(benches)) if benches else None)
    print(f"tickers: {len(W)}  benches: {list(benches)}", flush=True)
    ev, live = [], []
    tickers = [t for t in W if t not in BENCH]
    if a.max: tickers = tickers[: a.max]
    for i, t in enumerate(tickers):
        for R in R_LIST:
            e_, l_ = detect(t, W[t], benches, R, delisted.get(t, False))
            ev += e_
            if l_: live.append(l_)
        if (i + 1) % 500 == 0: print(f"  {i+1}/{len(tickers)} tickers, {len(ev)} events", flush=True)
    df = pd.DataFrame(ev); lv = pd.DataFrame(live)
    df.to_csv(f"{a.out}/base_events.csv", index=False); lv.to_csv(f"{a.out}/base_live.csv", index=False)
    summ = summarize(df, bench_name) if len(df) else {}
    summ["_meta"] = dict(tickers=len(tickers), events=int(len(df)), live_bases=int(len(lv)), prices=a.prices, params=dict(R=R_LIST, LMIN=LMIN, CONFIRM_WK=CONFIRM_WK, FLAT=FLAT, MIN_PRICE=MIN_PRICE, MIN_WK_DOLLAR_VOL=MIN_WK_DOLLAR_VOL))
    json.dump(summ, open(f"{a.out}/base_summary.json", "w"), indent=1, default=str)
    print(json.dumps(summ, indent=1, default=str))

if __name__ == "__main__":
    main()
