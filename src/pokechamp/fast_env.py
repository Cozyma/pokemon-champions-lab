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
# active: types(18) + stats(6) + hp(1) + status(1) + item(8) = 34
# moves: 4 * (bp + type_eff + stab + priority + category + is_setup + boost_total + is_heal + is_debuff) = 36
# opponent active: types(18) + stats(5) + hp(1) + status(1) + ability(3) + item(8) = 36
# opponent revealed moves: 4 * (bp + type_eff + stab + category) = 16
# bench (2 slots): 2 * (types(18) + stats(6) + hp(1) + move_eff(4) + item(8)) = 74
# opp team (6 slots): 6 * (type1 + type2 + phys_bias + bulk + spe + revealed + hp + alive) = 48
# own boosts: 7 (atk, def, spa, spd, spe, accuracy, evasion)
# opp boosts: 7
# weather: 8
# terrain: 4 (electric, grassy, misty, psychic)
# hazards: 6 (3 per side: rocks, spikes, tspikes)
# mega flags: 2
# force_switch: 1
# trapped: 1
# inference signals: 5 (speed order x3, overall speed ratio, current matchup speed)
# action mask: 9
# Total: 294
OBS_DIM = 294


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


# Item category encoding (8 categories)
_ITEM_CATEGORIES = {
    # Choice items (lock move, boost one stat)
    "choicescarf": 0, "choiceband": 0, "choicespecs": 0,
    # Life Orb
    "lifeorb": 1,
    # Focus Sash
    "focussash": 2,
    # Leftovers / Black Sludge (passive recovery)
    "leftovers": 3, "blacksludge": 3,
    # Berries
    "sitrusberry": 4, "lumberry": 4, "cheriberry": 4, "chestoberry": 4,
    "pechaberry": 4, "rawstberry": 4, "aspearberry": 4, "leppaberry": 4,
    "oranberry": 4, "persimberry": 4, "figyberry": 4, "wikiberry": 4,
    "magoberry": 4, "aguavberry": 4, "iapapaberry": 4,
    # Resist berries
    "occaberry": 4, "passhoberry": 4, "wacanberry": 4, "rindoberry": 4,
    "yacheberry": 4, "chopleberry": 4, "kebiaberry": 4, "shucaberry": 4,
    "cobaberry": 4, "payapaberry": 4, "tangaberry": 4, "chartiberry": 4,
    "kasibberry": 4, "habanberry": 4, "colburberry": 4, "babiriberry": 4,
    "chilanberry": 4, "roseliberry": 4,
    # Type-boosting items
    "mysticwater": 6, "charcoal": 6, "miracleseed": 6, "magnet": 6,
    "nevermeltice": 6, "blackbelt": 6, "poisonbarb": 6, "softsand": 6,
    "sharpbeak": 6, "twistedspoon": 6, "silverpowder": 6, "hardstone": 6,
    "spelltag": 6, "dragonfang": 6, "blackglasses": 6, "metalcoat": 6,
    "silkscarf": 6, "pixieplate": 6, "fairyfeather": 6,
    # Other boost items
    "expertbelt": 6, "wiseglasses": 6, "muscleband": 6,
    "scopelens": 6, "razorclaw": 6, "brightpowder": 6,
    "whiteherb": 7, "mentalherb": 7, "eviolite": 7,
    "heavydutyboots": 7, "airballoon": 7, "redcard": 7,
}
N_ITEM_CATEGORIES = 8  # 0-7


def _encode_item(item_id: str) -> list[float]:
    """Encode item as 8-dim one-hot category vector."""
    vec = [0.0] * N_ITEM_CATEGORIES
    key = item_id.lower().replace(" ", "").replace("-", "")
    # Mega stones (category 5)
    if key.endswith("ite") or key.endswith("inite") or key.endswith("nite"):
        if key not in _ITEM_CATEGORIES:  # not a berry ending in -ite
            vec[5] = 1.0
            return vec
    cat = _ITEM_CATEGORIES.get(key, 7)  # default: other
    vec[cat] = 1.0
    return vec


