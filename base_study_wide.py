"""Long-base pattern study — wide universe (v0.8, 2026-09-23).

H23 (v0.8, Eric 2026-09-23): "polish the entry point" inside an open base with
  a weekly MACD crossover and an Elliott-oscillator (EO = SMA5 - SMA35) bottom —
  a two-tranche entry. All states are causal and fire once per base:
    MX   = first qualifying bullish MACD(12,26,9) cross after the base low:
           MACD < 0 at the cross and price in the lower half of the band (the
           MACD-alone baseline; crosses are tracked from the base start, the
           state can only fire once the base is >= LMIN bars)
    E1   = MX whose cross falls within E_WINDOW bars of a confirmed EO trough
           (EO minimum since the base low, followed by EO_CONFIRM rising bars)
           -> the TEST tranche (1/3 size)
    E2   = after E1, the earlier of  (a) bounce off support: a pivot low (2 bars
           each side) that held at/above the E1-time base low and within E2_TOUCH
           of it, followed by a rise of E2_BOUNCE x band from that low, or
           (b) EO crossing above zero;  E2 must arrive within E2_MAX_WK weeks in
           the same base                 -> the MAIN tranche (2/3 size)
    CTRL = one deterministic pseudo-random bar per base in its first 27 eligible
           weeks (hash of ticker+base start) = "any bar of the same base" control
  E1 rows carry: weeks/return to E2 and its kind, whether COMP or DIVUP fired
  earlier in the base, weeks/return to COMP, support_failed (close below the
  E1-time base low before E2), the test-tranche outcome under three invalidation
  variants (hold / close below the base low / -25% stop) and the capital-
  weighted blend 1/3 @E1 + 2/3 @E2 measured 26 wks after E2 (return, MAE, and
  the E1-only return at the same bar). MACD/EO depths (as % of price) are
  recorded for binning. Live bases get e1/e2 dates and MACD/EO readings.
  h23 summary block: entry_vs_comp table per R (E1 / MX / CTRL / COMP / DIVUP /
  E2, listed names) and the E1 detail (blend, stranded, invalidation, bins).

v0.7.1 (2026-09-22) and earlier:

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
RSI DIVERGENCE (v0.7, Eric 2026-09-22, the IOVA shape): price flat while RSI
  makes higher highs (bottom) — or the mirror at a top. Two new causal states,
  evaluated every week an open base exists and fired the FIRST week they turn
  true (one per base per kind, same as COMP/ANTI):
    DIVUP = pos <= 0.5 & RSI14 > 50 & last two RSI swing highs (k=4, both
            inside the base, latest within 26 wks) rising by >= DIV_MARGIN
            points while the price at those swing highs is NOT higher
            (px_h2 <= px_h1 x (1+DIV_PX_TOL))          -> early-entry candidate
    DIVDN = pos >= 0.5 & RSI14 < 50 & RSI swing highs FALLING by >= DIV_MARGIN
            while price at them is NOT lower (px_h2 >= px_h1 x (1-DIV_PX_TOL))
                                                        -> early-exit candidate
  Each DIV row also records wk_to_comp / wk_to_anti (weeks until the base's
  COMP / ANTI state fires, if ever) and ret_to_comp / ret_to_anti (price change
  to that bar) so DIVDN can be scored as a front-runner of the ANTI warning and
  DIVUP as a front-runner of the composite trigger. rsi_slope26 (RSI regression
  slope over the last 26 wks, pts/wk) and px_slope26 (price drift, %/wk) are
  recorded for every signal as a continuous version of the same idea.
  R = 3.0 added (IOVA's 2025-26 range was 2.4x, invisible at R <= 2.0).
Outputs (in --out dir): base_events.csv, base_signals.csv, base_live.csv
  (bases open NOW, listed names only, current as-of), base_summary.json.
"""
import argparse, json, sys
import numpy as np, pandas as pd

R_LIST = [1.5, 2.0, 3.0]; LMIN = 26; LMAX = 156; CONFIRM_WK = 4; FWD = [13, 26, 52]; FLAT = 0.4
MIN_PRICE = 3.0            # median close over the base
MIN_WK_DOLLAR_VOL = 5e6    # median weekly $ volume over the base (~$1M/day)
BENCH = ("SPY", "SMH", "QQQ")
DIV_K = 4; DIV_MARGIN = 3.0; DIV_PX_TOL = 0.05; DIV_RECENT = 26   # v0.7 divergence parameters
# v0.8 H23 entry parameters
MACD_F, MACD_S, MACD_SIG = 12, 26, 9; EO_F, EO_S = 5, 35
E_WINDOW = 6        # bars: the MACD cross and the EO trough must fall within this many bars of each other (and E1 fires within E_WINDOW of the cross)
E1_POS_MAX = 0.5    # the qualifying cross must happen in the lower half of the band (a bottoming, not a mid-base pullback)
EO_CONFIRM = 2      # rising EO bars needed to call the trough (causal confirmation)
E2_TOUCH = 0.10     # pullback low at/above the E1-time base low and within 10% of it = "retest of support"
E2_BOUNCE = 0.15    # bounce = close rises 15% of the band above that pullback low
E2_MAX_WK = 52      # E2 must arrive within 52 weeks of E1, same base
INV_STOP = -0.25    # test-tranche invalidation variant: the speculative stop
CTRL_SPAN = 27      # control bar: pseudo-random offset 0..26 from the first eligible week
BLEND_W1 = 1/3      # test tranche weight (main tranche = 1 - BLEND_W1)

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

