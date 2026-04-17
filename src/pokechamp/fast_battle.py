"""Fast Showdown battle runner via subprocess.

Runs battles using node pokemon-showdown simulate-battle directly,
with an embedded heuristic AI for move selection.
No server needed, no WebSocket overhead. ~0.8s per battle.
"""
from __future__ import annotations

import json
import re
import select
import subprocess
import time
from pathlib import Path

from pokechamp.damage import type_effectiveness
from pokechamp.models import TypeName

SHOWDOWN_DIR = Path(__file__).resolve().parent.parent.parent / "engines" / "showdown"

# ---------------------------------------------------------------------------
# Type effectiveness (delegates to pokechamp.damage)
# ---------------------------------------------------------------------------


def _calc_type_effectiveness(move_type: str, defender_types: list[str]) -> float:
    """Return combined type effectiveness multiplier for a move vs a defender."""
    try:
        atk_type = TypeName(move_type.lower())
    except ValueError:
        return 1.0
    eff = 1.0
    for dt in defender_types:
        try:
            def_type = TypeName(dt.lower())
            eff *= type_effectiveness(atk_type, def_type)
        except ValueError:
            pass
    return eff


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
    opponent: dict = {"species": "", "types": [], "hp_pct": 100.0, "stats": {}}

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


# ---------------------------------------------------------------------------
# Damage-based helpers for switch decisions
# ---------------------------------------------------------------------------

_POKEMON_STATS_CACHE: dict[str, dict] = {}


def _load_pokemon_base_stats(species: str) -> dict | None:
    """Load base stats for a species, with caching. Returns None on failure."""
    key = species.lower().replace(" ", "-")
    if key in _POKEMON_STATS_CACHE:
        return _POKEMON_STATS_CACHE[key]
    try:
        from pokechamp.loader import load_pokemon
        poke = load_pokemon(key)
        result = {
            "attack": poke.base_stats.attack,
            "sp_attack": poke.base_stats.sp_attack,
            "defense": poke.base_stats.defense,
            "sp_defense": poke.base_stats.sp_defense,
            "speed": poke.base_stats.speed,
        }
    except Exception:
        result = None  # type: ignore[assignment]
    _POKEMON_STATS_CACHE[key] = result  # type: ignore[assignment]
    return result


def _estimate_opponent_speed(species: str) -> int:
    """Estimate opponent's speed stat from base stats (EV=32, IV=31, Lv50, neutral)."""
    base = _load_pokemon_base_stats(species)
    if base is None:
        return 100  # fallback
    from pokechamp.damage import calc_stat
    from pokechamp.models import Nature
    return calc_stat(base["speed"], 31, 32, 50, Nature.HARDY, "speed")


def _estimate_opponent_max_damage(
    opponent_species: str,
    opponent_types: list[str],
    my_def: int,
    my_spd: int,
    my_types: list[str],
) -> int:
    """Estimate max STAB damage the opponent can deal to us.

    Assumes opponent uses ~80 base power STAB move, standard EVs (EV=32, IV=31, Lv50).
    Returns 0 when estimation is not possible.
    """
    base = _load_pokemon_base_stats(opponent_species)
    if base is None:
        return 0

    from pokechamp.damage import calc_stat, calc_damage_range, type_effectiveness
    from pokechamp.models import Nature, TypeName

    opp_atk = calc_stat(base["attack"], 31, 32, 50, Nature.HARDY, "attack")
    opp_spa = calc_stat(base["sp_attack"], 31, 32, 50, Nature.HARDY, "sp_attack")

    max_damage = 0
    for opp_type_str in opponent_types:
        try:
            opp_type = TypeName(opp_type_str.lower())
        except ValueError:
            continue

        # Type effectiveness against us
        eff = 1.0
        for my_type_str in my_types:
            try:
                eff *= type_effectiveness(opp_type, TypeName(my_type_str.lower()))
            except ValueError:
                pass

        if eff == 0:
            continue

        # Physical STAB damage (power 80)
        phys_dmg = calc_damage_range(
            level=50, power=80, attack_stat=opp_atk, defense_stat=max(my_def, 1),
            stab=True, type_eff=eff,
        )
        max_damage = max(max_damage, max(phys_dmg))

        # Special STAB damage (power 80)
        spec_dmg = calc_damage_range(
            level=50, power=80, attack_stat=opp_spa, defense_stat=max(my_spd, 1),
            stab=True, type_eff=eff,
        )
        max_damage = max(max_damage, max(spec_dmg))

    return max_damage


