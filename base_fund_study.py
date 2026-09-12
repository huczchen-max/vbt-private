"""Fundamentals as a SELECTION layer on the base-pattern screen (v0.5, 2026-09-12).

Question (Eric): among bases that look ready (composite signals) — and among
confirmed upside breaks — do revenue/earnings growth, growth acceleration,
earnings surprise and quality separate the ones that beat the market?

Point-in-time join: for each signal/event date D, use the latest quarter whose
filing_date <= D (fallback: quarter end + 45 days when filing_date is missing).
Earnings history: latest report_date <= D.
Features (all as-of D):
  rev_yoy       revenue of latest quarter vs same quarter a year earlier
  rev_yoy_prev  the same for the prior quarter -> rev_accel = rev_yoy - rev_yoy_prev
  rev_ttm_yoy   trailing-4Q revenue vs prior trailing-4Q
  eps_yoy       latest eps_actual vs 4 reports earlier; surprise_pct of the latest report
  quality       TTM net income > 0 AND TTM FCF > 0  (Rulebook v2 definition)
Outputs: base_fund_signals.csv, base_fund_summary.json, base_live_fund.csv (live screen
enriched, incl. CURRENT short ratio / % float from fund_snapshot — snapshot only).
Usage: python base_fund_study.py --cache eodhd_cache --in . --out .
"""
import argparse, json
import numpy as np, pandas as pd

LAG_DAYS = 45
REV_BINS = [-9, 0, 0.10, 0.25, 0.50, 99]; REV_LABELS = ["<0%", "0-10%", "10-25%", "25-50%", ">50%"]
ACC_BINS = [-99, -0.10, -0.02, 0.02, 0.10, 99]; ACC_LABELS = ["decel>10pp", "decel", "flat", "accel", "accel>10pp"]

def prep_income(inc):
    inc = inc.dropna(subset=["revenue"]).copy()
    inc["q_date"] = pd.to_datetime(inc.q_date, errors="coerce"); inc["filing_date"] = pd.to_datetime(inc.filing_date, errors="coerce")
    inc["avail"] = inc.filing_date.fillna(inc.q_date + pd.Timedelta(days=LAG_DAYS))
    inc = inc.dropna(subset=["q_date"]).sort_values(["ticker", "q_date"]).drop_duplicates(["ticker", "q_date"], keep="last")
    g = inc.groupby("ticker")
    inc["rev_yoy"] = g.revenue.transform(lambda s: s / s.shift(4) - 1)
    inc["rev_yoy_prev"] = g.rev_yoy.transform(lambda s: s.shift(1))
    inc["rev_accel"] = inc.rev_yoy - inc.rev_yoy_prev
    ttm = g.revenue.transform(lambda s: s.rolling(4).sum())
    inc["rev_ttm_yoy"] = ttm / g.revenue.transform(lambda s: s.rolling(4).sum().shift(4)) - 1
    inc["ni_ttm"] = g.net_income.transform(lambda s: s.rolling(4).sum())
    inc["gm"] = inc.gross_profit / inc.revenue.replace(0, np.nan)
    return inc

def prep_cf(cf):
    cf = cf.copy(); cf["q_date"] = pd.to_datetime(cf.q_date, errors="coerce"); cf["filing_date"] = pd.to_datetime(cf.filing_date, errors="coerce")
    cf["avail"] = cf.filing_date.fillna(cf.q_date + pd.Timedelta(days=LAG_DAYS))
    cf = cf.dropna(subset=["q_date"]).sort_values(["ticker", "q_date"]).drop_duplicates(["ticker", "q_date"], keep="last")
    cf["fcf_ttm"] = cf.groupby("ticker").fcf.transform(lambda s: s.rolling(4).sum())
    return cf[["ticker", "q_date", "avail", "fcf_ttm"]]

def prep_earn(earn):
    e = earn.dropna(subset=["eps_actual"]).copy(); e["report_date"] = pd.to_datetime(e.report_date, errors="coerce")
    e = e.dropna(subset=["report_date"]).sort_values(["ticker", "report_date"]).drop_duplicates(["ticker", "report_date"], keep="last")
    g = e.groupby("ticker")
    prev = g.eps_actual.transform(lambda s: s.shift(4))
    e["eps_yoy"] = np.where((prev.abs() > 0.01), (e.eps_actual - prev) / prev.abs(), np.nan)
    e["eps_turn_pos"] = (e.eps_actual > 0) & (prev <= 0)
    return e[["ticker", "report_date", "eps_actual", "eps_yoy", "surprise_pct", "eps_turn_pos"]]

