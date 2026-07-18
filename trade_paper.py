"""Paper-trading engine — executes the recovery strategy on Alpaca paper. (v1.0)

Runs nightly in the Action after compute_signals.py. Reads docs/signals.json,
applies the strategy rules, submits orders to the Alpaca PAPER account, and
writes docs/paper.json (account snapshot + positions + ledger) for the
dashboard. Skips silently if ALPACA_KEY / ALPACA_SECRET are not configured.

STRATEGY RULES (v1 — user-approved 2026-07-18):
  Entry : ticker transitions INTO stage 3 (confirmed recovery) today
          -> market buy queued for next open. Skip if already held.
  Size  : 8% of equity if quality, 4% if speculative. Max 15 positions.
          Whole shares, floor. Skip if buying power insufficient.
  Exit  : stage drops back to 1 or 2 (breakdown), or holding age > 182 days
          (26w backtest horizon) -> market sell queued for next open.
          Stages 0/4 while held are HOLD.
  Orders: plain market, time_in_force=day; submitted after close so they
          execute at next open. PAPER MONEY ONLY.
"""
import json
import os
import sys
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

# Runs from the PUBLIC repo root (workflow cwd); this file lives in the
# private checkout so strategy mechanics stay off the public repo.
HERE = Path.cwd()
DOCS = HERE / "docs"
# Paper state lives in a PRIVATE repo checkout (vbt-private) (positions/ledger are not
# published). Workflow sets PAPER_STATE_DIR to that checkout.
PAPER_PATH = Path(os.environ.get("PAPER_STATE_DIR") or DOCS) / "paper.json"

BASE = "https://paper-api.alpaca.markets"
KEY = os.environ.get("ALPACA_KEY", "").strip()
SECRET = os.environ.get("ALPACA_SECRET", "").strip()

# Phase-2 LLM screen: SHADOW MODE. Verdicts from llm_screen.py are logged
# against every trade; set ENFORCE_LLM=True (and update RULEBOOK) only after
# the shadow record proves the layer adds value.
ENFORCE_LLM = False

QUALITY_PCT, SPEC_PCT = 0.08, 0.04
MAX_POSITIONS = 15
MAX_PER_GROUP = 4        # rulebook v2: one narrative can hit a whole group
MAX_HOLD_DAYS = 182
EXIT_STAGES = {1, 2}
CAT_STOP_SPEC = -0.25    # rulebook v2: catastrophic stop, SPEC positions only

# One-time cold-start seed (user-approved 2026-07-18): stage-3 names whose
# transition was ≤4 weeks old at engine launch. Entry date = actual transition
# date so the 26-week clock is honest. Processed once (state["seeded"]).
SEED = {"CIEN": "2026-07-10", "CORZ": "2026-07-10",
        "SNPS": "2026-07-03", "TLN": "2026-06-26"}


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


def load_state():
    if PAPER_PATH.exists():
        try:
            return json.loads(PAPER_PATH.read_text())
        except Exception:
            pass
    return {"entries": {}, "ledger": []}