def _parse_current_hp(pokemon: dict) -> int:
    """Return current HP as an integer from condition string."""
    condition = pokemon.get("condition", "")
    m = re.match(r"(\d+)/(\d+)", condition)
    if m:
        return int(m.group(1))
    return 0


def _calc_type_effectiveness_score(attacker_types: list[str], defender_types: list[str]) -> float:
    """Return max type effectiveness score for attacker vs defender."""
    return max(
        (_calc_type_effectiveness(t, defender_types) for t in attacker_types),
        default=1.0,
    )


# ---------------------------------------------------------------------------
# Heuristic AI: move scoring and switch decision
# ---------------------------------------------------------------------------

SPEED_TIER_COEFFICIENT = 0.1
HP_FRACTION_COEFFICIENT = 0.4
SWITCH_OUT_MATCHUP_THRESHOLD = -2.0


def _estimate_matchup(
    active_types: list[str],
    active_stats: dict[str, int],
    active_hp_pct: float,
    opp_types: list[str],
    opp_stats: dict[str, int],
    opp_hp_pct: float,
) -> float:
    """Estimate matchup score (positive = favourable for active).

    Mirrors SimpleHeuristicsPlayer._estimate_matchup logic.
    """
    # Offensive: best damage multiplier opponent's types take from our types
    opp_incoming = max(
        (_calc_type_effectiveness(t, opp_types) for t in active_types),
        default=1.0,
    )
    # Defensive: best damage multiplier we take from opponent's types
    my_incoming = max(
        (_calc_type_effectiveness(t, active_types) for t in opp_types),
        default=1.0,
    )

    score = opp_incoming - my_incoming

    # Speed tier
    my_spe = active_stats.get("spe", 100)
    opp_spe = opp_stats.get("spe", 100)
    if my_spe > opp_spe:
        score += SPEED_TIER_COEFFICIENT
    elif opp_spe > my_spe:
        score -= SPEED_TIER_COEFFICIENT

    # HP fraction
    score += (active_hp_pct / 100.0) * HP_FRACTION_COEFFICIENT
    score -= (opp_hp_pct / 100.0) * HP_FRACTION_COEFFICIENT

    return score


