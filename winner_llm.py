"""Phase 2 LLM winner rubric — quarterly qualitative pass on the top
quant-ranked names per theme (VBT-2; Eric 2026-07-19).

For the top N (default 3) names per theme in winners.json, ask Claude
(web search enabled) to score "next big winner" potential on a fixed
rubric. SHADOW: judgments are forward-logged and scoreable; nothing is
enforced. Skips silently without ANTHROPIC_API_KEY.

Outputs: winners_llm.json (latest), winners_llm_log.jsonl (append).
"""
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from llm_screen import call_claude, extract_json  # noqa: E402

TOP_N = int(os.environ.get("WINNER_TOP_N", "3"))
KEY = os.environ.get("ANTHROPIC_API_KEY", "").strip()

RUBRIC_PROMPT = """You are a growth-equity analyst screening for the
NEXT BIG WINNER within a secular investment theme. Candidate: {ticker}
({name_hint}), theme: {theme}. Quant screen context: composite score
{score}/100, revenue growth {growth}%, growth acceleration {accel}pp,
margin inflection {margin}pp, 26-week relative strength vs theme ETF
{rs26}%, trend intact: {intact}.

Using web search on the last 3 months, assess:
1. PRODUCT CYCLE — is a major product/platform cycle starting, peaking, or fading?
2. TAM & SHARE — is the addressable market expanding and is this company gaining share?
3. MOAT — pricing power, switching costs, network effects, or none?
4. ESTIMATE MOMENTUM — are analyst estimates being revised up or down?
5. RED FLAGS — dilution, customer concentration, accounting issues, key-person risk.

Be decisive and terse. End with ONLY this JSON on its own line:
{{"ticker": "{ticker}", "llm_score": 0-100, "conviction": "HIGH" or "MEDIUM" or "LOW",
"thesis": "one sentence", "product_cycle": "starting|mid|peaking|fading|unclear",
"estimate_momentum": "up|flat|down|unclear", "moat": "strong|some|none",
"red_flags": ["..."], "catalysts": ["..."]}}"""


def main():
    if not KEY:
        print("winner_llm: no ANTHROPIC_API_KEY — skipped")
        return
    w = json.loads((HERE / "winners.json").read_text())
    today = w.get("date")
    out = {"date": today, "top_n": TOP_N,
           "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "judgments": {}}
    for theme, ranked in w["themes"].items():
        for r in ranked[:TOP_N]:
            t = r["ticker"]
            try:
                text = call_claude(RUBRIC_PROMPT.format(
                    ticker=t, name_hint=t, theme=theme, score=r.get("score"),
                    growth=r.get("growth_pct"), accel=r.get("accel_pp"),
                    margin=r.get("margin_pp"), rs26=r.get("rs26_pct"),
                    intact=r.get("intact")))
                j = extract_json(text) or {}
                j["quant_score"] = r.get("score")
                j["theme"] = theme
                out["judgments"][t] = j
                print(f"{theme}/{t}: llm {j.get('llm_score')} "
                      f"({j.get('conviction')}) — {j.get('thesis')}")
            except Exception as e:
                print(f"WARN {t}: {e}", file=sys.stderr)
                out["judgments"][t] = {"error": str(e), "theme": theme}
    (HERE / "winners_llm.json").write_text(json.dumps(out, indent=1))
    with open(HERE / "winners_llm_log.jsonl", "a") as f:
        f.write(json.dumps(out) + "\n")


if __name__ == "__main__":
    main()