def pivot_highs_arr(v, k=4):
    """Indices of local maxima of a numpy array (k bars either side); NaNs never qualify.
    v0.7.1: strictly above the k bars before it (a flat plateau counts once, at its first bar)."""
    return [i for i in range(k, len(v) - k) if not np.isnan(v[i]) and v[i] > np.nanmax(v[i-k:i]) and v[i] >= np.nanmax(v[i+1:i+k+1])]

def divergence_at(v, r, rhighs, s, t):
    """v0.7: RSI-vs-price divergence state at bar t for the base starting at s.
    Returns (kind or None, diag dict). rhighs = precomputed RSI pivot-high indices."""
    seg = v[s:t+1]; bhi, blo = seg.max(), seg.min()
    if bhi <= blo or np.isnan(r[t]):
        return None, {}
    pos = (v[t] - blo) / (bhi - blo)
    ph = [i for i in rhighs if s <= i <= t - DIV_K]        # causal: a pivot needs DIV_K bars after it
    if len(ph) < 2 or t - ph[-1] > DIV_RECENT:
        return None, {}
    h1, h2 = ph[-2], ph[-1]
    d = dict(rsi_h1=round(float(r[h1]), 1), rsi_h2=round(float(r[h2]), 1), px_h2_over_h1=round(float(v[h2] / v[h1]), 3),
             wk_h1_h2=int(h2 - h1), wk_since_h2=int(t - h2))
    if pos <= 0.5 and r[t] > 50 and r[h2] >= r[h1] + DIV_MARGIN and v[h2] <= v[h1] * (1 + DIV_PX_TOL):
        return "DIVUP", d
    if pos >= 0.5 and r[t] < 50 and r[h2] <= r[h1] - DIV_MARGIN and v[h2] >= v[h1] * (1 - DIV_PX_TOL):
        return "DIVDN", d
    return None, d

def macd(c, f=MACD_F, s=MACD_S, sig=MACD_SIG):
    """MACD line and signal (EMA, adjust=False); the first s+sig bars are NaN (warm-up)."""
    ml = c.ewm(span=f, adjust=False).mean() - c.ewm(span=s, adjust=False).mean()
    sg = ml.ewm(span=sig, adjust=False).mean()
    ml = ml.copy(); sg = sg.copy(); ml.iloc[:s + sig] = np.nan; sg.iloc[:s + sig] = np.nan
    return ml, sg

def eo(c, f=EO_F, s=EO_S):
    """Elliott oscillator: SMA(f) - SMA(s) of the close."""
    return c.rolling(f).mean() - c.rolling(s).mean()

def scan_entries(v, ml, sg, eo_, s, j0, jmax, ticker=""):
    """v0.8: causal MX / E1 / E2 bars for the base starting at s (numpy arrays). Crosses are tracked from the base start;
    states may only FIRE from j0 (first eligible week) to jmax (last week this base is open). Every condition at bar j
    uses bars <= j only. Returns a dict of bar indices (None when the state never happened) plus diagnostics."""
    o = dict(mx=None, e1=None, e1_cross=None, e1_trough=None, e2=None, e2_kind=None, e2a=None, e2b=None, e2_pivot=None,
             support_failed_wk=None, ctrl=None, pos_cross=None)
    if jmax < j0 or j0 < 1: return o
    import zlib
    o["ctrl"] = j0 + (zlib.crc32(f"{ticker}|{s}".encode()) % CTRL_SPAN)
    if o["ctrl"] > jmax: o["ctrl"] = None
    low_i = -1; cross = None; blo = bhi = None; piv = None
    for j in range(max(s + 1, 1), jmax + 1):
        if np.isnan(ml[j]) or np.isnan(sg[j]) or np.isnan(ml[j-1]) or np.isnan(sg[j-1]) or np.isnan(eo_[j]):
            continue
        if o["e1"] is None:
            li = s + int(np.argmin(v[s:j+1]))                     # base low as of j
            if li != low_i: low_i = li; cross = None               # a new low restarts "first cross after the low"
            if cross is None and j > li and ml[j] > sg[j] and ml[j-1] <= sg[j-1] and ml[j] < 0:
                bhi_j, blo_j = v[s:j+1].max(), v[s:j+1].min()
                if bhi_j > blo_j and (v[j] - blo_j) / (bhi_j - blo_j) <= E1_POS_MAX:   # a qualifying cross: MACD below zero, price in the lower half of the band
                    cross = j; o["pos_cross"] = round(float((v[j] - blo_j) / (bhi_j - blo_j)), 2)
                    if o["mx"] is None and j >= j0: o["mx"] = j
            if j < j0 or cross is None or j - cross > E_WINDOW:
                continue
            # EO trough: minimum since the base low, at least EO_CONFIRM bars old, EO rising since, within E_WINDOW of the cross
            seg = eo_[li:j+1]
            if len(seg) <= EO_CONFIRM or np.isnan(seg).any(): continue
            m = li + int(np.argmin(seg[:len(seg) - EO_CONFIRM]))
            if seg.min() < eo_[m]: continue                        # a lower EO reading arrived since -> no trough yet
            rising = all(eo_[m + k + 1] > eo_[m + k] for k in range(EO_CONFIRM))
            if rising and abs(cross - m) <= E_WINDOW:
                o.update(e1=j, e1_cross=cross, e1_trough=m); blo = float(v[s:j+1].min()); bhi = float(v[s:j+1].max())
            continue
        # ---- after E1: support failure, E2a (pivot low near support, then bounce), E2b (EO crosses above zero)
        e1 = o["e1"]
        if j - e1 > E2_MAX_WK: break
        if o["support_failed_wk"] is None and v[j] < blo: o["support_failed_wk"] = j - e1
        if o["e2b"] is None and eo_[j] > 0 and eo_[j-1] <= 0: o["e2b"] = j
        p = j - 2
        if piv is None and p > e1 and p - 2 >= s and v[p] <= v[p-2:p].min() and v[p] <= v[p+1:j+1].min() and blo <= v[p] <= blo * (1 + E2_TOUCH):
            piv = p
        if o["e2a"] is None and piv is not None and bhi > blo and (v[j] - v[piv]) / (bhi - blo) >= E2_BOUNCE:
            o["e2a"] = j; o["e2_pivot"] = piv
        if o["e2"] is None:
            cands = [x for x in (o["e2a"], o["e2b"]) if x is not None]
            if cands:
                o["e2"] = min(cands); o["e2_kind"] = "bounce" if o["e2"] == o["e2a"] else "eo_zero"
        if o["e2"] is not None and o["e2a"] is not None and o["e2b"] is not None: break
    return o

