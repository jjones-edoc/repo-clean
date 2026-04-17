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
Flag only confirmed code duplication: the same logic appearing in multiple places where extracting it would genuinely simplify both call sites. Do NOT flag based on textual similarity alone, boilerplate, test setup, or config patterns. Do NOT create abstractions for code that "might" be reused. If in doubt, skip it.

### `file-size` — File Size
Files over 1,900 lines must be split into smaller, focused modules. These are pre-flagged by the caller before build runs — do not re-detect them.

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
Resolve or remove all TODO, FIXME, HACK, and SKIP markers. In test files, never use `t.Skip()`, `skip()`, `xit()`, `xtest`, `pytest.mark.skip`, or any equivalent skip mechanism.

### `test-quality` — Test Quality
- No mocks for internal code, SQL queries, or internal APIs
- Mocks are ONLY acceptable for external/3rd-party API calls (HTTP clients, payment providers, etc.)
- Follow the existing test patterns already established in this repo — read the test files first
- Only flag when major functionality has no test coverage at all — do not require tests for every change, and do not chase edge cases or failure paths

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

Interactively review results with the user. Stay in conversation until they are satisfied.

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
   - Add notes to a failed item before retrying
   - Ask questions about the codebase or review specific files
4. Remain interactive until the user explicitly says they are done

### `status`

Show current state without making any changes.

1. Resolve repo root and DB path
2. Print meta values
3. Print todo counts by status
4. List all non-complete, non-skipped todos: id, status, rule, file_path, description, notes
