"""H24 — blind labelling set (v0.1, 2026-09-23).

Question under test: does Eric's eye separate the bases that go on to
outperform from the ones that do not, when nothing but the chart is visible?
Every backtested trigger (H17-H23) failed; this tests the pattern recognition
the detectors only approximate.

Design
  Population = rows of base_signals.csv (base_study_wide v0.8): one row per
  (ticker, band R, decision bar) inside an open base, with forward returns
  already measured from that bar's close. Listed AND delisted names.
  Sample = N decision bars, stratified by kind:
      CTRL  random bar of a base            40%   (the honest baseline)
      DIVUP price low, RSI higher highs     25%   (the shape Eric believes in)
      E1    MACD cross at the EO trough     15%
      COMP  composite trigger               10%
      ANTI  mirror                          10%
  one row per (ticker, base) so no base appears twice, R2.0 preferred when a
  base fires on several bands; ret26 required (non-truncated); flat-line rows
  removed; +DUPS exact repeats of already-chosen items (test-retest).
Blinding: the page carries only the bars BEFORE the decision bar (up to
  CTX bars), closes rebased to 100 at the decision bar, $volume rebased to
  its median, RSI14, MACD/EO (% of price), the open-base band, and an opaque
  id. No ticker, no dates, no outcome. The answer key (ticker, date, kind,
  forward returns, excess vs SPY, MAE, next break, delisted, year, dup_of)
  is written to a separate file the labeller must not open.
Outputs: label/label_set.json, label/label_page.html (template
  label_template.html next to this script), label/label_key.csv.
Usage:
  python label_set.py --signals private/base_signals.csv --prices eodhd_cache/eod_us.parquet \
         --out private/label --n 300 --dups 30 --seed 24 --ctx 780
"""
import argparse, hashlib, json, os, sys
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from base_study_wide import weekly, rsi, macd, eo, FLATLINE_MAX

MIX = {"CTRL": 0.40, "DIVUP": 0.25, "E1": 0.15, "COMP": 0.10, "ANTI": 0.10}
KEY_COLS = ["ticker", "R", "date", "year", "kind", "base_start", "base_len", "pos", "rsi", "wk_since_low", "delisted", "regime_spy_up",
            "mad_med", "pre_vol", "contr8", "vol_dry8", "rsi_slope26", "next_break", "wk_to_break",
            "ret13", "exc13_SPY", "mae13", "ret26", "exc26_SPY", "mae26", "ret52", "exc52_SPY", "mae52", "trunc52",
            "wk_to_comp", "ret_to_comp", "comp_before", "divup_before", "e1_before"]

def opaque_id(ticker, date, R, seed):
    return hashlib.sha1(f"{seed}|{ticker}|{date}|{R}".encode()).hexdigest()[:10]

def sample_rows(sg, n, seed):
    rng = np.random.default_rng(seed)
    d = sg[sg.kind.isin(MIX)].dropna(subset=["ret26"]).copy()
    if "trunc26" in d: d = d[d.trunc26 != True]
    if "zero_wk_share" in d: d = d[~(d.zero_wk_share > FLATLINE_MAX)]
    # one row per (ticker, base): prefer R2.0, then 1.5, then 3.0 (the IOVA range was 2.4x)
    d["rpref"] = d.R.map({2.0: 0, 1.5: 1, 3.0: 2}).fillna(3)
    d = d.sort_values(["ticker", "base_start", "rpref"]).drop_duplicates(["ticker", "base_start", "kind"])
    picks = []
    used = set()
    for kind, share in MIX.items():
        k = int(round(n * share)); pool = d[(d.kind == kind) & ~d.set_index(["ticker", "base_start"]).index.isin(used)]
        if not len(pool): continue
        take = pool.sample(min(k, len(pool)), random_state=int(rng.integers(1e9)))
        picks.append(take); used |= set(zip(take.ticker, take.base_start))
    out = pd.concat(picks).reset_index(drop=True)
    return out

