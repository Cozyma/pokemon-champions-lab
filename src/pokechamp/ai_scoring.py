"""AI scoring, stat estimation, and matchup evaluation.

Move scoring with Showdown data enhancements, stat estimation from
base stats, and type-based matchup evaluation.
"""
from __future__ import annotations

import re

from pokechamp import showdown_data
from pokechamp.damage import type_effectiveness
from pokechamp.models import TypeName


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
    confirmed_ability: str = "",
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

    # Ability-based damage multiplier
    if confirmed_ability:
        mult = showdown_data.ability_attack_multiplier(confirmed_ability)
        if mult:
            _stat_name, factor = mult
            max_damage = int(max_damage * factor)
    else:
        for ab_id in showdown_data.get_species_abilities(opponent_species):
            mult = showdown_data.ability_attack_multiplier(ab_id)
            if mult:
                _stat_name, factor = mult
                max_damage = int(max_damage * (1.0 + (factor - 1.0) * 0.5))
                break

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


def _get_pokemon_types(mon: dict) -> list[str]:
    """Get a pokemon's types, falling back to pokedex lookup from ident."""
    types = mon.get("types", [])
    if types:
        return types
    # Request JSON doesn't include types for bench pokemon — look up from pokedex
    ident = mon.get("ident", "")
    species = ident.split(": ", 1)[-1] if ": " in ident else ""
    if species:
        pokedex = showdown_data.load_pokedex()
        key = species.lower().replace(" ", "").replace("-", "")
        entry = pokedex.get(key)
        if entry:
            return [t.lower() for t in entry.get("types", [])]
    return []


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
    active_boosts: dict | None = None,
) -> float:
    """Score a single move using base stats and Showdown data enhancements."""
    move_id = move.get("id", "")

    # Showdown request JSON doesn't include basePower/type/category — look up from cache
    sd_move = showdown_data.get_move(move_id) if move_id else None
    base_power = move.get("basePower") or (sd_move.get("basePower", 0) if sd_move else 0) or 0
    if base_power == 0:
        return 0.0
    move_type = (move.get("type") or (sd_move.get("type", "") if sd_move else "") or "").lower()
    active_types = [t.lower() for t in active_pokemon.get("types", [])]

    # STAB
    stab = 1.5 if move_type in active_types else 1.0

    # Category ratio
    category = (move.get("category") or (sd_move.get("category", "") if sd_move else "") or "").lower()
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
        expected_hits = sum(expected_hits) / len(expected_hits)

    score = base_power * stab * ratio * accuracy * expected_hits * effectiveness

    # --- Showdown data enhancements ---
    if move_id:
        # Type immunity via ability (e.g. Levitate blocks Ground)
        opp_ability = opponent.get("ability", "")
        opp_species = opponent.get("species", "")
        if opp_ability:
            immune_type = showdown_data.ability_grants_type_immunity(opp_ability)
            if immune_type and move_type == immune_type:
                return 0.0
        elif opp_species:
            possible_immunities = showdown_data.species_type_immunities(opp_species)
            if move_type in possible_immunities:
                score *= 0.5  # ~50% chance of immunity

        # Drain: reward HP recovery (e.g. +50% for Giga Drain)
        drain = showdown_data.move_drain_ratio(move_id)
        if drain > 0:
            score *= (1.0 + drain * 0.5)

        # Recoil: penalize self-damage (e.g. -25% for Brave Bird)
        recoil = showdown_data.move_recoil_ratio(move_id)
        if recoil > 0:
            score *= (1.0 - recoil * 0.75)

        # Self-debuff: penalize stat drops after attacking.
        # If the relevant stat is already deeply negative, apply an extra
        # penalty proportional to how far in the hole we already are.
        # e.g. Draco Meteor at spa=-6: extra * 2/(2+6)=0.25, making it
        # much weaker than Dragon Pulse despite higher base power.
        debuff_penalty = showdown_data.move_self_debuff_penalty(move_id)
        if debuff_penalty < 1.0 and active_boosts:
            m_data = showdown_data.get_move(move_id)
            if m_data and "selfBoosts" in m_data:
                for stat, drop in m_data["selfBoosts"].items():
                    if drop < 0:
                        current_boost = active_boosts.get(stat, 0)
                        if current_boost < 0:
                            # Extra penalty: 2 / (2 + |current_negative_boost|)
                            extra = 2 / (2 + abs(current_boost))
                            debuff_penalty *= extra
        score *= debuff_penalty

        # Two-turn moves: halve effective damage (charge/recharge = 2 turns for 1 hit)
        if showdown_data.move_is_two_turn(move_id):
            my_ability = active_pokemon.get("ability", "").lower().replace(" ", "")
            # Mega Sol allows Solar Beam/Blade without charging
            if move_id in ("solarbeam", "solarblade") and my_ability == "megasol":
                pass  # no penalty
            else:
                score *= 0.5

        # Contact move penalty (Rough Skin, Iron Barbs = 1/8 HP per hit)
        if showdown_data.move_is_contact(move_id):
            opp_ability = opponent.get("ability", "")
            opp_species = opponent.get("species", "")
            if opp_ability and showdown_data.ability_has_contact_punish(opp_ability):
                score *= 0.875  # confirmed contact-punish: -12.5%
            elif opp_species and showdown_data.species_may_have_contact_punish(opp_species):
                score *= 0.93  # possible contact-punish
            else:
                score *= 0.97  # unknown: small default penalty

        # Flinch bonus (only valuable when we're faster)
        flinch = showdown_data.move_flinch_chance(move_id)
        if flinch > 0:
            active_spe = active_pokemon.get("stats", {}).get("spe", 100)
            opp_spe = opponent.get("stats", {}).get("spe", 100)
            if active_spe > opp_spe:
                score *= (1.0 + flinch * 0.3)

        # Status infliction bonus
        status, chance = showdown_data.move_status_chance(move_id)
        if status and chance > 0:
            status_value = {"brn": 0.15, "par": 0.12, "psn": 0.05, "tox": 0.10, "slp": 0.20, "frz": 0.20}
            bonus = status_value.get(status, 0.05) * chance
            score *= (1.0 + bonus)

    return score


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
