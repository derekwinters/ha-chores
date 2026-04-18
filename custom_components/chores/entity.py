from __future__ import annotations

import logging
from datetime import date, datetime, time, timedelta
from typing import Callable, Optional

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import Entity
from homeassistant.util import dt as dt_util
from homeassistant.helpers.event import async_track_point_in_time

from .const import (
    STATE_DUE,
    STATE_COMPLETE,
    ASSIGNMENT_FIXED,
    ASSIGNMENT_ROTATING,
    ATTR_NEXT_DUE,
    ATTR_AGE,
    ATTR_ASSIGNMENT_TYPE,
    ATTR_ELIGIBLE_PEOPLE,
    ATTR_CURRENT_ASSIGNEE,
    ATTR_NEXT_ASSIGNEE,
    ATTR_LAST_CHANGE_TYPE,
    ATTR_LAST_CHANGED_AT,
    ATTR_LAST_CHANGED_BY,
    ATTR_LAST_COMPLETED_BY,
    ATTR_LAST_COMPLETED_AT,
    ATTR_POINTS,
    ATTR_SCHEDULE_SUMMARY,
    CHANGE_COMPLETED,
    CHANGE_SKIPPED,
    CHANGE_REASSIGNED,
    CHANGE_FORCED_DUE,
)
from .coordinator import ChoreCoordinator
from .schedule import IntervalSchedule, build_schedule

_LOGGER = logging.getLogger(__name__)


