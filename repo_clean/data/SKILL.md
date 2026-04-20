---
name: repo-clean
description: Analyzes and cleans up git repositories against a defined set of code quality rules. Use when asked to clean a repo, remove dead code, fix comments, enforce DRY, or manage repository quality. Operates via a SQLite todo list — supports build (analyze and populate todos), clean (work one item), summarize (interactive review), and status (show state) parameters.
when_to_use: Repository cleanup, code quality enforcement, dead code removal, comment hygiene, unused file deletion, TODO/FIXME resolution, test quality checks, CLAUDE.md hygiene.
---

# repo-clean Skill

Manages repository code quality cleanup using a SQLite todo list.

## Finding the Database

```bash
REPO_ROOT=$(git rev-parse --show-toplevel)
DB_PATH="$REPO_ROOT/.claude/repo_clean.db"
```

## Database Schema

**meta** — key/value pairs:
- `last_clean_date` — ISO 8601 UTC timestamp of last successful clean
- `last_clean_commit` — git commit hash of last successful clean

**todos** — one row per cleanup item:
| column | type | notes |
|--------|------|-------|
| id | INTEGER | primary key |
| sort_order | INTEGER | ascending processing order |
| description | TEXT | what needs to be done |
| file_path | TEXT | affected file, relative to repo root |
| rule | TEXT | which clean rule was violated |
| status | TEXT | `pending`, `in_progress`, `complete`, `failed`, `skipped` |
| notes | TEXT | Claude's notes, especially on failure |
| created_at | TEXT | UTC ISO timestamp |
| updated_at | TEXT | UTC ISO timestamp |

## Database Operations

Use Python via Bash tool for all DB operations:

```bash
python3 - <<'EOF'
import sqlite3
import os

db_path = os.path.join(
    subprocess.check_output(["git", "rev-parse", "--show-toplevel"]).decode().strip(),
    ".claude", "repo_clean.db"
)
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
c = conn.cursor()
# your query here
conn.commit()
conn.close()
EOF
```

Or inline:
```bash
python3 -c "
import sqlite3, subprocess
root = subprocess.check_output(['git','rev-parse','--show-toplevel']).decode().strip()
db = root + '/.claude/repo_clean.db'
conn = sqlite3.connect(db)
# query here
conn.commit(); conn.close()
"
```

---

## Clean Rules

Apply these rules when analyzing code. Each rule has a `rule` identifier for the DB.

### `dry` — DRY Principle
Flag duplication only when extracting a helper would reduce total line count (helper body + per-call-site overhead < current duplication). If it breaks even or grows, skip it.

### `file-size` — File Size
Files over 1,900 lines must be split into smaller, focused modules. These are pre-flagged by the caller before build runs — do not re-detect them.

When working a `file-size` todo, skip with a note if the file is primarily generated, vendored, or flat declarative data (lookup tables, SQL schemas, protocol definitions, large dispatch/match tables). Splitting these doesn't improve the code.

### `comments` — Comment Policy
Only these comment types are allowed:
- Justification comments: WHY a decision was made (not what the code does)
- Legal or license headers
- References to external algorithms, RFCs, or specifications (a link or citation)

Delete ALL other comments. Code must be self-documenting through naming. Never explain what code does in a comment.

### `dead-code` — Commented-Out Code
Delete all commented-out code blocks entirely. Do not leave disabled code in the codebase.

### `unused-files` — Unused Files
Flag files that are definitively unreferenced — not imported, not required, not referenced in any code, config, CI, or build file. Only flag files you are certain about; if there is any doubt (dynamic imports, entry points, scripts, generated files), skip them. Group all candidates into a single todo item worded as: "Verify these files are safe to delete, then delete them: [list]". Do not create one todo per file.

### `todo-fixme` — TODO / FIXME / SKIP
Every TODO, FIXME, HACK, or SKIP marker must either be:
1. **Resolved** — do the work now and remove the marker, or
2. **Linked** — include a ticket/issue reference (e.g., `TODO(#1234): ...`) so the deferral is tracked outside the code, or
3. **Removed** — if the marker is stale, obvious, or redundant.

An unresolved, unlinked TODO is noise — either commit to tracking it or delete it.

In test files, never use `t.Skip()`, `skip()`, `xit()`, `xtest`, `pytest.mark.skip`, or any equivalent skip mechanism.

### `test-quality` — Test Quality
- Follow the existing test patterns already established in this repo — read the test files first.
- If the repo pervasively mocks internal code (functions, SQL queries, internal APIs), flag this as a **single discussion todo** with 2–3 representative examples. Do NOT rewrite tests en masse — the pattern may be intentional. This todo is for the human to decide during summarize.
- Mocks for external/3rd-party calls (HTTP clients, payment providers) are expected and should not be flagged.
- Only flag coverage gaps when major functionality has no test coverage at all — do not require tests for every change, and do not chase edge cases or failure paths.

### `unused-imports` — Unused Imports
Remove imports that are never referenced in the file. Use available tooling (`ruff`, `autoflake`, ESLint, etc.) if present in the repo — otherwise detect by inspection. Flag one todo per file with unused imports.

