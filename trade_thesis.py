"""VBT-2 Phase 5 — thesis paper portfolio (Eric's decisions 2026-07-19):
  1. Conviction NAMES, no ETF core.
  2. Sizing skewed to winners (weights ~ winner score squared).
  3. Shares VBT-1's Alpaca paper account; every order tagged
     client_order_id "vbt2-..." and the book is tracked in its own
     ledger (thesis_paper.json) — VBT-1's paper.json stays untouched.
  4. 80% of the VBT-2 budget in 3-4 stocks; 20% reserved as the options
     risk budget (consumed by options_engine proposals — this script
     sizes contracts against it, journal-paper only).

Budget: VBT2_BUDGET_PCT of account equity (default 40% — leaves VBT-1's
recovery engine its room in the shared account).

Selection: global winner-screen ranking across themes, gated to names
whose ladder door is open (ENTRY-BOTTOM / ENTRY-MACROSS / IN-TREND),
max 2 per theme (diversification), max 4 names.

Rules (each traces to a study):
  - Buy-and-hold: NO exits on structure noise. A holding is replaced
    ONLY after its trend is BROKEN for 4+ consecutive weeks (an
    escalated review — logged with the counterfactual so the rule
    itself gets scored; a documented pragmatic deviation from pure
    hold, required by a 3-4 name book).
  - Adds: if fewer than MAX_NAMES held and budget is free, buy the
    next-ranked eligible winner (no L2/L3 signal-waiting — adds
    whenever capital allows, per the re-entry study).
  - Weekly cadence (Saturdays); market orders queue for Monday open.

State/ledger: thesis_paper.json. Runs in tracker.yml after the options
engine. Skips silently without Alpaca keys.
"""
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
BASE = "https://paper-api.alpaca.markets"
KEY = os.environ.get("ALPACA_KEY", "").strip()
SECRET = os.environ.get("ALPACA_SECRET", "").strip()

VBT2_BUDGET_PCT = 0.40
STOCK_SLEEVE = 0.80
OPTIONS_SLEEVE = 0.20
MAX_NAMES = 4
MIN_NAMES = 3
MAX_PER_THEME = 2
BROKEN_WEEKS_TO_REPLACE = 4
OPEN_DOORS = {"ENTRY-BOTTOM", "ENTRY-MACROSS", "IN-TREND"}
STATE_PATH = HERE / "thesis_paper.json"


