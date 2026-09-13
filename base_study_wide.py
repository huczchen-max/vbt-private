"""Long-base pattern study — wide universe (v0.6, 2026-09-12).

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
SIGNAL pass (v0.3, Eric 2026-09-11): the tradeable version. For every
  ticker-week where a base >= LMIN (and <= LMAX) is open, COMPOSITE =
  pos-in-band > 0.66 & RSI14 > 55 & MA13 > MA26 (all causal). A SIGNAL fires
  the FIRST week composite turns true (one per base). Forward 13/26-week
  returns are measured from the signal close regardless of what the base does
  next; SPY excess, MAE, and which break (if any) followed within 26 weeks are
  recorded. ANTI = mirror (pos < 0.33 & RSI < 45 & MA13 < MA26) as control.
  REGIME = SPY above its 40-week MA at the signal date.
TIGHTNESS (v0.4, Eric 2026-09-11): dispersion of weekly closes around the
  base median — mad_med = median|x-med|/med, cv = std/mean, mid_share = share
  of closes inside the middle half of the band. Computed causally (over the
  base up to the event/signal bar) and binned in the summary; pre_vol = the
  name's own weekly-return std in the 52 wks before the base (control).
SPRING (v0.4): base preceded (within 30 wks of its start) by a DOWN break
  that did not hold — the MSTR case; flagged, not yet acted on.
CONTRACTION + RISK (v0.6, Eric 2026-09-12, "dive deeper into tight bases"):
  A. mad_tail8/13 = MAD/median of the LAST 8/13 weekly closes; contr8 =
     mad_tail8 / mad_med (<1 = range contracting into the bar); vol_dry8 =
     median weekly $vol of the last 8 wks / median over the base (<1 = drying
     up). rel_tight = mad_med / pre_vol (tight relative to the name's own vol).
     zero_wk_share = share of base weeks with |return| < 0.1% (flat-line guard;
     rows > 0.3 are excluded from summaries).
  B. 52-week horizon (ret52/exc52/mae52) and risk-adjusted views per bin:
     ret/|MAE| (ex post) and ret26 / expected 26-wk vol from pre_vol (ex ante).
Outputs (in --out dir): base_events.csv, base_signals.csv, base_live.csv
  (bases open NOW, listed names only, current as-of), base_summary.json.
"""
import argparse, json, sys
import numpy as np, pandas as pd

R_LIST = [1.5, 2.0]; LMIN = 26; LMAX = 156; CONFIRM_WK = 4; FWD = [13, 26, 52]; FLAT = 0.4
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

def tightness(seg):
    """seg: numpy array of weekly closes inside the base."""
    med = np.median(seg); hi, lo = seg.max(), seg.min()
    if med <= 0 or hi <= lo:
        return dict(mad_med=np.nan, cv=np.nan, mid_share=np.nan)
    return dict(mad_med=round(float(np.median(np.abs(seg - med)) / med), 4),
                cv=round(float(seg.std() / seg.mean()), 4),
                mid_share=round(float(np.mean((seg >= lo + 0.25 * (hi - lo)) & (seg <= lo + 0.75 * (hi - lo)))), 3))

def extra_feats(cseg, dseg, retseg, mad_med, pv):
    """v0.6 causal features over a base segment (numpy arrays: closes, $vol, returns)."""
    def mad(x):
        m = np.median(x); return float(np.median(np.abs(x - m)) / m) if m > 0 else np.nan
    f = {}
    f["mad_tail8"] = round(mad(cseg[-8:]), 4) if len(cseg) >= 8 else np.nan
    f["mad_tail13"] = round(mad(cseg[-13:]), 4) if len(cseg) >= 13 else np.nan
    f["contr8"] = round(f["mad_tail8"] / mad_med, 2) if mad_med and mad_med > 0 and not np.isnan(f["mad_tail8"]) else np.nan
    dmed = np.median(dseg) if len(dseg) else 0
    f["vol_dry8"] = round(float(np.median(dseg[-8:]) / dmed), 2) if len(dseg) >= 8 and dmed > 0 else np.nan
    f["rel_tight"] = round(mad_med / pv, 2) if pv and pv > 0 and mad_med is not None and not np.isnan(mad_med) else np.nan
    r = retseg[~np.isnan(retseg)]
    f["zero_wk_share"] = round(float(np.mean(np.abs(r) < 0.001)), 2) if len(r) else np.nan
    return f

def pre_vol(ret, s):
    r = ret[max(0, s - 52):s]
    return round(float(np.nanstd(r)), 4) if len(r) >= 20 else np.nan

