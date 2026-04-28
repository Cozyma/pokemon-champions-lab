"""Gymnasium environment for team selection (team preview phase).

The RL agent picks 3 pokemon from 6 at team preview, then the battle
plays out using heuristic AI. Reward = +1 win / -1 loss.

Each episode is a single step (contextual bandit):
  reset() → team preview observation
  step(action) → selection + full battle → reward

Usage:
    env = SelectionEnv(team_paste=MY_TEAM, opponent_pool=[OPP1, OPP2, ...])
    obs, info = env.reset()
    action = model.predict(obs)
    obs, reward, terminated, truncated, info = env.step(action)
    # terminated is always True (1-step episode)
"""
from __future__ import annotations

import itertools
import json
import subprocess

import gymnasium as gym
import numpy as np
from gymnasium import spaces

from pokechamp.ai_decision import _choose_action
from pokechamp.fast_battle import (
    SHOWDOWN_DIR,
    _find_winner,
    _parse_sideupdate_requests,
    _paste_to_packed,
    _read_until_idle,
)
from pokechamp import showdown_data
from pokechamp.fast_env import _encode_types_onehot, _species_types, encode_request

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# All C(6,3) = 20 team combinations (0-indexed)
TEAM_COMBOS = list(itertools.combinations(range(6), 3))
N_SELECTION_ACTIONS = len(TEAM_COMBOS)  # 20

# Observation: own 6 slots (6*30=180) + opponent 6 slots (6*30=180) = 360
N_TEAM_SLOTS = 6
DIMS_PER_SLOT = 30  # types(18) + stats(6) + role(3) + ability(3)
SELECTION_OBS_DIM = N_TEAM_SLOTS * DIMS_PER_SLOT * 2  # 360

# Abilities considered beneficial for setup / sweeping / walling
SETUP_ABILITIES = {
    "unaware", "multiscale", "disguise", "magicguard", "moldbreaker",
    "technician", "hugepower", "purepower", "speedboost", "protean",
    "libero", "adaptability", "shedskin", "naturalcure", "regenerator",
    "magicbounce", "shadowtag", "arenatrap", "stamina", "bulletproof",
}


# ---------------------------------------------------------------------------
# Observation encoding helpers
# ---------------------------------------------------------------------------

def _encode_species_full(species: str) -> list[float]:
    """Encode a species into a 30-dim feature vector.

    Layout (30 dims):
      [0:18]  type multi-hot
      [18:24] base stats (hp/atk/def/spa/spd/spe) each / 200.0
      [24:27] role indicators (physical_bias, special_bias, bulk_rating)
      [27:30] ability flags (contact_punish, type_immunity, setup_potential)
    """
    # --- Types (18 dims) ---
    types = _species_types(species) if species else []
    vec = list(_encode_types_onehot(types))

    # --- Base stats (6 dims) ---
    pokedex = showdown_data.load_pokedex()
    key = species.lower().replace(" ", "").replace("-", "") if species else ""
    entry = pokedex.get(key)
    raw_stats = entry.get("baseStats", {}) if entry else {}
    hp = raw_stats.get("hp", 0)
    atk = raw_stats.get("atk", 0)
    dfn = raw_stats.get("def", 0)
    spa = raw_stats.get("spa", 0)
    spd = raw_stats.get("spd", 0)
    spe = raw_stats.get("spe", 0)
    vec.extend([
        hp / 200.0,
        atk / 200.0,
        dfn / 200.0,
        spa / 200.0,
        spd / 200.0,
        spe / 200.0,
    ])

    # --- Role indicators (3 dims) ---
    physical_bias = max(-1.0, min(1.0, (atk - spa) / 200.0))
    special_bias = max(-1.0, min(1.0, (spa - atk) / 200.0))
    bulk_rating = (hp + dfn + spd) / 600.0
    vec.extend([physical_bias, special_bias, bulk_rating])

    # --- Ability flags (3 dims) ---
    abilities = showdown_data.get_species_abilities(species) if species else []
    has_contact = 0.0
    has_immunity = 0.0
    has_setup = 0.0
    for ab_id in abilities:
        if showdown_data.ability_has_contact_punish(ab_id):
            has_contact = 1.0
        if showdown_data.ability_grants_type_immunity(ab_id) is not None:
            has_immunity = 1.0
        if ab_id in SETUP_ABILITIES:
            has_setup = 1.0
    vec.extend([has_contact, has_immunity, has_setup])

    assert len(vec) == DIMS_PER_SLOT, f"Expected {DIMS_PER_SLOT}, got {len(vec)}"
    return vec


