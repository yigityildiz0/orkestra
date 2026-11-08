# Model atlas (updated: 2026-11-08, with /orkestra update)

Sources: Artificial Analysis (AA) Intelligence Index v5.0.1 pages, official Anthropic/OpenAI/Google documentation, Vals, LMArena and OpenAI Codex pricing; research by 13 agents and cross-checking. v4.3.2 and v5 scores are not comparable. Figures are indicative; test consequential choices on your own task.

## BANNED (default policy)

Fable 5.1 and GPT-6 Astra (Claude Mythos and Gemini 4 Carbon are outside this ban). gpt-oss-120b is being removed from agy on November 18: do not select it.

## Intelligence score by effort (AA v5.0.1; selector Z)

| Model | low | medium | high | xhigh | max |
|---|---|---|---|---|---|
| Opus 5.5 | 35 | 48 | 52 | 57 | 59 |
| Sonnet 5.5 | 26 | 31 | 42 | 50 | 55 |
| Haiku 5.5 | 19 | 25 | 30 | 35 | 36 |
| GPT-6.1 Sol | 35 | 46 | 50 | 52 | 55 |
| GPT-6.1 Terra | 29 | 38 | 42 | 45 | 51 |
| GPT-6 Luna | ? | ? | 21 | ? | 28 |
| Gemini 4 Argon | ? | ? | 50 | – | – |
| Gemini 3.8 Flash | 23 | 30 | 31 | – | – |

Lesson: effort is a bigger lever than model choice. Sonnet scores 31 at medium and 55 at max. Change effort first, then model.

## Price and total cost of the same work (price × tokens spent)

| Model | API $/1M (input/output) | AA per task (max) | Index run output tokens | Note |
|---|---|---|---|---|
| Opus 5.5 | 4 / 20 | $10.04 | 218M | medium $2.45, low $0.98 |
| Sonnet 5.5 | 2 / 10 | $10.02 | 335M | half the price per token but 1.5 times the tokens: as expensive as Opus at max |
| Haiku 5.5 | 0.10 / 0.50 | $0.41 | 298M | $0.50/$2.50 above 100K prompt tokens (5 times); uses more tokens than Luna |
| Sol 6.1 | 2 / 10 | $1.27 | 63.7M | most token-efficient top model; within 4 points of Opus, ~8 times cheaper |
| Terra 6.1 | 1 / 5 | $0.96 | 99.4M | xhigh $0.40 / 34.7M tokens / 45 points |
| Luna 6 | 0.10 / 0.50 | $0.15 | 110M | cheap per point, low quality |
| Argon 4 | 2 / 10 → 4 / 20 from Dec 1 | $9.95 | 113M | slow (71 tokens/sec), token-hungry |
| Flash 3.8 | 0.75 / 3.75 → 2x from Jan 1 2027 | $7.77 | 126M | expensive per point |

Subscriptions spend quota rather than cash. Official Codex Plus local 5-hour message ranges: Sol 15-160, Terra 35-285, Luna 350-3000 (Terra ≈ twice Sol's work). No official per-model multiplier exists for Claude Max or agy: selector rates are estimates derived from AA cost ratios; measure with `olc`.

## Effort curve (efficiency)

Score per cost usually peaks at low or medium; diminishing returns start around high. For most models xhigh→max costs 1.5-3 times the tokens for +1..+5 points. High effort helps substantially with code migration, terminal agents, law and deep research (Vals +10..+19); less with finance and Excel (+3..+5). In real repository repair, added effort did not improve care (Opus medium and Sol low/medium were best).

- Opus: medium by default; high-xhigh for difficult or long work; max once only if xhigh fails.
- Sonnet: high (medium→high is the steepest step, +11); xhigh for code; max only when needed.
- Haiku: medium; low stops early; xhigh/max wasteful.
- Sol: high for code (DeepSWE peak; xhigh/max decline); xhigh for long research. Ultra only for independent parallel work (6-12 times the quota).
- Terra: medium-high, xhigh/max if quality requires it. Luna: simple work. Argon: low/medium routine, high for difficult reasoning.
- Flash: medium (high wastes resources for +1 point).

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
- **Argon 4:** assign research needing factual accuracy (lowest hallucination, ~4%), code review and third opinions. Avoid urgent work; the weekly counter is tight.
- **Flash 3.8:** still the newest Flash. Assign video/audio/long-document input, cheap summaries/translations and broad scanning. Avoid long agent loops (loop/503 complaints in agy) and factual questions (55% hallucination).

## Defaults by class (selector adjusts for quota)

| Work | First | Backup |
|---|---|---|
| Mechanical, formatting | Flash low | Haiku low, Luna |
| Summary, data cleaning | Flash | Haiku medium, Terra low |
| Research | Terra medium | Sonnet high; Argon if factual accuracy is critical |
| Normal code | Terra high | Sol medium, Sonnet high |
| Multi-file code, agent | Sol high | Sonnet xhigh, Opus medium |
| Difficult architecture, ambiguous bug | Sol high/xhigh or Opus high | Sonnet max |
| Critical, final verification | Opus xhigh | Sol max second opinion from a different family |
| Image generation | Codex image_gen (Sol high, by default) | Nano Banana manually |
| Animation / GIF | Codex image_gen, GPT Image 2.6 (4 Nov 2026): ask for a looping sprite sheet; Codex slices the frames into a GIF/APNG | Frame by frame by hand |
| Image understanding | Terra/Sol | Opus, Argon |
| Video understanding/generation | cannot be automated | ffmpeg+Whisper; Gemini app manually |

## Quota pools

- Claude Max 5x: 5-hour + weekly, shared by all models (plus a separate Fable weekly quota). Numeric quota is not published. Read with `get_usage`.
- Codex (ChatGPT Plus): 5-hour + weekly; shared pool with ChatGPT from December 2026 (secondary source). Fast mode consumes 2.5 times, images 3-5 times as much.
- agy (Google AI Pro): separate Gemini, Argon (weekly only) and “Claude and GPT models” pools; Opus/Sonnet in agy do not consume Claude Max (quality equivalence has not been measured: run a small A/B for critical work). Keep AI Credit Overages set to “Never”.

## Known changes and dates

- November 18: gpt-oss-120b and Opus/Sonnet 4.6 leave agy. November 30/December 1: Argon API $4/$20.
- December: ChatGPT and Codex share a quota pool. January 1 2027: Flash 3.8 price doubles.
- Codex: `bin\codex.exe` is old; use the newest `bin\<hash>\codex.exe`. When supplying an image with `-i`, close input (`< /dev/null`) to avoid waiting on stdin.

## Fine tactics

1. Do not give the same failure to the same model a second time; use another family.
2. Adjust effort first, then change model; do not default to max.
3. Give verifiable work to cheaper models and unverifiable work to stronger ones; a stronger model checks Luna/Flash/Haiku output.
4. If factual accuracy is critical, cross-check with Argon or Terra; do not use Opus/Sol as the sole factual source.
5. If the benchmark difference is ≤3 points, select the non-Claude option with ample quota.
6. Codex/agy output is a claim: verify with diff, tests and grep; watch for bulk replacement errors.
