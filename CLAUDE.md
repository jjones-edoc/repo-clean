# repo-clean

Python CLI tool that uses Claude Code to iteratively clean up git repositories against a defined set of rules.

## Install & Run

```bash
pip install -e .   # install once from repo root
repo-clean         # run from inside any git repo
```

## Commands

```bash
repo-clean           # full run: build → clean loop → summarize → finalize
repo-clean build     # analyze repo and populate todo list only
repo-clean clean     # run clean loop on existing todos
repo-clean scaffold  # (re)configure the .claude/repo-map.md navigation file
repo-clean status    # show current state (no Claude invoked)
```

## Tests

```bash
pip install -e .[test]
pytest
```

## Skill Sync

On every invocation, `skill.py` compares a SHA-256 hash of the bundled `data/SKILL.md` against the installed skill file. If they differ, it overwrites. To update the skill, edit `data/SKILL.md` and reinstall (`pip install -e .`).

## Per-Repo State

Each cleaned repo gets `.claude/repo_clean.db` (auto-added to `.gitignore`). The DB stores:
- `meta` table: `last_clean_date` (UTC ISO), `last_clean_commit` (git hash), `repo_map_enabled` (`"1"`/`"0"`)
- `todos` table: one row per cleanup item with status (`pending`, `in_progress`, `complete`, `failed`, `skipped`)

If the user opts in via `repo-clean scaffold` (also prompted automatically on the first run after `init`), repo-clean produces `.claude/repo-map.md` — a factual package/symbol/dependency overview for Claude Code sessions. Unlike the DB, this file **is** committed (shared team resource, refreshed automatically during `build` when mapped paths change).

## Clean Rules

See `data/SKILL.md` for rule definitions and DB interaction protocol.