def spring_flag(down_breaks, s):
    return bool(any(s - 30 <= bi <= s + 4 for bi in down_breaks))

# ------------------------------------------------------------ detector
def detect(ticker, w, benches, R, delisted=False, live_only=False):
    c = w["close"]; n = len(c); v = c.values.astype(float)
    if n < LMIN + 5 or np.nanmin(v) <= 0:
        return [], None
    L = longest_window_len(v, R)
    ma13 = c.rolling(13).mean(); ma26 = c.rolling(26).mean(); ma200 = c.rolling(200, min_periods=100).mean()
    rs = rsi(c); ret = c.pct_change(); plows = sorted(pivot_lows(c)); retv = ret.values
    events = []; last_break = -1; down_breaks = []

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
    if LMIN <= L[e] <= LMAX and not delisted:
        s = e - L[e] + 1; ok = base_ok(s, e)
        if ok:
            base, hi, lo, drift = ok
            pre = c.iloc[max(0, s-104):s]
            live = dict(ticker=ticker, R=R, start=str(c.index[s].date()), asof=str(c.index[e].date()),
                        base_len=int(e - s + 1), close=round(float(c.iloc[e]), 2), base_hi=round(float(hi), 2), base_lo=round(float(lo), 2),
                        range_ratio=round(float(hi/lo), 2), drift=round(float(drift), 2),
                        prior_dd=round(float(lo / pre.max() - 1), 2) if len(pre) > 20 else np.nan,
                        above_ma200=bool(c.iloc[e] > ma200.iloc[e]) if not np.isnan(ma200.iloc[e]) else None,
                        **tightness(base.values.astype(float)), pre_vol=pre_vol(retv, s),
                        **lead_features(c, ma13, ma26, rs, plows, s, e, "now"))
            live.update(extra_feats(base.values.astype(float), w["dvol"].values[s:e+1], retv[s:e+1], live["mad_med"], live["pre_vol"]))
    if live_only:
        return [], live

    for b in range(1, n):
        if not (LMIN <= L[b-1] <= LMAX and L[b] < L[b-1]):   # v0.6: events now respect LMAX too (signals/live already did)
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
        spring = spring_flag(down_breaks, s)
        if d == "DOWN":
            down_breaks.append(b)
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
                   break_bar_pct=round(float(cb / c.iloc[e] - 1) * 100, 1),
                   **tightness(base.values.astype(float)), pre_vol=pre_vol(retv, s), spring=spring, b_idx=int(b))
        row.update(extra_feats(base.values.astype(float), w["dvol"].values[s:e+1], retv[s:e+1], row["mad_med"], row["pre_vol"]))
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
    if live is not None:
        s_live = e - L[e] + 1
        live["spring"] = spring_flag(down_breaks, s_live)
    return events, live


# ------------------------------------------------------------ signal pass (v0.3)
def composite_at(v, m13, m26, r, s, t):
    """v, m13, m26, r are numpy arrays (close, MA13, MA26, RSI)."""
    seg = v[s:t+1]; bhi, blo = seg.max(), seg.min()
    if bhi <= blo or np.isnan(m26[t]) or np.isnan(r[t]):
        return None, np.nan
    pos = (v[t] - blo) / (bhi - blo)
    comp = bool(pos > 0.66 and r[t] > 55 and m13[t] > m26[t])
    anti = bool(pos < 0.33 and r[t] < 45 and m13[t] < m26[t])
    return ("COMP" if comp else "ANTI" if anti else None), pos

