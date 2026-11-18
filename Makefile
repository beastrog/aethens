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
	$(RUN) python bench/run_bench.py
	$(RUN) python bench/external/run_external.py --sample
