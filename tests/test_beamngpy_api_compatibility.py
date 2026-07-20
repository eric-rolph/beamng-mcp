"""Offline contracts for the BeamNGpy public calls used by the adapter."""

from __future__ import annotations

import inspect
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import Any

import pytest
from beamngpy import BeamNGpy, Scenario, Vehicle
from beamngpy.sensors import (
    GPS,
    AdvancedIMU,
    Camera,
    Damage,
    Electrics,
    Lidar,
    PowertrainSensor,
    Radar,
    RoadsSensor,
    State,
    Ultrasonic,
)


@dataclass(frozen=True)
class CallShape:
    """One public BeamNGpy callable and the argument shape the adapter uses."""

    name: str
    target: Callable[..., Any]
    args: tuple[Any, ...] = ()
    kwargs: dict[str, Any] = field(default_factory=dict)


def _core_call_shapes() -> Iterable[CallShape]:
    """Build contracts without opening a BeamNG socket or launching the game."""

    bng = BeamNGpy("127.0.0.1", 25252, quit_on_close=False)
    scenario = Scenario("gridmap_v2", "compatibility", description="offline contract")
    vehicle = Vehicle(
        "ego",
        "etk800",
        license="MCP",
        color="White",
        part_config="vehicles/etk800/base.pc",
    )
    position = (0.0, 0.0, 0.0)
    rotation = (0.0, 0.0, 0.0, 1.0)

    return (
        CallShape(
            "BeamNGpy",
            BeamNGpy,
            ("127.0.0.1", 25252),
            {"home": None, "binary": None, "user": None, "quit_on_close": False},
        ),
        CallShape(
            "BeamNGpy.open",
            bng.open,
            kwargs={"extensions": None, "launch": False, "listen_ip": "127.0.0.1"},
        ),
        CallShape("BeamNGpy.disconnect", bng.disconnect),
        CallShape("BeamNGpy.tech_enabled", bng.tech_enabled),
        CallShape(
            "SystemApi.get_info",
            bng.system.get_info,
            kwargs={"os": True, "cpu": False, "gpu": False, "power": False},
        ),
        CallShape("ControlApi.pause", bng.control.pause),
        CallShape("ControlApi.resume", bng.control.resume),
        CallShape("ControlApi.step", bng.control.step, (1,), {"wait": True}),
        CallShape(
            "SettingsApi.set_deterministic",
            bng.settings.set_deterministic,
            kwargs={"steps_per_second": 60, "speed_factor": 1},
        ),
        CallShape("SettingsApi.set_nondeterministic", bng.settings.set_nondeterministic),
        CallShape("EnvironmentApi.get_gravity", bng.env.get_gravity),
        CallShape("EnvironmentApi.get_tod", bng.env.get_tod),
        CallShape("EnvironmentApi.set_gravity", bng.env.set_gravity, (-9.807,)),
        CallShape(
            "EnvironmentApi.set_tod",
            bng.env.set_tod,
            kwargs={"tod": 0.5, "play": False},
        ),
        CallShape(
            "EnvironmentApi.set_weather_preset",
            bng.env.set_weather_preset,
            ("cloudy", 1.0),
        ),
        CallShape(
            "TrafficApi.spawn",
            bng.traffic.spawn,
            kwargs={"max_amount": 4, "police_ratio": 0.25, "parked_amount": 2},
        ),
        CallShape("TrafficApi.stop", bng.traffic.stop, (True,)),
        CallShape("TrafficApi.reset", bng.traffic.reset),
        CallShape("ScenarioApi.get_scenarios", bng.scenario.get_scenarios, (None,)),
        CallShape(
            "ScenarioApi.get_level_scenarios",
            bng.scenario.get_level_scenarios,
            ("gridmap_v2",),
        ),
        CallShape("ScenarioApi.load", bng.scenario.load, (scenario,)),
        CallShape("ScenarioApi.start", bng.scenario.start),
        CallShape("ScenarioApi.restart", bng.scenario.restart),
        CallShape("ScenarioApi.stop", bng.scenario.stop),
        CallShape("ScenarioApi.get_vehicle", bng.scenario.get_vehicle, ("ego",)),
        CallShape(
            "ScenarioApi.get_road_network",
            bng.scenario.get_road_network,
            kwargs={"include_edges": True, "drivable_only": True},
        ),
        CallShape("ScenarioApi.get_road_edges", bng.scenario.get_road_edges, ("road",)),
        CallShape(
            "ScenarioApi.find_objects_class",
            bng.scenario.find_objects_class,
            ("TSStatic",),
        ),
        CallShape(
            "Scenario",
            Scenario,
            ("gridmap_v2", "compatibility"),
            {"description": "offline contract"},
        ),
        CallShape(
            "Scenario.add_vehicle",
            scenario.add_vehicle,
            (vehicle,),
            {"pos": position, "rot_quat": rotation, "cling": True},
        ),
        CallShape("Scenario.make", scenario.make, (bng,)),
        CallShape(
            "Vehicle",
            Vehicle,
            ("ego", "etk800"),
            {
                "license": "MCP",
                "color": "White",
                "part_config": "vehicles/etk800/base.pc",
            },
        ),
        CallShape("Vehicle.is_connected", vehicle.is_connected),
        CallShape("Vehicle.connect", vehicle.connect, (bng,)),
        CallShape(
            "Vehicle.control",
            vehicle.control,
            kwargs={
                "steering": 0.0,
                "throttle": 0.0,
                "brake": 1.0,
                "parkingbrake": 1.0,
                "clutch": 0.0,
                "gear": 1,
                "is_adas": True,
            },
        ),
        CallShape("VehiclesApi.get_current", bng.vehicles.get_current),
        CallShape("VehiclesApi.get_current_info", bng.vehicles.get_current_info, (True,)),
        CallShape("VehiclesApi.get_states", bng.vehicles.get_states, (["ego"],)),
        CallShape(
            "VehiclesApi.spawn",
            bng.vehicles.spawn,
            (vehicle, position, rotation, True, True),
        ),
        CallShape("VehiclesApi.despawn", bng.vehicles.despawn, (vehicle,)),
        CallShape(
            "VehiclesApi.teleport",
            bng.vehicles.teleport,
            (vehicle, position, rotation, True),
        ),
        CallShape("AIApi.set_mode", vehicle.ai.set_mode, ("span",)),
        CallShape("AIApi.set_speed", vehicle.ai.set_speed, (10.0,), {"mode": "limit"}),
        CallShape("AIApi.set_aggression", vehicle.ai.set_aggression, (0.5,)),
        CallShape("AIApi.drive_in_lane", vehicle.ai.drive_in_lane, (True,)),
        CallShape("AIApi.set_target", vehicle.ai.set_target, ("target",), {"mode": "chase"}),
        CallShape("AIApi.set_waypoint", vehicle.ai.set_waypoint, ("waypoint",)),
        CallShape("Sensors.attach", vehicle.sensors.attach, ("electrics", object())),
        CallShape("Sensors.poll", vehicle.sensors.poll, ("electrics",)),
        CallShape("Sensors.detach", vehicle.sensors.detach, ("electrics",)),
    )


