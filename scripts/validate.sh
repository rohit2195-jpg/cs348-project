#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MODE="${1:-all}"
PYTHON_BIN="python3"
PYTHON_CMD=()

if [[ -x "$ROOT_DIR/.venv/bin/python" ]]; then
  PYTHON_BIN="$ROOT_DIR/.venv/bin/python"
elif [[ -x "$ROOT_DIR/backend/.venv/bin/python" ]]; then
  PYTHON_BIN="$ROOT_DIR/backend/.venv/bin/python"
fi

CURRENT_ARCH="$(arch)"
PYDANTIC_CORE_SO="$(find "$ROOT_DIR/backend/.venv/lib" -path "*/site-packages/pydantic_core/_pydantic_core*.so" 2>/dev/null | head -n 1 || true)"
if [[ -n "$PYDANTIC_CORE_SO" ]] && [[ "$CURRENT_ARCH" != "arm64" ]]; then
  if file "$PYDANTIC_CORE_SO" | grep -q "arm64"; then
    PYTHON_CMD=(arch -arm64 "$PYTHON_BIN")
  fi
fi

if [[ ${#PYTHON_CMD[@]} -eq 0 ]]; then
  PYTHON_CMD=("$PYTHON_BIN")
fi

run_step() {
  echo
  echo "==> $1"
  shift
  "$@"
}

if [[ "$MODE" != "all" && "$MODE" != "--backend-only" && "$MODE" != "--frontend-only" ]]; then
  echo "Unknown mode: $MODE"
  echo "Usage: bash scripts/validate.sh [--backend-only|--frontend-only]"
  exit 1
fi

if [[ "$MODE" != "--backend-only" ]]; then
  run_step "Frontend lint" npm --prefix "$ROOT_DIR/frontend" run lint
  run_step "Frontend build" npm --prefix "$ROOT_DIR/frontend" run build
fi

if [[ "$MODE" != "--frontend-only" ]]; then
run_step "Backend Python syntax check" "${PYTHON_CMD[@]}" - "$ROOT_DIR" <<'PY'
import pathlib
import sys

root = pathlib.Path(sys.argv[1])
backend = root / "backend"
files = sorted(
    path for path in backend.rglob("*.py")
    if "_deprecated" not in path.parts
    and ".venv" not in path.parts
    and "venv" not in path.parts
    and "__pycache__" not in path.parts
)

failed = []
for path in files:
    try:
        source = path.read_text(encoding="utf-8")
        compile(source, str(path), "exec")
    except Exception as exc:
        failed.append((path, exc))

if failed:
    for path, exc in failed:
        print(f"[FAIL] {path}: {exc}")
    raise SystemExit(1)

print(f"Compiled {len(files)} backend Python file(s).")
PY

  run_step "Backend dependency and project smoke check" "${PYTHON_CMD[@]}" - "$ROOT_DIR" <<'PY'
import importlib
import pathlib
import sys

root = pathlib.Path(sys.argv[1])
sys.path.insert(0, str(root / "backend"))

modules = [
    "flask",
    "sqlalchemy",
    "dotenv",
    "alpaca",
    "validation",
    "database",
    "trading",
    "feature_store",
    "evaluator",
    "simulator",
]

for name in modules:
    importlib.import_module(name)
    print(f"import ok: {name}")
PY
fi
