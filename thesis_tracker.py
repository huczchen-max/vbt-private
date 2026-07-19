"""Phase 3 thesis tracker — theme health + ladder status per name +
review ledger (VBT-2; Eric 2026-07-19).

Per name (weekly, causal — same engines as everything else):
  DOOR   — ENTRY-BOTTOM (confirmed bottom within 13w) |
           ENTRY-MACROSS (13w/52w cross within 4w) |
           IN-TREND (L1 intact) | BROKEN (not intact)
  plus structure state, drawdown, distance to MA52.

Theme health: benchmark ETF's own ladder + breadth (% of theme names
L1-intact, % weekly Uptrend) + the adopted ETF COMBO brake status
(Downtrend AND close < MA52 -> BRAKE ON).

Ledger (thesis_ledger.csv, append-only): every week-over-week
transition — TREND-BROKEN (review trigger, NOT a sale), TREND-REPAIRED,
NEW-BOTTOM, BRAKE-ON/OFF (ETFs) — with date and price, so reviews and
brakes can be scored against what followed.

Output: thesis_state.json (private). Weekly via tracker.yml (Saturdays).
"""
import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import yfinance as yf

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from breakout_radar import causal_trend_history, analyze  # noqa: E402

BENCH = {"ai": "SMH", "grid": "GRID", "robotics": "BOTZ",
         "defense": "ITA", "health": "XLV", "outlier": "QQQ"}
CHUNK = 100


def ladder(wk):
    """Ladder status dict for one symbol's 2y weekly OHLCV."""
    close = wk["Close"]
    ma13 = close.rolling(13).mean()
    ma52 = close.rolling(52).mean()
    states = causal_trend_history(wk["High"], wk["Low"])
    r = analyze(wk) or {}
    intact = bool(pd.notna(ma52.iloc[-1])
                  and float(ma13.iloc[-1]) > float(ma52.iloc[-1]))
    cross_recent = False
    for j in range(max(1, len(wk) - 4), len(wk)):
        if (pd.notna(ma52.iloc[j]) and pd.notna(ma52.iloc[j - 1])
                and float(ma13.iloc[j]) > float(ma52.iloc[j])
                and float(ma13.iloc[j - 1]) <= float(ma52.iloc[j - 1])):
            cross_recent = True
    state = str(states.iloc[-1])
    if r.get("bottom"):
        door = "ENTRY-BOTTOM"
    elif cross_recent:
        door = "ENTRY-MACROSS"
    elif intact:
        door = "IN-TREND"
    else:
        door = "BROKEN"
    below_ma52 = bool(pd.notna(ma52.iloc[-1])
                      and float(close.iloc[-1]) < float(ma52.iloc[-1]))
    return {
        "door": door, "intact": intact, "state": state,
        "close": round(float(close.iloc[-1]), 2),
        "dd_pct": r.get("dd_pct"),
        "vs_ma52_pct": round((float(close.iloc[-1]) / float(ma52.iloc[-1]) - 1)
                             * 100, 1) if pd.notna(ma52.iloc[-1]) else None,
        "bottom_date": r.get("bottom_date"),
        "brake_on": bool(state == "Downtrend" and below_ma52),
    }


def main():
    rows = list(csv.DictReader(open(HERE / "thesis_universe.csv")))
    today = datetime.now(timezone.utc).date().isoformat()
    prev_p = HERE / "thesis_state.json"
    prev = {}
    if prev_p.exists():
        try:
            prev = {k: v for k, v in
                    json.loads(prev_p.read_text()).get("names", {}).items()}
        except Exception:
            prev = {}

    tickers = [r["ticker"] for r in rows]
    theme_of = {r["ticker"]: r["theme"] for r in rows}
    data = {}
    for i in range(0, len(tickers), CHUNK):
        batch = tickers[i:i + CHUNK]
        df = yf.download(batch, period="2y", interval="1wk",
                         group_by="ticker", threads=True,
                         progress=False, auto_adjust=True)
        for t in batch:
            try:
                sub = df[t].dropna() if len(batch) > 1 else df.dropna()
                if len(sub) >= 60:
                    data[t] = sub
            except Exception:
                continue
        print(f"prices {min(i + CHUNK, len(tickers))}/{len(tickers)}",
              flush=True)

    names, events = {}, []
    for t, wk in data.items():
        try:
            st = ladder(wk)
        except Exception as e:
            print(f"WARN {t}: {e}", file=sys.stderr)
            continue
        st["theme"] = theme_of[t]
        names[t] = st
        p = prev.get(t, {})
        if p:
            if p.get("intact") and not st["intact"]:
                events.append((t, "TREND-BROKEN"))
            elif st["intact"] and not p.get("intact"):
                events.append((t, "TREND-REPAIRED"))
            if st["door"] == "ENTRY-BOTTOM" and p.get("door") != "ENTRY-BOTTOM":
                events.append((t, "NEW-BOTTOM"))
            if theme_of[t] == "etf":
                if st["brake_on"] and not p.get("brake_on"):
                    events.append((t, "BRAKE-ON"))
                elif p.get("brake_on") and not st["brake_on"]:
                    events.append((t, "BRAKE-OFF"))

    theme_health = {}
    for theme, b in BENCH.items():
        members = [t for t, s in names.items()
                   if s["theme"] == theme]
        etf = names.get(b, {})
        n = len(members)
        theme_health[theme] = {
            "benchmark": b,
            "etf_door": etf.get("door"), "etf_state": etf.get("state"),
            "etf_dd_pct": etf.get("dd_pct"),
            "etf_brake_on": etf.get("brake_on"),
            "breadth_intact_pct": round(
                100 * sum(1 for t in members if names[t]["intact"]) / n, 1)
            if n else None,
            "breadth_uptrend_pct": round(
                100 * sum(1 for t in members
                          if names[t]["state"] == "Uptrend") / n, 1)
            if n else None,
            "names": n,
        }

    state = {"date": today,
             "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
             "theme_health": theme_health, "names": names,
             "events": [{"ticker": t, "event": e} for t, e in events]}
    prev_p.write_text(json.dumps(state, indent=1))

    logp = HERE / "thesis_ledger.csv"
    new = not logp.exists()
    with open(logp, "a", newline="") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["date", "ticker", "theme", "event", "close",
                        "dd_pct", "state"])
        for t, e in events:
            s = names[t]
            w.writerow([today, t, s["theme"], e, s["close"],
                        s["dd_pct"], s["state"]])

    doors = {}
    for s in names.values():
        doors[s["door"]] = doors.get(s["door"], 0) + 1
    print(f"tracked {len(names)} names; doors {doors}; "
          f"events this run {len(events)}")
    for th, h in theme_health.items():
        print(f"  {th:9s} etf={h['etf_door']}/{h['etf_state']} "
              f"breadth intact {h['breadth_intact_pct']}% "
              f"uptrend {h['breadth_uptrend_pct']}%")


if __name__ == "__main__":
    main()
