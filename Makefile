.PHONY: all test


all:


test:
	python3 -m pytest tests

lint:
	python3 -m pylint pdp

cov:
	python3 -m coverage run -m pytest tests
	python3 -m coverage report -m

mut:
	PYTHONPATH=tests python3 -m mutmut --runner "python3 -m hammett -x" run
	python3 -m mutmut results
