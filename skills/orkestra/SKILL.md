---
name: orkestra
description: Routes tasks across available AI models and quota pools by difficulty, remaining capacity, and user preferences, with verification where appropriate. Activates on its own for substantial, multi-step or subagent work (auto mode); obeys any model, tool or worker count the user names.
---

# Orkestra

The leader plans, briefs, delegates and verifies while conserving capacity without reducing quality. The default pools are Claude Max (leader), ChatGPT/Codex and Google Antigravity (agy). Configure other platforms in `~/.orkestra/platformlar.json`; see `examples/platformlar.example.json` (paid pool) and `examples/evren.example.json` (a free, key-gated, privacy-restricted platform) in the repository.

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

## Auto mode (activates on its own)

Apply the Orkestra method without being asked when work will use subagents, has several independent parts, means long reading, writing or translation, or needs an image. Skip it for a one-file fix, a short question or chat: the leader does those itself.

Goal, compared with plain Claude subagents: the same or better quality, fewer Claude tokens, and faster results because independent parts run in parallel.
- Plenty of quota is never a reason to pick the biggest model or the highest effort: the selector looks for the most economical variant that is smart enough and penalises overkill.
- Low quota is never a reason to drop below the task's intelligence threshold (Q) in any gear; if nothing qualifies, ask the user.
- When the pick rests on a single factor, the selector prints `↳ NOT:` (limit forced it, only one candidate left, intelligence overkill). Pass it on in one line, and say "because of limits" when quality was not the reason.
- Announce once at the start: `orkestra: <class> → <model:effort> (<platform>), N workers`. If the user objects, follow them.
- Route choice: read only the matching section of `references/playbook.md` (contents first): priority table, roles, the busy-free-platform decision tree, 12 patterns and 41 scenarios (code, research, media, quota/privacy, mixed cases). If nothing fits, design a route with its "Creative mode" principles; if it worked, PROPOSE adding it to the playbook (never write without approval).
- Worker count has NO fixed cap in auto mode: pass the number of independent pieces with `--parca N`; the selector caps it by each pool's EXPECTED consumption above its floor (success probability and the 5-hour margin included; at most 90% of what is left in a paid pool) and prints a split such as `↳ İŞÇİ: 200× evren-glm-5.3:high` starting from the cheapest pool. In a free pool concurrency (`esz` − 2, `paralel_ajan` for editing agents) is not capacity: pieces that fit its quota queue there in waves (`↳ DALGA: EVREN 200 parça, aynı anda ≤22, 10 dalga`) and spill to the next pool only if `--sure-dk` would be exceeded. Without `--parca` the selector prints pool capacities instead of inventing a number. Only an explicit `light`/`ultra` keeps the 2/6 cap, and only for paid pools. Do not split tiny work: every worker costs a brief, context and a check.

## Roles (watchdog and checker subagents)

