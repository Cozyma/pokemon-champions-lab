"""Fast Showdown battle runner via subprocess.

Runs battles using node pokemon-showdown simulate-battle directly,
with an embedded heuristic AI for move selection.
No server needed, no WebSocket overhead. ~0.8s per battle.

AI logic is split across:
- ai_scoring.py: move scoring, stat estimation, matchup evaluation
- log_parser.py: battle log parsing (opponent info, boosts, weather, etc.)
- ai_decision.py: action selection, switching, mega evolution, team selection
"""
from __future__ import annotations

import json
import re
import select
import subprocess
import time
from pathlib import Path

from pokechamp.ai_decision import _choose_action  # noqa: F401

SHOWDOWN_DIR = Path(__file__).resolve().parent.parent.parent / "engines" / "showdown"

# ---------------------------------------------------------------------------
# Paste → Packed format converter
# ---------------------------------------------------------------------------

# EV stat name aliases used in showdown paste (e.g. "Atk", "SpA", "Spe")
_EV_STAT_MAP: dict[str, str] = {
    "hp": "hp",
    "atk": "atk",
    "def": "def",
    "spa": "spa",
    "spd": "spd",
    "spe": "spe",
}


def _paste_to_packed(paste: str) -> str:
    """Convert Showdown paste format to packed team format.

    Packed format (per pokemon, joined by ']'):
    ``Species||Item|Ability|Move1,Move2,Move3,Move4|Nature|H,A,D,SA,SD,S EVs|Gender|IVs|Shiny|Level||``
    """
    pokemon_blocks = re.split(r"\n\n+", paste.strip())
    packed_parts: list[str] = []

    for block in pokemon_blocks:
        lines = [ln.strip() for ln in block.strip().splitlines() if ln.strip()]
        if not lines:
            continue

        # First line: "Species @ Item" or just "Species"
        first_line = lines[0]
        if " @ " in first_line:
            species_raw, item = first_line.split(" @ ", 1)
        else:
            species_raw = first_line
            item = ""
        species = species_raw.strip()

        ability = ""
        nature = ""
        evs: dict[str, int] = {"hp": 0, "atk": 0, "def": 0, "spa": 0, "spd": 0, "spe": 0}
        ivs: dict[str, int] = {}
        moves: list[str] = []
        shiny = ""
        level = "50"
        gender = ""

        for line in lines[1:]:
            if line.startswith("Ability: "):
                ability = line[9:].strip()
            elif line.startswith("EVs: "):
                ev_str = line[5:]
                for part in ev_str.split(" / "):
                    part = part.strip()
                    m = re.match(r"(\d+)\s+(\S+)", part)
                    if m:
                        val, stat_key = int(m.group(1)), m.group(2).lower()
                        mapped = _EV_STAT_MAP.get(stat_key)
                        if mapped:
                            evs[mapped] = val
            elif line.startswith("IVs: "):
                iv_str = line[5:]
                for part in iv_str.split(" / "):
                    part = part.strip()
                    m = re.match(r"(\d+)\s+(\S+)", part)
                    if m:
                        val, stat_key = int(m.group(1)), m.group(2).lower()
                        mapped = _EV_STAT_MAP.get(stat_key)
                        if mapped:
                            ivs[mapped] = val
            elif line.endswith(" Nature"):
                nature = line.replace(" Nature", "").strip()
            elif line.startswith("- "):
                moves.append(line[2:].strip())
            elif line.startswith("Shiny: Yes"):
                shiny = "S"
            elif line.startswith("Level: "):
                level = line[7:].strip()
            elif line == "M" or line == "F":
                gender = line

        ev_str = ",".join(
            str(evs.get(k, 0))
            for k in ("hp", "atk", "def", "spa", "spd", "spe")
        )
        iv_str = ""
        if ivs:
            iv_str = ",".join(
                str(ivs.get(k, 31))
                for k in ("hp", "atk", "def", "spa", "spd", "spe")
            )

        moves_str = ",".join(moves)

        # Packed: Species||Item|Ability|Moves|Nature|EVs|Gender|IVs|Shiny|Level||
        packed = f"{species}||{item}|{ability}|{moves_str}|{nature}|{ev_str}|{gender}|{iv_str}|{shiny}|{level}||"
        packed_parts.append(packed)

    return "]".join(packed_parts)


