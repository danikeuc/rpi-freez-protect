"""Build a pinned offline light-only installation bundle; no target access."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import tarfile
import zipfile
from email.parser import BytesParser
from pathlib import Path

VERSIONS = {
    "rpi-freeze-protect-light": "1.0.0", "fastapi": "0.142.2",
    "pydantic": "2.13.5", "uvicorn": "0.54.0", "gpiod": "2.3.0",
    "pydantic-core": "2.46.5", "annotated-doc": "0.0.5",
    "annotated-types": "0.8.0", "click": "8.5.0", "h11": "0.16.0",
    "opentelemetry-api": "1.45.0", "starlette": "1.7.0", "anyio": "4.15.1",
    "idna": "3.20", "typing-extensions": "4.16.0", "typing-inspection": "0.4.4",
}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def requirements_lock(packages):
    lines = []
    for name, (version, digest) in sorted(packages.items()):
        if not (re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", name)
                and re.fullmatch(r"[0-9]+(?:\.[0-9]+)*", version)
                and re.fullmatch(r"[0-9a-f]{64}", digest)):
            raise ValueError("invalid pinned requirement")
        lines.append(f"{name}=={version} --hash=sha256:{digest}\n")
    return "".join(lines)


def wheel_identity(path):
    with zipfile.ZipFile(path) as archive:
        metadata = [n for n in archive.namelist() if n.endswith('.dist-info/METADATA')]
        if len(metadata) != 1:
            raise ValueError("wheel metadata")
        message = BytesParser().parsebytes(archive.read(metadata[0]))
        name = re.sub(r"[-_.]+", "-", message["Name"]).lower()
        return name, message["Version"]


def verify_source(wheel, repo):
    expected = {"freeze_protect/__init__.py": repo / "src/freeze_protect/__init__.py"}
    expected.update({"freeze_protect/lighting/" + p.name: p
                     for p in (repo / "src/freeze_protect/lighting").glob("*.py")})
    with zipfile.ZipFile(wheel) as archive:
        code = {n for n in archive.namelist() if not n.split('/')[0].endswith('.dist-info')}
        if code != set(expected) or any(archive.read(n) != p.read_bytes()
                                         for n, p in expected.items()):
            raise ValueError("light wheel/source mismatch")


def build(repo, wheels, public_key, output):
    if output.exists():
        raise ValueError("output must be new")
    selected = {}
    for path in sorted(wheels.glob("*.whl")):
        name, version = wheel_identity(path)
        if name not in VERSIONS or VERSIONS[name] != version:
            continue
        if name in selected:
            raise ValueError("duplicate target wheel")
        if name in ("gpiod", "pydantic-core"):
            if "-cp313-cp313-" not in path.name or "aarch64" not in path.name:
                raise ValueError("target ABI mismatch")
        elif not path.name.endswith("-none-any.whl"):
            raise ValueError("unexpected platform dependency")
        selected[name] = path
    if set(selected) != set(VERSIONS):
        raise ValueError("incomplete wheelhouse")
    verify_source(selected["rpi-freeze-protect-light"], repo)
    output.mkdir(parents=True)
    package = output / "package"
    package.mkdir()
    (package / "wheelhouse").mkdir()
    for path in selected.values():
        shutil.copyfile(path, package / "wheelhouse" / path.name)
    (package / "runtime-install.lock").write_text(requirements_lock({
        name: (VERSIONS[name], sha(path)) for name, path in selected.items()}))
    assets = repo / "deployment/lighting/install"
    for name in ("install_light.py", "light-gpio.service", "light-controller.service",
                 "light-camera.conf", "wait_executor.py", "README"):
        shutil.copyfile(assets / name, package / name)
    shutil.copyfile(repo / "deployment/paired-gpio-migration/operator_checks.py",
                    package / "operator_checks.py")
    shutil.copyfile(public_key, package / "recipient-public.pem")
    files = {p.relative_to(package).as_posix(): sha(p)
             for p in sorted(package.rglob('*')) if p.is_file()}
    (package / "manifest.json").write_text(json.dumps(files, indent=2, sort_keys=True) + "\n")
    sums = {**files, "manifest.json": sha(package / "manifest.json")}
    (package / "SHA256SUMS").write_text("".join(f"{h}  {n}\n" for n, h in sorted(sums.items())))
    archive = output / "light-runtime-20261015.tar.gz"
    with tarfile.open(archive, 'w:gz') as tar:
        for path in sorted(package.rglob('*')):
            if path.is_file():
                info = tar.gettarinfo(str(path), arcname=path.relative_to(package).as_posix())
                info.uid = info.gid = 0
                info.uname = info.gname = ''
                info.mode = 0o600
                with path.open('rb') as stream:
                    tar.addfile(info, stream)
    return {"archive": str(archive), "sha256": sha(archive),
            "manifest_sha256": sums["manifest.json"], "wheel_count": len(selected)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--wheelhouse', required=True, type=Path)
    parser.add_argument('--recipient-public-key', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[3]
    print(json.dumps(build(repo, args.wheelhouse, args.recipient_public_key, args.output)))


if __name__ == '__main__':
    main()
