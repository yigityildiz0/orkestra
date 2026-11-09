# Model atlas (updated: 2026-11-09: free platform resilience, roles, playbook; previous: 2026-11-08 third pass)

Sources: Artificial Analysis (AA) Intelligence Index v5.0.1 pages, official Anthropic/OpenAI/Google documentation, Vals, LMArena and OpenAI Codex pricing; research by 13 agents and cross-checking. v4.3.2 and v5 scores are not comparable. Figures are indicative; test consequential choices on your own task.

## Change note (2026-11-09: resilience, roles, playbook)

- Free platform cooldown: 429/503 are classified and stored persistently (`~/.orkestra/evren_durum.json` → `soguma`, per model or `*`). 503: 5-10-20 minutes exponential (longer if the server's `resets_at` says so, ≤60 minutes); fair share 2-4-8 minutes; concurrency 30 s × n (≤5 minutes); 5-minute token window until `resets_at`; daily quota until `daily_reset_at` (else 00:00Z). Short hints (≤60 s) wait on the same model with backoff and jitter. Siblings: glm-5.3 high (28) ↔ deepseek-v4.1-flash high (27); glm low (21) and deepseek non-thinking (17) are not siblings (threshold). The selector excludes cooling models and prints WAIT (≤30 minutes, not urgent) and PARTIAL SWITCH (`--parca`, at most half to the platform) notes. Durations are estimates; measure and adjust (`update.md`).
- Roles (`kapasite.py --rol`): watchdog, checker, judge, messenger, archivist, devil's advocate. Fast, cheap watchers: Haiku low/medium (Z19/25), Luna medium/high (18/21), Flash low (23), a free platform on public data (27-28). Judge and devil's advocate never come from a free pool; the producer's family is excluded.
- `references/playbook.md`: priority table, roles, the busy-platform decision tree, 12 patterns, 41 scenarios, creative mode (an audit pass added 3: mixed sensitivity, confidential document review, flaky bugs).

## Change note (2026-11-08, third pass)

- Free platforms as ordinary pools: `bedava`, `gerekli_env` (closed without the key), `bitis` (closed after the end date), `gizlilik: kamu` (only `--veri genel` work), daily window `gun`. Example: EVREN (`examples/evren.example.json`), table below.
- Free and spend-down pools (agy, free platforms) use flat scarcity: equally cheap while the work fits (agy used to drift to Codex at 40% and to Claude Haiku at 3-10%). A daily window counts as 1/7 of a weekly one.
- agy call: `--print-timeout` is 3 × the estimated time (at least 15m; Argon ≈ 28 min per work unit) instead of a fixed 180s; file-editing work uses `--mode accept-edits`. agy consumption rates are marked `o_kaynak: tahmin` (estimate).
- No fixed worker cap in auto mode: pieces (`--parca`), quota and platform concurrency decide; explicit light/ultra keeps 2/6. Efforts of one model within 10% in score resolve to the cheaper one.
- `.orkestra.json` weight floor 0.2 → 0.01 (agy's 0.15 is no longer made more expensive); new `gizli` and `yasak_havuz` fields. Missing pool fields default to a 10% floor (0 for free/spend-down pools) and weight 1.0.

## Change note (2026-11-08, second pass)

- Default policy: Antigravity (Flash, Argon and the "Claude and GPT models" pool inside agy) is the first pool to spend, with **a floor of 0: it may be spent down to zero**. Selector weight 0.15 (was 0.5/0.7/0.6 with a 5% floor). The ChatGPT/Codex 30% weekly floor and the Claude rules (30% weekly, 15% leader reserve) are unchanged. The intelligence threshold never drops in any gear.
- Variants that really exist in agy were added: agy Opus low (35), agy Sonnet low (26) and medium (31), Flash high (31). Argon low/medium exist in agy but have no AA score, so the selector does not use them.
- Luna medium 17 (estimate) → 18 (AA); Luna low 10, xhigh 23 and Haiku xhigh 35 added. Luna rate Sol/15 → Sol/20.
- One global effort multiplier was replaced by a per-model multiplier (`ec`, table below). The largest gap is Sonnet xhigh/max (global 2.3/4.5, actual 4.27/11.75).
- agy call: `agy -p "<brief>" --model <id-with-effort> --mode plan --output-format json --print-timeout <duration>` (flags checked with `agy --help`; the model id carries the effort; `0` waits until done).

## BANNED (default policy)

Fable 5.1 and GPT-6 Astra (Claude Mythos and Gemini 4 Carbon are outside this ban; Carbon is also absent from `agy models`). gpt-oss-120b is being removed from agy on November 18 and has no AA v5.0.1 score: do not select it.

## Intelligence score by effort (AA v5.0.1; selector Z)

| Model | low | medium | high | xhigh | max |
|---|---|---|---|---|---|
| Opus 5.5 | 35 | 48 | 52 | 57 | 59 |
| Sonnet 5.5 | 26 | 31 | 42 | 50 | 55 |
| Haiku 5.5 | 19 | 25 | 30 | 35 | 36 |
| GPT-6.1 Sol | 35 | 46 | 50 | 52 | 55 |
| GPT-6.1 Terra | 29 | 38 | 42 | 45 | 51 |
| GPT-6 Luna | 10 | 18 | 21 | 23 | 28 |
| Gemini 4 Argon | unverified | unverified | 50 | – | – |
| Gemini 3.8 Flash | 23 | 30 | 31 | – | – |
| gpt-oss-120b (agy, medium) | – | unverified | – | – | – |

Opus/Sonnet in agy are the same models (same Z), but the agy CLI only offers low/medium/high. Argon low/medium can be picked in agy, but the AA page returns 404: with no Z the selector does not use them. Left out of the selector: Haiku max (+1 point for 1.75 times the cost), Luna max (Terra low is cheaper and smarter).

Lesson: effort is a bigger lever than model choice. Sonnet scores 31 at medium and 55 at max. Change effort first, then model.

## Effort cost multiplier (medium = 1; ratio of AA total index cost; selector `ec`)

| Model | low | high | xhigh | max |
|---|---|---|---|---|
| Opus 5.5 | 0.48 | 1.34 | 2.35 | 4.39 |
| Sonnet 5.5 | 0.73 | 1.87 | 4.27 | 11.75 |
| Haiku 5.5 | 0.55 | 1.66 | 2.64 | 4.64 |
| Sol 6.1 | 0.61 | 1.47 | 1.85 | 2.89 |
| Terra 6.1 | 0.58 | 1.41 | 2.11 | 5.12 |
| Luna 6 | 0.23 | 1.58 | 2.15 | 3.40 |
| Flash 3.8 | not measured (global 0.5) | 1.27 | – | – |

Assumption: subscription quota is proportional to dollar cost (unverified; `olc` measures it). Argon and Flash low use the global multiplier (low .5, high 1.5). agy Opus/Sonnet take the same model's multiplier (estimate: agy quota is measured by workload). Dominated variants (a smarter one costs less in the same pool): on Claude Max, Sonnet xhigh < Opus high, Sonnet max < Opus xhigh, Sonnet low/medium and Opus low < Haiku xhigh; on Codex, Sol low < Terra medium, Terra xhigh ≈ Sol medium, Terra max < Sol xhigh. The selector does not ban them; with correct multipliers they lose on score. agy has no Haiku and no xhigh/max, so Sonnet medium (31) there is not dominated.

## Price and total cost of the same work (price × tokens spent)

| Model | API $/1M (input/output) | AA per task (max) | Index run output tokens | Note |
|---|---|---|---|---|
| Opus 5.5 | 4 / 20 | $10.04 | 218M | medium $2.45, low $0.98 |
| Sonnet 5.5 | 2 / 10 | $10.02 | 335M | half the price per token but 1.5 times the tokens: as expensive as Opus at max |
| Haiku 5.5 | 0.10 / 0.50 | $0.41 | 298M | $0.50/$2.50 above 100K prompt tokens (5 times); uses more tokens than Luna |
| Sol 6.1 | 2 / 10 | $1.27 | 63.7M | most token-efficient top model; within 4 points of Opus, ~8 times cheaper |
| Terra 6.1 | 1 / 5 | $0.96 | 99.4M | xhigh $0.40 / 34.7M tokens / 45 points |
| Luna 6 | 0.10 / 0.50 | $0.15 | 110M | cheap per point, low quality |
| Argon 4 | 4 / 20 (AA current); the $2/$10 promo and its Dec 1 end come only from secondary sources | $9.95 (high) | 113M | slow: 71 tokens/sec, 40 s to first answer token, 27.5 min per task; 1M context |
| Flash 3.8 | 0.75 / 3.75 (90% cache discount) → 2x from Jan 1 2027 | $7.77 (high), $6.26 (medium) | 126M | 112 tokens/sec, 19.9 s to first token; expensive per point, but dollars do not matter inside agy quota |

Subscriptions spend quota rather than cash. Official Codex Plus local 5-hour message ranges: Sol 15-160, Terra 35-285, Luna 350-3000 (Terra ≈ twice Sol's work, Luna ≈ 19-23 times). No official per-model multiplier exists for Claude Max or agy: selector rates are estimates derived from AA cost ratios; measure with `olc`.

## Effort curve (efficiency)

Score per cost usually peaks at low or medium; diminishing returns start around high. For most models xhigh→max costs 1.5-3 times the tokens for +1..+5 points. High effort helps substantially with code migration, terminal agents, law and deep research (Vals +10..+19); less with finance and Excel (+3..+5). In real repository repair, added effort did not improve care (Opus medium and Sol low/medium were best).

- Opus: medium by default; high-xhigh for difficult or long work; max once only if xhigh fails.
- Sonnet: high (medium→high is the steepest step, +11); xhigh for code; max only when needed.
- Haiku: medium; low stops early; xhigh/max wasteful.
- Sol: high for code (DeepSWE peak; xhigh/max decline); xhigh for long research. Ultra only for independent parallel work (6-12 times the quota).
- Terra: low-high (Q ≤ 42). If Q ≥ 44 is needed, use Sol medium/high instead of Terra xhigh/max: smarter and cheaper. Luna: simple work. Argon: the selector uses high only (low/medium scores are unmeasured; try them by hand and check quality yourself).
- Flash: low/medium; high adds only +1 point (allowed because agy quota is cheap; medium usually wins).

## Capability matrix (access path: CLIs)

| Capability | Claude Code | Codex CLI | agy CLI |
|---|---|---|---|
| Text + image input | yes | yes (`-i`) | yes |
| PDF | yes (600 pages) | undocumented | yes (Gemini) |
| Video understanding | no (ffmpeg frames + Whisper) | no | Gemini understands video but `agy -p` cannot accept files; drag and drop in interactive agy |
| Audio understanding | no (local Whisper) | no | Gemini understands it; CLI path undocumented |
| Image generation/editing | no (draws SVG/HTML/Pillow) | yes: `image_gen` (GPT Image), consumes quota 3-5 times faster | Nano Banana undocumented in CLI (untested) |
| Video generation | no | no | no (manual Gemini app/Flow: Omni Flash) |
| Web search | WebSearch/WebFetch | yes | yes |
| Browser/computer | yes (Chrome, computer-use) | yes (browser_use, computer_use) | yes |
| Context | 1M | Sol/Terra 500K, Luna 272K | Gemini 1M |

## Generation priority (LMArena + AA, November 6-8 2026)

- Image generation and editing: 1) Codex `image_gen` (GPT Image 2.x family leads both tables), 2) Gemini Nano Banana (Gemini app; separate quota, one tier lower), 3) Claude drawing with code. For Turkish text in images, generate without text and overlay it in code (no independent test of ç ğ ı İ ö ş ü).
- Video generation: no automatic path. Manually use Gemini Omni Flash (LMArena T2V/I2V 1st; 12th in AA, a conflict), Veo 3.1 Lite. Sora closed.