def slope26(x, t):
    """Regression slope over the last 26 bars ending at t (per bar); NaN if short."""
    seg = x[max(0, t-25):t+1]; seg = seg[~np.isnan(seg)]
    if len(seg) < 20: return np.nan
    k, _ = np.polyfit(np.arange(len(seg)), seg, 1); return float(k)

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
    rhighs = pivot_highs_arr(rs.values, DIV_K)
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
            ck, _ = composite_at(v, ma13.values, ma26.values, rs.values, s, e); dk, dd = divergence_at(v, rs.values, rhighs, s, e)
            live["state_now"] = ck or dk; live.update({f"{k}_now": val for k, val in dd.items()})
            live["rsi_slope26"] = round(slope26(rs.values, e), 2); live["px_slope26"] = round(slope26(v / v[e] * 100, e), 2)
            # v0.8: H23 entry states for the live base + MACD/EO readings
            ml, sg = macd(c); eo_ = eo(c); mlv, sgv, eov = ml.values, sg.values, eo_.values
            en = scan_entries(v, mlv, sgv, eov, s, s + LMIN - 1, e, ticker)
            dstr = lambda i: (str(c.index[i].date()) if i is not None else None)
            live.update(mx_date=dstr(en["mx"]), e1_date=dstr(en["e1"]), e1_wk_ago=(e - en["e1"]) if en["e1"] is not None else None,
                        e2_date=dstr(en["e2"]), e2_kind=en["e2_kind"], e2_wk_ago=(e - en["e2"]) if en["e2"] is not None else None,
                        support_failed_wk=en["support_failed_wk"],
                        macd_pct=round(float(mlv[e] / v[e] * 100), 2) if not np.isnan(mlv[e]) else np.nan,
                        macd_hist_pct=round(float((mlv[e] - sgv[e]) / v[e] * 100), 2) if not np.isnan(sgv[e]) else np.nan,
                        macd_bull=bool(mlv[e] > sgv[e]) if not np.isnan(sgv[e]) else None,
                        eo_pct=round(float(eov[e] / v[e] * 100), 2) if not np.isnan(eov[e]) else np.nan,
                        eo_rising=bool(eov[e] > eov[e-1]) if e > 0 and not np.isnan(eov[e-1]) else None)
            # weeks since the last bullish MACD cross (any sign), for the "watch" lists
            k = e
            while k > s and not (mlv[k] > sgv[k] and mlv[k-1] <= sgv[k-1]): k -= 1
            live["macd_cross_wk_ago"] = (e - k) if (k > s) else None
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
    """First-week COMP/ANTI/DIVUP/DIVDN triggers inside open bases (v0.3-v0.7) plus the v0.8 entry states
    MX / E1 / E2 / CTRL; forward returns from every trigger close. Several kinds may fire on the same bar."""
    c = w["close"]; n = len(c); v = c.values.astype(float)
    if n < LMIN + 5 or np.nanmin(v) <= 0:
        return []
    L = longest_window_len(v, R)
    ma13 = c.rolling(13).mean(); ma26 = c.rolling(26).mean(); rs = rsi(c); retv = c.pct_change().values
    m13, m26, r_ = ma13.values, ma26.values, rs.values
    rhighs = pivot_highs_arr(r_, DIV_K)
    ml, sg = macd(c); eo_ = eo(c); mlv, sgv, eov = ml.values, sg.values, eo_.values
    out = []; prev_kind = None; prev_start = -1; last_fire = {}; ent = {}
    dvol = w["dvol"].values

    def fwd(row, t, ct):
        """Forward returns / excess / MAE from bar t (shared by every kind)."""
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

    def bench_ret(i0, i1):
        bs = benches.get("SPY")
        if bs is None or c.index[i0] not in bs.index or c.index[i1] not in bs.index: return np.nan
        return float(bs.loc[c.index[i1]] / bs.loc[c.index[i0]] - 1)

    def to_state(t, s, want):
        """Weeks / return until the base's COMP or ANTI state fires after t (same base only, 52 wks)."""
        for j in range(t + 1, min(n, t + 53)):
            if not (LMIN <= L[j] <= LMAX) or j - L[j] + 1 != s: break
            k2, _ = composite_at(v, m13, m26, r_, s, j)
            if k2 == want: return j
        return None

    for t in range(LMIN, n):
        if not (LMIN <= L[t] <= LMAX):
            prev_kind = None; continue
        s = t - L[t] + 1
        if s not in ent:                                   # v0.8: first eligible week of this base -> scan its entry states once
            jmax = t
            while jmax + 1 < n and (jmax + 1) - L[jmax + 1] + 1 == s and L[jmax + 1] <= LMAX: jmax += 1
            ent[s] = scan_entries(v, mlv, sgv, eov, s, t, jmax, ticker)
        en = ent[s]
        kind, pos = composite_at(v, m13, m26, r_, s, t)
        diag = {}
        if kind is None:                                   # v0.7: COMP/ANTI take precedence; DIV states are mutually exclusive with them anyway
            kind, diag = divergence_at(v, r_, rhighs, s, t)
        fire = kind is not None and not (kind == prev_kind and s == prev_start)
        if fire and last_fire.get((kind, s)) is not None:  # one signal of each kind per base
            fire = False
        prev_kind, prev_start = kind, s
        if fire: last_fire[(kind, s)] = t                   # (set here, as in v0.7: a filtered bar still consumes the base's one firing of that kind)
        kinds = [(kind, diag)] if fire else []
        for ek in ("mx", "e1", "e2", "ctrl"):
            if en[ek] == t: kinds.append((ek.upper(), {}))
        if not kinds:
            continue
        base = c.iloc[s:t+1]
        if base.median() < MIN_PRICE or w["dvol"].iloc[s:t+1].median() < MIN_WK_DOLLAR_VOL:
            continue
        hi, lo = base.max(), base.min()
        if not hi > lo:
            continue
        x = np.arange(len(base)); k, _ = np.polyfit(x, base.values, 1)
        drift = k * (len(base) - 1) / (hi - lo)
        if abs(drift) > FLAT:
            continue
        ct = c.iloc[t]
        if np.isnan(pos): pos = (float(ct) - lo) / (hi - lo)
        tight = tightness(base.values.astype(float)); pv = pre_vol(retv, s)
        ef = extra_feats(base.values.astype(float), dvol[s:t+1], retv[s:t+1], tight["mad_med"], pv)
        common = dict(ticker=ticker, R=R, date=str(c.index[t].date()), year=int(c.index[t].year),
                      base_start=str(c.index[s].date()), base_len=int(t - s + 1), close=round(float(ct), 2),
                      pos=round(float(pos), 2), rsi=round(float(rs.iloc[t]), 1), range_ratio=round(float(hi / lo), 2),
                      wk_since_low=int(t - (int(base.values.argmin()) + s)), delisted=bool(delisted),
                      **tight, pre_vol=pv, spring=spring_flag(down_breaks, s),
                      regime_spy_up=(bool(spy_regime.loc[c.index[t]]) if spy_regime is not None and c.index[t] in spy_regime.index else None), **ef,
                      rsi_slope26=round(slope26(r_, t), 2), px_slope26=round(slope26(v / v[t] * 100, t), 2),
                      macd_pct=(round(float(mlv[t] / v[t] * 100), 2) if not np.isnan(mlv[t]) else np.nan),
                      eo_pct=(round(float(eov[t] / v[t] * 100), 2) if not np.isnan(eov[t]) else np.nan),
                      e1_before=bool(en["e1"] is not None and en["e1"] < t), wk_since_e1=((t - en["e1"]) if en["e1"] is not None and en["e1"] <= t else None))
        # what happened next within 26 weeks: first close beyond the band as of t
        nxt = "NONE"; wk_to_break = None
        for j in range(t + 1, min(n, t + 27)):
            if c.iloc[j] > hi: nxt, wk_to_break = "UP", j - t; break
            if c.iloc[j] < lo: nxt, wk_to_break = "DOWN", j - t; break
        common.update(next_break=nxt, wk_to_break=wk_to_break)
        for kd, dg in kinds:
            row = dict(common, kind=kd); row.update(dg)
            if kd in ("DIVUP", "DIVDN", "E1", "E2", "MX", "CTRL"):
                # does the base's COMP (bottom states) / ANTI (DIVDN) state fire later, and where is price then?
                want = "ANTI" if kd == "DIVDN" else "COMP"; hit = to_state(t, s, want); tag = "anti" if want == "ANTI" else "comp"
                row[f"wk_to_{tag}"] = (hit - t) if hit else None
                row[f"ret_to_{tag}"] = round(float(v[hit] / ct - 1) * 100, 1) if hit else np.nan
                row["comp_before"] = bool(last_fire.get(("COMP", s)) is not None and last_fire[("COMP", s)] < t)
                row["divup_before"] = bool(last_fire.get(("DIVUP", s)) is not None and last_fire[("DIVUP", s)] < t)
            if kd == "E1":
                e1, e2, m, x = t, en["e2"], en["e1_trough"], en["e1_cross"]
                blo_e1 = float(lo)
                row.update(e1_cross_wk_ago=int(t - x), e1_trough_wk_ago=int(t - m), pos_cross=en["pos_cross"],
                           macd_pct_cross=round(float(mlv[x] / v[x] * 100), 2), eo_pct_trough=round(float(eov[m] / v[m] * 100), 2),
                           wk_to_e2=((e2 - t) if e2 is not None else None), e2_kind=en["e2_kind"],
                           wk_to_e2a=((en["e2a"] - t) if en["e2a"] is not None else None), wk_to_e2b=((en["e2b"] - t) if en["e2b"] is not None else None),
                           ret_to_e2=(round(float(v[e2] / ct - 1) * 100, 1) if e2 is not None else np.nan),
                           support_failed_wk=en["support_failed_wk"], support_failed=bool(en["support_failed_wk"] is not None))
                # test-tranche outcome at 26 wks under the three invalidation variants (exit at the close that triggers; cash after)
                for name, cond in (("struct", lambda j: v[j] < blo_e1), ("stop", lambda j: v[j] / ct - 1 <= INV_STOP)):
                    val = np.nan; ex_wk = None
                    if t + 26 < n or (delisted and n - 1 > t):
                        end_i = min(t + 26, n - 1); val = v[end_i] / ct - 1
                        for j in range(t + 1, end_i + 1):
                            if cond(j): val = v[j] / ct - 1; ex_wk = j - t; break
                        val = round(float(val) * 100, 1)
                    row[f"ret26_inv_{name}"] = val; row[f"exit_wk_{name}"] = ex_wk
                # capital-weighted blend: 1/3 at E1, 2/3 at E2, measured 26 wks after E2; E1-only return at the same bar
                if e2 is not None and e2 + 26 < n:
                    h = e2 + 26; w1, w2 = BLEND_W1, 1 - BLEND_W1
                    pnl = [w1 * (v[j] / ct - 1) + (w2 * (v[j] / v[e2] - 1) if j >= e2 else 0.0) for j in range(t, h + 1)]
                    row.update(blend_h_wk=int(h - t), blend_ret=round(float(pnl[-1]) * 100, 1), blend_mae=round(float(min(pnl)) * 100, 1),
                               e1only_ret_h=round(float(v[h] / ct - 1) * 100, 1), e1only_mae_h=round(float(v[t:h+1].min() / ct - 1) * 100, 1),
                               e2_ret26=round(float(v[h] / v[e2] - 1) * 100, 1), e2_mae26=round(float(v[e2:h+1].min() / v[e2] - 1) * 100, 1),
                               blend_exc=(round(float(pnl[-1] - (w1 * bench_ret(t, h) + w2 * bench_ret(e2, h))) * 100, 1) if not np.isnan(bench_ret(t, h)) else np.nan))
                else:
                    row.update(blend_h_wk=None, blend_ret=np.nan, blend_mae=np.nan, e1only_ret_h=np.nan, e1only_mae_h=np.nan, e2_ret26=np.nan, e2_mae26=np.nan, blend_exc=np.nan)
            if kd == "E2":
                e1 = en["e1"]
                row.update(e2_kind=en["e2_kind"], ret_since_e1=round(float(ct / v[e1] - 1) * 100, 1), support_failed=bool(en["support_failed_wk"] is not None and en["support_failed_wk"] <= t - e1),
                           e2a_wk=((en["e2a"] - e1) if en["e2a"] is not None else None), e2b_wk=((en["e2b"] - e1) if en["e2b"] is not None else None))
            if kd == "MX":
                row.update(macd_pct_cross=round(float(mlv[t] / v[t] * 100), 2), became_e1=bool(en["e1"] is not None), wk_to_e1=((en["e1"] - t) if en["e1"] is not None else None))
            fwd(row, t, ct)
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
            v7 = {}
            if kind in ("DIVUP", "DIVDN") and len(g):
                tag = "comp" if kind == "DIVUP" else "anti"; wk = g[f"wk_to_{tag}"]
                v7 = dict(**{f"{tag}_follows_share": round(float(wk.notna().mean()), 2), f"wk_to_{tag}_q": q(wk.dropna()), f"ret_to_{tag}_med": (None if g[f"ret_to_{tag}"].isna().all() else round(float(g[f"ret_to_{tag}"].median()), 1))},
                          rsi_h1_q=q(g.rsi_h1), rsi_h2_q=q(g.rsi_h2), wk_h1_h2_q=q(g.wk_h1_h2),
                          by_rsi_gap={str(k): risk_block(h, exc) for k, h in g.groupby(pd.cut(g.rsi_h2 - g.rsi_h1, [-99, -10, -5, 5, 10, 99], labels=["<-10", "-10..-5", "-5..5", "5..10", ">10"]), observed=True) if len(h) >= 30},
                          by_pos={str(k): risk_block(h, exc) for k, h in g.groupby(pd.cut(g.pos, [-.01, .2, .35, .5, .65, .8, 1.01], labels=["0-.2", ".2-.35", ".35-.5", ".5-.65", ".65-.8", ".8-1"]), observed=True) if len(h) >= 30},
                          risk=risk_block(g, exc), risk_listed=risk_block(g[g.delisted == False], exc),
                          risk_listed_x_vol={str(k): risk_block(h, exc) for k, h in g[g.delisted == False].groupby("vol_tercile", observed=True) if len(h) >= 30} if g["vol_tercile"] is not None else {})
            if "rsi_slope26" in g and len(g) >= 60:
                g["rsi_slope_bin"] = pd.cut(g.rsi_slope26, [-99, -0.5, -0.1, 0.1, 0.5, 99], labels=["falling fast", "falling", "flat", "rising", "rising fast"])
                v7["by_rsi_slope26"] = {str(k): risk_block(h, exc) for k, h in g.groupby("rsi_slope_bin", observed=True) if len(h) >= 30}
            v8 = h23_block(kind, g, exc)
            sec[kind] = dict(all=block(g), listed_only=block(g[g.delisted == False]), v06=v6, v07=v7, v08=v8,
                             spy_up=block(g[g.regime_spy_up == True]), spy_down=block(g[g.regime_spy_up == False]),
                             spring=block(g[g.spring == True]), no_spring=block(g[g.spring == False]),
                             by_tightness={str(k): block(h) for k, h in g.groupby("tight_bin", observed=True)},
                             by_tightness_x_vol={f"{k[0]}|{k[1]}": dict(n=int(len(h)), ret26_med=round(float(h.ret26.median()), 1), exc26_med=(round(float(h[exc].median()), 1) if exc in h else None))
                                                 for k, h in g.groupby(["tight_bin", "vol_tercile"], observed=True)} if g["vol_tercile"] is not None else {},
                             mad_med_q=q(g.mad_med, 3),
                             by_year={str(y): dict(n=int(len(h)), ret26_med=round(float(h.ret26.median()), 1), exc26_med=(round(float(h[exc].median()), 1) if exc in h else None)) for y, h in g.groupby("year")})
        out[f"R{R}"] = sec
    return out