def _should_switch_out(
    request: dict,
    opponent: dict,
) -> bool:
    """Decide whether we should switch out (mirrors SimpleHeuristicsPlayer._should_switch_out).

    Enhanced with damage-based OHKO/2HKO detection.
    """
    team = request.get("side", {}).get("pokemon", [])
    active_pokemon = next((p for p in team if p.get("active")), None)
    if active_pokemon is None:
        return False

    available_switches = [
        p for p in team
        if not p.get("active")
        and not _is_fainted(p)
    ]
    if not available_switches:
        return False

    active_types = active_pokemon.get("types", [])
    active_stats = active_pokemon.get("stats", {})
    active_hp = _hp_pct(active_pokemon)
    opp_types = opponent.get("types", [])
    opp_stats = opponent.get("stats", {})
    opp_hp = opponent.get("hp_pct", 100.0)
    opp_species = opponent.get("species", "")

    # Check if there is a decent switch-in
    has_good_switch = any(
        _estimate_matchup(
            p.get("types", []), p.get("stats", {}), _hp_pct(p),
            opp_types, opp_stats, opp_hp,
        ) > 0
        for p in available_switches
    )
    if not has_good_switch:
        return False

    # Check for 'good' reason to switch out
    boosts = active_pokemon.get("boosts", {})
    if boosts.get("def", 0) <= -3 or boosts.get("spd", 0) <= -3:
        return True
    if boosts.get("atk", 0) <= -3 and active_stats.get("atk", 0) >= active_stats.get("spa", 0):
        return True
    if boosts.get("spa", 0) <= -3 and active_stats.get("spa", 0) > active_stats.get("atk", 0):
        return True

    # Damage-based OHKO/2HKO check
    if opp_species and opp_types:
        my_def = active_stats.get("def", 100)
        my_spd = active_stats.get("spd", 100)
        my_current_hp = _parse_current_hp(active_pokemon)
        max_incoming = _estimate_opponent_max_damage(
            opp_species, opp_types, my_def, my_spd, active_types
        )
        if max_incoming > 0 and my_current_hp > 0:
            if max_incoming >= my_current_hp:
                return True  # confirmed OHKO
            my_spe = active_stats.get("spe", 100)
            opp_spe = _estimate_opponent_speed(opp_species)
            if max_incoming * 2 >= my_current_hp and opp_spe > my_spe:
                return True  # 2HKO and we're slower

    matchup = _estimate_matchup(
        active_types, active_stats, active_hp,
        opp_types, opp_stats, opp_hp,
    )
    if matchup < SWITCH_OUT_MATCHUP_THRESHOLD:
        return True

    return False


def _choose_best_switch(request: dict, opponent: dict) -> str | None:
    """Return switch command for the best available team member.

    Enhanced to skip switch targets that would be OHKO'd on switch-in.
    """
    team = request.get("side", {}).get("pokemon", [])
    opp_types = opponent.get("types", [])
    opp_stats = opponent.get("stats", {})
    opp_hp = opponent.get("hp_pct", 100.0)
    opp_species = opponent.get("species", "")

    best_idx = None
    best_score = float("-inf")

    for i, mon in enumerate(team):
        if mon.get("active") or _is_fainted(mon):
            continue

        mon_types = mon.get("types", [])
        mon_stats = mon.get("stats", {})
        mon_current_hp = _parse_current_hp(mon)

        # Skip if this switch target would be OHKO'd on switch-in
        if opp_species and opp_types and mon_current_hp > 0:
            mon_def = mon_stats.get("def", 100)
            mon_spd = mon_stats.get("spd", 100)
            switch_in_dmg = _estimate_opponent_max_damage(
                opp_species, opp_types, mon_def, mon_spd, mon_types
            )
            if switch_in_dmg >= mon_current_hp:
                continue  # would die on switch-in, skip

        score = _estimate_matchup(
            mon_types, mon_stats, _hp_pct(mon),
            opp_types, opp_stats, opp_hp,
        )
        if score > best_score:
            best_score = score
            best_idx = i + 1  # 1-indexed

    return f"switch {best_idx}" if best_idx is not None else None


def _choose_first_switch(request: dict) -> str | None:
    """Return first available (non-fainted, non-active) switch index."""
    team = request.get("side", {}).get("pokemon", [])
    for i, mon in enumerate(team):
        if not mon.get("active") and not _is_fainted(mon):
            return f"switch {i + 1}"
    return None


def _is_fainted(pokemon: dict) -> bool:
    condition = pokemon.get("condition", "")
    return condition == "0 fnt" or condition.startswith("0/")


def _hp_pct(pokemon: dict) -> float:
    condition = pokemon.get("condition", "100/100")
    m = re.match(r"(\d+)/(\d+)", condition)
    if m:
        cur, mx = int(m.group(1)), int(m.group(2))
        return (cur / mx * 100.0) if mx else 0.0
    return 0.0 if condition == "0 fnt" else 100.0


