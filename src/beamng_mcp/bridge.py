import asyncio

from .app import Application


async def run() -> None:
    app = Application()
    await app.lua.start()
    print(f"BeamNG Lua bridge listening on ws://{app.settings.lua_ws_host}:{app.settings.lua_ws_port}")
    try:
        await asyncio.Future()
    finally:
        await app.lua.close()


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