## Model strengths and weaknesses (assign / avoid)

- **Opus 5.5:** assign architecture, planning, ambiguous long agent work, hard bugs, final verification, UI polish. Avoid batch/mechanical tasks, factual recall (50-59% hallucination), urgent work at max effort (minutes to first token).
- **Sonnet 5.5:** assign implementation and review, terminal/code agents, automation. Avoid assuming it is cheap (at max it costs as much as Opus), and open-ended judgment.
- **Haiku 5.5:** assign codebase search, log/test triage, classification, summaries and formatting (verified read-only). Avoid implementation, factual recall, prompts above 100K, quality-sensitive Turkish.
- **Sol 6.1:** assign deep code/backend/algorithms, second opinions and cross-checks. Avoid latency-sensitive work (slow start at high/max).
- **Terra 6.1:** assign medium-difficulty tasks, repetitive code; better calibrated than Sol (34.5% hallucination). Avoid complex work requiring Sol quality (verify on your own task).
- **Luna 6:** assign formatting, simple transformations and batch light work. Avoid factual knowledge, complex code and agent work (~77% hallucination). Always verify output.
- **Argon 4:** among the first pools to spend (floor 0). Assign research needing factual accuracy, code review and third opinions. Hallucination is contested: the earlier atlas said ~4%, a secondary source (aiweekly, Oct 1) says ~15%; not verified on AA, so never use it as the only factual source. Avoid urgent work (40 s to first answer token, 27.5 min per task).
- **Flash 3.8:** still the newest Flash. Assign video/audio/long-document input, cheap summaries/translations and broad scanning. Avoid long agent loops (loop/503 complaints in agy) and factual questions (55% hallucination).