def _score_move(
    move: dict,
    active_pokemon: dict,
    opponent: dict,
    physical_ratio: float,
    special_ratio: float,
) -> float:
    """Score a single move (mirrors SimpleHeuristicsPlayer's inline scoring)."""
    base_power = move.get("basePower", 0) or 0
    if base_power == 0:
        return 0.0

    move_type = (move.get("type") or "").lower()
    active_types = [t.lower() for t in active_pokemon.get("types", [])]

    # STAB
    stab = 1.5 if move_type in active_types else 1.0

    # Category ratio
    category = (move.get("category") or "").lower()
    if category == "physical":
        ratio = physical_ratio
    elif category == "special":
        ratio = special_ratio
    else:
        return 0.0  # status move

    # Type effectiveness
    opp_types = opponent.get("types", [])
    effectiveness = _calc_type_effectiveness(move_type, opp_types)

    accuracy = (move.get("accuracy") if move.get("accuracy") is not True else 100) or 100
    accuracy = accuracy / 100.0

    expected_hits = move.get("multihit", 1) or 1
    if isinstance(expected_hits, list):
        # e.g. [2, 5] multi-hit: expected ~3.17
        expected_hits = sum(expected_hits) / len(expected_hits)

    return base_power * stab * ratio * accuracy * expected_hits * effectiveness


def _stat_estimation(base_stat: int, boost: int) -> float:
    """Estimate effective stat including boost stages."""
    if boost > 1:
        boost_mult = (2 + boost) / 2
    else:
        boost_mult = 2 / (2 - boost)
    return ((2 * base_stat + 31) + 5) * boost_mult


def _priority_can_ko(
    move: dict,
    active_pokemon: dict,
    opponent: dict,
    physical_ratio: float,
    special_ratio: float,
) -> bool:
    """Estimate if a priority move can KO the opponent this turn.

    Uses a rough damage estimate: score > opp_hp_pct * threshold.
    This is intentionally conservative — only returns True when clearly able to KO.
    """
    opp_hp_pct = opponent.get("hp_pct", 100.0)
    if opp_hp_pct <= 0:
        return False
    move_score = _score_move(move, active_pokemon, opponent, physical_ratio, special_ratio)
    if move_score <= 0:
        return False
    # Heuristic: if score (damage proxy) exceeds opp hp% * 1.5, likely KO
    # The score is base_power * modifiers, typically 60-200 for normal attacks.
    # opp_hp_pct is 0-100. Threshold tuned so score ~100+ vs low HP triggers KO.
    return move_score >= opp_hp_pct * 1.5