# ---------------------------------------------------------------------------
# Subprocess battle runner
# ---------------------------------------------------------------------------


def _read_chunk(proc: subprocess.Popen, timeout: float) -> bytes:
    """Read all available bytes from proc.stdout within timeout seconds.

    Once data starts arriving, uses a short 20ms idle window to collect
    all data from the same batch.
    """
    buf = b""
    deadline = time.monotonic() + timeout
    idle_extend = 0.02  # 20ms idle window after each chunk
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        ready, _, _ = select.select([proc.stdout], [], [], min(remaining, idle_extend))
        if not ready:
            break
        chunk = proc.stdout.read(65536)
        if not chunk:
            break
        buf += chunk
        deadline = max(deadline, time.monotonic() + idle_extend)
    return buf


def _read_until_idle(
    proc: subprocess.Popen,
    first_line_timeout: float = 5.0,
    idle_timeout: float = 0.3,
) -> list[str]:
    """Read lines until no new data arrives for idle_timeout seconds.

    Waits up to first_line_timeout for the very first byte (node startup),
    then keeps reading until quiet for idle_timeout seconds.

    Uses unbuffered binary reads to avoid Python IO layer buffering.
    """
    # Wait for first byte with generous timeout (Node.js startup ~0.7-1s)
    ready, _, _ = select.select([proc.stdout], [], [], first_line_timeout)
    if not ready:
        return []

    # Read all available data
    buf = _read_chunk(proc, idle_timeout)
    if not buf:
        return []

    return buf.decode("utf-8", errors="replace").splitlines()


def _parse_sideupdate_requests(lines: list[str]) -> dict[str, dict]:
    """Parse sideupdate blocks and return {player_id: request_json}."""
    requests: dict[str, dict] = {}
    i = 0
    while i < len(lines):
        if lines[i] == "sideupdate":
            # Next line is player id (p1 or p2)
            if i + 1 < len(lines):
                player_id = lines[i + 1].strip()
                # Next non-empty line should be the |request| line
                j = i + 2
                while j < len(lines) and lines[j] == "":
                    j += 1
                if j < len(lines) and lines[j].startswith("|request|"):
                    json_str = lines[j][len("|request|"):]
                    try:
                        requests[player_id] = json.loads(json_str)
                    except json.JSONDecodeError:
                        pass
                    i = j + 1
                    continue
        i += 1
    return requests


def _find_winner(lines: list[str]) -> str | None | bool:
    """Return 'p1'/'p2' if a winner is found, False for tie, None if not found."""
    for line in lines:
        m = re.search(r"\|win\|(.+)", line)
        if m:
            name = m.group(1).strip()
            return "p1" if name == "p1" else "p2"
        if line.strip() == "|tie|":
            return False  # tie sentinel
    return None


def _count_remaining(log_lines: list[str], player_id: str) -> int:
    """Count remaining (non-fainted) pokemon for a player from log."""
    fainted: set[str] = set()
    seen: set[str] = set()

    for line in log_lines:
        m = re.search(rf"\|(?:switch|drag)\|{player_id}a: ([^|]+)\|", line)
        if m:
            seen.add(m.group(1).strip())
        m = re.search(rf"\|faint\|{player_id}a: (.+)", line)
        if m:
            fainted.add(m.group(1).strip())

    return max(len(seen) - len(fainted), 0)


