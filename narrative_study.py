"""GDELT fetcher for the narrative lead/lag study.

For each historical stage-3 signal, pulls daily news TONE and VOLUME timelines
for the company from GDELT (free, no key) over [signal-180d, signal+30d].
Dumps raw series to JSON; analysis happens separately so we fetch only once.
Run inside the GitHub Action (GDELT unreachable from the analysis sandbox).
"""
import argparse, json, time, urllib.parse, urllib.request
from datetime import datetime, timedelta

EVENTS = json.loads(r'''[{"ticker": "ALAB", "date": "2025-10-24", "ret26": 0.2902, "q": true}, {"ticker": "AMAT", "date": "2019-05-31", "ret26": 0.5085, "q": true}, {"ticker": "AMD", "date": "2018-12-07", "ret26": 0.6655, "q": true}, {"ticker": "AMD", "date": "2023-03-10", "ret26": 0.2833, "q": true}, {"ticker": "AMD", "date": "2024-08-16", "ret26": -0.2387, "q": true}, {"ticker": "ANET", "date": "2020-09-11", "ret26": 0.3719, "q": true}, {"ticker": "ANET", "date": "2023-01-06", "ret26": 0.4051, "q": true}, {"ticker": "APLD", "date": "2023-04-21", "ret26": 0.4702, "q": false}, {"ticker": "APLD", "date": "2025-01-10", "ret26": 0.1074, "q": false}, {"ticker": "APLD", "date": "2025-12-26", "ret26": 0.6283, "q": false}, {"ticker": "ARM", "date": "2024-08-16", "ret26": 0.2244, "q": true}, {"ticker": "ARM", "date": "2025-02-28", "ret26": 0.0503, "q": true}, {"ticker": "CIEN", "date": "2020-12-04", "ret26": 0.2774, "q": true}, {"ticker": "CIFR", "date": "2024-02-02", "ret26": 0.6157, "q": false}, {"ticker": "CIFR", "date": "2024-10-11", "ret26": -0.4224, "q": false}, {"ticker": "CIFR", "date": "2025-12-26", "ret26": 0.7077, "q": false}, {"ticker": "COHR", "date": "2022-05-06", "ret26": -0.4829, "q": false}, {"ticker": "COHR", "date": "2023-03-10", "ret26": -0.1386, "q": false}, {"ticker": "COHR", "date": "2023-10-27", "ret26": 0.8889, "q": false}, {"ticker": "CRDO", "date": "2022-09-09", "ret26": -0.288, "q": true}, {"ticker": "CRDO", "date": "2023-03-24", "ret26": 0.8002, "q": true}, {"ticker": "DELL", "date": "2019-12-27", "ret26": 0.0249, "q": true}, {"ticker": "GLXY", "date": "2025-11-28", "ret26": 0.1124, "q": false}, {"ticker": "HPE", "date": "2020-06-19", "ret26": 0.2624, "q": true}, {"ticker": "HUT", "date": "2019-08-30", "ret26": -0.4755, "q": false}, {"ticker": "HUT", "date": "2021-07-30", "ret26": 0.167, "q": false}, {"ticker": "HUT", "date": "2023-04-14", "ret26": -0.1948, "q": false}, {"ticker": "HUT", "date": "2023-08-18", "ret26": -0.16, "q": false}, {"ticker": "HUT", "date": "2024-02-02", "ret26": 0.7033, "q": false}, {"ticker": "HUT", "date": "2024-10-11", "ret26": 0.0375, "q": false}, {"ticker": "INTC", "date": "2025-02-21", "ret26": -0.0028, "q": false}, {"ticker": "IREN", "date": "2023-08-25", "ret26": 0.4785, "q": false}, {"ticker": "IREN", "date": "2024-03-15", "ret26": 0.6435, "q": false}, {"ticker": "IREN", "date": "2024-08-16", "ret26": 0.6324, "q": false}, {"ticker": "LITE", "date": "2023-09-22", "ret26": 0.0963, "q": true}, {"ticker": "LITE", "date": "2025-05-09", "ret26": 2.7014, "q": true}, {"ticker": "MOD", "date": "2017-03-24", "ret26": 0.6545, "q": false}, {"ticker": "MOD", "date": "2019-05-24", "ret26": -0.476, "q": false}, {"ticker": "MOD", "date": "2020-09-11", "ret26": 1.5593, "q": false}, {"ticker": "MPWR", "date": "2022-04-15", "ret26": -0.2418, "q": true}, {"ticker": "MRVL", "date": "2023-04-21", "ret26": 0.2705, "q": true}, {"ticker": "MRVL", "date": "2026-01-09", "ret26": 1.8357, "q": true}, {"ticker": "MU", "date": "2019-04-12", "ret26": 0.0736, "q": true}, {"ticker": "MU", "date": "2023-03-03", "ret26": 0.2445, "q": true}, {"ticker": "NRG", "date": "2022-12-23", "ret26": 0.1118, "q": true}, {"ticker": "NRG", "date": "2023-06-09", "ret26": 0.4299, "q": true}, {"ticker": "ON", "date": "2019-06-07", "ret26": 0.1616, "q": true}, {"ticker": "ON", "date": "2025-09-12", "ret26": 0.2132, "q": true}, {"ticker": "POWL", "date": "2022-01-07", "ret26": -0.1978, "q": true}, {"ticker": "QCOM", "date": "2023-03-10", "ret26": -0.0656, "q": true}, {"ticker": "QCOM", "date": "2023-10-13", "ret26": 0.5945, "q": true}, {"ticker": "SMCI", "date": "2018-03-09", "ret26": 0.0248, "q": false}, {"ticker": "SMCI", "date": "2019-07-19", "ret26": 0.5089, "q": false}, {"ticker": "SMCI", "date": "2024-05-31", "ret26": -0.5839, "q": false}, {"ticker": "SMCI", "date": "2025-03-28", "ret26": 0.3374, "q": false}, {"ticker": "SMCI", "date": "2025-09-05", "ret26": -0.2252, "q": false}, {"ticker": "SNPS", "date": "2025-10-17", "ret26": 0.0043, "q": true}, {"ticker": "STX", "date": "2020-07-17", "ret26": 0.2839, "q": true}, {"ticker": "VRT", "date": "2022-12-16", "ret26": 0.7154, "q": true}, {"ticker": "WDC", "date": "2019-05-03", "ret26": 0.0813, "q": true}, {"ticker": "WDC", "date": "2020-06-19", "ret26": 0.1982, "q": true}, {"ticker": "WDC", "date": "2022-02-11", "ret26": -0.057, "q": true}, {"ticker": "WDC", "date": "2023-07-21", "ret26": 0.43, "q": true}, {"ticker": "WULF", "date": "2020-06-12", "ret26": 0.9841, "q": false}, {"ticker": "WULF", "date": "2024-05-03", "ret26": 1.8311, "q": false}, {"ticker": "WULF", "date": "2025-08-01", "ret26": 1.8088, "q": false}]''')

