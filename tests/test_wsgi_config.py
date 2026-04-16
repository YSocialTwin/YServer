from __future__ import annotations

import importlib.util
import json
import sys
import types
from pathlib import Path


def test_wsgi_loads_toxicity_annotation_flag(tmp_path, monkeypatch):
    config_path = tmp_path / "exp_config.json"
    config_path.write_text(
        json.dumps(
            {
                "perspective_api": None,
                "toxicity_annotation": True,
                "sentiment_annotation": False,
                "emotion_annotation": False,
                "stress_reward": {"enabled": True},
            }
        ),
        encoding="utf-8",
    )

    fake_app = types.SimpleNamespace(config={})
    fake_y_server = types.ModuleType("y_server")
    fake_y_server.app = fake_app
    monkeypatch.setitem(sys.modules, "y_server", fake_y_server)
    monkeypatch.setenv("YSERVER_CONFIG", str(config_path))

    module_path = Path("/Users/rossetti/PycharmProjects/YWeb/external/YServer/wsgi.py")
    spec = importlib.util.spec_from_file_location("yserver_wsgi_test", module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    assert fake_app.config["toxicity_annotation"] is True
    assert fake_app.config["stress_reward_enabled"] is True
