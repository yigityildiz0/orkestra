# INSTALL.md: instructions for the AI agent doing the install

You are an AI coding agent (Claude Code, Codex, OpenCode, Antigravity or similar). A person asked you to
install **Orkestra** from this repository. They told you which AI platforms they have. Follow these steps
in order, adapt to their machine, fix what you can, and report honestly. Türkçe konuşan kullanıcıya Türkçe yanıt ver.

## Ground rules

- Never ask for or store API keys, passwords or tokens. Orkestra works with the subscriptions' own CLIs.
- Never turn on paid overages, credits or extra usage. Never sign up for anything.
- Do not edit unrelated configuration. Back up any file you change.
- Anything that spends quota (a test prompt to a worker) needs the person's OK first.
- What the person told you is a starting point. Check what is really installed and say where reality differs.

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
| ChatGPT Plus / Pro via **Codex CLI** | `codex --version`; on Windows the newest build is in `%LOCALAPPDATA%\OpenAI\Codex\bin\<hash>\codex.exe` | workers, image generation, quota read automatically |
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

Orkestra ships with three built-in pools: `claude`, `codex`, and Antigravity's `agy_gemini`, `agy_argon` and
`agy_tp`. Write `~/.orkestra/platformlar.json` (start from `examples/platformlar.example.json`):

- `"kapali"`: every built-in pool the person does **not** have (for example `["agy_gemini", "agy_argon", "agy_tp"]`).
  If Claude is not available, add `"claude"`.
- `"havuz"`: one entry per extra platform: `{"taban": {"hafta": 10}, "agirlik": 0.6, "ad": "OpenCode Go"}`.
  `taban` is the reserve (percent) never spent; `agirlik` is how reluctant Orkestra is to spend it (lower means spend first).
- `"model"`: one entry per model on those platforms: `h` (pool), `aile` (family, used to pick a cross-family verifier),
  `o` (share of the weekly window one medium task costs, start with 1.0), `z` (intelligence per effort, from the
  Artificial Analysis Intelligence Index v5 for that model and effort; if you cannot find it, use a cautious low value
  and tell the person), `cagri` (the exact headless command; verify it with the CLI's `--help`).
- `"kota"`: if the platform cannot report its remaining quota, leave it out (Orkestra then assumes 50% and treats the
  pool as twice as expensive), or ask the person for a rough percentage.
- Policy changes the person asks for (another reserve, "never use X") go here too.

## 6. Verify

Run from the installed skill folder:

```sh
python -I scripts/kapasite.py kontrol        # every line must say PASS
python -I scripts/kota_oku.py --fresh        # reads Codex and Antigravity quota; no model is called
python -I scripts/kapasite.py durum          # pools, reserves and remaining work as the person's setup sees it
```

Fix problems you can fix (wrong path, missing pool, a typo in `platformlar.json`). If a built-in model is missing from
the person's CLIs or a new one appears ("YENİ MODEL" in the output), run the update flow in
`skills/orkestra/references/update.md` now, so the atlas and scores match what they really have.

With the person's OK, send one tiny prompt ("reply with OK") through each worker platform's `cagri` command and check
that it answers.

## 7. Report

Tell the person, in plain words and in their language:

1. Which platforms were found, which are active in Orkestra, and anything they listed that is not installed.
2. The files you wrote or changed (and backups).
3. How to use it: `/orkestra` (status), `/orkestra <task>`, `/orkestra light <task>`, `/orkestra ultra <task>`,
   `/orkestra on` / `off`, `/orkestra update` (monthly or when a new model ships). Mention auto mode: for bigger jobs it
   switches on by itself and says in one line which model it picked and why.
4. What you could not verify, and why.
