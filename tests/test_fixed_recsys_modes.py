"""A scenario-defined fixed-order recommender (``fixed:<name>``) is a supported mode of this platform."""

from ysocial_platform.recsys import modes


def test_fixed_modes_are_supported_and_keep_their_name():
    assert modes._normalize_content_recsys_mode(" FIXED: Alpha ") == "fixed:Alpha"
    assert modes.is_supported_content_recsys_mode("fixed:Alpha")
    assert modes.describe("fixed:Alpha")


def test_an_empty_fixed_name_and_other_modes_are_unchanged():
    assert not modes.is_supported_content_recsys_mode("fixed:")
    assert modes.is_supported_content_recsys_mode("ReverseChrono")
    assert modes._normalize_content_recsys_mode("rc") == "ReverseChrono"


def test_an_older_core_without_the_fixed_reader_degrades_to_no_fixed_modes(monkeypatch):
    """PLATFORM_API < 1.4: the platform keeps working and simply does not offer ``fixed:<name>``."""
    import importlib
    import sys

    monkeypatch.setitem(sys.modules, "y_web.sdk.fixed_recsys", None)   # makes the import fail
    try:
        reloaded = importlib.reload(modes)
        assert not reloaded.is_supported_content_recsys_mode("fixed:Alpha")
        assert reloaded.is_supported_content_recsys_mode("ReverseChrono")
        assert reloaded.describe("fixed:Alpha") is None
    finally:
        monkeypatch.undo()
        importlib.reload(modes)
