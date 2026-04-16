"""Tests for fast_battle module."""
from __future__ import annotations

import pytest


# ---------------------------------------------------------------------------
# Paste → Packed conversion
# ---------------------------------------------------------------------------


def test_paste_to_packed_basic():
    from pokechamp.fast_battle import _paste_to_packed

    paste = """Garchomp @ Choice Scarf
Ability: Rough Skin
EVs: 2 HP / 32 Atk / 32 Spe
Jolly Nature
- Earthquake
- Outrage
- Dragon Claw
- Stone Edge"""
    packed = _paste_to_packed(paste)
    assert "Garchomp" in packed
    assert "Choice Scarf" in packed
    assert "Rough Skin" in packed
    assert "Earthquake,Outrage,Dragon Claw,Stone Edge" in packed
    assert "Jolly" in packed


def test_paste_to_packed_evs():
    from pokechamp.fast_battle import _paste_to_packed

    paste = """Garchomp @ Choice Scarf
Ability: Rough Skin
EVs: 2 HP / 32 Atk / 32 Spe
Jolly Nature
- Earthquake
- Outrage
- Dragon Claw
- Stone Edge"""
    packed = _paste_to_packed(paste)
    # EVs field: hp,atk,def,spa,spd,spe
    assert "2,32,0,0,0,32" in packed


def test_paste_to_packed_multi_pokemon():
    from pokechamp.fast_battle import _paste_to_packed

    paste = """Garchomp @ Choice Scarf
Ability: Rough Skin
EVs: 32 Atk / 32 Spe
Jolly Nature
- Earthquake
- Outrage
- Dragon Claw
- Stone Edge

Corviknight @ Leftovers
Ability: Pressure
EVs: 32 Atk / 32 Spe
Jolly Nature
- Iron Head
- Body Press
- Air Slash
- Flash Cannon"""
    packed = _paste_to_packed(paste)
    parts = packed.split("]")
    assert len(parts) == 2
    assert "Garchomp" in parts[0]
    assert "Corviknight" in parts[1]


def test_paste_to_packed_level_50():
    from pokechamp.fast_battle import _paste_to_packed

    paste = """Garchomp @ Choice Scarf
Ability: Rough Skin
EVs: 32 Atk / 32 Spe
Jolly Nature
- Earthquake
- Outrage
- Dragon Claw
- Stone Edge"""
    packed = _paste_to_packed(paste)
    # Should have level 50 (default)
    assert "|50|" in packed


# ---------------------------------------------------------------------------
# Type effectiveness helper
# ---------------------------------------------------------------------------


def test_calc_type_effectiveness_super_effective():
    from pokechamp.fast_battle import _calc_type_effectiveness

    # Fire vs Grass = 2.0
    assert _calc_type_effectiveness("fire", ["grass"]) == 2.0


def test_calc_type_effectiveness_immune():
    from pokechamp.fast_battle import _calc_type_effectiveness

    # Normal vs Ghost = 0.0
    assert _calc_type_effectiveness("normal", ["ghost"]) == 0.0


def test_calc_type_effectiveness_dual_type():
    from pokechamp.fast_battle import _calc_type_effectiveness

    # Water vs Fire/Rock = 2.0 * 2.0 = 4.0
    assert _calc_type_effectiveness("water", ["fire", "rock"]) == 4.0


def test_calc_type_effectiveness_unknown_type():
    from pokechamp.fast_battle import _calc_type_effectiveness

    # Unknown type returns 1.0
    assert _calc_type_effectiveness("???", ["grass"]) == 1.0


# ---------------------------------------------------------------------------
# Heuristic helpers
# ---------------------------------------------------------------------------


def test_hp_pct_full():
    from pokechamp.fast_battle import _hp_pct

    mon = {"condition": "155/155"}
    assert _hp_pct(mon) == pytest.approx(100.0)


def test_hp_pct_half():
    from pokechamp.fast_battle import _hp_pct

    mon = {"condition": "77/155"}
    assert _hp_pct(mon) == pytest.approx(49.677, abs=0.1)


