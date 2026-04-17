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
Flag actual code duplication: 3+ lines that are identical or near-identical appearing in multiple places. Do NOT create preventative abstractions. Only fix real, existing duplication.

### `file-size` — File Size
Files larger than 50kb must be split into smaller, focused modules. The Python script pre-flags these, but also flag any discovered during analysis.

### `comments` — Comment Policy
Only these comment types are allowed:
- Justification comments: WHY a decision was made (not what the code does)
- Legal or license headers
- References to external algorithms, RFCs, or specifications (a link or citation)

Delete ALL other comments. Code must be self-documenting through naming. Never explain what code does in a comment.

### `dead-code` — Commented-Out Code
Delete all commented-out code blocks entirely. Do not leave disabled code in the codebase.

### `unused-files` — Unused Files
Delete files that are never imported, required, or referenced anywhere in the codebase.

### `todo-fixme` — TODO / FIXME / SKIP
Resolve or remove all TODO, FIXME, HACK, and SKIP markers. In test files, never use `t.Skip()`, `skip()`, `xit()`, `xtest`, `pytest.mark.skip`, or any equivalent skip mechanism.

### `test-quality` — Test Quality
- No mocks for internal code, SQL queries, or internal APIs
- Mocks are ONLY acceptable for external/3rd-party API calls (HTTP clients, payment providers, etc.)
- Follow the existing test patterns already established in this repo — read the test files first
- Any changed or added files must have corresponding test coverage

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
2. Query `meta` for `last_clean_commit`:
   - Found → `git diff <hash>..HEAD --name-only` → analyze only changed files
   - Not found → scan the entire codebase
3. Apply all Clean Rules to each relevant file
4. Auto-flag any files over 50kb as `file-size` violations (use `find` or check file sizes)
5. For each violation found, INSERT a todo:
   ```python
   now = __import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat()
   c.execute("""
       INSERT INTO todos (sort_order, description, file_path, rule, status, created_at, updated_at)
       VALUES (?, ?, ?, ?, 'pending', ?, ?)
   """, (sort_order, description, file_path, rule, now, now))
   ```
6. Order todos: `file-size` first, then `dead-code`, then `unused-files`, then `todo-fixme`, then `comments`, then `dry`, then `test-quality`, then `claude-md`
7. Print a summary of what was found grouped by rule

### `clean`

Work ONE pending todo item, then exit. The calling script handles the loop.

**Steps:**

1. Resolve repo root and DB path
2. Fetch next item:
   ```sql
   SELECT * FROM todos WHERE status='pending' ORDER BY sort_order LIMIT 1
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
