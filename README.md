**English** · [Türkçe](README.tr.md)

# Orkestra

A Claude Code skill that picks the model, effort and platform for sub-agent and multi-step work: **quality first, then quota**.

It is for people who run Claude Code next to other subscriptions (Codex, Gemini via Antigravity, a free API, local models) and do not want to choose a model by hand for every sub-task, or drain one quota while the others sit idle.

```sh
git clone https://github.com/yigityildiz0/orkestra ~/.claude/skills/orkestra && python3 -I ~/.claude/skills/orkestra/scripts/ork.py kur
```

Windows (PowerShell) and the remaining setup steps are under [Install](#install).

## Features

- **Quality floor.** Every task class has a quality threshold. A model below it is never picked to produce the result; when quota runs short, the job waits instead of falling back to a weaker model.
- **Capacity aware.** It reads what is left in each subscription pool (Claude, Codex, Gemini/Antigravity), plus optional free APIs and local models. It never spends below your per-pool floors and keeps a last share for critical work.
- **Leader ceiling.** Workers never exceed the leader's own model and effort. If a task needs more than that, it asks you instead of quietly downgrading.
- **Cross-family verification.** Output is checked by external evidence first (tests, schemas, link lookups), then by a different model family. The leader never grades its own work.
- **Privacy by default.** Data with no declared class is treated as unknown. Health and secret data stays on the host provider and local models unless you explicitly approve otherwise.
- **Self-updating registry.** `/orkestra-guncelle` finds new models, successors and retirements, and records every score with its source link.
- **Cheap to run.** The scripts use only the Python standard library and call no model themselves; reading quota and choosing a model cost zero tokens.

## How a task is routed

1. **Classify**: task class (mechanical, simple, research, normal, code, hard, critical), domain, data class, size.
2. **Read quota**: remaining share per pool; unreadable pools count as unknown and are never preferred.
3. **Select**: `ork sec` returns the model, effort, platform, a ready call line and fallbacks.
4. **Split and brief**: independent parts run in parallel, each with a short brief written for the target model family.
5. **Run and verify**: workers return; the result is checked as described above.
6. **Report**: the leader states the choice up front and lists every worker at the end.

Small tasks are not split: the leader just does them.

## Install

**Requirements:** Python 3.10 or newer (verified on 3.12) and Claude Code. Codex, Antigravity and free APIs are optional; a platform that is not installed stays closed during discovery.

1. Put this repository in your skills folder.

   ```sh
   # macOS / Linux / Git Bash
   git clone https://github.com/yigityildiz0/orkestra ~/.claude/skills/orkestra
   ```

   ```powershell
   # Windows PowerShell
   git clone https://github.com/yigityildiz0/orkestra "$HOME\.claude\skills\orkestra"
   ```

   No git? Download the ZIP of the `main` branch from the **Code** button and unpack it as `~/.claude/skills/orkestra`.

2. Run the installer. It copies the `/orkestra-guncelle` menu command to `~/.claude/commands` and creates your personal files in `~/.orkestra` from the examples. Files you already have are left alone.

   ```sh
   python3 -I ~/.claude/skills/orkestra/scripts/ork.py kur
   ```

   On Windows: `python -I "$HOME\.claude\skills\orkestra\scripts\ork.py" kur`. Below, `ork` stands for this command.

3. Edit the two personal files in `~/.orkestra`:
   - `kullanici-kurallari.json`: your rules (floors, banned model families, privacy lists, extra-cost policy).
   - `platformlar.json`: your platforms and pools. Codex and Antigravity start as `"durum": "kapali"` (closed); set `"aktif"` for the ones you actually have. `ork kesif --giris` shows which CLIs are installed and signed in.

4. Check the setup, then start a new Claude Code session.

   ```sh
   ork kontrol
   ```

`~` is your home folder (`%USERPROFILE%` on Windows). Personal files live only in `~/.orkestra` and never in this repository.

## Use

| Command | What it does |
|---|---|
| `/orkestra <task>` | Classify the task, choose, split, run, verify. |
| `/orkestra kota` | Remaining quota per pool. |
| `/orkestra hafif <task>` | Light: the cheapest model that still meets the threshold, at most 2 workers. |
| `/orkestra ultra <task>` | Ultra: top tier allowed, verified by a different family. Floors and privacy still apply. |
| `/orkestra neden <model> <class>` | Why a model was chosen or ruled out. |
| `/orkestra plan` | Weekly plan: target per day for each pool. |
| `/orkestra aç` / `kapat` | Orchestrate every substantial task in this session, or stop. |
| `/orkestra-guncelle [hizli \| tam \| platform \| platform-ekle <name> \| model <name>]` | Update the model and platform registry. `tam` plans source-backed web research for the platforms you own. |

The keywords are Turkish (`hafif` = light, `kota` = quota, `neden` = why, `aç`/`kapat` = on/off, `guncelle` = update). You can also steer in plain words: "use 4 agents", "run this on Codex", "do not spend Claude".

`ork --help` prints the full command-line reference.

## Update

- **The skill:** `git -C ~/.claude/skills/orkestra pull`, then `ork kur` once more to refresh the menu command.
- **Models and platforms:** `/orkestra-guncelle`. Run it when a new model ships, or about once a month.

## Uninstall

Delete the skill folder `~/.claude/skills/orkestra` and the menu command `~/.claude/commands/orkestra-guncelle.md`. Delete `~/.orkestra` too if you also want to drop your rules, platform file and measurement history.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `HATA kişisel dosya yok, örnek veri yüklendi` | The personal files are missing. Run `ork kur`, then edit them. `--ornek-kabul` only tries the selector with the sample data. |
| `/orkestra-guncelle` is not in the `/` menu | Run `ork kur` and open a new session. |
| A platform is never chosen | It is still closed in `platformlar.json`, or not signed in. Check with `ork kesif --giris`. |
| A pool shows as unknown | Its quota cannot be read. Claude's quota has no programmatic endpoint: pass it with `--claude 5s=<left>,hafta=<left>`, or let the leader read it from the usage screen. |
| `ork sec` exits with 4 or 5 | 4: the selector needs your answer or approval first. 5: no pool has room yet; the message says when the earliest one reopens. |
| `ork kontrol` fails | Check `python --version` (3.10 or newer). If it still fails, open an issue with the output. |

## Repository layout

| Path | Contents |
|---|---|
| `SKILL.md` | Entry point the leader reads. |
| `references/` | Detail read on demand: algorithm, briefs, privacy, update flow, platform notes (in Turkish). |
| `scripts/ork.py`, `scripts/ork/` | The command-line tool: selector, quota reader, discovery, updater. |
| `data/` | Public model data, schemas and `*.ornek.json` examples of the personal files. |
| `commands/` | The `/orkestra-guncelle` menu command. |
| `tests/` | Test suite, run by `ork kontrol`. |

The skill and its reference documents are written in Turkish; the skill description is bilingual.

## Contributing

Run `ork kontrol` before every change and add a test for new behavior. Before publishing, `ork disa-aktar --kuru` must come back clean (no personal data). The rules are in [AGENTS.md](AGENTS.md).

## License

[MIT](LICENSE). Third-party scores and licensing notes: [NOTICE.md](NOTICE.md).
