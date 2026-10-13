"""Exercise the real daemon boundary with simulated kernel and MMIO only."""
import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

DAEMON = Path(__file__).parents[2] / "deployment/node-red/paired_gpio_daemon.py"


def load():
    spec = importlib.util.spec_from_file_location("paired_ownership", DAEMON)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def hardware(monkeypatch):
    daemon = load()
    trace = []
    state = SimpleNamespace(owned=False, level=0, fsel=0, fail=None, light=False)
    line = SimpleNamespace(
        Direction=SimpleNamespace(AS_IS="as-is", OUTPUT="output"),
        Bias=SimpleNamespace(AS_IS="bias-as-is"),
        Edge=SimpleNamespace(NONE="none"),
        Value=SimpleNamespace(ACTIVE="high"),
    )

    def kernel_light(output):
        # A kernel-serialized request/release only changes its own FSEL field.
        state.light = output
        state.fsel = (state.fsel & ~(7 << 3)) | (int(output) << 3)

    class Request:
        def reconfigure_lines(self, config):
            assert state.owned
            assert set(config) == {(26, 20)}
            settings = config[(26, 20)]
            assert settings.direction == "output"
            assert settings.active_low is False
            assert settings.output_value == "high"
            assert state.level & ((1 << 26) | (1 << 20)) == 68157440
            trace.append("configure")
            for pin in (26, 20):
                kernel_light(not state.light)
                state.fsel = (state.fsel & ~(7 << ((pin % 10) * 3))) | (
                    1 << ((pin % 10) * 3)
                )
                if state.fail == "configure":
                    raise OSError("configure failed")

        def release(self):
            assert state.owned
            trace.append("release")
            state.owned = False
            kernel_light(False)

    class Chip:
        def __init__(self, path):
            trace.append("chip")
            assert path == "/dev/gpiochip0"
            self.fd = 99

        def get_info(self):
            return SimpleNamespace(name="gpiochip0", label="pinctrl-bcm2835",
                                   num_lines=54)

        def get_line_info(self, pin):
            return SimpleNamespace(offset=pin, name=f"GPIO{pin}",
                                   used=state.fail == "busy",
                                   active_low=False)

        def request_lines(self, *, consumer, config):
            trace.append("request")
            assert consumer == "freeze-protect-pair"
            assert set(config) == {(26, 20)}
            settings = config[(26, 20)]
            assert settings.direction == "as-is"
            assert settings.bias == "bias-as-is"
            assert settings.edge_detection == "none"
            assert settings.active_low is False
            if state.fail == "request":
                raise OSError("request failed")
            state.owned = True
            return Request()

        def close(self):
            trace.append("chip-close")

    class Registers:
        def __init__(self, *args, **kwargs):
            assert state.owned, "MMIO opened before exclusive kernel ownership"
            trace.append("map")
            if state.fail == "map":
                raise OSError("map failed")

        def read32(self, offset):
            assert state.owned
            assert offset == 0x34, "userspace read configuration register"
            trace.append(("read", offset))
            if state.fail == "read":
                raise OSError("read failed")
            return state.level

        def write32(self, offset, value):
            assert state.owned
            assert offset in (0x1c, 0x28), "userspace wrote configuration register"
            assert value == 68157440
            trace.append(("write", offset, value))
            kernel_light(not state.light)
            state.level = state.level | value if offset == 0x1c else state.level & ~value
            if state.fail == "write":
                raise OSError("write failed")

        def close(self):
            assert state.owned
            trace.append("unmap")
            if state.fail == "unmap":
                raise OSError("unmap failed")

    gpiod = SimpleNamespace(Chip=Chip, LineSettings=lambda **kw: SimpleNamespace(**kw),
                            __version__="2.3.0")
    monkeypatch.setitem(sys.modules, "gpiod", gpiod)
    monkeypatch.setitem(sys.modules, "gpiod.line", line)
    monkeypatch.setattr(daemon, "GpiomemRegisters", Registers)
    monkeypatch.setattr(daemon, "validate_platform",
                        lambda *args: trace.append("validate") or 123, raising=False)
    monkeypatch.setenv("PAIRED_GPIO_PROFILE", "bcm2835-gpiomem-v1")
    monkeypatch.setenv("PAIRED_GPIO_CHIP", "/dev/gpiochip0")
    monkeypatch.setattr(sys, "argv", ["paired_gpio_daemon"])
    return daemon, trace, state, gpiod


