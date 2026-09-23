.PHONY: help install test lint typecheck verify format audit clean dashboard docs

PYTHON ?= .venv/bin/python
TEST_WORKERS ?= 2

help:
	@echo "DEC-MAPF - developer and researcher commands"
	@echo "make install    Install locked development extras"
	@echo "make verify     Run lint, types and Python tests"
	@echo "make test       Run all Python tests with two pytest workers (TEST_WORKERS=0 for serial)"
	@echo "make audit      Check documentation links and parameter references"
	@echo "make dashboard  Start the optional local GUI (build frontend first)"
	@echo "make docs       Build the local searchable documentation"

install:
	uv sync --locked --python 3.12 --extra gui --extra analysis --extra dev --extra docs

test:
	$(PYTHON) -m pytest -n $(TEST_WORKERS) --dist loadfile --max-worker-restart=0

lint:
	$(PYTHON) -m ruff check src tests examples

format:
	$(PYTHON) -m ruff format src tests examples

typecheck:
	$(PYTHON) -m mypy src

verify: lint typecheck test

audit:
	$(PYTHON) scripts/documentation_reference.py --check
	$(PYTHON) scripts/check_documentation.py

dashboard:
	$(PYTHON) -m mapf.cli dashboard --host 127.0.0.1 --port 8000

docs:
	$(PYTHON) scripts/build_docs.py

clean:
	$(PYTHON) -c 'from pathlib import Path; import shutil; [shutil.rmtree(p) for root in ("src", "tests", "examples", "scripts") for p in Path(root).rglob("__pycache__")]; [shutil.rmtree(p) for p in map(Path, (".pytest_cache", ".ruff_cache", ".mypy_cache")) if p.is_dir()]'
