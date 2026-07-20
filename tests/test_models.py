import pytest
from pydantic import ValidationError

from beamng_mcp.models import ControlInput, Pose, RoadSpec, ScenarioSpec, VehicleSpec


def test_scenario_accepts_vehicle_and_road() -> None:
    scenario = ScenarioSpec(
        level="west_coast_usa",
        name="mcp_demo",
        vehicles=[VehicleSpec(vehicle_id="ego", pose=Pose(pos=(0, 0, 1)))],
        roads=[RoadSpec(material="track_editor_A_center", nodes=[(0, 0, 0, 8), (20, 0, 0, 8)])],
    )
    assert scenario.vehicles[0].vehicle_id == "ego"


def test_controls_are_bounded() -> None:
    with pytest.raises(ValidationError):
        ControlInput(vehicle_id="ego", throttle=1.1)

