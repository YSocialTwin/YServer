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
