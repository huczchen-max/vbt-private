# VBT — Master Document

*Source of truth for the VBT systematic trading project. Version 1.4, 23 September 2026. Every figure below is traceable to a file in vbt-private, a project doc, or a dated conversation; where a number is an estimate it is marked as such. This documents a personal, paper-first systematic process; it is not investment advice.*

## Project brief

**Outcome:** One document that lets Eric (or a future Claude session) re-enter VBT cold and know what it is for, what exists, what has been proven or rejected, and what to do next.
**Audience:** Eric. Full detail, candid about failures.
**Constraints:** Paper money only until the record earns size. Every rule must be earned by a test. No credentials or account numbers in this document.
**Tone/style:** Plain, evidence-first, teal/slate. Facts, assumptions and preferences kept separate.
**Inputs:** vbt-private (THE_STRATEGY.md, RULEBOOK.md, ONE_WINNER_PLAYBOOK.md, NARRATIVE_STUDY_FINAL.md, study result JSONs, paper ledgers), vbt-data workflows, the VBT project docs (judgment logs, base-pattern study), and the September 2026 sessions.
**Deliverable format:** This Markdown master (kept in the VBT project and in vbt-private), a Word rendering, and a companion deck regenerated from it.

## North Star

**Goal:** Compound a personal recovery-strategy portfolio through a rules-based, paper-first system that removes discretionary error, and grow it only as fast as the logged record justifies.
**Audience:** Eric as operator; future sessions as maintainers.
**Constraints:** Weekly causal bars decide; paper account first; no leverage on margin; every new idea must clear the Rulebook bar (76% win, +25% median at 26 weeks, positive excess vs benchmark) before it becomes a rule.
**Must-include:** A written, dated, later-scored judgment for every decision; a hypothesis register with rejected ideas kept visible; a monthly ledger-vs-rulebook review.
**Must-avoid:** Breakout chasing, profit-taking on winners, tight stops, daily/hourly timing, acting on narrative tone, untested "improvements" slipped into the engine.
**Tone:** Expectancy × survival × time. When a rule and a feeling disagree, the rule wins.

---

## 1. The problem we are solving

The starting point was a portfolio that needed to recover, and a recognition that discretionary decisions under stress were the main source of error: chasing strength, selling winners early, adding on emotion, and reading news as signal. The design question became: what part of investing actually pays without foresight, and can that part be reduced to rules that a machine executes and a person only supervises?

THE_STRATEGY.md answers with three asymmetries. Selection (owning quality names inside secular themes: the same entry signal that merely market-performs on a random stock earns about +12% median excess on a well-chosen one). The fat tail (means are 2–3× medians; one or two holdings make the decade, so the right tail is never capped). Time horizon (sitting through drawdowns the crowd structurally cannot sit through is the only edge institutions cannot copy). Everything built since exists to collect those three with discipline.

The secondary problem is trust. A rule is only worth following if it was tested, so VBT was built as a laboratory as much as a trading engine: every rule carries its evidence, and rejected alternatives stay listed so they are not re-tried by accident.

## 2. Principles (from THE_STRATEGY.md and RULEBOOK.md)

Enter through two doors only: the weekly swing-structure flip from Mixed to Uptrend after a ≥30% correction (the aggressive door: 76% win, +25.3% median at 26 weeks) or the 13/52-week MA cross (the calm standing gate). Never chase 52-week-high breakouts; they lose to holding the ETF.

Hold without exit rules. Every tested exit destroyed wealth (the best kept 82 cents of the hold dollar). A broken trend triggers a review, never an automatic sale. Drawdown control comes from sizing: quality names 8% of equity, speculative 4%, max 15 positions, max 4 per group, catastrophic −25% stop on speculative names only, 26-week clock.

Add whenever capital allows inside an intact trend; waiting for pullback patterns tested worse than adding on a random week. No profit-taking before an exit rule fires (selling half at +25% cut average return from 33.7% to 24.6%).