def test_hp_pct_fainted():
    from pokechamp.fast_battle import _hp_pct

    assert _hp_pct({"condition": "0 fnt"}) == 0.0


def test_is_fainted():
    from pokechamp.fast_battle import _is_fainted

    assert _is_fainted({"condition": "0 fnt"})
    assert not _is_fainted({"condition": "100/100"})


def test_estimate_matchup_favourable():
    from pokechamp.fast_battle import _estimate_matchup

    # Dragon/Ground active vs Fire opponent
    # opp_incoming = max(ground vs fire=2.0, dragon vs fire=1.0) = 2.0
    # my_incoming = fire vs [dragon,ground] combined = fire_vs_dragon(0.5) * fire_vs_ground(1.0) = 0.5
    # speed bonus: 100 > 80 → +0.1
    # hp: equal → 0
    # total = 2.0 - 0.5 + 0.1 = 1.6
    score = _estimate_matchup(
        ["dragon", "ground"],  # active types
        {"spe": 100},  # active stats
        100.0,  # active HP
        ["fire"],  # opp types
        {"spe": 80},  # opp stats (slower)
        100.0,
    )
    assert score == pytest.approx(1.6, abs=0.01)


# ---------------------------------------------------------------------------
# Choose action
# ---------------------------------------------------------------------------


def test_choose_action_team_preview():
    from pokechamp.fast_battle import _choose_action

    request = {
        "teamPreview": True,
        "maxChosenTeamSize": 3,
        "side": {
            "pokemon": [
                {"ident": "p1: Garchomp"},
                {"ident": "p1: Corviknight"},
                {"ident": "p1: Primarina"},
                {"ident": "p1: Volcarona"},
                {"ident": "p1: Gengar"},
                {"ident": "p1: Hydreigon"},
            ]
        },
    }
    action = _choose_action(request, [], "p1")
    assert action == "team 123"


def test_choose_action_force_switch():
    from pokechamp.fast_battle import _choose_action

    request = {
        "forceSwitch": [True],
        "side": {
            "pokemon": [
                {"ident": "p1: Garchomp", "active": True, "condition": "0 fnt", "types": ["dragon", "ground"], "stats": {"spe": 100}},
                {"ident": "p1: Corviknight", "active": False, "condition": "173/173", "types": ["steel", "flying"], "stats": {"spe": 130}},
                {"ident": "p1: Primarina", "active": False, "condition": "155/155", "types": ["water", "fairy"], "stats": {"spe": 112}},
            ]
        },
    }
    action = _choose_action(request, [], "p1")
    assert action.startswith("switch ")


def test_choose_action_returns_move():
    from pokechamp.fast_battle import _choose_action

    request = {
        "active": [
            {
                "moves": [
                    {"move": "Earthquake", "id": "earthquake", "pp": 16, "maxpp": 16,
                     "basePower": 100, "type": "Ground", "category": "Physical",
                     "accuracy": 100, "target": "normal", "disabled": False},
                    {"move": "Outrage", "id": "outrage", "pp": 16, "maxpp": 16,
                     "basePower": 120, "type": "Dragon", "category": "Physical",
                     "accuracy": 100, "target": "randomNormal", "disabled": False},
                ]
            }
        ],
        "side": {
            "pokemon": [
                {
                    "ident": "p1: Garchomp",
                    "active": True,
                    "condition": "183/183",
                    "types": ["dragon", "ground"],
                    "stats": {"atk": 182, "def": 115, "spa": 90, "spd": 105, "spe": 169},
                    "boosts": {},
                }
            ]
        },
    }
    action = _choose_action(request, [], "p1")
    assert action.startswith("move ")


# ---------------------------------------------------------------------------
# Full battle integration test (requires Showdown)
# ---------------------------------------------------------------------------

