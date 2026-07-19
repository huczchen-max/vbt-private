"""Phase 4c — options regime->strategy engine, self-journaled paper
(VBT-2; Eric 2026-07-19). PROPOSES, never executes.

Weekly pipeline (Saturdays, after tracker/winners/exhaustion/IV):
1. Candidates = winner-screen top-3 per theme + any ENTRY-BOTTOM door.
2. Regime cell per name (from thesis_state + exhaustion_watch):
     BULL-NORMAL / BULL-PARABOLIC / RANGE (entry-bottom basing) /
     BEAR-NORMAL / BEAR-CAPITULATIVE / BROKEN
3. Doctrine map (each rule traces to a study):
     BULL-NORMAL      -> BULL PUT SPREAD  ~40 DTE, short ~10% below
                         spot, ~5% wide  (L1/exit/hourly studies)
     RANGE            -> CASH-SECURED PUT ~15% below, 30-45 DTE
     BEAR-CAPITULATIVE-> CSP (EXPERIMENTAL — paid knife-catching,
                         hpat study candidate rule)
     BULL-PARABOLIC   -> CALL DEBIT SPREAD with trend (EXPERIMENTAL);
                         NO new short premium (fattening left tail)
     BEAR-NORMAL/BROKEN-> NO TRADE (protection is portfolio-level)
4. Gates: earnings within 14 days -> skip; premium selling requires
   IV30 - RV20 > 0 (interim vol gate; switches to IV-rank >= 40 once
   iv_history has ~60 sessions); chain must have usable quotes.
5. Strikes/credits from the REAL chain (mid of bid/ask, lastPrice
   fallback). Max 5 new proposals/week, QUALITY first.
6. Management of open journal positions, weekly:
     profit >= 60% of credit -> CLOSE-PROFIT (doctrine: don't milk the
     last 40%) · short strike breached -> CLOSE-BREACH (don't hope) ·
     regime flips BEAR/BROKEN -> CLOSE-REGIME · expiry -> SETTLE.
State: options_state.json. Journal: options_journal.csv (append-only).
Latest proposals: options_paper.json. All private. SHADOW/PAPER ONLY.
"""
import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import yfinance as yf

HERE = Path(__file__).resolve().parent
MAX_NEW = 5
DTE_TARGET = 40
EARNINGS_BLACKOUT_D = 14


def load(name, default):
    p = HERE / name
    try:
        return json.loads(p.read_text())
    except Exception:
        return default


def latest_iv():
    out = {}
    try:
        for row in csv.DictReader(open(HERE / "iv_history.csv")):
            out[row["ticker"]] = row  # last row per ticker wins
    except Exception:
        pass
    return out


def earnings_within(tk, days):
    try:
        cal = tk.calendar
        dates = []
        if isinstance(cal, dict):
            dates = cal.get("Earnings Date") or []
        elif cal is not None and hasattr(cal, "loc"):
            dates = list(cal.loc["Earnings Date"]) if "Earnings Date" in cal.index else []
        for d in dates if isinstance(dates, (list, tuple)) else [dates]:
            try:
                dd = pd.Timestamp(d).tz_localize(None)
                delta = (dd - pd.Timestamp.utcnow().tz_localize(None)).days
                if 0 <= delta <= days:
                    return True
            except Exception:
                continue
    except Exception:
        pass
    return False