Options: sell the side you don't want and keep the side you do. Put spreads below names you would own more of; never covered calls on conviction holdings; defined risk; no premium selling within 14 days of earnings or when IV is cheap; in parabolic runs stop selling premium and never buy puts to call the top.

Timeframes know their place: weekly decides regime, daily colors character, hourly is for execution only. Exhaustion grades risk and never triggers entries.

Discipline: every judgment written, dated and scored later; paper record first; the rule wins over the feeling.

## 3. What we built

### 3.1 Architecture

Two GitHub repositories. **vbt-data** holds the workflows, the fetched market data and the nightly signal snapshot (docs/signals.json, docs/index.html); it was the public shell of the project until 23 September, when the GitHub Pages deployment was removed from `fetch.yml`; once Eric unpublishes the old Pages site and flips the repository to private (§8), nothing is published any more. **vbt-private** holds every script, rulebook, ledger and study result. All dashboards are now browsed locally through the **VBT Console** (`vbt-private/console/index.html`, launched by double-clicking `VBT Console.command`, which serves ~/Projects on 127.0.0.1 only): nine tabs — overview, VBT-1 tracker, VBT-2 thesis book, options, scanners (radar, winners, exhaustion), bases (live screen, gallery), divergence (the review page embedded, strict lists per scale, chart pages), symbol charts (candles, Bollinger, MACD, RSI from data/prices.csv) and the documents/study results — all read straight from the two clones, so a `git pull` is the refresh. Each Actions run clones vbt-private with a PRIVATE_REPO_TOKEN, runs the pipeline, and commits results back. One-off jobs are started by committing a trigger file whose first word is the mode (for example `base-trigger.txt` → `fund`). Secrets live in vbt-data Actions: Alpaca paper keys, the Anthropic key, EODHD_API_KEY, PRIVATE_REPO_TOKEN.

Fourteen workflows exist. Four are scheduled: `fetch.yml` (nightly 21:45 UTC Mon–Fri: market data, signals, the VBT-1 paper engine, the LLM shadow screen, the GDELT trickle), `radar.yml` (Saturday breakout radar), `tracker.yml` (Saturday thesis tracker for VBT-2), `winners.yml` (Saturday winner screen, quarterly LLM pass). The rest are one-off study labs (exit, collar, hourly, hpat, l1, l23, overlay, phase1, thesis fundamentals) and the new `base.yml` (EODHD base-pattern study with seven modes).

Outside GitHub, two scheduled Claude tasks read the dashboards and write judgment logs into the VBT project: a daily signal briefing (22:30 UTC Mon–Fri) and a Monday weekly brief (13:00 UTC). Their logs are `claude/narrative-judgment-log*.md`.

### 3.2 Engines

**VBT-1, the recovery engine** (`trade_paper.py`, v1.0): nightly, it reads signals.json, buys any ticker that transitions into stage 3 (confirmed recovery) at the next open, sizes 8%/4%, enforces group caps, sells on breakdown to stage 1–2, on the speculative −25% stop, or at 182 days. Runs on the Alpaca paper account. `ENFORCE_LLM = False`: the LLM risk officer's GO/CAUTION/VETO and regime verdicts are logged against every trade but not enforced.

**VBT-2, the thesis book** (`trade_thesis.py`, `thesis_tracker.py`): a conviction sleeve (~40% of equity) of theme leaders scored on fundamentals and trend, with a weekly "door" (IN-TREND / BROKEN) per name and per theme ETF. Holdings since 19 July: MU, GH, LLY, BE.

**Options engine** (`options_engine.py`): proposes bull put spreads and cash-secured puts under the playbook's gates (trend intact, not parabolic, no earnings within 14 days, IV−RV positive); paper journal only. Sixteen open paper positions and five new proposals on 12 September.

**Supporting scanners:** breakout radar, winner screen, exhaustion watch (TOP/BOTTOM flags), IV log, thesis fundamentals.

### 3.3 Data layer (new, September 2026)

