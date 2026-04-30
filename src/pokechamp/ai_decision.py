"""AI decision-making: action selection, switching, mega evolution, team selection.

Main entry point is _choose_action which orchestrates all heuristic decisions.
"""
from __future__ import annotations

import itertools
import random
import re

from pokechamp import showdown_data
from pokechamp.ai_scoring import (
    _calc_type_effectiveness,
    _estimate_matchup,
    _estimate_opponent_max_damage,
    _estimate_opponent_speed,
    _get_pokemon_types,
    _hp_pct,
    _is_fainted,
    _load_pokemon_base_stats,
    _parse_current_hp,
    _parse_max_hp,
    _priority_can_ko,
    _score_move,
    _stat_estimation,
)
from pokechamp.log_parser import (
    _count_opponent_remaining,
    _opponent_used_recovery,
    _parse_current_turn,
    _parse_move_order,
    _parse_opponent_boosts,
    _parse_opponent_from_log,
    _parse_self_boosts,
    _parse_side_conditions,
    _parse_switch_in_turn,
    _parse_weather,
)

# ---------------------------------------------------------------------------
# Mega Evolution lookup tables
# ---------------------------------------------------------------------------

# Type-changing megas: species -> {base_types, mega_types}
# Only the 10 megas whose types change on evolution.
MEGA_TYPE_CHANGES: dict[str, dict[str, list[str]]] = {
    "charizard": {"base_types": ["fire", "flying"], "mega_types": ["fire", "dragon"]},  # X
    "pinsir": {"base_types": ["bug"], "mega_types": ["bug", "flying"]},
    "gyarados": {"base_types": ["water", "flying"], "mega_types": ["water", "dark"]},
    "ampharos": {"base_types": ["electric"], "mega_types": ["electric", "dragon"]},
    "aggron": {"base_types": ["steel", "rock"], "mega_types": ["steel"]},
    "altaria": {"base_types": ["dragon", "flying"], "mega_types": ["dragon", "fairy"]},
    "chimecho": {"base_types": ["psychic"], "mega_types": ["psychic", "steel"]},
    "audino": {"base_types": ["normal"], "mega_types": ["normal", "fairy"]},
    "feraligatr": {"base_types": ["water"], "mega_types": ["water", "dragon"]},
    "meganium": {"base_types": ["grass"], "mega_types": ["grass", "fairy"]},
}

# Pre-mega abilities that are situationally valuable.
# species -> {ability, check} where check is the condition type.
MEGA_VALUABLE_ABILITIES: dict[str, dict[str, str]] = {
    "clefable": {"ability": "unaware", "check": "opponent_has_boosts"},
    "venusaur": {"ability": "chlorophyll", "check": "weather_is_sun"},
}

SWITCH_OUT_MATCHUP_THRESHOLD = -2.0


def _extract_species_key(species: str) -> str:
    """Normalize species name to lookup key (e.g. 'Charizard' -> 'charizard')."""
    return species.split("-")[0].strip().lower()


def _should_mega_evolve(
    species: str,
    active_types: list[str],
    opp_types: list[str],
    opp_boosts: dict[str, int],
    weather: str,
    moves: list[dict],
) -> bool:
    """Decide whether to mega evolve this turn.

    Default: True (always mega).
    Exceptions:
      - Category A: Type change increases opponent's max damage against us,
        OR type change reduces our best move's effective score.
      - Category B: Pre-mega ability is situationally valuable
        (Clefable/Unaware when opponent has boosts, Venusaur/Chlorophyll in sun).
    """
    key = _extract_species_key(species)

    # --- Category B: valuable pre-mega ability ---
    if key in MEGA_VALUABLE_ABILITIES:
        entry = MEGA_VALUABLE_ABILITIES[key]
        check = entry["check"]
        if check == "opponent_has_boosts":
            if any(v > 0 for v in opp_boosts.values()):
                return False
        elif check == "weather_is_sun":
            if weather == "sunnyday":
                return False

    # --- Category A: type change evaluation ---
    if key not in MEGA_TYPE_CHANGES:
        return True

    info = MEGA_TYPE_CHANGES[key]
    base_types = info["base_types"]
    mega_types = info["mega_types"]

    # 1. Defensive check: does mega increase max incoming damage?
    base_incoming = max(
        (_calc_type_effectiveness(t, base_types) for t in opp_types),
        default=1.0,
    )
    mega_incoming = max(
        (_calc_type_effectiveness(t, mega_types) for t in opp_types),
        default=1.0,
    )
    if mega_incoming > base_incoming:
        return False

    # 2. Offensive check: does mega reduce our best move score?
    base_best = 0.0
    mega_best = 0.0
    for move in moves:
        bp = move.get("basePower", 0) or 0
        if bp == 0:
            continue
        move_type = (move.get("type") or "").lower()
        eff = _calc_type_effectiveness(move_type, opp_types)
        base_stab = 1.5 if move_type in [t.lower() for t in base_types] else 1.0
        mega_stab = 1.5 if move_type in [t.lower() for t in mega_types] else 1.0
        base_best = max(base_best, bp * base_stab * eff)
        mega_best = max(mega_best, bp * mega_stab * eff)

    if mega_best < base_best:
        return False

    return True


def _estimate_incoming_after_boost(
    boost_stages: dict[str, int],
    base_incoming: int,
    opp_species: str,
) -> int:
    """Estimate incoming damage after defensive boosts.

    def boosts only reduce physical; spd boosts only reduce special.
    Stage formula: damage * 2/(2+stages).
    """
    if base_incoming <= 0:
        return 0
    opp_base = _load_pokemon_base_stats(opp_species)
    opp_atk = opp_base["attack"] if opp_base else 100
    opp_spa = opp_base["sp_attack"] if opp_base else 100
    opp_is_physical = opp_atk >= opp_spa

    stages = boost_stages.get("def", 0) if opp_is_physical else boost_stages.get("spd", 0)
    if stages > 0:
        return int(base_incoming * 2 / (2 + stages))
    return base_incoming


