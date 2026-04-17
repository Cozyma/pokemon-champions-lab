"""Showdown data loader for AI decision-making.

Loads pre-extracted move and ability data from data/showdown-cache/.
Run `node scripts/extract_showdown_data.js` to regenerate the cache.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

CACHE_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "showdown-cache"


@lru_cache(maxsize=1)
def load_moves() -> dict[str, dict]:
    """Load all moves from the Showdown cache."""
    path = CACHE_DIR / "moves.json"
    if not path.exists():
        return {}
    with open(path) as f:
        return json.load(f)


@lru_cache(maxsize=1)
def load_abilities() -> dict[str, dict]:
    """Load all abilities from the Showdown cache."""
    path = CACHE_DIR / "abilities.json"
    if not path.exists():
        return {}
    with open(path) as f:
        return json.load(f)


def get_move(move_id: str) -> dict | None:
    """Look up a move by its Showdown ID (e.g. 'earthquake')."""
    return load_moves().get(move_id)


def get_ability(ability_id: str) -> dict | None:
    """Look up an ability by its Showdown ID (e.g. 'roughskin')."""
    return load_abilities().get(ability_id)


def move_drain_ratio(move_id: str) -> float:
    """Return HP recovery ratio for drain moves (e.g. 0.5 for Giga Drain).

    Returns 0.0 for non-drain moves.
    """
    m = get_move(move_id)
    if not m or "drain" not in m:
        return 0.0
    num, den = m["drain"]
    return num / den


def move_recoil_ratio(move_id: str) -> float:
    """Return recoil damage ratio (e.g. 0.33 for Brave Bird).

    Returns 0.0 for non-recoil moves.
    """
    m = get_move(move_id)
    if not m or "recoil" not in m:
        return 0.0
    num, den = m["recoil"]
    return num / den


def move_self_debuff_penalty(move_id: str) -> float:
    """Return a penalty multiplier for self-debuffing moves.

    e.g. Close Combat (def-1, spd-1) -> 0.85
         Draco Meteor (spa-2) -> 0.7
         V-create (spe-1, def-1, spd-1) -> 0.75
    Returns 1.0 for moves without self-debuffs.
    """
    m = get_move(move_id)
    if not m or "selfBoosts" not in m:
        return 1.0
    total_drop = sum(v for v in m["selfBoosts"].values() if v < 0)
    # Each -1 stage is roughly -10% effectiveness for subsequent turns
    # Penalty: 1.0 + total_drop * 0.1 (capped at 0.5 minimum)
    return max(0.5, 1.0 + total_drop * 0.1)


def move_is_two_turn(move_id: str) -> bool:
    """Return True if the move takes two turns (charge or recharge)."""
    m = get_move(move_id)
    if not m:
        return False
    return bool(m.get("recharge") or m.get("charge"))


# Moves that can only be used on the turn the pokemon switches in.
# Showdown encodes this in onTry conditions, not as a simple flag.
_SWITCH_IN_ONLY_MOVES = frozenset({"fakeout", "firstimpression"})


def move_is_switch_in_only(move_id: str) -> bool:
    """Return True if the move can only be used on the switch-in turn.

    Covers Fake Out, First Impression, etc.
    """
    if move_id in _SWITCH_IN_ONLY_MOVES:
        return True
    m = get_move(move_id)
    if not m:
        return False
    return bool(m.get("switchInOnly"))


def move_is_self_destruct(move_id: str) -> bool:
    """Return True if the move KOs the user."""
    m = get_move(move_id)
    if not m:
        return False
    return bool(m.get("selfdestruct"))


def move_flinch_chance(move_id: str) -> float:
    """Return flinch chance (0.0-1.0) for a move."""
    m = get_move(move_id)
    if not m:
        return 0.0
    sec = m.get("secondary", {})
    if sec.get("volatileStatus") == "flinch":
        return (sec.get("chance", 0)) / 100.0
    for s in m.get("secondaries", []):
        if s.get("volatileStatus") == "flinch":
            return (s.get("chance", 0)) / 100.0
    return 0.0


def move_status_chance(move_id: str) -> tuple[str, float]:
    """Return (status, chance) for status-inflicting moves.

    Returns ("", 0.0) if the move doesn't inflict status.
    """
    m = get_move(move_id)
    if not m:
        return ("", 0.0)
    # Direct status (e.g. Thunder Wave)
    if m.get("status") and m.get("category") == "Status":
        return (m["status"], 1.0)
    # Secondary status (e.g. Flamethrower 10% burn)
    sec = m.get("secondary", {})
    if sec.get("status"):
        return (sec["status"], sec.get("chance", 100) / 100.0)
    for s in m.get("secondaries", []):
        if s.get("status"):
            return (s["status"], s.get("chance", 100) / 100.0)
    return ("", 0.0)


def move_is_contact(move_id: str) -> bool:
    """Return True if the move makes contact."""
    m = get_move(move_id)
    if not m:
        return False
    return bool(m.get("contact"))


def ability_has_contact_punish(ability_id: str) -> bool:
    """Return True if the ability punishes contact moves (Rough Skin, Iron Barbs, etc.)."""
    a = get_ability(ability_id)
    if not a:
        return False
    return "contactPunish" in a.get("flags", [])


def ability_is_power_boost(ability_id: str) -> bool:
    """Return True if the ability boosts attack power."""
    a = get_ability(ability_id)
    if not a:
        return False
    flags = a.get("flags", [])
    return bool({"modifyAtk", "modifySpA", "modifyPower", "modifySTAB"} & set(flags))


@lru_cache(maxsize=1)
def load_pokedex() -> dict[str, dict]:
    """Load all species from the Showdown cache."""
    path = CACHE_DIR / "pokedex.json"
    if not path.exists():
        return {}
    with open(path) as f:
        return json.load(f)


def get_species_abilities(species: str) -> list[str]:
    """Return list of ability IDs for a species (e.g. ['sandveil', 'roughskin'])."""
    key = species.lower().replace(" ", "").replace("-", "")
    pokedex = load_pokedex()
    entry = pokedex.get(key)
    if not entry:
        return []
    return list(entry.get("abilities", {}).values())


# Type immunity abilities: ability_id -> immune_type
_TYPE_IMMUNITY_ABILITIES: dict[str, str] = {
    "levitate": "ground",
    "flashfire": "fire",
    "waterabsorb": "water",
    "voltabsorb": "electric",
    "sapsipper": "grass",
    "lightningrod": "electric",
    "stormdrain": "water",
    "motordrive": "electric",
    "dryskin": "water",
    "eartheater": "ground",
    "wellbakedbody": "fire",
}

# Attack multiplier abilities: ability_id -> (stat, multiplier)
_ATTACK_MULTIPLIER_ABILITIES: dict[str, tuple[str, float]] = {
    "hugepower": ("atk", 2.0),
    "purepower": ("atk", 2.0),
    "hustle": ("atk", 1.5),
    "gorillatactics": ("atk", 1.5),
}


def ability_grants_type_immunity(ability_id: str) -> str | None:
    """Return the type this ability grants immunity to, or None."""
    return _TYPE_IMMUNITY_ABILITIES.get(ability_id)


def ability_attack_multiplier(ability_id: str) -> tuple[str, float] | None:
    """Return (stat, multiplier) if ability boosts attack, else None."""
    return _ATTACK_MULTIPLIER_ABILITIES.get(ability_id)


def species_may_have_contact_punish(species: str) -> bool:
    """Return True if any of the species' possible abilities punishes contact."""
    for ab_id in get_species_abilities(species):
        if ability_has_contact_punish(ab_id):
            return True
    return False


def species_type_immunities(species: str) -> list[str]:
    """Return list of types this species might be immune to via abilities."""
    immunities = []
    for ab_id in get_species_abilities(species):
        immune_type = ability_grants_type_immunity(ab_id)
        if immune_type:
            immunities.append(immune_type)
    return immunities
