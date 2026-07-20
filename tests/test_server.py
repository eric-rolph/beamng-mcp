from beamng_mcp.server import app


def test_safe_defaults() -> None:
    assert app.settings.lua_ws_host == "127.0.0.1"
    assert app.settings.max_speed_kph <= 130

