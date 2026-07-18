"""VBT data relay — fetch daily prices + fundamentals for the AI-infra universe.

Runs on a GitHub Actions runner (open internet). Commits CSVs consumed by the
analysis environment. Full-refresh each run: idempotent, no append bugs.
Data layer is intentionally swappable — replace this file to switch providers
(e.g. Schwab API) without touching downstream consumers of data/*.csv.
"""
import json, time, sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import yfinance as yf

UNIVERSE = {
    # Semis / IP
    "NVDA": "semi", "AMD": "semi", "AVGO": "semi", "ARM": "semi", "MRVL": "semi",
    "MU": "semi", "TSM": "semi", "ASML": "semi", "AMAT": "semi", "LRCX": "semi",
    "KLAC": "semi", "QCOM": "semi", "SNPS": "semi", "CDNS": "semi", "CRDO": "semi",
    "ALAB": "semi", "MPWR": "semi", "ON": "semi", "INTC": "semi",
    # Networking / hardware / storage / cooling
    "ANET": "hw", "SMCI": "hw", "DELL": "hw", "HPE": "hw", "VRT": "hw",
    "CIEN": "hw", "COHR": "hw", "LITE": "hw", "MOD": "hw", "STX": "hw",
    "WDC": "hw", "PSTG": "hw",
    # Power / datacenter buildout
    "VST": "power", "CEG": "power", "TLN": "power", "NRG": "power",
    "GEV": "power", "ETN": "power", "PWR": "power", "POWL": "power",
    # Neocloud / miner-pivot / speculative infra
    "CRWV": "neocloud", "NBIS": "neocloud", "IREN": "neocloud", "APLD": "neocloud",
    "WULF": "neocloud", "CORZ": "neocloud", "CIFR": "neocloud", "HUT": "neocloud",
    "GLXY": "neocloud",
    # Benchmarks
    "SPY": "bench", "SMH": "bench", "QQQ": "bench",
}

FUND_FIELDS = [
    "marketCap", "trailingPE", "forwardPE", "priceToSalesTrailing12Months",
    "profitMargins", "grossMargins", "operatingMargins", "revenueGrowth",
    "earningsGrowth", "totalDebt", "totalCash", "freeCashflow", "operatingCashflow",
    "sharesOutstanding", "floatShares", "shortPercentOfFloat", "beta",
    "fiftyTwoWeekHigh", "fiftyTwoWeekLow",
]

OUT = Path.cwd() / "data"  # runs from public repo root
OUT.mkdir(exist_ok=True)


def fetch_prices() -> pd.DataFrame:
    tickers = list(UNIVERSE)
    px = yf.download(tickers, period="10y", interval="1d",
                     auto_adjust=True, progress=False, group_by="ticker")
    frames = []
    for t in tickers:
        try:
            df = px[t].dropna(how="all")
        except KeyError:
            print(f"WARN no price data for {t}", file=sys.stderr)
            continue
        df = df.reset_index()
        df["ticker"] = t
        df["group"] = UNIVERSE[t]
        frames.append(df[["ticker", "group", "Date", "Open", "High", "Low", "Close", "Volume"]])
    out = pd.concat(frames, ignore_index=True)
    out.columns = [c.lower() for c in out.columns]
    return out


def fetch_fundamentals() -> pd.DataFrame:
    rows = []
    for t in UNIVERSE:
        if UNIVERSE[t] == "bench":
            continue
        try:
            info = yf.Ticker(t).info
            row = {"ticker": t, "group": UNIVERSE[t]}
            row.update({f: info.get(f) for f in FUND_FIELDS})
            row["shortName"] = info.get("shortName")
            rows.append(row)
        except Exception as e:
            print(f"WARN fundamentals failed for {t}: {e}", file=sys.stderr)
        time.sleep(0.5)  # be polite, avoid rate limits
    return pd.DataFrame(rows)


if __name__ == "__main__":
    prices = fetch_prices()
    prices.to_csv(OUT / "prices.csv", index=False)
    print(f"prices.csv: {len(prices)} rows, {prices['ticker'].nunique()} tickers")

    funds = fetch_fundamentals()
    funds.to_csv(OUT / "fundamentals.csv", index=False)
    print(f"fundamentals.csv: {len(funds)} rows")

    meta = {
        "updated_utc": datetime.now(timezone.utc).isoformat(),
        "tickers": len(UNIVERSE),
        "price_rows": int(len(prices)),
        "source": "yfinance",
    }
    (OUT / "meta.json").write_text(json.dumps(meta, indent=2))
    print(json.dumps(meta))
# pipeline v2.1 — engine runs from private checkout