### `unused-deps` — Unused Dependencies
Flag packages in pyproject.toml, requirements.txt, package.json, etc. that appear to have no usage anywhere in the codebase. Only flag obvious cases — if there is any doubt (runtime deps, optional features, CLI tools, transitive deps), skip them. Group all candidates into a single todo worded as: "Verify these dependencies are safe to remove, then remove them: [list]".

### `claude-md` — CLAUDE.md Hygiene
If the repo contains CLAUDE.md files, ensure they follow best practices:
- Target under 200 lines — prune ruthlessly
- Remove anything inferrable from reading the code
- Ensure all `@imports` reference existing files
- Must include: non-obvious commands, architectural gotchas, non-default conventions
- Must exclude: standard language conventions, file-by-file descriptions, verbose tutorials

---

## Parameters

### `build`

Analyze the repository and populate the todo list. Do NOT begin working items.

**Steps:**

1. Resolve repo root and DB path via `git rev-parse --show-toplevel`
2. Read existing todos from the DB so agents do not duplicate what is already there:
   ```sql
   SELECT file_path, rule FROM todos WHERE status NOT IN ('complete', 'skipped')
   ```
3. Query `meta` for `last_clean_commit`:
   - Found → `git diff <hash>..HEAD --name-only` → determine the set of changed files
   - Not found → full codebase scan
4. You are the orchestrator. Spawn agents to detect violations — one agent per rule. Launch up to 4 agents at a time and work through all rules before proceeding. Rules to cover (skip `file-size`, already seeded by the caller):
   - `dead-code`, `unused-files`, `unused-imports`, `unused-deps`, `todo-fixme`, `comments`, `dry`, `test-quality`, `claude-md`
5. Brief each agent with: the rule definition (from the Clean Rules section), the repo root path, the set of files to scan, and the list of existing todos to avoid duplicating. Tell each agent to return a list of violations in the format: `file_path | description`.
6. Collect all agent results. For each violation not already in the existing todos, INSERT a todo:
   ```python
   now = __import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat()
   c.execute("""
       INSERT INTO todos (sort_order, description, file_path, rule, status, created_at, updated_at)
       VALUES (?, ?, ?, ?, 'pending', ?, ?)
   """, (sort_order, description, file_path, rule, now, now))
   ```
7. Order todos: `file-size` first, then `dead-code`, then `unused-files`, then `unused-imports`, then `unused-deps`, then `todo-fixme`, then `comments`, then `dry`, then `test-quality`, then `claude-md`
8. Print a summary of what was found grouped by rule, including any `file-size` items already in the list

### `clean`

Work ONE pending todo item, then exit. The calling script handles the loop.

**Steps:**

1. Resolve repo root and DB path
2. Fetch next item (resume any interrupted in_progress item first):
   ```sql
   SELECT * FROM todos WHERE status IN ('in_progress', 'pending') ORDER BY CASE status WHEN 'in_progress' THEN 0 ELSE 1 END, sort_order LIMIT 1
   ```
   If none found, print "No pending items." and exit.
3. Set item to `in_progress`:
   ```python
   now = ...isoformat()
   c.execute("UPDATE todos SET status='in_progress', updated_at=? WHERE id=?", (now, item_id))
   ```
4. Work the item — read the file, make the necessary changes, run tests if applicable
5. If you discover additional violations while working, INSERT them as new `pending` todos (append to end of sort_order)
6. On success:
   ```python
   c.execute("UPDATE todos SET status='complete', updated_at=? WHERE id=?", (now, item_id))
   ```
7. On failure — document exactly what you tried:
   ```python
   c.execute("UPDATE todos SET status='failed', notes=?, updated_at=? WHERE id=?", (notes, now, item_id))
   ```
8. Print what was done (or why it failed) and exit

### `summarize`

Interactively review the todo list with the user. Your role here is **todo list management only** — do NOT work, fix, or implement any items. Stay in conversation until the user says they are done.

**Steps:**

1. Resolve repo root and DB path
2. Display a summary:
   - Meta: last clean date, last clean commit
   - Counts by status (pending, in_progress, complete, failed, skipped)
   - All `failed` items with their notes
   - All remaining `pending` items
3. Engage the user. They may want to:
   - Reset a failed item: `UPDATE todos SET status='pending', notes=NULL, updated_at=? WHERE id=?`
   - Add a new item: `INSERT INTO todos ...` (append to sort_order)
   - Skip an item: `UPDATE todos SET status='skipped', updated_at=? WHERE id=?`
   - Add notes to an item
   - Ask questions about the codebase or review specific files to decide whether to keep or skip an item
4. When the user is satisfied with the list, remind them to type `/exit` — this will start the clean loop immediately (or, if called after cleaning, proceed to finalization)

### `status`

Show current state without making any changes.

1. Resolve repo root and DB path
2. Print meta values
3. Print todo counts by status
4. List all non-complete, non-skipped todos: id, status, rule, file_path, description, notes
