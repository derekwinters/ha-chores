# ha-chores

A Home Assistant custom integration for tracking household chores. Each chore is a persistent entity with a schedule, assignment, and point value. Chores transition between `due` and `complete` automatically based on their schedule.

## Requirements

- Home Assistant 2024.1.0 or newer

## Installation

### HACS (recommended)

1. Add this repository to HACS as a custom repository.
2. Search for **Chores** and install it.
3. Restart Home Assistant.
4. Add configuration to `configuration.yaml` (see below).

### Manual

1. Copy `custom_components/chores/` into your Home Assistant `config/custom_components/` directory.
2. Restart Home Assistant.
3. Add configuration to `configuration.yaml` (see below).
4. Restart Home Assistant again.

## Configuration

Chores are defined in `configuration.yaml` under the `chores:` key. Each entry becomes a separate entity.

```yaml
chores:
  - name: Vacuum Living Room
    schedule:
      type: weekly
      days: [monday, thursday]
    assignment_type: rotating
    eligible_people: [alice, bob]
    points: 5

  - name: Clean Bathroom
    schedule:
      type: monthly
      day_of_month: 1
    assignment_type: fixed
    assignee: alice
    points: 10

  - name: Take Out Trash
    schedule:
      type: interval
      days: 7
    points: 2
```

### Chore options

| Key | Required | Default | Description |
|-----|----------|---------|-------------|
| `name` | Yes | — | Display name. Also used to generate the entity ID. |
| `unique_id` | No | derived from name | Override the unique ID. |
| `schedule` | Yes | — | When the chore is due. See [Schedules](#schedules). |
| `assignment_type` | No | `open` | `fixed`, `rotating`, or `open`. |
| `eligible_people` | No | `[]` | List of people for rotating or open chores. |
| `assignee` | No | — | Required for `fixed` assignment type. |
| `points` | No | `0` | Points awarded on completion. |

### Schedules

#### Weekly

```yaml
schedule:
  type: weekly
  days: [monday, wednesday, friday]   # day names or integers (0=Mon … 6=Sun)
  every_other_week: false             # optional, default false
  reference_date: "2024-01-01"        # anchor for every_other_week alternation
```

#### Monthly

```yaml
# On a fixed day of the month (-1 = last day)
schedule:
  type: monthly
  day_of_month: 15

# On the Nth weekday of the month
schedule:
  type: monthly
  weekday_occurrence:
    week: 2        # 1–5
    weekday: tuesday
```

#### Interval

```yaml
schedule:
  type: interval
  days: 14
```

### Conditions

Any schedule can include optional conditions that restrict valid due dates.

```yaml
schedule:
  type: weekly
  days: [saturday]
  conditions:
    - type: even_days     # only even-numbered days of the month
  condition_failure: skip  # skip | delay (default: skip)
```

- `skip` — skip this occurrence and advance to the next scheduled date.
- `delay` — slide the due date forward day-by-day until the condition is met.

Available condition types: `even_days`, `odd_days`.

## Entities

Each chore creates one entity with domain `chores`. Entity IDs follow the pattern `chores.<name_slug>`.

### States

| State | Meaning |
|-------|---------|
| `due` | The current cycle is active and waiting to be completed or skipped. |
| `complete` | The current cycle is resolved. Automatically returns to `due` when the next due date arrives. |

### Attributes

| Attribute | Description |
|-----------|-------------|
| `next_due` | ISO date string of the next due date. |
| `age` | Days since `next_due`. Negative = due in the future, 0 = due today, positive = overdue. |
| `schedule_summary` | Human-readable schedule description, e.g. "Weekly on Mon, Thu". |
| `assignment_type` | `fixed`, `rotating`, or `open`. |
| `eligible_people` | List of people eligible for this chore. |
| `current_assignee` | Person currently assigned. |
| `next_assignee` | Next person in rotation (rotating chores only). |
| `points` | Point value awarded on completion. |
| `last_change_type` | `completed`, `skipped`, or `reassigned`. |
| `last_changed_at` | ISO datetime of the last state change. |
| `last_changed_by` | Person responsible for the last change. |
| `last_completed_by` | Person who last completed the chore. |
| `last_completed_at` | ISO datetime of the last completion. |

## Services

### `chores.complete`

Mark a chore as completed. Advances the schedule to the next due date and awards points.

```yaml
service: chores.complete
target:
  entity_id: chores.vacuum_living_room
data:
  completed_by: alice   # optional; defaults to current_assignee
```

### `chores.skip`

Skip the current occurrence without awarding or penalizing points. Advances to the next due date.

```yaml
service: chores.skip
target:
  entity_id: chores.vacuum_living_room
```

### `chores.skip_and_reassign`

Skip the current occurrence and change the assignee. For rotating chores, advances the rotation if no assignee is specified.

```yaml
service: chores.skip_and_reassign
target:
  entity_id: chores.vacuum_living_room
data:
  assignee: bob   # optional
```

### `chores.reassign`

Change the current assignee without affecting the schedule.

```yaml
service: chores.reassign
target:
  entity_id: chores.vacuum_living_room
data:
  assignee: bob   # required
```

## Assignment types

| Type | Behavior |
|------|----------|
| `fixed` | Always assigned to the same person. |
| `rotating` | Assigned to one person at a time; rotates to the next person on completion. |
| `open` | No fixed assignee; any person can complete it. |

## Development

```bash
cd chores
python3 -m venv .venv
source .venv/bin/activate

# Layer 1 — schedule unit tests (no HA install required)
pip install pytest pytest-asyncio
pytest tests/unit/ -v

# All tests
pip install -r requirements-test.txt
pytest -v
```

Activate the conventional commit hook:

```bash
git config core.hooksPath .githooks
```
