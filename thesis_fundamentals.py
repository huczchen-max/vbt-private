"""One-off fundamentals fetch for the VBT-2 thesis universe.

Reads thesis_universe.csv (this directory), pulls key fundamentals per
symbol via yfinance, writes thesis_fundamentals.csv. ETFs get market data
only (fund fields don't apply). Run inside GitHub Actions (relay).
"""
import csv
import sys
import time
from pathlib import Path

import yfinance as yf

HERE = Path(__file__).resolve().parent
FIELDS = [
    "shortName", "marketCap", "trailingPE", "forwardPE",
    "totalRevenue", "revenueGrowth", "grossMargins", "operatingMargins",
    "profitMargins", "freeCashflow", "totalCash", "totalDebt",
    "fiftyTwoWeekHigh", "fiftyTwoWeekLow", "currentPrice",
]


def main():
    rows = list(csv.DictReader(open(HERE / "thesis_universe.csv")))
    out = []
    for i, r in enumerate(rows):
        t = r["ticker"].replace("-", ".") if r["ticker"] == "BRK-B" else r["ticker"]
        rec = {"ticker": r["ticker"], "theme": r["theme"]}
        try:
            info = yf.Ticker(t).info
            for f in FIELDS:
                rec[f] = info.get(f)
            if rec.get("currentPrice") is None:  # ETFs
                rec["currentPrice"] = info.get("regularMarketPrice") or info.get("navPrice")
                rec["marketCap"] = rec.get("marketCap") or info.get("totalAssets")
        except Exception as e:
            print(f"WARN {t}: {e}", file=sys.stderr)
        out.append(rec)
        if i % 25 == 0:
            print(f"{i}/{len(rows)}", flush=True)
        time.sleep(0.3)
    w = csv.DictWriter(open(HERE / "thesis_fundamentals.csv", "w", newline=""),
                       fieldnames=["ticker", "theme"] + FIELDS)
    w.writeheader()
    w.writerows(out)
    got = sum(1 for r in out if r.get("marketCap"))
    print(f"thesis_fundamentals.csv: {len(out)} rows, {got} with marketCap")


if __name__ == "__main__":
    main()
