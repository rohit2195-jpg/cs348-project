# CODEX.md

## Overview
- Stock trading simulator built on Alpaca paper trading with a Flask backend, SQLite via SQLAlchemy ORM, and a React/Vite frontend.
- The active user-facing app is the React frontend in `frontend/` backed by the Flask API in `backend/server.py`.
- `backend/_deprecated/` is historical code and should be ignored unless a task explicitly targets it.

## Architecture
- Backend API: `backend/server.py`
- Database models and persistence helpers: `backend/database.py`
- Trading and market data wrapper: `backend/trading.py`
- Frontend app: `frontend/src/`
- Project background guide: `claude.md`

## Run Commands
- Backend: `cd backend && python3 server.py`
- Frontend: `cd frontend && npm run dev`

## Validation Commands
- Standard repo validation: `npm run validate`
- Frontend only: `npm run validate:frontend`
- Backend only: `npm run validate:backend`

Codex should run the relevant validation command before finalizing code changes and report any step that could not run or failed.

## Repo Rules
- Prefer active backend/frontend paths over anything in `backend/_deprecated/`.
- Keep DB access on SQLAlchemy ORM helpers. Do not introduce raw SQL built from request values.
- For backend API changes, validate request inputs at the Flask boundary before calling trading or DB helpers.
- For frontend changes, preserve the existing UI patterns unless the task explicitly asks for redesign.
- If a change affects both frontend and backend, validate both sides with `npm run validate`.

## Security Notes
- Best SQL injection protection in this repo is parameterized ORM queries plus strict server-side validation, not manual escaping.
- Treat all user-controlled text as untrusted, including symbols in path params, JSON body fields, watchlist notes, and filter query params.
- Invalid user input should return clear `400` responses instead of falling through to generic `500` errors.
