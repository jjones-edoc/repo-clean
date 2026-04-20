from repo_clean import skill


def test_sync_skill_writes_when_missing(tmp_path, monkeypatch, capsys):
    target_dir = tmp_path / "skills" / "repo-clean"
    target = target_dir / "SKILL.md"
    monkeypatch.setattr(skill, "SKILL_DIR", target_dir)
    monkeypatch.setattr(skill, "SKILL_FILE", target)

    skill.sync_skill()
    assert target.exists()
    assert "repo-clean Skill" in target.read_text(encoding="utf-8")
    assert "synced" in capsys.readouterr().out


def test_sync_skill_noop_when_hash_matches(tmp_path, monkeypatch, capsys):
    target_dir = tmp_path / "skills" / "repo-clean"
    target = target_dir / "SKILL.md"
    target_dir.mkdir(parents=True)
    target.write_bytes(skill._bundled_content().encode("utf-8"))
    mtime_before = target.stat().st_mtime_ns

    monkeypatch.setattr(skill, "SKILL_DIR", target_dir)
    monkeypatch.setattr(skill, "SKILL_FILE", target)

    skill.sync_skill()
    assert target.stat().st_mtime_ns == mtime_before
    assert capsys.readouterr().out == ""


def test_sync_skill_overwrites_when_content_differs(tmp_path, monkeypatch):
    target_dir = tmp_path / "skills" / "repo-clean"
    target = target_dir / "SKILL.md"
    target_dir.mkdir(parents=True)
    target.write_text("stale content", encoding="utf-8")

    monkeypatch.setattr(skill, "SKILL_DIR", target_dir)
    monkeypatch.setattr(skill, "SKILL_FILE", target)

    skill.sync_skill()
    assert target.read_bytes() == skill._bundled_content().encode("utf-8")
