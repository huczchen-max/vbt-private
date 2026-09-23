"""Visual gallery of matched bases from the wide study (v0.8, 2026-09-23).

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
  e1_hits        v0.8 H23: E1 rows (MACD cross + EO trough) that were followed by an E2, with MACD and EO panels
  e1_stranded    v0.8 H23: E1 rows that never got an E2 (test tranche left alone)
  live_e1        v0.8: open bases with an E1 in the last 26 weeks and no E2 yet (test-tranche candidates)
  live_e2        v0.8: open bases whose E2 fired in the last 26 weeks
Usage: python gallery_wide.py --prices eodhd_cache/eod_us.parquet --in private --out private/gallery
"""
import argparse, math, os
import numpy as np, pandas as pd, matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from base_study_wide import weekly, macd, eo

TEAL, SLATE, ORANGE, INK = "#0F766E", "#64748B", "#C2410C", "#1E293B"
PER_PAGE, COLS, N_PER_SET, SEED = 9, 3, 18, 7

def panel(ax, c, r, live=False):
    s = pd.Timestamp(r.start); e = pd.Timestamp(r["end"] if not live else r.asof)
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

def panel_entry(axp, axm, axo, c, r, live=False):
    """v0.8: price + base band with E1/E2 markers, MACD (line, signal, histogram) and EO (bars) below."""
    s = pd.Timestamp(r.base_start if not live else r.start); d = pd.Timestamp(r.date if not live else r.asof)
    i_s = c.index.get_loc(s); i_d = c.index.get_loc(d)
    i0 = max(0, i_s - 26); i1 = min(len(c), i_d + (1 if live else 31))
    seg = c.iloc[i0:i1]; ml, sg = macd(c); eo_ = eo(c)
    axp.plot(seg.index, seg.values, color=INK, lw=1.1)
    axp.axhspan(r.base_lo, r.base_hi, color=SLATE, alpha=0.10) if "base_lo" in r else None
    axp.axvspan(s, d if live else c.index[min(i_d + int(r.wk_to_break) if pd.notna(r.get("wk_to_break", np.nan)) else i_d, len(c) - 1)], color=SLATE, alpha=0.12)
    e1 = pd.Timestamp(r.e1_date) if live and isinstance(r.get("e1_date"), str) else (d if not live else None)
    e2 = None
    if live and isinstance(r.get("e2_date"), str): e2 = pd.Timestamp(r.e2_date)
    if not live and pd.notna(r.get("wk_to_e2", np.nan)): e2 = c.index[min(i_d + int(r.wk_to_e2), len(c) - 1)]
    if e1 is not None: axp.axvline(e1, color=TEAL, lw=1.4, ls="--")
    if e2 is not None: axp.axvline(e2, color="#1D4ED8", lw=1.4)
    if not live and isinstance(r.get("next_break"), str) and r.next_break in ("UP", "DOWN") and pd.notna(r.wk_to_break):
        b = c.index[min(i_d + int(r.wk_to_break), len(c) - 1)]; axp.axvline(b, color=TEAL if r.next_break == "UP" else ORANGE, lw=1.0, alpha=0.7)
    if live:
        head = f"{r.ticker}  LIVE  E1 {r.e1_date or '—'} ({r.e1_wk_ago:.0f}w ago)" + (f"  E2 {r.e2_date} {r.e2_kind}" if isinstance(r.get('e2_date'), str) else "  no E2 yet") + f"  close {r.close}  pos {r.pos_now:.2f}"
    else:
        ret = f"  26w {r.ret26:+.0f}%" if pd.notna(r.ret26) else ""; bl = f"  blend {r.blend_ret:+.0f}% (mae {r.blend_mae:.0f}%)" if pd.notna(r.get("blend_ret", np.nan)) else ""
        head = f"{r.ticker}  E1 {r.date}  pos {r.pos:.2f}" + (f"  E2 +{int(r.wk_to_e2)}w {r.e2_kind}" if pd.notna(r.wk_to_e2) else "  stranded") + ret + bl + (f"  {r.next_break} +{int(r.wk_to_break)}w" if isinstance(r.next_break, str) and r.next_break != 'NONE' else "")
    axp.set_title(head + f"\nbase {r.base_len}w from {str(s.date())[:7]}  MACD@cross {r.get('macd_pct_cross', r.get('macd_pct', np.nan)):.1f}%  EO trough {r.get('eo_pct_trough', r.get('eo_pct', np.nan)):.1f}%  R{r.R}", fontsize=7.2, color=INK, loc="left")
    axp.set_yscale("log"); axp.yaxis.set_minor_formatter(matplotlib.ticker.NullFormatter()); axp.yaxis.set_major_formatter(matplotlib.ticker.ScalarFormatter())
    m_, sg_, eo_s = ml.iloc[i0:i1], sg.iloc[i0:i1], eo_.iloc[i0:i1]
    axm.bar(m_.index, (m_ - sg_).values, width=6, color=np.where((m_ - sg_).values >= 0, TEAL, ORANGE), alpha=0.6)
    axm.plot(m_.index, m_.values, color="#1D4ED8", lw=0.9); axm.plot(sg_.index, sg_.values, color=ORANGE, lw=0.9); axm.axhline(0, color=SLATE, lw=0.6)
    axo.bar(eo_s.index, eo_s.values, width=6, color=np.where(eo_s.values >= 0, TEAL, ORANGE), alpha=0.7); axo.axhline(0, color=SLATE, lw=0.6)
    for ax, lab in ((axm, "MACD"), (axo, "EO")):
        ax.text(0.005, 0.85, lab, transform=ax.transAxes, fontsize=6.5, color=SLATE)
        if e1 is not None: ax.axvline(e1, color=TEAL, lw=0.8, ls="--")
        if e2 is not None: ax.axvline(e2, color="#1D4ED8", lw=0.8)
    for ax in (axp, axm, axo):
        ax.grid(alpha=0.15); ax.tick_params(labelsize=6, colors=SLATE); ax.set_xlim(seg.index[0], seg.index[-1])
        for sp in ax.spines.values(): sp.set_color("#E2E8F0")
        ax.xaxis.set_major_locator(matplotlib.dates.YearLocator()); ax.xaxis.set_major_formatter(matplotlib.dates.DateFormatter("%Y"))
    axp.tick_params(labelbottom=False); axm.tick_params(labelbottom=False); axo.tick_params(labelbottom=True)

