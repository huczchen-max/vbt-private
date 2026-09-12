"""EODHD fundamentals fetch for VBT (v0.5, 2026-09-12). Runs in GitHub Actions.

Pulls, per ticker, only the pieces the base study needs and stores them as
point-in-time tables in EODHD_CACHE_DIR:
  fund_income.parquet   ticker, q_date, filing_date, revenue, gross_profit, op_income, net_income
  fund_cf.parquet       ticker, q_date, filing_date, cfo, capex, fcf
  fund_earn.parquet     ticker, report_date, q_date, eps_actual, eps_estimate, surprise_pct
  fund_snapshot.csv     ticker, sector, industry, mkt_cap, short_ratio, short_pct_float,
                        shares_short, shares_short_prior  (CURRENT values only — EODHD
                        keeps no short-interest history; usable for the live screen, not backtests)
Cost: 1 call per ticker (universe.csv from eodhd_fetch.py --full); ~18k calls.
Usage: python fund_fetch.py --smoke | --full [--max N] [--listed-only]
"""
import argparse, json, os, sys, time
import urllib.request, urllib.parse, urllib.error
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import pandas as pd

BASE = "https://eodhd.com/api"
FILTER = ",".join(["General::Code", "General::Sector", "General::Industry", "General::IsDelisted",
                   "Highlights::MarketCapitalization", "SharesStats",
                   "Earnings::History", "Financials::Income_Statement::quarterly", "Financials::Cash_Flow::quarterly"])
WORKERS = 6

def token():
    t = os.environ.get("EODHD_API_KEY", "").strip()
    if t: return t
    for p in (Path(".eodhd_token"), Path(__file__).parent / ".eodhd_token"):
        if p.exists(): return p.read_text().strip()
    sys.exit("no EODHD token")

TOKEN = None
def get(path, retries=4, **params):
    params = {**params, "api_token": TOKEN, "fmt": "json"}
    url = f"{BASE}/{path}?{urllib.parse.urlencode(params)}"
    for i in range(retries):
        try:
            with urllib.request.urlopen(url, timeout=90) as r:
                return json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            if e.code == 404: return None
            if e.code == 429 or e.code >= 500: time.sleep(2 * (i + 1)); continue
            return None
        except Exception:
            time.sleep(2 * (i + 1))
    return None

def cache_dir():
    d = Path(os.environ.get("EODHD_CACHE_DIR", "eodhd_cache")); d.mkdir(parents=True, exist_ok=True); return d

def num(x):
    try: return float(x) if x is not None else None
    except (TypeError, ValueError): return None

def extract(ticker, j):
    """Flatten one fundamentals JSON into row lists."""
    inc, cf, earn = [], [], []
    fin = (j.get("Financials") or {})
    for q, v in ((fin.get("Income_Statement") or {}).get("quarterly") or {}).items():
        inc.append(dict(ticker=ticker, q_date=v.get("date") or q, filing_date=v.get("filing_date"),
                        revenue=num(v.get("totalRevenue")), gross_profit=num(v.get("grossProfit")),
                        op_income=num(v.get("operatingIncome")), net_income=num(v.get("netIncome"))))
    for q, v in ((fin.get("Cash_Flow") or {}).get("quarterly") or {}).items():
        cfo = num(v.get("totalCashFromOperatingActivities")); capex = num(v.get("capitalExpenditures"))
        cf.append(dict(ticker=ticker, q_date=v.get("date") or q, filing_date=v.get("filing_date"), cfo=cfo, capex=capex,
                       fcf=num(v.get("freeCashFlow")) if v.get("freeCashFlow") is not None else (cfo - abs(capex) if cfo is not None and capex is not None else None)))
    for d, v in ((j.get("Earnings") or {}).get("History") or {}).items():
        earn.append(dict(ticker=ticker, report_date=v.get("reportDate"), q_date=v.get("date") or d,
                         eps_actual=num(v.get("epsActual")), eps_estimate=num(v.get("epsEstimate")), surprise_pct=num(v.get("surprisePercent"))))
    g = j.get("General") or {}; ss = j.get("SharesStats") or {}; hl = j.get("Highlights") or {}
    snap = dict(ticker=ticker, sector=g.get("Sector"), industry=g.get("Industry"), is_delisted=g.get("IsDelisted"),
                mkt_cap=num(hl.get("MarketCapitalization")), short_ratio=num(ss.get("ShortRatio")),
                short_pct_float=num(ss.get("ShortPercentFloat") if ss.get("ShortPercentFloat") is not None else ss.get("ShortPercent")),
                shares_short=num(ss.get("SharesShort")), shares_short_prior=num(ss.get("SharesShortPriorMonth")))
    return inc, cf, earn, snap

def fetch_one(ticker):
    j = get(f"fundamentals/{ticker}.US", filter=FILTER)
    if not j or not isinstance(j, dict): return None
    return extract(ticker, j)

def main():
    global TOKEN
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true"); ap.add_argument("--full", action="store_true")
    ap.add_argument("--max", type=int, default=0); ap.add_argument("--listed-only", action="store_true")
    a = ap.parse_args(); TOKEN = token(); d = cache_dir()

    if a.smoke:
        j = get("fundamentals/MRNA.US", filter=FILTER)
        if not j: sys.exit("smoke: no fundamentals returned for MRNA — check plan/token")
        print("top-level keys:", list(j.keys()))
        inc, cf, earn, snap = extract("MRNA", j)
        print("income rows:", len(inc), "sample:", inc[:2]); print("cf rows:", len(cf), "sample:", cf[:1])
        print("earnings rows:", len(earn), "sample:", earn[:2]); print("snapshot:", snap)
        q = (j.get("Financials") or {}).get("Income_Statement", {}).get("quarterly", {})
        if q:
            k = next(iter(q)); print("raw income fields:", sorted(q[k].keys())[:60])
        return

    if a.full:
        u = pd.read_csv(d / "universe.csv")
        if a.listed_only: u = u[u.delisted == False]
        tickers = [t for t in u.ticker.tolist() if t not in ("SPY", "SMH", "QQQ")]
        if a.max: tickers = tickers[: a.max]
        print(f"fundamentals: {len(tickers)} tickers", flush=True)
        INC, CF, EARN, SNAP = [], [], [], []; done = 0; t0 = time.time(); ok = 0
        with ThreadPoolExecutor(WORKERS) as ex:
            futs = {ex.submit(fetch_one, t): t for t in tickers}
            for f in as_completed(futs):
                r = f.result(); done += 1
                if r:
                    inc, cf, earn, snap = r; INC += inc; CF += cf; EARN += earn; SNAP.append(snap); ok += 1
                if done % 500 == 0: print(f"  {done}/{len(tickers)} ({ok} with data), {time.time()-t0:.0f}s", flush=True)
        for name, rows in (("fund_income", INC), ("fund_cf", CF), ("fund_earn", EARN)):
            df = pd.DataFrame(rows)
            if len(df): df.to_parquet(d / f"{name}.parquet", index=False, compression="zstd")
            print(name, len(df))
        pd.DataFrame(SNAP).to_csv(d / "fund_snapshot.csv", index=False); print("fund_snapshot", len(SNAP))
        meta_p = d / "meta.json"; meta = json.loads(meta_p.read_text()) if meta_p.exists() else {}
        meta["fundamentals_pull"] = time.strftime("%Y-%m-%d"); meta["fundamentals_tickers"] = ok; meta_p.write_text(json.dumps(meta, indent=1))
        return
    ap.print_help()

if __name__ == "__main__":
    main()
