.PHONY: install format lint typecheck test schema-audit check cleanup-merged

install:
	bash scripts/install.sh

schema-audit:
	uv run --extra dev vasp-lsp-schema-audit

format:
	bash scripts/format.sh

lint:
	bash scripts/lint.sh

typecheck:
	bash scripts/typecheck.sh

test:
	bash scripts/test.sh

check: lint typecheck test schema-audit

cleanup-merged:
	bash scripts/cleanup_merged_worktrees.sh
