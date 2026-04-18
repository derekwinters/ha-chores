"""Tests for ChoreEntity — uses hass fixture from pHAcc."""
from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.chores.const import (
    STATE_COMPLETE,
    STATE_DUE,
    CHANGE_COMPLETED,
    CHANGE_SKIPPED,
    CHANGE_REASSIGNED,
    CHANGE_FORCED_DUE,
)
from custom_components.chores.coordinator import ChoreCoordinator
from custom_components.chores.entity import ChoreEntity


def _make_coordinator(hass):
    coord = ChoreCoordinator(hass)
    coord.async_save = AsyncMock()
    return coord


def _make_entity(hass, config_overrides=None):
    base_config = {
        "name": "Vacuum",
        "unique_id": "vacuum",
        "schedule": {"type": "interval", "days": 7},
        "assignment_type": "open",
        "eligible_people": [],
        "points": 0,
    }
    if config_overrides:
        base_config.update(config_overrides)
    coord = _make_coordinator(hass)
    entity = ChoreEntity(base_config, coord)
    entity.hass = hass
    entity.entity_id = "chores.vacuum"
    entity.async_write_ha_state = MagicMock()
    return entity, coord


async def _add_to_hass(entity):
    """Simulate async_added_to_hass without a real HA entity registry."""
    stored = entity._coordinator.get_chore_data(entity.unique_id)
    if stored:
        entity._restore_from_stored(stored)
    else:
        entity._initialize_first_run()
        entity._persist()


# ---------------------------------------------------------------------------
# Initialization
# ---------------------------------------------------------------------------

async def test_initial_state_interval_chore(hass):
    entity, _ = _make_entity(hass)
    await _add_to_hass(entity)
    # Interval chores start complete (not yet due)
    assert entity.state == STATE_COMPLETE
    assert entity._next_due is not None
    assert entity._next_due > date.today()


async def test_initial_state_weekly_due_today(hass):
    # Force weekly schedule with today's weekday so it comes due today
    today = date.today()
    entity, _ = _make_entity(hass, {
        "schedule": {"type": "weekly", "days": [today.weekday()]},
    })
    await _add_to_hass(entity)
    # next_due == today → state should be due
    assert entity._next_due == today
    assert entity.state == STATE_DUE


# ---------------------------------------------------------------------------
# async_complete
# ---------------------------------------------------------------------------

async def test_complete_advances_schedule(hass):
    entity, _ = _make_entity(hass)
    await _add_to_hass(entity)
    # Force the chore to be overdue so completing it must advance next_due
    entity._next_due = date(2026, 1, 1)

    with patch("custom_components.chores.entity.async_track_point_in_time"):
        await entity.async_complete()

    assert entity.state == STATE_COMPLETE
    assert entity._next_due is not None
    assert entity._next_due > date.today()
    assert entity._last_change_type == CHANGE_COMPLETED


async def test_complete_records_completer(hass):
    entity, _ = _make_entity(hass)
    await _add_to_hass(entity)

    with patch("custom_components.chores.entity.async_track_point_in_time"):
        await entity.async_complete(completed_by="alice")

    assert entity._last_completed_by == "alice"
    assert entity._last_changed_by == "alice"


async def test_complete_awards_points(hass):
    entity, coord = _make_entity(hass, {"points": 10, "assignment_type": "open"})
    await _add_to_hass(entity)

    with patch("custom_components.chores.entity.async_track_point_in_time"):
        await entity.async_complete(completed_by="bob")

    total = coord.get_points_since("bob", datetime(2000, 1, 1, tzinfo=timezone.utc))
    assert total == 10


# ---------------------------------------------------------------------------
# async_skip
# ---------------------------------------------------------------------------

async def test_skip_advances_schedule(hass):
    entity, _ = _make_entity(hass)
    await _add_to_hass(entity)
    # Force the chore to be overdue so skipping it must advance next_due
    entity._next_due = date(2026, 1, 1)

    with patch("custom_components.chores.entity.async_track_point_in_time"):
        await entity.async_skip()

    assert entity.state == STATE_COMPLETE
    assert entity._next_due > date.today()
    assert entity._last_change_type == CHANGE_SKIPPED
    assert entity._last_changed_by is None


