from __future__ import annotations

import calendar
from datetime import date, timedelta
from typing import Optional

SCHEDULE_WEEKLY = "weekly"
SCHEDULE_MONTHLY = "monthly"
SCHEDULE_INTERVAL = "interval"

WEEKDAY_MAP = {
    "monday": 0, "mon": 0,
    "tuesday": 1, "tue": 1,
    "wednesday": 2, "wed": 2,
    "thursday": 3, "thu": 3,
    "friday": 4, "fri": 4,
    "saturday": 5, "sat": 5,
    "sunday": 6, "sun": 6,
}


class Condition:
    def is_valid(self, d: date) -> bool:
        raise NotImplementedError

    def summary(self) -> str:
        raise NotImplementedError


class EvenDaysCondition(Condition):
    def is_valid(self, d: date) -> bool:
        return d.day % 2 == 0

    def summary(self) -> str:
        return "even-numbered days only"


class OddDaysCondition(Condition):
    def is_valid(self, d: date) -> bool:
        return d.day % 2 != 0

    def summary(self) -> str:
        return "odd-numbered days only"


def build_condition(config: dict) -> Condition:
    ctype = config["type"]
    if ctype == "even_days":
        return EvenDaysCondition()
    if ctype == "odd_days":
        return OddDaysCondition()
    raise ValueError(f"Unknown condition type: {ctype}")


class Schedule:
    def __init__(self, conditions: list[Condition], failure_behavior: str) -> None:
        self.conditions = conditions
        self.failure_behavior = failure_behavior  # "skip" or "delay"

    def _all_conditions_met(self, d: date) -> bool:
        return all(c.is_valid(d) for c in self.conditions)

    def next_occurrence_after(self, after: date) -> Optional[date]:
        raise NotImplementedError

    def next_due(self, after: date) -> Optional[date]:
        """Return the next valid due date strictly after `after`."""
        candidate = self.next_occurrence_after(after)
        if candidate is None or not self.conditions:
            return candidate

        if self.failure_behavior == "delay":
            # Slide forward day-by-day until conditions are satisfied
            for _ in range(31):
                if self._all_conditions_met(candidate):
                    return candidate
                candidate += timedelta(days=1)
            return None

        # failure_behavior == "skip": advance to next scheduled occurrence until satisfied
        for _ in range(366):
            if self._all_conditions_met(candidate):
                return candidate
            next_candidate = self.next_occurrence_after(candidate)
            if next_candidate is None or next_candidate <= candidate:
                return None
            candidate = next_candidate
        return None

    def summary(self) -> str:
        raise NotImplementedError


class WeeklySchedule(Schedule):
    def __init__(
        self,
        days: list[int],
        every_other_week: bool,
        conditions: list[Condition],
        failure_behavior: str,
        reference_date: Optional[date] = None,
    ) -> None:
        super().__init__(conditions, failure_behavior)
        self.days = sorted(set(days))
        self.every_other_week = every_other_week
        self._reference_monday = self._monday_of(reference_date or date.today())

    @staticmethod
    def _monday_of(d: date) -> date:
        return d - timedelta(days=d.weekday())

    def _is_active_week(self, d: date) -> bool:
        if not self.every_other_week:
            return True
        weeks_offset = (self._monday_of(d) - self._reference_monday).days // 7
        return weeks_offset % 2 == 0

    def next_occurrence_after(self, after: date) -> Optional[date]:
        if not self.days:
            return None
        start = after + timedelta(days=1)
        for delta in range(14 if self.every_other_week else 7):
            candidate = start + timedelta(days=delta)
            if candidate.weekday() in self.days and self._is_active_week(candidate):
                return candidate
        return None

    def summary(self) -> str:
        day_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        days_str = ", ".join(day_names[d] for d in self.days)
        prefix = "Every other week on" if self.every_other_week else "Weekly on"
        return f"{prefix} {days_str}"


class MonthlySchedule(Schedule):
    def __init__(
        self,
        day_of_month: Optional[int],
        weekday_occurrence: Optional[tuple[int, int]],
        conditions: list[Condition],
        failure_behavior: str,
    ) -> None:
        super().__init__(conditions, failure_behavior)
        self.day_of_month = day_of_month
        self.weekday_occurrence = weekday_occurrence  # (1-indexed week, 0-indexed weekday)

    def _occurrence_in_month(self, year: int, month: int) -> Optional[date]:
        last_day = calendar.monthrange(year, month)[1]
        if self.day_of_month is not None:
            day = last_day if self.day_of_month == -1 else min(self.day_of_month, last_day)
            return date(year, month, day)
        if self.weekday_occurrence is not None:
            week_num, weekday = self.weekday_occurrence
            count = 0
            for day in range(1, last_day + 1):
                if date(year, month, day).weekday() == weekday:
                    count += 1
                    if count == week_num:
                        return date(year, month, day)
        return None

    def next_occurrence_after(self, after: date) -> Optional[date]:
        year, month = after.year, after.month
        for _ in range(13):
            candidate = self._occurrence_in_month(year, month)
            if candidate is not None and candidate > after:
                return candidate
            month += 1
            if month > 12:
                month = 1
                year += 1
        return None

    def summary(self) -> str:
        if self.day_of_month is not None:
            if self.day_of_month == -1:
                return "Monthly on the last day"
            ordinals = {1: "1st", 2: "2nd", 3: "3rd"}
            suffix = ordinals.get(self.day_of_month, f"{self.day_of_month}th")
            return f"Monthly on the {suffix}"
        if self.weekday_occurrence:
            week_num, weekday = self.weekday_occurrence
            day_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
            ordinals = ["1st", "2nd", "3rd", "4th", "5th"]
            return f"Monthly on the {ordinals[week_num - 1]} {day_names[weekday]}"
        return "Monthly"


class IntervalSchedule(Schedule):
    def __init__(self, days: int, conditions: list[Condition], failure_behavior: str) -> None:
        super().__init__(conditions, failure_behavior)
        self.days = days

    def next_occurrence_after(self, after: date) -> Optional[date]:
        return after + timedelta(days=self.days)

    def summary(self) -> str:
        return f"Every {self.days} day{'s' if self.days != 1 else ''}"


def build_schedule(config: dict) -> Schedule:
    stype = config["type"]
    conditions = [build_condition(c) for c in config.get("conditions", [])]
    failure = config.get("condition_failure", "skip")

    if stype == SCHEDULE_WEEKLY:
        raw_days = config.get("days", [])
        days = [WEEKDAY_MAP[d.lower()] if isinstance(d, str) else d for d in raw_days]
        every_other = config.get("every_other_week", False)
        ref = None
        if "reference_date" in config:
            ref = date.fromisoformat(config["reference_date"])
        return WeeklySchedule(days, every_other, conditions, failure, ref)

    if stype == SCHEDULE_MONTHLY:
        day_of_month = config.get("day_of_month")
        weekday_occ = None
        if "weekday_occurrence" in config:
            wo = config["weekday_occurrence"]
            wday = wo["weekday"]
            if isinstance(wday, str):
                wday = WEEKDAY_MAP[wday.lower()]
            weekday_occ = (wo["week"], wday)
        return MonthlySchedule(day_of_month, weekday_occ, conditions, failure)

    if stype == SCHEDULE_INTERVAL:
        days_raw = config["days"]
        days = days_raw[0] if isinstance(days_raw, list) else days_raw
        return IntervalSchedule(int(days), conditions, failure)

    raise ValueError(f"Unknown schedule type: {stype!r}")
