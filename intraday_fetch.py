"""EODHD 1-hour intraday pull for the multi-scale divergence screen (v0.1, 2026-09-22).

Regular session only (09:30-16:00 New York), DAYS calendar days back (default 200
~ 135 trading days ~ 900 hourly bars: enough for LMAX = 156 bars plus RSI warm-up).
One request per ticker. EODHD bills intraday requests at a multiple of a plain
EOD call (documented as 5; ASSUMPTION — the run logs the /user quota counter
before and after so the true cost is recorded in the log).
Resumable: per-chunk parts in eodhd_cache/intraday_parts/, assembled into
eodhd_cache/intraday_1h.parquet (ticker, dt [UTC ISO], close, volume) + meta.
Tickers already in the parquet with bars within the last 2 days are skipped.

Usage: python intraday_fetch.py --needed private/div_screen/intraday_needed.txt [--budget 4000] [--days 200] [--smoke]
"""
import argparse, json, os, sys, time
import urllib.request, urllib.parse, urllib.error
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from pathlib import Path
import pandas as pd

BASE = "https://eodhd.com/api"
WORKERS = 6; CHUNK = 250; BUDGET_DEFAULT = 4000; MAX_CONSEC_FAIL = 100

class QuotaError(Exception):
    pass

def token():
    t = os.environ.get("EODHD_API_KEY", "").strip()
    if t: return t
    for p in (Path(".eodhd_token"), Path(__file__).parent / ".eodhd_token"):
        if p.exists(): return p.read_text().strip()
    sys.exit("eodhd: no token (set EODHD_API_KEY or create .eodhd_token)")

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

def quota():
    try:
        u = get("user") or {}
        return dict(used=u.get("apiRequests"), limit=u.get("dailyRateLimit"), date=u.get("apiRequestsDate"))
    except QuotaError as ex:
        return dict(error=str(ex))

def fetch_one(t, t0, t1):
    data = get(f"intraday/{t}.US", interval="1h", **{"from": int(t0), "to": int(t1)})
    if not data or not isinstance(data, list): return t, None
    df = pd.DataFrame(data)
    if df.empty or "timestamp" not in df or "close" not in df: return t, None
    dt = pd.to_datetime(pd.to_numeric(df["timestamp"], errors="coerce"), unit="s", utc=True)
    ny = dt.dt.tz_convert("America/New_York"); mins = ny.dt.hour * 60 + ny.dt.minute
    vol = pd.to_numeric(df.get("volume"), errors="coerce").fillna(0)
    keep = (mins >= 570) & (ny.dt.hour < 16) & (vol > 0) & pd.to_numeric(df["close"], errors="coerce").notna()
    out = pd.DataFrame(dict(ticker=t, dt=dt[keep].dt.strftime("%Y-%m-%dT%H:%M:%SZ"), close=pd.to_numeric(df["close"], errors="coerce")[keep].astype("float32"), volume=vol[keep].astype("int64")))
    return t, (out if len(out) else None)

def parts_dir(d):
    p = d / "intraday_parts"; p.mkdir(exist_ok=True); return p

def assemble(d, new_parts, existing):
    frames = [existing] if existing is not None and len(existing) else []
    frames += [pd.read_parquet(f) for f in sorted(parts_dir(d).glob("part_*.parquet"))]
    if not frames: return None
    df = pd.concat(frames, ignore_index=True).drop_duplicates(["ticker", "dt"], keep="last").sort_values(["ticker", "dt"])
    df.to_parquet(d / "intraday_1h.parquet", index=False, compression="zstd")
    for f in parts_dir(d).glob("part_*.parquet"): f.unlink()
    return df

def main():
    global TOKEN
    ap = argparse.ArgumentParser()
    ap.add_argument("--needed", required=True); ap.add_argument("--budget", type=int, default=BUDGET_DEFAULT)
    ap.add_argument("--days", type=int, default=200); ap.add_argument("--smoke", action="store_true")
    a = ap.parse_args(); TOKEN = token(); d = cache_dir()
    need = [x.strip() for x in open(a.needed) if x.strip()]
    if a.smoke: need = need[:5]
    existing = pd.read_parquet(d / "intraday_1h.parquet") if (d / "intraday_1h.parquet").exists() else None
    fresh = set()
    if existing is not None and len(existing):
        last = existing.groupby("ticker").dt.max()
        cutoff = (datetime.now(timezone.utc) - timedelta(days=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
        fresh = set(last[last >= cutoff].index)
    todo = [t for t in need if t not in fresh][: a.budget]
    q0 = quota(); print(f"intraday: needed {len(need)}, already fresh {len(need) - len([t for t in need if t not in fresh])}, pulling {len(todo)} (budget {a.budget}); quota before: {q0}", flush=True)
    now = datetime.now(timezone.utc); t1 = int(now.timestamp()); t0 = int((now - timedelta(days=a.days)).timestamp())
    ok = empty = 0; consec = 0; stopped = None; t_start = time.time(); part_i = 0
    for ci in range(0, len(todo), CHUNK):
        chunk = todo[ci:ci + CHUNK]; got = []
        try:
            with ThreadPoolExecutor(WORKERS) as ex:
                futs = [ex.submit(fetch_one, t, t0, t1) for t in chunk]
                for f in as_completed(futs):
                    t, df = f.result()
                    if df is None: empty += 1; consec += 1
                    else: got.append(df); ok += 1; consec = 0
        except QuotaError as ex:
            stopped = str(ex)
        if got:
            pd.concat(got, ignore_index=True).to_parquet(parts_dir(d) / f"part_{part_i:04d}.parquet", index=False); part_i += 1
        print(f"  {min(ci + CHUNK, len(todo))}/{len(todo)}  ok {ok}  empty {empty}  {time.time() - t_start:.0f}s", flush=True)
        if stopped or consec >= MAX_CONSEC_FAIL:
            print(f"STOPPED: {stopped or f'{consec} consecutive empty responses (plan may not include intraday, or symbols unknown)'}", flush=True); break
    df = assemble(d, part_i, existing)
    q1 = quota()
    meta = dict(updated_utc=now.isoformat(timespec="seconds"), tickers=int(df.ticker.nunique()) if df is not None else 0, rows=int(len(df)) if df is not None else 0,
                pulled=len(todo), ok=ok, empty=empty, stopped=stopped, quota_before=q0, quota_after=q1, days=a.days)
    (d / "intraday_meta.json").write_text(json.dumps(meta, indent=1, default=str))
    try:
        cost = (q1.get("used") or 0) - (q0.get("used") or 0)
        print(f"quota after: {q1}; calls consumed this run: {cost} for {ok + empty} requests -> {cost / max(1, ok + empty):.1f} calls/request", flush=True)
    except Exception: pass
    print(f"intraday parquet: {meta['tickers']} tickers, {meta['rows']} rows; status={'ok' if not stopped else 'PARTIAL'}", flush=True)

if __name__ == "__main__":
    main()
