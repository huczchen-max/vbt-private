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

*From the wide-universe base study (Sept 2026: 17,706 tickers incl. ~12k
delisted, 2009–2026, weekly bars, SPY control; details in the VBT project's
base-pattern doc and the master register H17–H23):*

- **Long-base breakout / composite trigger as an entry** (H17) — direction
  is predictable (composite 85% up vs mirror 14%) but the entry loses:
  −3.8 to −4.2% vs SPY, win 55%, negative excess in 14 of 18 years. The
  trigger fires 2–3 weeks before the break; it is a breakout-chase in disguise.
- **Tight bases / VCP** (H18, H21) — tight bases break up more often but the
  return effect is the low-volatility effect; volume dry-up predicts a DOWN
  break (abandonment, not accumulation); best cell +1.6% vs SPY on n=469.
- **Fundamentals as a base selector** (H20) — no cell clears the bar; high
  revenue growth at the trigger is the WORST cell (>50% growth: −7.8% vs
  SPY); the one positive cell was a 2020 recovery artifact.
- **RSI divergence, both directions** (H22) — the "IOVA shape": bottom
  divergence −2.8 to −5.6% vs SPY and no direction call; top divergence is
  followed by an UP break 2–3× more often than DOWN. Not an entry, not an exit.
- **MACD cross at the Elliott-oscillator trough, two-tranche entry** (H23) —
  equal to a random bar of the same base at the 1.5× band (+2.8% vs +4.3%,
  both ≈ −3.5% vs SPY) and worse at wider bands; the base breaks DOWN more
  often than UP after it (39% vs 28%); the ⅓ + ⅔ blend lowers the tail only
  by holding cash and gives up the return the confirmation costs.
- **Base-low invalidation for a test position** (H23) — closing below the
  base low fires on 41% of entries and makes them worse than holding
  (whipsaws). Same lesson as the tight stops above.

## Caveats

66 events, one survivor-built universe, one broadly rising decade, quality
flags from 2026 fundamentals applied retroactively, stop simulation on weekly
lows (gap risk unmodeled). These are directional findings the paper account
is now forward-testing — not guarantees.


---

# Current Thinking (living section — update with every change)

*This page is the single source of truth for the system's logic. The VBT
Console's Docs tab renders it from the local clone. When rules or hypotheses
change, change THIS file (and trade_paper.py constants in lockstep), and add
a change-log entry.*

## Status of each layer

- **Mechanical core (ENFORCED)**: Rulebook v2 above — stage-3 entries,
  8%/4% sizing, group caps, spec-only −25% stop, 26-week clock. This is what
  the paper engine actually trades.
- **LLM risk officer (SHADOW)**: GO/CAUTION/VETO + regime gate computed
  nightly, logged against every trade, NOT enforced. Decision point: score
  the judgment log ~Oct 2026; flip ENFORCE_LLM only if VETO/RISK-OFF cohorts
  measurably underperform.
- **Narrative layer (CONTEXT ONLY — settled 2026-08-01)**: full GDELT study
  (58/66 events, NARRATIVE_STUDY_FINAL.md) — narrative tone is NOT a timing
  signal. Weekly narrative-state + KOL stances remain logged for context.
- **Base-pattern layer (RISK FLAGS ONLY — settled 2026-09-12 → 09-23)**:
  `base_study_wide.py` v0.8 runs on the full US universe (Actions mode
  `study`; live lists in `base_summary.json`, charts in the VBT Console).
  Nothing from it is an entry. What it is allowed to do: (a) **ANTI state in
  a held name's base, especially with volume drying up** = "review, don't
  add" — the strongest breakdown warning measured (DOWN break 66–68%; with
  dry volume −13% vs SPY, win 43%); (b) quality and low pre-base volatility
  are sizing/risk inputs (MAE −10% vs −16%), never return predictors; (c)
  the live COMP / DIVUP / DIVDN / E1 / E2 lists are context for the Monday
  brief and the review page, to be labelled, not traded.

## Narrative hypotheses — RESOLVED (2026-08-01, n=58)

1. **Narrative leads structure** — PARTLY: tone troughs lead the signal on
   81% of events, but by a median 75d with IQR 20–135d. Real lead, useless
   spread. Context, not timing.
2. **Narrative as CONTRARIAN conditioner** — SOFTENED, not confirmed. Full
   sample: gloomy +26.2%/78% vs improving +21.3%/68% (p≈0.36). The n=16
   inversion was mostly noise. The effect concentrates in SPEC names:
   SPEC+improving-narrative = −13.9% median / 44% win (n=9, p≈0.26).
   RULE: improving narrative is never confirmation; SPEC signal + sunny
   narrative = caution flag (spec-minimum size), not a veto. QUALITY names:
   ignore narrative entirely.