def asof_join(sig, tbl, on_date, keep):
    """sig has ticker+date; tbl has ticker + on_date; take latest tbl row with on_date <= date."""
    s = sig[["_id", "ticker", "date"]].sort_values("date"); t = tbl.sort_values(on_date)
    m = pd.merge_asof(s, t[["ticker", on_date] + keep], left_on="date", right_on=on_date, by="ticker", direction="backward")
    return m.set_index("_id")[keep + [on_date]]

def block(h, exc):
    if not len(h): return dict(n=0)
    return dict(n=int(len(h)), ret26_med=round(float(h.ret26.median()), 1), exc26_med=round(float(h[exc].median()), 1),
                win26=round(float((h.ret26 > 0).mean()), 2), mae26_med=round(float(h.mae26.median()), 1),
                ret26_p90=round(float(h.ret26.quantile(.9)), 1))

def tables(g, exc):
    out = {}
    g = g.copy()
    g["rev_bin"] = pd.cut(g.rev_yoy, REV_BINS, labels=REV_LABELS); g["acc_bin"] = pd.cut(g.rev_accel, ACC_BINS, labels=ACC_LABELS)
    g["eps_bin"] = pd.cut(g.eps_yoy, [-99, -0.2, 0, 0.25, 1.0, 99], labels=["<-20%", "-20-0%", "0-25%", "25-100%", ">100%"])
    g["surp_bin"] = pd.cut(g.surprise_pct, [-999, -5, 5, 999], labels=["miss>5%", "inline", "beat>5%"])
    out["all"] = block(g, exc); out["with_fundamentals"] = block(g.dropna(subset=["rev_yoy"]), exc); out["no_fundamentals"] = block(g[g.rev_yoy.isna()], exc)
    for col in ("rev_bin", "acc_bin", "eps_bin", "surp_bin", "quality", "eps_turn_pos"):
        out[f"by_{col}"] = {str(k): block(h, exc) for k, h in g.groupby(col, observed=True, dropna=False) if len(h) >= 30}
    # composite of fundamentals: growth>25% & accelerating & quality
    top = g[(g.rev_yoy > 0.25) & (g.rev_accel > 0) & (g.quality == True)]; out["growth_accel_quality"] = block(top, exc)
    q = g[g.quality == True]; out["quality_x_rev_bin"] = {str(k): block(h, exc) for k, h in q.groupby("rev_bin", observed=True) if len(h) >= 30}
    if "pre_vol" in g and g.pre_vol.notna().sum() > 100:
        g["vol_terc"] = pd.qcut(g.pre_vol.rank(method="first"), 3, labels=["lowvol", "midvol", "highvol"])
        out["rev_bin_x_vol"] = {f"{k[0]}|{k[1]}": block(h, exc) for k, h in g.groupby(["rev_bin", "vol_terc"], observed=True) if len(h) >= 30}
        out["quality_x_vol"] = {f"{k[0]}|{k[1]}": block(h, exc) for k, h in g.groupby(["quality", "vol_terc"], observed=True) if len(h) >= 30}
    out["by_year_growth_accel_quality"] = {str(y): block(h, exc) for y, h in top.groupby("year") if len(h) >= 10}
    return out