def api(path, method="GET", body=None):
    req = urllib.request.Request(
        BASE + path, method=method,
        data=json.dumps(body).encode() if body else None,
        headers={"APCA-API-KEY-ID": KEY, "APCA-API-SECRET-KEY": SECRET,
                 "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode() or "null")
    except urllib.error.HTTPError as e:
        detail = e.read().decode()[:200]
        raise RuntimeError(f"Alpaca {method} {path} -> {e.code}: {detail}") from None


def load(name, default):
    try:
        return json.loads((HERE / name).read_text())
    except Exception:
        return default


def main():
    if not KEY or not SECRET:
        print("thesis-paper: no Alpaca keys — skipping")
        return
    today = datetime.now(timezone.utc).date().isoformat()
    thesis = load("thesis_state.json", {}).get("names", {})
    winners = load("winners.json", {}).get("themes", {})
    options = load("options_state.json", {"open": []})
    state = load("thesis_paper.json", {"holdings": {}, "broken_weeks": {},
                                       "ledger": []})
    holdings = state["holdings"]     # sym -> {entry, weight, theme, score}
    broken_w = state["broken_weeks"]
    ledger = state["ledger"]

    account = api("/v2/account")
    if account.get("trading_blocked"):
        print("thesis-paper: account trading_blocked", file=sys.stderr)
        return
    equity = float(account["equity"])
    budget = equity * VBT2_BUDGET_PCT
    stock_budget = budget * STOCK_SLEEVE
    options_budget = budget * OPTIONS_SLEEVE
    positions = {p["symbol"]: p for p in api("/v2/positions")}

    def log(action, sym, note):
        ledger.append({"date": today, "action": action, "symbol": sym,
                       "note": note})
        print(f"thesis-paper: {action} {sym} — {note}")

    def order(sym, notional_or_qty, side, qty_mode=False):
        body = {"symbol": sym, "side": side, "type": "market",
                "time_in_force": "day",
                "client_order_id": f"vbt2-{sym}-{today}-{side}"}
        if qty_mode:
            body["qty"] = str(notional_or_qty)
        else:
            body["notional"] = str(round(notional_or_qty, 2))
        api("/v2/orders", "POST", body)

    # ---- rank the eligible universe -------------------------------------
    ranked = []
    for theme, rows in winners.items():
        for r in rows:
            t = r["ticker"]
            s = thesis.get(t, {})
            if s.get("door") in OPEN_DOORS:
                ranked.append({"ticker": t, "theme": theme,
                               "score": r.get("score") or 0,
                               "door": s.get("door")})
    ranked.sort(key=lambda x: -x["score"])

    # ---- replacement rule: BROKEN for 4+ consecutive weeks --------------
    for sym in list(holdings):
        door = thesis.get(sym, {}).get("door")
        if door == "BROKEN":
            broken_w[sym] = broken_w.get(sym, 0) + 1
            if broken_w[sym] >= BROKEN_WEEKS_TO_REPLACE:
                px = thesis.get(sym, {}).get("close")
                if sym in positions:
                    order(sym, positions[sym]["qty"], "sell", qty_mode=True)
                log("REPLACE-SELL", sym,
                    f"BROKEN {broken_w[sym]}w; close {px} — counterfactual "
                    f"tracked via thesis_ledger")
                holdings.pop(sym, None)
                broken_w.pop(sym, None)
        else:
            broken_w.pop(sym, None)

    # ---- target book: top-ranked, max 2/theme, max 4 names --------------
    target, per_theme = [], {}
    for r in ranked:
        if len(target) >= MAX_NAMES:
            break
        if per_theme.get(r["theme"], 0) >= MAX_PER_THEME:
            continue
        if r["ticker"] in holdings or all(r["ticker"] != x["ticker"]
                                          for x in target):
            target.append(r)
            per_theme[r["theme"]] = per_theme.get(r["theme"], 0) + 1

    # keep existing holdings in the book even if their rank slipped
    # (buy-and-hold: rank decides ENTRY, not eviction)
    slots_left = MAX_NAMES - len(holdings)
    buys = [r for r in target if r["ticker"] not in holdings][:max(0, slots_left)]

    # skew-to-winners weights over the POST-buy book (score^2)
    book = list(holdings.keys()) + [b["ticker"] for b in buys]
    scores = {}
    for t in book:
        sc = next((r["score"] for r in ranked if r["ticker"] == t), None)
        scores[t] = (sc if sc is not None
                     else holdings.get(t, {}).get("score", 50) or 50)
    denom = sum(s ** 2 for s in scores.values()) or 1
    weights = {t: s ** 2 / denom for t, s in scores.items()}

    for b in buys:
        t = b["ticker"]
        notional = stock_budget * weights[t]
        try:
            order(t, notional, "buy")
            holdings[t] = {"entry": today, "theme": b["theme"],
                           "score": b["score"], "door_at_entry": b["door"],
                           "target_weight": round(weights[t], 3),
                           "notional_at_entry": round(notional, 2)}
            log("BUY", t, f"{b['door']} score {b['score']} "
                          f"~${notional:,.0f} ({weights[t]:.0%} of sleeve)")
        except Exception as e:
            log("BUY-FAIL", t, str(e)[:120])

    # ---- options sleeve sizing (journal-paper, not sent anywhere) -------
    open_opts = options.get("open", [])
    committed = 0.0
    sized = []
    for p in open_opts:
        ml = (p.get("max_loss") or 0) * 100
        if ml <= 0:
            continue
        room = options_budget - committed
        contracts = int(min(room // ml, max(1, (options_budget * 0.25) // ml)))
        if contracts >= 1:
            committed += contracts * ml
            sized.append({"ticker": p["ticker"], "strategy": p["strategy"],
                          "contracts": contracts,
                          "max_loss_total": round(contracts * ml, 0)})

    state["holdings"] = holdings
    state["broken_weeks"] = broken_w
    state["ledger"] = ledger
    state["snapshot"] = {
        "date": today, "account_equity": round(equity, 2),
        "vbt2_budget": round(budget, 2),
        "stock_sleeve": round(stock_budget, 2),
        "options_sleeve": round(options_budget, 2),
        "options_committed": round(committed, 2),
        "options_sizing": sized,
        "book": {t: {**h, "current_close": thesis.get(t, {}).get("close"),
                     "door_now": thesis.get(t, {}).get("door")}
                 for t, h in holdings.items()},
    }
    STATE_PATH.write_text(json.dumps(state, indent=1))
    print(f"thesis-paper: equity ${equity:,.0f}, budget ${budget:,.0f}, "
          f"book {list(holdings)}, options sized {len(sized)} "
          f"(${committed:,.0f}/{options_budget:,.0f})")


if __name__ == "__main__":
    main()
