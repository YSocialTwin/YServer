"""Scenario Design driver of this platform: Microblogging on the Standard (Flask) runtime.

The Scenario Design plugin (``external/ScenarioDesign``) asks a platform's provider for ``scenario_design_driver``. The driver
here only says which experiments it serves; publication, seeding and database access come from the plugin's ``StandardKit``
(``modules.scenario_editor.backend.drivers.kits``, SCENARIO_API 1.2). Without the plugin the factory answers ``None`` and
nothing changes for the platform.
"""
from __future__ import annotations

import functools

PLATFORM_KEY = "microblogging"


@functools.lru_cache(maxsize=1)
def build_driver():
    """The driver, or ``None`` when the Scenario Design plugin is not installed."""
    try:
        from modules.scenario_editor.backend.drivers.kits import StandardKit, with_identity
    except ImportError:
        return None

    class PlatformDriver(StandardKit):
        def info(self):
            return with_identity(super().info(), family="ysocial_server", platform_key=PLATFORM_KEY, simulator_types=("Standard",))

        def matches(self, exp):
            return getattr(exp, "platform_type", None) == PLATFORM_KEY and super().matches(exp)

    return PlatformDriver()
