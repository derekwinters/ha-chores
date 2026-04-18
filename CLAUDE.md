# Chores — Claude Code Instructions

## Commits

All commits must use **Conventional Commits** format:

```
type(scope): short description

optional body
```

**Types** (drives release-please versioning):
- `feat` — new feature → bumps minor version
- `fix` — bug fix → bumps patch version
- `feat!` / `fix!` — breaking change → bumps major version
- `chore` — maintenance, no release
- `docs` — documentation only
- `test` — test changes only
- `refactor` — code restructure, no behavior change
- `ci` — CI/CD changes

**Scopes** (optional but encouraged):
- `schedule` — schedule calculation logic
- `entity` — ChoreEntity state machine
- `coordinator` — storage/persistence
- `config` — manifest, config schema

**Examples:**
```
feat(entity): add points multiplier for overdue chores
fix(schedule): monthly last-day calculation in February
chore(ci): pin pytest to 7.4
test(schedule): add even-days condition edge cases
```

Subject line ≤ 72 characters. Body only when the "why" isn't obvious from the subject.