def run_battle(
    team_a_paste: str,
    team_b_paste: str,
    format_id: str = "gen9championsbssregma",
    seed: list[int] | None = None,
    return_log: bool = False,
) -> dict:
    """Run a single battle via Showdown subprocess.

    Both sides use the embedded heuristic AI for move selection.
    Teams should be in Showdown paste format (will be converted to packed).

    Returns:
        {
            "winner": "p1" | "p2" | None,
            "turns": int,
            "p1_remaining": int,
            "p2_remaining": int,
        }
    """
    packed_a = _paste_to_packed(team_a_paste)
    packed_b = _paste_to_packed(team_b_paste)

    seed_part = f',"seed":{json.dumps(seed)}' if seed else ""
    start_msg = f'>start {{"formatid":"{format_id}"{seed_part}}}'
    p1_msg = f'>player p1 {json.dumps({"name": "p1", "team": packed_a})}'
    p2_msg = f'>player p2 {json.dumps({"name": "p2", "team": packed_b})}'

    proc = subprocess.Popen(
        ["node", "pokemon-showdown", "simulate-battle"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        bufsize=0,  # unbuffered binary mode — avoids Python IO layer buffering
        cwd=str(SHOWDOWN_DIR),
    )

    def send(line: str) -> None:
        proc.stdin.write((line + "\n").encode())
        proc.stdin.flush()

    send(start_msg)
    send(p1_msg)
    send(p2_msg)

    log_lines: list[str] = []
    winner: str | None = None
    turns = 0
    max_turns = 200  # safety limit to avoid infinite loops

    # Pending requests that haven't been answered yet
    pending_requests: dict[str, dict] = {}
    first_read = True

    try:
        while turns <= max_turns:
            # Read all available output
            # First read uses generous timeout for Node.js startup; subsequent reads are faster
            if first_read:
                output = _read_until_idle(proc, first_line_timeout=5.0, idle_timeout=0.1)
                first_read = False
            else:
                output = _read_until_idle(proc, first_line_timeout=3.0, idle_timeout=0.05)

            if not output:
                if proc.poll() is not None:
                    break
                # Stalled - no output and no pending requests answered
                if not pending_requests:
                    break
                continue

            log_lines.extend(output)

            # Detect trapped state from errors (Shadow Tag, etc.)
            for line in output:
                if "|error|" in line and "trapped" in line.lower():
                    # Mark in log so _choose_action knows not to switch
                    log_lines.append("|trapped|")
                    break

            # Check for winner / tie
            win_result = _find_winner(output)
            if win_result is not None:
                if win_result is False:
                    winner = None  # tie
                else:
                    winner = win_result  # type: ignore[assignment]
                break

            # Count turns
            for line in output:
                m = re.match(r"\|turn\|(\d+)", line)
                if m:
                    turns = int(m.group(1))

            # Parse any new requests from this batch of output
            new_requests = _parse_sideupdate_requests(output)
            pending_requests.update(new_requests)

            # Respond to all pending requests
            for pid, req in list(pending_requests.items()):
                if req.get("wait"):
                    continue  # skip wait requests
                action = _choose_action(req, log_lines, pid)
                send(f">{pid} {action}")
            pending_requests.clear()

    except (BrokenPipeError, OSError):
        pass
    finally:
        try:
            proc.stdin.close()  # type: ignore[union-attr]
        except Exception:
            pass
        try:
            proc.wait(timeout=2.0)
        except subprocess.TimeoutExpired:
            proc.kill()
        except Exception:
            pass

    # Count remaining pokemon
    p1_remaining = _count_remaining(log_lines, "p1")
    p2_remaining = _count_remaining(log_lines, "p2")

    result = {
        "winner": winner,
        "turns": turns,
        "p1_remaining": p1_remaining,
        "p2_remaining": p2_remaining,
    }
    if return_log:
        result["log"] = log_lines
    return result


# ---------------------------------------------------------------------------
# Re-exports for backwards compatibility
# ---------------------------------------------------------------------------
# Tests and other modules import from pokechamp.fast_battle — keep working.

from pokechamp.ai_decision import (  # noqa: E402, F401
    MEGA_TYPE_CHANGES,
    MEGA_VALUABLE_ABILITIES,
    SWITCH_OUT_MATCHUP_THRESHOLD,
    _choose_best_switch,
    _choose_first_switch,
    _extract_species_key,
    _select_team_preview,
    _should_mega_evolve,
    _should_switch_out,
)
from pokechamp.ai_scoring import (  # noqa: E402, F401
    HP_FRACTION_COEFFICIENT,
    SPEED_TIER_COEFFICIENT,
    _calc_type_effectiveness,
    _calc_type_effectiveness_score,
    _estimate_matchup,
    _estimate_opponent_max_damage,
    _estimate_opponent_speed,
    _get_pokemon_types,
    _hp_pct,
    _is_fainted,
    _load_pokemon_base_stats,
    _parse_current_hp,
    _priority_can_ko,
    _score_move,
    _stat_estimation,
)
from pokechamp.log_parser import (  # noqa: E402, F401
    _count_opponent_remaining,
    _get_species_types,
    _opponent_used_recovery,
    _parse_current_turn,
    _parse_move_order,
    _parse_opponent_ability,
    _parse_opponent_boosts,
    _parse_opponent_from_log,
    _parse_self_boosts,
    _parse_side_conditions,
    _parse_switch_in_turn,
    _parse_weather,
)
