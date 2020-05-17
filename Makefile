tests: lint
	python3 -W ignore -m pytest

lint:
	pylint aioweb

all: tests 