Yahoo scraping was replaced for wide-universe research by EODHD (plan upgraded to All-In-One on 12 September, which adds fundamentals, news, screener and intraday). `eodhd_fetch.py` pulls the full US common-stock universe including delisted names (17,886 tickers since 2009, 36 minutes) into a parquet cache that lives in the Actions cache rather than git; `fund_fetch.py` pulls point-in-time fundamentals. The sandbox and the Mac cannot reach EODHD, so all pulls and studies run in Actions; Eric pushes from clones at ~/Projects/vbt-data and ~/Projects/vbt-private.

## 4. Outputs

**Rulebook v2** (adopted 18 July 2026) with evidence per rule and a "Tested and rejected" list; **THE_STRATEGY.md** (one page); **ONE_WINNER_PLAYBOOK.md** (five layers for farming a confirmed winner, worked on MU); **NARRATIVE_STUDY_FINAL.md**; the base-pattern study doc in the VBT project.

**VBT-1 paper ledger, 18 July → 11 September 2026 (facts):** 30 ledger entries: 12 buys, 6 sells, 12 skips (all skips were group caps in semis/hardware). Sells: three "left universe" (BE, GH, LLY, later reinstated on the VBT-2 side), SNPS and MOD on structure breakdown, CORZ on the −25% speculative stop (−25.9%). Account equity $99,225 with $16,497 cash; total P&L +$1,428 on a ~$100k paper account. Thirteen positions: BE +22%, COHR +23%, INTC +18%, NBIS +13%, MU +9%, GH +3%, KLAC +2%, GLXY +2%, LLY −5%, ON −8%, CIEN −9%, WDC −16%, TLN −18%. Interpretation, not fact: eight weeks is far too short to judge a 26-week strategy; the useful signal so far is that the engine executed every rule without deviation.

**VBT-2 snapshot (12 Sep):** account equity $99,262; VBT-2 budget $39,705; stock sleeve $31,764; options sleeve $7,941 with $7,735 committed. Theme health: AI IN-TREND (SMH −13.8% from high, 74% of names intact), grid IN-TREND (48% intact). Events this week: ARM and QCOM new bottoms; APLD, TXT, PL trend-broken; AXON, IGV repaired.

**Dashboards and logs (all private, read by the local VBT Console):** signals.json/index.html, paper.json, thesis_state.json, radar_watch.json, exhaustion_watch.json, winners.json, llm_log.jsonl, and the two Claude judgment logs (daily since July, weekly on Mondays).

## 5. Hypothesis register

Each row: what was asked, how it was tested, what came back, and what was decided. Rejected ideas stay here so they are not re-tested without new evidence.