def _encode_status(status: str) -> float:
    """Encode status as 0-1."""
    status_map = {"": 0.0, "brn": 0.17, "frz": 0.33, "par": 0.5, "psn": 0.67, "tox": 0.67, "slp": 0.83, "fnt": 1.0}
    return status_map.get(status, 0.0)


def _parse_revealed_moves(
    log_lines: list[str], opp_id: str, current_opp_species: str,
) -> list[str]:
    """Extract opponent's revealed move IDs for current active pokemon."""
    revealed: list[str] = []
    tracking = False
    norm_species = current_opp_species.lower().replace("-", "").replace(" ", "")
    for line in log_lines:
        # Start tracking when the current species switches in
        if f"|switch|{opp_id}a:" in line or f"|drag|{opp_id}a:" in line:
            sp = line.split("|")
            if len(sp) > 3:
                sw_species = sp[3].split(",")[0].strip()
                if sw_species.lower().replace("-", "").replace(" ", "") == norm_species:
                    tracking = True
                    revealed = []
                else:
                    tracking = False
        # Track moves used
        if tracking and f"|move|{opp_id}a:" in line:
            parts = line.split("|")
            if len(parts) > 3:
                move_name = parts[3].strip()
                move_id = move_name.lower().replace(" ", "").replace("-", "")
                if move_id not in revealed:
                    revealed.append(move_id)
    return revealed[:4]


def _parse_boosts(log_lines: list[str], player_id: str) -> list[float]:
    """Parse current stat boosts for player's active pokemon. Returns 7 floats."""
    stat_keys = ["atk", "def", "spa", "spd", "spe", "accuracy", "evasion"]
    boosts = {k: 0 for k in stat_keys}
    for line in log_lines:
        # Reset on switch-in
        if f"|switch|{player_id}a:" in line or f"|drag|{player_id}a:" in line:
            boosts = {k: 0 for k in stat_keys}
        # |-boost|p1a: Garchomp|atk|2
        if f"|-boost|{player_id}a:" in line:
            parts = line.split("|")
            # parts: ['', '-boost', 'p1a: Garchomp', 'atk', '2', ...]
            if len(parts) >= 5:
                stat = parts[3].strip().lower()
                try:
                    amount = int(parts[4].strip())
                except (ValueError, IndexError):
                    amount = 1
                if stat in boosts:
                    boosts[stat] = min(boosts[stat] + amount, 6)
        # |-unboost|p1a: Garchomp|spe|1
        if f"|-unboost|{player_id}a:" in line:
            parts = line.split("|")
            if len(parts) >= 5:
                stat = parts[3].strip().lower()
                try:
                    amount = int(parts[4].strip())
                except (ValueError, IndexError):
                    amount = 1
                if stat in boosts:
                    boosts[stat] = max(boosts[stat] - amount, -6)
        # |-setboost|p1a: Mimikyu|atk|6
        if f"|-setboost|{player_id}a:" in line:
            parts = line.split("|")
            if len(parts) >= 5:
                stat = parts[3].strip().lower()
                try:
                    amount = int(parts[4].strip())
                except (ValueError, IndexError):
                    amount = 0
                if stat in boosts:
                    boosts[stat] = max(min(amount, 6), -6)
        # |-clearallboost  (no player specifier, clears all)
        if "|-clearallboost" in line:
            boosts = {k: 0 for k in stat_keys}
        # |-clearnegativeboost|p1a: Species
        if f"|-clearnegativeboost|{player_id}a:" in line:
            for k in stat_keys:
                if boosts[k] < 0:
                    boosts[k] = 0
        # |-clearpositiveboost|p1a: Species
        if f"|-clearpositiveboost|{player_id}a:" in line:
            for k in stat_keys:
                if boosts[k] > 0:
                    boosts[k] = 0
    return [boosts[k] / 6.0 for k in stat_keys]


def _parse_terrain(log_lines: list[str]) -> str:
    """Parse current terrain from log lines."""
    terrain = ""
    for line in log_lines:
        if "|-fieldstart|" in line:
            field = line.split("|-fieldstart|")[1].split("|")[0].strip().lower()
            if "terrain" in field:
                terrain = field.replace("move: ", "").replace(" ", "").lower()
        if "|-fieldend|" in line:
            field = line.split("|-fieldend|")[1].split("|")[0].strip().lower()
            if "terrain" in field:
                terrain = ""
    return terrain


