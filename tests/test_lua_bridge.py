import pytest

from beamng_mcp.lua_bridge import LuaBridge


def test_bridge_rejects_non_loopback_bind() -> None:
    with pytest.raises(ValueError, match="loopback"):
        LuaBridge("0.0.0.0", 8765, "long-secret")

