# Orkestra playbook

Which subagent combination for which goal. The leader does not read this file end to end: it reads the section that
fits the task (table of contents) and, when needed, the priority table. Think in **roles**, not model names; the
selector picks the concrete model every time (`kapasite.py --sinif ...` or `--rol ...`). Model examples below are
typical results with today's quota, not rules. An explicit user instruction overrides any route.

Abbreviations: S = `scripts/kapasite.py`, E = `scripts/evren_suru.py` (free platform client, EVREN as the example).
Z/Q: AA v5.0.1 intelligence score / class threshold. WU (İB): a medium job of ~40-60K tokens. "Different family":
claude, gpt, gemini, glm, deepseek.
`--dogrulayici` takes the **producer model's name**, not a family name (e.g. `--dogrulayici gpt-6.1-sol`, `sonnet`,
`flash`); the selector derives the family. `--dogrulayici gpt` is an error (exit 2). Always pass it with `--rol`:
without it no family is excluded. The free platform only meets the threshold of mechanical/simple classes (Z ≤ 28): for
the free-platform sub-step of a research/normal/code job, run the selector separately with `--sinif basit --veri genel`;
the merge/decision step is selected with its own class.

## Contents
1. Priority table (who goes first, when)
2. Roles (watchdog, checker, judge, messenger, archivist, devil's advocate) and how to call them
3. Free platform resilience: decision tree for a busy or rate-limited server
4. Patterns: 1-12
5. Scenarios: code (13-24), research and text (25-33), media (34-38), quota/time/privacy (39-50), mixed cases (51-53)
6. Creative mode: design a route the playbook does not cover
7. Discovered routes (approved additions)

---

## 1. Priority table

Read each row left to right; a condition narrows the previous one, it does not override it.

| Condition | First | Then | Last / never |
|---|---|---|---|
| Any job | variants that meet the Q threshold (Z ≥ Q) | among them the most spendable pool | Z < Q under any quota |
| Spendability | free platform (only `--veri genel`, mechanical/simple) | agy (Flash, Argon, agy's Claude pool) | Codex, Claude Max last |
| Same Claude model | agy's Claude pool | Claude Max | — |
| Verification | a DIFFERENT family from the producer | same family, separate context | the author itself |
| Swarm correctness judge / reducer | Z ≥ Q, non-free pool | — | a free platform is never the judge |
| Second opinion (`--rol hakem`) | Z ≥ max(22, Q−6), different family from the producer, non-free pool | — | a free platform is never the judge |
| Monitoring (watchdog) | fast and cheap: free platform (public data), Flash, Luna | agy Sonnet, Haiku (if the producer is not Claude) | Opus/Sol/Argon only when nothing else qualifies (the selector drops them) |
| Image generation | Codex `gpt-6.1-sol:high` image tool | — | images with text (the leader adds text) |
| Private/personal/health data | local tools + subscription models | — | free/public platforms |
| User is waiting | `--sure-dk` with the fastest model that meets the threshold: Flash, Luna, free platform for mechanical/simple; agy Sonnet/Opus low, Claude for normal/code/research | ask the user to choose speed or quality | a fast model below the threshold; a 28-minute Argon job on the critical path |
| Scarce quota | light mode: cheapest model that qualifies | split, defer to night or reset | crossing floors (Codex 30%, Claude 30%/15%) |
| Bulk simple job overflows (free platform cooling) | as much as fits on agy/Codex | queue the rest until the platform is back | pouring hundreds of simple pieces into Claude Max (Haiku) |

Golden rules: (1) spend intelligence on the brief, not on the worker; (2) verifiable parts go to cheap models,
unverifiable ones to strong models; (3) every worker costs a brief, context and a check, so do not split tiny work;
(4) worker output is a claim: verify with evidence.

## 2. Roles

Selector: `python -I S --rol <role> --sinif <class of the watched job> --dogrulayici <producer model> --veri <...>`.
Thresholds are per role: `Z ≥ max(role floor, job Q − role gap)` (+3 in ultra mode; the header prints the effective
threshold); the producer's family is excluded; fast models rank first. In monitoring roles (watchdog, checker,
messenger, archivist) Opus/Sol/Argon/agy Opus are listed only when nothing smaller qualifies. Judges and devil's
advocates never come from a free pool; only the claude, gpt and gemini families remain in paid pools, so when the
producer is one of them at most 2 judges from different families are listed (the third vote is the producer's own
answer). The `kritik` class may yield no judge: the leader then evaluates itself or asks the user.

| Role (`--rol`) | Floor / gap | Typical model | Job | Free pool |
|---|---|---|---|---|
| `nobetci` watchdog | 18 / 25 | free platform (public data), Flash low, Luna high, Haiku low | watches progress: loops, empty output, red tests, out-of-scope files, token waste, secret leaks, invented sources | yes |
| `kontrolcu` checker | 20 / 20 | Flash, Luna, Haiku medium | schema and "Done" evidence (file exists, test output attached, quotes verbatim) | yes |
| `hakem` judge | 22 / 6 | agy Sonnet high, Terra high, Argon | second opinion, A/B; majority vote = the producer's answer + 2 judges from other families (3 families, 3 votes) | no |
| `haberci` messenger | 20 / 22 | free platform, Flash | 5-10 line summary of long output for the leader | yes |
| `arsivci` archivist | 16 / 40 | free platform, Luna low, Flash low | naming, index, CHECKPOINT, decision log | yes |
| `muhalif` devil's advocate | 38 / 8 | Terra high, Argon, agy Opus | red team: strongest objections, failure scenarios | no |

How the watchdog works: the leader starts workers in the background; every 5-10 minutes or after each worker step
the watchdog only READS (logs, diff summary, test output) and writes one line per finding to the leader:
`WARNING <worker> <type>: <evidence file:line>`. The leader decides (stop, re-brief, escalate). The watchdog never
fixes, never runs code, never writes to workers. Its brief: paths to watch, expected output format, what "stuck" means
(same step 3×, no output for 10 minutes), token budget, scope (allowed folders), secret patterns, the source list (to
catch invented sources).

## 3. Free platform resilience (busy server / limits)

`evren_suru` classifies every 429/503 and writes a persistent cooldown record (`~/.orkestra/evren_durum.json` →
`soguma`); the selector and `kota_oku` read it. Decision tree:

1. **Briefly busy** (Retry-After/resets_at ≤ 60 s): exponential backoff with jitter on the same model, at most twice. No cooldown.
2. **Model busy** (503 without a hint or with a long one, fair share): the model cools down (503: 5 → 10 → 20 minutes,
   exponential); switch to a **sibling** model in the same Z band (≤4 points; never below the primary − 1 or the
   `--sinif` Q). Note: `glm-5.3 soğumada (5 dk); yerine deepseek-v4.1-flash:high`.
3. **Platform-wide** (daily quota, 5-minute token window, concurrency): `*` cooldown. Daily: until the next reset
   (`daily_reset_at`, otherwise 00:00Z). The selector ranks without the platform meanwhile:
   `↳ NOT: EVREN dolu: sunucu dolu (503), 12 dk soğumada; yerine agy Gemini gemini-3.8-flash:low (eşik aynı)`.
4. **Wait option**: if the job is not urgent (no `--sure-dk`, or it is longer than the cooldown) and the cooldown is
   ≤ 30 minutes: queue it and re-run the selector afterwards. Do not wait out a daily quota (hours).
5. **Partial switch** (`--parca N`): when the platform is shaky (a sibling is cooling or a probe is pending) at most half
   of the pieces go to it, the rest to the next pool; if no other pool exists or it is too small, the rest goes to the
   platform too (nothing sits idle). When it is fully cooling for a short time, half go elsewhere now and half wait for
   the platform. When the platform is the only candidate pool and it is cooling, the selector says "no suitable model"
   but computes the wait from the cooldown and prints a `↳ BEKLE` (wait) line.
6. **Probe**: when the cooldown ends the first call sends a 16-token ping; success deletes the record, failure
   increments the streak and extends the cooldown. Manually: `python -I E ping --model glm-5.3:high`, status
   `python -I E soguma`, clear `--temizle hepsi`.
7. **The threshold never drops**: the replacement must also have Z ≥ Q; Luna high (21) does not get a simple job (22).
   The selector's free-platform CALL line carries `--min-z <effective Q>`: E's sibling switch never goes below it
   either. Do not drop this flag (or `--sinif`) when calling E by hand.
8. Exit 4 → re-run the selector (it already reads the cooldown) or `--haric evren`. Exit 5 → escalate.

---

## 4. Patterns (building blocks of every scenario)

### 1. Producer-critic loop
- **Goal:** fix one-pass output of uncertain quality in one round.
- **Agents:** producer (class pick) → critic in the judge role (different family, Z ≥ Q−6) → producer one round.
- **Order:** produce → critique as a bullet list only → revise → checker verifies evidence. At most 2 rounds.
- **When:** writing, plans, single-module code. **Not when:** closed answers (a vote is cheaper), free-platform swarms (no self-critique loops).
- **Cost:** ~1.6 × production.

### 2. Best-of-N with a verifier
- **Goal:** produce N candidates; an automatic verifier (tests, schema, quote check) picks the best.
- **Agents:** N × cheap producer (free platform `--yontem test|kapsam`, or Luna/Flash) + script verifier + Z ≥ Q picker.
- **Order:** N candidates (E `--yontem test --n N`, or N workers by hand) → the leader runs tests in a separate copy → independently audit 1/5 of accepted results.
- **Selector note:** the `↳ SÜRÜ:` / `↳ KASKAD:` line only appears when a cheap swarm model is at most 8 points below Q;
  with today's models (free platform Z ≤ 28) it practically never appears. Do not wait for it; set best-of-N up by hand:
  pick the producer among cheap models that meet the job's own class threshold (free platform or Flash/Luna for
  simple/mechanical pieces). If the platform writes its own tests, swarm ΔZ = 0.
