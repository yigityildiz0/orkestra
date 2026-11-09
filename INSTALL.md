# INSTALL.md: instructions for the AI agent doing the install

You are an AI coding agent (Claude Code, Codex, OpenCode, Antigravity or similar). A person asked you to
install **Orkestra** from this repository. They told you which AI platforms they have. Follow these steps
in order, adapt to their machine, fix what you can, and report honestly. Türkçe konuşan kullanıcıya Türkçe yanıt ver.

## Ground rules

- Codex, Claude and Antigravity subscriptions use their own signed-in CLIs and never need API keys. Never ask for, read, print, type or store credentials. The **only exception to the no API keys rule** is an optional free platform such as EVREN: the person sets their own `EVREN_API_KEY` user environment variable themselves. You check presence only; the runtime scripts use the value in memory for authentication, without exposing it.
- Never turn on paid overages, credits or extra usage. Never sign up for anything.
- Do not edit unrelated configuration. Back up any file you change.
- Anything that spends quota (a test prompt to a worker) needs the person's OK first.
- What the person told you is a starting point. Check what is really installed and say where reality differs.
- Sending to public/free platforms is **closed by default**. Always pass `--veri`; only the person's explicit public, non-personal classification permits `--veri genel`. Unknown, personal, confidential and health data stay out, even when a free model is available.

## 1. Get the files

Clone or download this repository into a temporary folder:

```sh
git clone https://github.com/yigityildiz0/orkestra
```

If `git` is missing, download `https://github.com/yigityildiz0/orkestra/archive/refs/heads/main.zip` and unzip it.

## 2. Check Python

Orkestra's helper scripts need Python 3.10 or newer (`python --version`, or `python3 --version`, or `py -3 --version`
on Windows). If it is missing, tell the person how to install it for their OS and continue after they agree.

## 3. Find the platforms

For each platform the person listed, and for the ones below even if they did not list them, check whether it is
installed and signed in. Use the tool's own version or status command; do not guess.

| Platform | Typical check | Role in Orkestra |
|---|---|---|
| ChatGPT Plus / Pro via **Codex CLI** | `codex --version`; if absent from PATH, discover the installed executable | workers, image generation, quota read automatically |
| **Claude Code** (Claude Pro / Max) | `claude --version` | usual leader; Claude workers |
| **Google Antigravity** CLI (Google AI Pro) | `agy --version`, `agy models` | Gemini workers and a separate Claude/GPT pool; quota read automatically |
| **OpenCode** (Go plan or its providers) | `opencode --version` | extra workers (for example Kimi, DeepSeek, Qwen, GLM, whatever the person's plan offers) |
| Other CLIs that can run one prompt headless | the CLI's `--help` | extra workers |

### If something is missing

Many people only know the chat apps. For every subscription the person pays for but whose terminal app is missing:
1. Say in plain words what it is ("Codex is ChatGPT's app for the terminal; it comes with your Plus plan").
2. Ask before installing. Use only the official installer from the vendor's own site or package (check its current docs).
3. If you cannot install it yourself, give click-by-click steps for their operating system.
4. Let the person sign in themselves in the browser window the tool opens. Never ask for or type their password.
5. Check again with the tool's version or status command before moving on.

## 4. Put the skill where each leader can find it

Copy the folder `skills/orkestra` (keep its `references/` and `scripts/`) into the skills folder of every tool
the person will use as a leader. Check that tool's current documentation for the exact folder. Common places:

- Claude Code: `~/.claude/skills/orkestra`
- Codex: `~/.codex/skills/orkestra`
- Antigravity: its global skills folder (for example `~/.gemini/config/skills/orkestra` on recent builds)
- OpenCode: its skills or instructions folder per its docs

If a tool has no skills feature, add a short line to its global instructions file pointing to `skills/orkestra/SKILL.md`.

## 5. Describe the person's platforms

Orkestra ships with three built-in platforms across five quota pools (shared model allowances): `claude`, `codex`,
and Antigravity's `agy_gemini`, `agy_argon` and `agy_tp`. Write `~/.orkestra/platformlar.json` (start from
`examples/platformlar.example.json`). Never put credentials in this file.

