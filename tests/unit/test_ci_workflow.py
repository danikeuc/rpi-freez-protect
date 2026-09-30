from pathlib import Path

ROOT = Path(__file__).parents[2]


def test_ci_checks_final_event_delta_instead_of_intermediate_commits() -> None:
    workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")

    assert "fetch-depth: 0" in workflow
    assert 'git diff --check "$PR_BASE_SHA...$PR_HEAD_SHA"' in workflow
    assert 'git diff --check "$PUSH_BEFORE_SHA" "$GITHUB_SHA"' in workflow
    assert 'EMPTY_TREE_SHA="$(git hash-object -t tree /dev/null)"' in workflow
    assert 'git diff --check "$EMPTY_TREE_SHA" "$GITHUB_SHA"' in workflow
    assert 'git log --check --format=' not in workflow
    assert 'PUSH_BEFORE_SHA: ${{ github.event.before }}' in workflow
    assert "run: git diff --check\n" not in workflow