# ------------------------------------------------------------ H23 (v0.8) summaries
def _med(x): return None if x is None or x.isna().all() else round(float(x.median()), 1)
def _win(x): return None if x is None or x.isna().all() else round(float((x.dropna() > 0).mean()), 2)
def _share(x): return None if x is None or not len(x) else round(float(x.mean()), 2)

def blend_stats(h):
    """Capital-weighted 1/3 @E1 + 2/3 @E2 outcome vs a single full entry at E1, same horizon (26 wks after E2)."""
    b = h.dropna(subset=["blend_ret"])
    if len(b) < 20: return dict(n=int(len(b)))
    mae = b.blend_mae.abs().clip(lower=1.0); mae1 = b.e1only_mae_h.abs().clip(lower=1.0)
    return dict(n=int(len(b)), horizon_wk_med=_med(b.blend_h_wk), blend_ret_med=_med(b.blend_ret), blend_win=_win(b.blend_ret), blend_mae_med=_med(b.blend_mae),
                blend_ret_over_mae_med=round(float((b.blend_ret / mae).median()), 2), blend_exc_med=_med(b.blend_exc),
                e1only_ret_med=_med(b.e1only_ret_h), e1only_win=_win(b.e1only_ret_h), e1only_mae_med=_med(b.e1only_mae_h),
                e1only_ret_over_mae_med=round(float((b.e1only_ret_h / mae1).median()), 2),
                e2_tranche_ret26_med=_med(b.e2_ret26), e2_tranche_mae26_med=_med(b.e2_mae26), ret_e1_to_e2_med=_med(b.ret_to_e2),
                p10_blend=round(float(b.blend_ret.quantile(.1)), 1), p90_blend=round(float(b.blend_ret.quantile(.9)), 1),
                p10_e1only=round(float(b.e1only_ret_h.quantile(.1)), 1), p90_e1only=round(float(b.e1only_ret_h.quantile(.9)), 1))