def main():
    if not KEY or not SECRET:
        print("paper: no ALPACA_KEY/ALPACA_SECRET configured — skipping")
        return

    signals = json.loads((DOCS / "signals.json").read_text())
    rows = {r["ticker"]: r for r in signals["rows"]}
    transitions = signals.get("transitions", [])
    today = signals.get("as_of", datetime.now(timezone.utc).date().isoformat())

    account = api("/v2/account")
    if account.get("trading_blocked"):
        print("paper: account trading_blocked", file=sys.stderr)
        return
    equity = float(account["equity"])
    positions = {p["symbol"]: p for p in api("/v2/positions")}
    open_orders = {o["symbol"] for o in api("/v2/orders?status=open&limit=200")}

    state = load_state()
    entries = state.get("entries", {})   # symbol -> entry date iso
    ledger = state.get("ledger", [])

    llm = {}
    llm_path = PAPER_PATH.parent / "llm_today.json"
    if llm_path.exists():
        try:
            cand = json.loads(llm_path.read_text())
            if cand.get("date") == today:
                llm = cand
        except Exception:
            pass
    llm_regime = (llm.get("regime") or {}).get("regime")

    def log(action, sym, note):
        ledger.append({"date": today, "action": action, "symbol": sym, "note": note})
        print(f"paper: {action} {sym} — {note}")

    # ---- EXITS first (frees buying power) --------------------------------
    for sym, pos in list(positions.items()):
        r = rows.get(sym)
        if sym in open_orders:
            continue
        held_days = None
        if sym in entries:
            try:
                held_days = (datetime.fromisoformat(today)
                             - datetime.fromisoformat(entries[sym])).days
            except Exception:
                pass
        plpc = float(pos.get("unrealized_plpc") or 0)
        reason = None
        if r and r["stage"] in EXIT_STAGES:
            reason = f"breakdown to stage {r['stage']} ({r['stage_name']})"
        elif r is not None and not r["quality"] and plpc <= CAT_STOP_SPEC:
            reason = f"catastrophic stop (spec, {plpc:.1%} <= {CAT_STOP_SPEC:.0%})"
        elif held_days is not None and held_days > MAX_HOLD_DAYS:
            reason = f"time exit ({held_days}d > {MAX_HOLD_DAYS}d)"
        elif r is None:
            reason = "left universe"
        if reason:
            api("/v2/orders", "POST", {
                "symbol": sym, "qty": pos["qty"], "side": "sell",
                "type": "market", "time_in_force": "day"})
            log("SELL", sym, reason)
            entries.pop(sym, None)

    # ---- ENTRIES: today's new stage-3 transitions ------------------------
    new_confirmed = [t["ticker"] for t in transitions if t.get("to") == 3]
    seeding = not state.get("seeded", False)
    if seeding:
        for sym in SEED:
            r = rows.get(sym)
            if r and r["stage"] == 3 and sym not in new_confirmed:
                new_confirmed.append(sym)
    for sym in new_confirmed:
        r = rows.get(sym)
        if r is None or sym in positions or sym in open_orders:
            continue
        if len(positions) + len([l for l in ledger if l["date"] == today
                                 and l["action"] == "BUY"]) >= MAX_POSITIONS:
            log("SKIP", sym, "max positions reached")
            continue
        grp = r.get("group")
        n_grp = sum(1 for psym in positions
                    if rows.get(psym, {}).get("group") == grp)
        n_grp += sum(1 for l in ledger if l["date"] == today and l["action"] == "BUY"
                     and rows.get(l["symbol"], {}).get("group") == grp)
        if n_grp >= MAX_PER_GROUP:
            log("SKIP", sym, f"group cap ({grp} already at {MAX_PER_GROUP})")
            continue
        pct = QUALITY_PCT if r["quality"] else SPEC_PCT
        target = equity * pct
        price = float(r["price"])
        qty = int(target // price)
        if qty < 1:
            log("SKIP", sym, f"target ${target:,.0f} < 1 share @ {price}")
            continue
        # ---- Phase-2 LLM screen (shadow unless ENFORCE_LLM) ----
        v = (llm.get("verdicts") or {}).get(sym)
        shadow_note = ""
        if v:
            mult = float(v.get("size_mult", 1.0))
            if llm_regime == "RISK-OFF" and not r["quality"]:
                mult = 0.0  # regime gate on speculative entries
            shadow_note = (f" | llm:{v['verdict']} mult:{mult:g}"
                           f" regime:{llm_regime or '?'}")
            if ENFORCE_LLM:
                qty = int(qty * mult)
                if qty < 1:
                    log("SKIP", sym, f"LLM-enforced skip{shadow_note} — "
                        + "; ".join(v.get("reasons", [])[:2]))
                    continue
        api("/v2/orders", "POST", {
            "symbol": sym, "qty": str(qty), "side": "buy",
            "type": "market", "time_in_force": "day"})
        entries[sym] = SEED[sym] if (seeding and sym in SEED) else today
        log("BUY", sym,
            f"{qty} sh ~${qty * price:,.0f} ({'quality' if r['quality'] else 'spec'} "
            f"{pct:.0%}) on stage-3 "
            f"{'seed (transition ' + entries[sym] + ')' if seeding and sym in SEED else 'entry'}"
            f" @ {price}{shadow_note}")

    # ---- snapshot for the dashboard --------------------------------------
    positions_now = api("/v2/positions")
    snap = {
        "as_of": today,
        "updated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "account": {
            "equity": round(float(account["equity"]), 2),
            "cash": round(float(account["cash"]), 2),
            "pl_total": round(float(account["equity"]) - float(account.get("last_equity", account["equity"])), 2),
        },
        "positions": [{
            "symbol": p["symbol"], "qty": float(p["qty"]),
            "avg_entry": round(float(p["avg_entry_price"]), 2),
            "current": round(float(p.get("current_price") or 0), 2),
            "pl_pct": round(float(p.get("unrealized_plpc") or 0) * 100, 2),
            "pl_usd": round(float(p.get("unrealized_pl") or 0), 2),
            "entered": entries.get(p["symbol"], "—"),
            "stage": rows.get(p["symbol"], {}).get("stage_name", "—"),
        } for p in positions_now],
        "entries": entries,
        "seeded": True,
        "ledger": ledger[-60:],
    }
    PAPER_PATH.write_text(json.dumps(snap, indent=1))
    print(f"paper: equity ${snap['account']['equity']:,.0f}, "
          f"{len(snap['positions'])} positions, {len(new_confirmed)} new signals")


if __name__ == "__main__":
    main()
