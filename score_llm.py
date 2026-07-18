"""Score the Phase-2 LLM screen against outcomes (run manually in sessions).

Reads llm_log.jsonl (judgments) + the public repo's data/prices.csv, computes
forward returns for each judged signal, and compares cohorts:
  - GO vs CAUTION vs VETO verdicts (did VETOs actually underperform?)
  - RISK-ON vs NEUTRAL vs RISK-OFF entry days (did the regime call predict?)

Usage (from the public repo root, with private checkout at private/):
  python private/score_llm.py [--horizon-weeks 8]

Sample discipline: verdicts are only scoreable once their horizon has passed;
expect months before n is meaningful. Compare against the unfiltered baseline
(all signals) — the screen adds value only if VETO/RISK-OFF cohorts
underperform GO/RISK-ON by more than chance.
"""
import argparse
import json
from pathlib import Path

import pandas as pd

STATE = Path(__file__).parent
PUB = Path.cwd()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--horizon-weeks", type=int, default=8)
    args = ap.parse_args()
    H = args.horizon_weeks * 5  # trading days

    log_path = STATE / "llm_log.jsonl"
    if not log_path.exists():
        print("no llm_log.jsonl yet — nothing to score")
        return
    judgments = [json.loads(l) for l in log_path.read_text().splitlines() if l.strip()]

    px = pd.read_csv(PUB / "data" / "prices.csv", parse_dates=["date"])
    closes = {t: g.set_index("date")["close"].sort_index() for t, g in px.groupby("ticker")}

    rows = []
    for j in judgments:
        date = pd.Timestamp(j["date"])
        regime = (j.get("regime") or {}).get("regime", "?")
        for tkr, v in (j.get("verdicts") or {}).items():
            s = closes.get(tkr)
            if s is None:
                continue
            idx = s.index[s.index >= date]
            if len(idx) == 0:
                continue
            i = s.index.get_loc(idx[0])
            entry = s.iloc[i]
            fwd = s.iloc[i + H] / entry - 1 if i + H < len(s) else None
            rows.append({"date": j["date"], "ticker": tkr, "regime": regime,
                         "verdict": v.get("verdict"), "fwd": fwd,
                         "resolved": fwd is not None})
    df = pd.DataFrame(rows)
    if df.empty:
        print("no scoreable judgments yet")
        return
    print(f"judgments: {len(df)}  resolved at {args.horizon_weeks}w: {int(df.resolved.sum())}\n")
    res = df[df.resolved]
    if not res.empty:
        for col in ["verdict", "regime"]:
            g = res.groupby(col)["fwd"].agg(["count", "median", "mean",
                                             lambda x: (x > 0).mean()])
            g.columns = ["n", "median", "mean", "win_rate"]
            print(f"== by {col} ==")
            print((g * pd.Series({"n": 1, "median": 100, "mean": 100,
                                  "win_rate": 100})).round(1).to_string(), "\n")
    pending = df[~df.resolved]
    if not pending.empty:
        print("pending (unresolved):",
              ", ".join(f"{r.ticker}({r.verdict})" for r in pending.itertuples()))


if __name__ == "__main__":
    main()
