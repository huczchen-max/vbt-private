# VBT Recovery Strategy — Rulebook v2

*Adopted 2026-07-18. Every rule below was tested against 66 resolved historical
signals (10 years, 45 AI-infra names, causal weekly swing structure). Rules
the lab rejected are listed at the bottom — they stay rejected until new
evidence. This documents a systematic process; it is not investment advice.*

## Setup (what qualifies as a candidate)

A stock in the tracked universe that fell **≥30% below its trailing 52-week
peak** within the last 26 weeks and still sits **≥15% below** that peak.
Evidence: without this context + the trigger below, dip-buying had **zero
excess return** vs SMH (control: −1.1%).

## Entry

**Weekly swing structure flips Mixed → Uptrend (causal: pivots confirmed ±5
weeks)** while the setup holds. Buy at the next open.
Evidence: 76% win rate at 26 weeks, median +25.3%, the only tested trigger
with positive excess vs SMH.
- Discretionary tiebreaker (not a hard rule): entries with weekly **EWO > 0**
  ran a median +31.4% vs +16.4% when EWO ≤ 0 — when choosing among several
  same-day signals, prefer positive EWO.

## Position size

- **Quality** (GAAP-profitable + FCF-positive): **8%** of equity.
  Evidence: 83% win rate, shallow −12.6% median MAE — consistency.
- **Speculative**: **4%** of equity.
  Evidence: bigger wins (median +33.7%, +7.1% excess) but 68% win rate,
  −20.9% median MAE, and every one of the worst blowups — magnitude with fat
  tails.
- **Max 15 positions** (historical max concurrency was 12).
- **Max 4 per group** (semis / hw / power / neoclouds) — the June-2026
  cluster showed one narrative can hit a whole group at once.

## Exits

1. **Structure breakdown** — weekly stage falls back to Downtrend or Base
   building → sell next open. (Primary exit; the stop that matches the entry logic.)
2. **Catastrophic stop, speculative names only: −25% from entry** → sell next
   open. Evidence: caps the worst outcome from −58% to −29% at a cost of only
   1.5 points of average return. Quality names carry NO hard stop — a third of
   all winners touched −15% first; tight stops destroyed returns in testing.
3. **Time exit: 26 weeks** — the tested horizon. Beyond it we have no evidence.

## Hold discipline

**No profit-taking before an exit rule fires.** Tested: selling half at +25%
cut average return from 33.7% to 24.6%; selling all at +25% cut it to 15.4%.
The strategy's edge is the right tail — amputating it is expensive. (If manual
comfort demands partial profit-taking, do it knowing the measured cost.)

## Portfolio guards

- Stop opening new positions if account drawdown from its high exceeds 15%.
- Review the paper ledger against these rules monthly; log every deviation.

## Tested and REJECTED

- **Volume ≥1.2× on the transition week** — made results *worse*
  (median +13.9%, excess −10.2%). High-volume transition weeks look like
  blowoff pops, not accumulation.
- **Daily-structure entries** — 438 signals, 69% win, **negative excess
  (−1.1%)**. Fires too often, no edge. Weekly stays.
- **Tight stops (−15%/−20%)** — stopped out 19 (of 34) eventual winners at
  −15%; average return fell by a third.
- **RSI>50 filter** — mildly better excess but weaker win rate on a small
  subset; not adopted, monitor.

## Caveats

66 events, one survivor-built universe, one broadly rising decade, quality
flags from 2026 fundamentals applied retroactively, stop simulation on weekly
lows (gap risk unmodeled). These are directional findings the paper account
is now forward-testing — not guarantees.


---

# Current Thinking (living section — update with every change)

*This page is the single source of truth for the system's logic. The portal's
Logic tab renders it live. When rules or hypotheses change, change THIS file
(and trade_paper.py constants in lockstep), and add a change-log entry.*

## Status of each layer

- **Mechanical core (ENFORCED)**: Rulebook v2 above — stage-3 entries,
  8%/4% sizing, group caps, spec-only −25% stop, 26-week clock. This is what
  the paper engine actually trades.
- **LLM risk officer (SHADOW)**: GO/CAUTION/VETO + regime gate computed
  nightly, logged against every trade, NOT enforced. Decision point: score
  the judgment log ~Oct 2026; flip ENFORCE_LLM only if VETO/RISK-OFF cohorts
  measurably underperform.
- **Narrative layer (HYPOTHESIS)**: weekly narrative-state + KOL stances +
  stage-2 "2+" flags are being logged, not acted on. GDELT historical study
  in progress (nightly trickle; full analysis due ~Aug 1 2026).

## Open hypotheses under test

1. **Narrative leads structure** — n=16 preliminary: tone inflections
   preceded ALL structural signals (median ~4 weeks). Looks supported;
   confirm at full sample.
2. **Narrative as CONTRARIAN conditioner** — n=16 preliminary (striking,
   unconfirmed): signals firing into still-gloomy narratives won 88% /
   +33.8% median; warmed-up narratives at entry LOST money (−14.5% median).
   If confirmed: comfort at confirmation = warning, fear = fuel. Do NOT
   trade on this until the full-sample study lands.
3. **"2+" early warning** — stage-2 names with positive narrative inflection
   should convert to stage 3 faster/more reliably. Forward-logged weekly.

## Review calendar

- Monthly: paper ledger vs rulebook (deviations logged).
- ~Aug 1 2026: full GDELT narrative study → update hypothesis 1/2 here.
- ~Oct 2026: LLM judgment-log scoring → ENFORCE_LLM decision. Also token
  renewals (3 places: Claude session, PRIVATE_REPO_TOKEN, .vbt_token).
- Quarterly: rule-lab rerun as the forward sample grows.

## Change log

- **2026-07-18** — Rulebook v2 adopted (rule lab on 66 events): spec-only
  −25% stop, MAX_PER_GROUP=4, no profit-taking confirmed, tight stops /
  volume filters / daily entries REJECTED. LLM screen deployed in shadow.
  Narrative layer added (weekly brief + KOL tracker + 2+ flags). GDELT
  study launched; n=16 preliminary shows contrarian inversion.
