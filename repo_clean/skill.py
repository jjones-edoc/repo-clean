import hashlib
from importlib.resources import files
from pathlib import Path


SKILL_DIR = Path.home() / ".claude" / "skills" / "repo-clean"
SKILL_FILE = SKILL_DIR / "SKILL.md"


def _bundled_content() -> str:
    return files("repo_clean").joinpath("data/SKILL.md").read_text(encoding="utf-8")


def sync_skill() -> None:
    content = _bundled_content()
    new_hash = hashlib.sha256(content.encode()).hexdigest()

    if SKILL_FILE.exists():
        existing_hash = hashlib.sha256(SKILL_FILE.read_bytes()).hexdigest()
        if existing_hash == new_hash:
            return

    SKILL_DIR.mkdir(parents=True, exist_ok=True)
    SKILL_FILE.write_text(content, encoding="utf-8")
    print(f"✓ repo-clean skill synced to {SKILL_FILE}")
