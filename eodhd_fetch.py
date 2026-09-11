"""EODHD fetch layer for VBT (v0.1, 2026-09-11).

Replaces the Yahoo scrape for wide-universe studies. Runs inside GitHub Actions
(sandbox + local VM cannot reach eodhd.com). PAID "EOD Historical Data — All
World" plan: ~100k calls/day, 1k/min, delisted tickers included.

Token: env EODHD_API_KEY, else a file named .eodhd_token in the private checkout.
Cache: a parquet + universe CSV + meta.json in EODHD_CACHE_DIR (default
        private/eodhd_cache/). Long format: ticker,date,open,high,low,close,
        adj_close,volume. Studies read the cache, never the API directly.

Usage:
  python eodhd_fetch.py --smoke            # 5 tickers, prove the key works
  python eodhd_fetch.py --full             # universe (incl. delisted) since 2009
  python eodhd_fetch.py --topup            # bulk last-day rows since cache end
  python eodhd_fetch.py --full --since 2015-01-01 --max 500   (partial pulls)
Full pull cost: ~1 call/ticker (~8-11k calls). Top-up: 1 call per missing day.
Full re-pull monthly is recommended (corporate-action re-adjustments).
"""
import argparse, json, os, sys, time, io
import urllib.request, urllib.parse, urllib.error
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta
from pathlib import Path
import pandas as pd

BASE = "https://eodhd.com/api"
KEEP_EXCH = {"NYSE", "NASDAQ", "NYSE ARCA", "NYSE MKT", "AMEX", "BATS"}
BENCH = ["SPY", "SMH", "QQQ"]          # ETFs kept as controls
START = "2009-01-01"
WORKERS = 6                             # ~1k/min cap; 6 workers ≈ 300-500/min

def token():
    t = os.environ.get("EODHD_API_KEY", "").strip()
    if t:
        return t
    for p in (Path(".eodhd_token"), Path(__file__).parent / ".eodhd_token"):
        if p.exists():
            return p.read_text().strip()
    sys.exit("eodhd: no token (set EODHD_API_KEY or create .eodhd_token)")

TOKEN = None
def get(path, retries=4, **params):
    params = {**params, "api_token": TOKEN, "fmt": "json"}
    url = f"{BASE}/{path}?{urllib.parse.urlencode(params)}"
    for i in range(retries):
        try:
            with urllib.request.urlopen(url, timeout=60) as r:
                return json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None                       # unknown ticker / no data
            if e.code == 429 or e.code >= 500:
                time.sleep(2 * (i + 1)); continue
            raise
        except Exception:
            time.sleep(2 * (i + 1))
    return None

def cache_dir():
    d = Path(os.environ.get("EODHD_CACHE_DIR", "eodhd_cache")); d.mkdir(parents=True, exist_ok=True)
    return d

# ---------------------------------------------------------------- universe
def universe():
    rows = []
    for delisted in (0, 1):
        data = get("exchange-symbol-list/US", delisted=delisted) or []
        for x in data:
            if x.get("Type") != "Common Stock":
                continue
            if x.get("Exchange", "") not in KEEP_EXCH:
                continue
            rows.append(dict(ticker=x["Code"], name=x.get("Name"), exchange=x.get("Exchange"),
                             isin=x.get("Isin"), delisted=bool(delisted)))
    u = pd.DataFrame(rows).drop_duplicates("ticker")
    u = pd.concat([u, pd.DataFrame([dict(ticker=b, name=b, exchange="ETF", isin=None, delisted=False) for b in BENCH])])
    return u.reset_index(drop=True)

# ---------------------------------------------------------------- history
def eod(ticker, since):
    data = get(f"eod/{ticker}.US", **{"from": since, "period": "d"})
    if not data:
        return None
    df = pd.DataFrame(data)
    if df.empty or "adjusted_close" not in df:
        return None
    df = df.rename(columns={"adjusted_close": "adj_close"})[["date", "open", "high", "low", "close", "adj_close", "volume"]]
    df.insert(0, "ticker", ticker)
    return df

