
all:
	@echo Here are some valid "make" targets. && echo
	@egrep '^[a-z-]*:' Makefile | awk '{print $$1}' | tr -d :

ACTIVATE := source .venv/bin/activate
export PYTHONPATH := .
export SPATIALITE_LIBRARY_PATH := /opt/homebrew/lib/mod_spatialite

.venv:
	uv sync

test: .venv
	env | sort | grep SPAT
	$(ACTIVATE) && python -m unittest tests/*_test.py

lint: .venv
	$(ACTIVATE) && black . && isort . && ruff check
	$(ACTIVATE) && pyright

profile: .venv
	$(ACTIVATE) && python -m cProfile tests/bench.py | head -30

COVERAGE := $(ACTIVATE) && coverage
coverage: .venv
	$(COVERAGE) erase
	$(COVERAGE) run tests/bench.py
	$(COVERAGE) report
	$(COVERAGE) html

clean:
	rm -rf htmlcov/
