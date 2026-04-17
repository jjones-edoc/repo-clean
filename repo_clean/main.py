import argparse
import subprocess
import sys
from pathlib import Path

from .db import init_db, count_by_status, finalize_clean, print_status
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
    result = subprocess.run(["claude", prompt])
    return result.returncode


def run_full(db_path: Path) -> None:
    if count_by_status(db_path, "pending") == 0:
        print("\n==> No pending items. Running build phase...\n")
        run_claude_headless("use the repo-clean skill with the build parameter")

        if count_by_status(db_path, "pending") == 0:
            print("\n✓ No issues found. Repository is already clean!")
            finalize_clean(db_path)
            return

    while count_by_status(db_path, "pending") > 0:
        remaining = count_by_status(db_path, "pending")
        print(f"\n==> {remaining} item(s) remaining. Running clean...\n")
        run_claude_headless("use the repo-clean skill with the clean parameter")

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
        run_claude_headless("use the repo-clean skill with the build parameter")
    elif args.command == "clean":
        while count_by_status(db_path, "pending") > 0:
            remaining = count_by_status(db_path, "pending")
            print(f"\n==> {remaining} item(s) remaining. Running clean...\n")
            run_claude_headless("use the repo-clean skill with the clean parameter")
    else:
        run_full(db_path)
