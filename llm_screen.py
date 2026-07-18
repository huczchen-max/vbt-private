"""Phase-2 LLM screen — runs INSIDE the nightly Action, only on days with new
stage-3 signals. Produces a macro regime call plus a per-ticker micro verdict
(GO / CAUTION / VETO + size multiplier) via the Claude API with web search.

SHADOW MODE: trade_paper.py logs these against every trade but does NOT act on
them until the shadow record earns enforcement (ENFORCE_LLM flag there).

Outputs (in the private checkout, committed by the workflow):
  llm_today.json  — {date, regime, verdicts{ticker: {...}}} for today's run
  llm_log.jsonl   — append-only judgment log for later scoring

Skips silently without ANTHROPIC_API_KEY. Cost: 1 regime call + 1 call per
new signal, web-search enabled — only on transition days (a few $/month max).
"""
import json
import os
import re
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

STATE = Path(os.environ.get("PAPER_STATE_DIR") or ".")
DOCS = Path.cwd() / "docs"
MODEL = os.environ.get("LLM_MODEL", "claude-sonnet-4-5")
KEY = os.environ.get("ANTHROPIC_API_KEY", "").strip()


def call_claude(prompt, max_tokens=1500):
    body = {
        "model": MODEL,
        "max_tokens": max_tokens,
        "tools": [{"type": "web_search_20250305", "name": "web_search", "max_uses": 6}],
        "messages": [{"role": "user", "content": prompt}],
    }
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=json.dumps(body).encode(),
        headers={"x-api-key": KEY, "anthropic-version": "2023-06-01",
                 "content-type": "application/json"})
    with urllib.request.urlopen(req, timeout=300) as r:
        resp = json.loads(r.read().decode())
    text = "".join(b.get("text", "") for b in resp.get("content", [])
                   if b.get("type") == "text")
    return text


def extract_json(text):
    """Pull the last JSON object out of a response."""
    matches = re.findall(r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", text, re.DOTALL)
    for m in reversed(matches):
        try:
            return json.loads(m)
        except Exception:
            continue
    return None


REGIME_PROMPT = """You are a risk officer for a systematic strategy that buys
US AI-infrastructure stocks (semis, AI hardware, datacenter power, neoclouds)
after deep corrections when trend structure confirms recovery. Using web
search, assess TODAY's environment for initiating such positions: hyperscaler
capex/surplus-compute news, semiconductor sector trend, imminent Fed/macro
events, China/export-control developments. Be decisive and terse.
End with ONLY this JSON on its own line:
{"regime": "RISK-ON" or "NEUTRAL" or "RISK-OFF", "reasons": ["...", "..."]}"""

VERDICT_PROMPT = """You are a risk officer screening a single mechanical buy
signal for idiosyncratic red flags. The system flagged {ticker} ({group},
{quality}) as a confirmed recovery: price {price}, {dd}% below its 52-week
peak. Using web search on the LAST 4 WEEKS of news for {ticker}, check ONLY
for: earnings scheduled within 14 days; announced share offerings/dilution;
guidance cuts; loss/concentration of a major customer; short-seller or
accounting/auditor issues; legal or regulatory actions. Ignore price
commentary and analyst opinions — you screen for events, not views.
Verdict rules: VETO only for disqualifying events (accounting scandal,
going-concern, major dilution announced, fraud allegations). CAUTION for a
concrete named concern (earnings within 14d is automatic CAUTION).
GO if nothing found. size_mult: GO=1.0, CAUTION=0.5, VETO=0.0.
End with ONLY this JSON on its own line:
{{"ticker": "{ticker}", "verdict": "GO" or "CAUTION" or "VETO",
"size_mult": 1.0 or 0.5 or 0.0, "reasons": ["...", "..."]}}"""


def main():
    if not KEY:
        print("llm_screen: no ANTHROPIC_API_KEY — skipped")
        return
    signals = json.loads((DOCS / "signals.json").read_text())
    rows = {r["ticker"]: r for r in signals["rows"]}
    new3 = [t["ticker"] for t in signals.get("transitions", []) if t.get("to") == 3]
    if not new3:
        print("llm_screen: no new stage-3 signals — skipped")
        return

    today = signals.get("as_of")
    out = {"date": today, "model": MODEL,
           "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds")}

    try:
        rtext = call_claude(REGIME_PROMPT)
        rj = extract_json(rtext) or {}
        out["regime"] = {"regime": rj.get("regime", "NEUTRAL"),
                         "reasons": rj.get("reasons", []),
                         "raw_ok": bool(rj)}
    except Exception as e:
        print(f"llm_screen: regime call failed: {e}", file=sys.stderr)
        out["regime"] = {"regime": "NEUTRAL", "reasons": [f"call failed: {e}"],
                         "raw_ok": False}

    verdicts = {}
    for t in new3:
        r = rows.get(t, {})
        try:
            vtext = call_claude(VERDICT_PROMPT.format(
                ticker=t, group=r.get("group", "?"),
                quality="quality" if r.get("quality") else "speculative",
                price=r.get("price", "?"), dd=r.get("dd", "?")))
            vj = extract_json(vtext) or {}
            verdicts[t] = {
                "verdict": vj.get("verdict", "GO"),
                "size_mult": float(vj.get("size_mult", 1.0)),
                "reasons": vj.get("reasons", []),
                "raw_ok": bool(vj),
            }
        except Exception as e:
            print(f"llm_screen: verdict for {t} failed: {e}", file=sys.stderr)
            verdicts[t] = {"verdict": "GO", "size_mult": 1.0,
                           "reasons": [f"call failed: {e}"], "raw_ok": False}
    out["verdicts"] = verdicts

    (STATE / "llm_today.json").write_text(json.dumps(out, indent=1))
    with open(STATE / "llm_log.jsonl", "a") as f:
        f.write(json.dumps(out) + "\n")
    summary = ", ".join(f"{k}:{v['verdict']}" for k, v in verdicts.items())
    print(f"llm_screen: regime={out['regime']['regime']}, verdicts=[{summary}]")


if __name__ == "__main__":
    main()