def pull(tickers, since, log=print):
    out, done, t0 = [], 0, time.time()
    with ThreadPoolExecutor(WORKERS) as ex:
        futs = {ex.submit(eod, t, since): t for t in tickers}
        for f in as_completed(futs):
            df = f.result(); done += 1
            if df is not None:
                out.append(df)
            if done % 250 == 0:
                log(f"  {done}/{len(tickers)} tickers, {len(out)} with data, {time.time()-t0:.0f}s")
    return pd.concat(out, ignore_index=True) if out else pd.DataFrame()

def bulk_day(d):
    data = get("eod-bulk-last-day/US", date=d) or []
    if not data:
        return pd.DataFrame()
    df = pd.DataFrame(data)
    df = df.rename(columns={"code": "ticker", "adjusted_close": "adj_close"})
    return df[["ticker", "date", "open", "high", "low", "close", "adj_close", "volume"]]

# ---------------------------------------------------------------- cache io
def load_cache():
    p = cache_dir() / "eod_us.parquet"
    return pd.read_parquet(p) if p.exists() else pd.DataFrame()

def save_cache(df, meta_update):
    d = cache_dir()
    df = df.drop_duplicates(["ticker", "date"], keep="last").sort_values(["ticker", "date"])
    df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
    for c in ("open", "high", "low", "close", "adj_close"):
        df[c] = pd.to_numeric(df[c], errors="coerce").astype("float32")
    df["volume"] = pd.to_numeric(df["volume"], errors="coerce").fillna(0).astype("int64")
    df.to_parquet(d / "eod_us.parquet", index=False, compression="zstd")
    meta = json.loads((d / "meta.json").read_text()) if (d / "meta.json").exists() else {}
    meta.update(meta_update, rows=int(len(df)), tickers=int(df["ticker"].nunique()),
                last_date=str(df["date"].max()), updated_utc=datetime.utcnow().isoformat(timespec="seconds"))
    (d / "meta.json").write_text(json.dumps(meta, indent=1))
    return meta

# ---------------------------------------------------------------- main
def main():
    global TOKEN
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true"); ap.add_argument("--full", action="store_true")
    ap.add_argument("--topup", action="store_true"); ap.add_argument("--since", default=START)
    ap.add_argument("--max", type=int, default=0, help="cap tickers (testing)")
    a = ap.parse_args(); TOKEN = token()

    if a.smoke:
        t = ["MRNA", "NVDA", "SPY", "SMCI", "INTC"]
        df = pull(t, "2026-08-01")
        print(df.groupby("ticker").agg(rows=("date", "size"), last=("date", "max")))
        u = get("exchange-symbol-list/US", delisted=1) or []
        print(f"delisted list ok: {len(u)} entries" if u else "delisted list: EMPTY (plan may not include it)")
        return

    if a.full:
        u = universe(); u.to_csv(cache_dir() / "universe.csv", index=False)
        tickers = u["ticker"].tolist()
        if a.max: tickers = tickers[: a.max]
        print(f"universe: {len(u)} ({int(u.delisted.sum())} delisted); pulling {len(tickers)} since {a.since}")
        df = pull(tickers, a.since)
        meta = save_cache(df, dict(last_full_pull=str(date.today()), since=a.since))
        print("cache:", meta)
        return

    if a.topup:
        cur = load_cache()
        if cur.empty:
            sys.exit("topup: cache empty — run --full first")
        last = datetime.strptime(cur["date"].max(), "%Y-%m-%d").date()
        days = [last + timedelta(i) for i in range(1, (date.today() - last).days + 1)]
        days = [d for d in days if d.weekday() < 5]
        known = set(cur["ticker"].unique()); new = []
        for d in days:
            b = bulk_day(d.isoformat())
            if not b.empty:
                new.append(b[b["ticker"].isin(known)])
            print(f"  {d}: {len(b)} rows")
        if new:
            cur = pd.concat([cur] + new, ignore_index=True)
        meta = save_cache(cur, dict(last_topup=str(date.today())))
        print("cache:", meta)
        return

    ap.print_help()

if __name__ == "__main__":
    main()
