"""Type-based fast filter for party building.

No battle simulation needed. Uses type chart to evaluate matchups instantly.
Screens the full 210-pokemon pool to surface threats and cover candidates.
"""
from __future__ import annotations

from pokechamp.damage import type_effectiveness
from pokechamp.loader import list_pokemon, load_pokemon
from pokechamp.models import TypeName


def _best_stab_effectiveness(
    attacker_types: list[TypeName],
    defender_types: list[TypeName],
) -> float:
    """Best type effectiveness from attacker's STAB moves against a defender.

    Returns the maximum multiplier achievable with any one of attacker's types.
    """
    best = 0.0
    for atk_type in attacker_types:
        eff = 1.0
        for def_type in defender_types:
            eff *= type_effectiveness(atk_type, def_type)
        best = max(best, eff)
    return best


def _worst_incoming_stab(
    defender_types: list[TypeName],
    attacker_types: list[TypeName],
) -> float:
    """Maximum effectiveness of attacker's STAB against defender.

    Higher = defender is more threatened. 4.0 = 4× weakness.
    """
    worst = 0.0
    for atk_type in attacker_types:
        eff = 1.0
        for def_type in defender_types:
            eff *= type_effectiveness(atk_type, def_type)
        worst = max(worst, eff)
    return worst


def find_threats(
    team_species: list[str],
    pool: list[str] | None = None,
) -> list[tuple[str, float]]:
    """Find pokemon in the pool that are hard for the current team to handle.

    A threat score is computed as:
      threat = max_incoming_stab_against_any_member / max_outgoing_stab_from_any_member
    where max_outgoing_stab < 1.0 means the team can't hit it super-effectively.

    Higher threat_score = harder to handle.

    Args:
        team_species: list of pokemon name_en strings in the current team.
        pool: list of candidate name_en strings to evaluate.
               Defaults to the full 210-pokemon pool.

    Returns:
        Sorted list of (species, threat_score) descending by threat.
    """
    if pool is None:
        pool = list_pokemon()

    team_members = [load_pokemon(s) for s in team_species]
    team_types_list = [m.types for m in team_members]

    results: list[tuple[str, float]] = []

    for candidate_name in pool:
        if candidate_name in team_species:
            continue
        try:
            candidate = load_pokemon(candidate_name)
        except FileNotFoundError:
            continue

        cand_types = candidate.types

        # How threatening is the candidate to ANY team member?
        max_damage_to_team = 0.0
        for member_types in team_types_list:
            incoming = _worst_incoming_stab(member_types, cand_types)
            max_damage_to_team = max(max_damage_to_team, incoming)

        # How well can ANY team member hit back?
        max_damage_from_team = 0.0
        for member_types in team_types_list:
            outgoing = _best_stab_effectiveness(member_types, cand_types)
            max_damage_from_team = max(max_damage_from_team, outgoing)

        # Avoid division by zero (immune to everything — extremely rare)
        if max_damage_from_team == 0.0:
            threat_score = max_damage_to_team * 4.0
        else:
            threat_score = max_damage_to_team / max_damage_from_team

        results.append((candidate_name, threat_score))

    results.sort(key=lambda x: x[1], reverse=True)
    return results


def suggest_additions(
    team_species: list[str],
    threats: list[str],
    pool: list[str] | None = None,
) -> list[tuple[str, float]]:
    """Suggest pokemon to add that cover the identified threats.

    A good addition:
    - Has STAB super-effective against top threats
    - Resists the threats' STAB types
    - Doesn't duplicate types already present in the team

    Cover score = offensive_score * defensive_score_bonus - type_redundancy_penalty

    Args:
        team_species: current team members (name_en list).
        threats: list of threatening pokemon name_en (ordered by threat, most dangerous first).
        pool: candidate pool; defaults to full 210-pokemon pool.

    Returns:
        Sorted list of (species, cover_score) descending.
    """
    if pool is None:
        pool = list_pokemon()

    # Load threat types
    threat_infos: list[list[TypeName]] = []
    for t in threats:
        try:
            threat_infos.append(load_pokemon(t).types)
        except FileNotFoundError:
            pass

    # Existing team types for redundancy check
    existing_types: set[TypeName] = set()
    for s in team_species:
        try:
            existing_types.update(load_pokemon(s).types)
        except FileNotFoundError:
            pass

    results: list[tuple[str, float]] = []

    for candidate_name in pool:
        if candidate_name in team_species:
            continue
        try:
            candidate = load_pokemon(candidate_name)
        except FileNotFoundError:
            continue

        cand_types = candidate.types

        if not threat_infos:
            # No threat info — just score by base stats total as tie-breaker
            score = 0.0
            results.append((candidate_name, score))
            continue

        # Offensive: average STAB effectiveness across top threats
        off_scores: list[float] = []
        for t_types in threat_infos:
            off_scores.append(_best_stab_effectiveness(cand_types, t_types))
        offensive = sum(off_scores) / len(off_scores)

        # Defensive: how well does this candidate resist the threats' STABs?
        # We want resistance (low multiplier = better); convert to a bonus.
        def_bonuses: list[float] = []
        for t_types in threat_infos:
            worst = _worst_incoming_stab(cand_types, t_types)
            # 0.25 → bonus 1.0, 0.5 → 0.75, 1.0 → 0.5, 2.0 → 0.25, 4.0 → 0.0
            # formula: bonus = 1.0 - worst/4.0  (capped at 0)
            bonus = max(0.0, 1.0 - worst / 4.0)
            def_bonuses.append(bonus)
        defensive_bonus = sum(def_bonuses) / len(def_bonuses)

        # Type redundancy penalty (0.0–0.3)
        new_types = set(cand_types)
        overlap = len(new_types & existing_types) / max(len(new_types), 1)
        redundancy_penalty = 0.3 * overlap

        score = offensive * (1.0 + defensive_bonus) - redundancy_penalty
        results.append((candidate_name, score))

    results.sort(key=lambda x: x[1], reverse=True)
    return results


def analyze_team(
    team_species: list[str],
    pool: list[str] | None = None,
    top_n: int = 10,
) -> dict:
    """Full team analysis: top threats + top cover suggestions.

    Returns:
        {
          "team": [...],
          "top_threats": [(species, score), ...],
          "suggested_additions": [(species, score), ...]
        }
    """
    threats = find_threats(team_species, pool=pool)
    top_threat_names = [t[0] for t in threats[:top_n]]
    suggestions = suggest_additions(team_species, top_threat_names, pool=pool)

    return {
        "team": team_species,
        "top_threats": threats[:top_n],
        "suggested_additions": suggestions[:top_n],
    }
