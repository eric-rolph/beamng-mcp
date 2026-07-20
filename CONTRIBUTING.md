# Contributing

Use Python 3.11 or newer and `uv sync --extra dev`. Run `uv run ruff check .` and
`uv run pytest -q` before submitting a pull request. New MCP tools must validate all
inputs and tests must not require a running copy of BeamNG. Integration tests should be
marked and opt-in because BeamNG.drive/BeamNG.tech is proprietary software.

