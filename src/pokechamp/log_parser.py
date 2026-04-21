"""Battle log parser for Showdown protocol.

Extracts opponent info, stat boosts, weather, abilities, move order,
side conditions, and turn tracking from battle log lines.
"""
from __future__ import annotations

import re

from pokechamp.ai_scoring import _estimate_opponent_speed

# ---------------------------------------------------------------------------
# Opponent info cache parsed from battle log
# ---------------------------------------------------------------------------

_SPECIES_TYPES_CACHE: dict[str, list[str]] = {}


def _get_species_types(species_raw: str) -> list[str]:
    """Return type list for a species name, with caching."""
    key = species_raw.lower().replace(" ", "-")
    if key in _SPECIES_TYPES_CACHE:
        return _SPECIES_TYPES_CACHE[key]
    try:
        from pokechamp.loader import load_pokemon
        poke = load_pokemon(key)
        result = [t.value for t in poke.types]
    except Exception:
        result = []
    _SPECIES_TYPES_CACHE[key] = result
    return result


def _parse_opponent_from_log(log_lines: list[str], my_player_id: str) -> dict:
    """Extract opponent's active pokemon info from battle log.

    Returns dict with keys: species, types, hp_pct, stats.
    """
    opp_id = "p2" if my_player_id == "p1" else "p1"
    opponent: dict = {"species": "", "types": [], "hp_pct": 100.0, "stats": {}, "ability": ""}

    for line in reversed(log_lines):
        if f"|switch|{opp_id}a: " in line or f"|drag|{opp_id}a: " in line:
            # |switch|p2a: Garchomp|Garchomp, L50, M|100/100
            parts = line.split("|")
            if len(parts) > 3:
                species_part = parts[3]
                species = species_part.split(",")[0].strip()
                opponent["species"] = species
                opponent["types"] = _get_species_types(species)

                # HP from last field
                if len(parts) > 4:
                    hp_field = parts[4].strip()
                    m = re.match(r"(\d+)/(\d+)", hp_field)
                    if m:
                        cur, mx = int(m.group(1)), int(m.group(2))
                        opponent["hp_pct"] = (cur / mx * 100) if mx else 100.0
            break

    # Update HP from latest damage/heal lines
    for line in reversed(log_lines):
        if f"|-damage|{opp_id}a: " in line or f"|-heal|{opp_id}a: " in line:
            parts = line.split("|")
            if len(parts) > 3:
                hp_field = parts[3].strip()
                m = re.match(r"(\d+)/(\d+)", hp_field)
                if m:
                    cur, mx = int(m.group(1)), int(m.group(2))
                    opponent["hp_pct"] = (cur / mx * 100) if mx else 100.0
            break

    # Estimate opponent speed from base stats if species known
    if opponent["species"] and not opponent["stats"].get("spe"):
        opp_spe = _estimate_opponent_speed(opponent["species"])
        opponent["stats"]["spe"] = opp_spe

    opponent["ability"] = _parse_opponent_ability(log_lines, my_player_id)
    return opponent


def _parse_opponent_boosts(log_lines: list[str], my_player_id: str) -> dict[str, int]:
    """Extract current opponent's stat boosts from battle log.

    Boosts reset on switch. Returns dict like {"atk": 2, "spe": 1}.
    """
    opp_id = "p2" if my_player_id == "p1" else "p1"
    boosts: dict[str, int] = {}

    for line in log_lines:
        # Reset boosts on opponent switch
        if f"|switch|{opp_id}a: " in line or f"|drag|{opp_id}a: " in line:
            boosts.clear()
        # |-boost|p2a: Garchomp|atk|2
        m = re.match(rf"\|-boost\|{opp_id}a: [^|]+\|(\w+)\|(\d+)", line)
        if m:
            stat, stages = m.group(1), int(m.group(2))
            boosts[stat] = boosts.get(stat, 0) + stages
        # |-unboost|p2a: Garchomp|atk|1
        m = re.match(rf"\|-unboost\|{opp_id}a: [^|]+\|(\w+)\|(\d+)", line)
        if m:
            stat, stages = m.group(1), int(m.group(2))
            boosts[stat] = boosts.get(stat, 0) - stages

    return boosts


