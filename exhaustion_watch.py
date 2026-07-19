"""Exhaustion Watch — mechanical layer (VBT-2; Eric 2026-07-19).

Hypothesis under test (Eric): trends persist, but signs of exhaustion
appear before turns. This layer measures exhaustion MECHANICALLY each
week; the companion exhaustion_llm.py reads narrative extremity. Both
are forward-logged and will be SCORED against subsequent 4-13 week
returns and actual MACROSS/BOTTOM transitions before anything trades
on them. Exhaustion grades regime risk — it is NOT an entry signal.

Per symbol (3y weekly, causal):
  TOP-exhaustion flags (0-5): bearish RSI divergence (price ~new high,
    RSI force lower than at the prior high) · extension above the 40w
    MA in the top decile of the symbol's own 3y history · >=6
    consecutive up-weeks · volume climax (last wk >= 2.5x 26w avg) on
    an up week · weekly RSI > 75.
  BOTTOM-exhaustion flags (0-5): mirrored (bullish divergence, bottom-
    decile extension, down-streaks, climax on a down week, RSI < 25).

Universe: benchmark ETFs + winner top-5 per theme (options universe).
Outputs: exhaustion_watch.json, exhaustion_log.csv (append).
Weekly via tracker.yml (Saturdays).
"""
import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import yfinance as yf

HERE = Path(__file__).resolve().parent
ETFS = ["SPY", "QQQ", "SMH", "GRID", "BOTZ", "ITA", "XLV"]
TOP_N = 5
CHUNK = 20


def universe():
    syms = list(ETFS)
    theme_of = {s: "benchmark" for s in syms}
    try:
        w = json.loads((HERE / "winners.json").read_text())
        for theme, ranked in w.get("themes", {}).items():
            for r in ranked[:TOP_N]:
                if r["ticker"] not in theme_of:
                    syms.append(r["ticker"])
                    theme_of[r["ticker"]] = theme
    except Exception as e:
        print(f"WARN winners.json: {e}", file=sys.stderr)
    return syms, theme_of


def rsi(series, n=14):
    d = series.diff()
    up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    rs = up / dn.replace(0, 1e-9)
    return 100 - 100 / (1 + rs)


def analyze(wk):
    close, vol = wk["Close"], wk["Volume"]
    if len(close) < 80:
        return None
    r = rsi(close)
    ma40 = close.rolling(40).mean()
    ext = close / ma40 - 1
    ext_hist = ext.dropna()
    cur_ext = float(ext.iloc[-1]) if pd.notna(ext.iloc[-1]) else None
    ext_rank = (float((ext_hist < cur_ext).mean() * 100)
                if cur_ext is not None and len(ext_hist) > 60 else None)

    early_c, recent_c = close.iloc[-27:-5], close.iloc[-5:]
    early_r, recent_r = r.iloc[-27:-5], r.iloc[-5:]
    bear_div = bool(float(recent_c.max()) >= float(early_c.max()) * 0.99
                    and float(recent_r.max()) < float(early_r.max()) - 3)
    bull_div = bool(float(recent_c.min()) <= float(early_c.min()) * 1.01
                    and float(recent_r.min()) > float(early_r.min()) + 3)

    ch = close.diff()
    up_streak = down_streak = 0
    for v in reversed(ch.dropna().tolist()):
        if v > 0 and down_streak == 0:
            up_streak += 1
        elif v < 0 and up_streak == 0:
            down_streak += 1
        else:
            break
    vol_ratio = (float(vol.iloc[-1]) / float(vol.tail(26).mean())
                 if float(vol.tail(26).mean()) > 0 else 0)
    up_week = bool(ch.iloc[-1] > 0)
    cur_rsi = float(r.iloc[-1])

    top_flags = {
        "bear_divergence": bear_div,
        "extended_top_decile": bool(ext_rank is not None and ext_rank >= 90),
        "up_streak_6plus": up_streak >= 6,
        "volume_climax_up": bool(vol_ratio >= 2.5 and up_week),
        "rsi_over_75": cur_rsi > 75,
    }
    bot_flags = {
        "bull_divergence": bull_div,
        "extension_bottom_decile": bool(ext_rank is not None and ext_rank <= 10),
        "down_streak_6plus": down_streak >= 6,
        "volume_climax_down": bool(vol_ratio >= 2.5 and not up_week),
        "rsi_under_25": cur_rsi < 25,
    }
    return {
        "close": round(float(close.iloc[-1]), 2),
        "rsi": round(cur_rsi, 1),
        "ext_vs_ma40_pct": round(cur_ext * 100, 1) if cur_ext is not None else None,
        "ext_rank_pct": round(ext_rank, 1) if ext_rank is not None else None,
        "up_streak": up_streak, "down_streak": down_streak,
        "vol_ratio": round(vol_ratio, 2),
        "top_score": sum(top_flags.values()),
        "bottom_score": sum(bot_flags.values()),
        "top_flags": [k for k, v in top_flags.items() if v],
        "bottom_flags": [k for k, v in bot_flags.items() if v],
    }


def main():
    today = datetime.now(timezone.utc).date().isoformat()
    syms, theme_of = universe()
    out = {}
    for i in range(0, len(syms), CHUNK):
        batch = syms[i:i + CHUNK]
        df = yf.download(batch, period="3y", interval="1wk",
                         group_by="ticker", threads=True,
                         progress=False, auto_adjust=True)
        for t in batch:
            try:
                wk = df[t].dropna() if len(batch) > 1 else df.dropna()
                a = analyze(wk)
                if a:
                    a["theme"] = theme_of[t]
                    out[t] = a
            except Exception as e:
                print(f"WARN {t}: {e}", file=sys.stderr)

    (HERE / "exhaustion_watch.json").write_text(json.dumps(
        {"date": today, "symbols": out}, indent=1))
    logp = HERE / "exhaustion_log.csv"
    new = not logp.exists()
    fields = ["date", "ticker", "theme", "close", "rsi", "ext_vs_ma40_pct",
              "ext_rank_pct", "up_streak", "down_streak", "vol_ratio",
              "top_score", "bottom_score", "top_flags", "bottom_flags"]
    with open(logp, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        if new:
            w.writeheader()
        for t, a in out.items():
            w.writerow({"date": today, "ticker": t, **{k: (";".join(v) if
                        isinstance(v, list) else v) for k, v in a.items()}})
    flagged = [(t, a) for t, a in out.items()
               if a["top_score"] >= 2 or a["bottom_score"] >= 2]
    print(f"exhaustion: {len(out)} symbols, {len(flagged)} flagged (score>=2)")
    for t, a in sorted(flagged, key=lambda x: -(x[1]['top_score'] +
                                                x[1]['bottom_score'])):
        side = "TOP" if a["top_score"] >= a["bottom_score"] else "BOTTOM"
        score = max(a["top_score"], a["bottom_score"])
        fl = a["top_flags"] if side == "TOP" else a["bottom_flags"]
        print(f"  {t:6s} {side}-exhaustion {score}/5: {', '.join(fl)}")


if __name__ == "__main__":
    main()
