from pathlib import Path

ROOT = Path(__file__).parents[2]


def test_ci_checks_committed_range_instead_of_clean_worktree() -> None:
    workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")

    assert "fetch-depth: 0" in workflow
    assert 'git diff --check "$PR_BASE_SHA...$PR_HEAD_SHA"' in workflow
    assert 'git show --check --format= "$GITHUB_SHA"' in workflow
    assert "run: git diff --check\n" not in workflow