def enrich(df, inc, cf, earn):
    df = df.copy(); df["_id"] = range(len(df)); df["date"] = pd.to_datetime(df["date"])
    a = asof_join(df, inc, "avail", ["rev_yoy", "rev_yoy_prev", "rev_accel", "rev_ttm_yoy", "ni_ttm", "gm", "q_date"])
    b = asof_join(df, cf, "avail", ["fcf_ttm"])
    c = asof_join(df, earn, "report_date", ["eps_actual", "eps_yoy", "surprise_pct", "eps_turn_pos"])
    df = df.set_index("_id").join(a.drop(columns=["avail"])).join(b.drop(columns=["avail"])).join(c.drop(columns=["report_date"]))
    # stale-data guard: fundamentals must be within 200 days of the signal
    stale = (df["date"] - pd.to_datetime(df["q_date"])).dt.days > 200
    for col in ("rev_yoy", "rev_yoy_prev", "rev_accel", "rev_ttm_yoy", "ni_ttm", "gm"): df.loc[stale, col] = np.nan
    df["quality"] = np.where(df.ni_ttm.isna() | df.fcf_ttm.isna(), None, (df.ni_ttm > 0) & (df.fcf_ttm > 0))
    return df.reset_index(drop=True)

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--cache", default="eodhd_cache"); ap.add_argument("--in", dest="inp", default="."); ap.add_argument("--out", default=".")
    a = ap.parse_args()
    inc = prep_income(pd.read_parquet(f"{a.cache}/fund_income.parquet")); cf = prep_cf(pd.read_parquet(f"{a.cache}/fund_cf.parquet")); earn = prep_earn(pd.read_parquet(f"{a.cache}/fund_earn.parquet"))
    snap = pd.read_csv(f"{a.cache}/fund_snapshot.csv")
    print(f"fundamentals: {inc.ticker.nunique()} tickers with income, {earn.ticker.nunique()} with earnings history", flush=True)
    sig = pd.read_csv(f"{a.inp}/base_signals.csv"); ev = pd.read_csv(f"{a.inp}/base_events.csv")
    exc = "exc26_SPY"
    S = enrich(sig, inc, cf, earn); S.to_csv(f"{a.out}/base_fund_signals.csv", index=False)
    E = ev.rename(columns={"break_date": "date"}); E = enrich(E, inc, cf, earn)
    summ = {"_meta": dict(signals=int(len(S)), signals_with_fund=int(S.rev_yoy.notna().sum()), events=int(len(E)), events_with_fund=int(E.rev_yoy.notna().sum()))}
    for R in sorted(S.R.unique()):
        for kind in ("COMP", "ANTI"):
            g = S[(S.R == R) & (S.kind == kind)].dropna(subset=["ret26"])
            summ[f"signals_R{R}_{kind}"] = tables(g, exc)
            summ[f"signals_R{R}_{kind}_listed"] = tables(g[g.delisted == False], exc)
        u = E[(E.R == R) & (E.dir == "UP") & (E.confirmed == True)].dropna(subset=["ret26"])
        summ[f"upbreaks_R{R}"] = tables(u, exc)
    # live screen enrichment
    lv = pd.read_csv(f"{a.inp}/base_live.csv"); lv["date"] = lv["asof"]
    L = enrich(lv, inc, cf, earn).merge(snap[["ticker", "sector", "industry", "mkt_cap", "short_ratio", "short_pct_float", "shares_short", "shares_short_prior"]], on="ticker", how="left")
    L["short_chg_mom"] = L.shares_short / L.shares_short_prior - 1
    L.to_csv(f"{a.out}/base_live_fund.csv", index=False)
    comp = L[(L.pos_now > 0.66) & (L.rsi_now > 55) & (L.ma_now == True)]
    summ["live_composite_fund"] = dict(n=int(len(comp)), growth_accel_quality=sorted(comp[(comp.rev_yoy > 0.25) & (comp.rev_accel > 0) & (comp.quality == True)].ticker.tolist()),
                                       quality_growth10=sorted(comp[(comp.rev_yoy > 0.10) & (comp.quality == True)].ticker.tolist()),
                                       high_short=sorted(comp[comp.short_pct_float > 0.15].ticker.tolist()))
    json.dump(summ, open(f"{a.out}/base_fund_summary.json", "w"), indent=1, default=str)
    print(json.dumps({k: v for k, v in summ.items() if k in ("_meta", "live_composite_fund")}, indent=1, default=str))
    for k in summ:
        if k.startswith("signals_R2.0_COMP"):
            print(k, json.dumps({kk: summ[k][kk] for kk in ("all", "with_fundamentals", "by_rev_bin", "by_acc_bin", "by_quality", "growth_accel_quality")}, indent=1, default=str))

if __name__ == "__main__":
    main()
