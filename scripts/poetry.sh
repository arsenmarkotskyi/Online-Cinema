#!/usr/bin/env bash
# macOS / some setups: no `python` on PATH, only python3 — Poetry may call `python`.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
PY="$(command -v python3.12 || command -v python3 || true)"
if [[ ! -x "${PY:-}" ]]; then
  echo "error: need python3.12 or python3 on PATH" >&2
  exit 1
fi
mkdir -p "$ROOT/.poetry-bin"
ln -sf "$PY" "$ROOT/.poetry-bin/python"
export PATH="$ROOT/.poetry-bin:$PATH"
exec poetry "$@"
