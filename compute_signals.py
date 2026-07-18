"""Compute recovery stages + daily transitions and publish the dashboard.

Runs in the GitHub Action right after fetch_data.py. Reads data/prices.csv,
classifies every universe name into a recovery stage using the causal weekly
swing-structure engine, diffs stages against the previous run, and writes:

  docs/signals.json  — machine-readable stages + today's transitions
  docs/index.html    — self-contained mobile-friendly dashboard (GitHub Pages)

Stage model (weekly bars, pivot ±5, drawdown vs trailing 52w peak):
  0 intact/no-correction · 1 Downtrend · 2 Base building (watch) ·
  3 CONFIRMED (Mixed→Uptrend, still ≥15% below peak) · 4 Recovered
Backtest (10y, 45 names): stage 3 was the only entry with positive excess
return vs SMH; stage 2 entries were early (negative excess).
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path.cwd()  # runs from public repo root; this file lives in the private repo
DOCS = HERE / "docs"
DOCS.mkdir(exist_ok=True)

LOOKBACK = 5
DD_ENTER = -0.30
DD_STILL_BELOW = -0.15

# ticker -> (group, quality)  quality = GAAP-profitable AND FCF+ (2026-07 snapshot)
UNIVERSE = {
    "ALAB": ("semi", True), "AMAT": ("semi", True), "AMD": ("semi", True),
    "ANET": ("hw", True), "APLD": ("neocloud", False), "ARM": ("semi", True),
    "ASML": ("semi", True), "AVGO": ("semi", True), "CDNS": ("semi", True),
    "CEG": ("power", False), "CIEN": ("hw", True), "CIFR": ("neocloud", False),
    "COHR": ("hw", False), "CORZ": ("neocloud", False), "CRDO": ("semi", True),
    "CRWV": ("neocloud", False), "DELL": ("hw", True), "ETN": ("power", True),
    "GEV": ("power", True), "GLXY": ("neocloud", False), "HPE": ("hw", True),
    "HUT": ("neocloud", False), "INTC": ("semi", False), "IREN": ("neocloud", False),
    "KLAC": ("semi", True), "LITE": ("hw", True), "LRCX": ("semi", True),
    "MOD": ("hw", False), "MPWR": ("semi", True), "MRVL": ("semi", True),
    "MU": ("semi", True), "NBIS": ("neocloud", False), "NRG": ("power", True),
    "NVDA": ("semi", True), "ON": ("semi", True), "POWL": ("power", True),
    "PWR": ("power", True), "QCOM": ("semi", True), "SMCI": ("hw", False),
    "SNPS": ("semi", True), "STX": ("hw", True), "TLN": ("power", False),
    "TSM": ("semi", True), "VRT": ("hw", True), "VST": ("power", False),
    "WDC": ("hw", True), "WULF": ("neocloud", False),
}

STAGE_NAMES = {
    0: "Intact", 1: "Downtrend", 2: "Base building", 3: "CONFIRMED", 4: "Recovered",
}


def find_pivots(high, low, lookback=LOOKBACK):
    win = 2 * lookback + 1
    return pd.DataFrame({
        "high_pivot": (high == high.rolling(win, center=True).max()).fillna(False),
        "low_pivot": (low == low.rolling(win, center=True).min()).fillna(False),
    })


def causal_trend_history(high, low, lookback=LOOKBACK):
    pivots = find_pivots(high, low, lookback)
    n, idx = len(high), high.index
    events = []
    for pos in range(n):
        if pivots.iloc[pos]["high_pivot"]:
            events.append((pos + lookback, pos, "H"))
        if pivots.iloc[pos]["low_pivot"]:
            events.append((pos + lookback, pos, "L"))
    events.sort()
    states, ei = [], 0
    last_h_val = last_l_val = last_h_lab = last_l_lab = None
    for j in range(n):
        while ei < len(events) and events[ei][0] <= j:
            _, ppos, kind = events[ei]
            ei += 1
            if kind == "H":
                v = float(high.iloc[ppos])
                if last_h_val is not None:
                    last_h_lab = "HH" if v > last_h_val else "LH"
                last_h_val = v
            else:
                v = float(low.iloc[ppos])
                if last_l_val is not None:
                    last_l_lab = "HL" if v > last_l_val else "LL"
                last_l_val = v
        states.append("Uptrend" if (last_h_lab, last_l_lab) == ("HH", "HL")
                      else "Downtrend" if (last_h_lab, last_l_lab) == ("LH", "LL")
                      else "Mixed")
    return pd.Series(states, index=idx)


def classify(daily):
    if daily is None or len(daily) < 200:
        return None
    w = daily.resample("W-FRI").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last"}).dropna()
    if len(w) < 2 * LOOKBACK + 20:
        return None
    close = w["close"]
    states = causal_trend_history(w["high"], w["low"])
    peak52 = close.rolling(52, min_periods=12).max()
    dd = close / peak52 - 1.0
    dd_min26 = dd.rolling(26, min_periods=1).min()
    cur_state, cur_dd = str(states.iloc[-1]), float(dd.iloc[-1])
    corrected = bool(dd_min26.iloc[-1] <= DD_ENTER)
    chg = states != states.shift()
    trans_idx = states.index[chg]
    last_trans = trans_idx[-1] if len(trans_idx) else states.index[0]
    weeks = int(len(states) - states.index.get_loc(last_trans))
    if not corrected:
        stage = 0
    elif cur_state == "Downtrend":
        stage = 1
    elif cur_state == "Mixed":
        stage = 2
    elif cur_dd <= DD_STILL_BELOW:
        stage = 3
    else:
        stage = 4
    return {
        "price": round(float(close.iloc[-1]), 2),
        "dd": round(cur_dd * 100, 1),
        "max_dd_26w": round(float(dd_min26.iloc[-1]) * 100, 1),
        "stage": stage, "stage_name": STAGE_NAMES[stage],
        "state": cur_state, "weeks_in_state": weeks,
        "since": last_trans.date().isoformat(),
    }


def main():
    px = pd.read_csv(HERE / "data" / "prices.csv", parse_dates=["date"])
    rows = []
    for t, g in px.groupby("ticker"):
        if t not in UNIVERSE:
            continue
        d = g.set_index("date")[["open", "high", "low", "close"]].sort_index()
        r = classify(d.tail(800))
        if r is None:
            continue
        grp, q = UNIVERSE[t]
        r.update({"ticker": t, "group": grp, "quality": q})
        rows.append(r)
    rows.sort(key=lambda r: ({3: 0, 2: 1, 1: 2, 4: 3, 0: 4}[r["stage"]], r["dd"]))

    # ---- transitions vs previous run
    prev_path = DOCS / "signals.json"
    prev_stages = {}
    if prev_path.exists():
        try:
            prev = json.loads(prev_path.read_text())
            prev_stages = {r["ticker"]: r["stage"] for r in prev.get("rows", [])}
        except Exception:
            pass
    today = datetime.now(timezone.utc).date().isoformat()
    transitions = []
    for r in rows:
        old = prev_stages.get(r["ticker"])
        if old is not None and old != r["stage"]:
            transitions.append({
                "ticker": r["ticker"], "date": today,
                "from": old, "to": r["stage"],
                "from_name": STAGE_NAMES[old], "to_name": STAGE_NAMES[r["stage"]],
                "alert": bool(r["stage"] == 3 or old == 3),
            })

    payload = {
        "as_of": today,
        "updated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "counts": {name: sum(1 for r in rows if r["stage"] == s)
                   for s, name in STAGE_NAMES.items()},
        "transitions": transitions,
        "rows": rows,
    }
    prev_path.write_text(json.dumps(payload, indent=1))
    (DOCS / "index.html").write_text(render_html(payload))
    print(f"signals: {len(rows)} rows, {len(transitions)} transitions "
          f"({sum(1 for t in transitions if t['alert'])} alert-worthy)")


def rerender_html_only():
    """Re-render index.html from existing signals.json (+ paper.json if
    present) without recomputing stages — used after trade_paper.py runs so
    the paper section is current, without wiping the day's transitions."""
    payload = json.loads((DOCS / "signals.json").read_text())
    (DOCS / "index.html").write_text(render_html(payload))
    print("re-rendered index.html")