- **When:** the verifier is decisive (tests, JSON schema). **Not when:** hard/critical work, subjective quality, tests written by the weak model.
- **Cost:** near zero on a free pool; N × small on a paid pool.

### 3. Cascade (escalate cheap → expensive)
- **Goal:** most pieces finish cheaply; only failures go to stronger models.
- **Agents:** tier 1 (free platform/Flash/Luna; the free platform only for simple/mechanical pieces) → tier 2 (Terra/agy Sonnet) → tier 3 (Sol/Opus).
- **Order:** automatic check at every tier; failures → next tier (`--min-z`). Escalate the model, not the effort.
  Every tier must meet its own class threshold: a normal/code piece never enters tier 1 (the selector drops it anyway).
- **When:** many similar pieces with a clear pass criterion. **Not when:** one large indivisible job.
- **Cost:** typically 60-80% savings, +20% in the worst case.

### 4. Shadow run
- **Goal:** a cheap model tries first; an expensive model only verifies (does not write).
- **Agents:** shadow (free platform/Flash) → verifier (Z ≥ Q, different family) "right/wrong + where to fix".
- **Order:** shadow draft → verifier reads the diff → if wrong, a strong producer rewrites (not the verifier).
- **When:** verifying is much cheaper than producing (summaries, transforms, translation). **Not when:** verifying is as hard as producing.
- **Cost:** 20-30% of the strong model.

