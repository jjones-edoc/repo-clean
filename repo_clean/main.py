import argparse
import subprocess
import sys
from pathlib import Path

from .db import init_db, insert_todo, count_by_status, finalize_clean, print_status
from .skill import sync_skill


def get_git_root() -> Path:
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        print("Error: Current directory is not a git repository.", file=sys.stderr)
        sys.exit(1)
    return Path(result.stdout.strip())


def setup_claude_dir(repo_root: Path) -> Path:
    claude_dir = repo_root / ".claude"
    claude_dir.mkdir(exist_ok=True)

    gitignore = repo_root / ".gitignore"
    if gitignore.exists():
        content = gitignore.read_text(encoding="utf-8")
        if ".claude/" not in content and ".claude" not in content:
            with open(gitignore, "a", encoding="utf-8") as f:
                f.write("\n.claude/\n")
    else:
        gitignore.write_text(".claude/\n", encoding="utf-8")

    return claude_dir


def run_claude_headless(prompt: str) -> int:
    process = subprocess.Popen(
        ["claude", "--print", "--dangerously-skip-permissions", prompt],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        encoding="utf-8",
        errors="replace",
    )
    for line in process.stdout:
        print(line, end="", flush=True)
    process.wait()
    return process.returncode


def run_claude_interactive(prompt: str) -> int:
    result = subprocess.run(["claude", "--dangerously-skip-permissions", prompt])
    return result.returncode


FILE_SIZE_LIMIT_LINES = 1900


def seed_large_files(repo_root: Path, db_path: Path) -> None:
    result = subprocess.run(
        ["git", "ls-files"],
        capture_output=True, text=True, cwd=repo_root
    )
    if result.returncode != 0:
        return

    found = 0
    for rel_path in result.stdout.splitlines():
        abs_path = repo_root / rel_path
        try:
            line_count = sum(1 for _ in abs_path.open(encoding="utf-8", errors="ignore"))
        except OSError:
            continue
        if line_count > FILE_SIZE_LIMIT_LINES:
            insert_todo(
                db_path,
                description=f"File is {line_count} lines — split into smaller, focused modules",
                file_path=rel_path,
                rule="file-size",
                sort_order=0,
            )
            found += 1

    if found:
        print(f"==> {found} large file(s) added to todo list.")


def run_clean_loop(db_path: Path) -> None:
    initial = count_by_status(db_path, "pending") + count_by_status(db_path, "in_progress")
    cap = initial * 2
    iterations = 0
    while iterations < cap:
        remaining = count_by_status(db_path, "pending") + count_by_status(db_path, "in_progress")
        if remaining == 0:
            return
        print(f"\n==> {remaining} item(s) remaining. Running clean... ({iterations + 1}/{cap})\n")
        run_claude_headless("use the repo-clean skill with the clean parameter")
        iterations += 1
    print(f"\n!! Iteration cap ({cap}) reached with items still pending. Run `repo-clean` again or review the todo list.")


def run_full(repo_root: Path, db_path: Path) -> None:
    if count_by_status(db_path, "pending") == 0 and count_by_status(db_path, "in_progress") == 0:
        print("\n==> No pending items. Running build phase...\n")
        seed_large_files(repo_root, db_path)
        run_claude_headless("use the repo-clean skill with the build parameter")

        if count_by_status(db_path, "pending") == 0:
            print("\n✓ No issues found. Repository is already clean!")
            finalize_clean(db_path)
            return

    print("\n==> Build complete. Starting interactive review...\n")
    print("    Exit the review session to begin cleaning.\n")
    run_claude_interactive("use the repo-clean skill with the summarize parameter")

    run_clean_loop(db_path)

    failed = count_by_status(db_path, "failed")
    if failed:
        print(f"\n!! {failed} item(s) failed. Review them in the summary before finalizing.")

    print("\n==> All pending items processed. Starting interactive summary...\n")
    run_claude_interactive("use the repo-clean skill with the summarize parameter")

    answer = input("\nMark repository as clean and clear todo list? (y/n): ").strip().lower()
    if answer == "y":
        finalize_clean(db_path)
    else:
        print("Run repo-clean again to continue cleaning.")


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="repo-clean",
        description="AI-powered repository cleanup using Claude Code",
    )
    parser.add_argument(
        "command",
        nargs="?",
        choices=["build", "clean", "status"],
        help="build: analyze repo and create todo list | clean: run clean loop | status: show current state",
    )
    args = parser.parse_args()

    sync_skill()

    if args.command == "status":
        repo_root = get_git_root()
        db_path = repo_root / ".claude" / "repo_clean.db"
        print_status(db_path)
        return

    repo_root = get_git_root()
    claude_dir = setup_claude_dir(repo_root)
    db_path = claude_dir / "repo_clean.db"
    init_db(db_path)

    if args.command == "build":
        seed_large_files(repo_root, db_path)
        run_claude_headless("use the repo-clean skill with the build parameter")
    elif args.command == "clean":
        run_clean_loop(db_path)
    else:
        run_full(repo_root, db_path)
