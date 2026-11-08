# /orkestra update

Start with local evidence, then research and update the atlas and selector. Record a URL and date for each material claim; mark missing evidence and contradictions explicitly. Use independent research and cross-checking when available and authorized; the leader synthesizes and edits.

## Local availability

- Run `python -I scripts/kota_oku.py` for quotas and model discovery.
- Where available, inspect `agy models` and the first 3 releases of `agy changelog`.
- Inspect `~/.codex/models_cache.json` for visibility, input modalities, context windows and reasoning levels; check `codex features list` for tools.
- Check Claude Code's model menu or official documentation, and equivalent tools for other configured platforms. Distinguish model capabilities from what each CLI and subscription can actually access.

## Research

1. Prices and total work cost: API input/output rates, Artificial Analysis cost to run and output tokens, speed, time to first token and subscription quota consumption.
2. Effort curves: score, tokens, cost, efficiency peak, diminishing returns and tasks where added effort matters.
3. Capabilities by model and access path: image, video and audio generation and understanding, PDF, web, browser/computer use, context and output limits. Separate CLI access from subscription apps.
4. Generation quality: LMArena and Artificial Analysis image and video tables, multilingual text rendering and subscription availability.
5. Strengths and weaknesses: hallucinations, long context, tool use, languages, speed, instruction following, code, known issues and retirement; provide assignment guidance.
6. Recent changes: models, plans, quotas, removals, CLI features, caching, parallel-agent costs, compression, rate limits, latency, provider differences, local models and overlooked implications.

Independently open key sources and correct unsupported claims; investigate consequential missing information.

## Update and verify

- Update `references/model-atlas.md`: scores, cost, effort, capabilities, generation priorities, strengths, defaults, changes and date.
- Update `scripts/kapasite.py` as needed for built-in models, Z scores, consumption priors, calls and class candidates. Models without a capability cannot be candidates; report when none can perform a task.
- Update model discovery lists in `scripts/kota_oku.py` as appropriate.
- Update `~/.orkestra/platformlar.json` for the user's platforms, including new or removed pools and models and evidence-based Z scores and consumption rates (`o`). Keep personal configuration private.
- Consumption priors should reflect total work cost; actual `olc` measurements override priors. Preserve the user's explicit fixed rules and bans unless the user approves a change; propose alternatives supported by evidence.

Edit the skill in place (or in your source repo), re-run `python -I scripts/kapasite.py kontrol`, copy to every tool's skills folder you use. Add meaningful rule scenarios when selector behavior changes. Check `durum` and class recommendations with available real quota data; compare with the previous decision. Report changes, evidence, uncertainty and any proposed user decisions.
