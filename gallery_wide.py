"""Visual gallery of matched bases from the wide study (v0.6, 2026-09-12).

Renders 3x3 pages of weekly charts so Eric can inspect what the detector calls a
tight base. Runs in Actions after base_study_wide.py (needs the parquet cache).
Sets (listed names only, seeded random sample, R=1.5 unless noted):
  tight_up       MAD < 5%, confirmed UP break
  tight_down     MAD < 5%, confirmed DOWN break
  tight_contract MAD < 7% and contr8 < 0.8 (range contracting into the break)
  loose_up       MAD 10-15%, confirmed UP break (contrast)
  live_tight     open bases now, MAD < 7%, composite state (the live screen)
  live_vcp       open bases now, contr8 < 0.8 and vol_dry8 < 0.9
  live_divup     v0.7: open bases now in the DIVUP state (price low in band, RSI higher highs), any R
  live_divdn     v0.7: open bases now in the DIVDN state (price high in band, RSI lower highs), any R
Usage: python gallery_wide.py --prices eodhd_cache/eod_us.parquet --in private --out private/gallery
"""
import argparse, math, os
import numpy as np, pandas as pd, matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from base_study_wide import weekly

TEAL, SLATE, ORANGE, INK = "#0F766E", "#64748B", "#C2410C", "#1E293B"
PER_PAGE, COLS, N_PER_SET, SEED = 9, 3, 18, 7

def panel(ax, c, r, live=False):
    s = pd.Timestamp(r.start); e = pd.Timestamp(r["end"] if not live else r["asof"])
    b = None if live else pd.Timestamp(r.break_date)
    i0 = max(0, c.index.get_loc(s) - 26); i1 = min(len(c), c.index.get_loc(e if live else b) + (1 if live else 27))
    seg = c.iloc[i0:i1]
    ax.plot(seg.index, seg.values, color=INK, lw=1.1)
    ax.axhspan(r.base_lo, r.base_hi, color=SLATE, alpha=0.10)
    ax.axvspan(s, e, color=SLATE, alpha=0.12)
    if not live:
        col = TEAL if r.dir == "UP" else ORANGE
        ax.axvline(b, color=col, lw=1.4)
        conf = "confirmed" if r.confirmed == True else ("FAKEOUT" if r.confirmed == False else "open")
        ret = f"  26w {r.ret26:+.0f}%" if pd.notna(r.ret26) else ""
        head = f"{r.ticker}  {r.dir} · {conf}{ret}"
    else:
        head = f"{r.ticker}  LIVE {r.state_now if 'state_now' in r and isinstance(r.state_now, str) else ''}  close {r.close}  pos {r.pos_now:.2f} rsi {r.rsi_now:.0f} ma13>26 {r.ma_now}"
    extra = f"MAD {r.mad_med*100:.1f}%"
    if "contr8" in r and pd.notna(r.contr8): extra += f"  contr8 {r.contr8:.2f}  voldry8 {r.vol_dry8:.2f}"
    ax.set_title(f"{head}\nbase {r.base_len}w  {str(r.start)[:7]}→{str(e.date())[:7]}   {extra}", fontsize=7.5, color=INK, loc="left")
    ax.set_yscale("log"); ax.grid(alpha=0.15); ax.tick_params(labelsize=6.5, colors=SLATE)
    for sp in ax.spines.values(): sp.set_color("#E2E8F0")
    ax.xaxis.set_major_locator(matplotlib.dates.YearLocator()); ax.xaxis.set_major_formatter(matplotlib.dates.DateFormatter("%Y"))
    ax.yaxis.set_minor_formatter(matplotlib.ticker.NullFormatter()); ax.yaxis.set_major_formatter(matplotlib.ticker.ScalarFormatter())

def render(name, df, W, out, live=False):
    df = df.reset_index(drop=True); pages = math.ceil(len(df) / PER_PAGE); files = []
    for p in range(pages):
        chunk = df.iloc[p*PER_PAGE:(p+1)*PER_PAGE]; rows = math.ceil(len(chunk) / COLS)
        fig, axes = plt.subplots(rows, COLS, figsize=(4.6*COLS, 3.2*rows), squeeze=False)
        for ax in axes.flat: ax.set_visible(False)
        for ax, (_, r) in zip(axes.flat, chunk.iterrows()):
            if r.ticker not in W: continue
            ax.set_visible(True)
            try: panel(ax, W[r.ticker]["close"], r, live)
            except Exception as ex: ax.set_title(f"{r.ticker}: {type(ex).__name__}: {str(ex)[:60]}", fontsize=7)
        fig.suptitle(f"{name} — page {p+1}/{pages}  (grey = base; teal/orange line = UP/DOWN break)", fontsize=10, color=TEAL, x=0.01, ha="left")
        fig.tight_layout(rect=(0, 0, 1, 0.97)); f = f"{out}/{name}_{p+1}.png"; fig.savefig(f, dpi=105); plt.close(fig); files.append(f)
    return files

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--prices", required=True); ap.add_argument("--in", dest="inp", default="."); ap.add_argument("--out", default="gallery")
    a = ap.parse_args(); os.makedirs(a.out, exist_ok=True)
    ev = pd.read_csv(f"{a.inp}/base_events.csv"); lv = pd.read_csv(f"{a.inp}/base_live.csv")
    ev = ev[(ev.delisted == False) & (ev.R == 1.5) & (ev.confirmed == True)]
    if "zero_wk_share" in ev: ev = ev[~(ev.zero_wk_share > 0.3)]
    rng = np.random.default_rng(SEED)
    def samp(d): return d.sample(min(N_PER_SET, len(d)), random_state=SEED) if len(d) else d
    sets = {"tight_up": samp(ev[(ev.mad_med < 0.05) & (ev.dir == "UP")]),
            "tight_down": samp(ev[(ev.mad_med < 0.05) & (ev.dir == "DOWN")]),
            "loose_up": samp(ev[(ev.mad_med.between(0.10, 0.15)) & (ev.dir == "UP")])}
    if "contr8" in ev: sets["tight_contract"] = samp(ev[(ev.mad_med < 0.07) & (ev.contr8 < 0.8)])
    l = lv[lv.R == 1.5]
    sets["live_tight"] = l[(l.mad_med < 0.07) & (l.pos_now > 0.66) & (l.rsi_now > 55) & (l.ma_now == True)].sort_values("mad_med").head(N_PER_SET)
    if "contr8" in l: sets["live_vcp"] = l[(l.contr8 < 0.8) & (l.vol_dry8 < 0.9)].sort_values("contr8").head(N_PER_SET)
    if "state_now" in lv:
        for st in ("DIVUP", "DIVDN"):
            d = lv[lv.state_now == st].sort_values("R").drop_duplicates("ticker")
            sets[f"live_{st.lower()}"] = d.sort_values("rsi_slope26", ascending=(st == "DIVDN")).head(N_PER_SET)
    need = set(pd.concat([d.ticker for d in sets.values() if len(d)]).unique())
    px = pd.read_parquet(a.prices, filters=[("ticker", "in", list(need))])
    W = {t: weekly(g) for t, g in px.groupby("ticker")}
    for name, d in sets.items():
        files = render(name, d, W, a.out, live=name.startswith("live"))
        print(name, len(d), "rows ->", files)
    pd.concat([d.assign(gallery_set=k) for k, d in sets.items() if len(d)]).to_csv(f"{a.out}/gallery_index.csv", index=False)

if __name__ == "__main__":
    main()
