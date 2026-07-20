"""Regression tests for untrusted configuration and MCP request boundaries."""

from __future__ import annotations

import math

import pytest
from pydantic import ValidationError

from beamng_mcp.config import LuaSettings
from beamng_mcp.models import (
    MAX_SENSOR_PIXELS,
    MIN_SENSOR_UPDATE_SECONDS,
    AutonomyStart,
    MapObjectMutation,
    MapObjectPatch,
    ScenarioRef,
    ScenarioSelector,
    SensorSpec,
    VehicleAIConfig,
    VehicleSpawn,
    VehicleTeleport,
)


@pytest.mark.parametrize(
    ("url", "canonical"),
    [
        ("ws://127.0.0.1:1", "ws://127.0.0.1:1"),
        ("ws://localhost:8765/", "ws://localhost:8765"),
        ("ws://[::1]:65535", "ws://[::1]:65535"),
    ],
)
def test_lua_url_accepts_only_canonical_loopback_shapes(url: str, canonical: str) -> None:
    assert LuaSettings(url=url).url == canonical


@pytest.mark.parametrize(
    "url",
    [
        "ws://127.0.0.1:8765@evil.example:80",
        "ws://user@localhost:8765",
        "wss://localhost:8765",
        "http://localhost:8765",
        "ws://localhost",
        "ws://localhost:",
        "ws://localhost:0",
        "ws://localhost:65536",
        "ws://localhost:not-a-port",
        "ws://127.0.0.2:8765",
        "ws://evil.example:8765",
        "ws://localhost:8765/bridge",
        "ws://localhost:8765?token=secret",
        "ws://localhost:8765#fragment",
        " ws://localhost:8765",
    ],
)
def test_lua_url_rejects_non_loopback_or_ambiguous_urls(url: str) -> None:
    with pytest.raises(ValidationError):
        LuaSettings(url=url)


@pytest.mark.parametrize(
    "identifier",
    [
        ".",
        "..",
        "../west_coast_usa",
        "west..coast",
        "west/coast",
        r"west\coast",
        "/absolute",
        r"C:\absolute",
    ],
)
def test_scenario_ref_rejects_paths_and_dot_segments(identifier: str) -> None:
    with pytest.raises(ValidationError):
        ScenarioRef(level=identifier, name="mcp_test")
    with pytest.raises(ValidationError):
        ScenarioRef(level="west_coast_usa", name=identifier)


def test_scenario_ref_accepts_typical_beamng_identifiers() -> None:
    ref = ScenarioRef(level="west_coast_usa", name="mcp-test.v2")
    assert ref.level == "west_coast_usa"
    assert ref.name == "mcp-test.v2"


def test_scenario_selector_accepts_display_names_but_rejects_controls() -> None:
    selector = ScenarioSelector(
        level="gridmap_v2", name="A built-in scenario (delivery / training)"
    )
    assert selector.name == "A built-in scenario (delivery / training)"
    with pytest.raises(ValidationError):
        ScenarioSelector(level="gridmap_v2", name="unsafe\nname")


def test_vehicle_spawn_requires_an_explicit_world_position() -> None:
    with pytest.raises(ValidationError, match="position"):
        VehicleSpawn(vehicle_id="ego", model="etk800")


def test_vehicle_ai_uses_beamngpy_modes_and_matching_targets() -> None:
    assert VehicleAIConfig(vehicle_id="ego", mode="stopping").mode == "stopping"
    assert (
        VehicleAIConfig(vehicle_id="ego", mode="flee", target_vehicle_id="pursuer").mode == "flee"
    )
    assert VehicleAIConfig(vehicle_id="ego", mode="manual", target_waypoint="wp_1").mode == "manual"

    for invalid in (
        {"vehicle_id": "ego", "mode": "stop"},
        {"vehicle_id": "ego", "mode": "traffic", "target_vehicle_id": "other"},
        {"vehicle_id": "ego", "mode": "traffic", "target_waypoint": "wp_1"},
        {
            "vehicle_id": "ego",
            "mode": "manual",
            "target_vehicle_id": "other",
            "target_waypoint": "wp_1",
        },
    ):
        with pytest.raises(ValidationError):
            VehicleAIConfig.model_validate(invalid)


def test_native_autonomy_preserves_targeted_ai_modes_under_engine_lease() -> None:
    chase = AutonomyStart(
        vehicle_id="ego",
        mode="native-ai",
        ai_mode="chase",
        ai_target_vehicle_id="target",
        ai_aggression=0.8,
        ai_drive_in_lane=False,
    )
    manual = AutonomyStart(
        vehicle_id="ego",
        mode="native-ai",
        ai_mode="manual",
        ai_target_waypoint="wp_1",
    )
    assert chase.ai_target_vehicle_id == "target"
    assert manual.ai_target_waypoint == "wp_1"

    for invalid in (
        {"vehicle_id": "ego", "mode": "native-ai", "ai_mode": "chase"},
        {"vehicle_id": "ego", "mode": "native-ai", "ai_mode": "manual"},
        {
            "vehicle_id": "ego",
            "mode": "native-ai",
            "ai_mode": "traffic",
            "ai_target_vehicle_id": "target",
        },
    ):
        with pytest.raises(ValidationError):
            AutonomyStart.model_validate(invalid)