TEAM_A_PASTE = """\
Garchomp @ Choice Scarf
Ability: Rough Skin
EVs: 32 Atk / 32 Spe
Jolly Nature
- Earthquake
- Outrage
- Dragon Claw
- Stone Edge

Corviknight @ Leftovers
Ability: Pressure
EVs: 32 Def / 32 SpD
Impish Nature
- Iron Head
- Body Press
- Air Slash
- Flash Cannon

Primarina @ Choice Specs
Ability: Torrent
EVs: 32 SpA / 32 Spe
Timid Nature
- Ice Beam
- Shadow Ball
- Psychic
- Moonblast

Volcarona @ Heavy-Duty Boots
Ability: Flame Body
EVs: 32 SpA / 32 Spe
Timid Nature
- Flamethrower
- Psychic
- Air Slash
- Quiver Dance

Gengar @ Choice Specs
Ability: Cursed Body
EVs: 32 SpA / 32 Spe
Timid Nature
- Thunderbolt
- Shadow Ball
- Sludge Bomb
- Psychic

Hydreigon @ Choice Specs
Ability: Levitate
EVs: 32 SpA / 32 Spe
Timid Nature
- Earthquake
- Flamethrower
- Dark Pulse
- Flash Cannon
"""

TEAM_B_PASTE = """\
Tyranitar @ Choice Band
Ability: Sand Stream
EVs: 32 Atk / 32 Spe
Adamant Nature
- Stone Edge
- Crunch
- Earthquake
- Ice Punch

Scizor @ Choice Band
Ability: Technician
EVs: 32 Atk / 32 Spe
Adamant Nature
- Bullet Punch
- U-turn
- Superpower
- Bug Bite

Togekiss @ Life Orb
Ability: Serene Grace
EVs: 32 SpA / 32 Spe
Timid Nature
- Air Slash
- Dazzling Gleam
- Flamethrower
- Nasty Plot

Arcanine @ Choice Band
Ability: Intimidate
EVs: 32 Atk / 32 Spe
Jolly Nature
- Flare Blitz
- Extreme Speed
- Wild Charge
- Close Combat

Lapras @ Leftovers
Ability: Water Absorb
EVs: 32 HP / 32 SpA
Modest Nature
- Ice Beam
- Surf
- Thunderbolt
- Freeze-Dry

Dragonite @ Choice Band
Ability: Multiscale
EVs: 32 Atk / 32 Spe
Adamant Nature
- Outrage
- Earthquake
- Fire Punch
- Extreme Speed
"""


@pytest.mark.integration
def test_run_battle_completes():
    """Full battle integration test. Requires Showdown engine."""
    from pokechamp.fast_battle import run_battle

    result = run_battle(
        TEAM_A_PASTE,
        TEAM_B_PASTE,
        format_id="gen9championsbssregma",
        seed=[1, 2, 3, 4],
    )
    assert result["winner"] in ("p1", "p2", None)
    assert result["turns"] > 0
    assert result["p1_remaining"] >= 0
    assert result["p2_remaining"] >= 0


@pytest.mark.integration
def test_run_battle_multiple_seeds():
    """Run multiple battles with different seeds to verify reproducibility."""
    from pokechamp.fast_battle import run_battle

    results = []
    for i in range(3):
        seed = [i * 4 + 1, i * 4 + 2, i * 4 + 3, i * 4 + 4]
        result = run_battle(TEAM_A_PASTE, TEAM_B_PASTE, seed=seed)
        results.append(result)

    # All should complete
    for r in results:
        assert r["winner"] in ("p1", "p2", None)
        assert r["turns"] > 0


@pytest.mark.integration
def test_run_battle_same_seed_reproducible():
    """Same seed should produce same result."""
    from pokechamp.fast_battle import run_battle

    seed = [42, 43, 44, 45]
    result1 = run_battle(TEAM_A_PASTE, TEAM_B_PASTE, seed=seed)
    result2 = run_battle(TEAM_A_PASTE, TEAM_B_PASTE, seed=seed)

    assert result1["winner"] == result2["winner"]
    assert result1["turns"] == result2["turns"]