# ---------------------------------------------------------------------------
# Dashboard HTML
# ---------------------------------------------------------------------------

STAGE_BADGE = {  # stage -> (label, css class)
    3: ("&#9679; CONFIRMED", "s3"), 2: ("&#9650; Base building", "s2"),
    1: ("&#9660; Downtrend", "s1"), 4: ("&#10003; Recovered", "s4"),
    0: ("&mdash; Intact", "s0"),
}


def render_html(p):
    row_html = []
    for r in p["rows"]:
        label, cls = STAGE_BADGE[r["stage"]]
        q = "quality" if r["quality"] else "spec"
        row_html.append(
            f'<tr class="{cls}-row">'
            f'<td class="tk"><a href="symbol.html?t={r["ticker"]}">{r["ticker"]}</a></td>'
            f'<td><span class="badge {cls}">{label}</span></td>'
            f'<td class="num">{r["price"]:,}</td>'
            f'<td class="num">{r["dd"]:+.1f}%</td>'
            f'<td class="num">{r["max_dd_26w"]:+.1f}%</td>'
            f'<td class="num">{r["weeks_in_state"]}w</td>'
            f'<td class="mut">{r["since"]}</td>'
            f'<td><span class="chip {q}">{q}</span></td>'
            f'<td class="mut">{r["group"]}</td></tr>'
        )
    paper_html = ""
    import os
    paper_path = Path(os.environ.get("PAPER_STATE_DIR") or "/nonexistent") / "paper.json"
    if paper_path.exists():
        try:
            pp = json.loads(paper_path.read_text())
            acct = pp.get("account", {})
            pos_rows = "".join(
                f'<tr><td class="tk"><a href="symbol.html?t={x["symbol"]}">{x["symbol"]}</a></td>'
                f'<td class="num">{x["qty"]:g}</td>'
                f'<td class="num">{x["avg_entry"]:,}</td>'
                f'<td class="num">{x["current"]:,}</td>'
                f'<td class="num" style="color:var(--{"good" if x["pl_usd"] >= 0 else "crit"})">'
                f'{x["pl_pct"]:+.1f}%</td>'
                f'<td class="mut">{x["stage"]}</td>'
                f'<td class="mut hide-m">{x["entered"]}</td></tr>'
                for x in pp.get("positions", []))
            if not pos_rows:
                pos_rows = '<tr><td colspan="7" class="mut">No open positions</td></tr>'
            recent = "".join(
                f'<li><b>{l["action"]}</b> {l["symbol"]} &middot; {l["note"]} '
                f'<span class="mut">({l["date"]})</span></li>'
                for l in reversed(pp.get("ledger", [])[-5:]))
            paper_html = (
                '<div class="card"><h2>Paper portfolio (Alpaca — simulated)</h2>'
                f'<div class="meta" style="color:var(--ink2);font-size:.8rem;margin-bottom:6px">'
                f'Equity ${acct.get("equity", 0):,.0f} &middot; cash ${acct.get("cash", 0):,.0f} '
                f'&middot; as of {pp.get("as_of", "")}</div>'
                '<table><thead><tr><th>Sym</th><th class="num">Qty</th>'
                '<th class="num">Entry</th><th class="num">Now</th><th class="num">P&amp;L</th>'
                '<th>Stage</th><th class="hide-m">Since</th></tr></thead>'
                f'<tbody>{pos_rows}</tbody></table>'
                + (f'<ul style="margin:8px 0 0;padding-left:18px;font-size:.8rem">{recent}</ul>'
                   if recent else "")
                + '</div>')
        except Exception:
            paper_html = ""
    trans_html = ""
    if p["transitions"]:
        items = "".join(
            f'<li><b>{t["ticker"]}</b> moved {t["from_name"]} &rarr; '
            f'<b>{t["to_name"]}</b>{" &#128276;" if t["alert"] else ""}</li>'
            for t in p["transitions"])
        trans_html = f'<div class="card trans"><h2>Changes today</h2><ul>{items}</ul></div>'
    c = p["counts"]
    return f"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>VBT &middot; AI-Infra Recovery Tracker</title>