@pytest.mark.parametrize("shape", _core_call_shapes(), ids=lambda shape: shape.name)
def test_beamngpy_public_api_accepts_adapter_call_shapes(shape: CallShape) -> None:
    """The supported SDK must accept every non-sensor call shape used by the adapter."""

    inspect.signature(shape.target).bind(*shape.args, **shape.kwargs)


def _sensor_constructor_shapes() -> Iterable[CallShape]:
    """Mirror each modern and legacy sensor allocation performed by the adapter."""

    bng = BeamNGpy("127.0.0.1", 25252, quit_on_close=False)
    vehicle = Vehicle("ego", "etk800")
    position = (0.0, 0.0, 1.7)
    direction = (0.0, -1.0, 0.0)
    common = {
        "name": "sensor",
        "bng": bng,
        "vehicle": vehicle,
        "requested_update_time": 0.1,
        "pos": position,
        "dir": direction,
    }
    timed = {
        "name": "sensor",
        "bng": bng,
        "vehicle": vehicle,
        "gfx_update_time": 0.1,
        "physics_update_time": 0.01,
        "is_visualised": False,
    }

    return (
        CallShape(
            "Camera",
            Camera,
            kwargs={
                **common,
                "resolution": (640, 480),
                "field_of_view_y": 70.0,
                "is_using_shared_memory": True,
                "is_streaming": True,
                "is_render_annotations": False,
                "is_render_depth": False,
                "is_visualised": False,
            },
        ),
        CallShape(
            "Lidar",
            Lidar,
            kwargs={
                **common,
                "is_using_shared_memory": True,
                "is_streaming": True,
                "is_visualised": False,
            },
        ),
        CallShape(
            "Radar",
            Radar,
            kwargs={**common, "is_streaming": True, "is_visualised": False},
        ),
        CallShape(
            "Ultrasonic",
            Ultrasonic,
            kwargs={**common, "is_streaming": True, "is_visualised": False},
        ),
        CallShape("GPS", GPS, kwargs={**timed, "pos": position}),
        CallShape(
            "AdvancedIMU",
            AdvancedIMU,
            kwargs={**timed, "pos": position, "dir": direction},
        ),
        CallShape("RoadsSensor", RoadsSensor, kwargs=timed),
        CallShape(
            "PowertrainSensor",
            PowertrainSensor,
            kwargs={key: value for key, value in timed.items() if key != "is_visualised"},
        ),
        CallShape("Electrics", Electrics),
        CallShape("Damage", Damage),
        CallShape("State", State),
    )


@pytest.mark.parametrize("shape", _sensor_constructor_shapes(), ids=lambda shape: shape.name)
def test_beamngpy_sensor_constructors_accept_adapter_call_shapes(shape: CallShape) -> None:
    """Sensor compatibility is checked without constructing engine-backed sensors."""

    inspect.signature(shape.target).bind(*shape.args, **shape.kwargs)


def _sensor_operation_shapes() -> Iterable[CallShape]:
    modern_sensors = (
        Camera,
        Lidar,
        Radar,
        Ultrasonic,
        GPS,
        AdvancedIMU,
        RoadsSensor,
        PowertrainSensor,
    )
    shapes = [
        CallShape(f"{sensor.__name__}.poll", sensor.poll, (object(),)) for sensor in modern_sensors
    ]
    shapes.extend(
        CallShape(f"{sensor.__name__}.remove", sensor.remove, (object(),))
        for sensor in modern_sensors
    )
    shapes.append(CallShape("Camera.stream", Camera.stream, (object(),)))
    return shapes


@pytest.mark.parametrize("shape", _sensor_operation_shapes(), ids=lambda shape: shape.name)
def test_beamngpy_sensor_methods_accept_adapter_call_shapes(shape: CallShape) -> None:
    """Every modern sensor operation used for polling and cleanup remains callable."""

    inspect.signature(shape.target).bind(*shape.args, **shape.kwargs)
