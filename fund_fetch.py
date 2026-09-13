"""EODHD fundamentals fetch for VBT (v0.6, 2026-09-12). Runs in GitHub Actions.

v0.6: EODHD charges 10 API calls per fundamentals request and caps 100k calls/day,
so the universe (~18k) needs two runs. This version checkpoints every CHUNK tickers
into EODHD_CACHE_DIR/fund_parts/, resumes on the next run (skips done tickers),
fetches LISTED names first, stops cleanly after --budget tickers or when the API
starts refusing, and writes fund_done.flag only when every ticker is covered.

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
CHUNK = 500
BUDGET_DEFAULT = 9500      # tickers per run (~95k API calls of the 100k/day cap)
MAX_CONSEC_FAIL = 200      # consecutive empty responses = quota/plan refusal -> stop

def token():
    t = os.environ.get("EODHD_API_KEY", "").strip()
    if t: return t
    for p in (Path(".eodhd_token"), Path(__file__).parent / ".eodhd_token"):
        if p.exists(): return p.read_text().strip()
    sys.exit("no EODHD token")

class QuotaError(Exception):
    pass

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
            if e.code in (402, 403): raise QuotaError(f"HTTP {e.code}: {e.read().decode(errors='replace')[:200]}")
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
    try:
        return extract(ticker, j)
    except Exception as e:                      # never let one odd payload kill the run
        return {"err": f"{ticker}: {type(e).__name__}: {e}"}

def parts_dir(d):
    p = d / "fund_parts"; p.mkdir(exist_ok=True); return p

def done_tickers(d):
    p = parts_dir(d) / "done.txt"
    return set(p.read_text().split()) if p.exists() else set()

def write_part(d, idx, INC, CF, EARN, SNAP, tick):
    p = parts_dir(d)
    for name, rows in (("income", INC), ("cf", CF), ("earn", EARN)):
        df = pd.DataFrame(rows)
        if len(df): df.to_parquet(p / f"{name}_{idx:04d}.parquet", index=False, compression="zstd")
    if SNAP: pd.DataFrame(SNAP).to_csv(p / f"snap_{idx:04d}.csv", index=False)
    with open(p / "done.txt", "a") as f: f.write("\n".join(tick) + "\n")

def assemble(d):
    p = parts_dir(d)
    for name in ("income", "cf", "earn"):
        fs = sorted(p.glob(f"{name}_*.parquet"))
        if fs: pd.concat([pd.read_parquet(f) for f in fs], ignore_index=True).drop_duplicates().to_parquet(d / f"fund_{name}.parquet", index=False, compression="zstd")
    fs = sorted(p.glob("snap_*.csv"))
    if fs: pd.concat([pd.read_csv(f) for f in fs], ignore_index=True).drop_duplicates("ticker", keep="last").to_csv(d / "fund_snapshot.csv", index=False)

def main():
    global TOKEN
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true"); ap.add_argument("--full", action="store_true")
    ap.add_argument("--max", type=int, default=0); ap.add_argument("--listed-only", action="store_true"); ap.add_argument("--budget", type=int, default=BUDGET_DEFAULT)
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
        u = u[~u.ticker.isin(("SPY", "SMH", "QQQ"))].sort_values("delisted")   # listed first
        done = done_tickers(d)
        todo = [t for t in u.ticker.tolist() if t not in done]
        budget = a.max or a.budget
        batch = todo[:budget]
        print(f"fundamentals: universe {len(u)}, done {len(done)}, todo {len(todo)}, this run {len(batch)} (budget {budget})", flush=True)
        t0 = time.time(); ok = 0; empty = 0; consec = 0; errs = []; stopped = None
        for ci in range(0, len(batch), CHUNK):
            chunk = batch[ci:ci + CHUNK]; INC, CF, EARN, SNAP, got = [], [], [], [], []
            try:
                with ThreadPoolExecutor(WORKERS) as ex:
                    for t, r in zip(chunk, ex.map(fetch_one, chunk)):
                        got.append(t)
                        if r is None: empty += 1; consec += 1
                        elif isinstance(r, dict): errs.append(r["err"]); consec = 0
                        else:
                            inc, cf, earn, snap = r; INC += inc; CF += cf; EARN += earn; SNAP.append(snap); ok += 1; consec = 0
            except QuotaError as e:
                stopped = str(e)
            if got: write_part(d, len(done) + ci, INC, CF, EARN, SNAP, got)
            print(f"  {min(ci + CHUNK, len(batch))}/{len(batch)}  ok {ok}  empty {empty}  errors {len(errs)}  {time.time() - t0:.0f}s", flush=True)
            if stopped or consec >= MAX_CONSEC_FAIL:
                stopped = stopped or f"{consec} consecutive empty responses — assuming daily quota reached"; break
        for e in errs[:10]: print("  extract error:", e)
        assemble(d)
        remaining = len(todo) - len(done_tickers(d) - done)
        meta_p = d / "meta.json"; meta = json.loads(meta_p.read_text()) if meta_p.exists() else {}
        meta.update(fundamentals_pull=time.strftime("%Y-%m-%d"), fundamentals_done=len(done_tickers(d)), fundamentals_remaining=remaining, fundamentals_with_data=meta.get("fundamentals_with_data", 0) + ok)
        meta_p.write_text(json.dumps(meta, indent=1))
        if stopped: print("STOPPED:", stopped)
        if remaining <= 0:
            (d / "fund_done.flag").write_text(time.strftime("%Y-%m-%d")); print("fundamentals COMPLETE")
        else:
            print(f"fundamentals PARTIAL — {remaining} tickers remain; re-run 'fund' after the daily quota resets (00:00 UTC)")
        return
    ap.print_help()

if __name__ == "__main__":
    main()
