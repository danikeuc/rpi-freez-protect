# Project reconciliation implementation plan

**Goal:** Reconcile current evidence and organize `rpi-freez-protect` so the active architecture, historical material, quality gates and remaining physical gaps are unambiguous.

**Base:** `origin/main` at `b861c0a67dd484264dc810aa5b7525c18731736c`  
**Branch:** `codex/project-evidence-reconciliation`  
**Safety:** repository-only work; no Pi mutation, GPIO command, service restart, 24 V action or firmware flash.

## Task 1: Repair the portable repository test baseline

**Files:**
- Modify `tests/integration/test_workstation_commissioning_assets.py`
- Modify `pyproject.toml` only if test configuration needs an explicit marker

**Steps:**
1. Preserve the four existing failing rollback scenarios as the red baseline.
2. Add a test helper that adapts extracted shell snippets to the current unprivileged test user only.
3. Keep production script assertions for UID 0 and root-owned `install` operations.
4. Run the focused test file and then the complete test suite.

## Task 2: Add repeatable project quality gates

**Files:**
- Create `.github/workflows/ci.yml`
- Create `tests/unit/test_documentation_links.py`
- Create `docs/VERIFICATION.md`
- Update `README.md`

**Steps:**
1. Add internal Markdown-link and anchor checks.
2. Add CI for Python 3.12 tests, Ruff, mypy, package build, JSON/JavaScript/shell syntax and whitespace.
3. Document exact local commands and what each result can and cannot prove.
4. Run each available gate locally; record unavailable environment-specific gates explicitly.

## Task 3: Reconcile active architecture and runbooks

**Files:**
- Create `docs/ARCHITECTURE.md`
- Create `deployment/DISPLAY_COMMISSIONING.md`
- Update `README.md`
- Update `deployment/COMMISSIONING.md`
- Update `deployment/WORKSTATION_CODEX_COMMISSIONING.md`
- Update `deployment/CROWPANEL_COMMISSIONING.md`
- Update `firmware/crowpanel/README.md`

**Steps:**
1. Scope automatic-mode sensor/weather statements so they do not contradict `manual_timed`.
2. Document the Waveshare path as active and CrowPanel as historical.
3. Correct expected startup/status values for `manual_timed`.
4. Keep exact safety gates and separate repository, deployed GPIO and physical observations.
5. Run Markdown links, targeted asset tests and whitespace checks.

## Task 4: Replace stale project evidence

**Files:**
- Rewrite `docs/PROJECT_STATE.md`

**Steps:**
1. Record current merged commit/tree equivalence and distinguish the Pi checkout from installed artifacts.
2. Record the observed services, mode, gateway behavior and disconnected DRAIN/SUPPLY/DRAIN GPIO sequence.
3. Record the Roon interaction observations and distinguish the hardware-tested development image from the unflashed release artifact.
4. Preserve unknown physical valve, PT100 and fault-injection outcomes.
5. Add a reconciliation table with claim, source, limit, category, minimal fix and owner.

## Task 5: Verify and review

1. Run the full Python suite, Ruff, mypy, package build, Node-RED structural check, JavaScript syntax, shell syntax, Markdown links and `git diff --check`.
2. Inspect the final diff for active/historical ambiguity and unsafe claims.
3. Request an independent code/documentation review against this plan.
4. Fix critical and important findings and rerun affected gates.
5. Present the verified branch integration choices without deploying it.
