from freeze_protect import __version__


def test_package_exposes_a_version() -> None:
    assert __version__ == "1.2.0"