### 5. Watchdog pattern
- **Goal:** catch errors early in long or parallel work.
- **Agents:** workers + watchdog (`--rol nobetci`, different family from the producer).
- **Order:** workers start → the watchdog reads periodically → WARNING → the leader steps in.
- **When:** ≥3 parallel workers, ≥20 minutes, secret-leak risk, invented-source risk. **Not when:** a single 5-minute job.
- **Cost:** 3-8% of the job.

### 6. Jury / debate
- **Goal:** reduce single-model bias in subjective or multi-criteria decisions.
- **Agents:** 3 votes from 3 families: the producer's own answer + the 2 judges of the MAJORITY VOTE (ÇOĞUNLUK OYU)
  line of `--rol hakem --dogrulayici <producer model>` (only claude/gpt/gemini remain in paid pools); leader synthesis.
  Without a producer (a pure jury: no candidate defends its own answer) call it without `--dogrulayici`: the line lists 3 families.
- **Order:** independent scores/reasons (blind to each other) → 2/3 agreement → on disagreement one tier stronger.
  If the `kritik` class yields no judge, the leader evaluates itself or asks the user.
- **When:** design choices, review priorities, text evaluation. **Not when:** factual questions (check sources).
- **Cost:** 3 × small.

### 7. Devil's advocate
- **Goal:** find the proposal's blind spot.
- **Agents:** proposer (Opus/Sol) + devil's advocate (`--rol muhalif`, different family, Z ≥ Q−8).
- **Order:** proposal → "5 strongest objections + failure scenario" → proposer answers → leader decides.
- **When:** architecture, irreversible decisions. **Not when:** routine work.
- **Cost:** ~0.5 WU.