def signals(ticker, w, benches, spy_regime, R, delisted=False, down_breaks=()):
    """First-week composite/anti triggers inside open bases; forward returns from the trigger close."""
    c = w["close"]; n = len(c); v = c.values.astype(float)
    if n < LMIN + 5 or np.nanmin(v) <= 0:
        return []
    L = longest_window_len(v, R)
    ma13 = c.rolling(13).mean(); ma26 = c.rolling(26).mean(); rs = rsi(c); retv = c.pct_change().values
    m13, m26, r_ = ma13.values, ma26.values, rs.values
    out = []; prev_kind = None; prev_start = -1; last_fire = {}
    for t in range(LMIN, n):
        if not (LMIN <= L[t] <= LMAX):
            prev_kind = None; continue
        s = t - L[t] + 1
        kind, pos = composite_at(v, m13, m26, r_, s, t)
        fire = kind is not None and not (kind == prev_kind and s == prev_start)
        # one signal of each kind per base (base identified by its start bar)
        if fire and last_fire.get((kind, s)) is not None:
            fire = False
        prev_kind, prev_start = kind, s
        if not fire:
            continue
        last_fire[(kind, s)] = t
        base = c.iloc[s:t+1]
        if base.median() < MIN_PRICE or w["dvol"].iloc[s:t+1].median() < MIN_WK_DOLLAR_VOL:
            continue
        hi, lo = base.max(), base.min()
        x = np.arange(len(base)); k, _ = np.polyfit(x, base.values, 1)
        drift = k * (len(base) - 1) / (hi - lo)
        if abs(drift) > FLAT:
            continue
        ct = c.iloc[t]
        row = dict(ticker=ticker, R=R, kind=kind, date=str(c.index[t].date()), year=int(c.index[t].year),
                   base_start=str(c.index[s].date()), base_len=int(t - s + 1), close=round(float(ct), 2),
                   pos=round(float(pos), 2), rsi=round(float(rs.iloc[t]), 1), range_ratio=round(float(hi / lo), 2),
                   wk_since_low=int(t - (int(base.values.argmin()) + s)), delisted=bool(delisted),
                   **tightness(base.values.astype(float)), pre_vol=pre_vol(retv, s), spring=spring_flag(down_breaks, s),
                   regime_spy_up=(bool(spy_regime.loc[c.index[t]]) if spy_regime is not None and c.index[t] in spy_regime.index else None))
        row.update(extra_feats(base.values.astype(float), w["dvol"].values[s:t+1], retv[s:t+1], row["mad_med"], row["pre_vol"]))
        # what happened next within 26 weeks: first close beyond the band as of t
        nxt = "NONE"; wk_to_break = None
        for j in range(t + 1, min(n, t + 27)):
            if c.iloc[j] > hi: nxt, wk_to_break = "UP", j - t; break
            if c.iloc[j] < lo: nxt, wk_to_break = "DOWN", j - t; break
        row["next_break"] = nxt; row["wk_to_break"] = wk_to_break
        for f in FWD:
            if t + f < n:
                r = c.iloc[t + f] / ct - 1; row[f"ret{f}"] = round(float(r) * 100, 1); row[f"trunc{f}"] = False
            elif delisted and n - 1 > t:
                r = c.iloc[-1] / ct - 1; row[f"ret{f}"] = round(float(r) * 100, 1); row[f"trunc{f}"] = True
            else:
                row[f"ret{f}"] = np.nan; row[f"trunc{f}"] = None; continue
            end_i = min(t + f, n - 1)
            for bn, bs in benches.items():
                if c.index[t] in bs.index and c.index[end_i] in bs.index:
                    row[f"exc{f}_{bn}"] = round(float(r - (bs.loc[c.index[end_i]] / bs.loc[c.index[t]] - 1)) * 100, 1)
            seg = c.iloc[t:end_i+1]
            row[f"mae{f}"] = round(float(seg.min() / ct - 1) * 100, 1)
        out.append(row)
    return out

TIGHT_BINS = [-0.001, 0.04, 0.07, 0.10, 0.15, 9]; TIGHT_LABELS = ["<4%", "4-7%", "7-10%", "10-15%", ">15%"]
CONTR_BINS = [-0.001, 0.5, 0.8, 1.2, 99]; CONTR_LABELS = ["<0.5 tight-tail", "0.5-0.8", "0.8-1.2 flat", ">1.2 widening"]
DRY_BINS = [-0.001, 0.6, 0.9, 1.2, 99]; DRY_LABELS = ["<0.6 dry", "0.6-0.9", "0.9-1.2", ">1.2 rising"]
FLATLINE_MAX = 0.30   # zero_wk_share above this = flat-lined / stale quotes

