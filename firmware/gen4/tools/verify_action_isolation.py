"""Check linked action routes and normal CT button labels after dummy provisioning."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ACTION_MARKERS = (
    b"/api/v1/display/actions/timed-shower",
    b"/api/v1/display/actions/drain",
    b"POST ",
)
BUTTON_MARKERS = (b"DRZI 2s ZA TUS", b"IZPUST")
READ_ONLY_TARGETS = (
    "gen4_28ct",
    "gen4_28",
    "gen4_28ct_offline",
    "gen4_28_network_bench",
)
TEST_TARGET = "gen4_28ct_test_hub"


def image(target: str) -> bytes:
    path = ROOT / ".pio" / "build" / target / "firmware.bin"
    if not path.is_file():
        raise SystemExit(f"Missing {target} firmware image: {path}")
    return path.read_bytes()


def main() -> None:
    for target in READ_ONLY_TARGETS:
        data = image(target)
        for marker in ACTION_MARKERS:
            if marker in data:
                raise SystemExit(f"{target}: action marker present: {marker!r}")

    normal_ct = image("gen4_28ct")
    # The offline inspection image intentionally retains disabled button labels.
    for marker in BUTTON_MARKERS:
        if marker in normal_ct:
            raise SystemExit(f"gen4_28ct: action button present: {marker!r}")

    fixture = image(TEST_TARGET)
    for marker in ACTION_MARKERS:
        if marker not in fixture:
            raise SystemExit(f"{TEST_TARGET}: missing isolated action marker: {marker!r}")
    for marker in BUTTON_MARKERS:
        if marker not in fixture:
            raise SystemExit(f"{TEST_TARGET}: missing isolated button: {marker!r}")

    print("Action endpoints absent from read-only images; isolated test image retains them")


if __name__ == "__main__":
    main()