<style>
:root {{
  color-scheme: light;
  --surface:#fcfcfb; --plane:#f9f9f7; --ink:#0b0b0b; --ink2:#52514e;
  --mut:#898781; --grid:#e1e0d9; --ring:rgba(11,11,11,.10);
  --good:#0ca30c; --warn:#fab219; --serious:#ec835a; --crit:#d03b3b; --blue:#2a78d6;
}}
@media (prefers-color-scheme: dark) {{ :root {{
  color-scheme: dark;
  --surface:#1a1a19; --plane:#0d0d0d; --ink:#ffffff; --ink2:#c3c2b7;
  --mut:#898781; --grid:#2c2c2a; --ring:rgba(255,255,255,.10); --blue:#3987e5;
}} }}
* {{ box-sizing:border-box; }}
body {{ margin:0; background:var(--plane); color:var(--ink);
  font:15px/1.45 system-ui,-apple-system,"Segoe UI",sans-serif; padding:16px; }}
.wrap {{ max-width:860px; margin:0 auto; }}
h1 {{ font-size:1.25rem; margin:0 0 2px; }}
.sub {{ color:var(--mut); font-size:.8rem; margin-bottom:14px; }}
.tiles {{ display:grid; grid-template-columns:repeat(4,1fr); gap:8px; margin-bottom:14px; }}
.tile {{ background:var(--surface); border:1px solid var(--ring); border-radius:10px;
  padding:10px 12px; }}
