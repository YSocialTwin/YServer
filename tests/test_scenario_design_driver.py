"""The Scenario Design driver of this platform (``ysocial_platform/scenario_design.py``).

Needs the Scenario Design plugin (``external/ScenarioDesign``) next to this repository; skipped without it.
"""
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

PLUGIN = Path(__file__).resolve().parents[2] / "ScenarioDesign"
if not (PLUGIN / "modules").is_dir():
    pytest.skip("the Scenario Design plugin is not installed", allow_module_level=True)
if str(PLUGIN) not in sys.path:
    sys.path.insert(0, str(PLUGIN))
pytest.importorskip("flask")

from ysocial_platform import scenario_design  # noqa: E402

PLATFORM, SIMULATOR, FAMILY = "microblogging", "Standard", "ysocial_server"


def exp(platform, simulator):
    return SimpleNamespace(platform_type=platform, simulator_type=simulator)


@pytest.fixture(autouse=True)
def fresh():
    scenario_design.build_driver.cache_clear()
    yield
    scenario_design.build_driver.cache_clear()


def test_the_driver_is_a_complete_scenario_driver():
    from modules.scenario_editor.backend.drivers.base import (
        DRIVER_API_VERSION, REQUIRED_METHODS, SUPPORTED_CONTENT_MODELS, DriverInfo, ScenarioDriver, api_major)

    driver = scenario_design.build_driver()
    assert isinstance(driver, ScenarioDriver)
    for name in REQUIRED_METHODS:
        assert not getattr(getattr(type(driver), name), "__isabstractmethod__", False), name
    info = driver.info()
    assert isinstance(info, DriverInfo) and info.family == FAMILY and info.platform_key == PLATFORM
    assert api_major(info.api_version) == api_major(DRIVER_API_VERSION)
    assert info.content_model in SUPPORTED_CONTENT_MODELS
    assert info.also_serves == ()


def test_it_serves_only_the_experiments_of_this_platform():
    driver = scenario_design.build_driver()
    assert driver.matches(exp(PLATFORM, SIMULATOR))
    for platform, simulator in [('forum', 'Standard'), ('microblogging', 'HPC')]:
        assert not driver.matches(exp(platform, simulator))


def test_the_provider_declares_it():
    from ysocial_platform import provider

    declared = [cls for cls in vars(provider).values()
                if isinstance(cls, type) and getattr(cls, "key", None) == PLATFORM
                and "scenario_design_driver" in vars(cls)]
    assert declared, "no provider of this platform declares scenario_design_driver"
    assert declared[0].scenario_design_driver() is scenario_design.build_driver()


def test_without_the_plugin_the_platform_is_unaffected(monkeypatch):
    monkeypatch.setitem(sys.modules, "modules.scenario_editor.backend.drivers.kits", None)
    assert scenario_design.build_driver() is None