def _count_action_turns(
    my_hp: int,
    incoming_per_turn: int,
    recovery_per_turn: int = 0,
) -> float:
    """How many turns can we act before fainting?

    Each turn: take incoming damage, then recover.
    Returns the number of turns we survive (can be fractional).
    """
    if incoming_per_turn <= 0:
        return 99.0  # effectively infinite
    net_damage = max(incoming_per_turn - recovery_per_turn, 1)
    return my_hp / net_damage


def _turns_to_ko(
    atk_score: float,
    opp_hp_pct: float,
) -> float:
    """Estimated turns to KO opponent given our attack score.

    atk_score is from _score_move (roughly proportional to %HP damage).
    """
    if atk_score <= 0:
        return 99.0
    # _score_move returns ~bp*stab*ratio*eff; a score of ~300 is roughly 100% HP
    dmg_pct = atk_score / 3.0  # rough: score/3 ≈ %HP per hit
    if dmg_pct <= 0:
        return 99.0
    return max(opp_hp_pct / dmg_pct, 1.0)


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
            _get_pokemon_types(p), p.get("stats", {}), _hp_pct(p),
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
        my_max_hp = _parse_max_hp(active_pokemon)
        max_incoming = _estimate_opponent_max_damage(
            opp_species, opp_types, my_def, my_spd, active_types,
            confirmed_ability=opponent.get("ability", ""),
        )
        if max_incoming > 0 and my_current_hp > 0:
            # --- Sacrifice check: low HP → stay and attack rather than switch ---
            # Switching wastes the switch-in's HP (takes a free hit).
            # If we're nearly dead, it's better to attack/sack and bring
            # the next pokemon in at full HP.
            hp_ratio = my_current_hp / my_max_hp if my_max_hp > 0 else 0
            if hp_ratio <= 0.20 and max_incoming >= my_current_hp:
                # We're dying either way — don't switch, sack this pokemon.
                return False

            if max_incoming >= my_current_hp:
                return True  # confirmed OHKO (but we have enough HP to justify saving)
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

        mon_types = _get_pokemon_types(mon)
        mon_stats = mon.get("stats", {})
        mon_current_hp = _parse_current_hp(mon)

        # Skip if this switch target would be OHKO'd on switch-in
        if opp_species and opp_types and mon_current_hp > 0:
            mon_def = mon_stats.get("def", 100)
            mon_spd = mon_stats.get("spd", 100)
            switch_in_dmg = _estimate_opponent_max_damage(
                opp_species, opp_types, mon_def, mon_spd, mon_types,
                confirmed_ability=opponent.get("ability", ""),
            )
            if switch_in_dmg >= mon_current_hp:
                continue  # would die on switch-in, skip

        score = _estimate_matchup(
            mon_types, mon_stats, _hp_pct(mon),
            opp_types, opp_stats, opp_hp,
        )

        # Defensive safety bonus: if opponent deals very little damage,
        # this pokemon can safely wall even without offensive advantage.
        # switch_in_dmg is already computed above (0 if estimation failed).
        if opp_species and opp_types and mon_current_hp > 0 and switch_in_dmg > 0:
            dmg_ratio = switch_in_dmg / mon_current_hp
            if dmg_ratio < 0.15:
                score += 1.0  # can tank ~7+ hits: excellent wall
            elif dmg_ratio < 0.25:
                score += 0.5  # can tank 4-6 hits: solid wall

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


