# Read-only paired GPIO inventory

Run only in the operator's trusted Raspberry Pi / DietPi console. This is not
a permitted remote helper command; do not widen its allowlist. The block reads
fixed model/device-tree/sysfs/device metadata and installed package metadata.
It does not open GPIO for requests, map registers, control services, install
packages or read secrets. Missing gpiod metadata is reported, not repaired.
Capture the output for mapping review before preparing the exact installer.
Python syntax and a non-Pi rejection check passed on the workstation; no Pi
execution or successful mapping validation is claimed.

```sh
sudo python3 -I -B - <<'PY'
from pathlib import Path
import json, os, subprocess

def emit(**data):
    print(json.dumps(data))

def read(path):
    try:
        return Path(path).read_bytes()[:4096]
    except OSError:
        return b""

def node(path):
    if not path.exists():
        return
    path = path.resolve()
    names = read(path / "gpio-line-names").decode(errors="replace").split("\0")
    emit(node=str(path), compatible=read(path / "compatible").decode(errors="replace").split("\0"),
         reg=read(path / "reg").hex(), address_cells=read(path.parent / "#address-cells").hex(),
         size_cells=read(path.parent / "#size-cells").hex(),
         lines={str(i): names[i] if i < len(names) else None for i in (20,21,26)})

model = read("/proc/device-tree/model").decode(errors="replace").strip("\0\n")
if not model.startswith("Raspberry Pi"):
    raise SystemExit("WRONG_HOST: run on the Raspberry Pi / DietPi")
emit(model=model, kernel=os.uname().release, page_size=os.sysconf("SC_PAGE_SIZE"),
     compatible=read("/proc/device-tree/compatible").decode(errors="replace").split("\0"))
for dev in sorted(Path("/dev").glob("gpiochip*")) + [Path("/dev/gpiomem")]:
    if not dev.exists():
        emit(device=str(dev), missing=True)
        continue
    st = dev.stat()
    char = Path(f"/sys/dev/char/{os.major(st.st_rdev)}:{os.minor(st.st_rdev)}").resolve()
    emit(device=str(dev), uid=st.st_uid, gid=st.st_gid, mode=oct(st.st_mode & 0o777),
         sysfs=str(char), subsystem=str((char / "subsystem").resolve()),
         parent_driver=str((char.parent / "driver").resolve()))
    node(char / "of_node")
    node(char.parent / "of_node")
for bound in sorted(Path("/sys/bus/platform/drivers/rpi-gpiomem").glob("*")):
    node(bound / "of_node")
for py in ("/usr/bin/python3", "/opt/rpi-freez-protect/.venv/bin/python3"):
    probe = 'import sys,importlib.metadata as m; print(sys.version.split()[0]); print(m.version("gpiod"))'
    try:
        result = subprocess.run([py,"-I","-B","-c",probe], capture_output=True, text=True, timeout=5)
        emit(interpreter=py, versions=result.stdout.splitlines(), gpiod_metadata_ok=result.returncode == 0)
    except (OSError, subprocess.TimeoutExpired) as exc:
        emit(interpreter=py, error=type(exc).__name__)
emit(result="READ_ONLY_INVENTORY_COMPLETE")
PY
```
