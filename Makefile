tests: lint
	python3 -m pytest

lint:
	pylint aioweb

all: tests 

coverage:
	coverage run --source=aioweb -m pytest
	coverage report -m
	coverage html