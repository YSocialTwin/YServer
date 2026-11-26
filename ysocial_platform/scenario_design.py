"""Scenario Design driver of this platform: Microblogging on the Standard (Flask) runtime.

The Scenario Design plugin (``external/ScenarioDesign``) asks a platform's provider for ``scenario_design_driver``. The driver
here only says which experiments it serves; publication, seeding and database access come from the plugin's ``StandardKit``
(``modules.scenario_editor.backend.drivers.kits``, SCENARIO_API 1.3). Without the plugin the factory answers ``None`` and
nothing changes for the platform.
"""
from __future__ import annotations

import functools
import importlib

PLATFORM_KEY = "microblogging"


@functools.lru_cache(maxsize=1)
def build_driver(kits=None):
    """The driver, or ``None`` when the Scenario Design plugin is not installed.

    The plugin passes its kits (SCENARIO_API 1.3): a platform cannot import the plugin, which YSocial loads under a
    private namespace. Called without them (tests, tools) it tries the plain import.
    """
    if kits is None:
        try:
            kits = importlib.import_module("modules.scenario_editor.backend.drivers.kits")
        except ImportError:
            return None
    StandardKit, with_identity = kits.StandardKit, kits.with_identity

    class PlatformDriver(StandardKit):
        def info(self):
            return with_identity(super().info(), family="ysocial_server", platform_key=PLATFORM_KEY, simulator_types=("Standard",))

        def matches(self, exp):
            return getattr(exp, "platform_type", None) == PLATFORM_KEY and super().matches(exp)

    return PlatformDriver()
