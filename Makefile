.PHONY: all test


all:


test:
	python3 -m pytest tests

lint:
	python3 -m pylint pdp
