test:
	uv run -m pytest

lint:
	ruff check

format:
	ruff format