# ---------------------------------------------------------------------------
# Observation encoding for team preview
# ---------------------------------------------------------------------------

def encode_team_preview(
    request: dict,
    log_lines: list[str],
    player_id: str,
) -> np.ndarray:
    """Encode team preview state into observation vector.

    Args:
        request: Showdown request JSON with teamPreview=true
        log_lines: Battle log including |poke| lines
        player_id: "p1" or "p2"

    Returns:
        Float32 array of shape (SELECTION_OBS_DIM,)
    """
    obs: list[float] = []

    # --- Own team (from request JSON) ---
    team = request.get("side", {}).get("pokemon", [])
    for i in range(N_TEAM_SLOTS):
        if i < len(team):
            mon = team[i]
            # Extract species from ident: "p1: Garchomp" -> "Garchomp"
            ident = mon.get("ident", "")
            species = ident.split(": ", 1)[-1] if ": " in ident else ""
            obs.extend(_encode_species_full(species))
        else:
            obs.extend([0.0] * DIMS_PER_SLOT)

    # --- Opponent team (from |poke| lines) ---
    opp_id = "p2" if player_id == "p1" else "p1"
    opp_species_list: list[str] = []
    for line in log_lines:
        if f"|poke|{opp_id}|" in line:
            parts = line.split("|")
            if len(parts) >= 4:
                species_part = parts[3]
                species = species_part.split(",")[0].strip()
                opp_species_list.append(species)

    for i in range(N_TEAM_SLOTS):
        if i < len(opp_species_list):
            obs.extend(_encode_species_full(opp_species_list[i]))
        else:
            obs.extend([0.0] * DIMS_PER_SLOT)

    assert len(obs) == SELECTION_OBS_DIM, f"Expected {SELECTION_OBS_DIM}, got {len(obs)}"
    return np.array(obs, dtype=np.float32)


# ---------------------------------------------------------------------------
# SelectionEnv
# ---------------------------------------------------------------------------