| # | Hypothesis | Test | Result | Decision | Date |
|---|---|---|---|---|---|
| H1 | Dip-buying after a ≥30% correction has excess return | 66 events, 45 AI-infra names, 10 years, causal weekly structure | Without the structure trigger: zero excess vs SMH (−1.1%) | Setup alone is not a signal | 2026-07-18 |
| H2 | Weekly structure flip Mixed→Uptrend inside the setup is the entry | Same lab | 76% win, +25.3% median at 26 wks; the only trigger with positive excess vs SMH | ADOPTED as the aggressive door | 2026-07-18 |
| H3 | Quality vs speculative deserve different sizes | Same lab, GAAP-profit + FCF flag | Quality 83% win, −12.6% MAE; spec 68% win, −20.9% MAE, +33.7% median | 8% / 4% sizing ADOPTED | 2026-07-18 |
| H4 | Volume ≥1.2× on the transition week improves entries | Same lab | Worse: +13.9% median, −10.2% excess | REJECTED | 2026-07-18 |
| H5 | Daily-structure entries add edge | 438 signals | 69% win but −1.1% excess; fires too often | REJECTED; weekly stays | 2026-07-18 |
| H6 | Tight stops (−15/−20%) protect returns | Same lab | Stopped 19 of 34 eventual winners; average return fell by a third | REJECTED; spec-only −25% stop kept | 2026-07-18 |
| H7 | Profit-taking at +25% helps | Same lab | Half at +25%: 33.7% → 24.6%; all: → 15.4% | REJECTED; no profit-taking | 2026-07-18 |
| H8 | Any exit rule beats holding | Exit lab, 170 names, 10 yrs, five exits | Best (combo) kept 0.82 of hold wealth; structure exit 0.64; MA52 0.52 | Hold without exits; breaks trigger review only | 2026-07-19 |
| H9 | Collars cut drawdowns cheaply | 170 stocks + 19 ETFs, BS-priced | Stock max-DD −57% → −48% at 0.80 of hold wealth | Insurance for sleep on oversized positions only | 2026-07-19 |
| H10 | Hourly patterns carry timing skill | 37 names, 730 days | Hourly up/down events ≈ control at 1/3/5 days | REJECTED; hourly = execution only | 2026-07-19 |
| H11 | Daily TOP/BOTTOM pivot patterns time options | hpat study | TOP pattern followed by +1.6% median 3-day drift in parabolic regimes | Never buy puts to call a top; capitulation bounce ~2:1 | 2026-07-19 |
| H12 | Bottom vs breakout signals across a wide universe | Phase 1: 6,177 symbols scanned, 2,728 liquid | Bottom 26-wk +8.7% (−2.3% vs bench); breakout +4.1% (−2.7%); only 28% of bottoms graduate to breakouts, median 24 wks | Confirms bottoms beat breakouts; neither beats the ETF unfiltered | 2026-07-19 |
| H13 | L1 bottom signal on the tracked universe | 172 names, 266 events | 26-wk +9.7% median, 52-wk +24.6%, 104-wk +53.3%; excess vs bench ≈ 0 at 26/52 wks | Selection (theme + quality), not the trigger, carries the excess | 2026-07-19 |
| H14 | Put-spread income overlay on winners | 160 names, 10 yrs, ≥4× winners n=71 | 91.5% of names net positive, 2.3%/yr median at conservative pricing, ~6% of hold P&L | ADOPTED as Layer 2, small by design | 2026-07-20 |
| H15 | News narrative leads or conditions the structural signal | GDELT tone, 58 of 66 events | Trough leads by median 75 d (IQR 20–135); gloomy +26.2%/78% vs improving +21.3%/68%, p≈0.36; SPEC+sunny −13.9%/44% (n=9) | Context only; SPEC+sunny = size at minimum, not a veto | 2026-08-01 |
| H16 | LLM risk officer improves entries | Shadow verdicts logged per trade | Running; 4 valid verdict days then API failures from 10 Aug (see §7) | Decision deferred; fix the call first | open |
| H17 | Long-base pattern (base → grind → break) is an entry door | 17,886 tickers incl. delisted, 29,565 events, 57,643 signals | Direction predictable (composite 85% up vs anti 14%) but composite-trigger entry −3.8/−4.2% vs SPY, 55% win, negative excess 14 of 18 yrs | NOT an entry door; ANTI state = "review, don't add" flag; live list = context | 2026-09-12 |
| H18 | Base tightness (MAD/median) changes the answer | Bins <4% … >15%, pre-base volatility control | Tight bases break up more (79% vs 38%) but return effect is the low-volatility effect; best cell +0.1% vs SPY | Direction yes, magnitude no | 2026-09-12 |
| H19 | Prior shakeout (spring) predicts the break | SPRING flag | 50/50 direction; weak tilt at R2.0 only | No effect | 2026-09-12 |
| H20 | Fundamentals (growth, acceleration, surprise, quality, short interest) select the winning bases | Point-in-time join, 89% coverage (51,180 signals), 200-day stale guard | No cell clears the bar. Growth is inversely related to outcome (R2.0 revenue >50% → −7.8% vs SPY, 49% win; <0% → −1.4%, 61%); the Rulebook growth+accel+quality screen is market-like (−4.2% vs SPY, 53% win, n=412); the one positive cell (low-vol, shrinking revenue, +5.3% vs SPY, n=640) is a 2020 artifact — ex-2020 every cell is negative vs SPY. Quality cuts MAE (−10% vs −16%) and adds 5 pts of win rate but also trims the upside tail | NOT a selection layer for bases; keep quality as a sizing/risk input; fundamentals thread closed for this pattern | 2026-09-14 |
| H21 | Contraction into the trigger (tail-8 MAD ÷ base MAD) and volume dry-up identify the good tight bases | v0.6, 27,065 events / 57,643 signals, LMAX applied, flat-line guard | Contraction alone: no information at R1.5 (−3.7 to −4.1% vs SPY in every bin), modest at R2.0. Volume dry-up is a NEGATIVE signal: dry bases break DOWN (19–35% up vs 55–61% when volume rises); dry composite triggers −5 to −9% vs SPY. Tight bases earn 2–3× more per unit of MAE but the edge vanishes once sized to equal expected vol. Best cell in the whole study: R2.0, listed, low-vol, contracting, non-dry → +11.7%, +1.6% vs SPY, 66% win, MAE −8.3%, n=469 | Not an entry door. Keep: ANTI + dry volume = strongest breakdown warning (−13% vs SPY, 43% win); low-vol contracting R2.0 cell = candidate universe for the long-call paper test | 2026-09-13 |
| H22 | RSI divergence (price flat, RSI higher highs — the IOVA shape) is an early entry; its mirror is an early exit | v0.7, R ∈ {1.5, 2.0, 3.0}, 75,467 signals, DIVUP/DIVDN states with pivot-based RSI swing highs | DIVUP: −2.8 to −5.6% vs SPY, win 51–57%, next break UP only 11–28%; the ones that worked (+8 to +13% vs SPY) are only identifiable after the composite trigger arrives 9–12 wks later. DIVDN: base breaks UP 2–3× more often than DOWN afterwards (+3.5%, win 57%); precedes only 3.5% of ANTI warnings. RSI slope at the composite trigger grades it mildly (rising-fast −2.6% vs falling-fast −9.0% vs SPY). R3.0 behaves like R2.0 | NOT an entry, NOT an exit; keep rsi_slope26 as a tie-breaker; divergence thread closed | 2026-09-22 |
| H23 | MACD crossover coinciding with an Elliott-oscillator bottom = test entry; support bounce or EO > 0 = main entry (two tranches, ⅓ + ⅔) | v0.8: causal MX/E1/E2 states inside open bases, random-bar control, ⅓+⅔ blend with three invalidation variants, MACD-alone baseline; 17,706 tickers, 7,852 E1 | E1 = the random-bar control at R1.5 (+2.8% vs +4.3%, both −3.5% vs SPY, win 55%) and worse at wider bands (−0.1% / −4.2%, −6.7 / −8.6% vs SPY); the base breaks DOWN more often than UP after it (39% vs 28%); MACD alone beats MACD + EO; E2 confirmation earns ~0 (+2.1 / 0.0 / +0.3%) and the support-bounce variant is the weaker one; the ⅓+⅔ blend +0.3% vs +3.0% for a single entry, same tail per unit of capital; 25–32% of E1s are stranded (−12 to −27%, DOWN break 78–84%); base-low invalidation worse than holding | NOT an entry, NOT a sizing rule; indicator-timing thread closed for weekly bars (with H22); keep "MACD/EO turn inside a base = bounce, not bottom" as a do-not-add note | 2026-09-23 |
| H24 | Eric's eye: does blind chart reading (no name, no dates, no future) separate the bases that go on to outperform? | `label` mode: 300 decision bars (40% random / 25% DIVUP / 15% E1 / 10% COMP / 10% ANTI, listed + delisted) + 30 repeats; Buy/Pass/Unsure on a blinded page, one sitting (33 min, 3.2 s/chart); pre-registered scorer | BUY −10.4% vs SPY (win 41%, n=126) vs PASS −2.1% (win 54%, n=168): −8.3 pts, p = 0.997 for the hypothesised direction (reverse p = 0.005); same sign on random bars (−11.1) and DIVUP (−7.8); BUYs = mid-band, RSI 54 and rising, 39 wks after the low — the visible turn, already priced; direction read correctly (UP break 41% vs 24%) but return negative; repeat agreement 73% (κ 0.48) | NEGATIVE: the eye buys the confirmed turn, the error the Rulebook removes; mechanical entries stay mechanical; shape-score tuning to labels dropped; contrarian reading noted, not adopted | 2026-09-23 |