### 8. Map-reduce
- **Goal:** split very large input and merge.
- **Agents:** N × map (free platform `toplu` on public data; otherwise Flash/Luna) + reducer (Z ≥ Q).
- **Order:** the leader splits with one brief template → schema JSON outputs → reducer → checker.
- **When:** inventories, summaries, labeling. **Not when:** pieces depend heavily on each other.
- **Cost:** cheap; the reducer is the real cost.

### 9. Exploration round (creative/ambiguous work)
- **Goal:** widen the solution space fast.
- **Agents:** 3 explorers from different families (e.g. Argon, Terra, agy Sonnet) independently; then a synthesizer (Opus/Sol).
- **Order:** same brief, 3 blind proposals → synthesis: common core + the best outlier idea.
- **When:** naming, product ideas, architecture options. **Not when:** single-answer tasks.
- **Cost:** 3 × medium.

### 10. Information agent first
- **Goal:** gather context before planning (read-only).
- **Agents:** 1-3 readers (agy `--mode plan`, free platform summaries on public data), leader plans.
- **Order:** readers in parallel, read-only → the leader reads the summaries → plan → workers.
- **When:** unknown codebase/folder. **Not when:** the leader already knows it.
- **Cost:** low; protects the leader's context.

### 11. Cross-family verification
- **Goal:** catch errors shared by one family.
- **Agents:** producer family A → verifier family B (`--dogrulayici <producer MODEL name>`, e.g. `--dogrulayici gpt-6.1-sol`; the selector derives the family).
- **Order:** the producer finishes → the verifier sees only the output and the evidence (not the producer's reasoning) → the leader on disagreement.
- **When:** every substantial output. **Not when:** a script verifies decisively.
- **Cost:** 20-40% of production.

### 12. Evidence gate
- **Goal:** tie every "Done" claim to evidence.
- **Agents:** checker (`--rol kontrolcu`) + scripts (tests, grep, schema, screenshot).
- **Order:** scripts first (cheap, decisive) → only what scripts cannot measure goes to the checker → on FAIL the worker gets the missing list.
- **When:** every worker output.
- **Cost:** very low.

---

## 5. Scenarios

### Code

### 13. Mapping a large codebase
- **Goal:** module map, dependencies, entry points across hundreds of files.
- **Agents:** free-platform swarm (`--sinif basit --veri genel --parca N`, one summary per file; public repos only) or Flash; reducer Sonnet high (agy first); messenger summary.
- **Order:** a knowledge graph first if one exists → parallel file summaries → reducer map → checker verifies 5 random files.
- **When:** new repo, before a refactor. **Not when:** private/company code (no free platform → Flash/Luna), a 10-file project.
- **Cost:** ~0 on a free platform; 0.5-1 WU to merge.

### 14. Bug hunt (detective + checker)
- **Goal:** root cause of an unclear bug.
- **Agents:** detective (`--sinif zor`: Opus high/Sol high; agy Opus first) + checker (Luna/Flash: repro steps and log evidence) + watchdog if long.
- **Order:** checker writes a minimal repro script → detective hypothesis + test → checker runs it → fix.
- **When:** hard, reproducible bug. **Not when:** a typo (the leader fixes it).
- **Cost:** 2-4 WU, mostly the detective.

### 15. Multi-file refactor
- **Goal:** change structure without changing behavior.
- **Agents:** producer Sonnet xhigh (or Sol high) + Luna watchdog (out-of-scope files, red tests) + judge from another family (diff review).
- **Order:** leader plan + file list → producer in file groups → tests per group → judge reviews the diff → checker attaches test output.
- **When:** ≥5 files with test coverage. **Not when:** no tests (do scenario 18 first).
- **Cost:** 3-6 WU.

### 16. New feature (vertical slice)
- **Goal:** a small end-to-end feature.
- **Agents:** leader brief (`--sinif normal`) → producer Terra high/agy Sonnet high → test writer (different family) → checker.
- **When:** clear requirements. **Not when:** requirements are vague (pattern 9 first).
- **Cost:** 1-3 WU.

### 17. Code review (two families)
- **Goal:** find bugs and risks in a PR.
- **Agents:** reviewer A (Sol medium) + reviewer B (agy Sonnet high or Argon) independently; the leader merges and dedupes.
- **Order:** both see the same diff, not each other → merge findings → report findings both share or that one backs with evidence.
- **When:** important PRs. **Not when:** formatting changes (a linter suffices).
- **Cost:** 2 × 0.5 WU.

### 18. Writing tests
- **Goal:** tests for existing code.
- **Agents:** test writer Terra medium/Flash (clear interface) + checker (do tests run and actually test something: mutation try) + the free platform only generates test DATA (not tests).
- **Order:** interface list → tests → leader runs them → inject a deliberate bug and see the test catch it.
- **When:** low-coverage modules. **Not when:** the swarm's weak model would write the tests (swarm ΔZ = 0).
- **Cost:** 0.5-2 WU.

### 19. Security scan
- **Goal:** secret leaks, injection, authorization bugs.
- **Agents:** script scan (E `tara`, grep) → triage Sol high / Opus high (critical) → devil's advocate (attacker view).
- **When:** before release. **Not when:** sending source to a free platform to ask "are there secrets" (that sends the secrets!).
- **Cost:** 1-3 WU.

### 20. Dependency/version upgrade
- **Goal:** jump versions without breakage.
- **Agents:** researcher (changelogs: Argon/docs tools) + producer Terra high + watchdog (red tests).
- **Order:** researcher lists breaking changes → producer upgrades step by step → tests at every step → watchdog warns on red tests.
- **When:** major versions. **Not when:** patch versions (the leader).
- **Cost:** 1-2 WU.

### 21. Debugging swarm (parallel hypotheses)
- **Goal:** eliminate several likely causes in parallel.
- **Agents:** 3 hypothesis workers (different families), each tests one hypothesis; a judge weighs results.
- **Order:** the leader writes 3 hypotheses + one discriminating experiment each → workers in parallel → the judge weighs the evidence → fix for the winning hypothesis.
- **When:** the detective is stuck. **Not when:** there is one cause.
- **Cost:** 3 × 0.5 WU.

### 22. Documentation / docstrings
- **Goal:** code documentation.
- **Agents:** free platform `toplu` (public code, `--sinif basit`) or Luna/Flash; checker matches signatures to docstrings (script).
- **Order:** signature list by script → docstring pieces in parallel → script signature check → sampled reading.
- **When:** many files. **Not when:** private code to a free platform.
- **Cost:** very low.

### 23. Migration / large mechanical change
- **Goal:** the same transform in 100+ files.
- **Agents:** codemod script (leader) + free platform/Luna for exception files + checker (build/test).
- **Order:** codemod on a small sample → tests → all files → exceptions the script skipped go to a cheap model → build/test.
- **When:** the pattern is clear. **Not when:** each file needs its own decision.
- **Cost:** low; watch for blanket find-and-replace errors.

### 24. Performance tuning
- **Goal:** a measured speed-up.
- **Agents:** profiling script → analysis Sol high → implementation Terra high → checker (before/after measurement).
- **When:** a measurement exists. **Not when:** "make it faster" without measuring.
- **Cost:** 1-3 WU.

### Research and text

### 25. Web research (quote-checked sources)
- **Goal:** a sourced answer.
- **Agents:** researcher agy Argon high (strong on facts) or Flash (fast sweep) + source checker (each URL opened, quotes verbatim) + watchdog (invented URLs).
- **Order:** decompose the question → parallel search → quoted claims → checker → leader synthesis.
- **When:** current information. **Not when:** accepting claims without URLs.
- **Cost:** 1-2 WU (Argon 1 WU ≈ 28 minutes: run it in the background).

### 26. Literature / academic
- **Goal:** paper search, sources for a student assignment.
- **Agents:** search (literature tools) → summarizer on the free platform `--yontem kapsam` (public abstracts only) → script quote check + checker → synthesis Opus/Sol.
- **Selection:** pick the free-platform summarizer step separately with `--sinif basit --veri genel --yontem kapsam`
  (`--sinif arastirma` drops the platform: Z28 < Q38); pick the synthesis separately with `--sinif arastirma`.
- **When:** a source list is needed. **Not when:** unpublished academic text to a free platform.
- **Cost:** medium; citation verification is mandatory.

### 27. Long document summary
- **Goal:** 100+ pages → executive summary.
- **Agents:** section summaries (free platform on public data, or Flash) → reducer Sonnet high → messenger.
- **When:** public reports. **Not when:** personal/confidential documents to a free platform.
- **Cost:** low.

### 28. Bulk translation
- **Goal:** translate many files/segments.
- **Agents:** free platform `toplu` (public text) or Terra medium; glossary by the leader; checker (format, placeholders, code such as `!important` preserved).
- **Order:** glossary → per-segment translation → script format check → sampled cross-family review.
- **When:** many segments. **Not when:** legal/clinical text (strong model + a human).
- **Cost:** very low.

### 29. Data cleaning (bulk)
- **Goal:** normalize CSV/JSON, labeling.
- **Agents:** scripts first (deterministic part) → free platform `toplu --yontem kapali` (schema, majority vote) → disagreements to Terra.
- **When:** public data. **Not when:** personal data (local scripts + subscriptions).
- **Cost:** near zero.

### 30. Documents / slides
- **Goal:** report, deck, README.
- **Agents:** outline Sonnet high → sections Terra/agy Sonnet → images Codex Sol high (no text) → checker (overflow, spelling, sources).
- **When:** multi-section documents. **Not when:** one paragraph.
- **Cost:** 1-3 WU + image quota (4×).

### 31. Editing / style
- **Goal:** language, tone, flow.
- **Agents:** editor Terra medium + critic (different family) for one round.
- **Order:** editor → critic bullet list → editor final round → the leader checks no meaning was lost.
- **When:** important text. **Not when:** short messages.
- **Cost:** low.

### 32. Q&A / knowledge base
- **Goal:** FAQ from documentation.
- **Agents:** free platform `kapsam` (quoted extraction) → reducer Z ≥ 38 → checker quotes.
- **Selection:** the extraction step with `--sinif basit --veri genel --yontem kapsam`; the reducer separately with `--sinif arastirma`.
- **When:** public documentation. **Not when:** internal docs to a free platform.
- **Cost:** low.

### 33. Comparison table
- **Goal:** compare products/libraries.
- **Agents:** source gatherer Flash → cell filler free platform/Flash (sourced) → judge for consistency.
- **When:** many rows. **Not when:** personal finance/investment decisions (separate skill, disclaimers).
- **Cost:** low.

### Media

### 34. Image generation
- **Goal:** poster, icon, illustration.
- **Agents:** Codex `gpt-6.1-sol:high` image tool (fixed default) → checker (opens the image: garbled text, logo imitation) → the leader adds text/names.
- **Order:** the leader writes a text-free image brief → producer → checker opens the image → the leader adds text.
- **When:** every image generation. **Not when:** a real UI screenshot (take a headless screenshot).
- **Quota at the floor:** near the Codex weekly floor (30%) the selector says `uygun model yok -> kullanıcıya sor` (no
  suitable model, ask the user); there is no other image producer: ask the user (wait, open the floor for this job, or make it by hand).
- **Cost:** consumes Codex quota 4× faster.

### 35. Image understanding
- **Goal:** read screenshots, diagrams, photos.
- **Agents:** `--sinif gorsel-anlama`: Argon, agy Opus, Opus, Sol, Terra; second opinion from another family.
- **Order:** first reading → a second opinion from another family only for unclear/important findings → the leader decides.
- **When:** visual evidence. **Not when:** a text-only free platform.
- **Cost:** medium.

### 36. Video understanding route
- **Goal:** understand video content.
- **Agents:** ffmpeg frame extraction (scene changes) + local Whisper → frames via `gorsel-anlama` → transcript summary `basit` (free platform on public data) → synthesis.
- **When:** a local video. **Not when:** "give the video to the model" (the CLIs do not take video).
- **Cost:** proportional to frames; thin them.

### 37. Video generation
- **Goal:** a video.
- **Agents:** none (no CLI generates video): manually in a subscription app; or video AS CODE with Remotion/HyperFrames (producer Terra/Sonnet).
- **Order:** code route: scene plan → producer code → render → sampled frames checked with `gorsel-anlama`.
- **When:** animation/motion graphics from code. **Not when:** "pretend it was made".
- **Cost:** the code route is a normal code job.

### 38. Audio / speech
- **Goal:** transcript, subtitles.
- **Agents:** local Whisper → corrector Flash/free platform (public data) → timing script.
- **When:** a recording exists. **Not when:** health conversations to a free platform.
- **Cost:** near zero.

### Quota, time and privacy

### 39. Free platform briefly busy
- **Goal:** keep working through a 503/short limit.
- **Agents:** sibling model → otherwise the next pool (Flash/Luna, same threshold) → WAIT if not urgent.
- **Order:** E handles it (section 3) → on exit 4 re-run the selector → relay the `↳ NOT` line in one sentence.
- **When:** cooldown ≤ 30 minutes. **Not when:** the daily quota is gone (scenario 40).
- **Cost:** the fallback pool's cheap quota.

### 40. Free platform daily quota exhausted
- **Goal:** plan without it until the reset.
- **Agents:** agy Flash/Argon, Codex Luna/Terra; large batches may move to the night.
- **Order:** agy Flash → Codex Luna/Terra → defer what does not fit until after the reset. If the selector's WORKER line
  sends overflowing simple pieces to Claude Haiku, do not accept it: queue those pieces (Claude Max stays protected) and
  give them to the platform when it is back.
- **When:** a "günlük kota bitti" note. **Not when:** stopping work to wait (hours).
- **Cost:** agy/Codex quota; floors stay.

### 41. Shaky free platform (partial switch)
- **Goal:** spread risk in piecewise work.
- **Agents:** `--parca N`: at most half to the free platform, the rest to the next pool (if that is too small, the rest to the platform too); a watchdog checks its outputs.
- **Order:** the platform share and the agy/Codex share start together → the watchdog tracks platform errors → failed
  platform pieces are redistributed by re-running the selector. Queue overflowing simple pieces headed for Claude Haiku.
- **When:** a sibling is cooling or a probe is pending. **Not when:** a single-piece job.
- **Cost:** N/2 pieces on a paid pool.

### 42. Quota rescue (load shifting)
- **Goal:** finish while Claude/Codex approach their floors.
- **Agents:** light mode; heavy reading/writing to Codex/agy; the leader only plans and verifies; public parts to the free platform.
- **Order:** public-data pieces to the free platform first → reading/writing on agy → Codex → the leader (Claude) only plans and does the final check.
- **When:** Claude 5-hour < 30% or weekly < 45%. **Not when:** it would cross a floor; if every pool is at its floor, ask the user.
- **Cost:** protects Claude.

### 43. Private data (no free platform)
- **Goal:** work on personal/health/finance/company data.
- **Agents:** `--veri gizli|kisisel|saglik`: local scripts + subscription models (agy, Codex, Claude); a watchdog monitors data leaving.
- **Order:** local scripts (extraction, counting) → subscription model (selector order: agy → Codex → Claude) → the watchdog scans outputs for private data.
- **When:** any personal data, private notes, patients, portfolios. **Not when:** "I anonymized it" so it goes to a free platform (scans miss free-form personal data).
- **Cost:** paid pools.

### 44. Long-running job (background + watchdog)
- **Goal:** supervised hours-long work.
- **Agents:** background workers + watchdog + archivist (CHECKPOINT) + messenger (periodic summary for the leader).
- **Order:** the archivist opens a CHECKPOINT → workers in the background → watchdog every 5-10 minutes → a messenger summary after each wave → the leader.
- **When:** > 30 minutes. **Not when:** the user wants to approve every step.
- **Cost:** +5-10% supervision.

### 45. Urgent job (user waiting)
- **Goal:** a result within minutes.
- **Agents:** the selector with `--sure-dk 10`: the FASTEST model that meets the threshold. For mechanical/simple jobs
  Flash, Luna, the pinged free platform, Terra low; for normal/code/research these miss the threshold and the selector
  returns agy Sonnet/Opus low or Claude (Claude may carry a "süre bilinmiyor" / duration unknown note). Not Argon (28 minutes).
- **Order:** the selector's first candidate → the fallback if it fails; no splitting (brief overhead eats the time).
- **When:** live questions. **Not when:** forcing a fast model below the threshold; quality is critical (ask the user to choose speed or quality).
- **Cost:** low; speed first.

### 46. Night batch (free platform plentiful)
- **Goal:** do not waste the daily free window.
- **Agents:** free platform `toplu` on public data (inventory, translation drafts, labeling), archivist; morning audit by the leader (1/5 sample).
- **Order:** plan in the evening with `toplu --kuru` → the platform at night → the archivist indexes results → sampled
  audit in the morning. If the platform goes into cooldown, do not pour overflow into Claude Haiku; queue it and resume later.
- **When:** unused daily quota before the reset. **Not when:** private data.
- **Cost:** zero.

### 47. Student / academic work
- **Goal:** assignment, presentation, correctly cited text.
- **Agents:** research (scenario 26) + source check (open every citation) + devil's advocate (weak arguments) + writer Sonnet/Terra.
- **Order:** gather sources → source check (invented citations removed) → writer → devil's advocate → writer final round → checker on citation format.
- **When:** source-dependent work. **Not when:** invented citations; unpublished text to a free platform.
- **Cost:** medium.

### 48. Health / clinical
- **Goal:** clinical information, patient notes.
- **Agents:** a clinical skill + evidence tools + a strong model (Opus/Sol) + human sign-off.
- **Order:** clinical skill → evidence search → strong-model draft (`--veri saglik`) → second opinion from another family → human sign-off.
- **When:** any health data. **Not when:** free platforms, cheap swarms, unsupported advice.
- **Cost:** high but required.

### 49. Architecture decision
- **Goal:** a design choice that is expensive to undo.
- **Agents:** proposer Opus high/Sol high + devil's advocate (different family) + exploration round if needed + a decision log entry.
- **Order:** (exploration round if unclear) → proposer → devil's advocate → proposer answers → the leader's decision note.
- **When:** critical/hard. **Not when:** a small module.
- **Cost:** 2-4 WU.

### 50. Quota measurement (calibration)
- **Goal:** replace estimated rates with measurements.
- **Agents:** one worker, `olc baslat` / `olc bitir`; nothing else running.
- **Order:** `olc baslat` → one worker → `olc bitir` → the rate is recorded; parallel work afterwards.
- **When:** a new model or estimated rate. **Not when:** parallel work is running.
- **Cost:** the job itself.

### Mixed cases

### 51. Mixed sensitivity (private core + public pieces)
- **Goal:** do the public sub-pieces on a cheap pool without touching private data.
- **Agents:** the leader splits pieces by data class; public pieces `--veri genel` (free platform/Flash), the private core
  `--veri gizli` (subscription model); a watchdog checks for leaks between pieces.
- **Order:** split list (a `--veri` label per piece) → E `tara` scans the public pieces → two branches in parallel → the
  merge runs on the private branch's model.
- **When:** public docs + personal notes, open-source code + company configuration. **Not when:** the pieces cannot be
  separated (treat everything as private).
- **Cost:** ~0 for the public part; paid for the private part.

### 52. Confidential document summary and risk review (contract, legal/company PDF)
- **Goal:** summarize a confidential document and find risky clauses.
- **Agents:** local PDF-to-text script → summarizer (`--veri gizli --sinif normal`: agy Sonnet/Terra) → risk review by a
  judge from another family (`--rol hakem --dogrulayici <summarizer model>`) → checker (every risk item quoted verbatim from the document).
- **Order:** text extraction → section summaries → risk list → judge → quote check → leader; the legal decision stays with the user.
- **When:** contracts, leases, job offers, company reports. **Not when:** free platforms (private data), giving "legal advice".
- **Cost:** 1-2 WU on paid pools.

### 53. Flaky bug / intermittently failing test
- **Goal:** find the condition behind an intermittent failure.
- **Agents:** a rerun script (N runs; environment, order and timing logged) → messenger statistics summary → hypothesis
  swarm (scenario 21) → detective (`--sinif zor`) → watchdog (long runs).
- **Order:** 20-100 scripted reruns and the failure rate first → one discriminating experiment per hypothesis → fix the
  winning hypothesis → compare the failure rate with the same number of reruns after the fix.
- **When:** intermittent CI red, suspected race condition. **Not when:** it fails every time (scenario 14).
- **Cost:** reruns are local; models 2-4 WU.

---

## 6. Creative mode (a situation this playbook does not cover)

If no route fits, the leader DESIGNS one. Five principles:
1. **Goal:** how will "Done" be proven? Write the evidence first.
2. **Verifiability:** define an automatic or cross-family verifier for every piece; if none exists, give the piece to a strong model.
3. **Diversity:** producer and checker in separate contexts, preferably different families; no single-model dependency on the critical path.
4. **Cost:** free/spendable pools first, but the Q threshold is never crossed; estimate cost with the selector (`--parca`, `--sure-dk`).
5. **Fallback:** write up front what happens when each step fails (sibling model, next pool, wait, ask the user).

Ideas to combine: watchdog + cascade; shadow run + jury; exploration round + devil's advocate; free-platform swarm
for test data + strong model for tests; a messenger chain (5 lines after each wave) to protect the leader's context.

If the route worked, the leader PROPOSES to the user: "Shall I add this route to the playbook under 'Discovered
routes'?" Nothing is written without approval. Use the same format as the scenarios (Goal, Agents, Order,
When/Not when, Cost) plus the date and evidence (which job, what result).

## 7. Discovered routes

(None yet. Added with user approval.)
