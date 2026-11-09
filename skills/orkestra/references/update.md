# /orkestra update

Start with local evidence, then research and update the atlas and selector. Record a URL and date for each material claim; mark missing evidence and contradictions explicitly. Use independent research and cross-checking when available and authorized; the leader synthesizes and edits.

## Local availability

- Run `python -I scripts/kota_oku.py` for quotas and model discovery.
- Where available, inspect `agy models` and the first 3 releases of `agy changelog`.
- Inspect `~/.codex/models_cache.json` for visibility, input modalities, context windows and reasoning levels; check `codex features list` for tools.
- For a configured free platform such as EVREN (only if its key exists; costs no tokens): `python -I scripts/evren_suru.py modeller` (`GET /v1/models`), `... kota` (`GET /v1/quota`), the public live list `GET https://api.ssyz.org.tr/api/v1/public/llm-stats` (speed, queue band, fleet concurrency) and `... ping` for a 16-token speed check.
- Check Claude Code's model menu or official documentation, and equivalent tools for other configured platforms. Distinguish model capabilities from what each CLI and subscription can actually access.

## Research

1. Prices and total work cost: API input/output rates, Artificial Analysis cost to run and output tokens, speed, time to first token and subscription quota consumption.
2. Effort curves: score, tokens, cost, efficiency peak, diminishing returns and tasks where added effort matters.
3. Capabilities by model and access path: image, video and audio generation and understanding, PDF, web, browser/computer use, context and output limits. Separate CLI access from subscription apps.
4. Generation quality: LMArena and Artificial Analysis image and video tables, multilingual text rendering and subscription availability.
5. Strengths and weaknesses: hallucinations, long context, tool use, languages, speed, instruction following, code, known issues and retirement; provide assignment guidance.
6. Free platform models (for example EVREN): for every chat model in the live list, the AA v5.0.1 score per effort (reasoning and non-reasoning separately; which snapshot and precision the platform serves), platform constraints (output cap, effort aliases), speed, concurrency and quota. Only models with AA evidence that meet at least the mechanical (16) or simple (22) threshold enter; without a composite AA score use `z_kaynak: tahmin`. Never raise a Z without a verified AA source; quality records only lower it. Keep `z_tavan` as a stale-scale guard and raise it only with a cited source.
7. Recent changes: models, plans, quotas, removals, CLI features, caching, parallel-agent costs, compression, rate limits, latency, provider differences, local models and overlooked implications.

Independently open key sources and correct unsupported claims; investigate consequential missing information.

## Free platform resilience and role models (every update)

- Error codes: check with a live `GET /v1/models/{model}` and a `ping` that the 429 codes (`concurrency_limit_exceeded`, `fair_share_limit_exceeded`, `token_rate_limit_exceeded`, `daily_token_limit_exceeded`) and the 503 `model_capacity_exhausted` body still carry `resets_at` / `daily_reset_at` / `Retry-After` under the same names. If not, update `hata_turu` and `ipucu` in `evren_suru.py` and `soguma_suresi` in `kota_oku.py`, and add a `kontrol` scenario.
- Cooldown lengths: compare `python -I scripts/evren_suru.py soguma` history and the platform's live load with the 5-10-20 minute 503 assumption and the daily reset time. Without records say "no measurement" and keep the values.
- Sibling band: if platform Z scores changed, check that `kardes_bul` (Z gap ≤ 4, never below primary − 1) still pairs sensible models and whether a new model is a sibling candidate. Check that the selector's free-platform CALL line still carries `--min-z <effective Q>` (`sec --sinif basit --veri genel --json` → `cagri`); without it a sibling switch could cross the threshold. Check the cooldown cap (36 h, daily included) and `BUYUK` (large models that monitoring roles use only as a last resort) against new models.
- Role models (`ROL`, `HIZLI` in `kapasite.py`): are the fast, cheap watchdog/checker/messenger models still the cheapest and fastest; add new fast models to `HIZLI`; check that role floors still make sense on the current Z scale. Live check: `--rol nobetci --sinif kod --dogrulayici sonnet` and `--rol hakem --sinif kod --dogrulayici sol` against the previous result.
- `references/playbook.md`: replace retired example models; add to "Discovered routes" only with user approval.

## Update and verify

- Update `references/model-atlas.md`: scores, cost, effort, capabilities, generation priorities, strengths, defaults, changes and date.
- Update `scripts/kapasite.py` as needed for built-in models, Z scores, consumption priors, calls and class candidates. Models without a capability cannot be candidates; report when none can perform a task.
- Update model discovery lists in `scripts/kota_oku.py` as appropriate.
- Update `~/.orkestra/platformlar.json` for the user's platforms, including new or removed pools and models and evidence-based Z scores and consumption rates (`o`). Keep personal configuration private.
- Consumption priors should reflect total work cost; actual `olc` measurements override priors. Preserve the user's explicit fixed rules and bans unless the user approves a change; propose alternatives supported by evidence.

Edit the skill in place (or in your source repo), re-run `python -I scripts/kapasite.py kontrol` and `python -I scripts/evren_suru.py kontrol`, copy to every tool's skills folder you use. Add meaningful rule scenarios when selector behavior changes. Check `durum` and class recommendations with available real quota data; compare with the previous decision. Report changes, evidence, uncertainty and any proposed user decisions.
