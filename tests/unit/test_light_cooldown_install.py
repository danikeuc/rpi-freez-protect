import importlib.util
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location(
    "cooldown_install",
    Path(__file__).resolve().parents[2]
    / "deployment/lighting/cooldown/install_cooldown.py",
)
assert SPEC and SPEC.loader
installer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(installer)


def test_baseline_drift_stops_before_any_service_command(tmp_path, monkeypatch):
    installed = tmp_path / "installed"
    installed.mkdir()
    for name in ("models.py", "controller.py"):
        (installed / name).write_text("old")
        (tmp_path / name).write_text("pass")
    monkeypatch.setattr(installer, "BASE", installed)
    monkeypatch.setattr(installer, "secure", lambda p: None)
    manifest = {
        n: {"before": "wrong", "after": installer.sha(tmp_path / n)}
        for n in ("models.py", "controller.py")
    }
    with pytest.raises(RuntimeError, match="BASELINE_CHANGED"):
        installer.validate_sources(tmp_path, manifest)


def test_tampered_package_is_rejected(tmp_path, monkeypatch):
    installed = tmp_path / "installed"
    installed.mkdir()
    for name in ("models.py", "controller.py"):
        (installed / name).write_text("old")
        (tmp_path / name).write_text("pass")
    monkeypatch.setattr(installer, "BASE", installed)
    monkeypatch.setattr(installer, "secure", lambda p: None)
    manifest = {
        n: {"before": installer.sha(installed / n), "after": "wrong"}
        for n in ("models.py", "controller.py")
    }
    with pytest.raises(RuntimeError, match="PACKAGE_CHANGED"):
        installer.validate_sources(tmp_path, manifest)


def test_private_receipt_never_overwrites_prior_attempt(tmp_path):
    target = tmp_path / "receipt"
    installer.private(target, b"original")
    with pytest.raises(FileExistsError):
        installer.private(target, b"replacement")
    assert target.read_bytes() == b"original"