3. **"2+" early warning** — the favorable-framing premise is contradicted
   (sunny cohort did worse everywhere it differed). "2+" flags stay logged
   as a neutral observation; no favorable interpretation.

## Long-base and indicator-timing hypotheses — RESOLVED (2026-09-12 → 09-23)

Seven hypotheses (H17–H23 in the master register), one answer: on weekly
bars, timing inside a base cannot be bought from price-derived indicators.
The composite state (MA13 > MA26 & RSI > 55), RSI divergence, a MACD cross
and the Elliott-oscillator trough are smoothers of the same closes; each
calls direction no better than the base's own history, and each entry loses
3–9 points to SPY on the wide universe, with negative excess in 12–15 of
the 17–18 years tested. The information in a base is in what it does *afterwards* — the
entries that worked are only identifiable once the composite or the second
tranche has arrived, which is hindsight — so selection (theme + quality,
Rulebook v2 Setup + Entry) keeps carrying the edge and the base study is
demoted to risk flags (layer status above).

H24 (23 Sep) closed the last open door: shown 300 historical bases blind
(no name, no date, no future), the operator's snap judgement bought the
visually confirmed turn (mid-band, RSI rising, ~9 months past the low) and
lost 8 points to the charts he passed on, with the same sign on random bars;
direction was read correctly and the return was negative anyway. Entries
stay mechanical; a discretionary override of the engine's entry is now
evidence-against, not merely untested.

Two nuances kept on record: the Entry tiebreaker "prefer EWO > 0 among
same-day stage-3 signals" stands — it was measured at the structure flip,
not inside a base, and H23 says nothing about that context; and a DIVUP
followed by an E1 in the same base tilted positive (+4 to +5%, win 58–64%,
n=65–75) — parked with the H21 low-vol cell as candidate universes for an
options paper test, not as stock entries.

## Review calendar

- Monthly: paper ledger vs rulebook (deviations logged).
- When GDELT trickle hits 66/66: refresh SPEC-flag numbers (n=9 → n≈12).
- ~Oct 2026: LLM judgment-log scoring → ENFORCE_LLM decision. Also token
  renewals (PAT expires 2026-10-16; it lives in the PRIVATE_REPO_TOKEN
  secret, .vbt_token, and the two scheduled-briefing prompts).
- Quarterly: rule-lab rerun as the forward sample grows; base study
  `study` mode rerun (cache is evicted after 7 idle days — `full` first).
- Label the divergence review page (weekly bottoms first) before any change
  to the divergence shape score.

## Change log

- **2026-07-18** — Rulebook v2 adopted (rule lab on 66 events): spec-only
  −25% stop, MAX_PER_GROUP=4, no profit-taking confirmed, tight stops /
  volume filters / daily entries REJECTED. LLM screen deployed in shadow.
  Narrative layer added (weekly brief + KOL tracker + 2+ flags). GDELT
  study launched; n=16 preliminary shows contrarian inversion.
- **2026-08-01** — Narrative study finalized (58/66 events): n=16 inversion
  softened to a weak SPEC-only caution flag; narrative demoted to context.
  Hypotheses 1–3 resolved above; weekly brief STEP 4 interpretation fixed.
- **2026-09-12/13** — Long-base study on the EODHD universe (H17–H19, H21):
  composite trigger, tightness, spring and contraction/volume dry-up all
  REJECTED as entries; ANTI + dry volume adopted as the review-don't-add
  risk flag; low-vol contracting R2.0 cell parked for an options test.
- **2026-09-14** — Fundamentals as a base selector (H20) REJECTED; quality
  kept as a sizing/risk input only.
- **2026-09-22** — RSI divergence states (H22) REJECTED both ways; R3.0
  band and rsi_slope26 kept in the study.
- **2026-09-23** — MACD + Elliott-oscillator two-tranche entry (H23)
  REJECTED as entry and as sizing rule; indicator-timing thread closed for
  weekly bars. Divergence screen (weekly/daily/hourly lists + local review
  page) and the local VBT Console replace the public dashboard; GitHub
  Pages deployment removed.
- **2026-09-23 (later)** — H24 blind-labelling test of the operator's eye
  REJECTED (BUY −10.4% vs PASS −2.1% vs SPY; direction right, return wrong).
  Plan to tune the divergence shape score to hand labels dropped.
- **2026-09-24** — Housekeeping: old GitHub Pages site unpublished and
  vbt-data made private; both scheduled briefings fetch signals.json with
  the token; H24 labels and score committed. No rule change.
