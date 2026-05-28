from __future__ import annotations

import sys
import types

from y_server.content_analysis import textual_data


def test_toxicity_skips_annotation_when_disabled(monkeypatch):
    persisted = []

    monkeypatch.setattr(
        textual_data,
        "_persist_toxicity_scores",
        lambda post_id, db, scores: persisted.append((post_id, scores)),
    )

    textual_data.toxicity("hello", None, 10, db=None, enabled=False)

    assert persisted == []


def test_toxicity_falls_back_to_detoxify_without_api_key(monkeypatch):
    persisted = []

    monkeypatch.setattr(
        textual_data,
        "_detoxify_scores",
        lambda text: {"toxicity": 0.42, "threat": 0.01},
    )
    monkeypatch.setattr(
        textual_data,
        "_persist_toxicity_scores",
        lambda post_id, db, scores: persisted.append((post_id, scores)),
    )

    textual_data.toxicity("hello", "", 11, db=None, enabled=True)

    assert persisted == [(11, {"toxicity": 0.42, "threat": 0.01})]


def test_toxicity_uses_perspective_when_api_key_present(monkeypatch):
    persisted = []

    class FakePerspectiveAPI:
        def __init__(self, api_key):
            self.api_key = api_key

        def score(self, text, tests):
            assert self.api_key == "api-key"
            assert text == "hello"
            assert "TOXICITY" in tests
            return {"TOXICITY": 0.91}

    monkeypatch.setitem(
        sys.modules,
        "perspective",
        types.SimpleNamespace(PerspectiveAPI=FakePerspectiveAPI),
    )
    monkeypatch.setattr(
        textual_data,
        "_persist_toxicity_scores",
        lambda post_id, db, scores: persisted.append((post_id, scores)),
    )

    textual_data.toxicity("hello", "api-key", 12, db=None, enabled=True)

    assert persisted == [(12, {"TOXICITY": 0.91})]


def test_should_annotate_toxicity_defaults_to_false():
    assert textual_data.should_annotate_toxicity({}) is False
    assert textual_data.should_annotate_toxicity({"toxicity_annotation": False}) is False
    assert textual_data.should_annotate_toxicity({"toxicity_annotation": True}) is True
