from __future__ import annotations

from datetime import datetime, timezone

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import STORAGE_KEY, STORAGE_VERSION


class ChoreCoordinator:
    """Persists chore state and points via HA storage."""

    def __init__(self, hass: HomeAssistant) -> None:
        self._hass = hass
        self._store: Store = Store(hass, STORAGE_VERSION, STORAGE_KEY)
        self._chore_data: dict[str, dict] = {}
        self._points_log: dict[str, list[dict]] = {}  # person -> [{date, points, chore_id}]

    async def async_load(self) -> None:
        stored = await self._store.async_load() or {}
        self._chore_data = stored.get("chores", {})
        self._points_log = stored.get("points", {})

    async def async_save(self) -> None:
        await self._store.async_save({
            "chores": self._chore_data,
            "points": self._points_log,
        })

    def get_chore_data(self, unique_id: str) -> dict:
        return self._chore_data.get(unique_id, {})

    def set_chore_data(self, unique_id: str, data: dict) -> None:
        self._chore_data[unique_id] = data

    def award_points(self, person: str, points: int, chore_id: str, completed_at: datetime) -> None:
        if person not in self._points_log:
            self._points_log[person] = []
        self._points_log[person].append({
            "date": completed_at.isoformat(),
            "points": points,
            "chore_id": chore_id,
        })

    def get_points_since(self, person: str, since: datetime) -> int:
        entries = self._points_log.get(person, [])
        total = 0
        for entry in entries:
            entry_dt = datetime.fromisoformat(entry["date"])
            # Normalize to aware datetime for comparison
            if entry_dt.tzinfo is None:
                entry_dt = entry_dt.replace(tzinfo=timezone.utc)
            if since.tzinfo is None:
                since_cmp = since.replace(tzinfo=timezone.utc)
            else:
                since_cmp = since
            if entry_dt >= since_cmp:
                total += entry["points"]
        return total
