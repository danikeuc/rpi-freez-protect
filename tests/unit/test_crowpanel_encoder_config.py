from pathlib import Path


def test_encoder_signals_use_vendor_required_unbiased_inputs() -> None:
    hardware_source = (
        Path(__file__).parents[2] / "firmware" / "crowpanel" / "src" / "hardware.cpp"
    ).read_text(encoding="utf-8")

    assert "pinMode(BoardPins::kEncoderA, INPUT);" in hardware_source
    assert "pinMode(BoardPins::kEncoderB, INPUT);" in hardware_source
    assert "pinMode(BoardPins::kEncoderA, INPUT_PULLUP);" not in hardware_source
    assert "pinMode(BoardPins::kEncoderB, INPUT_PULLUP);" not in hardware_source


def test_crowpanel_target_explicitly_compiles_as_cpp17() -> None:
    platformio = (
        Path(__file__).parents[2] / "firmware" / "crowpanel" / "platformio.ini"
    ).read_text(encoding="utf-8")
    crowpanel_section = platformio.split("[env:native]", maxsplit=1)[0]

    assert "build_unflags = -std=gnu++11" in crowpanel_section
    assert "-std=gnu++17" in crowpanel_section