def test_main_reserves_pair_before_mapping_and_kernel_configures_without_fsel_race(
    hardware, monkeypatch,
):
    daemon, trace, state, _ = hardware

    def serve(_socket, gpio):
        for command in ("SUPPLY", "DRAIN", "SUPPLY"):
            before = len(trace)
            expected = 0 if command == "SUPPLY" else 1
            assert gpio.write_and_verify(command) == {"26": expected, "20": expected}
            assert trace[before:] == [
                ("write", 0x28 if command == "SUPPLY" else 0x1c, 68157440),
                ("read", 0x34),
            ]
            # Concurrent kernel line21 request/release leaves pair output fields intact.
            assert state.fsel & 0x1c0007 == 0x40001

    monkeypatch.setattr(daemon, "run_daemon", serve)
    assert daemon.main() == 0
    assert trace[:6] == ["chip", "validate", "request", "map",
                         ("write", 0x1c, 68157440), "configure"]
    assert trace[-3:] == ["unmap", "release", "chip-close"]
    assert not state.owned


@pytest.mark.parametrize("failure", ["request", "map", "configure", "read", "write"])
def test_partial_failure_preserves_cause_and_closes_in_ownership_order(
    hardware, monkeypatch, failure,
):
    daemon, trace, state, _ = hardware
    state.fail = failure
    monkeypatch.setattr(daemon, "run_daemon", lambda *_: pytest.fail("served after failure"))
    with pytest.raises(OSError, match=f"{failure} failed"):
        daemon.main()
    if failure == "request":
        assert "map" not in trace
        assert "release" not in trace
    else:
        assert trace[-2:] == ["release", "chip-close"]
        if failure != "map":
            assert trace[-3] == "unmap"
    assert not state.owned


def test_serve_error_survives_emergency_drain_failure(hardware, monkeypatch):
    daemon, trace, state, _ = hardware

    def fail(*_):
        state.fail = "write"
        raise RuntimeError("original service failure")

    monkeypatch.setattr(daemon, "run_daemon", fail)
    with pytest.raises(RuntimeError, match="original service failure"):
        daemon.main()
    assert trace[-3:] == ["unmap", "release", "chip-close"]


def test_failed_unmap_does_not_release_owned_lines(hardware, monkeypatch):
    daemon, trace, state, _ = hardware

    def fail(*_):
        state.fail = "unmap"

    monkeypatch.setattr(daemon, "run_daemon", fail)
    with pytest.raises(OSError, match="unmap failed"):
        daemon.main()
    assert state.owned
    assert "release" not in trace


@pytest.mark.parametrize("variable,value", [
    ("PAIRED_GPIO_PROFILE", ""), ("PAIRED_GPIO_PROFILE", "rp1"),
    ("PAIRED_GPIO_CHIP", ""), ("PAIRED_GPIO_CHIP", "/dev/mem"),
])
def test_missing_or_invalid_configuration_does_not_open_devices(
    hardware, monkeypatch, variable, value,
):
    daemon, trace, _, _ = hardware
    monkeypatch.setenv(variable, value)
    with pytest.raises(ValueError):
        daemon.main()
    assert trace == []


@pytest.mark.parametrize("failure", ["busy", "wrong-name", "wrong-chip", "old-api"])
def test_wrong_metadata_or_dependency_has_no_request_or_mmio(hardware, monkeypatch, failure):
    daemon, trace, state, gpiod = hardware
    state.fail = failure
    if failure == "wrong-name":
        monkeypatch.setattr(gpiod.Chip, "get_line_info",
                            lambda _, pin: SimpleNamespace(offset=pin, name="OTHER", used=False))
    if failure == "wrong-chip":
        monkeypatch.setattr(gpiod.Chip, "get_info",
                            lambda _: SimpleNamespace(name="gpiochip0", label="rp1", num_lines=54))
    if failure == "old-api":
        gpiod.__version__ = "1.6.0"
    with pytest.raises((ValueError, RuntimeError)):
        daemon.main()
    assert "request" not in trace
    assert "map" not in trace


