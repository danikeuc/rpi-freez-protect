import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("light_package", ROOT / "deployment/lighting/install/build_package.py")
m = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(m)


def test_lock_exact_hashes_and_no_indexes():
    lock = m.requirements_lock({"gpiod": ("2.3.0", "a" * 64),
                                "rpi-freeze-protect-light": ("1.0.0", "b" * 64)})
    assert lock.splitlines() == ["gpiod==2.3.0 --hash=sha256:" + "a" * 64,
                                "rpi-freeze-protect-light==1.0.0 --hash=sha256:" + "b" * 64]


@pytest.mark.parametrize("bad", ["https://secret", "name;echo", "../name", "x\ny"])
def test_lock_rejects_injection(bad):
    with pytest.raises(ValueError):
        m.requirements_lock({bad: ("1", "a" * 64)})


def test_venv_and_device_separation():
    executor = (ROOT / "deployment/lighting/install/light-gpio.service").read_text()
    controller = (ROOT / "deployment/lighting/install/light-controller.service").read_text()
    for text in (executor, controller):
        assert "/opt/rpi-freez-protect/.venv" not in text
        assert "freeze-protect.service" not in text
        assert "Restart=on-failure" in text
    assert "RuntimeDirectoryPreserve=no" in executor
    assert "DeviceAllow=/dev/gpiochip0 rw" in executor
    assert "SupplementaryGroups=gpio" in executor
    assert "SupplementaryGroups" not in controller
    assert "PrivateDevices=true" in controller


def test_camera_route_does_not_expose_display_or_settings():
    text = (ROOT / "deployment/lighting/install/light-camera.conf").read_text()
    assert "listen 192.168.114.192:8443 ssl;" in text
    assert "location = /api/v1/lights/events/unifi" in text
    assert "if ($request_method != POST) { return 405; }" in text
    assert "location / { return 404; }" in text
    assert "/actions" not in text and "/settings" not in text
    assert "listen 8081" not in text and "access_log off;" in text
    assert "proxy_pass http://127.0.0.1:8002;" in text


def test_executor_readiness_waits_for_delayed_socket(tmp_path):
    import socket
    import threading
    import time

    spec = importlib.util.spec_from_file_location(
        "light_ready", ROOT / "deployment/lighting/install/wait_executor.py")
    ready = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ready)
    path = tmp_path / 'executor.sock'
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as server:
        def start():
            time.sleep(0.08)
            server.bind(str(path))
            server.listen(1)
        worker = threading.Thread(target=start)
        worker.start()
        try:
            ready.wait_ready(path, timeout=1)
            connection, _ = server.accept()
            connection.close()
        finally:
            worker.join()
    with pytest.raises(TimeoutError):
        ready.wait_ready(tmp_path / 'missing.sock', timeout=0.02)
    unit = (ROOT / 'deployment/lighting/install/light-gpio.service').read_text()
    assert 'ExecStartPost=/opt/independent-light/venv/bin/python -I -B /opt/independent-light/wait_executor.py' in unit
