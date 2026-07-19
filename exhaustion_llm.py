"""Exhaustion Watch — LLM narrative layer (VBT-2; Eric 2026-07-19).

Weekly, per theme: rate narrative EXTREMITY on a -5..+5 scale with
cited evidence, plus KOL unanimity — the qualitative exhaustion tells
(euphoria, capitulation, unanimity) that numbers can't read. SHADOW:
forward-logged (exhaustion_llm_log.jsonl), scored against subsequent
returns and transitions before anything acts on it.

Skips silently without ANTHROPIC_API_KEY.
"""
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from llm_screen import call_claude, extract_json  # noqa: E402

KEY = os.environ.get("ANTHROPIC_API_KEY", "").strip()
THEMES = {
    "ai": "AI infrastructure (semis, AI hardware, datacenters, neoclouds, AI software)",
    "grid": "electrification & grid (power generation, nuclear/SMR, grid equipment, datacenter power)",
    "robotics": "robotics & automation (humanoids, machine vision, industrial automation)",
    "defense": "defense & space (rearmament, defense tech, launch, satellites)",
    "health": "healthcare innovation (GLP-1/metabolic, AI in medicine, medtech, genomics)",
    "outlier": "US mega-cap multi-theme names (SpaceX/SPCX, Tesla, Palantir, GE Vernova, Coinbase)",
}

PROMPT = """You are measuring NARRATIVE EXTREMITY for a systematic
exhaustion study. Theme: {desc}.

Using web search on the LAST 2 WEEKS of financial media, X/social
commentary, and prominent investor (KOL) statements about this theme,
rate where crowd sentiment sits on this scale:
  -5 = full capitulation ("the theme is dead", forced selling, funds closing)
  -3 = deep pessimism, bearish pieces dominate
   0 = balanced / contested, bulls and bears both loud
  +3 = broad optimism, skeptics mocked
  +5 = euphoria ("this time is different", price targets leapfrogging,
        retail flooding in, magazine-cover energy)
Extremes in EITHER direction are exhaustion evidence. Also judge KOL
unanimity: are prominent voices aligned (a contrarian tell) or split?
Be concrete — cite 2-4 specific pieces of evidence with sources.
End with ONLY this JSON on its own line:
{{"theme": "{theme}", "extremity": -5 to 5, "kol_unanimity":
"bullish" or "bearish" or "split", "direction_2wk": "hotter" or
"cooler" or "stable", "evidence": ["...", "..."]}}"""


def main():
    if not KEY:
        print("exhaustion_llm: no ANTHROPIC_API_KEY — skipped")
        return
    today = datetime.now(timezone.utc).date().isoformat()
    out = {"date": today,
           "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "themes": {}}
    for theme, desc in THEMES.items():
        try:
            text = call_claude(PROMPT.format(theme=theme, desc=desc))
            j = extract_json(text) or {}
            out["themes"][theme] = j
            print(f"{theme:9s} extremity {j.get('extremity')} "
                  f"({j.get('kol_unanimity')}, {j.get('direction_2wk')})")
        except Exception as e:
            print(f"WARN {theme}: {e}", file=sys.stderr)
            out["themes"][theme] = {"error": str(e)}
    (HERE / "exhaustion_llm.json").write_text(json.dumps(out, indent=1))
    with open(HERE / "exhaustion_llm_log.jsonl", "a") as f:
        f.write(json.dumps(out) + "\n")


if __name__ == "__main__":
    main()
