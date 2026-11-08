---
name: orkestra
description: Routes tasks across available AI models and quota pools by difficulty, remaining capacity, and user preferences, with verification where appropriate.
---

# Orkestra

The leader plans, briefs, delegates and verifies while conserving capacity without reducing quality. The default pools are Claude Max (leader), ChatGPT/Codex and Google Antigravity (agy). Configure other platforms in `~/.orkestra/platformlar.json`; see `examples/platformlar.example.json` in the repository.

## Commands

| Command | Action |
|---|---|
| `/orkestra` or `/orkestra status` | Read quota and show pools and recommendations by class. |
| `/orkestra <task>` | Classify, select models and worker count, execute and verify; summarize contributions. |
| `/orkestra light <task>` or `/orkestra hafif <task>` | Use the cheapest sufficiently capable model, at most 2 workers; verify when risk warrants it. |
| `/orkestra ultra <task>` | Favor quality, use a stronger model and verification from another family, at most 6 workers; preserve floors. |
| `/orkestra on` or `/orkestra aç`; `/orkestra off` or `/orkestra kapat` | Enable or disable orchestration for substantial work in this session. |
| `/orkestra update` or `/orkestra güncelle` | Follow `references/update.md`. |
| `/orkestra why <model> <class>` or `/orkestra neden <model> <class>` | Explain a selection or rejection. |

These are skill-level commands, not literal Python subcommands. Explicit user instructions about the model, tool, worker count and mode take priority. Respect the atlas default policy unless the user changes it; do not add paid services, API keys or credits without authorization.

## Quota and selection

Default spend preference is agy, then Codex, then Claude Max; use agy's separate Claude pool before Claude Max for the same model where available. Do not select a model below the task's intelligence threshold. When Claude wins, a GPT/Gemini alternative at most 2 intelligence points lower and at most 2.2 times worse in score is preferred, except in ultra mode. Image generation and editing default to Codex's image tool where available; use the capability matrix for other media and report unavailable capabilities honestly.

Defaults, change in `platformlar.json`: weekly floors Codex 30%, Claude 30%, agy 5%; Claude also reserves 15% in its 5-hour window. Pool weights: agy 0.5–0.7, Codex 0.9, Claude 2.5. Codex and agy decisions use the weekly window; the 5-hour window eliminates work that does not fit. Claude's 5-hour window also affects its score. If every candidate is at its floor, ask the user. Below 30% Claude 5-hour capacity, delegate heavy reading, writing and translation; at 15%, reserve capacity for leadership.

Use `kapali` to disable unavailable pools, `havuz` to add or override pools, and `model` to add models with `h`, `aile`, `o`, `z` and `cagri`. Supply a manual remaining percentage in `kota` or `--kota pool:window=remaining[@ISO]`; an unreadable pool defaults to 50% and is treated as twice as expensive. Example rates and Z scores are illustrative. `--platformlar` selects another configuration file. A project `.orkestra.json` can set required or forbidden models and weights.

Read Codex and agy quota with `python -I scripts/kota_oku.py` without calling a model. If available, use the Claude desktop usage tool; remaining capacity is 100 minus percent used. Otherwise Claude's quota is unknown. The leader reads once at the start, using the 10-minute cache; `--fresh` refreshes it. Re-read when a pool approaches its floor and report newly discovered models.

Automatic mode is light if Claude weekly capacity is below 45% or 5-hour capacity below 30%, ultra only for critical work when Claude is plentiful, normal otherwise. Worker count is bounded by independent pieces, available work above the floors and mode limits of 2, 4 and 6. The selector reports `paralel ≤N`.

## Selector CLI

The script CLI stays Turkish; script output labels are Turkish; read them as data. Run from the skill directory.

| Option or command | Meaning |
|---|---|
| `--sinif` | Task class: `mekanik`, `basit`, `arastirma`, `normal`, `kod`, `zor`, `kritik`, `gorsel`, `gorsel-anlama`, `video-anlama`, `video-uret`. |
| `--is` | Work units: 1 is approximately 40–60K tokens, small 0.5, large 2–3. |
| `--mod hafif\|normal\|ultra` | Override automatic mode. |
| `--zorla model[:effort]` | Force the requested model and optionally effort. |
| `--dogrulayici model` | Select a verifier for the named author model. |
| `--kota pool:window=remaining[@ISO]` | Supply manual quota; repeat for multiple windows. |
| `--platformlar path` | Use a specific platform configuration. |
| `durum` | Show pool status and remaining work. |
| `neden --model model[:effort] --sinif class` | Explain selection or rejection. |
| `kontrol` | Run synthetic rule checks; failures exit with status 1. |
| `olc baslat` / `olc bitir --model model --efor effort --is units` | Measure consumption before and after a Codex/agy task; avoid overlapping work. |

```sh
python -I scripts/kapasite.py --sinif kod --is 1 --proje . --claude-5s 50 --claude-hafta 50
python -I scripts/kapasite.py --platformlar platforms.json --kota opencode_go:hafta=80 durum
python -I scripts/kapasite.py neden --model terra:high --sinif kod
python -I scripts/kapasite.py kontrol
```

Claude reset times can be supplied with `--claude-5s-reset` and `--claude-hafta-reset` in ISO format; `--json` requests structured output and `--senaryo` supplies a scenario. Intelligence thresholds Q (same scale as the Artificial Analysis Intelligence Index v5.0.1 per effort): mechanical 16, simple 22, research 38, normal 41, code 45, difficult 50, critical 55. Image generation counts 4x quota; video understanding and generation are reported as not automatable with the manual route. Use the first suitable result or the next if eliminated. Rates are estimates; calibrate using `olc`. If quality is insufficient, increase capability; do not compensate for insufficient model intelligence with effort alone.

## How to show it

- `/orkestra` status: if the host has an in-chat visual tool, draw a small dashboard (a fill bar per pool with the reserve hatched, the pick per task class, the current gear). Otherwise show the selector's bar lines (█ spendable, ▓ reserve, · empty) and a 3–4 line summary table, not the raw dump.
- After each task, one line: `model:effort → what it did` (for example `gpt-6.1-sol:medium → translation; claude-opus → review`).
- Docs, README and promo images: ask Codex's image tool for pictures WITHOUT text, then add names, titles and numbers yourself (image models can garble letters). To fix an existing image, pass it with `-i <file>` and close stdin. Open every image and check it: no stray text, no overflow, no imitation of real logos.

## Leader and workers

A Claude leader can use its Agent tool with model and effort controls when available. A leader cannot assume it can change its own model. If Codex, OpenCode or agy leads, follow the same classify → select → brief → execute → verify flow using its own available subagent or CLI tools. Check actual tool support before delegating. If Claude is unavailable, set `"kapali": ["claude"]` in `platformlar.json`. Never claim a model or effort changed without tool support.

Use read-only discovery, a plan, independent work and verification in a separate context, preferably from another model family where useful. Brief workers with context and paths, objective, constraints and observable completion checks. Verify external agent claims with diffs, tests, searches or screenshots; avoid bulk search-and-replace on translations. Assign easily verified, low-risk work to cheaper models and ambiguous or consequential work to stronger ones.
