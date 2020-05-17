tests: lint
	python3 -m pytest

lint:
	pylint aioweb

all: tests 