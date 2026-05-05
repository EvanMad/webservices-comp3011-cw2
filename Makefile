test:
	uv run -m pytest

lint:
	ruff check

format:
	ruff format

coverage:
	uv run -m pytest --cov=src