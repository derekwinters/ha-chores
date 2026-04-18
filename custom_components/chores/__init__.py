"""Home Assistant Chore Tracking integration."""
from __future__ import annotations

import logging
import re

import voluptuous as vol
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.entity_component import EntityComponent
from homeassistant.helpers.typing import ConfigType

from .const import (
    DOMAIN,
    SERVICE_COMPLETE,
    SERVICE_SKIP,
    SERVICE_SKIP_AND_REASSIGN,
    SERVICE_REASSIGN,
    SERVICE_MARK_DUE,
)
from .coordinator import ChoreCoordinator
from .entity import ChoreEntity

_LOGGER = logging.getLogger(__name__)

_CONDITION_SCHEMA = vol.Schema(
    {
        vol.Required("type"): vol.In(["even_days", "odd_days"]),
    }
)

_SCHEDULE_SCHEMA = vol.Schema(
    {
        vol.Required("type"): vol.In(["weekly", "monthly", "interval"]),
        vol.Optional("days"): vol.All(cv.ensure_list, [vol.Any(str, int)]),
        vol.Optional("every_other_week", default=False): cv.boolean,
        vol.Optional("reference_date"): cv.string,
        vol.Optional("day_of_month"): int,
        vol.Optional("weekday_occurrence"): vol.Schema(
            {
                vol.Required("week"): vol.All(int, vol.Range(min=1, max=5)),
                vol.Required("weekday"): vol.Any(str, int),
            }
        ),
        vol.Optional("conditions", default=[]): vol.All(cv.ensure_list, [_CONDITION_SCHEMA]),
        vol.Optional("condition_failure", default="skip"): vol.In(["skip", "delay"]),
    },
    extra=vol.ALLOW_EXTRA,
)

_CHORE_SCHEMA = vol.Schema(
    {
        vol.Required("name"): cv.string,
        vol.Optional("unique_id"): cv.string,
        vol.Required("schedule"): _SCHEDULE_SCHEMA,
        vol.Optional("assignment_type", default="open"): vol.In(["fixed", "rotating", "open"]),
        vol.Optional("eligible_people", default=[]): vol.All(cv.ensure_list, [cv.string]),
        vol.Optional("assignee"): cv.string,
        vol.Optional("points", default=0): vol.All(int, vol.Range(min=0)),
    }
)

CONFIG_SCHEMA = vol.Schema(
    {DOMAIN: vol.All(cv.ensure_list, [_CHORE_SCHEMA])},
    extra=vol.ALLOW_EXTRA,
)


def _make_unique_id(name: str) -> str:
    return re.sub(r"\W+", "_", name.lower()).strip("_")


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    chore_configs: list[dict] = list(config.get(DOMAIN, []))

    for chore in chore_configs:
        if "unique_id" not in chore:
            chore["unique_id"] = _make_unique_id(chore["name"])

    coordinator = ChoreCoordinator(hass)
    await coordinator.async_load()

    component = EntityComponent(_LOGGER, DOMAIN, hass)
    entities = [ChoreEntity(chore, coordinator) for chore in chore_configs]
    await component.async_add_entities(entities)

    component.async_register_entity_service(
        SERVICE_COMPLETE,
        {vol.Optional("completed_by"): cv.string},
        "async_complete",
    )
    component.async_register_entity_service(
        SERVICE_SKIP,
        {},
        "async_skip",
    )
    component.async_register_entity_service(
        SERVICE_SKIP_AND_REASSIGN,
        {vol.Optional("assignee"): cv.string},
        "async_skip_and_reassign",
    )
    component.async_register_entity_service(
        SERVICE_REASSIGN,
        {vol.Required("assignee"): cv.string},
        "async_reassign",
    )
    component.async_register_entity_service(
        SERVICE_MARK_DUE,
        {},
        "async_mark_due",
    )

    hass.data[DOMAIN] = {"coordinator": coordinator, "component": component}
    return True