def _select_team_preview(
    team: list[dict], log_lines: list[str], max_size: int,
) -> list[int]:
    """Select best pokemon for team preview based on type matchup vs opponent.

    Parses opponent team from |poke| lines in log, scores all C(n, max_size)
    combinations, and picks from the top candidates with slight randomness.
    Returns 1-indexed picks like [2, 4, 5].
    """
    # Parse opponent species from |poke| lines
    opp_species_list: list[str] = []
    for line in log_lines:
        if "|poke|" in line:
            parts = line.split("|")
            if len(parts) >= 4:
                # |poke|p2|Garchomp, L50, M|
                poke_info = parts[3]
                species = poke_info.split(",")[0].strip()
                # Only opponent's pokemon (detect from p1/p2)
                player_tag = parts[2].strip()
                # We don't know which player we are at this point,
                # so collect all and deduplicate by player
                opp_species_list.append((player_tag, species))

    # Determine which player tag is ours from team idents
    my_tag = ""
    if team:
        ident = team[0].get("ident", "")
        if ident.startswith("p1"):
            my_tag = "p1"
        elif ident.startswith("p2"):
            my_tag = "p2"

    opp_species = [sp for tag, sp in opp_species_list if tag != my_tag]

    if not opp_species:
        # Fallback: pick first max_size
        return list(range(1, min(max_size, len(team)) + 1))

    # Get types and move types for our team
    my_pokemon: list[tuple[int, list[str]]] = []
    my_move_types: list[list[str]] = []  # move types per pokemon (for coverage calc)
    for i, mon in enumerate(team):
        types = _get_pokemon_types(mon)
        my_pokemon.append((i, types))
        # Collect actual move types from the pokemon's moveset
        mon_move_types: list[str] = []
        for move_id in (mon.get("moves") or []):
            if isinstance(move_id, dict):
                move_id = move_id.get("id", "")
            sd = showdown_data.get_move(str(move_id))
            if sd:
                mt = sd.get("type", "").lower()
                bp = sd.get("basePower", 0)
                if mt and bp > 0 and mt not in mon_move_types:
                    mon_move_types.append(mt)
        my_move_types.append(mon_move_types)

    opp_types_list: list[list[str]] = []
    opp_abilities_list: list[list[str]] = []  # abilities per opponent pokemon
    pokedex = showdown_data.load_pokedex()
    for sp in opp_species:
        key = sp.lower().replace(" ", "").replace("-", "")
        entry = pokedex.get(key)
        if entry:
            opp_types_list.append([t.lower() for t in entry.get("types", [])])
            opp_abilities_list.append(list(entry.get("abilities", {}).values()))
        else:
            opp_types_list.append([])
            opp_abilities_list.append([])

    # Detect threatening abilities in opponent team
    opp_has_shadow_tag = any(
        "shadowtag" in ab for abs_list in opp_abilities_list for ab in abs_list
    )
    # Abilities that reduce specific type damage
    opp_damage_reducers: dict[int, dict[str, float]] = {}  # opp_idx -> {type: mult}
    for oi, abs_list in enumerate(opp_abilities_list):
        for ab in abs_list:
            for check_type in ("fire", "ice", "ground", "water", "electric", "grass", "ghost"):
                mod = showdown_data.ability_damage_modifier(ab, check_type)
                if mod != 1.0:
                    opp_damage_reducers.setdefault(oi, {})[check_type] = mod

    # Score each combination of max_size pokemon
    indices = list(range(len(team)))
    best_combos: list[tuple[float, tuple[int, ...]]] = []

    for combo in itertools.combinations(indices, min(max_size, len(team))):
        score = 0.0
        combo_types = [my_pokemon[i][1] for i in combo]

        for oi, opp_t in enumerate(opp_types_list):
            if not opp_t:
                continue
            # Best matchup any of our 3 has against this opponent
            best_vs_this_opp = -10.0
            worst_vs_this_opp = 10.0  # for Shadow Tag check
            # Track: can opponent hit all 3 of ours super-effectively?
            min_incoming = 10.0  # lowest eff opponent deals to any of our 3
            for ci_idx, my_t in enumerate(combo_types):
                if not my_t:
                    continue
                # Offensive: use actual move types if available, fall back to STAB types
                move_types = my_move_types[combo[ci_idx]]
                coverage_types = move_types if move_types else my_t
                atk_eff = max(
                    (_calc_type_effectiveness(t, opp_t) for t in coverage_types),
                    default=1.0,
                )
                # Adjust for opponent's damage reduction abilities
                if oi in opp_damage_reducers:
                    for my_atk_type in coverage_types:
                        if my_atk_type in opp_damage_reducers[oi]:
                            atk_eff *= opp_damage_reducers[oi][my_atk_type]

                # Defensive: best type eff they deal to us
                def_eff = max(
                    (_calc_type_effectiveness(t, my_t) for t in opp_t),
                    default=1.0,
                )
                matchup = atk_eff - def_eff
                best_vs_this_opp = max(best_vs_this_opp, matchup)
                worst_vs_this_opp = min(worst_vs_this_opp, matchup)
                min_incoming = min(min_incoming, def_eff)
            score += best_vs_this_opp

            # Penalty: if opponent hits all 3 of ours super-effectively
            if min_incoming > 1.0:
                score -= min_incoming
            elif min_incoming <= 0.5:
                score += 0.5


        # Shadow Tag penalty: if opponent has trapping ability,
        # getting caught in a bad matchup is devastating.
        # Penalize combos where ANY of our 3 has a terrible matchup vs the trapper.
        # Exception: pokemon with U-turn/Volt Switch/Flip Turn can escape.
        if opp_has_shadow_tag:
            # Check which of our combo members have pivot moves
            pivot_move_ids = {"uturn", "voltswitch", "flipturn", "teleport", "batonpass"}
            combo_has_pivot = []
            for ci in combo:
                mon_moves = team[ci].get("moves", [])
                has_pivot = any(m in pivot_move_ids for m in mon_moves)
                combo_has_pivot.append(has_pivot)

            for oi, abs_list in enumerate(opp_abilities_list):
                if "shadowtag" in abs_list:
                    opp_t = opp_types_list[oi]
                    for mi, my_t in enumerate(combo_types):
                        if not my_t or not opp_t:
                            continue
                        m_types = my_move_types[combo[mi]] or my_t
                        atk = max((_calc_type_effectiveness(t, opp_t) for t in m_types), default=1.0)
                        dfe = max((_calc_type_effectiveness(t, my_t) for t in opp_t), default=1.0)
                        this_matchup = atk - dfe
                        if this_matchup < -1.0:
                            if combo_has_pivot[mi]:
                                score -= 0.5  # can escape, mild penalty
                            else:
                                score -= 2.0  # trapped and disadvantaged

        best_combos.append((score, combo))

    # Sort by score descending, pick from top 3 with randomness
    # Use hash of opponent species as deterministic seed for reproducibility
    best_combos.sort(key=lambda x: -x[0])
    top_n = min(3, len(best_combos))
    if top_n > 0:
        rng = random.Random(hash(tuple(opp_species)))
        chosen = rng.choice(best_combos[:top_n])
        return [i + 1 for i in chosen[1]]

    return list(range(1, min(max_size, len(team)) + 1))