## 6. What we learned

Selection carries the edge, triggers carry the timing. Across the labs the same bottom trigger earns roughly zero excess on a random liquid stock and double-digit excess on a theme-and-quality name. This is why VBT-2 exists next to VBT-1.

Timing skill dies as the timeframe shrinks. Weekly structure was the only level where a trigger beat its control; daily fired too often for no excess; hourly matched noise. Five studies in a row agreed.

Every exit tested cost more than it saved. This is the most counter-intuitive and most consistent finding, and it is why breaks trigger a review rather than a sale, and why drawdown control lives in sizing.

Direction is often predictable; return is not. The base study is the clearest case: the composite state calls the break direction 85% of the time, yet buying on it loses to SPY because the break is already priced by the time the state is visible. A good classifier is not a good trade.

Controls change conclusions. "Tight bases work" became "low-volatility names work" once pre-base volatility was held constant; the n=16 narrative inversion became noise at n=58. Small samples and missing controls produced every exciting early result.

Survivorship matters. Phase 1 was survivorship-biased and said so; the EODHD universe includes ~12k delisted names, and 38% of base events belong to them. Wide studies now start from that universe.

Infrastructure is most of the work, and it pays back. Trigger files, the private/public split, the Actions cache, the Mac push ritual and the point-in-time join were each a day of friction; every study after them took hours.

