"""Fast Gymnasium environment using Showdown subprocess.

No server needed. ~1s/battle vs poke-env's ~15s/battle.
RL agent controls p1, heuristic AI controls p2.

Usage:
    from pokechamp.fast_env import FastBattleEnv

    env = FastBattleEnv(team_paste=TEAM_STR, opponent_paste=OPP_STR)
    obs, info = env.reset()
    done = False
    while not done:
        action = env.action_space.sample()
        obs, reward, terminated, truncated, info = env.step(action)
        done = terminated or truncated
    env.close()
"""
from __future__ import annotations

import json
import re
import subprocess

import gymnasium as gym
import numpy as np
from gymnasium import spaces

from pokechamp import showdown_data
from pokechamp.ai_decision import _choose_action
from pokechamp.ai_scoring import _calc_type_effectiveness
from pokechamp.fast_battle import (
    SHOWDOWN_DIR,
    _find_winner,
    _parse_sideupdate_requests,
    _paste_to_packed,
    _read_until_idle,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

N_MOVES = 4
N_SWITCHES = 5
N_ACTIONS = N_MOVES + N_SWITCHES  # 9

ALL_TYPES = [
    "normal", "fire", "water", "electric", "grass", "ice",
    "fighting", "poison", "ground", "flying", "psychic", "bug",
    "rock", "ghost", "dragon", "dark", "steel", "fairy",
]
TYPE_TO_IDX = {t: i for i, t in enumerate(ALL_TYPES)}
N_TYPES = len(ALL_TYPES)

# Observation dimensions:
# active: types(18) + stats(6) + hp(1) + status(1) = 26
# moves: 4 * (bp + type_eff + stab + priority + category) = 20
# opponent active: types(18) + hp(1) + status(1) = 20
# team hp: 3
# opp team hp: 3
# weather: 8
# mega flags: 2
# force_switch: 1
# trapped: 1
# action mask: 9
# Total: 93
OBS_DIM = 93


# ---------------------------------------------------------------------------
# Observation encoding from request JSON
# ---------------------------------------------------------------------------


def _species_types(species: str) -> list[str]:
    """Get types for a species from pokedex."""
    pokedex = showdown_data.load_pokedex()
    key = species.lower().replace(" ", "").replace("-", "")
    entry = pokedex.get(key)
    if entry:
        return [t.lower() for t in entry.get("types", [])]
    return []


def _encode_types_onehot(types: list[str]) -> list[float]:
    """Encode types as 18-dim multi-hot."""
    vec = [0.0] * N_TYPES
    for t in types:
        idx = TYPE_TO_IDX.get(t.lower())
        if idx is not None:
            vec[idx] = 1.0
    return vec


def _parse_condition(condition: str) -> tuple[float, str]:
    """Parse condition string to (hp_fraction, status)."""
    if condition == "0 fnt":
        return 0.0, "fnt"
    parts = condition.split()
    hp_str = parts[0]
    status = parts[1] if len(parts) > 1 else ""
    m = re.match(r"(\d+)/(\d+)", hp_str)
    if m:
        return int(m.group(1)) / int(m.group(2)), status
    return 1.0, status


def _encode_status(status: str) -> float:
    """Encode status as 0-1."""
    status_map = {"": 0.0, "brn": 0.17, "frz": 0.33, "par": 0.5, "psn": 0.67, "tox": 0.67, "slp": 0.83, "fnt": 1.0}
    return status_map.get(status, 0.0)


def encode_request(
    request: dict,
    log_lines: list[str],
    player_id: str,
) -> tuple[np.ndarray, np.ndarray]:
    """Encode a Showdown request JSON into observation and action mask.

    Returns (obs, action_mask) where obs is OBS_DIM float32 and
    action_mask is N_ACTIONS float32 (1=valid, 0=invalid).
    """
    obs: list[float] = []
    mask = np.zeros(N_ACTIONS, dtype=np.float32)

    active_list = request.get("active", [{}])
    active_req = active_list[0] if active_list else {}
    team = request.get("side", {}).get("pokemon", [])
    active_mon = next((p for p in team if p.get("active")), {})

    is_force_switch = bool(request.get("forceSwitch"))
    is_trapped = bool(active_req.get("trapped"))

    # --- Active pokemon (26) ---
    species = active_mon.get("ident", "").split(": ", 1)[-1] if active_mon else ""
    details = active_mon.get("details", "")
    # Use details for mega form detection
    base_species = details.split(",")[0].strip() if details else species
    types = _species_types(base_species)
    obs.extend(_encode_types_onehot(types))  # 18

    stats = active_mon.get("stats", {})
    obs.append(stats.get("atk", 100) / 200.0)
    obs.append(stats.get("def", 100) / 200.0)
    obs.append(stats.get("spa", 100) / 200.0)
    obs.append(stats.get("spd", 100) / 200.0)
    obs.append(stats.get("spe", 100) / 200.0)
    obs.append(max(stats.get("atk", 0), stats.get("spa", 0)) / 200.0)  # best offensive

    condition = active_mon.get("condition", "100/100")
    hp_frac, status = _parse_condition(condition)
    obs.append(hp_frac)
    obs.append(_encode_status(status))

    # --- Moves (20) ---
    moves = active_req.get("moves", [])
    opp_id = "p2" if player_id == "p1" else "p1"
    # Parse opponent species from log
    opp_species = ""
    for line in reversed(log_lines):
        if f"|switch|{opp_id}a: " in line or f"|drag|{opp_id}a: " in line:
            parts = line.split("|")
            if len(parts) > 3:
                opp_species = parts[3].split(",")[0].strip()
            break
    opp_types = _species_types(opp_species)

    for i in range(N_MOVES):
        if i < len(moves) and not moves[i].get("disabled") and not is_force_switch:
            m = moves[i]
            move_id = m.get("id", "")
            sd = showdown_data.get_move(move_id)
            bp = (sd.get("basePower", 0) if sd else 0) / 250.0
            move_type = (sd.get("type", "") if sd else "").lower()
            eff = _calc_type_effectiveness(move_type, opp_types) / 4.0 if opp_types else 0.25
            stab = 1.0 if move_type in types else 0.0
            pri = max(min(sd.get("priority", 0) if sd else 0, 5), -5) / 5.0
            cat_map = {"Physical": 1.0, "Special": 0.5, "Status": 0.0}
            cat = cat_map.get(sd.get("category", "") if sd else "", 0.0)
            obs.extend([bp, eff, stab, pri, cat])
            mask[i] = 1.0
        else:
            obs.extend([0.0] * 5)

    # --- Opponent active (20) ---
    obs.extend(_encode_types_onehot(opp_types))  # 18
    # Opponent HP from log
    opp_hp = 1.0
    for line in reversed(log_lines):
        if f"|-damage|{opp_id}a: " in line or f"|-heal|{opp_id}a: " in line:
            parts = line.split("|")
            if len(parts) > 3:
                hp_str = parts[3].strip().split()[0]
                hp_m = re.match(r"(\d+)/(\d+)", hp_str)
                if hp_m:
                    opp_hp = int(hp_m.group(1)) / int(hp_m.group(2))
                elif "fnt" in hp_str:
                    opp_hp = 0.0
            break
    obs.append(opp_hp)
    obs.append(0.0)  # opponent status (unknown from log, placeholder)

    # --- Team HP (3) ---
    for i in range(3):
        if i < len(team):
            hp_f, _ = _parse_condition(team[i].get("condition", "100/100"))
            obs.append(hp_f)
        else:
            obs.append(0.0)

    # --- Opponent team HP (3) - from log ---
    opp_fainted = 0
    for line in log_lines:
        if f"|faint|{opp_id}a:" in line:
            opp_fainted += 1
    opp_alive = max(3 - opp_fainted, 0)
    for i in range(3):
        obs.append(1.0 if i < opp_alive else 0.0)  # rough estimate

    # --- Weather (8) ---
    weather_types = ["sunnyday", "raindance", "sandstorm", "hail", "snowscape",
                     "desolateland", "primordialsea", "deltastream"]
    current_weather = ""
    for line in log_lines:
        wm = re.match(r"\|-weather\|(\w+)", line)
        if wm:
            w = wm.group(1).lower()
            current_weather = "" if w == "none" else w
    for w in weather_types:
        obs.append(1.0 if current_weather == w else 0.0)

    # --- Mega flags (2) ---
    can_mega = bool(active_req.get("canMegaEvo"))
    used_mega = "Mega" in details or "-Mega" in details
    obs.append(1.0 if can_mega else 0.0)
    obs.append(1.0 if used_mega else 0.0)

    # --- Force switch (1) ---
    obs.append(1.0 if is_force_switch else 0.0)

    # --- Trapped (1) ---
    obs.append(1.0 if is_trapped else 0.0)

    # --- Switch mask ---
    if is_force_switch or (not is_trapped):
        switch_candidates = [
            p for p in team
            if not p.get("active") and p.get("condition", "") != "0 fnt"
        ]
        for i in range(min(len(switch_candidates), N_SWITCHES)):
            mask[N_MOVES + i] = 1.0

    # --- Action mask (9) ---
    obs.extend(mask.tolist())

    arr = np.array(obs, dtype=np.float32)
    assert len(arr) == OBS_DIM, f"OBS_DIM mismatch: {len(arr)} != {OBS_DIM}"
    return arr, mask


# ---------------------------------------------------------------------------
# Action to Showdown command
# ---------------------------------------------------------------------------


def action_to_command(
    action: int,
    request: dict,
    mega: bool = False,
) -> str:
    """Convert gym action index to Showdown command string."""
    if action < N_MOVES:
        mega_str = " mega" if mega else ""
        return f"move {action + 1}{mega_str}"
    else:
        switch_idx = action - N_MOVES
        team = request.get("side", {}).get("pokemon", [])
        candidates = [
            (i, p) for i, p in enumerate(team)
            if not p.get("active") and p.get("condition", "") != "0 fnt"
        ]
        if switch_idx < len(candidates):
            return f"switch {candidates[switch_idx][0] + 1}"
        # Fallback
        if candidates:
            return f"switch {candidates[0][0] + 1}"
        return "move 1"


# ---------------------------------------------------------------------------
# Gymnasium Environment
# ---------------------------------------------------------------------------


class FastBattleEnv(gym.Env):
    """Pokemon Champions battle environment using Showdown subprocess.

    p1 = RL agent, p2 = heuristic AI.
    """

    metadata = {"render_modes": []}

    def __init__(
        self,
        team_paste: str,
        opponent_paste: str,
        format_id: str = "gen9championsbssregma",
    ):
        super().__init__()
        self.team_paste = team_paste
        self.opponent_paste = opponent_paste
        self.format_id = format_id

        self.observation_space = spaces.Box(
            low=0.0, high=1.0, shape=(OBS_DIM,), dtype=np.float32,
        )
        self.action_space = spaces.Discrete(N_ACTIONS)

        self._proc: subprocess.Popen | None = None
        self._log_lines: list[str] = []
        self._current_request: dict = {}
        self._turn = 0
        self._prev_obs: np.ndarray | None = None
        self._prev_team_hp: float = 0.0
        self._prev_opp_fainted: int = 0

    def _send(self, line: str) -> None:
        if self._proc and self._proc.stdin:
            self._proc.stdin.write((line + "\n").encode())
            self._proc.stdin.flush()

    def _read_output(self, first: bool = False) -> list[str]:
        if not self._proc:
            return []
        if first:
            return _read_until_idle(self._proc, first_line_timeout=5.0, idle_timeout=0.1)
        return _read_until_idle(self._proc, first_line_timeout=1.0, idle_timeout=0.03)

    def reset(self, *, seed=None, options=None):
        super().reset(seed=seed)

        # Kill previous process cleanly
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

        # Start new battle
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
        self._turn = 0
        self._prev_team_hp = 3.0
        self._prev_opp_fainted = 0

        # Read initial output and get first request
        output = self._read_output(first=True)
        self._log_lines.extend(output)

        # Handle team preview for both sides
        requests = _parse_sideupdate_requests(output)

        # p1 team preview: use heuristic selection
        if "p1" in requests and requests["p1"].get("teamPreview"):
            p1_action = _choose_action(requests["p1"], self._log_lines, "p1")
            self._send(f">p1 {p1_action}")

        # p2 team preview
        if "p2" in requests and requests["p2"].get("teamPreview"):
            p2_action = _choose_action(requests["p2"], self._log_lines, "p2")
            self._send(f">p2 {p2_action}")

        # Read until we get p1's first battle request
        obs = self._advance_to_p1_request()
        self._prev_obs = obs
        return obs, {"turn": self._turn}

    def _advance_to_p1_request(self) -> np.ndarray:
        """Read output and respond as p2 until p1 has a non-wait request."""
        max_iters = 20
        empty_reads = 0
        for _ in range(max_iters):
            output = self._read_output()
            if not output:
                empty_reads += 1
                if self._proc and self._proc.poll() is not None:
                    break
                if empty_reads >= 3:
                    break  # avoid long hangs
                continue
            empty_reads = 0

            self._log_lines.extend(output)

            # Check for trapped errors
            for line in output:
                if "|error|" in line and "trapped" in line.lower():
                    self._log_lines.append("|trapped|")

            # Check for game end
            win = _find_winner(output)
            if win is not None:
                break

            # Count turns
            for line in output:
                m = re.match(r"\|turn\|(\d+)", line)
                if m:
                    self._turn = int(m.group(1))

            # Parse requests
            requests = _parse_sideupdate_requests(output)

            # Respond as p2 (heuristic)
            if "p2" in requests and not requests["p2"].get("wait"):
                p2_action = _choose_action(requests["p2"], self._log_lines, "p2")
                self._send(f">p2 {p2_action}")

            # Return p1's request if available
            if "p1" in requests and not requests["p1"].get("wait"):
                self._current_request = requests["p1"]
                obs, _ = encode_request(
                    self._current_request, self._log_lines, "p1",
                )
                return obs

        # Fallback: return zero obs (game ended)
        return np.zeros(OBS_DIM, dtype=np.float32)

    def step(self, action: int):
        request = self._current_request

        # Convert action to command
        # Check if mega should be applied (use heuristic rule)
        active_req = request.get("active", [{}])
        can_mega = (active_req[0] if active_req else {}).get("canMegaEvo", False)
        mega = can_mega and action < N_MOVES  # always mega when attacking

        cmd = action_to_command(action, request, mega=mega)
        self._send(f">p1 {cmd}")

        # Advance to next p1 request (p2 plays automatically)
        obs = self._advance_to_p1_request()

        # Check if game ended
        terminated = False
        winner = _find_winner(self._log_lines[-50:])  # check recent lines
        if winner is not None:
            terminated = True

        truncated = self._turn >= 200

        # Compute reward
        reward = self._compute_reward(winner)

        self._prev_obs = obs
        return obs, reward, terminated, truncated, {"turn": self._turn, "winner": winner}

    def _compute_reward(self, winner) -> float:
        """Compute step reward."""
        if winner is not None:
            if winner == "p1":
                return 1.0
            elif winner == "p2":
                return -1.0
            return 0.0  # tie

        # Intermediate rewards: HP changes and KOs
        reward = 0.0
        team = self._current_request.get("side", {}).get("pokemon", [])

        # Team HP sum
        team_hp = sum(
            _parse_condition(p.get("condition", "0 fnt"))[0]
            for p in team
        )
        reward += (team_hp - self._prev_team_hp) * 0.1
        self._prev_team_hp = team_hp

        # Opponent fainted count
        opp_fainted = sum(1 for line in self._log_lines if "|faint|p2a:" in line)
        new_kos = opp_fainted - self._prev_opp_fainted
        reward += new_kos * 0.3
        self._prev_opp_fainted = opp_fainted

        return reward

    def close(self):
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

    def get_action_mask(self) -> np.ndarray:
        """Return current valid action mask."""
        if not self._current_request:
            return np.ones(N_ACTIONS, dtype=np.float32)
        _, mask = encode_request(self._current_request, self._log_lines, "p1")
        return mask