def _choose_action(request: dict, log_lines: list[str], player_id: str) -> str:
    """Choose an action given the current request JSON.

    Returns a command string like 'move 1', 'switch 2', 'team 123', etc.
    """
    # Team preview — select best 3 based on type matchup vs opponent team
    if request.get("teamPreview"):
        max_size = request.get("maxChosenTeamSize", 3)
        team = request.get("side", {}).get("pokemon", [])
        picks = _select_team_preview(team, log_lines, max_size)
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

    # Ensure active pokemon has types (request JSON may omit them)
    if not active_pokemon.get("types"):
        active_pokemon = dict(active_pokemon)  # copy to avoid mutating request
        active_pokemon["types"] = _get_pokemon_types(active_pokemon)

    # Derive stat ratios for physical/special scoring
    active_stats = active_pokemon.get("stats", {})
    active_boosts = active_pokemon.get("boosts", {})
    # Merge self boosts from log (request JSON misses move-induced self-debuffs)
    log_boosts = _parse_self_boosts(log_lines, player_id)
    if log_boosts:
        active_boosts = dict(active_boosts)  # copy to avoid mutating request
        for stat, val in log_boosts.items():
            active_boosts[stat] = active_boosts.get(stat, 0) + val
    opp = _parse_opponent_from_log(log_lines, player_id)
    opp_stats = opp.get("stats", {})
    opp_boosts = _parse_opponent_boosts(log_lines, player_id)

    # Mega evolution decision
    can_mega = active_req.get("canMegaEvo", False)
    mega_suffix = ""
    if can_mega:
        species_name = active_pokemon.get("ident", "").split(": ", 1)[-1] if active_pokemon else ""
        weather = _parse_weather(log_lines)
        if _should_mega_evolve(
            species=species_name,
            active_types=active_pokemon.get("types", []),
            opp_types=opp.get("types", []),
            opp_boosts=opp_boosts,
            weather=weather,
            moves=moves,
        ):
            mega_suffix = " mega"

    # Detect possible Choice Scarf from move order
    # If opponent moved first despite our speed being higher, they may have scarf
    move_order = _parse_move_order(log_lines, player_id)
    my_spe = active_stats.get("spe", 100)
    opp_est_spe = opp.get("stats", {}).get("spe", 100)
    if move_order == "opp" and my_spe > opp_est_spe:
        # Opponent outsped us despite lower estimated speed -> likely scarf
        opp.setdefault("stats", {})["spe"] = int(opp_est_spe * 1.5)

    atk_est = _stat_estimation(active_stats.get("atk", 100), active_boosts.get("atk", 0))
    spa_est = _stat_estimation(active_stats.get("spa", 100), active_boosts.get("spa", 0))
    opp_def_est = _stat_estimation(opp_stats.get("def", 100), opp_boosts.get("def", 0))
    opp_spd_est = _stat_estimation(opp_stats.get("spd", 100), opp_boosts.get("spd", 0))

    physical_ratio = atk_est / opp_def_est if opp_def_est else 1.0
    special_ratio = spa_est / opp_spd_est if opp_spd_est else 1.0

    available_moves = [
        m for m in moves
        if not m.get("disabled") and m.get("pp", 1) not in (0, None)
    ]

    # Filter switch-in-only moves (Fake Out, First Impression, etc.)
    current_turn = _parse_current_turn(log_lines)
    switch_in_turn = _parse_switch_in_turn(log_lines, player_id)
    is_switch_in_turn = (current_turn <= switch_in_turn + 1)
    if not is_switch_in_turn:
        available_moves = [
            m for m in available_moves
            if not showdown_data.move_is_switch_in_only(m.get("id", ""))
        ]

    # Filter self-destruct moves unless it's a favorable trade
    # (only use when we're on last pokemon or opponent is low HP)
    my_remaining = sum(1 for p in team if not _is_fainted(p))
    opp_hp = opp.get("hp_pct", 100.0)
    if my_remaining > 1 and opp_hp > 30:
        available_moves = [
            m for m in available_moves
            if not showdown_data.move_is_self_destruct(m.get("id", ""))
        ]

    # Remove already-set hazards from available moves to prevent fallback selection
    opp_id_for_hazards = "p2" if player_id == "p1" else "p1"
    opp_hazard_conditions = _parse_side_conditions(log_lines, opp_id_for_hazards)
    opp_hazard_lower = [c.lower() for c in opp_hazard_conditions]
    hazard_name_map = {
        "stealthrock": "stealth rock",
        "spikes": "spikes",
        "stickyweb": "sticky web",
        "toxicspikes": "toxic spikes",
    }
    available_moves = [
        m for m in available_moves
        if m.get("id", "") not in hazard_name_map
        or hazard_name_map.get(m.get("id", ""), "") not in opp_hazard_lower
    ]

    available_switches = [p for p in team if not p.get("active") and not _is_fainted(p)]

    # Detect trapped state (Shadow Tag, Arena Trap, charge moves, etc.)
    # Showdown's request JSON includes "trapped": true when switching is impossible
    is_trapped = active_req.get("trapped", False) or any(
        "|trapped|" in line for line in log_lines[-20:]
    )
    if is_trapped:
        available_switches = []  # cannot switch when trapped

    # Pre-compute damage estimation (used by setup, slugfest, recovery, and switch decisions)
    my_hp_abs = _parse_current_hp(active_pokemon)
    my_max_hp_abs = 0
    cond_pre = active_pokemon.get("condition", "")
    cond_pre_m = re.match(r"(\d+)/(\d+)", cond_pre)
    if cond_pre_m:
        my_max_hp_abs = int(cond_pre_m.group(2))
    opp_species_dmg = opp.get("species", "")
    opp_types_dmg = opp.get("types", [])
    max_incoming_setup = 0
    if opp_species_dmg and opp_types_dmg and my_max_hp_abs > 0:
        max_incoming_setup = _estimate_opponent_max_damage(
            opp_species_dmg, opp_types_dmg,
            active_stats.get("def", 100), active_stats.get("spd", 100),
            active_pokemon.get("types", []),
            confirmed_ability=opp.get("ability", ""),
        )

    # Priority move check: if we have a priority move that can KO, use it instead of switching
    priority_ko_move = None
    for move in available_moves:
        if move.get("priority", 0) > 0:
            if _priority_can_ko(move, active_pokemon, opp, physical_ratio, special_ratio):
                priority_ko_move = move
                break

    # Detect switch loop: if we've switched 3+ times in a row recently, stop switching
    recent_switches = 0
    for line in reversed(log_lines[-30:]):
        if f"|switch|{player_id}a: " in line:
            recent_switches += 1
        elif f"|move|{player_id}a: " in line:
            break
    in_switch_loop = recent_switches >= 3

    # Determine if we should switch out (but not if we have a priority KO available)
    # If we have boosts, only switch if we lose the slugfest (boosts aren't saving us)
    has_positive_boosts = any(v > 0 for v in active_boosts.values())
    should_consider_switch = True
    if has_positive_boosts and my_max_hp_abs > 0 and max_incoming_setup > 0:
        # Check if boosts make us win the slugfest — if so, stay
        def_boost = active_boosts.get("def", 0) + active_boosts.get("spd", 0)
        boost_factor = 2.0 / (2.0 + def_boost) if def_boost > 0 else 1.0
        adjusted = int(max_incoming_setup * boost_factor)
        best_score = max(
            (_score_move(m, active_pokemon, opp, physical_ratio, special_ratio, active_boosts)
             for m in available_moves),
            default=0.0,
        )
        if best_score > 0 and adjusted > 0:
            opp_hp_now = opp.get("hp_pct", 100.0)
            our_turns = max(opp_hp_now / max(best_score / 3.0, 1.0), 1.0)
            their_turns = my_hp_abs / adjusted
            if our_turns <= their_turns:
                should_consider_switch = False  # we win — stay and fight

    if (priority_ko_move is None and available_switches
            and not in_switch_loop and should_consider_switch
            and _should_switch_out(request, opp)):
        # Prefer pivot moves (U-turn, Volt Switch) over raw switch —
        # BUT only if we survive the opponent's attack this turn.
        # If we're slower and opponent OHKOs us, pivot wastes the turn.
        is_faster = active_stats.get("spe", 100) > opp_stats.get("spe", 100)
        will_survive_turn = max_incoming_setup < my_hp_abs if my_hp_abs > 0 else False
        if will_survive_turn or is_faster:
            pivot_ids = {"uturn", "voltswitch", "flipturn"}
            for move in available_moves:
                if move.get("id", "") in pivot_ids:
                    return f"move {moves.index(move) + 1}{mega_suffix}"
        switch_cmd = _choose_best_switch(request, opp)
        if switch_cmd:
            return switch_cmd

    # Use the priority KO move if found
    if priority_ko_move is not None:
        return f"move {moves.index(priority_ko_move) + 1}{mega_suffix}"

    if available_moves:
        # Entry hazards setup (if opponent has >=3 mons remaining and not already set)
        opp_remaining = _count_opponent_remaining(log_lines, player_id)
        if opp_remaining >= 3:
            opp_id = "p2" if player_id == "p1" else "p1"
            opp_conditions = _parse_side_conditions(log_lines, opp_id)
            opp_conditions_lower = [c.lower() for c in opp_conditions]
            for i, move in enumerate(available_moves):
                move_id = move.get("id", "")
                if move_id in ("stealthrock", "spikes", "stickyweb", "toxicspikes"):
                    hazard_names = {
                        "stealthrock": "stealth rock",
                        "spikes": "spikes",
                        "stickyweb": "sticky web",
                        "toxicspikes": "toxic spikes",
                    }
                    hazard_name = hazard_names.get(move_id, "")
                    if hazard_name and hazard_name in opp_conditions_lower:
                        continue
                    return f"move {moves.index(move) + 1}{mega_suffix}"

        # Pre-compute: do we have a recovery move?
        has_recovery = any(
            showdown_data.get_move(m.get("id", "")) and
            showdown_data.get_move(m.get("id", "")).get("isHeal") and
            showdown_data.get_move(m.get("id", "")).get("category") == "Status" and
            showdown_data.get_move(m.get("id", "")).get("target") == "self"
            for m in available_moves
        )

        # Hazard removal
        my_conditions = _parse_side_conditions(log_lines, player_id)
        if my_conditions:
            for i, move in enumerate(available_moves):
                if move.get("id") in ("rapidspin", "defog"):
                    return f"move {moves.index(move) + 1}{mega_suffix}"

        # =================================================================
        # Status moves: Toxic and recovery (action-turn theory)
        #
        # Toxic: 1-turn investment → opponent takes increasing residual damage
        #   each turn (1/16, 2/16, 3/16...). With recovery, we outlast them.
        #   Worth using when: opponent isn't already poisoned, we can survive
        #   long enough for poison to KO (i.e., we have recovery or high bulk).
        #
        # Recovery: extends our action turns. Use when HP is below threshold
        #   and incoming damage is survivable.
        #
        # Haze: resets opponent boosts. Use when opponent has boosted.
        # =================================================================

        # --- Toxic: apply poison if we can wall the opponent ---
        # Parse opponent status from log
        opp_status = ""
        opp_id_status = "p2" if player_id == "p1" else "p1"
        for line in reversed(log_lines):
            if f"|switch|{opp_id_status}a:" in line or f"|drag|{opp_id_status}a:" in line:
                break  # status resets on switch
            if f"|-status|{opp_id_status}a:" in line:
                parts = line.split("|")
                if len(parts) > 3:
                    opp_status = parts[3].strip()
                break
        if not opp_status:  # opponent not already statused
            for move in available_moves:
                if move.get("id") in ("toxic", "willowisp"):
                    move_sd = showdown_data.get_move(move.get("id", ""))
                    if not move_sd:
                        continue
                    # Only use if we can survive multiple turns (wall check)
                    if max_incoming_setup > 0 and my_hp_abs > 0:
                        survive_turns = _count_action_turns(
                            my_hp_abs, max_incoming_setup,
                            my_max_hp_abs // 2 if has_recovery else 0,
                        )
                        if survive_turns >= 4:
                            # We can wall → poison is the best win condition
                            return f"move {moves.index(move) + 1}{mega_suffix}"

        # --- Haze: reset opponent boosts ---
        if any(v > 0 for v in opp_boosts.values()):
            for move in available_moves:
                if move.get("id") == "haze":
                    return f"move {moves.index(move) + 1}{mega_suffix}"

        # --- Recovery: heal when HP is low and we can survive ---
        if has_recovery and my_max_hp_abs > 0:
            hp_pct = (my_hp_abs / my_max_hp_abs * 100) if my_max_hp_abs > 0 else 100
            recovery_amount = my_max_hp_abs // 2
            # Use recovery if: HP below 50% AND incoming won't KO us next turn
            # OR HP below 70% AND we're walling (incoming < recovery)
            is_walling = max_incoming_setup < recovery_amount
            should_recover = (
                (hp_pct < 50 and max_incoming_setup < my_hp_abs)
                or (hp_pct < 70 and is_walling)
            )
            if should_recover:
                for move in available_moves:
                    sd_heal = showdown_data.get_move(move.get("id", ""))
                    if (sd_heal and sd_heal.get("isHeal")
                            and sd_heal.get("category") == "Status"
                            and sd_heal.get("target") == "self"):
                        return f"move {moves.index(move) + 1}{mega_suffix}"

        # =================================================================
        # Action-turn accounting: compare "attack now" vs "setup first"
        # by estimating how many total action turns each path yields.
        #
        # action_turns_now:  survive turns with current stats
        # action_turns_setup: spend 1 turn setting up → survive turns
        #                     with boosted stats (+ recovery if available)
        # If setup path yields more net action turns → setup is worth it.
        # =================================================================

        _pivot_ids_setup = {"uturn", "voltswitch", "flipturn"}
        survives_setup_turn = (max_incoming_setup < my_hp_abs) if my_hp_abs > 0 else False

        # Recovery detection (already computed above)
        recovery_per_turn = my_max_hp_abs // 2 if (my_max_hp_abs > 0 and has_recovery) else 0

        # Current incoming damage (adjusted for existing boosts)
        current_incoming = _estimate_incoming_after_boost(
            active_boosts, max_incoming_setup, opp.get("species", ""),
        )

        # Current best attack score (excluding pivots for "stay and fight" evaluation)
        best_atk_now = max(
            (_score_move(m, active_pokemon, opp, physical_ratio, special_ratio, active_boosts)
             for m in available_moves if m.get("id", "") not in _pivot_ids_setup),
            default=0.0,
        )

        # How many turns can we act right now?
        my_action_turns_now = _count_action_turns(my_hp_abs, current_incoming, recovery_per_turn)

        # Evaluate each setup move
        best_setup_move = None
        best_setup_gain = 0.0  # must be positive to justify setup

        if survives_setup_turn:
            opp_hp_pct = opp.get("hp_pct", 100.0)

            for move in available_moves:
                sd_setup = showdown_data.get_move(move.get("id", ""))
                if not sd_setup:
                    continue
                boosts = sd_setup.get("boosts") or {}
                if not boosts or sd_setup.get("category") != "Status":
                    continue
                if sum(v for v in boosts.values() if v > 0) < 2:
                    continue
                if (sd_setup.get("target", move.get("target", "")) != "self"):
                    continue
                # Already maxed?
                if all(active_boosts.get(s, 0) >= 6 for s, v in boosts.items() if v > 0):
                    continue

                # Simulate boosts after setup
                sim_boosts = dict(active_boosts)
                for stat, val in boosts.items():
                    sim_boosts[stat] = min(sim_boosts.get(stat, 0) + val, 6)

                # Attack score after setup
                atk_after = max(
                    (_score_move(m, active_pokemon, opp, physical_ratio, special_ratio, sim_boosts)
                     for m in available_moves if m.get("id", "") not in _pivot_ids_setup),
                    default=0.0,
                )
                if atk_after <= 0:
                    continue  # no effective attack even after boosting — skip

                # Incoming damage after setup (defensive boosts applied)
                incoming_after = _estimate_incoming_after_boost(
                    sim_boosts, max_incoming_setup, opp.get("species", ""),
                )

                # HP after taking one hit during setup turn
                hp_after_setup = my_hp_abs - max_incoming_setup

                # Action turns after setup (with new survivability)
                action_turns_after = _count_action_turns(
                    hp_after_setup, incoming_after, recovery_per_turn,
                )

                # KO turns: how fast do we KO the opponent with/without setup?
                ko_turns_now = _turns_to_ko(best_atk_now, opp_hp_pct)
                ko_turns_after = _turns_to_ko(atk_after, opp_hp_pct)

                # Net gain from setup. Two benefits:
                # A) Survive longer (action_turns increase) — matters when we die before KO
                # B) KO faster (ko_turns decrease) — matters when we can already survive
                # Score = "can we KO before dying" improvement
                can_ko_now = my_action_turns_now >= ko_turns_now
                can_ko_after = action_turns_after >= ko_turns_after
                if can_ko_after and not can_ko_now:
                    # Setup turns a loss into a win — huge gain
                    gain = 5.0
                elif can_ko_after and can_ko_now:
                    # Both can KO, but setup might KO faster (saves HP for next matchup)
                    # Only worth it if we actually gain at least 1 turn
                    gain = ko_turns_now - ko_turns_after  # positive = faster KO after setup
                    if gain < 1.0:
                        gain = 0.0  # marginal speedup not worth a turn of setup
                elif not can_ko_after and not can_ko_now:
                    # Neither can KO — but setup might let us deal more total damage
                    # (action_turns_after * atk_after) vs (action_turns_now * best_atk_now)
                    total_dmg_now = my_action_turns_now * best_atk_now
                    total_dmg_after = action_turns_after * atk_after
                    gain = (total_dmg_after - total_dmg_now) / max(total_dmg_now, 1.0)
                else:
                    # Setup makes us die before KO when we could KO without — bad
                    gain = -5.0

                if gain > best_setup_gain:
                    best_setup_gain = gain
                    best_setup_move = move

        if best_setup_move is not None:
            return f"move {moves.index(best_setup_move) + 1}{mega_suffix}"

        # Slugfest check: if we can KO before they KO us, attack now
        if best_atk_now > 0 and current_incoming > 0 and my_hp_abs > 0:
            opp_hp_pct_now = opp.get("hp_pct", 100.0)
            our_ko = _turns_to_ko(best_atk_now, opp_hp_pct_now)
            their_ko = _count_action_turns(my_hp_abs, current_incoming, recovery_per_turn)
            if our_ko <= their_ko:
                best_move_obj = max(
                    available_moves,
                    key=lambda m: _score_move(m, active_pokemon, opp,
                                              physical_ratio, special_ratio, active_boosts),
                )
                return f"move {moves.index(best_move_obj) + 1}{mega_suffix}"

        # Recovery move evaluation
        # Use recovery when HP is low, not OHKO'd, and recovery helps survive.
        # If incoming damage < recovery amount (wall matchup), recover more aggressively.
        active_hp_pct = _hp_pct(active_pokemon)
        my_current_hp = _parse_current_hp(active_pokemon)
        my_max_hp = 0
        cond = active_pokemon.get("condition", "")
        cond_m = re.match(r"(\d+)/(\d+)", cond)
        if cond_m:
            my_max_hp = int(cond_m.group(2))
        if my_max_hp > 0 and active_hp_pct < 75.0:
            opp_species = opp.get("species", "")
            opp_types_for_dmg = opp.get("types", [])
            my_def = active_stats.get("def", 100)
            my_spd = active_stats.get("spd", 100)
            max_incoming = 0
            if opp_species and opp_types_for_dmg:
                max_incoming = _estimate_opponent_max_damage(
                    opp_species, opp_types_for_dmg, my_def, my_spd,
                    active_pokemon.get("types", []),
                    confirmed_ability=opp.get("ability", ""),
                )
            if max_incoming < my_current_hp:  # not OHKO'd
                recovery_amount = my_max_hp // 2
                hp_after_recovery = min(my_current_hp + recovery_amount, my_max_hp)
                # Wall matchup: incoming < recovery → recover at higher HP threshold
                is_wall_matchup = max_incoming < recovery_amount
                should_recover = False
                if is_wall_matchup and active_hp_pct < 70.0:
                    should_recover = True  # wall: recover aggressively
                elif not is_wall_matchup and active_hp_pct < 50.0:
                    # Not a wall: only recover if it pushes us out of 2HKO range
                    should_recover = (max_incoming * 2) < hp_after_recovery
                if should_recover:
                    for move in available_moves:
                        sd = showdown_data.get_move(move.get("id", ""))
                        if sd and sd.get("isHeal") and sd.get("category") == "Status":
                            if sd.get("target", "") == "self":
                                return f"move {moves.index(move) + 1}{mega_suffix}"

        # --- Advantageous position: predict opponent switch and choose best pivot ---
        # If we're clearly winning this matchup, the opponent may switch.
        # In that case, prefer moves that are good regardless of who comes in:
        #   - U-turn/Volt Switch: damage + see what switches in
        #   - Stealth Rock: chip all switch-ins
        #   - Status moves (Thunder Wave, Will-O-Wisp, Yawn): cripple any switch-in
        #   - Attacks with broad coverage across opponent's known team
        matchup_score = _estimate_matchup(
            active_pokemon.get("types", []), active_stats, _hp_pct(active_pokemon),
            opp.get("types", []), opp_stats, opp.get("hp_pct", 100.0),
        )
        opp_likely_to_switch = matchup_score > 1.5  # we're strongly winning

        if opp_likely_to_switch:
            # Collect opponent's known pokemon types for coverage calc
            opp_known_species = list(opp.get("opp_known_hp", {}).keys()) if "opp_known_hp" in opp else []
            # Also use team preview info from log (|poke| lines)
            opp_all_types: list[list[str]] = []
            opp_id_str = "p2" if player_id == "p1" else "p1"
            for line in log_lines:
                if f"|poke|{opp_id_str}|" in line:
                    parts = line.split("|")
                    if len(parts) >= 4:
                        sp = parts[3].split(",")[0].strip()
                        sp_types = _get_pokemon_types({"ident": f"{opp_id_str}: {sp}"})
                        if sp_types:
                            opp_all_types.append(sp_types)

            # Score each available move for "pivot value"
            best_pivot = None
            best_pivot_score = -1.0

            for move in available_moves:
                mid = move.get("id", "")
                sd = showdown_data.get_move(mid)
                if not sd:
                    continue

                pivot_score = 0.0

                # U-turn / Volt Switch: damage + switch advantage
                if mid in ("uturn", "voltswitch", "flipturn"):
                    pivot_score = 80.0  # high base value for pivot moves

                # Stealth Rock (not yet set)
                elif mid == "stealthrock":
                    opp_side = "p2" if player_id == "p1" else "p1"
                    opp_conds = _parse_side_conditions(log_lines, opp_side)
                    if "Stealth Rock" not in [c for c in opp_conds]:
                        opp_rem = _count_opponent_remaining(log_lines, player_id)
                        pivot_score = 60.0 * (opp_rem / 3.0)

                # Status moves: Thunder Wave, Will-O-Wisp, Yawn, Toxic
                elif mid in ("thunderwave", "willowisp", "yawn", "toxic", "toxicspikes",
                             "glare", "stunspore", "sleeppowder", "spore"):
                    pivot_score = 50.0  # cripples any switch-in

                # Spikes / Sticky Web (not yet set)
                elif mid in ("spikes", "stickyweb"):
                    opp_side = "p2" if player_id == "p1" else "p1"
                    opp_conds = _parse_side_conditions(log_lines, opp_side)
                    hazard_map = {"spikes": "Spikes", "stickyweb": "Sticky Web"}
                    if hazard_map.get(mid, "") not in opp_conds:
                        pivot_score = 45.0

                # Attacking move: score by coverage across opponent's team
                elif sd.get("basePower", 0) > 0:
                    move_type = sd.get("type", "").lower()
                    coverage_hits = 0
                    for opp_t in opp_all_types:
                        eff = _calc_type_effectiveness(move_type, opp_t)
                        if eff >= 1.0:
                            coverage_hits += 1
                    if opp_all_types:
                        coverage_ratio = coverage_hits / len(opp_all_types)
                    else:
                        coverage_ratio = 0.5
                    # Combine: normal score × coverage bonus
                    normal_score = _score_move(move, active_pokemon, opp, physical_ratio, special_ratio, active_boosts)
                    pivot_score = normal_score * (0.7 + 0.6 * coverage_ratio)

                if pivot_score > best_pivot_score:
                    best_pivot_score = pivot_score
                    best_pivot = move

            if best_pivot and best_pivot_score > 0:
                return f"move {moves.index(best_pivot) + 1}{mega_suffix}"

        # Score ALL moves: attacking moves via _score_move, status moves via context
        scored = []
        opp_spe_val = opp_stats.get("spe", 100)
        my_spe_val = active_stats.get("spe", 100)

        for move in available_moves:
            mid = move.get("id", "")
            sd = showdown_data.get_move(mid) if mid else None

            # Attacking move score
            atk_score = _score_move(move, active_pokemon, opp, physical_ratio, special_ratio, active_boosts)

            # Status move score (context-dependent)
            status_score = 0.0
            if sd and sd.get("category") == "Status" and atk_score == 0:
                # Will-O-Wisp: halve physical attacker's damage
                if mid == "willowisp":
                    opp_atk = opp_stats.get("atk", 100)
                    opp_spa = opp_stats.get("spa", 100)
                    if opp_atk >= opp_spa:  # physical or mixed attacker
                        status_score = 120.0  # very valuable
                    else:
                        status_score = 30.0  # less useful vs special

                # Thunder Wave: cripple fast opponent's speed
                elif mid in ("thunderwave", "glare", "stunspore"):
                    if opp_spe_val > my_spe_val:
                        status_score = 110.0  # outsped → paralyze is huge
                    else:
                        status_score = 40.0  # already faster, less value

                # Yawn: force switch or sleep
                elif mid == "yawn":
                    status_score = 80.0  # always good, forces action

                # Toxic: beats walls and recovery users
                elif mid == "toxic":
                    opp_has_rec = _opponent_used_recovery(log_lines, player_id)
                    status_score = 100.0 if opp_has_rec else 50.0

                # Sleep moves: very strong
                elif mid in ("spore", "sleeppowder", "hypnosis", "darkvoid", "lovelykiss"):
                    acc = sd.get("accuracy", 75)
                    if acc is True:
                        acc = 100
                    status_score = 130.0 * (acc / 100.0)

                # Encore: lock opponent into bad move
                elif mid == "encore":
                    status_score = 60.0

                # Taunt: shut down setup/recovery
                elif mid == "taunt":
                    status_score = 70.0

            final_score = max(atk_score, status_score)
            scored.append((move, final_score))

        if scored:
            best_move, best_score = max(scored, key=lambda x: x[1])
            if best_score > 0:
                # Check if we can't meaningfully damage the opponent — switch if possible
                if available_switches and not in_switch_loop:
                    opp_hp_pct = opp.get("hp_pct", 100.0)
                    # A move that 2HKOs typically scores 150+ (80bp * STAB * ratio * SE).
                    # If best_score < 40, we have no real offensive pressure.
                    # If best_score < 80 and opponent has recovery, they'll just heal it back.
                    opp_has_recovery = _opponent_used_recovery(log_lines, player_id)
                    should_bail = False
                    if best_score < 40 and opp_hp_pct > 30:
                        should_bail = True  # no effective attacks at all
                    elif opp_has_recovery and best_score < 80 and opp_hp_pct > 50:
                        should_bail = True  # can't break through recovery
                    if should_bail:
                        # Only switch if a teammate has a meaningfully better matchup.
                        # Prevents pointless back-and-forth when nobody can break through.
                        my_matchup = _estimate_matchup(
                            active_pokemon.get("types", []), active_stats, _hp_pct(active_pokemon),
                            opp.get("types", []), opp_stats, opp.get("hp_pct", 100.0),
                        )
                        switch_improves = any(
                            _estimate_matchup(
                                _get_pokemon_types(sw), sw.get("stats", {}), _hp_pct(sw),
                                opp.get("types", []), opp_stats, opp.get("hp_pct", 100.0),
                            ) > my_matchup + 0.5
                            for sw in available_switches
                        )
                        if switch_improves:
                            switch_cmd = _choose_best_switch(request, opp)
                            if switch_cmd:
                                return switch_cmd
                return f"move {moves.index(best_move) + 1}{mega_suffix}"
            # All moves score 0 (immune/no effect): switch if possible (unless looping)
            if available_switches and not in_switch_loop:
                switch_cmd = _choose_best_switch(request, opp)
                if switch_cmd:
                    return switch_cmd
            # No switch available: use first move as last resort
            return f"move {moves.index(available_moves[0]) + 1}{mega_suffix}"

    # Fallback to first move
    if moves:
        first_avail = next((m for m in moves if not m.get("disabled")), moves[0])
        return f"move {moves.index(first_avail) + 1}{mega_suffix}"

    # If we have switches, switch to best
    if available_switches:
        switch_cmd = _choose_best_switch(request, opp)
        return switch_cmd or "move 1"

    return "move 1"