## Defaults by class (selector adjusts for quota)

| Work | First | Backup |
|---|---|---|
| Mechanical, formatting | free platform (e.g. EVREN glm low) for public data | Flash low, Haiku low, Luna |
| Summary, data cleaning | free platform (e.g. EVREN ds high) for public data | Flash, Haiku medium, Terra low |
| Research | Terra medium | Sonnet high; Argon if factual accuracy is critical |
| Normal code | Terra high | Sol medium, Sonnet high |
| Multi-file code, agent | Sol high | Sonnet xhigh, Opus medium |
| Difficult architecture, ambiguous bug | Sol high/xhigh or Opus high | Sonnet max |
| Critical, final verification | Opus xhigh | Sol max second opinion from a different family |
| Image generation | Codex image_gen (Sol high, by default) | Nano Banana manually |
| Animation / GIF | Codex image_gen (GPT Image 2.x; "2.6, 4 Nov 2026" comes only from third parties, unverified): ask for a looping sprite sheet; Codex slices the frames into a GIF/APNG. One image ≈ 0.4% of the weekly quota: count frames × attempts first | Frame by frame by hand |
| Image understanding | Terra/Sol | Opus, Argon |
| Video understanding/generation | cannot be automated | ffmpeg+Whisper; Gemini app manually |

