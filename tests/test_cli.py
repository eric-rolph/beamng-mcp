from __future__ import annotations

import pytest

from beamng_mcp.cli import main


def test_serve_rejects_zero_port_before_starting_server(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["serve", "--port", "0"]) == 2
    captured = capsys.readouterr()
    assert "MCP port must be between 1 and 65535" in captured.err