def risk_block(h, exc):
    """v0.6 risk-adjusted view of a signal cohort (h has ret26, mae26, pre_vol, optionally ret52/exc52/mae52)."""
    if not len(h): return dict(n=0)
    mae = h.mae26.abs().clip(lower=1.0)
    o = dict(n=int(len(h)), ret26_med=round(float(h.ret26.median()), 1), exc26_med=(round(float(h[exc].median()), 1) if exc in h else None),
             win26=round(float((h.ret26 > 0).mean()), 2), mae26_med=round(float(h.mae26.median()), 1),
             ret_over_mae_med=round(float((h.ret26 / mae).median()), 2),
             ret_over_mae_mean=round(float(h.ret26.mean() / mae.mean()), 2),
             p10_ret26=round(float(h.ret26.quantile(.1)), 1), p90_ret26=round(float(h.ret26.quantile(.9)), 1))
    ev = h.pre_vol * np.sqrt(26) * 100          # expected 26-wk move (%) from the name's own pre-base weekly vol
    ok = ev.notna() & (ev > 0)
    if ok.sum() >= 30:
        o["ret26_per_expvol_med"] = round(float((h.ret26[ok] / ev[ok]).median()), 2)
        o["exp_vol26_med"] = round(float(ev[ok].median()), 1)
        # constant-risk sizing: scale each trade so expected 26-wk vol = 20% (weight = 20/ev, capped 2x)
        wgt = (20.0 / ev[ok]).clip(upper=2.0); o["ret26_riskparity_mean"] = round(float((h.ret26[ok] * wgt).mean()), 1)
        if exc in h: o["exc26_riskparity_mean"] = round(float((h[exc][ok] * wgt).mean()), 1)
    if "ret52" in h and h.ret52.notna().sum() >= 30:
        h52 = h.dropna(subset=["ret52"]); e52 = exc.replace("26", "52")
        o["n52"] = int(len(h52)); o["ret52_med"] = round(float(h52.ret52.median()), 1); o["win52"] = round(float((h52.ret52 > 0).mean()), 2)
        o["exc52_med"] = (round(float(h52[e52].median()), 1) if e52 in h52 else None); o["mae52_med"] = round(float(h52.mae52.median()), 1)
    return o

def summarize_signals(df, bench_name):
    out = {}
    exc = f"exc26_{bench_name}"
    def block(h):
        if not len(h): return dict(n=0)
        return dict(n=int(len(h)), ret13_med=round(float(h.ret13.median()), 1), ret26_med=round(float(h.ret26.median()), 1),
                    exc26_med=(round(float(h[exc].median()), 1) if exc in h else None), win26=round(float((h.ret26 > 0).mean()), 2),
                    mae26_med=round(float(h.mae26.median()), 1), ret26_mean=round(float(h.ret26.mean()), 1),
                    next_break={k: round(float(v), 2) for k, v in h.next_break.value_counts(normalize=True).items()},
                    wk_to_break_med=(None if h.wk_to_break.isna().all() else round(float(h.wk_to_break.median()), 1)))
    for R, g0 in df.groupby("R"):
        sec = {}
        for kind, g in g0.groupby("kind"):
            g = g.dropna(subset=["ret26"])
            g = g.copy(); g["tight_bin"] = pd.cut(g.mad_med, TIGHT_BINS, labels=TIGHT_LABELS)
            g["vol_tercile"] = pd.qcut(g.pre_vol.rank(method="first"), 3, labels=["lowvol", "midvol", "highvol"]) if g.pre_vol.notna().sum() > 30 else None
            n_flat = int((g.get("zero_wk_share", pd.Series(dtype=float)) > FLATLINE_MAX).sum()) if "zero_wk_share" in g else 0
            if "zero_wk_share" in g: g = g[~(g.zero_wk_share > FLATLINE_MAX)]
            v6 = {}
            if "contr8" in g:
                g["contr_bin"] = pd.cut(g.contr8, CONTR_BINS, labels=CONTR_LABELS); g["dry_bin"] = pd.cut(g.vol_dry8, DRY_BINS, labels=DRY_LABELS)
                g["rel_terc"] = pd.qcut(g.rel_tight.rank(method="first"), 3, labels=["rel-tight", "rel-mid", "rel-loose"]) if g.rel_tight.notna().sum() > 30 else None
                v6 = dict(flatline_excluded=n_flat, contr8_q=q(g.contr8, 2), vol_dry8_q=q(g.vol_dry8, 2), rel_tight_q=q(g.rel_tight, 2),
                          by_contraction={str(k): risk_block(h, exc) for k, h in g.groupby("contr_bin", observed=True) if len(h) >= 30},
                          by_vol_dry={str(k): risk_block(h, exc) for k, h in g.groupby("dry_bin", observed=True) if len(h) >= 30},
                          by_rel_tight={str(k): risk_block(h, exc) for k, h in g.groupby("rel_terc", observed=True) if len(h) >= 30} if g["rel_terc"] is not None else {},
                          by_tightness_risk={str(k): risk_block(h, exc) for k, h in g.groupby("tight_bin", observed=True) if len(h) >= 30},
                          by_tightness_x_contraction={f"{k[0]}|{k[1]}": risk_block(h, exc) for k, h in g.groupby(["tight_bin", "contr_bin"], observed=True) if len(h) >= 30},
                          by_contraction_x_vol={f"{k[0]}|{k[1]}": risk_block(h, exc) for k, h in g.groupby(["contr_bin", "vol_tercile"], observed=True) if len(h) >= 30} if g["vol_tercile"] is not None else {},
                          by_contraction_x_dry={f"{k[0]}|{k[1]}": risk_block(h, exc) for k, h in g.groupby(["contr_bin", "dry_bin"], observed=True) if len(h) >= 30},
                          vcp=risk_block(g[(g.contr8 < 0.8) & (g.vol_dry8 < 0.9)], exc),
                          vcp_listed_lowvol=risk_block(g[(g.contr8 < 0.8) & (g.vol_dry8 < 0.9) & (g.delisted == False) & (g.vol_tercile == "lowvol")], exc) if g["vol_tercile"] is not None else {},
                          vcp_x_tightness={str(k): risk_block(h, exc) for k, h in g[(g.contr8 < 0.8) & (g.vol_dry8 < 0.9)].groupby("tight_bin", observed=True) if len(h) >= 30})
            sec[kind] = dict(all=block(g), listed_only=block(g[g.delisted == False]), v06=v6,
                             spy_up=block(g[g.regime_spy_up == True]), spy_down=block(g[g.regime_spy_up == False]),
                             spring=block(g[g.spring == True]), no_spring=block(g[g.spring == False]),
                             by_tightness={str(k): block(h) for k, h in g.groupby("tight_bin", observed=True)},
                             by_tightness_x_vol={f"{k[0]}|{k[1]}": dict(n=int(len(h)), ret26_med=round(float(h.ret26.median()), 1), exc26_med=(round(float(h[exc].median()), 1) if exc in h else None))
                                                 for k, h in g.groupby(["tight_bin", "vol_tercile"], observed=True)} if g["vol_tercile"] is not None else {},
                             mad_med_q=q(g.mad_med, 3),
                             by_year={str(y): dict(n=int(len(h)), ret26_med=round(float(h.ret26.median()), 1), exc26_med=(round(float(h[exc].median()), 1) if exc in h else None)) for y, h in g.groupby("year")})
        out[f"R{R}"] = sec
    return out