Volume tells direction, not quality. In the base study, volume drying up into the bar was the single strongest directional feature, and it pointed DOWN: abandonment, not quiet accumulation. The VCP folklore did not survive contact with 27,000 events; neither did RSI divergence in either direction (H22), nor a MACD cross at the Elliott-oscillator bottom (H23: equal to a random bar of the same base, and a two-tranche entry on it only lowers the tail by holding cash), and neither did the idea that fundamentals pick the bases that break out: the growth-and-quality screen that carries the excess at L1 bottoms carries nothing at a long base, and the only positive cell was a 2020 recovery artifact.

Negative results compound. The rulebook's "Tested and rejected" list and this register are the assets that stop the same idea from being re-tried in a weaker moment.

The operator's eye is a momentum indicator. Shown 300 bases blind — no name, no date, no future — Eric bought the ones that had visibly turned (mid-band, RSI rising, nine months past the low) and passed on the unconfirmed lows; the BUYs lost 8 points to the PASSes (H24). Direction was read correctly and the return was negative anyway, which is the base study's central finding in human form: what is visible is priced. This is the strongest argument in the project for keeping entries mechanical.

## 7. Current status and health (23 September 2026)

**Running:** nightly fetch and paper engine, Saturday radar/tracker/winners, both Claude briefings.

**Resolved 12 Sep:** the LLM shadow screen had returned "HTTP 400" on every call since 10 August. Root cause (surfaced by logging the API error body): the Anthropic API account had run out of prepaid credits. Credits added 12 Sep; the first valid verdicts are expected on the next weekday run. The shadow record has a five-week hole (10 Aug–12 Sep) that the October ENFORCE_LLM scoring must account for. `llm_screen.py` now logs the API's own error text; the workflows read `LLM_MODEL` from a repository variable.

