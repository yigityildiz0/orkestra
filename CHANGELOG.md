# Changelog

Notable changes to Orkestra are recorded here, following [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
The v6 entry is not yet tagged as a GitHub release.

## v6 (unreleased)

### Added

- `skills/orkestra/references/playbook.md`: 12 patterns and 41 scenarios, a routing priority table, six helper
  roles, a busy-platform decision tree and guidance for designing a route. New discovered routes require approval.
- Helper selection through `kapasite.py --rol`: watchdog (`nobetci`), checker (`kontrolcu`), judge (`hakem`),
  messenger (`haberci`), archivist (`arsivci`) and devil's advocate (`muhalif`). Thresholds depend on role and job;
  `--dogrulayici` takes the producer's model name to exclude its family. Judges and devil's advocates use non-free
  pools. A watchdog reads progress and reports evidence to the leader; it does not fix files or direct workers.
- `skills/orkestra/scripts/evren_suru.py`: standard-library text client, parallel calls (swarm), bulk jobs,
  closed-answer voting, candidate files for external tests and quote-checked extraction. It never executes model
  code. Non-free judges/mergers must meet the job threshold. Claimed swarm intelligence gain is capped, requires
  a verifiable method and is calibrated downward only from audited results. Audit one in five accepted results;
  calibration starts after 20 records, intelligence reduction after 30 with acceptance below 0.8. Current EVREN
  scores give no swarm gain for research or harder work; tests from the weak model give no gain either.
- `examples/evren.example.json`: optional free-platform configuration, daily quota, key-presence gate,
  expiry, public-data restriction, concurrency, forbidden paths and model/rate evidence labels. EVREN is Turkey's
  national LLM platform; the configured free period ends on 1 December 2026 at 03:00 Turkey time. Missing
  `EVREN_API_KEY` or expiry closes the selector's pool. It is not required for subscription platforms.
- Busy-platform handling: short Retry-After/reset hints use exponential backoff with jitter (at most two retries);
  a busy model gets persistent cooldown and a same-tier sibling, never below the effective threshold or primary
  score minus one. Unhinted/long 503 cooldown grows 5/10/20 minutes. Daily exhaustion, token-window and concurrency
  limits cool the whole platform; the selector routes around it, offers a short wait when appropriate, or suggests
  a partial split. After cooldown a 16-token ping tests recovery. File-locked slots, model-share adjustment and a
  five-minute token bucket coordinate calls across workers.

### Changed

- Reworked `kapasite.py` for free/spend-down pools, daily decision windows, expiry and environment gates, roles,
  swarm estimates, model-specific effort costs and latency. It chooses an economical effort that meets the
  intelligence threshold; near-tied efforts of one model prefer the cheaper/faster one. agy calls distinguish
  read-only and editing modes and use an estimated-duration timeout instead of a fixed 180 seconds.
- Reworked `kota_oku.py` with optional EVREN quota/model metadata reads, normalized quota fields, locked atomic
  state updates and persistent cooldown. Quota readings remain cached for ten minutes; cooldown lines are fresh.
- Removed the fixed worker cap in auto mode, including when auto selects light or ultra behaviour. Independent
  pieces, expected quota consumption and platform concurrency decide. Only explicitly requested light/ultra
  caps paid-pool workers at 2/6. Free-pool pieces queue in waves; a time budget can move overflow to another pool.
- Antigravity reserves are now 0% with weight 0.15. Free/spend-down pools use flat scarcity and stay preferred while
  suitable work fits, including near zero. Codex keeps 30% weekly; Claude keeps 30% weekly and 15% in five hours.
  No gear lowers the intelligence threshold. New pools default to a 10% decision-window reserve, or 0% when free
  or spend-down, weight 1.0 and five-hour scoring weight 0.
- Updated the model atlas and refresh instructions for effort evidence, available variants, optional EVREN,
  helper roles and both offline check commands. Added beginner explanations and bilingual v6 routing diagrams.

### Fixed

- Spend-down pools no longer become artificially scarce and drift to Codex or Claude while suitable work fits.
- Missing/malformed decision windows cannot yield a zero-cost score. Unreadable **paid** quota is labelled as an
  assumption (50%, double-cost penalty); **free** quota instead uses a configured estimate or 80%, without that
  penalty.
- Whole batches account for consumption shared across models in the same pool, success probability and a 25%
  five-hour margin. Non-spend-down paid pools plan at most 90% of capacity above reserves. This protects reserves
  under the consumption estimates; unknown quota and estimated rates are not proof of real remaining capacity.
- Free-platform calls carry the effective minimum intelligence into sibling fallback. Explicit platform-file
  choices reach the client too. Interrupted streams count as failures; stale or malformed cooldown records are
  bounded/handled without silently losing a valid platform-wide block.

### Security-Privacy

- Public/free sharing is closed by default (`--veri bilinmiyor`); only explicitly public, non-personal work with
  `--veri genel` qualifies. Before sending, the client blocks matching key/credential patterns, checksum-valid
  Turkish IDs, TR IBANs, Luhn-valid cards, e-mails, Turkish phone numbers, health terms and secret/forbidden paths.
  Pattern scanning cannot recognise every name, address or other personal detail; classification remains essential.
- Fail-closed sending: missing/unreadable pool configuration, secret or forbidden-pool project rules and
  unscannable files stop requests. File scans cover text and supported Office formats; binary/image, undecodable
  or oversized files are refused. Path checks resolve symlinks, junctions and short names. There is no scan override.
- EVREN is the only exception to the no API keys rule. The person sets their own user environment variable;
  the AI helper checks presence only. Runtime scripts read it in memory to authenticate, mask it in output/errors,
  require HTTPS and do not follow redirects. Codex, Claude and Antigravity subscriptions never need keys.
- Editing through an EVREN Codex profile requires a scanned, clean public-file copy and explicit
  `-s workspace-write`; that sandbox alone does not restrict all file reads.

## 1.0 - 2026-11-08

- Initial routing, quota reader, model atlas, install instructions and MIT license
  ([6a21cf1](https://github.com/yigityildiz0/orkestra/commit/6a21cf12a9065582d678922aa953ed80457ec886)).
- Bilingual cast illustrations, social assets, contribution notes and plain-language introduction (`43b00cc`).
- Image animation route documented in the atlas (`45a17e9`).
- Automatic activation, selection-reason notes and a beginner install prompt (`0bc69ce`). All four local commits
  above are dated 2026-11-08; this history does not establish a published GitHub tag.
