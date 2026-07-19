"""Breakout Radar — market-wide discovery screen (VBT-2).

Scans ALL US-listed common stocks for DEFINITIVE 52-week breakouts:
  - first weekly close >1% above the prior 52-week closing high
  - after >=26 weeks without a new high (a real base, not a grinding trend)
  - price >= $5, avg weekly dollar volume >= $25M, >=53 weeks of history

Hits are then enriched via yfinance .info and filtered:
  - market cap >= $1B  (Eric's criterion 1)
  - QUALITY tag: (profitable OR FCF-positive) AND revenue growth >= 0
Non-quality hits are logged too (tagged SPEC) so the filter itself can be
scored later — but the radar's headline list is the quality set.

Outputs (private repo):
  radar_latest.json — this run's hits with fundamentals
  radar_log.csv     — append-only history of every hit (for backtesting)

Run weekly inside GitHub Actions (radar.yml). Runtime ~15 min.
"""
import csv
import io
import json
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import yfinance as yf

HERE = Path(__file__).resolve().parent
MARGIN = 1.01          # close must exceed prior 52w high by 1%
BASE_WEEKS = 26        # min weeks since the last 52w high
MIN_PRICE = 5.0
MIN_WK_DOLLAR_VOL = 25e6
MIN_CAP = 1e9
CHUNK = 200


def get_symbols():
    """All US-listed common stocks from the Nasdaq Trader symbol directory."""
    urls = [
        "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt",
        "https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt",
    ]
    syms = []
    for u in urls:
        with urllib.request.urlopen(u, timeout=60) as r:
            text = r.read().decode()
        rows = list(csv.DictReader(io.StringIO(text), delimiter="|"))
        for row in rows:
            s = (row.get("Symbol") or row.get("ACT Symbol") or "").strip()
            if not s or "File Creation" in s:
                continue
            if row.get("ETF", "N") == "Y" or row.get("Test Issue", "N") == "Y":
                continue
            # skip warrants/units/preferred/rights (suffix conventions)
            if any(c in s for c in "$.=+^~"):
                continue
            if len(s) == 5 and s[-1] in "WRUP":  # NASDAQ suffix codes
                continue
            syms.append(s)
    syms = sorted(set(syms))
    print(f"symbol directory: {len(syms)} common-stock symbols")
    return syms


def scan(symbols):
    """Batch-download 1y weekly closes and find definitive 52w breakouts."""
    hits = []
    for i in range(0, len(symbols), CHUNK):
        batch = symbols[i:i + CHUNK]
        try:
            df = yf.download(batch, period="1y", interval="1wk",
                             group_by="ticker", threads=True,
                             progress=False, auto_adjust=True)
        except Exception as e:
            print(f"WARN batch {i}: {e}", file=sys.stderr)
            continue
        for t in batch:
            try:
                sub = df[t].dropna() if len(batch) > 1 else df.dropna()
                closes = sub["Close"]
                vols = sub["Volume"]
                if len(closes) < 53:
                    continue
                cur = float(closes.iloc[-1])
                if cur < MIN_PRICE:
                    continue
                if float((closes * vols).tail(13).mean()) < MIN_WK_DOLLAR_VOL:
                    continue
                prior = closes.iloc[:-1]
                hi52 = float(prior.tail(52).max())
                hi_recent = float(prior.tail(BASE_WEEKS).max())
                # breakout: current close clears 52w high by margin,
                # and no new high was set in the last BASE_WEEKS weeks
                # (the 52w max is older than the base window)
                if cur > hi52 * MARGIN and hi_recent < hi52 * 0.999:
                    hits.append({"ticker": t, "close": round(cur, 2),
                                 "prior_52w_high": round(hi52, 2),
                                 "breakout_pct": round((cur / hi52 - 1) * 100, 1)})
            except Exception:
                continue
        if (i // CHUNK) % 5 == 0:
            print(f"scanned {i + len(batch)}/{len(symbols)}, hits so far: {len(hits)}",
                  flush=True)
    return hits


def enrich(hits):
    """Fetch fundamentals for hits; apply $1B cap + quality filter."""
    out = []
    for h in hits:
        try:
            info = yf.Ticker(h["ticker"]).info
        except Exception as e:
            print(f"WARN info {h['ticker']}: {e}", file=sys.stderr)
            info = {}
        cap = info.get("marketCap") or 0
        if cap < MIN_CAP:
            continue
        pm = info.get("profitMargins")
        fcf = info.get("freeCashflow")
        rg = info.get("revenueGrowth")
        quality = (((pm or 0) > 0 or (fcf or 0) > 0)
                   and (rg is None or rg >= 0))
        h.update({
            "name": (info.get("shortName") or "").strip(),
            "sector": info.get("sector", ""),
            "industry": info.get("industry", ""),
            "mkt_cap_B": round(cap / 1e9, 1),
            "pe": info.get("trailingPE"),
            "fwd_pe": info.get("forwardPE"),
            "rev_growth_pct": round(rg * 100, 1) if rg is not None else None,
            "profit_margin_pct": round(pm * 100, 1) if pm is not None else None,
            "fcf_B": round(fcf / 1e9, 2) if fcf else None,
            "tag": "QUALITY" if quality else "SPEC",
        })
        out.append(h)
    return out


def main():
    today = datetime.now(timezone.utc).date().isoformat()
    symbols = get_symbols()
    raw = scan(symbols)
    print(f"price-structure breakouts: {len(raw)}")
    hits = enrich(raw)
    hits.sort(key=lambda h: (h["tag"] != "QUALITY", -h["mkt_cap_B"]))
    q = [h for h in hits if h["tag"] == "QUALITY"]
    print(f">= $1B hits: {len(hits)} ({len(q)} QUALITY)")

    (HERE / "radar_latest.json").write_text(json.dumps(
        {"date": today, "criteria": {"margin": MARGIN, "base_weeks": BASE_WEEKS,
                                     "min_cap_B": MIN_CAP / 1e9},
         "hits": hits}, indent=1, default=str))

    logp = HERE / "radar_log.csv"
    fields = ["date", "ticker", "name", "tag", "close", "prior_52w_high",
              "breakout_pct", "mkt_cap_B", "sector", "industry", "pe",
              "fwd_pe", "rev_growth_pct", "profit_margin_pct", "fcf_B"]
    new = not logp.exists()
    with open(logp, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        if new:
            w.writeheader()
        for h in hits:
            w.writerow({"date": today, **h})
    for h in q[:20]:
        print(f"  {h['tag']:7s} {h['ticker']:6s} {h['name'][:28]:28s} "
              f"cap {h['mkt_cap_B']}B  +{h['breakout_pct']}% over 52w high")


if __name__ == "__main__":
    main()