def _parse_self_boosts(log_lines: list[str], player_id: str) -> dict[str, int]:
    """Extract own active pokemon's stat boosts from battle log.

    Boosts reset on switch. Returns dict like {"spa": -4, "def": -2}.
    Needed because request JSON boosts don't include move-induced self-debuffs
    (e.g. Draco Meteor's SpA -2, Close Combat's Def/SpD -1).
    """
    boosts: dict[str, int] = {}

    for line in log_lines:
        if f"|switch|{player_id}a: " in line or f"|drag|{player_id}a: " in line:
            boosts.clear()
        m = re.match(rf"\|-boost\|{player_id}a: [^|]+\|(\w+)\|(\d+)", line)
        if m:
            stat, stages = m.group(1), int(m.group(2))
            boosts[stat] = boosts.get(stat, 0) + stages
        m = re.match(rf"\|-unboost\|{player_id}a: [^|]+\|(\w+)\|(\d+)", line)
        if m:
            stat, stages = m.group(1), int(m.group(2))
            boosts[stat] = boosts.get(stat, 0) - stages

    return boosts


def _parse_opponent_ability(log_lines: list[str], my_player_id: str) -> str:
    """Extract opponent's revealed ability from battle log.

    Returns lowercase ability ID (e.g. "intimidate") or "" if not revealed.
    Resets when opponent switches.
    """
    opp_id = "p2" if my_player_id == "p1" else "p1"
    ability = ""

    for line in log_lines:
        if f"|switch|{opp_id}a: " in line or f"|drag|{opp_id}a: " in line:
            ability = ""
        # |-ability|p2a: Gyarados|Intimidate|boost
        m = re.match(rf"\|-ability\|{opp_id}a: [^|]+\|([^|]+)", line)
        if m:
            ability = m.group(1).strip().lower().replace(" ", "")
        # |-immune|p2a: Bronzong|[from] ability: Levitate
        # But NOT: |-damage|p2a: Bronzong|...|[from] ability: Rough Skin|[of] p1a: Garchomp
        # The [of] tag indicates the ability belongs to a DIFFERENT pokemon.
        if f"{opp_id}a: " in line and "[from] ability: " in line:
            # Skip if [of] points to a different player (ability belongs to them, not opponent)
            if f"[of] {opp_id}a:" not in line and "[of]" in line:
                pass  # ability belongs to someone else
            else:
                idx = line.index("[from] ability: ") + len("[from] ability: ")
                ab_name = line[idx:].split("|")[0].strip().lower().replace(" ", "")
                if ab_name:
                    ability = ab_name
        # |-activate|p2a: Heatran|ability: Flash Fire
        if f"|-activate|{opp_id}a: " in line and "ability: " in line:
            idx = line.index("ability: ") + len("ability: ")
            ab_name = line[idx:].split("|")[0].strip().lower().replace(" ", "")
            if ab_name:
                ability = ab_name

    return ability


def _parse_move_order(log_lines: list[str], my_player_id: str) -> str | None:
    """Determine who moved first in the most recent turn from battle log.

    Returns "me", "opp", or None if not determinable.
    Only considers the last turn's moves (ignores priority moves).
    """
    opp_id = "p2" if my_player_id == "p1" else "p1"

    # Find moves from the most recent turn
    last_turn_moves: list[str] = []
    in_last_turn = False

    for line in log_lines:
        if re.match(r"\|turn\|\d+", line):
            in_last_turn = True
            last_turn_moves.clear()
        if in_last_turn and line.startswith("|move|"):
            last_turn_moves.append(line)

    if len(last_turn_moves) < 2:
        return None

    first_move = last_turn_moves[0]
    first_mover = my_player_id if f"|move|{my_player_id}a: " in first_move else opp_id

    return "me" if first_mover == my_player_id else "opp"