**Fixed 12 Sep:** `fetch.yml` pushes now rebase before pushing (a push race with a manual commit failed run #64). Event detector now applies the 156-week maximum base length (events 29,565 → 27,065).

**Resolved 14 Sep:** the fundamentals pull completed in one run after restricting it to the 7,259 study tickers and parsing EODHD's flattened response (7,256 ok, 10 min); H20 recorded (negative). The point-in-time fundamentals table (income, cash flow, earnings, snapshot with short interest) was cached for reuse — note the Actions cache is evicted after 7 idle days, so it is gone again and would need a one-day re-pull.

**Resolved 22 Sep:** base study v0.7 (RSI divergence states, R3.0 band, rsi_slope26) ran on a fresh full pull (17,706 tickers, 45 min end to end); H22 recorded (negative both ways). Found and fixed a bug that had left the live pages of the v0.6 gallery blank (`r.asof` name collision); a `gallery` trigger mode now re-renders charts without re-running the study.

**Done 23 Sep (privacy + local console):** the divergence screen (`screen` trigger mode: weekly + daily on the full liquid US universe, hourly on the open-base subset via EODHD intraday) produces ticker lists, chart pages and a self-contained review page (`div_screen/div_review.html`, Y/N/unsure labels kept in the browser, CSV export) — 277 strict names on 21 Sep. Every dashboard moved into the local VBT Console; `fetch.yml` no longer builds or deploys GitHub Pages (the nightly fetch, signals, paper engine and LLM screen are unchanged); pending on Eric's side: unpublish the old Pages site and make vbt-data private, after which Actions minutes count against the private-repo allowance (2,000 min/month on GitHub's free plan; the nightly job is ~5 min, a `screen` run ~35 min, a `full` study ~45 min — roughly 400–600 min/month at the current cadence).

**Resolved 23 Sep (H24):** the blind-labelling test of Eric's own pattern recognition ran the same day (run #17, 330 charts, labelled in 33 minutes): negative — the BUY set lost 8 points to the PASS set, with the same sign on the random bars; the eye buys the visually confirmed turn. Recorded in the register and the base-pattern doc; tooling (`label_set.py`, `label_template.html`, `label_score.py`, Actions mode `label`) stays for any future set.

**Rulebook updated 23 Sep:** the wide-universe results (H17–H23) are now in RULEBOOK.md — six rejected items, a "Base-pattern layer (RISK FLAGS ONLY)" status entry, a resolved-hypotheses block, and change-log entries; the Console's Docs tab renders it.

