import importlib.util
import json
from pathlib import Path

import pytest

PATH = (
    Path(__file__).resolve().parents[2]
    / "deployment/lighting/diagnostics/continue_pre_stop.py"
)
SPEC = importlib.util.spec_from_file_location("continuation", PATH)
assert SPEC and SPEC.loader
c = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(c)


@pytest.fixture
def rig(tmp_path, monkeypatch):
    prior, package = tmp_path / "prior", tmp_path / "package"
    prior.mkdir()
    package.mkdir()
    marker = tmp_path / "marker"
    marker.write_text(str(prior))
    monkeypatch.setattr(c, "PRIOR", prior)
    monkeypatch.setattr(c.installer, "MARKER", marker)
    monkeypatch.setattr(c.support, "secure", lambda p: None)
    for name in ("ENV", "SHOWER_ENV"):
        path = tmp_path / name
        path.write_text("secret")
        monkeypatch.setattr(c.support, name, path)
    manifest = {"node_red.py": {"before": "hash", "after": "new"}}
    (package / "baseline.json").write_text(json.dumps(manifest))
    (prior / "node_red.py").write_text("old")
    monkeypatch.setattr(c.support, "sha", lambda p: "hash")
    (prior / "before.json").write_text(
        json.dumps(
            {
                "source": manifest,
                "environment_hashes": {
                    str(c.support.ENV): "hash",
                    str(c.support.SHOWER_ENV): "hash",
                },
                "settings": {"manual_seconds": 1800},
            }
        )
    )
    monkeypatch.setattr(c.installer, "validate_sources", lambda *a: None)
    monkeypatch.setattr(c.support, "environment", lambda p: {})
    monkeypatch.setattr(
        c.support,
        "API",
        lambda *a: (
            lambda kind, endpoint: (
                {"manual_seconds": 1800} if endpoint == "settings" else {}
            )
        ),
    )
    monkeypatch.setattr(c.support, "active_units", lambda: None)
    monkeypatch.setattr(c.support, "drain_check", lambda: None)
    monkeypatch.setattr(c.installer, "durable_off", lambda *a, **kw: None)
    monkeypatch.setattr(c.installer, "preflight", lambda *a, **kw: None)
    installs = []
    monkeypatch.setattr(c.installer, "install_locked", lambda p: installs.append(p))
    return package, prior, marker, installs


@pytest.mark.parametrize(
    "name",
    [
        "stop-started.json",
        "install-started.json",
        "success.json",
        "reviewed-started-marker",
        "continuation-reviewed.json",
    ],
)
def test_prior_mutation_or_previous_continuation_refuses(rig, name):
    package, prior, marker, installs = rig
    (prior / name).write_text("{}")
    with pytest.raises(RuntimeError, match="ATTEMPT_NOT_PRE_STOP"):
        c.continue_locked(package)
    assert marker.exists() and not installs


def test_other_attempt_refuses(rig):
    package, _prior, marker, installs = rig
    marker.write_text("/root/other")
    with pytest.raises(RuntimeError, match="OTHER_ATTEMPT"):
        c.continue_locked(package)
    assert marker.exists() and not installs


def test_short_manual_hold_keeps_original_marker(rig, monkeypatch):
    package, _prior, marker, installs = rig

    def fail(*a, **kw):
        assert kw["minimum"] == 600
        raise RuntimeError("MANUAL_OFF_TIME_REQUIRED")

    monkeypatch.setattr(c.installer, "preflight", fail)
    with pytest.raises(RuntimeError, match="MANUAL_OFF_TIME_REQUIRED"):
        c.continue_locked(package)
    assert marker.exists() and not installs


def test_review_preserves_marker_and_all_evidence_before_one_install(rig):
    package, prior, marker, installs = rig
    c.continue_locked(package)
    assert not marker.exists()
    assert (prior / "reviewed-started-marker").read_text() == str(prior)
    assert (prior / "before.json").exists()
    assert (prior / "continuation-reviewed.json").exists()
    assert installs == [package]
