.PHONY: install dev run test lint fmt clean

install:
	pip install -e .

dev:
	pip install -e ".[dev]"

run:
	python -m wati_agent

run-mock:
	WATI_USE_MOCK_API=true python -m wati_agent

test:
	pytest tests/ -v

test-cov:
	pytest tests/ -v --cov=wati_agent --cov-report=term-missing

lint:
	ruff check src/ tests/
	mypy src/

fmt:
	ruff format src/ tests/
	ruff check --fix src/ tests/

clean:
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type d -name .pytest_cache -exec rm -rf {} +
	rm -rf dist build *.egg-info .coverage htmlcov
