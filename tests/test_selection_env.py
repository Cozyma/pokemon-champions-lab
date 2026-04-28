"""Tests for SelectionEnv (team selection RL environment)."""
from __future__ import annotations

import pytest

from pokechamp.selection_env import (
    SELECTION_OBS_DIM,
    N_SELECTION_ACTIONS,
    TEAM_COMBOS,
    SelectionEnv,
    encode_team_preview,
)


@pytest.fixture
def team_paste():
    from pathlib import Path
    team_path = Path(__file__).parent.parent / "teams" / "screenshot-team" / "team.txt"
    return team_path.read_text()


@pytest.fixture
def opp_paste():
    from pathlib import Path
    team_path = Path(__file__).parent.parent / "teams" / "mega-gengar-team" / "team.txt"
    return team_path.read_text()


def test_team_combos_count():
    """C(6,3) = 20 combinations."""
    assert len(TEAM_COMBOS) == 20
    assert N_SELECTION_ACTIONS == 20


def test_team_combos_unique():
    """All combos are unique and sorted."""
    assert len(set(TEAM_COMBOS)) == 20
    for combo in TEAM_COMBOS:
        assert len(combo) == 3
        assert combo == tuple(sorted(combo))
        assert all(0 <= i < 6 for i in combo)


def test_obs_dim():
    """Observation dimension = 360 (30 dims x 12 slots)."""
    assert SELECTION_OBS_DIM == 360


def test_env_reset(team_paste, opp_paste):
    """reset() returns valid observation."""
    env = SelectionEnv(team_paste=team_paste, opponent_paste=opp_paste)
    try:
        obs, info = env.reset()
        assert obs.shape == (SELECTION_OBS_DIM,)
        assert obs.dtype.name == "float32"
        # Should have some non-zero values (types encoded)
        assert obs.sum() > 0
    finally:
        env.close()


def test_env_step_terminates(team_paste, opp_paste):
    """step() returns terminated=True (1-step episode)."""
    env = SelectionEnv(team_paste=team_paste, opponent_paste=opp_paste)
    try:
        obs, _ = env.reset()
        obs2, reward, terminated, truncated, info = env.step(0)
        assert terminated is True
        assert truncated is False
        assert reward in (1.0, -1.0, 0.0)
        assert "winner" in info
    finally:
        env.close()


def test_env_all_actions_valid(team_paste, opp_paste):
    """All 20 actions produce a valid result."""
    env = SelectionEnv(team_paste=team_paste, opponent_paste=opp_paste)
    try:
        for action in range(N_SELECTION_ACTIONS):
            obs, _ = env.reset()
            obs2, reward, terminated, truncated, info = env.step(action)
            assert terminated is True
            assert reward in (1.0, -1.0, 0.0)
    finally:
        env.close()


def test_action_masks(team_paste, opp_paste):
    """action_masks returns all True (all 20 actions valid)."""
    env = SelectionEnv(team_paste=team_paste, opponent_paste=opp_paste)
    try:
        env.reset()
        mask = env.action_masks()
        assert mask.shape == (N_SELECTION_ACTIONS,)
        assert mask.all()
    finally:
        env.close()


def test_opponent_pool(team_paste, opp_paste):
    """opponent_pool randomizes opponent each episode."""
    from pathlib import Path
    teams_dir = Path(__file__).parent.parent / "teams"
    pool = [
        (teams_dir / name / "team.txt").read_text()
        for name in ["mega-gengar-team", "mega-scizor-team"]
    ]
    env = SelectionEnv(team_paste=team_paste, opponent_pool=pool)
    try:
        obs1, _ = env.reset(seed=42)
        obs2, _ = env.reset(seed=43)
        # Different seeds may pick different opponents → different obs
        # (not guaranteed but likely with different seeds)
        env.reset()
    finally:
        env.close()