# ------------------------------------------------------------ summary
def q(s, nd=1): return {k: (None if pd.isna(v) else round(float(v), nd)) for k, v in s.quantile([.25, .5, .75]).items()} if len(s) else {}
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
        sec["by_delisted"] = share(g, "delisted"); sec["by_spring"] = share(g, "spring")
        g["tight_bin"] = pd.cut(g.mad_med, TIGHT_BINS, labels=TIGHT_LABELS)
        sec["mad_med_q"] = q(g.mad_med, 3)
        sec["by_tightness"] = {}
        for k, h in g.groupby("tight_bin", observed=True):
            hu = h[h.dir == "UP"]; hd = h[h.dir == "DOWN"]
            g0t = g0[pd.cut(g0.mad_med, TIGHT_BINS, labels=TIGHT_LABELS) == k]
            sec["by_tightness"][str(k)] = dict(n=int(len(h)), up_share=round(float(h.up.mean()), 2),
                fakeout_up=round(float((g0t[g0t.dir == "UP"].confirmed == False).mean()), 2) if len(g0t[g0t.dir == "UP"]) else None,
                fakeout_dn=round(float((g0t[g0t.dir == "DOWN"].confirmed == False).mean()), 2) if len(g0t[g0t.dir == "DOWN"]) else None,
                UP=dict(n=int(len(hu)), ret26_med=round(float(hu.ret26.median()), 1) if len(hu) else None, exc26_med=(round(float(hu[exc].median()), 1) if len(hu) and exc in hu else None),
                        win26=round(float((hu.ret26 > 0).mean()), 2) if len(hu) else None, break_bar_med=round(float(hu.break_bar_pct.median()), 1) if len(hu) else None,
                        ret26_p90=round(float(hu.ret26.quantile(.9)), 1) if len(hu) else None),
                DOWN=dict(n=int(len(hd)), ret26_med=round(float(hd.ret26.median()), 1) if len(hd) else None, break_bar_med=round(float(hd.break_bar_pct.median()), 1) if len(hd) else None))
        if "contr8" in g:
            g["contr_bin"] = pd.cut(g.contr8, CONTR_BINS, labels=CONTR_LABELS); g["dry_bin"] = pd.cut(g.vol_dry8, DRY_BINS, labels=DRY_LABELS)
            sec["by_contraction"] = share(g, "contr_bin"); sec["by_vol_dry"] = share(g, "dry_bin")
            sec["by_contraction_x_tightness"] = {f"{k[0]}|{k[1]}": dict(n=int(len(h)), up_share=round(float(h.up.mean()), 2)) for k, h in g.groupby(["contr_bin", "tight_bin"], observed=True) if len(h) >= 30}
            hu = g[g.dir == "UP"]
            sec["up_ret_by_contraction"] = {str(k): dict(n=int(len(h)), ret26_med=round(float(h.ret26.median()), 1), exc26_med=(round(float(h[exc].median()), 1) if exc in h else None), mae26_med=round(float(h.mae26.median()), 1)) for k, h in hu.groupby("contr_bin", observed=True) if len(h) >= 30}
        # composite-at-8wk-lead x tightness (direction tilt within tightness bins)
        if "pos_L8" in g:
            c8 = g[(g.pos_L8 > 0.66) & (g.rsi_L8 > 55) & (g.ma_L8 == True)]
            sec["composite_L8_by_tightness"] = share(c8, "tight_bin")
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
    spy_regime = None
    if "SPY" in W:
        spy = W["SPY"]["close"]; spy_regime = (spy > spy.rolling(40).mean())
    asof_all = max(w.index[-1] for w in W.values())
    print(f"tickers: {len(W)}  benches: {list(benches)}", flush=True)
    ev, live, sig = [], [], []
    tickers = [t for t in W if t not in BENCH]
    if a.max: tickers = tickers[: a.max]
    for i, t in enumerate(tickers):
        for R in R_LIST:
            dl = delisted.get(t, False) or ("_" in t)
            e_, l_ = detect(t, W[t], benches, R, dl)
            ev += e_
            if l_ and W[t].index[-1] == asof_all: live.append(l_)
            dbs = [r["b_idx"] for r in e_ if r["dir"] == "DOWN"]
            sig += signals(t, W[t], benches, spy_regime, R, dl, dbs)
        if (i + 1) % 500 == 0: print(f"  {i+1}/{len(tickers)} tickers, {len(ev)} events", flush=True)
    df = pd.DataFrame(ev); lv = pd.DataFrame(live); sg = pd.DataFrame(sig)
    df.to_csv(f"{a.out}/base_events.csv", index=False); lv.to_csv(f"{a.out}/base_live.csv", index=False); sg.to_csv(f"{a.out}/base_signals.csv", index=False)
    summ = summarize(df, bench_name) if len(df) else {}
    summ["signals"] = summarize_signals(sg, bench_name) if len(sg) else {}
    if len(lv):
        scr = lv[(lv.pos_now > 0.66) & (lv.rsi_now > 55) & (lv.ma_now == True)].copy()
        scr["tight_bin"] = pd.cut(scr.mad_med, TIGHT_BINS, labels=TIGHT_LABELS).astype(str)
        summ["live_screen"] = dict(open_bases=int(len(lv)), composite_now=int(len(scr)), tickers={str(R): sorted(scr[scr.R == R].ticker.tolist()) for R in R_LIST},
                                   by_tightness={str(R): scr[scr.R == R].groupby("tight_bin").size().to_dict() for R in R_LIST},
                                   vcp_now={str(R): sorted(scr[(scr.R == R) & (scr.contr8 < 0.8) & (scr.vol_dry8 < 0.9)].ticker.tolist()) for R in R_LIST} if "contr8" in scr else {},
                                   tight_contracting_now={str(R): sorted(scr[(scr.R == R) & (scr.mad_med < 0.07) & (scr.contr8 < 0.8)].ticker.tolist()) for R in R_LIST} if "contr8" in scr else {})
    summ["_meta"] = dict(tickers=len(tickers), events=int(len(df)), signals=int(len(sg)), live_bases=int(len(lv)), asof=str(asof_all.date()), prices=a.prices, params=dict(R=R_LIST, LMIN=LMIN, LMAX=LMAX, CONFIRM_WK=CONFIRM_WK, FLAT=FLAT, MIN_PRICE=MIN_PRICE, MIN_WK_DOLLAR_VOL=MIN_WK_DOLLAR_VOL))
    json.dump(summ, open(f"{a.out}/base_summary.json", "w"), indent=1, default=str)
    print(json.dumps(summ, indent=1, default=str))

if __name__ == "__main__":
    main()
