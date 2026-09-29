.PHONY: help install install-dev test lint format type-check clean demo eval

help:
	@echo "PR-to-Production Agent Team - Makefile Commands"
	@echo ""
	@echo "Setup:"
	@echo "  make install       Install production dependencies"
	@echo "  make install-dev   Install dev dependencies"
	@echo ""
	@echo "Development:"
	@echo "  make format        Format code with black"
	@echo "  make lint          Lint code with ruff"
	@echo "  make type-check    Type check with mypy"
	@echo "  make test          Run all tests"
	@echo "  make demo          Run end-to-end demo (mock mode)"
	@echo "  make eval          Run evaluation harness"
	@echo ""
	@echo "Cleanup:"
	@echo "  make clean         Remove generated files"

install:
	pip install -e .

install-dev:
	pip install -e ".[dev]"

test:
	pytest -v

lint:
	ruff check pr_to_prod tests

format:
	black pr_to_prod tests
	ruff check --fix pr_to_prod tests

type-check:
	mypy pr_to_prod

demo:
	python -m pr_to_prod.cli demo --mock

eval:
	python -m pr_to_prod.evaluations.run_eval --provider mock

clean:
	rm -rf build/
	rm -rf dist/
	rm -rf *.egg-info
	rm -rf .pytest_cache/
	rm -rf .mypy_cache/
	rm -rf .ruff_cache/
	rm -rf htmlcov/
	rm -rf .coverage
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
