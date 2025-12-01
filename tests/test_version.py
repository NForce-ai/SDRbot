from sdrbot_cli.version import __version__


def test_version_is_string():
    assert isinstance(__version__, str)
    assert len(__version__) > 0


def test_version_format():
    # Simple check that it looks like a version (numbers and dots)
    import re

    assert re.match(r"^\d+\.\d+\.\d+", __version__)
