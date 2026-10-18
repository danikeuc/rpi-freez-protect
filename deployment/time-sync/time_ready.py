"""Bounded boot gate. Reads time status only; never changes clock or outputs."""

import subprocess
import time


def wait_ready(probe, now, sleep, timeout=50):
    deadline = now() + timeout
    consecutive = 0
    while now() < deadline:
        consecutive = consecutive + 1 if probe() else 0
        if consecutive >= 3:
            return True
        sleep(min(1, max(0, deadline - now())))
    return False


def synchronized():
    try:
        for args, expected in (
            (
                ["/usr/bin/systemctl", "is-active", "systemd-timesyncd.service"],
                b"active",
            ),
            (
                [
                    "/usr/bin/timedatectl",
                    "show",
                    "--property=NTPSynchronized",
                    "--value",
                ],
                b"yes",
            ),
        ):
            result = subprocess.run(
                args,
                stdin=subprocess.DEVNULL,
                capture_output=True,
                timeout=2,
                check=False,
                env={"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LANG": "C"},
            )
            if result.returncode or result.stdout.strip() != expected:
                return False
        return True
    except (OSError, subprocess.TimeoutExpired):
        return False


if __name__ == "__main__":
    ok = wait_ready(synchronized, time.monotonic, time.sleep)
    print("TIME_READY" if ok else "TIME_NOT_READY")
    raise SystemExit(0 if ok else 1)
