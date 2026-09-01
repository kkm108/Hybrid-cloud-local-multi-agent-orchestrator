PYTHON := python
PYTEST := $(PYTHON) -m pytest

.PHONY: test lint smoke backup consult restore install

test:
	$(PYTEST) -q -m "not gpu and not live and not ui"

lint:
	ruff check .

smoke:
	$(PYTHON) -m socialai.cli --smoke

backup:
	$(PYTHON) scripts/backup.py --mode restore

consult:
	$(PYTHON) scripts/backup.py --mode consult

restore:
	$(PYTHON) scripts/restore.py --bundle $(BUNDLE)

install:
	$(PYTHON) -m pip install -e ".[dev]"