Keep the built-in reserves unless the person explicitly changes the policy: Codex **30% weekly**, Claude
**30% weekly plus 15% in its 5-hour window**, Antigravity **0%**. These reserves are never spent in any gear or
across a batch. Free platforms also default to 0%; they and Antigravity stay preferred until suitable work no
longer fits. Intelligence requirements never drop, even for a free pool or low quota.

Configure these fields:

- `"kapali"`: every built-in pool the person does **not** have (for example `["agy_gemini", "agy_argon", "agy_tp"]`).
  If Claude is not available, add `"claude"`.
- `"havuz"`: one entry per extra platform: `{"taban": {"hafta": 10}, "agirlik": 0.6, "ad": "OpenCode Go"}`.
  `taban` is the reserve (percent) never spent; `agirlik` is how reluctant Orkestra is to spend it (lower means spend first).
  Missing fields default to a 10% reserve in the decision window (5-hour default 0), weight 1.0 and `w5` 0;
  `"bedava"` (free) or `"harcanabilir"` (spend-down) pools default to reserve 0. These defaults for **new** pools
  do not replace the built-in reserves above. Optional free-platform fields belong to step 6.
- `"model"`: one entry per model on those platforms: `h` (pool), `aile` (family, used to pick a cross-family verifier),
  `o` (percent of each quota window one medium task costs), `z` (intelligence per effort from the Artificial Analysis
  Intelligence Index v5), `cagri` (the exact headless command; verify it with the CLI's `--help`). Mark estimated
  rates `o_kaynak: "tahmin"`; if intelligence evidence is unavailable, mark `z_kaynak: "tahmin"` and say so.
  Estimated intelligence is excluded from research and harder work (Q ≥ 38); easier work needs a 2-point margin.
- `"kota"`: supply an honest remaining percentage or leave it unknown. Missing or malformed decision windows in
  **paid** pools use a labelled 50% assumption and a double-cost penalty; they never become a zero-cost bargain.
  **Free** pools use a configured estimate or 80% without that penalty. Neither assumption verifies the real quota
  or reserve. Codex/Antigravity decide by weekly quota, EVREN by daily quota; Claude needs both 5-hour and weekly data.
- Policy changes the person asks for (another reserve, "never use X") go here too.

Auto mode has no fixed worker cap: independent pieces (`--parca`), expected consumption above reserves and platform
concurrency decide. Only an explicit light/ultra request imposes 2/6 workers across paid pools; free pools are
outside those caps and queue pieces in waves. Do not split small jobs merely to use more workers.

## 6. Optional: enable a free platform

**Skip this entire step unless the person wants it.** EVREN is an optional example of Turkey's national LLM
platform, free until **1 December 2026 at 03:00 Turkey time** according to the shipped configuration. It is not
needed for Orkestra or for any subscription. Do not create an account, obtain a key or enable paid usage for them.

If they already have their own EVREN account and choose to enable it:

1. Merge the `havuz`, `model`, `takma` and `kota` entries from `examples/evren.example.json` into their existing
   `~/.orkestra/platformlar.json`, preserving other platforms. Keep `gerekli_env: "EVREN_API_KEY"`,
   `gizlilik: "kamu"`, `bedava: true`, the daily reserve 0 and `bitis`. The example also defines concurrency (`esz`,
   `paralel_ajan`), the quota reader and forbidden folders (`yasak_yol`); adapt forbidden folders to their machine
   without publishing their private paths. Without the key, or after the end date, the selector keeps the pool closed.
2. Tell the person to set a **user environment variable themselves**, with the steps below. Never ask them to paste
   the key into chat, a prompt, a command argument, a screenshot or a configuration file. Do not watch or record
   their input. Do not run shell tracing (`set -x`) or dump the environment.
3. After they finish, check **presence only**. With a fresh terminal or AI app that inherited the variable, use
   `python -I -c "import os; print('EVREN_API_KEY' in os.environ)"`. This prints only `True` or `False`.
   On Windows the selector also checks user variables in the registry, so an older app may still find it even when
   this process-only check says `False`. Reopen the relevant app with the person's agreement if needed; never
   close active sessions yourself. Report only present, absent or not verified. Do not retrieve the value to test it.

Give the person these plain steps in their language:

- **Windows:** open Start, search for **Edit environment variables for your account**, open it, then under
  **User variables** choose **New**. Name it `EVREN_API_KEY`, enter the key privately as the value, and confirm.
  Open a new terminal and launch the AI app from it; an already open app may need reopening to inherit it.
- **macOS (default zsh):** open Terminal. Turn off tracing with `set +x`, then run
  `read -rs 'EVREN_API_KEY?EVREN key (hidden): '`. Enter the key privately at the hidden prompt and press Enter.
  Run `export EVREN_API_KEY`, then launch the AI CLI from that same Terminal window.
- **Linux (bash):** open a terminal. Turn off tracing with `set +x`, then run
  `IFS= read -r -s -p 'EVREN key (hidden): ' EVREN_API_KEY`. Enter the key privately at the hidden prompt and press
  Enter. Run `export EVREN_API_KEY`, then launch the AI CLI from that same terminal.

The macOS/Linux steps set a user-session variable for that terminal and its child apps; repeat them in a new
terminal. Do not put a literal key in shell history or startup files. Other shells need equivalent hidden-input steps.

Only explicitly public, non-personal work uses `--veri genel`. `evren_suru.py` scans before sending: keys, ID
numbers, IBANs, cards, e-mails, phone numbers, health terms and secret paths block the request. Unscannable files,
missing/unreadable platform settings and a project marked secret also stop it. The scan is pattern-based and
cannot recognise every name or address; the public-data declaration remains essential. There is no scan override.
For file editing, follow SKILL.md: scan a clean copy containing only the public job files and explicitly use
`-s workspace-write`; that sandbox does not itself restrict all reads.

EVREN's current models qualify on their own only for mechanical/simple work. Parallel calls (a swarm) do not make
them strong enough for research or code; keep the full job's threshold for its merger/verifier. Busy-platform
retry, cooldown, same-tier sibling and ping behaviour is detailed in [`CHANGELOG.md`](CHANGELOG.md).

## 7. Verify

Run from the installed skill folder:

```sh
python -I scripts/kapasite.py kontrol        # offline synthetic rule checks
python -I scripts/evren_suru.py kontrol      # offline free-platform checks with fakes
```

Every individual check must say PASS; each command also prints a count summary and must exit 0. These checks
need neither a real key nor a network and do not prove sign-in or live service access.

Then, if network/local-tool access is allowed, run:

```sh
python -I scripts/kota_oku.py --fresh        # local quota tools; EVREN /quota and /models if its key exists
python -I scripts/kapasite.py durum          # configured pools, reserves, estimates and remaining work
```

No model is called by quota reading, but optional EVREN metadata needs network access and its runtime reads the
environment key internally. Do not call these live readers in an offline session. A ping **does** call a model and
uses a tiny quota; do not describe it as a free offline check.

Fix problems you can fix (wrong path, missing pool, a typo in `platformlar.json`). If a built-in model is missing from
the person's CLIs or a new one appears ("YENİ MODEL" in the output), run the update flow in
`references/update.md` from the installed skill folder when network access is allowed. Otherwise report the
unverified difference and defer the refresh; do not invent scores or successful access.

With the person's OK, send one tiny prompt ("reply with OK") through each worker platform's `cagri` command and check
that it answers.

## 8. Report

Tell the person, in plain words and in their language:

1. Which platforms were found, which are active in Orkestra, and anything they listed that is not installed.
2. The files you wrote or changed (and backups).
3. How to use it: `/orkestra` (status), `/orkestra <task>`, `/orkestra light <task>`, `/orkestra ultra <task>`,
   `/orkestra on` / `off`, `/orkestra update` (monthly or when a new model ships). Mention auto mode: for bigger jobs it
   switches on by itself and says in one line which model it picked and why.
4. Which offline checks passed (counts and exit codes), which quota readings were live versus assumed, and which
   platforms actually answered a permitted test. Installation, sign-in and real execution are separate findings.
5. Whether optional EVREN was skipped, key presence was checked, or access was actually tested. State that public/free
   sharing starts closed; explain reserves and auto's lack of a fixed worker cap. Never include a key or private content.
6. What you could not verify, why, and the exact next step. Do not call the setup fully working if execution is untested.