.tile .v {{ font-size:1.5rem; font-weight:700; }}
.tile .l {{ font-size:.7rem; color:var(--ink2); }}
.card {{ background:var(--surface); border:1px solid var(--ring); border-radius:10px;
  padding:12px 14px; margin-bottom:14px; }}
.card h2 {{ font-size:.95rem; margin:0 0 6px; }}
.trans ul {{ margin:4px 0 0; padding-left:18px; }}
table {{ width:100%; border-collapse:collapse; background:var(--surface);
  border:1px solid var(--ring); border-radius:10px; overflow:hidden; font-size:.85rem; }}
th {{ text-align:left; color:var(--mut); font-weight:600; font-size:.7rem;
  text-transform:uppercase; letter-spacing:.04em; padding:8px 8px;
  border-bottom:1px solid var(--grid); position:sticky; top:0; background:var(--surface); }}
td {{ padding:7px 8px; border-bottom:1px solid var(--grid); }}
tr:last-child td {{ border-bottom:none; }}
.tk {{ font-weight:700; }}
.tk a {{ color:var(--blue); text-decoration:none; border-bottom:1px dotted var(--blue); }}
.num {{ font-variant-numeric:tabular-nums; text-align:right; }}
.mut {{ color:var(--mut); }}
.badge {{ font-size:.72rem; font-weight:700; padding:2px 8px; border-radius:999px;
  white-space:nowrap; }}
.s3 {{ color:var(--good); background:color-mix(in srgb,var(--good) 14%,transparent); }}
.s2 {{ color:var(--warn); background:color-mix(in srgb,var(--warn) 14%,transparent); }}
.s1 {{ color:var(--crit); background:color-mix(in srgb,var(--crit) 14%,transparent); }}
.s4 {{ color:var(--blue); background:color-mix(in srgb,var(--blue) 14%,transparent); }}
.s0 {{ color:var(--mut); }}
.chip {{ font-size:.7rem; padding:1px 7px; border-radius:999px; border:1px solid var(--ring); }}
.chip.quality {{ color:var(--ink2); }}
.chip.spec {{ color:var(--serious); }}
.note {{ color:var(--mut); font-size:.72rem; margin-top:12px; }}
@media (max-width:640px) {{
  .hide-m {{ display:none; }}
  .tiles {{ grid-template-columns:repeat(2,1fr); }}
}}
</style></head><body><div class="wrap">
<h1>AI-Infra Recovery Tracker</h1>
<div class="sub">As of {p["as_of"]} &middot; weekly causal swing structure &middot;
correction = &ge;30% below 52w peak &middot; data: yfinance (delayed/EOD)</div>
<div class="tiles">
<div class="tile"><div class="v">{c["CONFIRMED"]}</div><div class="l">&#9679; Confirmed recovery</div></div>
<div class="tile"><div class="v">{c["Base building"]}</div><div class="l">&#9650; Base building (watch)</div></div>
<div class="tile"><div class="v">{c["Downtrend"]}</div><div class="l">&#9660; Still in downtrend</div></div>
<div class="tile"><div class="v">{c["Recovered"]}</div><div class="l">&#10003; Recovered</div></div>
</div>
{trans_html}
{paper_html}
<table>
<thead><tr><th>Ticker</th><th>Stage</th><th class="num">Price</th>
<th class="num">DD</th><th class="num hide-m">Max DD 26w</th><th class="num">Wks</th>
<th class="hide-m">Since</th><th>Cohort</th><th class="hide-m">Group</th></tr></thead>
<tbody>{"".join(row_html)}</tbody>
</table>
<div class="note">Backtest (10y, 45 names): CONFIRMED entries (Mixed&rarr;Uptrend while
&ge;15% below peak) — median +25% / 71% win at 26w, the only stage with positive excess
vs SMH. Base building was historically too early (negative excess). Quality = profitable
+ FCF-positive. ~70 samples; survivorship &amp; regime caveats apply. Not investment advice.</div>
</div></body></html>"""


if __name__ == "__main__":
    if "--html-only" in sys.argv:
        rerender_html_only()
    else:
        main()
