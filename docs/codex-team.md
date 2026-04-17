# Codex Team

This repo now includes a repo-local Codex team marketplace at `.agents/plugins/marketplace.json`.

## Roles

- `cs348-team-lead`: Breaks work into parallel tracks, assigns owners, and keeps frontend/backend changes aligned.
- `cs348-code-reviewer`: Reviews diffs for bugs, regressions, missing validation, and missing tests.
- `cs348-ui-engineer`: Owns React/Vite UI work in `frontend/src/` and preserves existing dashboard patterns.
- `cs348-backend-engineer`: Owns Flask, validation, ORM, and trading integration work in `backend/`.
- `cs348-bug-fixer`: Reproduces issues, narrows root cause, and lands the smallest defensible fix.
- `cs348-qa-validator`: Chooses and runs validation relevant to the change, then reports residual risk.
- `cs348-trading-specialist`: Handles Alpaca, quotes, order flow, portfolio math, and market-data edge cases.
- `cs348-plan-guardian`: Compares implementation to the original plan, detects drift, and applies focused repairs.

## Suggested Handoffs

- UI bug or redesign: `cs348-team-lead` -> `cs348-ui-engineer` -> `cs348-code-reviewer` -> `cs348-qa-validator`
- API or DB change: `cs348-team-lead` -> `cs348-backend-engineer` -> `cs348-code-reviewer` -> `cs348-qa-validator`
- Trading behavior issue: `cs348-team-lead` -> `cs348-trading-specialist` -> `cs348-bug-fixer` -> `cs348-qa-validator`
- Cross-stack feature: `cs348-team-lead` coordinates `cs348-ui-engineer` and `cs348-backend-engineer`, then hands off to review and QA
- Drift from intended scope or behavior: `cs348-team-lead` or `cs348-plan-guardian` -> targeted specialist -> `cs348-code-reviewer` -> `cs348-qa-validator`

## Repo Context Baked Into Prompts

- Active app: React frontend in `frontend/` and Flask backend in `backend/server.py`
- DB access stays in SQLAlchemy helpers in `backend/database.py`
- Trading integration stays in `backend/trading.py`
- Ignore `backend/_deprecated/` unless a task explicitly targets it
- Standard validation: `npm run validate`
- Slice-specific validation: `npm run validate:frontend` and `npm run validate:backend`

## Notes

- These are repo-local plugins, so they travel with the project.
- If your Codex UI does not immediately show them, reload the workspace so it re-reads `.agents/plugins/marketplace.json`.