def test_missing_gpiod_has_no_mmio(hardware, monkeypatch):
    daemon, trace, _, _ = hardware
    monkeypatch.setitem(sys.modules, "gpiod", None)
    with pytest.raises(ImportError):
        daemon.main()
    assert trace == []


def test_platform_rejection_happens_before_request(hardware, monkeypatch):
    daemon, trace, _, _ = hardware

    def reject(*_):
        raise ValueError("unsupported mapping")

    monkeypatch.setattr(daemon, "validate_platform", reject)
    with pytest.raises(ValueError, match="unsupported mapping"):
        daemon.main()
    assert "request" not in trace
    assert "map" not in trace


@pytest.fixture
def platform(tmp_path, monkeypatch):
    import os
    import stat
    import struct

    daemon = load()
    tree = tmp_path / "dt"
    tree.mkdir()
    (tree / "compatible").write_bytes(b"raspberrypi,4-model-b\0brcm,bcm2711\0")
    bus = tree / "soc"
    bus.mkdir()
    for name in ("#address-cells", "#size-cells"):
        (bus / name).write_bytes(struct.pack(">I", 1))
    chip_node = bus / "gpio@7e200000"
    memory_node = bus / "gpiomem"
    for node, compatible, size in (
        (chip_node, "brcm,bcm2711-gpio", 0xf4),
        (memory_node, "brcm,bcm2835-gpiomem", 0x1000),
    ):
        node.mkdir()
        (node / "compatible").write_bytes(compatible.encode() + b"\0")
        (node / "reg").write_bytes(struct.pack(">II", 0x7e200000, size))
    sys_char = tmp_path / "dev-char"
    chip_device = tmp_path / "gpio-platform"
    chip_device.mkdir()
    (chip_device / "of_node").symlink_to(chip_node)
    pin_driver = tmp_path / "pinctrl-bcm2835"
    pin_driver.mkdir()
    (chip_device / "driver").symlink_to(pin_driver)
    (sys_char / "254:0").mkdir(parents=True)
    (sys_char / "254:0" / "device").symlink_to(chip_device)
    memory_class = tmp_path / "gpiomem-class" / "gpiomem"
    memory_class.mkdir(parents=True)
    (memory_class / "dev").write_text("240:0\n")
    sys_char.joinpath("240:0").symlink_to(memory_class)
    # Actual legacy driver creates its character device with NULL parent.
    assert not (memory_class / "device").exists()
    memory_driver = tmp_path / "rpi-gpiomem"
    memory_driver.mkdir()
    bound = tmp_path / "memory-platform"
    bound.mkdir()
    (bound / "of_node").symlink_to(memory_node)
    (memory_driver / "fe200000.gpiomem").symlink_to(bound)
    monkeypatch.setattr(daemon, "DEVICE_TREE", tree)
    monkeypatch.setattr(daemon, "SYS_DEV_CHAR", sys_char)
    monkeypatch.setattr(daemon, "GPIOMEM_CLASS", memory_class, raising=False)
    monkeypatch.setattr(daemon, "GPIOMEM_DRIVER", memory_driver, raising=False)
    monkeypatch.setattr(daemon.os, "fstat",
                        lambda _: SimpleNamespace(st_mode=stat.S_IFCHR, st_rdev=os.makedev(254, 0)))
    real_stat = os.stat

    def device_stat(path, *args, **kwargs):
        if str(path) == "/dev/gpiomem":
            return SimpleNamespace(st_mode=stat.S_IFCHR, st_rdev=os.makedev(240, 0))
        return real_stat(path, *args, **kwargs)

    monkeypatch.setattr(daemon.os, "stat", device_stat)
    return daemon, tree, chip_node, memory_node, memory_driver, memory_class


