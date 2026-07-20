"""Domain exceptions with messages that are safe to return through MCP."""

from __future__ import annotations


class BeamNGMCPError(RuntimeError):
    """Base class for expected operational failures."""


class ConfigurationError(BeamNGMCPError):
    """Configuration is missing, inconsistent, or unsafe."""


class SimulatorConnectionError(BeamNGMCPError):
    """BeamNGpy cannot connect to or communicate with BeamNG."""


class LuaBridgeError(BeamNGMCPError):
    """The private Lua WebSocket bridge failed."""


class SafetyInterlockError(BeamNGMCPError):
    """A requested mutation was rejected by a safety interlock."""


class WorkspaceError(BeamNGMCPError):
    """A mod workspace operation was invalid or escaped its root."""


class NotFoundError(BeamNGMCPError):
    """A requested scenario, vehicle, sensor, object, or artifact was absent."""


class ConflictError(BeamNGMCPError):
    """An optimistic-concurrency precondition did not match."""
