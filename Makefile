.PHONY: all test


all:


test:
	python3 -m pytest tests

lint:
	python3 -m pylint pdp

cov:
	python3 -m coverage run --source=. -m pytest tests
	python3 -m coverage report -m