def chain_pick(tk, spot, kind):
    """Real strikes + mid credit from the chain nearest DTE_TARGET.
    kind: 'bps' (bull put spread), 'csp', 'cds' (call debit spread)."""
    try:
        exps = tk.options
        if not exps:
            return None
        now = pd.Timestamp.now().tz_localize(None)
        exp, dte = min(((e, (pd.Timestamp(e) - now).days) for e in exps),
                       key=lambda x: abs(x[1] - DTE_TARGET))
        if dte < 21 or dte > 75:
            return None
        ch = tk.option_chain(exp)

        def mid(df, strike):
            row = df.iloc[(df["strike"] - strike).abs().argsort()[:1]]
            b, a, lp = (float(row["bid"].iloc[0] or 0),
                        float(row["ask"].iloc[0] or 0),
                        float(row["lastPrice"].iloc[0] or 0))
            k = float(row["strike"].iloc[0])
            m = (b + a) / 2 if (b > 0 and a > 0) else lp
            return k, round(m, 2)

        if kind == "bps":
            ks, ms = mid(ch.puts, spot * 0.90)
            kl, ml = mid(ch.puts, spot * 0.85)
            if ks <= kl or ms <= 0:
                return None
            credit = round(ms - ml, 2)
            if credit <= 0.05 * (ks - kl):
                return None  # not paid enough to bother
            return {"exp": exp, "dte": dte, "short_k": ks, "long_k": kl,
                    "credit": credit, "width": round(ks - kl, 2),
                    "max_loss": round(ks - kl - credit, 2)}
        if kind == "csp":
            ks, ms = mid(ch.puts, spot * 0.85)
            if ms <= 0:
                return None
            return {"exp": exp, "dte": dte, "short_k": ks, "long_k": None,
                    "credit": ms, "width": None,
                    "max_loss": round(ks - ms, 2)}
        if kind == "cds":
            kl_, ml_ = mid(ch.calls, spot * 1.00)
            ku, mu = mid(ch.calls, spot * 1.08)
            if ku <= kl_ or ml_ <= 0:
                return None
            debit = round(ml_ - mu, 2)
            if debit <= 0:
                return None
            return {"exp": exp, "dte": dte, "short_k": ku, "long_k": kl_,
                    "credit": -debit, "width": round(ku - kl_, 2),
                    "max_loss": debit}
    except Exception as e:
        print(f"WARN chain {kind}: {e}", file=sys.stderr)
    return None


def regime_cell(door, state, ex):
    top = (ex or {}).get("top_score", 0)
    bot = (ex or {}).get("bottom_score", 0)
    if door == "ENTRY-BOTTOM":
        return "RANGE"
    if door in ("IN-TREND", "ENTRY-MACROSS"):
        return "BULL-PARABOLIC" if top >= 2 else "BULL-NORMAL"
    if door == "BROKEN":
        if state == "Downtrend":
            return "BEAR-CAPITULATIVE" if bot >= 2 else "BEAR-NORMAL"
        return "BROKEN"
    return "BROKEN"


STRATEGY = {"BULL-NORMAL": ("BULL_PUT_SPREAD", "bps", False),
            "RANGE": ("CASH_SECURED_PUT", "csp", False),
            "BEAR-CAPITULATIVE": ("CSP_KNIFECATCH", "csp", True),
            "BULL-PARABOLIC": ("CALL_DEBIT_SPREAD", "cds", True)}


