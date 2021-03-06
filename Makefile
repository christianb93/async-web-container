tests: lint
	python3 -m pytest -v

lint:
	pylint aioweb
	mypy -p aioweb

all: tests 

coverage:
	coverage run --source=aioweb -m pytest
	coverage report -m
	coverage html