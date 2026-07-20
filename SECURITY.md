# Security

The MCP server and Lua bridge are intended for a single trusted user on one machine.
The WebSocket server refuses non-loopback binds and authenticates the Lua client with
a shared secret. Do not expose MCP stdio through an untrusted relay. Tool inputs are
validated, direct Lua evaluation is deliberately absent, and Lua operations are
allow-listed on both sides.

Self-driving is experimental and simulation-only. A dead-man timer brakes a controlled
vehicle when commands stop, and the configurable speed ceiling suppresses throttle.
These safeguards are not suitable for controlling a physical vehicle.

Report vulnerabilities privately through GitHub's security advisory feature.