def journal(rows):
    p = HERE / "options_journal.csv"
    new = not p.exists()
    fields = ["date", "event", "ticker", "strategy", "regime", "tag",
              "experimental", "exp", "dte", "short_k", "long_k", "credit",
              "width", "max_loss", "spot", "iv30", "iv_rv", "mark",
              "pnl_per_spread", "note"]
    with open(p, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        if new:
            w.writeheader()
        w.writerows(rows)


def main():
    today = datetime.now(timezone.utc).date().isoformat()
    thesis = load("thesis_state.json", {}).get("names", {})
    winners = load("winners.json", {}).get("themes", {})
    exw = load("exhaustion_watch.json", {}).get("symbols", {})
    state = load("options_state.json", {"open": []})
    iv = latest_iv()
    events = []

    # ---- manage open positions -----------------------------------------
    still_open = []
    for pos in state["open"]:
        t = pos["ticker"]
        try:
            tk = yf.Ticker(t)
            spot = float(tk.fast_info["lastPrice"])
        except Exception:
            still_open.append(pos)
            continue
        s = thesis.get(t, {})
        cell = regime_cell(s.get("door"), s.get("state"), exw.get(t))
        expired = pd.Timestamp(pos["exp"]) <= pd.Timestamp(today)
        mark = None
        try:
            ch = yf.Ticker(t).option_chain(pos["exp"]) if not expired else None
            if ch is not None:
                df = ch.puts if "PUT" in pos["strategy"] or "CSP" in pos["strategy"] else ch.calls
                row = df.iloc[(df["strike"] - pos["short_k"]).abs().argsort()[:1]]
                b, a = float(row["bid"].iloc[0] or 0), float(row["ask"].iloc[0] or 0)
                mark = round((b + a) / 2, 2) if (b > 0 and a > 0) else float(row["lastPrice"].iloc[0] or 0)
        except Exception:
            pass
        close_reason = None
        if expired:
            intrinsic = max(0.0, pos["short_k"] - spot) if pos["credit"] > 0 else max(0.0, spot - pos["short_k"])
            pnl = round((pos["credit"] - min(intrinsic, pos.get("width") or intrinsic)) * 100, 0)
            close_reason, mark = "SETTLE", round(intrinsic, 2)
        elif pos["credit"] > 0 and mark is not None and mark <= pos["credit"] * 0.4:
            close_reason = "CLOSE-PROFIT"
            pnl = round((pos["credit"] - mark) * 100, 0)
        elif pos["credit"] > 0 and spot < pos["short_k"]:
            close_reason = "CLOSE-BREACH"
            pnl = round((pos["credit"] - (mark if mark is not None else pos["credit"] * 2)) * 100, 0)
        elif cell in ("BEAR-NORMAL", "BROKEN") and pos["credit"] > 0:
            close_reason = "CLOSE-REGIME"
            pnl = round((pos["credit"] - (mark if mark is not None else pos["credit"])) * 100, 0)
        if close_reason:
            events.append({"date": today, "event": close_reason, **pos,
                           "spot": round(spot, 2), "mark": mark,
                           "pnl_per_spread": pnl})
        else:
            events.append({"date": today, "event": "MARK", **pos,
                           "spot": round(spot, 2), "mark": mark,
                           "pnl_per_spread": round((pos["credit"] - mark) * 100, 0)
                           if (mark is not None and pos["credit"] > 0) else None})
            still_open.append(pos)
    state["open"] = still_open

    # ---- candidates -----------------------------------------------------
    cands, seen = [], {p["ticker"] for p in state["open"]}
    for theme, ranked in winners.items():
        for r in ranked[:3]:
            if r["ticker"] not in seen:
                cands.append((r["ticker"], theme, r.get("score"),
                              "QUALITY" if (r.get("growth_pct") or 0) >= 0 else "?"))
    for t, s in thesis.items():
        if s.get("door") == "ENTRY-BOTTOM" and t not in seen \
                and all(t != c[0] for c in cands):
            cands.append((t, s.get("theme"), None, "?"))

    proposals = []
    for t, theme, score, tag in cands:
        if len(proposals) >= MAX_NEW:
            break
        s = thesis.get(t, {})
        cell = regime_cell(s.get("door"), s.get("state"), exw.get(t))
        strat = STRATEGY.get(cell)
        if not strat:
            continue
        name, kind, experimental = strat
        ivrow = iv.get(t, {})
        iv_rv = float(ivrow["iv_rv_spread"]) if ivrow.get("iv_rv_spread") else None
        if kind in ("bps", "csp") and iv_rv is not None and iv_rv <= 0:
            print(f"skip {t}: vol gate (IV-RV {iv_rv})")
            continue
        tk = yf.Ticker(t)
        if earnings_within(tk, EARNINGS_BLACKOUT_D):
            print(f"skip {t}: earnings within {EARNINGS_BLACKOUT_D}d")
            continue
        try:
            spot = float(tk.fast_info["lastPrice"])
        except Exception:
            continue
        pick = chain_pick(tk, spot, kind)
        if not pick:
            print(f"skip {t}: no usable chain for {name}")
            continue
        pos = {"ticker": t, "strategy": name, "regime": cell, "tag": tag,
               "experimental": experimental, "opened": today, **pick,
               "spot_open": round(spot, 2)}
        proposals.append(pos)
        state["open"].append(pos)
        events.append({"date": today, "event": "OPEN", **pos,
                       "spot": round(spot, 2),
                       "iv30": ivrow.get("iv30"), "iv_rv": iv_rv,
                       "note": f"theme={theme} score={score}"})

    (HERE / "options_state.json").write_text(json.dumps(state, indent=1))
    (HERE / "options_paper.json").write_text(json.dumps(
        {"date": today, "new_proposals": proposals,
         "open_positions": state["open"]}, indent=1, default=str))
    journal(events)
    print(f"options engine: {len(proposals)} new proposals, "
          f"{len(state['open'])} open, {len(events)} journal events")
    for p in proposals:
        side = "credit" if p["credit"] > 0 else "debit"
        print(f"  {p['strategy']:17s} {p['ticker']:6s} [{p['regime']}] "
              f"exp {p['exp']} short {p['short_k']} "
              f"{side} {abs(p['credit'])} max_loss {p['max_loss']}"
              + ("  (EXPERIMENTAL)" if p["experimental"] else ""))


if __name__ == "__main__":
    main()