def _parse_hazards(log_lines: list[str], player_id: str) -> list[float]:
    """Parse entry hazards for a given side. Returns 3 floats: rocks, spikes/3, tspikes/2."""
    rocks = 0
    spikes = 0
    tspikes = 0
    side_prefix = f"{player_id}: "
    for line in log_lines:
        if "|-sidestart|" in line and side_prefix in line:
            field = line.split("|")
            # |-sidestart|p1: Player1|Stealth Rock
            for part in field:
                low = part.strip().lower()
                if low == "stealth rock" or low == "move: stealth rock":
                    rocks = 1
                elif low == "spikes" or low == "move: spikes":
                    spikes = min(spikes + 1, 3)
                elif low == "toxic spikes" or low == "move: toxic spikes":
                    tspikes = min(tspikes + 1, 2)
        if "|-sideend|" in line and side_prefix in line:
            field = line.split("|")
            for part in field:
                low = part.strip().lower()
                if low == "stealth rock" or low == "move: stealth rock":
                    rocks = 0
                elif low == "spikes" or low == "move: spikes":
                    spikes = 0
                elif low == "toxic spikes" or low == "move: toxic spikes":
                    tspikes = 0
    return [float(rocks), spikes / 3.0, tspikes / 2.0]


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
    obs.extend(_encode_item(active_mon.get("item", "")))  # 8

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
            # Status move features
            is_setup = 0.0     # self-boost (Swords Dance, Iron Defense, etc.)
            boost_total = 0.0  # total boost stages / 6
            is_heal = 0.0      # recovery (Recover, Roost, etc.)
            is_debuff = 0.0    # opponent debuff or status (Toxic, Will-O-Wisp, Icy Wind, etc.)
            if sd:
                boosts = sd.get("boosts") or {}
                target = sd.get("target", "")
                if boosts and target == "self":
                    positive_sum = sum(v for v in boosts.values() if v > 0)
                    if positive_sum > 0:
                        is_setup = 1.0
                        boost_total = min(positive_sum / 6.0, 1.0)
                # Debuff: moves that lower opponent stats or inflict status
                if boosts and target in ("normal", "allAdjacentFoes", "allAdjacent"):
                    negative_sum = sum(-v for v in boosts.values() if v < 0)
                    if negative_sum > 0:
                        is_debuff = 1.0
                if sd.get("status") in ("brn", "par", "psn", "tox", "slp", "frz"):
                    is_debuff = 1.0
                # Secondary effect debuffs (Icy Wind spe-1, etc.)
                for sec in (sd.get("secondaries") or []):
                    if sec.get("boosts"):
                        neg = sum(-v for v in sec["boosts"].values() if v < 0)
                        if neg > 0:
                            is_debuff = 1.0
                # Single secondary (some moves use "secondary" not "secondaries")
                single_sec = sd.get("secondary") or {}
                if single_sec.get("boosts"):
                    neg = sum(-v for v in single_sec["boosts"].values() if v < 0)
                    if neg > 0:
                        is_debuff = 1.0
                if single_sec.get("status") in ("brn", "par", "psn", "tox", "slp", "frz"):
                    is_debuff = 1.0
                if sd.get("isHeal") and sd.get("category") == "Status":
                    is_heal = 1.0
            obs.extend([bp, eff, stab, pri, cat, is_setup, boost_total, is_heal, is_debuff])
            mask[i] = 1.0
        else:
            obs.extend([0.0] * 9)

    # --- Opponent active (28) ---
    obs.extend(_encode_types_onehot(opp_types))  # 18

    # Opponent stats from pokedex (base stats as proxy)
    opp_pokedex = showdown_data.load_pokedex()
    opp_key = opp_species.lower().replace(" ", "").replace("-", "") if opp_species else ""
    opp_entry = opp_pokedex.get(opp_key, {})
    opp_bs = opp_entry.get("baseStats", {})
    obs.append(opp_bs.get("atk", 80) / 200.0)
    obs.append(opp_bs.get("def", 80) / 200.0)
    obs.append(opp_bs.get("spa", 80) / 200.0)
    obs.append(opp_bs.get("spd", 80) / 200.0)
    obs.append(opp_bs.get("spe", 80) / 200.0)  # 5 dims

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
    obs.append(opp_hp)  # 1 dim
    obs.append(0.0)  # opponent status (unknown from log, placeholder)  # 1 dim

    # Opponent ability features (3 dims)
    # Parse confirmed ability from log
    opp_confirmed_ability = ""
    for line in reversed(log_lines[-50:]):
        if f"|switch|{opp_id}a:" in line or f"|drag|{opp_id}a:" in line:
            break
        if f"{opp_id}a:" in line and "[from] ability:" in line:
            idx = line.index("[from] ability:") + len("[from] ability: ")
            opp_confirmed_ability = line[idx:].split("|")[0].strip().lower().replace(" ", "")
            break
        if f"|-ability|{opp_id}a:" in line:
            parts = line.split("|")
            if len(parts) > 3:
                opp_confirmed_ability = parts[3].strip().lower().replace(" ", "")
            break

    # Feature 1: has contact punish (Rough Skin, Iron Barbs)
    if opp_confirmed_ability:
        has_contact_punish = 1.0 if showdown_data.ability_has_contact_punish(opp_confirmed_ability) else 0.0
    elif opp_species:
        has_contact_punish = 1.0 if showdown_data.species_may_have_contact_punish(opp_species) else 0.0
    else:
        has_contact_punish = 0.0

    # Feature 2: has type immunity ability (Levitate, Flash Fire, etc.)
    has_immunity = 0.0
    if opp_confirmed_ability:
        has_immunity = 1.0 if showdown_data.ability_grants_type_immunity(opp_confirmed_ability) else 0.0
    elif opp_species:
        has_immunity = 1.0 if showdown_data.species_type_immunities(opp_species) else 0.0

    # Feature 3: has damage reduction (Thick Fat, Filter, etc.)
    has_reduction = 0.0
    if opp_confirmed_ability:
        has_reduction = 1.0 if showdown_data.ability_damage_modifier(opp_confirmed_ability, "", is_supereffective=True) < 1.0 else 0.0
    elif opp_species:
        # Check any ability
        for ab in showdown_data.get_species_abilities(opp_species):
            if showdown_data.ability_damage_modifier(ab, "fire") < 1.0 or showdown_data.ability_damage_modifier(ab, "ice") < 1.0:
                has_reduction = 1.0
                break

    obs.append(has_contact_punish)
    obs.append(has_immunity)
    obs.append(has_reduction)  # 3 dims

    # Opponent item (8) — from log if revealed (Knock Off, Trick, etc.)
    opp_item = ""
    for line in reversed(log_lines[-50:]):
        if f"|switch|{opp_id}a:" in line:
            break
        if f"|-enditem|{opp_id}a:" in line or f"|-item|{opp_id}a:" in line:
            parts = line.split("|")
            if len(parts) > 3:
                opp_item = parts[3].strip()
            break
    obs.extend(_encode_item(opp_item))  # 8

    # --- Opponent revealed moves (16) ---
    revealed_moves = _parse_revealed_moves(log_lines, opp_id, opp_species)
    for i in range(N_MOVES):
        if i < len(revealed_moves):
            rm_id = revealed_moves[i]
            rm_sd = showdown_data.get_move(rm_id)
            rm_bp = (rm_sd.get("basePower", 0) if rm_sd else 0) / 250.0
            rm_type = (rm_sd.get("type", "") if rm_sd else "").lower()
            rm_eff = _calc_type_effectiveness(rm_type, types) / 4.0 if types else 0.25
            rm_stab = 1.0 if rm_type in opp_types else 0.0
            rm_cat_map = {"Physical": 1.0, "Special": 0.5, "Status": 0.0}
            rm_cat = rm_cat_map.get(rm_sd.get("category", "") if rm_sd else "", 0.0)
            obs.extend([rm_bp, rm_eff, rm_stab, rm_cat])
        else:
            obs.extend([0.0] * 4)

    # --- Bench pokemon (58) - 2 slots × 29 dims ---
    # Encode non-active team members with full info for switch decisions
    bench = [p for p in team if not p.get("active") and p.get("condition", "") != "0 fnt"]
    for i in range(2):
        if i < len(bench):
            b_mon = bench[i]
            # Types (18)
            b_species = b_mon.get("ident", "").split(": ", 1)[-1] if b_mon else ""
            b_types = _species_types(b_species)
            obs.extend(_encode_types_onehot(b_types))
            # Stats (6): atk/def/spa/spd/spe/hp normalized
            b_stats = b_mon.get("stats", {})
            obs.append(b_stats.get("atk", 100) / 200.0)
            obs.append(b_stats.get("def", 100) / 200.0)
            obs.append(b_stats.get("spa", 100) / 200.0)
            obs.append(b_stats.get("spd", 100) / 200.0)
            obs.append(b_stats.get("spe", 100) / 200.0)
            # HP stat from condition (max HP)
            b_cond = b_mon.get("condition", "100/100")
            b_hp_frac, _ = _parse_condition(b_cond)
            b_max_hp_m = re.match(r"\d+/(\d+)", b_cond)
            b_max_hp = int(b_max_hp_m.group(1)) / 300.0 if b_max_hp_m else 0.5
            obs.append(b_max_hp)
            # Current HP fraction (1)
            obs.append(b_hp_frac)
            # Move effectiveness vs opponent active (4)
            b_moves = b_mon.get("moves", [])
            for mi in range(4):
                if mi < len(b_moves):
                    m_id = b_moves[mi] if isinstance(b_moves[mi], str) else b_moves[mi].get("id", "")
                    m_sd = showdown_data.get_move(m_id)
                    if m_sd and m_sd.get("basePower", 0) > 0:
                        m_type = m_sd.get("type", "").lower()
                        m_eff = _calc_type_effectiveness(m_type, opp_types) / 4.0 if opp_types else 0.25
                        obs.append(m_eff)
                    else:
                        obs.append(0.0)
                else:
                    obs.append(0.0)
            # Item (8)
            obs.extend(_encode_item(b_mon.get("item", "")))
        else:
            obs.extend([0.0] * 37)  # 29 + 8 = 37 per bench slot

    # --- Opponent team slots (48) - 6 slots × 8 dims ---
    # Parse opponent team from |poke| lines (team preview) and track HP/faint
    opp_team_species: list[str] = []
    for line in log_lines:
        if f"|poke|{opp_id}|" in line:
            parts = line.split("|")
            if len(parts) >= 4:
                sp = parts[3].split(",")[0].strip()
                opp_team_species.append(sp)

    # Track which opponent pokemon have been seen in battle and their HP
    opp_seen_hp: dict[str, float] = {}  # species_key -> hp_fraction
    opp_fainted_set: set[str] = set()
    for line in log_lines:
        # Track switches (reveals pokemon)
        if f"|switch|{opp_id}a:" in line or f"|drag|{opp_id}a:" in line:
            parts = line.split("|")
            if len(parts) > 3:
                sw_sp = parts[3].split(",")[0].strip()
                sw_key = sw_sp.lower().replace(" ", "").replace("-", "")
                if sw_key not in opp_seen_hp:
                    opp_seen_hp[sw_key] = 1.0
                # Parse HP from condition in switch line
                if len(parts) > 4:
                    cond = parts[4].strip() if len(parts) > 4 else ""
                    hp_m = re.match(r"(\d+)/(\d+)", cond)
                    if hp_m:
                        opp_seen_hp[sw_key] = int(hp_m.group(1)) / int(hp_m.group(2))
        # Track damage/heal
        if f"|-damage|{opp_id}a:" in line or f"|-heal|{opp_id}a:" in line:
            parts = line.split("|")
            if len(parts) > 3:
                # Find current species from most recent switch
                cur_key = opp_species.lower().replace(" ", "").replace("-", "") if opp_species else ""
                hp_str = parts[3].strip().split()[0] if len(parts) > 3 else ""
                hp_m = re.match(r"(\d+)/(\d+)", hp_str)
                if hp_m and cur_key:
                    opp_seen_hp[cur_key] = int(hp_m.group(1)) / int(hp_m.group(2))
                elif "fnt" in hp_str and cur_key:
                    opp_seen_hp[cur_key] = 0.0
        # Track faints
        if f"|faint|{opp_id}a:" in line:
            parts = line.split("|")
            if len(parts) > 2:
                faint_name = parts[2].split(":")[1].strip() if ":" in parts[2] else ""
                faint_key = faint_name.lower().replace(" ", "").replace("-", "")
                opp_fainted_set.add(faint_key)
                opp_seen_hp[faint_key] = 0.0

    pokedex = showdown_data.load_pokedex()
    for i in range(6):
        if i < len(opp_team_species):
            sp = opp_team_species[i]
            sp_key = sp.lower().replace(" ", "").replace("-", "")
            entry = pokedex.get(sp_key, {})
            bs = entry.get("baseStats", {})
            sp_types = _species_types(sp)

            # type1_idx / 18, type2_idx / 18
            t1_idx = TYPE_TO_IDX.get(sp_types[0], 0) / 18.0 if sp_types else 0.0
            t2_idx = TYPE_TO_IDX.get(sp_types[1], 0) / 18.0 if len(sp_types) > 1 else 0.0
            # physical_bias
            atk_val = bs.get("atk", 80)
            spa_val = bs.get("spa", 80)
            phys_bias = max(min((atk_val - spa_val) / 200.0, 1.0), -1.0)
            # bulk_rating
            bulk = (bs.get("hp", 80) + bs.get("def", 80) + bs.get("spd", 80)) / 600.0
            # base_spe
            base_spe = bs.get("spe", 80) / 200.0
            # revealed, hp, alive
            revealed = 1.0 if sp_key in opp_seen_hp else 0.0
            hp_frac = opp_seen_hp.get(sp_key, 1.0)
            alive = 0.0 if sp_key in opp_fainted_set else 1.0

            obs.extend([t1_idx, t2_idx, phys_bias, bulk, base_spe, revealed, hp_frac, alive])
        else:
            obs.extend([0.0] * 8)

    # --- Own boosts (7) ---
    obs.extend(_parse_boosts(log_lines, player_id))

    # --- Opponent boosts (7) ---
    obs.extend(_parse_boosts(log_lines, opp_id))

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

    # --- Terrain (4) ---
    terrain_types = ["electricterrain", "grassyterrain", "mistyterrain", "psychicterrain"]
    current_terrain = _parse_terrain(log_lines)
    for t in terrain_types:
        obs.append(1.0 if current_terrain == t else 0.0)

    # --- Entry hazards (6) ---
    obs.extend(_parse_hazards(log_lines, player_id))   # own side: 3
    obs.extend(_parse_hazards(log_lines, opp_id))       # opp side: 3

    # --- Mega flags (2) ---
    can_mega = bool(active_req.get("canMegaEvo"))
    used_mega = "Mega" in details or "-Mega" in details
    obs.append(1.0 if can_mega else 0.0)
    obs.append(1.0 if used_mega else 0.0)

    # --- Force switch (1) ---
    obs.append(1.0 if is_force_switch else 0.0)

    # --- Trapped (1) ---
    obs.append(1.0 if is_trapped else 0.0)

    # --- Opponent inference signals (5) ---
    # Materials for inferring opponent's item/EV spread from battle observations.
    # 1-3: Move order last 3 turns (1.0 = we moved first, 0.0 = opp first, 0.5 = unknown)
    # 4: Times opponent moved first overall (ratio) — speed tier inference
    # 5: Opponent moved first THIS matchup (since switch-in) — current speed comparison
    #
    # Simple approach: scan log for move line order within each turn.
    we_first_count = 0
    opp_first_count = 0
    recent_order = [0.5, 0.5, 0.5]
    recent_idx = 0
    i_line = 0
    while i_line < len(log_lines):
        line = log_lines[i_line]
        if "|turn|" in line:
            # Scan moves in this turn
            our_pos, opp_pos = -1, -1
            for j in range(i_line + 1, min(i_line + 20, len(log_lines))):
                if "|turn|" in log_lines[j]:
                    break
                if f"|move|{player_id}a:" in log_lines[j] and our_pos < 0:
                    our_pos = j
                if f"|move|{opp_id}a:" in log_lines[j] and opp_pos < 0:
                    opp_pos = j
            if our_pos > 0 and opp_pos > 0:
                we_went_first = our_pos < opp_pos
                if we_went_first:
                    we_first_count += 1
                else:
                    opp_first_count += 1
                if recent_idx < 3:
                    recent_order[recent_idx] = 1.0 if we_went_first else 0.0
                    recent_idx += 1
        i_line += 1
    obs.extend(recent_order)  # 3 dims
    total_order = we_first_count + opp_first_count
    obs.append(we_first_count / max(total_order, 1))  # 1 dim: overall speed win ratio

    # Current matchup speed: did we move first since last switch-in?
    current_matchup_first = 0.5
    for line in reversed(log_lines):
        if f"|switch|{player_id}a:" in line or f"|switch|{opp_id}a:" in line:
            break
        if f"|move|{player_id}a:" in line:
            current_matchup_first = 1.0
            break
        if f"|move|{opp_id}a:" in line:
            current_matchup_first = 0.0
            break
    obs.append(current_matchup_first)  # 1 dim

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
        opponent_paste: str | None = None,
        opponent_pool: list[str] | None = None,
        team_pool: list[str] | None = None,
        format_id: str = "gen9championsbssregma",
        selection_model=None,
    ):
        """Create battle environment.

        Args:
            team_paste: RL agent's team (Showdown paste format)
            opponent_paste: Single opponent team (fixed matchup)
            opponent_pool: List of opponent teams (random each episode)
                          If both are None, opponent_paste defaults to team_paste.
            team_pool: List of p1 teams (random each episode).
                      If None, team_paste is used every episode.
            selection_model: Optional MaskablePPO for p1 team selection.
                            If None, uses heuristic _choose_action.
        """
        super().__init__()
        self.team_paste = team_paste
        self._team_pool = team_pool  # p1 team randomization
        self._opponent_pool = opponent_pool or ([opponent_paste] if opponent_paste else [team_paste])
        self.opponent_paste = self._opponent_pool[0]
        self.format_id = format_id
        self._selection_model = selection_model

        self.observation_space = spaces.Box(
            low=-1.0, high=1.0, shape=(OBS_DIM,), dtype=np.float32,
        )
        self.action_space = spaces.Discrete(N_ACTIONS)

        self._proc: subprocess.Popen | None = None
        self._log_lines: list[str] = []
        self._current_request: dict = {}
        self._turn = 0
        self._prev_obs: np.ndarray | None = None
        self._prev_action_balance: float = 0.0

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

        # Randomize p1 team from pool
        if self._team_pool and len(self._team_pool) > 1:
            idx = int(self.np_random.integers(0, len(self._team_pool)))
            self.team_paste = self._team_pool[idx]

        # Randomize opponent from pool
        if len(self._opponent_pool) > 1:
            idx = int(self.np_random.integers(0, len(self._opponent_pool)))
            self.opponent_paste = self._opponent_pool[idx]

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
        self._prev_action_balance = 0.0

        # Read initial output and get first request
        output = self._read_output(first=True)
        self._log_lines.extend(output)

        # Handle team preview for both sides
        requests = _parse_sideupdate_requests(output)

        # p1 team preview: use selection model if available, else heuristic
        if "p1" in requests and requests["p1"].get("teamPreview"):
            if self._selection_model is not None:
                from pokechamp.selection_env import encode_team_preview, TEAM_COMBOS
                sel_obs = encode_team_preview(requests["p1"], self._log_lines, "p1")
                sel_action, _ = self._selection_model.predict(
                    sel_obs, deterministic=True,
                )
                combo = TEAM_COMBOS[int(sel_action)]
                p1_action = "team " + "".join(str(i + 1) for i in combo)
            else:
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
        try:
            self._send(f">p1 {cmd}")
        except (BrokenPipeError, OSError):
            # Showdown process died — treat as loss
            return self._prev_obs, -1.0, True, False, {"turn": self._turn, "winner": "p2"}

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
        """Compute step reward based on action-turn balance theory.

        Core idea: reward = change in (my_action_turns - opp_action_turns).
        This naturally rewards:
        - Dealing damage (reduces opp survival → their action_turns drop)
        - Defensive boosts (reduces incoming → our action_turns increase)
        - Offensive boosts (faster KO → fewer turns needed)
        - Recovery (extends our action_turns)
        And naturally penalizes:
        - Taking damage (our action_turns drop)
        - Wasting a turn on immune moves (no opp damage, we take a hit)
        """
        if winner is not None:
            if winner == "p1":
                return 1.0
            elif winner == "p2":
                return -1.0
            return 0.0  # tie

        # --- Compute current action-turn balance ---
        from pokechamp.ai_decision import (
            _estimate_incoming_after_boost,
            _count_action_turns,
            _turns_to_ko,
        )

        team = self._current_request.get("side", {}).get("pokemon", [])
        active = next((p for p in team if p.get("active")), {})
        active_stats = active.get("stats", {})

        # Our HP
        my_hp = 0
        my_max_hp = 0
        cond = active.get("condition", "0/0")
        cond_m = re.match(r"(\d+)/(\d+)", cond)
        if cond_m:
            my_hp = int(cond_m.group(1))
            my_max_hp = int(cond_m.group(2))

        # Alive count (our remaining pokemon)
        my_alive = sum(1 for p in team if p.get("condition", "") != "0 fnt")

        # Opponent info from log
        from pokechamp.log_parser import _parse_opponent_from_log
        opp = _parse_opponent_from_log(self._log_lines, "p1")
        opp_hp_pct = opp.get("hp_pct", 100.0)
        opp_species = opp.get("species", "")
        opp_types = opp.get("types", [])

        # Estimate incoming damage
        from pokechamp.ai_scoring import (
            _estimate_opponent_max_damage,
            _score_move,
        )
        incoming = 0
        if opp_species and opp_types and my_max_hp > 0:
            incoming = _estimate_opponent_max_damage(
                opp_species, opp_types,
                active_stats.get("def", 100), active_stats.get("spd", 100),
                active.get("types", []),
            )

        # Check for recovery
        active_req = self._current_request.get("active", [{}])
        active_moves = (active_req[0] if active_req else {}).get("moves", [])
        has_recovery = any(
            showdown_data.get_move(m.get("id", "")) and
            showdown_data.get_move(m.get("id", "")).get("isHeal")
            for m in active_moves
        )
        recovery = my_max_hp // 2 if has_recovery else 0

        # Our best attack score
        active_boosts = active.get("boosts", {})
        phys_ratio = active_stats.get("atk", 100) / 100
        spec_ratio = active_stats.get("spa", 100) / 100
        best_atk = max(
            (_score_move(m, active, opp, phys_ratio, spec_ratio, active_boosts)
             for m in active_moves if m.get("id")),
            default=0.0,
        )

        # Compute action-turn balance
        my_action_turns = _count_action_turns(my_hp, incoming, recovery)
        opp_ko_turns = _turns_to_ko(best_atk, opp_hp_pct)

        # Balance: how many "useful" turns do we have?
        # useful = min(survive, KO) — no point living past KO
        # Also factor in remaining pokemon count
        my_useful = min(my_action_turns, opp_ko_turns) + (my_alive - 1) * 3
        opp_alive = 3 - sum(1 for line in self._log_lines if "|faint|p2a:" in line)
        opp_useful = opp_alive * 3  # rough estimate

        balance = my_useful - opp_useful

        # Reward = change in balance from previous step
        reward = (balance - self._prev_action_balance) * 0.05
        self._prev_action_balance = balance

        # Clamp to avoid extreme values
        reward = max(min(reward, 0.5), -0.5)

        # Keep immune penalty — clear bug signal
        recent = self._log_lines[-20:]
        for line in recent:
            if "|-immune|p2a:" in line:
                opp_switched = any("|switch|p2a:" in l and "[from]" not in l for l in recent)
                if not opp_switched:
                    reward -= 0.3

        return reward

    def action_masks(self) -> np.ndarray:
        """Return valid action mask (required by MaskablePPO from sb3-contrib).

        Returns boolean array: True = valid action, False = invalid.
        """
        return self.get_action_mask().astype(bool)

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
