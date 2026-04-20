import os
import subprocess
import sys


def _run_cli(cwd, *args):
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    return subprocess.run(
        [sys.executable, "-m", "repo_clean.main", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
    )


def test_status_no_db(git_repo):
    result = _run_cli(git_repo, "status")
    assert result.returncode == 0
    assert "No repo_clean.db found" in result.stdout


def test_status_outside_git_repo(tmp_path):
    result = _run_cli(tmp_path, "status")
    assert result.returncode != 0
    assert "not a git repository" in result.stderr