def h23_block(kind, g, exc):
    """Per-kind H23 detail for summarize_signals (g = one kind, one R, flat-lines removed, ret26 present)."""
    if not len(g): return {}
    if kind == "E1":
        e2 = g[g.wk_to_e2.notna()]; st = g[g.wk_to_e2.isna()]
        o = dict(n=int(len(g)), e2_follows_share=_share(g.wk_to_e2.notna()), wk_to_e2_q=q(e2.wk_to_e2), ret_to_e2_med=_med(e2.ret_to_e2),
                 e2_kind_share={str(k): round(float(v), 2) for k, v in e2.e2_kind.value_counts(normalize=True).items()},
                 wk_to_e2a_q=q(g.wk_to_e2a.dropna()), wk_to_e2b_q=q(g.wk_to_e2b.dropna()),
                 comp_before_share=_share(g.comp_before), divup_before_share=_share(g.divup_before), comp_follows_share=_share(g.wk_to_comp.notna()),
                 wk_to_comp_q=q(g.wk_to_comp.dropna()), ret_to_comp_med=_med(g.ret_to_comp), support_failed_share=_share(g.support_failed),
                 cross_wk_ago_q=q(g.e1_cross_wk_ago), trough_wk_ago_q=q(g.e1_trough_wk_ago), wk_since_low_q=q(g.wk_since_low), pos_q=q(g.pos, 2),
                 macd_pct_cross_q=q(g.macd_pct_cross, 2), eo_pct_trough_q=q(g.eo_pct_trough, 2),
                 hold=risk_block(g, exc), hold_listed=risk_block(g[g.delisted == False], exc),
                 invalidation=dict(hold=dict(ret26_med=_med(g.ret26), win26=_win(g.ret26), mae26_med=_med(g.mae26)),
                                   struct=dict(ret26_med=_med(g.ret26_inv_struct), win26=_win(g.ret26_inv_struct), exit_share=_share(g.exit_wk_struct.notna()), exit_wk_med=_med(g.exit_wk_struct)),
                                   stop=dict(ret26_med=_med(g.ret26_inv_stop), win26=_win(g.ret26_inv_stop), exit_share=_share(g.exit_wk_stop.notna()), exit_wk_med=_med(g.exit_wk_stop))),
                 blend=blend_stats(g), blend_listed=blend_stats(g[g.delisted == False]),
                 blend_by_e2_kind={str(k): blend_stats(h) for k, h in e2.groupby("e2_kind") if len(h) >= 20},
                 stranded=dict(n=int(len(st)), ret26_med=_med(st.ret26), win26=_win(st.ret26), mae26_med=_med(st.mae26), exc26_med=_med(st[exc]) if exc in st else None,
                               next_break={str(k): round(float(v), 2) for k, v in st.next_break.value_counts(normalize=True).items()},
                               ret26_inv_struct_med=_med(st.ret26_inv_struct), ret26_inv_stop_med=_med(st.ret26_inv_stop), support_failed_share=_share(st.support_failed)),
                 with_e2=dict(n=int(len(e2)), ret26_med=_med(e2.ret26), win26=_win(e2.ret26), mae26_med=_med(e2.mae26), exc26_med=_med(e2[exc]) if exc in e2 else None,
                              next_break={str(k): round(float(v), 2) for k, v in e2.next_break.value_counts(normalize=True).items()}),
                 by_pos={str(k): risk_block(h, exc) for k, h in g.groupby(pd.cut(g.pos, [-.01, .2, .35, .5, .65, .8, 1.01], labels=["0-.2", ".2-.35", ".35-.5", ".5-.65", ".65-.8", ".8-1"]), observed=True) if len(h) >= 30},
                 by_wk_since_low={str(k): risk_block(h, exc) for k, h in g.groupby(pd.cut(g.wk_since_low, [-1, 4, 13, 26, 999], labels=["0-4", "5-13", "14-26", ">26"]), observed=True) if len(h) >= 30},
                 by_divup_before={str(k): risk_block(h, exc) for k, h in g.groupby("divup_before") if len(h) >= 30},
                 by_comp_before={str(k): risk_block(h, exc) for k, h in g.groupby("comp_before") if len(h) >= 30},
                 by_support_failed={str(k): risk_block(h, exc) for k, h in g.groupby("support_failed") if len(h) >= 30})
        for col, name in (("macd_pct_cross", "by_macd_depth"), ("eo_pct_trough", "by_eo_depth")):
            if g[col].notna().sum() >= 90:
                terc = pd.qcut(g[col].rank(method="first"), 3, labels=["deepest", "mid", "shallow"])
                o[name] = {str(k): risk_block(h, exc) for k, h in g.groupby(terc, observed=True) if len(h) >= 30}
        if g.pre_vol.notna().sum() > 30:
            vt = pd.qcut(g.pre_vol.rank(method="first"), 3, labels=["lowvol", "midvol", "highvol"])
            o["by_vol"] = {str(k): risk_block(h, exc) for k, h in g.groupby(vt, observed=True) if len(h) >= 30}
            o["blend_lowvol_listed"] = blend_stats(g[(vt == "lowvol") & (g.delisted == False)])
        return o
    if kind == "E2":
        return dict(n=int(len(g)), by_e2_kind={str(k): risk_block(h, exc) for k, h in g.groupby("e2_kind") if len(h) >= 30}, ret_since_e1_q=q(g.ret_since_e1),
                    by_support_failed={str(k): risk_block(h, exc) for k, h in g.groupby("support_failed") if len(h) >= 30},
                    comp_before_share=_share(g.comp_before), comp_follows_share=_share(g.wk_to_comp.notna()), wk_to_comp_q=q(g.wk_to_comp.dropna()))
    if kind == "MX":
        return dict(n=int(len(g)), became_e1_share=_share(g.became_e1), wk_to_e1_q=q(g.wk_to_e1.dropna()), macd_pct_cross_q=q(g.macd_pct_cross, 2),
                    by_became_e1={str(k): risk_block(h, exc) for k, h in g.groupby("became_e1") if len(h) >= 30})
    if kind in ("COMP", "DIVUP", "CTRL", "ANTI", "DIVDN"):
        o = dict(n=int(len(g)))
        if "e1_before" in g and g.e1_before.notna().any():
            o["by_e1_before"] = {str(k): risk_block(h, exc) for k, h in g.groupby("e1_before") if len(h) >= 30}
        return o
    return {}

