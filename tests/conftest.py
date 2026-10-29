"""Fixtures compartidas: la misión completa tarda ~2,5 min, así que se construye una sola vez."""

import pytest

from artemis_sim.export import MissionTrajectory
from artemis_sim.mission import MissionSummaryPhase5, build_mission_phases_1_to_5


@pytest.fixture(scope="session")
def mission5() -> tuple[MissionTrajectory, MissionSummaryPhase5]:
    return build_mission_phases_1_to_5()
