"""Unit tests for schedule.py — pure Python, no HA dependency."""
from datetime import date

import pytest

from custom_components.chores.schedule import (
    EvenDaysCondition,
    IntervalSchedule,
    MonthlySchedule,
    OddDaysCondition,
    WeeklySchedule,
    build_schedule,
)

# ---------------------------------------------------------------------------
# WeeklySchedule
# ---------------------------------------------------------------------------

def test_weekly_next_occurrence_basic():
    # Mon=0, Wed=2, Fri=4
    sched = WeeklySchedule(days=[0, 2, 4], every_other_week=False, conditions=[], failure_behavior="skip")
    # 2026-04-13 is a Monday; next after it should be Wednesday 2026-04-15
    result = sched.next_occurrence_after(date(2026, 4, 13))
    assert result == date(2026, 4, 15)


def test_weekly_wraps_to_next_week():
    sched = WeeklySchedule(days=[0], every_other_week=False, conditions=[], failure_behavior="skip")
    # 2026-04-13 is Monday; next Monday is 2026-04-20
    result = sched.next_occurrence_after(date(2026, 4, 13))
    assert result == date(2026, 4, 20)


def test_weekly_every_other_week_on_week():
    # Reference Monday: 2026-04-13. Active weeks are even offsets (0, 2, 4…).
    ref = date(2026, 4, 13)
    sched = WeeklySchedule(
        days=[0], every_other_week=True, conditions=[], failure_behavior="skip", reference_date=ref
    )
    # Next Monday after ref is 2026-04-20 (offset=1, odd → skip); 2026-04-27 (offset=2, even → active)
    result = sched.next_occurrence_after(ref)
    assert result == date(2026, 4, 27)


def test_weekly_every_other_week_already_active():
    ref = date(2026, 4, 13)
    sched = WeeklySchedule(
        days=[1], every_other_week=True, conditions=[], failure_behavior="skip", reference_date=ref
    )
    # Tuesday of the ref week (2026-04-14) is in the active week (offset=0)
    result = sched.next_occurrence_after(date(2026, 4, 13))
    assert result == date(2026, 4, 14)


def test_weekly_string_day_names_via_build_schedule():
    sched = build_schedule({
        "type": "weekly",
        "days": ["monday", "friday"],
        "every_other_week": False,
    })
    # 2026-04-13 is Monday; next is Friday 2026-04-17
    result = sched.next_occurrence_after(date(2026, 4, 13))
    assert result == date(2026, 4, 17)


def test_weekly_no_days_returns_none():
    sched = WeeklySchedule(days=[], every_other_week=False, conditions=[], failure_behavior="skip")
    assert sched.next_occurrence_after(date(2026, 4, 13)) is None


# ---------------------------------------------------------------------------
# MonthlySchedule
# ---------------------------------------------------------------------------

def test_monthly_day_of_month_same_month():
    sched = MonthlySchedule(day_of_month=20, weekday_occurrence=None, conditions=[], failure_behavior="skip")
    result = sched.next_occurrence_after(date(2026, 4, 10))
    assert result == date(2026, 4, 20)


def test_monthly_day_of_month_next_month():
    sched = MonthlySchedule(day_of_month=5, weekday_occurrence=None, conditions=[], failure_behavior="skip")
    result = sched.next_occurrence_after(date(2026, 4, 10))
    assert result == date(2026, 5, 5)


def test_monthly_last_day():
    sched = MonthlySchedule(day_of_month=-1, weekday_occurrence=None, conditions=[], failure_behavior="skip")
    result = sched.next_occurrence_after(date(2026, 4, 28))
    assert result == date(2026, 4, 30)


def test_monthly_last_day_february():
    sched = MonthlySchedule(day_of_month=-1, weekday_occurrence=None, conditions=[], failure_behavior="skip")
    result = sched.next_occurrence_after(date(2026, 1, 31))
    assert result == date(2026, 2, 28)


def test_monthly_weekday_occurrence_second_tuesday():
    # (week=2, weekday=1) = 2nd Tuesday
    sched = MonthlySchedule(day_of_month=None, weekday_occurrence=(2, 1), conditions=[], failure_behavior="skip")
    # April 2026: Tuesdays on 7, 14, 21, 28 → 2nd Tuesday = April 14
    result = sched.next_occurrence_after(date(2026, 4, 1))
    assert result == date(2026, 4, 14)


def test_monthly_weekday_occurrence_via_build_schedule():
    sched = build_schedule({
        "type": "monthly",
        "weekday_occurrence": {"week": 1, "weekday": "friday"},
    })
    # April 2026: first Friday = April 3
    result = sched.next_occurrence_after(date(2026, 3, 31))
    assert result == date(2026, 4, 3)


# ---------------------------------------------------------------------------
# IntervalSchedule
# ---------------------------------------------------------------------------

def test_interval_adds_days():
    sched = IntervalSchedule(days=7, conditions=[], failure_behavior="skip")
    result = sched.next_occurrence_after(date(2026, 4, 13))
    assert result == date(2026, 4, 20)


def test_interval_one_day():
    sched = IntervalSchedule(days=1, conditions=[], failure_behavior="skip")
    result = sched.next_occurrence_after(date(2026, 4, 13))
    assert result == date(2026, 4, 14)


def test_interval_via_build_schedule():
    sched = build_schedule({"type": "interval", "days": 14})
    result = sched.next_occurrence_after(date(2026, 4, 1))
    assert result == date(2026, 4, 15)


# ---------------------------------------------------------------------------
# Conditions
# ---------------------------------------------------------------------------

def test_even_days_condition():
    cond = EvenDaysCondition()
    assert cond.is_valid(date(2026, 4, 2)) is True
    assert cond.is_valid(date(2026, 4, 3)) is False


def test_odd_days_condition():
    cond = OddDaysCondition()
    assert cond.is_valid(date(2026, 4, 3)) is True
    assert cond.is_valid(date(2026, 4, 4)) is False


def test_condition_failure_skip():
    # Weekly on Sunday (6); add even_days condition with skip behavior.
    # If Sunday lands on an odd day, skip to the next Sunday.
    # April 2026: Sun Apr 5 (odd→skip), Sun Apr 12 (even→valid)
    sched = build_schedule({
        "type": "weekly",
        "days": ["sunday"],
        "conditions": [{"type": "even_days"}],
        "condition_failure": "skip",
    })
    result = sched.next_due(date(2026, 4, 4))
    assert result is not None
    assert result.weekday() == 6  # Sunday
    assert result.day % 2 == 0   # even day


def test_condition_failure_delay():
    # Interval every 7 days from Apr 6 → Apr 13 (odd day).
    # delay behavior slides forward until an even day.
    sched = IntervalSchedule(days=7, conditions=[EvenDaysCondition()], failure_behavior="delay")
    result = sched.next_due(date(2026, 4, 6))
    assert result is not None
    assert result.day % 2 == 0
    assert result >= date(2026, 4, 13)


# ---------------------------------------------------------------------------
# Summaries (smoke test)
# ---------------------------------------------------------------------------

def test_weekly_summary():
    sched = WeeklySchedule(days=[0, 4], every_other_week=False, conditions=[], failure_behavior="skip")
    assert "Mon" in sched.summary()
    assert "Fri" in sched.summary()


def test_monthly_summary_day():
    sched = MonthlySchedule(day_of_month=15, weekday_occurrence=None, conditions=[], failure_behavior="skip")
    assert "15" in sched.summary()


def test_interval_summary():
    sched = IntervalSchedule(days=3, conditions=[], failure_behavior="skip")
    assert "3" in sched.summary()
