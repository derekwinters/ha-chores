"""Tests for ChoreCoordinator — uses hass fixture from pHAcc."""
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from custom_components.chores.coordinator import ChoreCoordinator


@pytest.fixture
def coordinator(hass):
    return ChoreCoordinator(hass)


async def test_load_empty(coordinator):
    with patch.object(coordinator._store, "async_load", AsyncMock(return_value=None)):
        await coordinator.async_load()
    assert coordinator.get_chore_data("any") == {}


async def test_set_and_get_roundtrip(coordinator):
    data = {"state": "due", "next_due": "2026-05-01"}
    coordinator.set_chore_data("chore_1", data)
    assert coordinator.get_chore_data("chore_1") == data


async def test_missing_key_returns_empty(coordinator):
    assert coordinator.get_chore_data("nonexistent") == {}


async def test_award_points_accumulates(coordinator):
    now = datetime(2026, 4, 17, 12, 0, tzinfo=timezone.utc)
    coordinator.award_points("alice", 5, "chore_1", now)
    coordinator.award_points("alice", 3, "chore_2", now)
    total = coordinator.get_points_since("alice", datetime(2026, 1, 1, tzinfo=timezone.utc))
    assert total == 8


async def test_get_points_since_filters_old_entries(coordinator):
    old = datetime(2026, 1, 1, tzinfo=timezone.utc)
    recent = datetime(2026, 4, 1, tzinfo=timezone.utc)
    coordinator.award_points("bob", 10, "chore_1", old)
    coordinator.award_points("bob", 7, "chore_2", recent)
    total = coordinator.get_points_since("bob", datetime(2026, 3, 1, tzinfo=timezone.utc))
    assert total == 7


async def test_get_points_unknown_person(coordinator):
    assert coordinator.get_points_since("nobody", datetime(2026, 1, 1, tzinfo=timezone.utc)) == 0


async def test_load_restores_saved_data(coordinator):
    stored = {
        "chores": {"c1": {"state": "complete"}},
        "points": {"alice": [{"date": "2026-04-01T00:00:00+00:00", "points": 5, "chore_id": "c1"}]},
    }
    with patch.object(coordinator._store, "async_load", AsyncMock(return_value=stored)):
        await coordinator.async_load()
    assert coordinator.get_chore_data("c1") == {"state": "complete"}
    total = coordinator.get_points_since("alice", datetime(2026, 1, 1, tzinfo=timezone.utc))
    assert total == 5
