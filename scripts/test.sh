#!/usr/bin/env bash
set -euo pipefail

PYTHON_BIN="${PYTHON:-python3}"

run_python() {
  if command -v uv >/dev/null 2>&1 && [ -f pyproject.toml ]; then
    uv run --extra dev "$@"
  else
    "$PYTHON_BIN" "$@"
  fi
}

ran=0

has_npm_script() {
  local script="$1"
  [ -f package.json ] || return 1
  node -e "const p=require('./package.json'); process.exit(p.scripts && p.scripts[process.argv[1]] ? 0 : 1)" "$script"
}

if has_npm_script test; then
  npm test
  ran=1
fi

if [ -f Cargo.toml ]; then
  cargo test --all-targets --all-features
  ran=1
fi

if ([ -d tests ] || [ -d test ] || [ -f pytest.ini ]) && ([ -f pyproject.toml ] || [ -f setup.py ] || [ -f pytest.ini ]); then
  run_python -m pytest
  ran=1
fi

if [ "$ran" -eq 0 ]; then
  echo "No test command configured; skipping."
fi