Cheap, fast models (Haiku low/medium, Luna, Flash, a free platform on public data) can watch other workers: `python -I scripts/kapasite.py --rol nobetci|kontrolcu|hakem|haberci|arsivci|muhalif --sinif <watched job> --dogrulayici <producer> --veri <...>`. Thresholds are per role (Z ≥ max(role floor, job Q − role gap): watchdog Z≥20 for a code job, judge Z≥39; +3 in ultra mode, the header prints the effective threshold); the producer's family is excluded; judge and devil's advocate never come from a free pool; fast models rank first; monitoring roles list Opus/Sol/Argon only when nothing smaller qualifies. `--dogrulayici` takes a MODEL name (e.g. `gpt-6.1-sol`, `sonnet`), not a family; always pass it (without it no family is excluded and the selector warns). The watchdog (`nobetci`) runs in the background on ≥3 parallel workers or ≥20-minute jobs, only READS logs, diffs and test output at intervals, and reports loops, empty output, red tests, out-of-scope files, token waste, secret leaks or invented sources to the leader as `WARNING <worker> <type>: <evidence>`; it never fixes or writes to workers. The checker verifies schema and "Done" evidence, the judge gives a second opinion (MAJORITY VOTE line: the producer's answer + 2 judges from other families = 3 votes), the messenger summarizes, the archivist keeps records.

## Quota and selection

Default spend preference is a free platform if configured, then agy, then Codex, then Claude Max. Free (`bedava`) and spend-down (`harcanabilir`, agy) pools use FLAT scarcity: as long as the work fits they stay equally cheap (first at 40% and at 3% left) and are dropped with "kota bitti" (quota used up) only when the work no longer fits; a daily window counts as 1/7 of a weekly one. agy (Flash, Argon and its "Claude and GPT models" pool) is the first pool to give up and may be spent down to zero; use agy's separate Claude pool before Claude Max for the same model where available. Cheap agy quota never lowers quality or justifies a bigger model: the intelligence threshold and the overkill penalty still apply. Do not select a model below the task's intelligence threshold. When Claude wins, a GPT/Gemini alternative at most 2 intelligence points lower and at most 2.2 times worse in score is preferred, except in ultra mode. Image generation and editing default to Codex's image tool where available; use the capability matrix for other media and report unavailable capabilities honestly.

Defaults, change in `platformlar.json`: weekly floors Codex 30%, Claude 30%, agy 0 (down to zero); Claude also reserves 15% in its 5-hour window. These floors are never crossed in any gear. Pool weights: agy 0.15, Codex 0.9, Claude 2.5; effort cost is per model (Sonnet max ≈ 11.75 times medium). Codex and agy decisions use the weekly window; the 5-hour window eliminates work that does not fit. In agy the 5-hour window stops applying once the weekly quota is used up, even if it shows 100%. Claude's 5-hour window also affects its score. If every candidate is at its floor, ask the user. Below 30% Claude 5-hour capacity, delegate heavy reading, writing and translation; at 15%, reserve capacity for leadership.

Use `kapali` to disable unavailable pools, `havuz` to add or override pools, and `model` to add models with `h`, `aile`, `o`, `z` and `cagri`. Missing pool fields default to a 10% floor in the decision window (0 for `bedava`/`harcanabilir` pools), weight 1.0 and `w5` 0. Optional pool fields: `bedava`, `harcanabilir`, `karar` (`5s`/`gun`/`hafta`), `bitis` (ISO end date; the pool closes after it), `gerekli_env` (the pool loads only if that environment variable exists; its value never reaches output), `gizlilik: "kamu"` (only `--veri genel` work), `esz`, `paralel_ajan`, `suru`, `z_tavan`, `kota_okuyucu`, `olc_esik`, `yasak_yol`. Optional model fields: `z_kaynak` (`aa`, `aa-indirimli`, `tahmin`; an estimated Z is never used for Q ≥ 38 and needs a 2-point margin below it), `o_kaynak`, `dk_ib` (minutes per work unit), `bekle_dk`, `baglam`, `cikti`, `api`, `dusunme`, `suru_cagri`, `duzenle` (`o`/`cagri`/`dk_ib` used for file-editing work) and `duzenleyemez`. Supply a manual remaining percentage in `kota` or `--kota pool:window=remaining[@ISO]`; an unreadable pool, or a pool whose decision window (weekly for Codex/agy, daily for a daily-quota platform, 5-hour and weekly for Claude) is missing or malformed, defaults to 50% and is treated as twice as expensive, so an unverifiable floor never looks cheap; a free (`bedava`) pool instead defaults to 80% with no penalty. Floor values must be numbers from 0 to 100. `kota_okuyucu` currently knows only the `evren` reader; other free platforms use the manual `kota` value. Example rates and Z scores are illustrative. `--platformlar` selects another configuration file. A project `.orkestra.json` can set required or forbidden models and weights; `gizli` and `yasak_havuz` are read fail-closed (a non-boolean `gizli` counts as true with a warning; pool names are case-insensitive).

Read Codex, agy and (if its key exists) EVREN quota with `python -I scripts/kota_oku.py` without calling a model. If available, use the Claude desktop usage tool; remaining capacity is 100 minus percent used. Otherwise Claude's quota is unknown. The leader reads once at the start, using the 10-minute cache; `--fresh` refreshes it. Re-read when a pool approaches its floor and report newly discovered models.

Automatic mode is light if Claude weekly capacity is below 45% or 5-hour capacity below 30%, ultra only for critical work when Claude is plentiful, normal otherwise. Worker count is bounded by independent pieces, available work above the floors and platform concurrency; a 2/6 cap applies only when the user explicitly chose light/ultra. With `--parca` the selector reports `eşzamanlı N`, the same number as its split. Effort: the cheapest effort that reaches the needed Z; efforts of one model within 10% in score resolve to the cheaper, faster one; models with `dk_ib` (medium-effort minutes; multiplied by the effort factor) add a latency factor and `--sure-dk` drops variants that will not finish in time; models without `dk_ib` get a "süre bilinmiyor" note. agy calls get `--print-timeout` of 3 × the estimated time (at least 15m) instead of a fixed 180s.

## Selector CLI

The script CLI stays Turkish; script output labels are Turkish; read them as data. Run from the skill directory.
Before selecting (explicit `/orkestra <task>` too, not only auto mode), read the `references/playbook.md` section that fits the task: it says which agent goes first, which roles to add and when to use the free platform or a watchdog; the selector then picks the concrete model.

| Option or command | Meaning |
|---|---|
| `--sinif` | Task class: `mekanik`, `basit`, `arastirma`, `normal`, `kod`, `zor`, `kritik`, `gorsel`, `gorsel-anlama`, `video-anlama`, `video-uret`. |
| `--is` | Work units: 1 is approximately 40–60K tokens, small 0.5, large 2–3. |
| `--mod hafif\|normal\|ultra` | Override automatic mode. |
| `--zorla model[:effort]` | Force the requested model and optionally effort. |
| `--dogrulayici model` | Select a verifier for the named author model. |
| `--veri genel\|kisisel\|gizli\|saglik\|bilinmiyor` | Data class (default `bilinmiyor`); `gizlilik: kamu` pools are candidates only with `genel`. |
| `--parca N` | Number of independent pieces; sets the worker count and split. |
| `--duzenle` | The work edits files: agy `--mode accept-edits`, a free platform's editing agent; otherwise read-only (`--mode plan`). |
| `--sure-dk M` | The user is waiting: drop variants estimated to take longer than M minutes. |
| `--yontem kapali\|test\|kapsam\|acik` | Swarm method when a verifier exists (closed-answer vote, tests, quote-checked extraction, open draft). |
| `--haric pool` | Exclude a pool for this run (for example after the free platform returned exit 4). |
| `--rol nobetci\|kontrolcu\|hakem\|haberci\|arsivci\|muhalif` | Pick a watchdog/checker/judge/messenger/archivist/devil's-advocate helper for the `--sinif` job (with `--dogrulayici <producer>`). |
| `--test-evren` | The tests were written by the swarm's own (weak) model: swarm ΔZ = 0. |
| `kalite kaydet --model m --efor e --yontem y --kabul 0\|1` | Record an audited swarm result; calibrates k (and Z) downward only. |
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
python -I scripts/evren_suru.py kontrol
```

Claude reset times can be supplied with `--claude-5s-reset` and `--claude-hafta-reset` in ISO format; `--json` requests structured output and `--senaryo` supplies a scenario. Intelligence thresholds Q (same scale as the Artificial Analysis Intelligence Index v5.0.1 per effort): mechanical 16, simple 22, research 38, normal 41, code 45, difficult 50, critical 55. Image generation counts 4x quota; video understanding and generation are reported as not automatable with the manual route. Use the first suitable result or the next if eliminated. Rates are estimates; calibrate using `olc`. If quality is insufficient, increase capability; do not compensate for insufficient model intelligence with effort alone.

## Free platform: EVREN as an example

A free platform enters as an ordinary pool from `platformlar.json` (copy `examples/evren.example.json`); nothing in the selector is EVREN-specific. EVREN (Turkey's national LLM platform) is free until 2026-12-01 03:00 Turkey time; after `bitis` or without `EVREN_API_KEY` the pool stays closed. Weight 0.05, daily window, floor 0.

- Intelligence decides, not price: the best EVREN models score Z≈27-28 on the AA v5.0.1 scale (below Sonnet medium), so on their own they take only mechanical (Q16) and simple (Q22) work; research, normal, code, hard and critical work never goes there. Only models with AA evidence enter: a model without a composite AA score is left out of the platform file (the example has none). If someone adds one as `z_kaynak: tahmin`, the selector never uses it for Q ≥ 38 and needs a 2-point margin below that.
- Spend it through breadth: split the job, send clear mechanical/simple pieces (quote-backed extraction, summaries, conversion, labelling, test data, docstrings, draft translation) with `--sinif basit --veri genel --parca N`, and let a model that meets the full task's Q merge them.
- Text work calls `python -I scripts/evren_suru.py --veri genel --model <api:effort> --istem <file>` directly over HTTP (seconds); `--model` also accepts the selector name (`evren-glm-5.3:high`) or its alias, so the selector's `cagri` line can be used as is (it adds `--platformlar` when the selector used a non-default file). Other subcommands: `toplu <input.jsonl>`, `--yontem tek|kapali|test|kapsam|acik|ilk|juri`, `tara`, `kota`, `modeller`, `ping`, `soguma`, `kabul`, `kontrol`. File-editing work (slow and token-heavy: a one-word job took ~790K tokens and 209 s) only as `codex exec -p evren -m <api> -c model_reasoning_effort=<e> -s workspace-write -C <temporary_clean_copy> --skip-git-repo-check --ephemeral -o <out.txt> "<brief>"`, after `evren_suru tara <copy>` exits 0. Never drop `-s` (a global Codex config may be `danger-full-access`; also set `sandbox_mode = "workspace-write"` in the profile). workspace-write does not restrict reading, so the copy holds only the job's files and only `--veri genel` work goes there.
- Swarm only with a verifier (`--yontem kapali|test|kapsam`): effective Z gain ΔZ = k·s·v·min(T, a·log2 N) with k ≤ 1 and s = clamp((Z−(Q−8))/5, 0, 1): with today's EVREN Z ≤ 28, s = 0 for Q ≥ 36 (research and above), so a swarm does not replace a stronger model today. k is lowered after 20 records, Z after 30 records with acceptance below 0.8; both only downward. Judges and mergers come from non-free pools with Z ≥ Q. No debate or self-critique loops; the swarm never writes the tests; the script never executes its code. Audit 1 in 5 accepted results independently and record them with `evren_suru kabul <ozet.json> evet|hayir`.
- `evren_suru.py` keeps total concurrency under the account limit with file-locked slots, lowers a model's share on fair-share 429s (AIMD) and keeps a 5-minute token bucket. Strategic cooldown (persistent, cross-process, locked and atomic: `~/.orkestra/evren_durum.json` → `soguma`): (a) a short hint (Retry-After/resets_at ≤ 60 s) → exponential backoff with jitter on the same model; (b) a long or missing hint on 503, and fair share → the model cools down (503: 5-10-20 minutes) and work moves to a SIBLING model in the same Z band (never below the primary − 1 or the `--min-z <effective Q>` that the selector's CALL line carries, or the `--sinif` Q; `--kardessiz` disables); (c) daily quota (until `daily_reset_at`, else 00:00Z), the 5-minute token window and concurrency → `*` (whole platform) cooldown. The selector ranks without cooling models and prints `↳ NOT: EVREN dolu: …, 12 dk soğumada; yerine <pool> <model> (eşik aynı)`, a WAIT option (`BEKLE`, not urgent and ≤30 minutes) and, with `--parca`, a PARTIAL SWITCH (`KISMİ GEÇİŞ`: at most half to the platform, all of it when no other pool fits). When the platform is the only candidate and cooling, the "no suitable model" line takes its wait time from the cooldown and prints `↳ BEKLE`. In bulk simple jobs, queue overflow instead of pouring it into Claude Haiku. When a cooldown ends the first call sends a 16-token ping (success clears it, failure extends it). Manual: `evren_suru soguma [--temizle hepsi]`, `evren_suru ping --model <m:e>`; `kota_oku` prints a `SOĞUMA` line. Fallbacks never lower the intelligence threshold. Exit 4 when EVREN is unusable (rerun the selector, which reads the cooldown, or `--haric evren`) or 5 when there is no agreement (escalate). Full tree: `references/playbook.md` section 3. Interrupted streams count as failures, never as answers. `ping`, `kota`, `modeller`, `--kuru` and `kontrol` cost no or minimal quota.

## Privacy (closed by default)

Always pass `--veri`. The default `bilinmiyor` keeps public (`gizlilik: kamu`) pools out. Only public, non-personal data gets `--veri genel`; personal, confidential, health/clinical and customer data, secrets, private notes, personal finance and unpublished research never go to such a pool. `evren_suru.py` refuses any `--veri` other than `genel` (exit 2) and scans before sending: key patterns (sk-, ghp_, AKIA, AIza, JWT, private keys, Slack xox*, `Authorization: Bearer`, connection-string passwords, `.env`/JSON/YAML assignments such as `SECRET_KEY=`, `DB_PASSWORD=`, `"api_key": "…"`, high-entropy 32+ character strings), the key itself, checksum-valid Turkish ID numbers, TR IBANs and Luhn-valid card numbers (also with space/dot/dash separators), e-mail addresses, +90 phone numbers, health terms, `.env`/`.ssh`/`auth.json`/`*.pem` paths and the pool's `yasak_yol` folders (8.3 short names, junctions and symlinks resolved). The scan is pattern-based and misses free-form personal data such as names and addresses; the `--veri` declaration is the real gate. A match exits 3 with zero requests and prints only the type name; there is no override. A project `.orkestra.json` with `"gizli": true` (or `"yasak_havuz": ["evren"]`) keeps the pool out of that project entirely; `evren_suru.py` also looks for it from the working directory and from each sent file's folder and exits 3. Fail-closed: without a readable platform file that defines the pool, `evren_suru.py` sends nothing (exit 2). `evren_suru tara` reads UTF-8, cp1254, UTF-16 and the text inside docx/xlsx/pptx/odt; binary, image, undecodable or >4 MB files count as `taranamayan` and exit 3. The key goes only to an https base URL and redirects are not followed.

## How to show it

- `/orkestra` status: if the host has an in-chat visual tool, draw a small dashboard (a fill bar per pool with the reserve hatched, the pick per task class, the current gear). Otherwise show the selector's bar lines (█ spendable, ▓ reserve, · empty) and a 3–4 line summary table, not the raw dump.
- After each task, one line: `model:effort → what it did` (for example `gpt-6.1-sol:medium → translation; claude-opus → review`).
- Docs, README and promo images: ask Codex's image tool for pictures WITHOUT text, then add names, titles and numbers yourself (image models can garble letters). To fix an existing image, pass it with `-i <file>` and close stdin. Open every image and check it: no stray text, no overflow, no imitation of real logos.

## Leader and workers

A Claude leader can use its Agent tool with model and effort controls when available. A leader cannot assume it can change its own model. If Codex, OpenCode or agy leads, follow the same classify → select → brief → execute → verify flow using its own available subagent or CLI tools. Check actual tool support before delegating. If Claude is unavailable, set `"kapali": ["claude"]` in `platformlar.json`. Never claim a model or effort changed without tool support.

Use read-only discovery, a plan, independent work and verification in a separate context, preferably from another model family where useful. Brief workers with context and paths, objective, constraints and observable completion checks. Verify external agent claims with diffs, tests, searches or screenshots; avoid bulk search-and-replace on translations. Assign easily verified, low-risk work to cheaper models and ambiguous or consequential work to stronger ones.
