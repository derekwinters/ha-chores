"""Mock HA and voluptuous so schedule.py can be imported without any HA install."""
import sys
from unittest.mock import MagicMock

_HA_MODULES = [
    "voluptuous",
    "homeassistant",
    "homeassistant.core",
    "homeassistant.helpers",
    "homeassistant.helpers.config_validation",
    "homeassistant.helpers.entity_component",
    "homeassistant.helpers.typing",
    "homeassistant.helpers.storage",
    "homeassistant.helpers.entity",
    "homeassistant.helpers.event",
    "homeassistant.util",
    "homeassistant.util.dt",
]

for mod in _HA_MODULES:
    sys.modules.setdefault(mod, MagicMock())
