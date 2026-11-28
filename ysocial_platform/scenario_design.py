"""Scenario Design driver of this platform: Microblogging on the Standard (Flask) runtime.

The Scenario Design plugin (``external/ScenarioDesign``) asks a platform's provider for ``scenario_design_driver``. The driver
here only says which experiments it serves; publication is done by ``scenario_adapter.py`` of this repository; seeding and database access come from the plugin's ``StandardKit``
(``modules.scenario_editor.backend.drivers.kits``, SCENARIO_API 1.3). Without the plugin the factory answers ``None`` and
nothing changes for the platform.
"""
from __future__ import annotations

import functools
import importlib

PLATFORM_KEY = "microblogging"

_support = None  # the plugin's ``kits.support``, set by ``build_driver`` (the adapter of this platform needs it)


def support():
    """What the adapter may use from the plugin (``kits.support``); only after the plugin built the driver."""
    if _support is None:
        raise RuntimeError("the Scenario Design plugin has not handed its support to this platform yet")
    return _support


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
    global _support
    StandardKit, with_identity = kits.StandardKit, kits.with_identity
    _support = getattr(kits, "support", None)

    class PlatformDriver(StandardKit):
        def info(self):
            return with_identity(super().info(), family="ysocial_server", platform_key=PLATFORM_KEY, simulator_types=("Standard",))

        def matches(self, exp):
            return getattr(exp, "platform_type", None) == PLATFORM_KEY and super().matches(exp)

        def _make_adapter(self):
            # the adapter of this platform; a plugin that does not offer ``support`` keeps using its own (SCENARIO_API < 1.3)
            if _support is None:
                return super()._make_adapter()
            from .scenario_adapter import StandardMaterializationAdapter

            return StandardMaterializationAdapter()

    return PlatformDriver()