**Resolved 23 Sep:** H23 (MACD + EO two-tranche entry) ran as base study v0.8 (run #16, 34 min, 129,441 signal rows) — negative as an entry and as a sizing rule; recorded in the register and the base-pattern doc. The review page and console now carry MACD/EO panels and the E1/E2 markers; the gallery has `e1_hits`, `e1_stranded`, `live_e1`, `live_e2` pages.

**Calendar:** Oct 16 PAT expiry (rotate; move it out of the scheduled-task prompts); Oct 17 Exhaustion-Watch scoring; October LLM judgment-log scoring and ENFORCE_LLM decision; monthly ledger-vs-rulebook review; quarterly rule-lab rerun as the forward sample grows.

## 8. Open questions and next steps

**Primary (this week):** commit the H24 labels and score to vbt-private; "update both prompts" (scheduled briefings) → unpublish Pages → vbt-data private; verify the weekday LLM verdicts (Overview tab: raw_ok). The research programme's honest state after H17–H24: nothing beats the benchmark out of the wide universe, including the operator's eye; the only live claim is selection (VBT-1/VBT-2 forward record) — leave it running and stop adding entry ideas until it has twelve months.

**Secondary:** test the ANTI-composite state as a "review, don't add" trigger against the paper ledger's stage-3 breakdown exits (does it fire earlier, and would it have helped on SNPS, MOD, CORZ?); label the 45-name base gallery so the detector is checked against the pattern Eric means.

**Later:** decide the options data source (Alpaca preferred) and paper-test a long-call/call-spread book on the R2.0 low-vol contracting cell (H21) and a mid-band premium-harvest book on tight bases (v0.7 measurements first: mid-band break hazard at 6/9 weeks; edge-bounce returns with and without the ANTI state); EODHD news sentiment as a contrarian check on SPEC signals. (H17–H23 were written into RULEBOOK.md "Current Thinking" on 23 Sep: rejected list extended, base-pattern layer added as risk flags only, change log updated.)

## 9. Retrospective

**What worked well:** committing to one evidence bar and applying it to every idea, including this month's; keeping every hypothesis and its rejection in writing; moving all computation into Actions so the system runs unattended; the paper engine executing without a single rule deviation in eight weeks.

**What was slow:** GitHub plumbing (tokens, protected workflow files, non-fast-forward pushes, index locks) consumed most of two sessions; the first base-study "tightness" measure was an artifact of the detector and had to be replaced; the sandbox's inability to reach data providers meant every iteration went through a 15–40 minute Actions run.

**Where misunderstandings occurred:** placeholder paths taken literally; which folder to connect; whether fundamentals were being analyzed for everything or only candidates (data for all, analysis for candidates).

**What needs human verification:** the LLM model fix; the EODHD fundamentals field names (fsmoke passed but its output was not inspected); whether the base detector matches Eric's visual pattern (gallery labels); the October token rotations.

**Reusable assets:** the Actions trigger-file pattern and private/public split; `eodhd_fetch.py` and the parquet cache; the point-in-time fundamentals join; the base detector and signal framework (any weekly pattern can be dropped into it); this register and the deck generator.

## Appendix A — Facts, assumptions, preferences

**Facts** are the numbers in §4–§5 and the file list in Appendix B.
**Assumptions:** 26-week horizon as the judging window; SPY/SMH as controls; composite thresholds 0.66/55 and FLAT 0.4 not swept; the Rulebook's 66-event lab is one survivor-built universe in one rising decade; quality flags from 2026 fundamentals applied retroactively; options overlays priced with Black–Scholes without skew.
**Preferences (Eric's):** paper first; no margin; teal/slate documents; 1 primary + 2 secondary next steps; weekly feedback loop; retrospectives at milestones.

## Appendix B — File map

vbt-private: THE_STRATEGY.md · RULEBOOK.md · ONE_WINNER_PLAYBOOK.md · NARRATIVE_STUDY_FINAL.md · trade_paper.py · trade_thesis.py · thesis_tracker.py · options_engine.py · llm_screen.py · compute_signals.py · fetch_data.py · eodhd_fetch.py · fund_fetch.py · base_study_wide.py · base_fund_study.py · study scripts (exit, collar, hourly, hpat, l1, l23, overlay, phase1, narrative) with *_results.json · ledgers (paper.json, thesis_paper.json, options_paper.json, thesis_ledger.csv, llm_log.jsonl) · base_events.csv, base_signals.csv, base_live.csv, base_summary.json.
vbt-private (browsing): console/index.html · VBT Console.command · div_screen/ (div_screen.csv/json/md, chart PNGs, div_series.json, div_review.html, div_review_template.html) · gallery/ · div_screen.py · intraday_fetch.py.
vbt-data (to be made private, 23 Sep): .github/workflows (14) · data/prices.csv · docs/signals.json, docs/index.html · trigger files.
VBT project (claude.ai): claude/narrative-judgment-log*.md · claude/base-pattern-study.md · this master document.

## Appendix C — Glossary

Stage 3: confirmed weekly recovery (swing structure Mixed → Uptrend after a ≥30% correction). Door: weekly IN-TREND/BROKEN status per name. Quality: GAAP-profitable and FCF-positive. MAE: maximum adverse excursion. Composite / ANTI: the base study's ready-to-break state and its mirror. MAD/median: base tightness. Spring: a downside break shortly before a base begins. ENFORCE_LLM: flag that would let the LLM risk officer veto trades.