def test_supported_mapping_validates_parentless_legacy_gpiomem(platform):
    import os
    daemon, *_ = platform
    assert daemon.validate_platform(99, "pinctrl-bcm2711") == os.makedev(240, 0)


@pytest.mark.parametrize("bad", [
    "rp1", "platform", "wrong-bank", "wrong-compatible", "wrong-driver",
    "ambiguous-driver", "wrong-character-device", "missing-metadata", "address-cells",
])
def test_platform_mapping_rejects_wrong_or_ambiguous_hardware(platform, bad):
    import struct
    daemon, tree, chip_node, memory_node, driver, device_class = platform
    if bad == "rp1":
        (tree / "compatible").write_bytes(b"raspberrypi,5-model-b\0brcm,bcm2712\0")
    elif bad == "platform":
        (tree / "compatible").write_bytes(b"unknown\0")
    elif bad == "wrong-bank":
        (memory_node / "reg").write_bytes(struct.pack(">II", 0x7e300000, 4096))
    elif bad == "wrong-compatible":
        (chip_node / "compatible").write_bytes(b"raspberrypi,rp1-gpio\0")
    elif bad == "wrong-driver":
        (driver / "fe200000.gpiomem").unlink()
    elif bad == "ambiguous-driver":
        (driver / "another").symlink_to((driver / "fe200000.gpiomem").resolve())
    elif bad == "wrong-character-device":
        (device_class / "dev").write_text("240:1\n")
    elif bad == "missing-metadata":
        (memory_node / "reg").unlink()
    elif bad == "address-cells":
        (memory_node.parent / "#address-cells").write_bytes(struct.pack(">I", 2))
    with pytest.raises((ValueError, OSError)):
        daemon.validate_platform(99, "pinctrl-bcm2711")


def test_restricted_mmio_refuses_fsel_other_masks_and_other_registers(monkeypatch):
    import mmap
    import stat
    import struct

    daemon = load()
    memory = mmap.mmap(-1, mmap.PAGESIZE)
    closed = []
    monkeypatch.setattr(daemon.os, "open", lambda *args: 123)
    monkeypatch.setattr(daemon.os, "fstat",
                        lambda _: SimpleNamespace(st_mode=stat.S_IFCHR, st_rdev=42))
    monkeypatch.setattr(daemon.os, "close", lambda fd: closed.append(fd))
    monkeypatch.setattr(daemon.mmap, "mmap", lambda *args, **kw: memory)
    registers = daemon.GpiomemRegisters(42)
    initial = memory[:]
    for offset, mask in ((8, 68157440), (0x1c, 1 << 21), (0x28, 1 << 20),
                         (0x34, 68157440)):
        with pytest.raises(ValueError):
            registers.write32(offset, mask)
    for offset in (8, 0x1c, 0x28):
        with pytest.raises(ValueError):
            registers.read32(offset)
    assert memory[:] == initial
    registers.write32(0x1c, 68157440)
    assert struct.unpack_from("<I", memory, 0x1c)[0] == 68157440
    struct.pack_into("<I", memory, 0x34, 68157440 | (1 << 21))
    assert registers.read32(0x34) == 68157440
    registers.close()
    assert closed == [123]


@pytest.mark.parametrize("failure", ["map", "identity"])
def test_mmio_partial_open_closes_descriptor_without_register_writes(monkeypatch, failure):
    import stat
    daemon = load()
    closed = []
    monkeypatch.setattr(daemon.os, "open", lambda *args: 123)
    monkeypatch.setattr(daemon.os, "fstat",
                        lambda _: SimpleNamespace(st_mode=stat.S_IFCHR,
                                                  st_rdev=999 if failure == "identity" else 42))
    monkeypatch.setattr(daemon.os, "close", lambda fd: closed.append(fd))

    def failed_map(*args, **kwargs):
        if failure == "identity":
            pytest.fail("mapping before device identity check")
        raise OSError("map failure")

    monkeypatch.setattr(daemon.mmap, "mmap", failed_map)
    with pytest.raises((OSError, ValueError)):
        daemon.GpiomemRegisters(42)
    assert closed == [123]
