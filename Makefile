PYTHON ?= python3


.PHONY: all test lint cov mut

all:

test:
	$(PYTHON) -m pytest tests

lint:
	$(PYTHON) -m pylint pdpy11

cov:
	$(PYTHON) -m coverage run -m pytest tests
	$(PYTHON) -m coverage report -m

mut:
	$(PYTHON) mutation.py run
	$(PYTHON) -m mutmut results