# ---------------------------------------------------------------------------
# Rotating assignment
# ---------------------------------------------------------------------------

async def test_rotating_assignment_cycles_on_complete(hass):
    entity, _ = _make_entity(hass, {
        "assignment_type": "rotating",
        "eligible_people": ["alice", "bob", "carol"],
    })
    await _add_to_hass(entity)
    assert entity._current_assignee == "alice"

    with patch("custom_components.chores.entity.async_track_point_in_time"):
        await entity.async_complete()

    assert entity._current_assignee == "bob"
    assert entity._rotation_index == 1


async def test_rotating_assignment_wraps_around(hass):
    entity, _ = _make_entity(hass, {
        "assignment_type": "rotating",
        "eligible_people": ["alice", "bob"],
    })
    await _add_to_hass(entity)
    entity._rotation_index = 1
    entity._current_assignee = "bob"

    with patch("custom_components.chores.entity.async_track_point_in_time"):
        await entity.async_complete()

    assert entity._current_assignee == "alice"
    assert entity._rotation_index == 0


# ---------------------------------------------------------------------------
# async_reassign
# ---------------------------------------------------------------------------

async def test_reassign_changes_assignee(hass):
    entity, _ = _make_entity(hass)
    await _add_to_hass(entity)

    await entity.async_reassign("dave")

    assert entity._current_assignee == "dave"
    assert entity._last_change_type == CHANGE_REASSIGNED


async def test_reassign_updates_rotation_index(hass):
    entity, _ = _make_entity(hass, {
        "assignment_type": "rotating",
        "eligible_people": ["alice", "bob", "carol"],
    })
    await _add_to_hass(entity)

    await entity.async_reassign("carol")

    assert entity._current_assignee == "carol"
    assert entity._rotation_index == 2


# ---------------------------------------------------------------------------
# async_mark_due
# ---------------------------------------------------------------------------

async def test_mark_due_forces_complete_chore_to_due(hass):
    entity, _ = _make_entity(hass)
    await _add_to_hass(entity)
    entity._state = STATE_COMPLETE

    await entity.async_mark_due()

    assert entity.state == STATE_DUE
    assert entity._last_change_type == CHANGE_FORCED_DUE


async def test_mark_due_is_noop_when_already_due(hass):
    entity, _ = _make_entity(hass)
    await _add_to_hass(entity)
    entity._state = STATE_DUE
    entity.async_write_ha_state.reset_mock()

    await entity.async_mark_due()

    assert entity.state == STATE_DUE
    entity.async_write_ha_state.assert_not_called()


async def test_mark_due_cancels_scheduled_transition(hass):
    entity, _ = _make_entity(hass)
    await _add_to_hass(entity)
    entity._state = STATE_COMPLETE
    unsub = MagicMock()
    entity._unsub_transition = unsub

    await entity.async_mark_due()

    unsub.assert_called_once()
    assert entity._unsub_transition is None


# ---------------------------------------------------------------------------
# Restore from stored
# ---------------------------------------------------------------------------

async def test_restore_from_stored(hass):
    entity, coord = _make_entity(hass)
    stored = {
        "state": STATE_COMPLETE,
        "next_due": "2026-06-01",
        "last_changed_at": "2026-04-17T10:00:00",
        "last_changed_by": "alice",
        "last_change_type": CHANGE_COMPLETED,
        "last_completed_at": "2026-04-17T10:00:00",
        "last_completed_by": "alice",
        "rotation_index": 0,
        "current_assignee": None,
    }
    coord.set_chore_data("vacuum", stored)

    entity._restore_from_stored(stored)

    assert entity._state == STATE_COMPLETE
    assert entity._next_due == date(2026, 6, 1)
    assert entity._last_changed_by == "alice"
    assert entity._last_change_type == CHANGE_COMPLETED