def _opponent_used_recovery(log_lines: list[str], my_player_id: str) -> bool:
    """Check if the current opponent has used a recovery move in this matchup.

    Tracks only moves from the current opponent (resets on switch).
    """
    opp_id = "p2" if my_player_id == "p1" else "p1"
    recovery_ids = {
        "recover", "roost", "softboiled", "slackoff", "moonlight", "synthesis",
        "morningsun", "milkdrink", "shoreup", "healorder", "rest",
    }
    used_recovery = False
    for line in log_lines:
        if f"|switch|{opp_id}a: " in line or f"|drag|{opp_id}a: " in line:
            used_recovery = False
        if f"|move|{opp_id}a: " in line:
            parts = line.split("|")
            if len(parts) > 3:
                move_name = parts[3].strip().lower().replace(" ", "").replace("-", "")
                if move_name in recovery_ids:
                    used_recovery = True
    return used_recovery


def _parse_weather(log_lines: list[str]) -> str:
    """Return current weather from battle log.

    Returns lowercase weather id (e.g. "sunnyday", "sandstorm") or "" if none.
    """
    weather = ""
    for line in log_lines:
        m = re.match(r"\|-weather\|(\w+)", line)
        if m:
            w = m.group(1).lower()
            weather = "" if w == "none" else w
    return weather


def _parse_current_turn(log_lines: list[str]) -> int:
    """Return the current turn number from battle log."""
    turn = 0
    for line in log_lines:
        m = re.match(r"\|turn\|(\d+)", line)
        if m:
            turn = int(m.group(1))
    return turn


def _parse_switch_in_turn(log_lines: list[str], player_id: str) -> int:
    """Return the turn number when the player's active pokemon last switched in.

    Returns 0 if switched in before turn 1 (team preview lead).
    """
    switch_in_turn = 0
    current_turn = 0
    for line in log_lines:
        m = re.match(r"\|turn\|(\d+)", line)
        if m:
            current_turn = int(m.group(1))
        if f"|switch|{player_id}a: " in line or f"|drag|{player_id}a: " in line:
            switch_in_turn = current_turn
    return switch_in_turn


def _count_opponent_remaining(log_lines: list[str], player_id: str) -> int:
    """Count opponent's remaining (non-fainted) pokemon from log."""
    opp_id = "p2" if player_id == "p1" else "p1"
    fainted: set[str] = set()
    seen: set[str] = set()

    for line in log_lines:
        # Track seen pokemon from switches
        m = re.search(rf"\|(?:switch|drag)\|{opp_id}a: ([^|]+)\|", line)
        if m:
            seen.add(m.group(1).strip())
        # Track fainted
        m = re.search(rf"\|faint\|{opp_id}a: (.+)", line)
        if m:
            fainted.add(m.group(1).strip())

    # If we can't tell, default to 3 (BSS has 3 active)
    remaining = max(len(seen) - len(fainted), 0)
    return remaining if remaining > 0 else 3


def _parse_side_conditions(log_lines: list[str], player_id: str) -> list[str]:
    """Parse active side conditions from log.

    Returns condition names with 'move: ' prefix stripped
    (e.g. 'Stealth Rock' not 'move: Stealth Rock').
    """
    conditions: list[str] = []
    for line in log_lines:
        if f"|-sidestart|{player_id}: " in line:
            parts = line.split("|")
            if len(parts) > 3:
                cond = parts[3].strip()
                # Strip 'move: ' prefix from condition names
                if cond.startswith("move: "):
                    cond = cond[6:]
                if cond not in conditions:
                    conditions.append(cond)
        elif f"|-sideend|{player_id}: " in line:
            parts = line.split("|")
            if len(parts) > 3:
                cond = parts[3].strip()
                if cond.startswith("move: "):
                    cond = cond[6:]
                if cond in conditions:
                    conditions.remove(cond)
    return conditions


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