## Example free platform: EVREN (values in `examples/evren.example.json`)

Turkey's national LLM platform (SSYZ), OpenAI-compatible API, free until 2026-12-01 03:00 Turkey time. Z on the AA v5.0.1 scale, discounted 1.5-4 points for EVREN constraints (FP8 GLM, 16K output cap can cut reasoning, undocumented effort mapping, unknown DeepSeek snapshot): `z_kaynak: aa-indirimli`.

| Selector name | Effort → Z | Basis | Speed tok/s | Context / output |
|---|---|---|---|---|
| evren-deepseek-v4.1-flash | high 27 | AA High 28.6 (Max 32.6 not assumed) | ~10 | 1M / 65K |
| evren-deepseek-v4.1-flash-nr | thinking off 17 | AA non-reasoning 18.5 | ~10 | 1M / 65K |
| evren-glm-5.3 | low 21 · high 28 | AA Low 23.1; Max 31.7 upper bound | ~8 | 512K / 16K |

Not in the selector: qwen3.8-flash-next (no AA composite score; no evidence, no entry), gemma-4-31b (v5 4.4), qwen3-vl-30b (no score), auto (32K context), OCR/ASR/embedding/rerank/TTS/guard models (no Z). The best EVREN Z≈27-28 is below Sonnet medium (31) and 13 points below Sonnet high (42): alone only mechanical and simple work. A swarm (N parallel calls + vote/judge) does not add reasoning; with a verifier it gives a bounded effective-Z gain, zero for Q ≥ 36 with today's Z ≤ 28, i.e. research and above (Snell 2408.03314, Stroebl 2411.17501, Debate-or-Vote 2508.17536, Huang 2310.01798, Self-MoA 2502.00674, JudgeBench 2410.12784).
Measured 2026-11-08: `/v1/quota` returns daily_limit_tokens 15M, daily_remaining_tokens, daily_reset_at, cap 2.5M per 5-minute window, concurrency_limit 32, model_concurrency_limit, fair_share_active, level. A direct chat call answered in 13 s with 88 tokens (ping 2.8 s, 18 tokens); the same one-word job through a Codex profile took 209 s and ~790K tokens, so text work goes over direct HTTP (`evren_suru.py`) and only file-editing work uses the Codex agent. Treat everything sent there as public (terms: logs kept, content may be used for training).

## Quota pools

Spend order and floors (default policy 2026-11-08): free platform if configured (floor 0) > agy (floor 0, down to zero) > Codex (30% weekly) > Claude Max (30% weekly, 15% leader reserve in the 5-hour window). Floors are never crossed in any gear. Selector weights: free platform 0.05 (example), agy 0.15, Codex 0.9, Claude 2.5.

- Claude Max 5x: 5-hour + weekly, shared by all models (plus a separate Fable weekly quota). Numeric quota is not published. Read with `get_usage`.
- Codex (ChatGPT Plus): 5-hour + weekly. From December 2026 one token-based allowance is shared with ChatGPT (Plus/Pro/Business; Instant chat does not count; date and size not announced). OpenAI Help 20001625 confirmed through search snippets; the page itself returned 403. Fast mode consumes 2.5 times (no Ultrafast on Plus), images 3-5 times on average. Local measurement (2026-11-08): one image ≈ 0.4% of the weekly quota; most quota goes to cached input (97-99% of input), i.e. long context. Three or four parallel Terra high sessions used 9-14% of the week in 15 minutes: give Codex short, narrow `codex exec` jobs, one or two at a time. The weekly reset can move (last week it came 5 days early). The selector reads Codex fresh at the start of each orchestration.