class ChoreEntity(Entity):
    _attr_should_poll = False

    def __init__(self, config: dict, coordinator: ChoreCoordinator) -> None:
        self._config = config
        self._coordinator = coordinator
        self._unsub_transition: Optional[Callable] = None

        self._schedule = build_schedule(config["schedule"])
        self._assignment_type: str = config.get("assignment_type", "open")
        self._eligible_people: list[str] = config.get("eligible_people", [])
        self._points_value: int = config.get("points", 0)

        # Mutable runtime state — overwritten by _restore_from_stored if data exists
        self._state: str = STATE_DUE
        self._next_due: Optional[date] = None
        self._current_assignee: Optional[str] = self._initial_assignee()
        self._rotation_index: int = 0
        self._last_changed_at: Optional[datetime] = None
        self._last_changed_by: Optional[str] = None
        self._last_change_type: Optional[str] = None
        self._last_completed_at: Optional[datetime] = None
        self._last_completed_by: Optional[str] = None

    def _initial_assignee(self) -> Optional[str]:
        if self._assignment_type == ASSIGNMENT_FIXED:
            return self._config.get("assignee")
        if self._assignment_type == ASSIGNMENT_ROTATING and self._eligible_people:
            return self._eligible_people[0]
        return None

    @property
    def unique_id(self) -> str:
        return self._config["unique_id"]

    @property
    def name(self) -> str:
        return self._config["name"]

    @property
    def state(self) -> str:
        return self._state

    @property
    def extra_state_attributes(self) -> dict:
        attrs: dict = {
            ATTR_NEXT_DUE: self._next_due.isoformat() if self._next_due else None,
            ATTR_AGE: self._age,
            ATTR_ASSIGNMENT_TYPE: self._assignment_type,
            ATTR_ELIGIBLE_PEOPLE: self._eligible_people,
            ATTR_CURRENT_ASSIGNEE: self._current_assignee,
            ATTR_LAST_CHANGE_TYPE: self._last_change_type,
            ATTR_LAST_CHANGED_AT: self._last_changed_at.isoformat() if self._last_changed_at else None,
            ATTR_LAST_CHANGED_BY: self._last_changed_by,
            ATTR_LAST_COMPLETED_BY: self._last_completed_by,
            ATTR_LAST_COMPLETED_AT: self._last_completed_at.isoformat() if self._last_completed_at else None,
            ATTR_POINTS: self._points_value,
            ATTR_SCHEDULE_SUMMARY: self._schedule.summary(),
        }
        if self._assignment_type == ASSIGNMENT_ROTATING:
            attrs[ATTR_NEXT_ASSIGNEE] = self._next_assignee
        return attrs

    @property
    def _age(self) -> Optional[int]:
        if self._next_due is None:
            return None
        return (date.today() - self._next_due).days

    @property
    def _next_assignee(self) -> Optional[str]:
        if not self._eligible_people:
            return None
        next_idx = (self._rotation_index + 1) % len(self._eligible_people)
        return self._eligible_people[next_idx]

    async def async_added_to_hass(self) -> None:
        stored = self._coordinator.get_chore_data(self.unique_id)
        if stored:
            self._restore_from_stored(stored)
        else:
            self._initialize_first_run()
            self._persist()

        self._check_and_schedule_transition()

    async def async_will_remove_from_hass(self) -> None:
        self._cancel_transition()

    def _restore_from_stored(self, stored: dict) -> None:
        self._state = stored.get("state", STATE_DUE)

        next_due_str = stored.get("next_due")
        self._next_due = date.fromisoformat(next_due_str) if next_due_str else None

        for dt_field in ("last_changed_at", "last_completed_at"):
            val = stored.get(dt_field)
            setattr(self, f"_{dt_field}", datetime.fromisoformat(val) if val else None)

        self._last_changed_by = stored.get("last_changed_by")
        self._last_change_type = stored.get("last_change_type")
        self._last_completed_by = stored.get("last_completed_by")
        self._rotation_index = stored.get("rotation_index", 0)

        if self._assignment_type == ASSIGNMENT_FIXED:
            self._current_assignee = self._config.get("assignee")
        elif self._assignment_type == ASSIGNMENT_ROTATING and self._eligible_people:
            self._current_assignee = self._eligible_people[self._rotation_index % len(self._eligible_people)]
        else:
            self._current_assignee = stored.get("current_assignee")

    def _initialize_first_run(self) -> None:
        """Set initial next_due for a newly configured chore."""
        today = date.today()
        if isinstance(self._schedule, IntervalSchedule):
            # Interval chores start with first occurrence interval days from today
            self._next_due = self._schedule.next_occurrence_after(today)
        else:
            # Use yesterday as anchor so today can be returned as the first due date
            self._next_due = self._schedule.next_due(today - timedelta(days=1))

        if self._next_due is None or self._next_due <= today:
            self._state = STATE_DUE
        else:
            self._state = STATE_COMPLETE  # Not yet due; transitions to due when next_due arrives

    def _check_and_schedule_transition(self) -> None:
        if self._next_due is None:
            return

        today = dt_util.now().date()

        if self._state == STATE_COMPLETE and self._next_due <= today:
            self._state = STATE_DUE
            self.async_write_ha_state()
            return

        if self._state == STATE_COMPLETE and self._next_due > today:
            self._schedule_transition(self._next_due)

    def _schedule_transition(self, due_date: date) -> None:
        self._cancel_transition()
        due_dt = dt_util.as_local(datetime.combine(due_date, time.min))

        @callback
        def _on_due(_now: datetime) -> None:
            self._state = STATE_DUE
            self._unsub_transition = None
            self.async_write_ha_state()

        self._unsub_transition = async_track_point_in_time(self.hass, _on_due, due_dt)

    def _cancel_transition(self) -> None:
        if self._unsub_transition:
            self._unsub_transition()
            self._unsub_transition = None

    def _persist(self) -> None:
        data = {
            "state": self._state,
            "next_due": self._next_due.isoformat() if self._next_due else None,
            "last_changed_at": self._last_changed_at.isoformat() if self._last_changed_at else None,
            "last_changed_by": self._last_changed_by,
            "last_change_type": self._last_change_type,
            "last_completed_at": self._last_completed_at.isoformat() if self._last_completed_at else None,
            "last_completed_by": self._last_completed_by,
            "rotation_index": self._rotation_index,
            "current_assignee": self._current_assignee,
        }
        self._coordinator.set_chore_data(self.unique_id, data)
        self.hass.async_create_task(self._coordinator.async_save())

    # -------------------------------------------------------------------------
    # Service handlers
    # -------------------------------------------------------------------------

    async def async_complete(self, completed_by: Optional[str] = None) -> None:
        now = dt_util.now()
        effective_completer = completed_by or self._current_assignee

        if self._points_value > 0 and effective_completer:
            self._coordinator.award_points(effective_completer, self._points_value, self.unique_id, now)

        if self._assignment_type == ASSIGNMENT_ROTATING and self._eligible_people:
            self._rotation_index = (self._rotation_index + 1) % len(self._eligible_people)
            self._current_assignee = self._eligible_people[self._rotation_index]

        self._next_due = self._schedule.next_due(now.date())
        self._state = STATE_COMPLETE
        self._last_change_type = CHANGE_COMPLETED
        self._last_changed_at = now
        self._last_changed_by = effective_completer
        self._last_completed_at = now
        self._last_completed_by = effective_completer

        self._persist()
        if self._next_due:
            self._schedule_transition(self._next_due)
        self.async_write_ha_state()

    async def async_skip(self) -> None:
        now = dt_util.now()

        self._next_due = self._schedule.next_due(now.date())
        self._state = STATE_COMPLETE
        self._last_change_type = CHANGE_SKIPPED
        self._last_changed_at = now
        self._last_changed_by = None

        self._persist()
        if self._next_due:
            self._schedule_transition(self._next_due)
        self.async_write_ha_state()

    async def async_skip_and_reassign(self, assignee: Optional[str] = None) -> None:
        await self.async_skip()

        if assignee:
            self._current_assignee = assignee
            if self._assignment_type == ASSIGNMENT_ROTATING and assignee in self._eligible_people:
                self._rotation_index = self._eligible_people.index(assignee)
        elif self._assignment_type == ASSIGNMENT_ROTATING and self._eligible_people:
            self._rotation_index = (self._rotation_index + 1) % len(self._eligible_people)
            self._current_assignee = self._eligible_people[self._rotation_index]

        self._persist()
        self.async_write_ha_state()

    async def async_mark_due(self) -> None:
        if self._state == STATE_DUE:
            return
        now = dt_util.now()
        self._state = STATE_DUE
        self._last_change_type = CHANGE_FORCED_DUE
        self._last_changed_at = now
        self._last_changed_by = None
        self._cancel_transition()
        self._persist()
        self.async_write_ha_state()

    async def async_reassign(self, assignee: str) -> None:
        now = dt_util.now()
        self._current_assignee = assignee
        if self._assignment_type == ASSIGNMENT_ROTATING and assignee in self._eligible_people:
            self._rotation_index = self._eligible_people.index(assignee)

        self._last_change_type = CHANGE_REASSIGNED
        self._last_changed_at = now
        self._last_changed_by = None

        self._persist()
        self.async_write_ha_state()