QUERY = json.loads(r'''{"ALAB": "\"Astera Labs\"", "AMAT": "\"Applied Materials\"", "AMD": "\"Advanced Micro Devices\" OR \"AMD chip\"", "ANET": "\"Arista Networks\"", "APLD": "\"Applied Digital\"", "ARM": "\"Arm Holdings\"", "CIEN": "\"Ciena\"", "CIFR": "\"Cipher Mining\"", "COHR": "\"Coherent Corp\" OR \"Coherent Inc\"", "CRDO": "\"Credo Technology\"", "DELL": "\"Dell Technologies\"", "GLXY": "\"Galaxy Digital\"", "HPE": "\"Hewlett Packard Enterprise\"", "HUT": "\"Hut 8\"", "INTC": "\"Intel\"", "IREN": "\"IREN Limited\" OR \"Iris Energy\"", "LITE": "\"Lumentum\"", "MOD": "\"Modine Manufacturing\"", "MPWR": "\"Monolithic Power\"", "MRVL": "\"Marvell\"", "MU": "\"Micron Technology\"", "NRG": "\"NRG Energy\"", "ON": "\"ON Semiconductor\" OR \"onsemi\"", "POWL": "\"Powell Industries\"", "QCOM": "\"Qualcomm\"", "SMCI": "\"Super Micro Computer\" OR \"Supermicro\"", "SNPS": "\"Synopsys\"", "STX": "\"Seagate\"", "VRT": "\"Vertiv\"", "WDC": "\"Western Digital\"", "WULF": "\"TeraWulf\""}''')

BASE = "https://api.gdeltproject.org/api/v2/doc/doc"

def fetch(query, mode, start, end):
    if " OR " in query and not query.startswith("("):
        query = "(" + query + ")"
    q = {"query": query + " sourcelang:english", "mode": mode,
         "startdatetime": start, "enddatetime": end,
         "format": "json", "timelinesmooth": 7}
    url = BASE + "?" + urllib.parse.urlencode(q)
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (research script; contact: none)"})
    with urllib.request.urlopen(req, timeout=60) as r:
        raw = r.read().decode()
    return json.loads(raw)

def fetch_retry(query, mode, start, end, tries=5):
    delay = 8
    for k in range(tries):
        try:
            return fetch(query, mode, start, end)
        except Exception as ex:
            if "429" in str(ex) and k < tries - 1:
                time.sleep(delay)
                delay = min(delay * 2, 90)
                continue
            raise


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="gdelt_raw.json")
    ap.add_argument("--max-events", type=int, default=0,
                    help="fetch at most N missing events then exit (trickle mode)")
    args = ap.parse_args()
    # resume: keep events that already have tone data
    done = {}
    try:
        for r in json.load(open(args.out)):
            if r.get("tone"):
                done[(r["ticker"], r["date"])] = r
        print(f"resuming: {len(done)} events already complete", flush=True)
    except Exception:
        pass
    out = list(done.values())
    fetched_now = 0
    for i, e in enumerate(EVENTS):
        t = e["ticker"]
        if (t, e["date"]) in done:
            continue
        if args.max_events and fetched_now >= args.max_events:
            break
        fetched_now += 1
        d = datetime.fromisoformat(e["date"])
        start = (d - timedelta(days=180)).strftime("%Y%m%d") + "000000"
        end = (d + timedelta(days=30)).strftime("%Y%m%d") + "000000"
        rec = dict(e)
        for mode, key in [("timelinetone", "tone"), ("timelinevolraw", "vol")]:
            try:
                data = fetch_retry(QUERY[t], mode, start, end)
                tl = data.get("timeline", [{}])[0].get("data", [])
                rec[key] = [[p.get("date", "")[:8], p.get("value")] for p in tl]
            except Exception as ex:
                rec[key] = []
                rec[key + "_err"] = str(ex)[:120]
            time.sleep(10)
        out.append(rec)
        json.dump(out, open(args.out, "w"))  # checkpoint every event
        if (i + 1) % 5 == 0:
            print(f"{i+1}/{len(EVENTS)} events fetched", flush=True)
    n_ok = sum(1 for r in out if r.get("tone"))
    print(f"done: {n_ok}/{len(out)} events with tone data -> {args.out}")

if __name__ == "__main__":
    main()