## agy (Google AI Pro) cost and quota

- Three separate pools: "Gemini Models" (Flash; 5-hour + weekly), "Gemini 4 Argon" (weekly only, added to Pro in October 2026; size not disclosed; the announcement is confirmed by secondary coverage, the X post could not be opened) and "Claude and GPT models" (agy Opus/Sonnet 5.5 and gpt-oss-120b; 5-hour + weekly). All have a floor of 0.
- The binding window is weekly: the 5-hour counter only refreshes until the weekly limit is reached (official plans page); at 0% weekly a 100% 5-hour reading cannot be used. The selector therefore decides agy on the weekly window.
- Quota tracks the agent's workload, not message count (official): context size and tool steps. No official model or effort multiplier exists; selector agy rates are estimates. Start every job as a new, single-task call (no `--continue`), keep briefs short, measure with `olc`.
- User reports say the Claude/GPT pool drains very fast (a few prompts; Opus ~4 times faster than Gemini). The evidence is anecdotal, from March 2026 and the 4.6 era; nothing is measured for Opus 5.5.
- Credits: keep AI Credit Overages at "Never" and `useG1Credits: false` in the CLI `settings.json` (no extra charges); check with `/usage` and `/credits`. The official page calls them "AI credits".
- Opus/Sonnet in agy do not consume Claude Max (quality equivalence has not been measured: run a small A/B for critical work).
- November 18: Opus/Sonnet 4.6 and gpt-oss-120b are removed; afterwards drop gpt-oss from `KNOWN_AGY` in `kota_oku.py`.

## Known changes and dates

- November 18: gpt-oss-120b and Opus/Sonnet 4.6 leave agy. Argon API: AA shows $4/$20; "$2/$10 until November 30" comes only from secondary sources (eesel says no end date was announced).
- December: ChatGPT and Codex share a quota pool. January 1 2027: Flash 3.8 price doubles.
- Gemini 4 Carbon tops AA (low 54, medium 58, high 60) but is not in the agy list: not a candidate.
- Codex: `bin\codex.exe` is old; use the newest `bin\<hash>\codex.exe`. When supplying an image with `-i`, close input (`< /dev/null`) to avoid waiting on stdin.

## Fine tactics

1. Do not give the same failure to the same model a second time; use another family.
2. Adjust effort first, then change model; do not default to max.
3. Give verifiable work to cheaper models and unverifiable work to stronger ones; a stronger model checks Luna/Flash/Haiku output.
4. If factual accuracy is critical, cross-check with Argon or Terra; do not use Opus/Sol as the sole factual source.
5. If the benchmark difference is ≤3 points, select the non-Claude option with ample quota.
6. Codex/agy output is a claim: verify with diff, tests and grep; watch for bulk replacement errors.

## Sources (2026-11-08 third pass)

- AA v5.0.1: https://artificialanalysis.ai/evaluations/artificial-analysis-intelligence-index and the model/comparison pages (claude-opus-5-5, claude-sonnet-5-5, claude-haiku-5-5, gpt-6-1-sol, gpt-6-1-terra, gpt-6-luna, gemini-4-argon, gemini-3-8-flash, gpt-oss-120b). Effort multipliers are computed from their total costs.
- agy: https://antigravity.google/docs/models/ , https://antigravity.google/docs/plans , https://antigravity.google/docs/cli/credits/ ; local `agy models`, `agy --help`, `kota_oku.py --fresh`; forum threads https://discuss.ai.google.dev/t/190487 and /135870 (anecdotal); Argon pool: https://github.com/n2ns/antigravity-panel/pull/210 , https://github.com/robinebers/openusage/issues/1397 , 9to5Google (Oct 15 2026).
- Codex: https://learn.chatgpt.com/docs/pricing ; OpenAI Help 20001625 (search snippet); local `~/.codex/models_cache.json` and `~/.codex/sessions` measurements.
- Unverified: Argon low/medium scores, gpt-oss-120b score, Argon hallucination rate, end date of the Argon promo, GPT Image 2.6 release and price, older v4.3 values.
- Free platform example (EVREN): its model catalogue/API page (base URL https://evren-llmapi.ssyz.org.tr/v1), https://api.ssyz.org.tr/api/v1/public/llm-stats, and local `evren_suru.py modeller|kota|ping` (2026-11-08). Quota: 15M tokens per day (all keys of an account), 2.5M per 5-minute window, 32 concurrent requests per account; the script keeps 22 (esz 24 − 2). EVREN Z values are AA scores discounted by estimate.