class SelectionEnv(gym.Env):
    """Team selection environment (1-step contextual bandit)."""

    metadata = {"render_modes": []}

    def __init__(
        self,
        team_paste: str,
        opponent_paste: str | None = None,
        opponent_pool: list[str] | None = None,
        team_pool: list[str] | None = None,
        format_id: str = "gen9championsbssregma",
        battle_model=None,
        p2_selection_model=None,
        p2_battle_model=None,
    ):
        super().__init__()

        self.team_paste = team_paste
        self._team_pool = team_pool  # p1 team randomization
        self.opponent_paste = opponent_paste or team_paste
        self._opponent_pool = opponent_pool or (
            [opponent_paste] if opponent_paste else [team_paste]
        )
        self.format_id = format_id
        self._battle_model = battle_model  # Optional: MaskablePPO for p1 battle decisions
        self._p2_selection_model = p2_selection_model  # Optional: MaskablePPO for p2 selection
        self._p2_battle_model = p2_battle_model  # Optional: MaskablePPO for p2 battle

        self.observation_space = spaces.Box(
            low=-1.0, high=1.0, shape=(SELECTION_OBS_DIM,), dtype=np.float32,
        )
        self.action_space = spaces.Discrete(N_SELECTION_ACTIONS)

        self._proc: subprocess.Popen | None = None
        self._log_lines: list[str] = []
        self._p1_request: dict = {}
        self._p2_request: dict = {}

    def _send(self, line: str) -> None:
        if self._proc and self._proc.stdin:
            self._proc.stdin.write((line + "\n").encode())
            self._proc.stdin.flush()

    def _read_output(self, first: bool = False) -> list[str]:
        if not self._proc:
            return []
        if first:
            return _read_until_idle(self._proc, first_line_timeout=5.0, idle_timeout=0.1)
        return _read_until_idle(self._proc, first_line_timeout=3.0, idle_timeout=0.05)

    def _kill_proc(self) -> None:
        if self._proc:
            try:
                self._proc.stdin.close()
            except Exception:
                pass
            try:
                self._proc.kill()
                self._proc.wait(timeout=2.0)
            except Exception:
                pass
            self._proc = None

    def reset(self, *, seed=None, options=None):
        super().reset(seed=seed)

        # Randomize p1 team from pool
        if self._team_pool and len(self._team_pool) > 1:
            idx = int(self.np_random.integers(0, len(self._team_pool)))
            self.team_paste = self._team_pool[idx]

        # Randomize opponent
        if len(self._opponent_pool) > 1:
            idx = int(self.np_random.integers(0, len(self._opponent_pool)))
            self.opponent_paste = self._opponent_pool[idx]

        self._kill_proc()

        # Start battle
        packed_a = _paste_to_packed(self.team_paste)
        packed_b = _paste_to_packed(self.opponent_paste)

        seed_list = [int(self.np_random.integers(0, 65536)) for _ in range(4)]
        seed_part = f',"seed":{json.dumps(seed_list)}'

        self._proc = subprocess.Popen(
            ["node", "pokemon-showdown", "simulate-battle"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=0,
            cwd=str(SHOWDOWN_DIR),
        )

        self._send(f'>start {{"formatid":"{self.format_id}"{seed_part}}}')
        self._send(f'>player p1 {json.dumps({"name": "p1", "team": packed_a})}')
        self._send(f'>player p2 {json.dumps({"name": "p2", "team": packed_b})}')

        self._log_lines = []

        # Read initial output (includes |poke| lines and team preview requests)
        output = self._read_output(first=True)
        self._log_lines.extend(output)

        # Parse team preview requests
        requests = _parse_sideupdate_requests(output)
        self._p1_request = requests.get("p1", {})
        self._p2_request = requests.get("p2", {})

        # Encode observation from team preview
        if self._p1_request.get("teamPreview"):
            obs = encode_team_preview(self._p1_request, self._log_lines, "p1")
        else:
            obs = np.zeros(SELECTION_OBS_DIM, dtype=np.float32)

        return obs, {}

    def step(self, action: int):
        combo = TEAM_COMBOS[action]
        team_cmd = "team " + "".join(str(i + 1) for i in combo)

        # Send p1 selection
        try:
            self._send(f">p1 {team_cmd}")
        except (BrokenPipeError, OSError):
            return np.zeros(SELECTION_OBS_DIM, dtype=np.float32), -1.0, True, False, {"winner": "p2"}

        # Send p2 selection (RL model or heuristic)
        if self._p2_request.get("teamPreview"):
            if self._p2_selection_model is not None:
                p2_obs = encode_team_preview(self._p2_request, self._log_lines, "p2")
                p2_sel_action, _ = self._p2_selection_model.predict(
                    p2_obs, deterministic=True,
                )
                p2_combo = TEAM_COMBOS[int(p2_sel_action)]
                p2_action = "team " + "".join(str(i + 1) for i in p2_combo)
            else:
                p2_action = _choose_action(self._p2_request, self._log_lines, "p2")
            try:
                self._send(f">p2 {p2_action}")
            except (BrokenPipeError, OSError):
                pass

        # Play out the battle using heuristic for both sides
        winner = self._play_battle()

        reward = 1.0 if winner == "p1" else (-1.0 if winner == "p2" else 0.0)
        obs = np.zeros(SELECTION_OBS_DIM, dtype=np.float32)

        return obs, reward, True, False, {"winner": winner}

    def _play_battle(self) -> str | None:
        """Play the battle to completion.

        p1: uses battle_model if available, else heuristic.
        p2: uses p2_battle_model if available, else heuristic.
        """
        from pokechamp.fast_env import N_MOVES, action_to_command

        max_turns = 200
        winner: str | None = None

        for _ in range(max_turns):
            output = self._read_output()
            if not output:
                if self._proc and self._proc.poll() is not None:
                    break
                continue

            self._log_lines.extend(output)

            # Check for winner
            win_result = _find_winner(output)
            if win_result is not None:
                winner = win_result if win_result is not False else None
                break

            # Parse and respond to requests
            requests = _parse_sideupdate_requests(output)
            for pid, req in requests.items():
                if req.get("wait") or req.get("teamPreview"):
                    continue

                # Determine which model to use for this player
                model = None
                if pid == "p1" and self._battle_model is not None:
                    model = self._battle_model
                elif pid == "p2" and self._p2_battle_model is not None:
                    model = self._p2_battle_model

                if model is not None:
                    obs, mask = encode_request(req, self._log_lines, pid)
                    action, _ = model.predict(
                        obs, deterministic=True, action_masks=mask.astype(bool),
                    )
                    action = int(action)
                    active_req = req.get("active", [{}])
                    can_mega = (active_req[0] if active_req else {}).get("canMegaEvo", False)
                    cmd = action_to_command(action, req, mega=can_mega and action < N_MOVES)
                else:
                    cmd = _choose_action(req, self._log_lines, pid)

                try:
                    self._send(f">{pid} {cmd}")
                except (BrokenPipeError, OSError):
                    return "p2" if pid == "p1" else "p1"

        return winner

    def action_masks(self) -> np.ndarray:
        """All 20 selections are always valid."""
        return np.ones(N_SELECTION_ACTIONS, dtype=bool)

    def close(self) -> None:
        self._kill_proc()
        super().close()