def test_map_object_models_match_lua_identifiers_and_classes() -> None:
    mutation = MapObjectMutation(
        name="_mcp-light.1",
        class_name="PointLight",
        fields={
            "color": (0.25, 0.5, 0.75, 1.0),
            "brightness": 3.5,
            "castShadows": True,
        },
    )
    assert mutation.fields["color"] == (0.25, 0.5, 0.75, 1.0)

    patch = MapObjectPatch(
        object_id="_mcp-light.1",
        new_name="renamed_light",
        fields={"color": (1, 0, 0), "enabled": False},
    )
    assert patch.new_name == "renamed_light"

    with pytest.raises(ValidationError):
        MapObjectMutation(name="sphere", class_name="SpawnSphere")


@pytest.mark.parametrize(
    "kwargs",
    [
        {"name": "1starts_with_digit", "class_name": "PointLight"},
        {"name": "a" * 97, "class_name": "PointLight"},
        {"name": "has/slash", "class_name": "PointLight"},
        {"name": "light", "class_name": "PointLight", "fields": {"color": (1.1, 0, 0)}},
        {"name": "light", "class_name": "PointLight", "fields": {"value": [1, 2]}},
    ],
)
def test_map_object_mutation_rejects_values_outside_typed_contract(
    kwargs: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        MapObjectMutation.model_validate(kwargs)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"object_id": 0},
        {"object_id": "1starts_with_digit"},
        {"object_id": "valid_name", "new_name": "bad/name"},
        {"object_id": "valid_name", "new_name": "a" * 97},
    ],
)
def test_map_object_patch_rejects_invalid_object_identifiers(kwargs: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        MapObjectPatch.model_validate(kwargs)


@pytest.mark.parametrize("non_finite", [math.nan, math.inf, -math.inf])
def test_strict_models_reject_non_finite_numbers_globally(non_finite: float) -> None:
    with pytest.raises(ValidationError):
        MapObjectMutation(
            name="light",
            class_name="PointLight",
            fields={"brightness": non_finite},
        )
    with pytest.raises(ValidationError):
        VehicleTeleport(vehicle_id="ego", position=(non_finite, 0, 0))


@pytest.mark.parametrize(
    "model",
    [
        VehicleSpawn(vehicle_id="ego", model="etk800", position=(0, 0, 0)).model_copy(
            update={"rotation": (0.0, 0.0, 0.0, 0.0)}
        ),
        VehicleTeleport(vehicle_id="ego", position=(0, 0, 0)).model_copy(
            update={"rotation": (0.0, 0.0, 0.0, 0.0)}
        ),
    ],
)
def test_vehicle_models_reject_degenerate_quaternions(model: object) -> None:
    with pytest.raises(ValidationError, match="quaternion must be nonzero"):
        type(model).model_validate(model.model_dump())


def test_geometry_inputs_are_bounded_and_scale_is_positive() -> None:
    with pytest.raises(ValidationError):
        VehicleTeleport(vehicle_id="ego", position=(1_000_001, 0, 0))
    with pytest.raises(ValidationError):
        VehicleSpawn(vehicle_id="ego", model="etk800", position=(0, 0, 0), rotation=(2, 0, 0, 1))
    with pytest.raises(ValidationError, match=r"greater than or equal to 0\.0001"):
        MapObjectMutation(name="box", class_name="TSStatic", scale=(0, 1, 1))
    with pytest.raises(ValidationError):
        MapObjectPatch(object_id="box", scale=(-1, 1, 1))


@pytest.mark.parametrize(
    "kwargs",
    [
        {"resolution": (2**31, 1080)},
        {"resolution": (0, 1080)},
        {"resolution": (8192, 8192)},
        {"resolution": (math.nan, 1080)},
        {"position": (math.nan, 0, 0)},
        {"update_time": 0.0},
        {"update_time": MIN_SENSOR_UPDATE_SECONDS / 2},
        {"direction": (0.0, 0.0, 0.0)},
    ],
)
def test_sensor_spec_rejects_unsafe_resource_and_geometry_requests(
    kwargs: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        SensorSpec.model_validate({"name": "camera", "sensor_type": "camera", **kwargs})


def test_sensor_spec_accepts_caps_at_the_boundary() -> None:
    spec = SensorSpec(
        name="camera",
        sensor_type="camera",
        resolution=(4096, MAX_SENSOR_PIXELS // 4096),
        update_time=MIN_SENSOR_UPDATE_SECONDS,
    )
    assert spec.resolution[0] * spec.resolution[1] == MAX_SENSOR_PIXELS
