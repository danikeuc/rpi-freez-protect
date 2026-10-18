"""Build a pinned root-console handoff; no network or device action."""
import hashlib
import io
import json
import sys
import tarfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
PACKAGE_SHA = 'f4c87e6439650f80c02b2d1b17c76661c5e3d74bbf7c672eab28edadc9883513'


def main():
    if len(sys.argv) != 3:
        raise SystemExit('usage: build_package.py migration-v2.tar.gz output.tar.gz')
    migration = Path(sys.argv[1]).read_bytes()
    if hashlib.sha256(migration).hexdigest() != PACKAGE_SHA:
        raise SystemExit('migration hash mismatch')
    files = {name: (HERE / name).read_bytes() for name in
             ('maintenance.py', 'install_access.py', 'README.md')}
    files['migration.tar.gz'] = migration
    for name, source in (
        ('original-dispatch', 'freeze-protect-commission-ssh-dispatch'),
        ('original-helper', 'freeze-protect-commission'),
        ('original-sudoers', 'freeze-protect-commission.sudoers'),
    ):
        files[name] = (ROOT / 'deployment/workstation-codex' / source).read_bytes()
    files['manifest.json'] = (json.dumps({'files': {
        name: hashlib.sha256(data).hexdigest() for name, data in files.items()
    }}, sort_keys=True, indent=2) + '\n').encode()
    files['SHA256SUMS'] = ''.join(hashlib.sha256(data).hexdigest() + '  ' + name + '\n'
                                 for name, data in sorted(files.items())).encode()
    output = Path(sys.argv[2])
    with output.open('xb') as stream, tarfile.open(fileobj=stream, mode='w:gz') as archive:
        for name, data in sorted(files.items()):
            member = tarfile.TarInfo(name)
            member.mode = 0o600
            member.size = len(data)
            archive.addfile(member, io.BytesIO(data))
    print(hashlib.sha256(output.read_bytes()).hexdigest() + '  ' + str(output))


if __name__ == '__main__':
    main()
