# Narrative Lead/Lag Study — Final Report

*GDELT news-tone vs the 66 VBT-1 recovery events · final analysis 2026-08-01.*
*Data: nightly GDELT trickle, 60/66 events fetched, 58 with usable tone series
(~90 trading days of daily average news tone before each stage-3 signal date).*

---

## The question

When our structural BOTTOM signal fires, does the news narrative around the
name tell us anything about the trade's outcome? The preliminary cut (n=16)
showed a striking **inversion**: improving narrative at the signal → *worse*
26-week returns (−14.5% median, 38% win) while gloomy narrative → far better
(+33.8%, 88% win). This report is the full-sample verdict.

**Measure:** `ndelta` = mean tone over the 14 days before the signal minus
mean tone over days 30–90 before. Positive = narrative improving into the
signal; negative = still gloomy.

## Verdict: the inversion SOFTENED — it did not hold at preliminary strength

Full sample (58 events, 26-week forward returns):

| Narrative at signal | n | median ret26 | mean | win rate |
|---|---|---|---|---|
| Improving (ndelta > 0) | 22 | +21.3% | +18.0% | 68% |
| Gloomy (ndelta ≤ 0) | 36 | **+26.2%** | **+32.6%** | **78%** |

The direction survives — gloom at the signal is still the better
configuration — but the gap is +4.9% of median and 10 points of win rate,
not the 48-point chasm the first 16 events suggested. A permutation test
puts the median gap at **p ≈ 0.36**: consistent with the contrarian story,
nowhere near proof of it. Terciles are not monotonic either (gloomiest
tercile 79% win, sunniest 70%, but the *middle* tercile has the best
median). The n=16 result was largely small-sample noise.

## Where the effect actually lives: SPEC names

Split by the quality tag, the story sharpens considerably:

| Segment | n | median ret26 | win rate |
|---|---|---|---|
| QUALITY · gloomy | 18 | +27.1% | 83% |
| QUALITY · improving | 13 | +21.3% | 85% |
| SPEC · gloomy | 18 | +16.7% | 72% |
| SPEC · improving | 9 | **−13.9%** | **44%** |

On QUALITY names narrative tone carries **no information** — the signal
works either way. The entire inversion is concentrated in **speculative
names whose narrative has already turned sunny before the structural
signal confirms**: 44% win, negative median. The economic reading is
plausible — a spec name that everyone already likes at the bottom has
pulled forward its re-rating; the recovery is pre-bought. But n=9, and
even the SPEC gloom-vs-sunny gap (+30.6% median) only reaches p ≈ 0.26.
Suggestive, unproven.

## Lead/lag timing

- Smoothed (7-day) tone **troughs a median of 75 days** before the
  structural signal (IQR 20–135d); 81% of events had their narrative
  trough ≥14 days before the signal.
- The narrative **inflection** (sustained tone recovery off the trough)
  leads the signal by a median of ~80 days, with enormous spread.

So narrative repair usually *precedes* structural confirmation — but with
an interquartile range of four months, it is context, not a timing tool.
Nothing here beats the structure engine at picking the entry week.

## What goes in the rulebook

1. **Narrative tone is NOT a timing signal.** Neither waiting for gloom
   nor waiting for improvement adds anything on QUALITY names.
2. **Improving narrative is never confirmation.** The old "positive
   narrative inflection = favorable early-warning" framing is contradicted
   by the data — the sunny cohort did *worse*, everywhere it differed.
3. **One mild flag survives:** a SPEC-tagged signal arriving with a
   rapidly improving narrative (ndelta clearly positive) is the weakest
   configuration we measured (44% win, n=9). Treat it as a caution flag —
   size at the spec minimum — not a veto. Re-examine when the last 6
   events trickle in and future signals accumulate.
4. **Gloom at the signal is normal and fine** (62% of all events). Fear in
   the headlines while structure confirms is the majority case of a
   working signal — not a warning, and not a bonus either.

## Housekeeping

- The one-off bulk study workflow (`study.yml` + trigger) is retired; the
  nightly 6-event GDELT trickle in `fetch.yml` continues until 66/66,
  after which it self-stops.
- Raw data: `gdelt_raw.json` (private repo); per-event ndelta table
  reproducible from it in ~20 lines.

*Honest-numbers note: this study replaces the preliminary "inverted
narrative" finding quoted in earlier docs. Where the playbook said gloom
is THE favorable configuration, read: gloom is normal; sunny-SPEC is the
one configuration to distrust.*