def h23_table(sg, bench_name):
    """Headline table: every entry kind side by side, listed names, flat-lines removed, per R; plus the same-base E1-vs-COMP pairing."""
    exc = f"exc26_{bench_name}"; out = {}
    for R, g0 in sg.groupby("R"):
        g0 = g0[g0.delisted == False]
        if "zero_wk_share" in g0: g0 = g0[~(g0.zero_wk_share > FLATLINE_MAX)]
        tab = {}
        for kd in ("E1", "MX", "CTRL", "COMP", "DIVUP", "E2", "ANTI"):
            h = g0[g0.kind == kd].dropna(subset=["ret26"])
            if len(h) < 30: continue
            b = risk_block(h, exc)
            b.update(next_up=round(float((h.next_break == "UP").mean()), 2), next_down=round(float((h.next_break == "DOWN").mean()), 2),
                     wk_to_break_med=_med(h.wk_to_break), pos_med=(None if h.pos.isna().all() else round(float(h.pos.median()), 2)), wk_since_low_med=_med(h.wk_since_low),
                     neg_years=int(sum(1 for y, hy in h.groupby("year") if len(hy) >= 20 and exc in hy and hy[exc].median() < 0)),
                     years=int(sum(1 for y, hy in h.groupby("year") if len(hy) >= 20)))
            tab[kd] = b
        e1 = g0[g0.kind == "E1"]; cp = g0[g0.kind == "COMP"]
        m = e1.merge(cp, on=["ticker", "base_start"], suffixes=("_e1", "_comp"))
        if len(m) >= 30:
            m = m.dropna(subset=["ret26_e1", "ret26_comp"])
            tab["paired_E1_vs_COMP"] = dict(n=int(len(m)), e1_first_share=_share(m.date_e1 < m.date_comp), e1_ret26_med=_med(m.ret26_e1), comp_ret26_med=_med(m.ret26_comp),
                                           e1_mae26_med=_med(m.mae26_e1), comp_mae26_med=_med(m.mae26_comp), e1_win=_win(m.ret26_e1), comp_win=_win(m.ret26_comp),
                                           e1_minus_comp_ret26_med=_med(m.ret26_e1 - m.ret26_comp), price_e1_to_comp_med=_med(m.ret_to_comp_e1))
        out[f"R{R}"] = tab
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
    summ["h23"] = h23_table(sg, bench_name) if len(sg) and "kind" in sg and (sg.kind == "E1").any() else {}
    if len(lv):
        scr = lv[(lv.pos_now > 0.66) & (lv.rsi_now > 55) & (lv.ma_now == True)].copy()
        scr["tight_bin"] = pd.cut(scr.mad_med, TIGHT_BINS, labels=TIGHT_LABELS).astype(str)
        summ["live_screen"] = dict(open_bases=int(len(lv)), composite_now=int(len(scr)), tickers={str(R): sorted(scr[scr.R == R].ticker.tolist()) for R in R_LIST},
                                   by_tightness={str(R): scr[scr.R == R].groupby("tight_bin").size().to_dict() for R in R_LIST},
                                   vcp_now={str(R): sorted(scr[(scr.R == R) & (scr.contr8 < 0.8) & (scr.vol_dry8 < 0.9)].ticker.tolist()) for R in R_LIST} if "contr8" in scr else {},
                                   tight_contracting_now={str(R): sorted(scr[(scr.R == R) & (scr.mad_med < 0.07) & (scr.contr8 < 0.8)].ticker.tolist()) for R in R_LIST} if "contr8" in scr else {},
                                   divup_now={str(R): sorted(lv[(lv.R == R) & (lv.state_now == "DIVUP")].ticker.tolist()) for R in R_LIST} if "state_now" in lv else {},
                                   divdn_now={str(R): sorted(lv[(lv.R == R) & (lv.state_now == "DIVDN")].ticker.tolist()) for R in R_LIST} if "state_now" in lv else {},
                                   rsi_rising_low_in_band={str(R): sorted(lv[(lv.R == R) & (lv.pos_now <= 0.5) & (lv.rsi_slope26 > 0.5) & (lv.rsi_now > 50)].ticker.tolist()) for R in R_LIST} if "rsi_slope26" in lv else {})
        if "e1_date" in lv:   # v0.8 H23 live lists
            e1w = pd.to_numeric(lv.e1_wk_ago, errors="coerce"); e2w = pd.to_numeric(lv.e2_wk_ago, errors="coerce"); mcw = pd.to_numeric(lv.macd_cross_wk_ago, errors="coerce")
            summ["live_screen"].update(
                e1_recent={str(R): sorted(lv[(lv.R == R) & (e1w <= 4) & lv.e2_date.isna()].ticker.tolist()) for R in R_LIST},
                e1_open={str(R): sorted(lv[(lv.R == R) & e1w.notna() & (e1w <= 52) & lv.e2_date.isna() & (lv.support_failed_wk.isna())].ticker.tolist()) for R in R_LIST},
                e2_recent={str(R): sorted(lv[(lv.R == R) & (e2w <= 4)].ticker.tolist()) for R in R_LIST},
                macd_cross_watch={str(R): sorted(lv[(lv.R == R) & (mcw <= 2) & (lv.macd_pct < 0) & (lv.pos_now <= 0.5) & lv.e1_date.isna()].ticker.tolist()) for R in R_LIST},
                counts=dict(e1_recent=int(((e1w <= 4) & lv.e2_date.isna()).sum()), e1_open=int((e1w.notna() & (e1w <= 52) & lv.e2_date.isna()).sum()), e2_recent=int((e2w <= 4).sum())))
    summ["_meta"] = dict(tickers=len(tickers), events=int(len(df)), signals=int(len(sg)), live_bases=int(len(lv)), asof=str(asof_all.date()), prices=a.prices, params=dict(R=R_LIST, LMIN=LMIN, LMAX=LMAX, CONFIRM_WK=CONFIRM_WK, FLAT=FLAT, MIN_PRICE=MIN_PRICE, MIN_WK_DOLLAR_VOL=MIN_WK_DOLLAR_VOL, DIV=dict(K=DIV_K, MARGIN=DIV_MARGIN, PX_TOL=DIV_PX_TOL, RECENT=DIV_RECENT),
        H23=dict(MACD=[MACD_F, MACD_S, MACD_SIG], EO=[EO_F, EO_S], E_WINDOW=E_WINDOW, EO_CONFIRM=EO_CONFIRM, E1_POS_MAX=E1_POS_MAX, E2_TOUCH=E2_TOUCH, E2_BOUNCE=E2_BOUNCE, E2_MAX_WK=E2_MAX_WK, INV_STOP=INV_STOP, BLEND_W1=round(BLEND_W1, 3))), version="0.8")
    json.dump(summ, open(f"{a.out}/base_summary.json", "w"), indent=1, default=str)
    print(json.dumps(summ, indent=1, default=str))

if __name__ == "__main__":
    main()
