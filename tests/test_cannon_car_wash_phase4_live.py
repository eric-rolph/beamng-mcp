"""Live Phase 4 impact and telemetry gate for the Cannon Car Wash."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.test_cannon_car_wash_phase3_live import _run_cannon_car_wash_live_gate


@pytest.mark.beamng_live
@pytest.mark.asyncio
async def test_cannon_car_wash_phase4_impact_and_damage_telemetry(
    tmp_path: Path,
) -> None:
    await _run_cannon_car_wash_live_gate(tmp_path, phase=4)