def export(rows, px, out, seed, ctx, dups):
    rng = np.random.default_rng(seed + 1)
    W = {t: weekly(g) for t, g in px[px.ticker.isin(set(rows.ticker))].groupby("ticker")}
    items = []; key = []
    for _, r in rows.iterrows():
        w = W.get(r.ticker)
        if w is None: continue
        c = w["close"]; v = c.values.astype(float); idx = c.index
        try: t = idx.get_loc(pd.Timestamp(r.date)); s = idx.get_loc(pd.Timestamp(r.base_start))
        except KeyError: continue
        if t - s < 5 or np.isnan(v[t]) or v[t] <= 0: continue
        i0 = max(0, t + 1 - ctx)
        rs = rsi(c).values; ml, sg_ = macd(c); eo_ = eo(c); dv = w["dvol"].values.astype(float)
        base = v[s:t + 1]; lo, hi = float(base.min()), float(base.max())
        scale = 100.0 / v[t]; dmed = float(np.nanmedian(dv[s:t + 1])) or 1.0
        pct = lambda a: [(None if np.isnan(x) else round(float(x / px_ * 100), 2)) for x, px_ in zip(a, v[i0:t + 1])]
        iid = opaque_id(r.ticker, r.date, r.R, seed)
        items.append(dict(id=iid, n=int(t + 1 - i0), s=int(s - i0),
                          c=[round(float(x * scale), 2) for x in v[i0:t + 1]], r=[(None if np.isnan(x) else round(float(x), 1)) for x in rs[i0:t + 1]],
                          dv=[round(float(x / dmed), 2) if not np.isnan(x) else 0 for x in dv[i0:t + 1]],
                          m=pct(ml.values[i0:t + 1]), ms=pct(sg_.values[i0:t + 1]), o=pct(eo_.values[i0:t + 1]),
                          lo=round(lo * scale, 2), hi=round(hi * scale, 2), band=round(float(r.R), 2)))
        k = {c_: (r[c_] if c_ in r else None) for c_ in KEY_COLS}; k["id"] = iid; k["dup_of"] = ""; key.append(k)
    # shuffle the originals, then insert each test-retest repeat (new id, same bars) at least GAP charts after its original
    rng.shuffle(items)
    GAP = 40 if len(items) > 120 else max(5, len(items) // 4)
    keyd = {k["id"]: k for k in key}
    src_pool = [it["id"] for it in items[:max(1, len(items) - GAP)]]
    for sid in rng.choice(src_pool, size=min(dups, len(src_pool)), replace=False):
        src_pos = next(i for i, it in enumerate(items) if it["id"] == sid); src = items[src_pos]
        nid = hashlib.sha1(("dup|" + sid).encode()).hexdigest()[:10]
        ins = int(rng.integers(src_pos + GAP, len(items) + 1)) if src_pos + GAP <= len(items) else len(items)
        items.insert(ins, dict(src, id=nid)); kk = dict(keyd[sid]); kk["id"] = nid; kk["dup_of"] = sid; key.append(kk)
    payload = dict(set_id=f"h24-{seed}", n=len(items), ctx=ctx, question="Would you buy this base here (26-week horizon, Rulebook sizing)?",
                   items=items)
    os.makedirs(out, exist_ok=True)
    txt = json.dumps(payload, separators=(",", ":"))
    open(f"{out}/label_set.json", "w").write(txt)
    pd.DataFrame(key).to_csv(f"{out}/label_key.csv", index=False)
    tpl = os.path.join(os.path.dirname(os.path.abspath(__file__)), "label_template.html")
    if os.path.exists(tpl):
        html = open(tpl, encoding="utf-8").read().replace("__LABEL_JSON__", txt.replace("</", "<\\/"))
        open(f"{out}/label_page.html", "w", encoding="utf-8").write(html)
    return len(items), len(key)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--signals", required=True); ap.add_argument("--prices", required=True); ap.add_argument("--out", default="label")
    ap.add_argument("--n", type=int, default=300); ap.add_argument("--dups", type=int, default=30); ap.add_argument("--seed", type=int, default=24); ap.add_argument("--ctx", type=int, default=780)
    a = ap.parse_args()
    sg = pd.read_csv(a.signals, low_memory=False)
    rows = sample_rows(sg, a.n, a.seed)
    print("sampled", len(rows), rows.kind.value_counts().to_dict(), "delisted share", round(float(rows.delisted.mean()), 2), "years", int(rows.year.min()), "-", int(rows.year.max()))
    px = pd.read_parquet(a.prices, filters=[("ticker", "in", sorted(set(rows.ticker)))]) if a.prices.endswith(".parquet") else pd.read_csv(a.prices)
    n_items, n_key = export(rows, px, a.out, a.seed, a.ctx, a.dups)
    print(f"label set: {n_items} charts ({a.dups} repeats), key rows {n_key} -> {a.out}/label_set.json, label_page.html, label_key.csv")

if __name__ == "__main__":
    main()
