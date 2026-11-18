# Aethens developer targets. RUN can be overridden, e.g. `make check RUN=` inside an activated venv.
RUN ?= uv run

.PHONY: check lint type test bench

check: lint type test bench

lint:
	$(RUN) ruff check .
	$(RUN) ruff format --check .

type:
	$(RUN) mypy

test:
	$(RUN) pytest

bench:
	@echo "bench: fixtures and manifest exist (bench/), the metrics runner and regression gate arrive in B6."