def _choose_action(request: dict, log_lines: list[str], player_id: str) -> str:
    """Choose an action given the current request JSON.

    Returns a command string like 'move 1', 'switch 2', 'team 123', etc.
    """
    # Team preview
    if request.get("teamPreview"):
        max_size = request.get("maxChosenTeamSize", 3)
        team = request.get("side", {}).get("pokemon", [])
        # Pick first max_size
        picks = list(range(1, min(max_size, len(team)) + 1))
        return f"team {''.join(str(p) for p in picks)}"

    # Force switch
    if request.get("forceSwitch"):
        opp = _parse_opponent_from_log(log_lines, player_id)
        switch_cmd = _choose_best_switch(request, opp)
        return switch_cmd or _choose_first_switch(request) or "move 1"

    # No active moves (pass)
    if request.get("wait"):
        return "move 1"  # should not happen but fallback

    active_list = request.get("active", [{}])
    active_req = active_list[0] if active_list else {}
    moves = active_req.get("moves", [])
    team = request.get("side", {}).get("pokemon", [])
    active_pokemon = next((p for p in team if p.get("active")), {})

    # Derive stat ratios for physical/special scoring
    active_stats = active_pokemon.get("stats", {})
    active_boosts = active_pokemon.get("boosts", {})
    opp = _parse_opponent_from_log(log_lines, player_id)
    opp_stats = opp.get("stats", {})
    opp_boosts: dict[str, int] = {}

    atk_est = _stat_estimation(active_stats.get("atk", 100), active_boosts.get("atk", 0))
    spa_est = _stat_estimation(active_stats.get("spa", 100), active_boosts.get("spa", 0))
    opp_def_est = _stat_estimation(opp_stats.get("def", 100), opp_boosts.get("def", 0))
    opp_spd_est = _stat_estimation(opp_stats.get("spd", 100), opp_boosts.get("spd", 0))

    physical_ratio = atk_est / opp_def_est if opp_def_est else 1.0
    special_ratio = spa_est / opp_spd_est if opp_spd_est else 1.0

    available_moves = [m for m in moves if not m.get("disabled")]
    available_switches = [p for p in team if not p.get("active") and not _is_fainted(p)]

    # Priority move check: if we have a priority move that can KO, use it instead of switching
    priority_ko_move = None
    for move in available_moves:
        if move.get("priority", 0) > 0:
            if _priority_can_ko(move, active_pokemon, opp, physical_ratio, special_ratio):
                priority_ko_move = move
                break

    # Determine if we should switch out (but not if we have a priority KO available)
    if priority_ko_move is None and available_switches and _should_switch_out(request, opp):
        switch_cmd = _choose_best_switch(request, opp)
        if switch_cmd:
            return switch_cmd

    # Use the priority KO move if found
    if priority_ko_move is not None:
        return f"move {moves.index(priority_ko_move) + 1}"

    if available_moves:
        # Entry hazards setup (if opponent has >=3 mons remaining)
        opp_remaining = _count_opponent_remaining(log_lines, player_id)
        if opp_remaining >= 3:
            for i, move in enumerate(available_moves):
                if move.get("id") in ("stealthrock", "spikes", "stickyweb", "toxicspikes"):
                    return f"move {moves.index(move) + 1}"

        # Hazard removal
        my_conditions = _parse_side_conditions(log_lines, player_id)
        if my_conditions:
            for i, move in enumerate(available_moves):
                if move.get("id") in ("rapidspin", "defog"):
                    return f"move {moves.index(move) + 1}"

        # Setup moves (only when at full HP and winning matchup)
        active_hp = _hp_pct(active_pokemon)
        opp_hp = opp.get("hp_pct", 100.0)
        if active_hp >= 100.0:
            matchup = _estimate_matchup(
                active_pokemon.get("types", []),
                active_stats,
                active_hp,
                opp.get("types", []),
                opp_stats,
                opp_hp,
            )
            if matchup > 0:
                for move in available_moves:
                    boosts = move.get("boosts") or {}
                    target = move.get("target", "")
                    if boosts and sum(boosts.values()) >= 2 and target == "self":
                        boost_sum = sum(boosts.values())
                        if boost_sum >= 2:
                            return f"move {moves.index(move) + 1}"

        # Score moves and pick best
        scored = []
        for move in available_moves:
            score = _score_move(move, active_pokemon, opp, physical_ratio, special_ratio)
            scored.append((move, score))

        if scored:
            best_move, best_score = max(scored, key=lambda x: x[1])
            if best_score > 0:
                return f"move {moves.index(best_move) + 1}"
            # All status moves or 0 power: pick first available
            return f"move {moves.index(available_moves[0]) + 1}"

    # Fallback to first move
    if moves:
        return f"move {moves.index(next(m for m in moves if not m.get('disabled')), moves[0]) + 1}"

    # If we have switches, switch to best
    if available_switches:
        switch_cmd = _choose_best_switch(request, opp)
        return switch_cmd or "move 1"

    return "move 1"


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
    """Parse active side conditions from log."""
    conditions: list[str] = []
    for line in log_lines:
        if f"|-sidestart|{player_id}: " in line:
            parts = line.split("|")
            if len(parts) > 3:
                cond = parts[3].strip()
                if cond not in conditions:
                    conditions.append(cond)
        elif f"|-sideend|{player_id}: " in line:
            parts = line.split("|")
            if len(parts) > 3:
                cond = parts[3].strip()
                if cond in conditions:
                    conditions.remove(cond)
    return conditions


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