def render_entry(name, df, W, out, live=False):
    df = df.reset_index(drop=True); per = 6; cols = 2; pages = math.ceil(len(df) / per); files = []
    for p in range(pages):
        chunk = df.iloc[p*per:(p+1)*per]; rows = math.ceil(len(chunk) / cols)
        fig = plt.figure(figsize=(6.4*cols, 4.8*rows)); gs = fig.add_gridspec(rows*4, cols, height_ratios=[3, 1, 1, 0.55]*rows, hspace=0.10, wspace=0.12)
        for k, (_, r) in enumerate(chunk.iterrows()):
            if r.ticker not in W: continue
            ri, ci = divmod(k, cols); axp = fig.add_subplot(gs[ri*4, ci]); axm = fig.add_subplot(gs[ri*4+1, ci], sharex=axp); axo = fig.add_subplot(gs[ri*4+2, ci], sharex=axp)
            try: panel_entry(axp, axm, axo, W[r.ticker]["close"], r, live)
            except Exception as ex: axp.set_title(f"{r.ticker}: {ex}", fontsize=7)
        fig.suptitle(f"{name} — page {p+1}/{pages}  (grey = base; teal dashed = E1 test tranche; blue = E2 main tranche; thin teal/orange = next break)", fontsize=9.5, color=TEAL, x=0.01, ha="left")
        fig.tight_layout(rect=(0, 0, 1, 0.97)); f = f"{out}/{name}_{p+1}.png"; fig.savefig(f, dpi=105); plt.close(fig); files.append(f)
    return files

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
            except Exception as ex: ax.set_title(f"{r.ticker}: {ex}", fontsize=7)
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
    entry_sets = {}
    try:
        sg = pd.read_csv(f"{a.inp}/base_signals.csv")
        e1 = sg[(sg.kind == "E1") & (sg.delisted == False)]
        if "zero_wk_share" in e1: e1 = e1[~(e1.zero_wk_share > 0.3)]
        e1 = e1.sort_values("R").drop_duplicates(["ticker", "base_start"])
        entry_sets["e1_hits"] = samp(e1[e1.wk_to_e2.notna() & e1.ret26.notna()])
        entry_sets["e1_stranded"] = samp(e1[e1.wk_to_e2.isna() & e1.ret26.notna()])
    except Exception as ex:
        print("no E1 rows for the gallery:", ex)
    if "e1_date" in lv:
        l2 = lv.sort_values("R").drop_duplicates("ticker")
        entry_sets["live_e1"] = l2[l2.e1_wk_ago.notna() & (l2.e1_wk_ago <= 26) & l2.e2_date.isna()].sort_values("e1_wk_ago").head(N_PER_SET)
        entry_sets["live_e2"] = l2[l2.e2_wk_ago.notna() & (l2.e2_wk_ago <= 26)].sort_values("e2_wk_ago").head(N_PER_SET)
    need = set(pd.concat([d.ticker for d in list(sets.values()) + list(entry_sets.values()) if len(d)]).unique())
    px = pd.read_parquet(a.prices, filters=[("ticker", "in", list(need))])
    W = {t: weekly(g) for t, g in px.groupby("ticker")}
    for name, d in sets.items():
        files = render(name, d, W, a.out, live=name.startswith("live"))
        print(name, len(d), "rows ->", files)
    for name, d in entry_sets.items():
        files = render_entry(name, d, W, a.out, live=name.startswith("live")) if len(d) else []
        print(name, len(d), "rows ->", files)
    pd.concat([d.assign(gallery_set=k) for k, d in {**sets, **entry_sets}.items() if len(d)]).to_csv(f"{a.out}/gallery_index.csv", index=False)

if __name__ == "__main__":
    main()
