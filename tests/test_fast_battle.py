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


# ---------------------------------------------------------------------------
# Damage-based switch helpers
# ---------------------------------------------------------------------------


def test_estimate_opponent_max_damage_super_effective():
    """Garchomp (ground/dragon) attacking a steel type: ground is SE vs steel."""
    from pokechamp.fast_battle import _estimate_opponent_max_damage

    dmg = _estimate_opponent_max_damage("garchomp", ["ground", "dragon"], 150, 100, ["steel"])
    assert dmg > 0  # ground is super effective vs steel


def test_estimate_opponent_max_damage_immune():
    """Ground attack vs flying type should be 0 (immune)."""
    from pokechamp.fast_battle import _estimate_opponent_max_damage

    dmg = _estimate_opponent_max_damage("garchomp", ["ground"], 150, 100, ["flying"])
    # Ground vs flying = 0x, so ground type should be 0. Dragon vs flying = 1x.
    # With only ground type, should be 0.
    assert dmg == 0


def test_estimate_opponent_max_damage_unknown_species():
    """Unknown species returns 0 (can't estimate, don't switch)."""
    from pokechamp.fast_battle import _estimate_opponent_max_damage

    dmg = _estimate_opponent_max_damage("unknownmon99", ["fire"], 100, 100, ["grass"])
    assert dmg == 0


def test_estimate_opponent_speed():
    """Garchomp speed estimate should be a positive integer."""
    from pokechamp.fast_battle import _estimate_opponent_speed

    spe = _estimate_opponent_speed("garchomp")
    assert spe > 0


def test_should_switch_out_ohko():
    """Should switch out when opponent can OHKO active pokemon."""
    from pokechamp.fast_battle import _should_switch_out

    # Active pokemon is a low-HP steel type facing a fire/ground garchomp
    # Garchomp ground STAB is SE vs steel
    request = {
        "side": {
            "pokemon": [
                {
                    "active": True,
                    "condition": "30/180",  # very low HP
                    "types": ["steel"],
                    "stats": {"atk": 80, "def": 130, "spa": 60, "spd": 85, "spe": 70},
                    "boosts": {},
                },
                {
                    "active": False,
                    "condition": "175/175",
                    "types": ["water", "fairy"],
                    "stats": {"atk": 77, "def": 92, "spa": 125, "spd": 116, "spe": 60},
                    "boosts": {},
                },
            ]
        }
    }
    opponent = {
        "species": "garchomp",
        "types": ["dragon", "ground"],
        "hp_pct": 100.0,
        "stats": {},
    }
    result = _should_switch_out(request, opponent)
    assert result is True


def test_choose_best_switch_skips_ohko_target():
    """choose_best_switch should skip a switch target that would be OHKO'd."""
    from pokechamp.fast_battle import _choose_best_switch

    # Team: active (fainted placeholder), mon2 would be OHKO'd, mon3 is safe
    request = {
        "side": {
            "pokemon": [
                {
                    "active": True,
                    "condition": "0 fnt",
                    "types": ["normal"],
                    "stats": {"atk": 80, "def": 70, "spa": 70, "spd": 70, "spe": 90},
                },
                {
                    "active": False,
                    "condition": "10/180",  # very low HP — would be OHKO'd
                    "types": ["steel"],
                    "stats": {"atk": 80, "def": 130, "spa": 60, "spd": 85, "spe": 70},
                },
                {
                    "active": False,
                    "condition": "180/180",
                    "types": ["water", "fairy"],
                    "stats": {"atk": 77, "def": 92, "spa": 125, "spd": 116, "spe": 60},
                },
            ]
        }
    }
    opponent = {
        "species": "garchomp",
        "types": ["dragon", "ground"],
        "hp_pct": 100.0,
        "stats": {},
    }
    cmd = _choose_best_switch(request, opponent)
    # Should pick switch 3 (water/fairy), not switch 2 (steel with 10 HP)
    assert cmd == "switch 3"


def test_choose_action_priority_ko_prevents_switch():
    """When a priority move can KO, don't switch even if matchup is bad."""
    from pokechamp.fast_battle import _choose_action

    # Active Scizor (steel/bug) vs opponent grass type at 5% HP
    # Bullet Punch (priority) should be used to KO instead of switching
    request = {
        "active": [
            {
                "moves": [
                    {
                        "move": "Bullet Punch", "id": "bulletpunch", "pp": 24, "maxpp": 24,
                        "basePower": 40, "type": "Steel", "category": "Physical",
                        "accuracy": 100, "target": "normal", "disabled": False,
                        "priority": 1,
                    },
                    {
                        "move": "U-turn", "id": "uturn", "pp": 32, "maxpp": 32,
                        "basePower": 70, "type": "Bug", "category": "Physical",
                        "accuracy": 100, "target": "normal", "disabled": False,
                        "priority": 0,
                    },
                ]
            }
        ],
        "side": {
            "pokemon": [
                {
                    "active": True,
                    "condition": "140/140",
                    "types": ["steel", "bug"],
                    "stats": {"atk": 130, "def": 100, "spa": 55, "spd": 80, "spe": 65},
                    "boosts": {},
                },
                {
                    "active": False,
                    "condition": "160/160",
                    "types": ["dragon", "ground"],
                    "stats": {"atk": 130, "def": 95, "spa": 80, "spd": 85, "spe": 102},
                    "boosts": {},
                },
            ]
        },
    }
    # Opponent grass type at very low HP (5%) — priority move should KO
    log_lines = ["|switch|p2a: Abomasnow|Abomasnow, L50|5/190"]
    action = _choose_action(request, log_lines, "p1")
    # Should use Bullet Punch (move 1) rather than switching
    assert action == "move 1"


def test_mega_type_changes_table():
    """MEGA_TYPE_CHANGES has correct entries for all type-changing megas."""
    from pokechamp.fast_battle import MEGA_TYPE_CHANGES

    assert len(MEGA_TYPE_CHANGES) == 10

    assert MEGA_TYPE_CHANGES["charizard"] == {
        "base_types": ["fire", "flying"],
        "mega_types": ["fire", "dragon"],
    }
    assert MEGA_TYPE_CHANGES["aggron"] == {
        "base_types": ["steel", "rock"],
        "mega_types": ["steel"],
    }
    assert MEGA_TYPE_CHANGES["altaria"] == {
        "base_types": ["dragon", "flying"],
        "mega_types": ["dragon", "fairy"],
    }


def test_mega_valuable_abilities_table():
    """MEGA_VALUABLE_ABILITIES has correct entries."""
    from pokechamp.fast_battle import MEGA_VALUABLE_ABILITIES

    assert len(MEGA_VALUABLE_ABILITIES) == 2
    assert MEGA_VALUABLE_ABILITIES["clefable"]["check"] == "opponent_has_boosts"
    assert MEGA_VALUABLE_ABILITIES["venusaur"]["check"] == "weather_is_sun"


def test_parse_weather_sun():
    """_parse_weather detects sun from log."""
    from pokechamp.fast_battle import _parse_weather

    log_lines = [
        "|-weather|SunnyDay|[from] ability: Drought|[of] p1a: Torkoal",
        "|turn|2",
    ]
    assert _parse_weather(log_lines) == "sunnyday"


def test_parse_weather_none():
    """_parse_weather returns empty string when no weather."""
    from pokechamp.fast_battle import _parse_weather

    log_lines = [
        "|turn|1",
        "|move|p1a: Garchomp|Earthquake|p2a: Corviknight",
    ]
    assert _parse_weather(log_lines) == ""


def test_parse_weather_ends():
    """_parse_weather detects weather ending."""
    from pokechamp.fast_battle import _parse_weather

    log_lines = [
        "|-weather|SunnyDay|[from] ability: Drought|[of] p1a: Torkoal",
        "|turn|2",
        "|-weather|none",
    ]
    assert _parse_weather(log_lines) == ""

def test_parse_opponent_boosts():
    """_parse_opponent_boosts extracts stat boosts from log."""
    from pokechamp.fast_battle import _parse_opponent_boosts

    log_lines = [
        "|switch|p2a: Garchomp|Garchomp, L50, M|183/183",
        "|-boost|p2a: Garchomp|atk|2",
        "|-boost|p2a: Garchomp|spe|1",
    ]
    boosts = _parse_opponent_boosts(log_lines, "p1")
    assert boosts.get("atk", 0) == 2
    assert boosts.get("spe", 0) == 1
    assert boosts.get("def", 0) == 0


def test_parse_opponent_boosts_unboost():
    """_parse_opponent_boosts handles unboost correctly."""
    from pokechamp.fast_battle import _parse_opponent_boosts

    log_lines = [
        "|switch|p2a: Garchomp|Garchomp, L50, M|183/183",
        "|-boost|p2a: Garchomp|atk|2",
        "|-unboost|p2a: Garchomp|atk|1",
    ]
    boosts = _parse_opponent_boosts(log_lines, "p1")
    assert boosts.get("atk", 0) == 1


def test_parse_opponent_boosts_reset_on_switch():
    """Boosts reset when opponent switches."""
    from pokechamp.fast_battle import _parse_opponent_boosts

    log_lines = [
        "|switch|p2a: Garchomp|Garchomp, L50, M|183/183",
        "|-boost|p2a: Garchomp|atk|2",
        "|switch|p2a: Corviknight|Corviknight, L50, F|173/173",
        "|-boost|p2a: Corviknight|def|1",
    ]
    boosts = _parse_opponent_boosts(log_lines, "p1")
    assert boosts.get("atk", 0) == 0
    assert boosts.get("def", 0) == 1


# ---------------------------------------------------------------------------
# Mega evolution decision tests
# ---------------------------------------------------------------------------


def test_should_mega_evolve_default_true():
    """Pokemon not in any lookup table should always mega evolve."""
    from pokechamp.fast_battle import _should_mega_evolve

    assert _should_mega_evolve(
        species="Lopunny",
        active_types=["normal"],
        opp_types=["dragon", "ground"],
        opp_boosts={},
        weather="",
        moves=[{"id": "return", "basePower": 102, "type": "Normal", "category": "Physical"}],
    ) is True


def test_should_mega_evolve_type_change_increases_incoming_damage():
    """Charizard-X gains Dragon type, weak to Dragon from Dragon opponent."""
    from pokechamp.fast_battle import _should_mega_evolve

    assert _should_mega_evolve(
        species="Charizard",
        active_types=["fire", "flying"],
        opp_types=["dragon"],
        opp_boosts={},
        weather="",
        moves=[{"id": "flareblitz", "basePower": 120, "type": "Fire", "category": "Physical"}],
    ) is False


def test_should_mega_evolve_type_change_reduces_incoming_damage():
    """Aggron loses Rock type, reducing Water weakness."""
    from pokechamp.fast_battle import _should_mega_evolve

    assert _should_mega_evolve(
        species="Aggron",
        active_types=["steel", "rock"],
        opp_types=["water"],
        opp_boosts={},
        weather="",
        moves=[{"id": "ironhead", "basePower": 80, "type": "Steel", "category": "Physical"}],
    ) is True


def test_should_mega_evolve_type_change_reduces_stab():
    """Gyarados loses Flying STAB when best move is Flying type."""
    from pokechamp.fast_battle import _should_mega_evolve

    assert _should_mega_evolve(
        species="Gyarados",
        active_types=["water", "flying"],
        opp_types=["grass"],
        opp_boosts={},
        weather="",
        moves=[
            {"id": "bounce", "basePower": 85, "type": "Flying", "category": "Physical"},
            {"id": "waterfall", "basePower": 80, "type": "Water", "category": "Physical"},
        ],
    ) is False


def test_should_mega_evolve_clefable_unaware_with_boosts():
    """Clefable should NOT mega when opponent has stat boosts (Unaware is valuable)."""
    from pokechamp.fast_battle import _should_mega_evolve

    assert _should_mega_evolve(
        species="Clefable",
        active_types=["fairy"],
        opp_types=["normal"],
        opp_boosts={"atk": 2},
        weather="",
        moves=[{"id": "moonblast", "basePower": 95, "type": "Fairy", "category": "Special"}],
    ) is False


def test_should_mega_evolve_clefable_unaware_no_boosts():
    """Clefable SHOULD mega when opponent has no boosts."""
    from pokechamp.fast_battle import _should_mega_evolve

    assert _should_mega_evolve(
        species="Clefable",
        active_types=["fairy"],
        opp_types=["normal"],
        opp_boosts={},
        weather="",
        moves=[{"id": "moonblast", "basePower": 95, "type": "Fairy", "category": "Special"}],
    ) is True


def test_should_mega_evolve_venusaur_in_sun():
    """Venusaur should NOT mega in sun (Chlorophyll doubles speed)."""
    from pokechamp.fast_battle import _should_mega_evolve

    assert _should_mega_evolve(
        species="Venusaur",
        active_types=["grass", "poison"],
        opp_types=["water"],
        opp_boosts={},
        weather="sunnyday",
        moves=[{"id": "sludgebomb", "basePower": 90, "type": "Poison", "category": "Special"}],
    ) is False


def test_should_mega_evolve_venusaur_no_sun():
    """Venusaur SHOULD mega when no sun."""
    from pokechamp.fast_battle import _should_mega_evolve

    assert _should_mega_evolve(
        species="Venusaur",
        active_types=["grass", "poison"],
        opp_types=["water"],
        opp_boosts={},
        weather="",
        moves=[{"id": "sludgebomb", "basePower": 90, "type": "Poison", "category": "Special"}],
    ) is True


def test_choose_action_mega_evolves_by_default():
    """When canMegaEvo is true and no reason to skip, appends ' mega' to move."""
    from pokechamp.fast_battle import _choose_action

    request = {
        "active": [
            {
                "canMegaEvo": True,
                "moves": [
                    {"move": "Return", "id": "return", "pp": 32, "maxpp": 32,
                     "basePower": 102, "type": "Normal", "category": "Physical",
                     "accuracy": 100, "target": "normal", "disabled": False},
                ],
            }
        ],
        "side": {
            "pokemon": [
                {
                    "ident": "p1: Lopunny",
                    "active": True,
                    "condition": "151/151",
                    "types": ["normal"],
                    "stats": {"atk": 150, "def": 94, "spa": 54, "spd": 96, "spe": 170},
                    "boosts": {},
                }
            ]
        },
    }
    action = _choose_action(request, [], "p1")
    assert action.endswith(" mega"), f"Expected 'move N mega', got '{action}'"


def test_choose_action_no_mega_when_not_available():
    """When canMegaEvo is absent/false, no mega suffix."""
    from pokechamp.fast_battle import _choose_action

    request = {
        "active": [
            {
                "moves": [
                    {"move": "Return", "id": "return", "pp": 32, "maxpp": 32,
                     "basePower": 102, "type": "Normal", "category": "Physical",
                     "accuracy": 100, "target": "normal", "disabled": False},
                ],
            }
        ],
        "side": {
            "pokemon": [
                {
                    "ident": "p1: Lopunny",
                    "active": True,
                    "condition": "151/151",
                    "types": ["normal"],
                    "stats": {"atk": 150, "def": 94, "spa": 54, "spd": 96, "spe": 170},
                    "boosts": {},
                }
            ]
        },
    }
    action = _choose_action(request, [], "p1")
    assert "mega" not in action


def test_choose_action_skips_pp_zero_moves():
    """Moves with pp=0 should be filtered out."""
    from pokechamp.fast_battle import _choose_action

    request = {
        "active": [
            {
                "moves": [
                    {"move": "Earthquake", "id": "earthquake", "pp": 0, "maxpp": 16,
                     "basePower": 100, "type": "Ground", "category": "Physical",
                     "accuracy": 100, "target": "normal", "disabled": False},
                    {"move": "Stone Edge", "id": "stoneedge", "pp": 8, "maxpp": 8,
                     "basePower": 100, "type": "Rock", "category": "Physical",
                     "accuracy": 80, "target": "normal", "disabled": False},
                ],
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
    assert action.startswith("move 2")


def test_choose_action_skips_stealth_rock_when_already_set():
    """AI should not use Stealth Rock when already set on opponent's side."""
    from pokechamp.fast_battle import _choose_action

    log_lines = [
        # Three p2 switches seen so opp_remaining >= 3 and hazard setup block fires
        "|switch|p2a: Corviknight|Corviknight, L50, F|173/173",
        "|switch|p2a: Dracovish|Dracovish, L50|155/155",
        "|switch|p2a: Togekiss|Togekiss, L50, F|177/177",
        "|-sidestart|p2: p2|Stealth Rock",
    ]
    request = {
        "active": [
            {
                "moves": [
                    {"move": "Stealth Rock", "id": "stealthrock", "pp": 16, "maxpp": 16,
                     "basePower": 0, "type": "Rock", "category": "Status",
                     "accuracy": True, "target": "foeSide", "disabled": False},
                    {"move": "Earthquake", "id": "earthquake", "pp": 16, "maxpp": 16,
                     "basePower": 100, "type": "Ground", "category": "Physical",
                     "accuracy": 100, "target": "normal", "disabled": False},
                ],
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
                },
                {"ident": "p1: Corviknight", "active": False, "condition": "173/173",
                 "types": ["steel", "flying"], "stats": {"spe": 130}},
                {"ident": "p1: Primarina", "active": False, "condition": "155/155",
                 "types": ["water", "fairy"], "stats": {"spe": 112}},
            ]
        },
    }
    action = _choose_action(request, log_lines, "p1")
    assert action.startswith("move 2"), f"Expected 'move 2...', got '{action}'"


def test_parse_current_turn():
    """_parse_current_turn extracts current turn number from log."""
    from pokechamp.fast_battle import _parse_current_turn

    log_lines = ["|turn|1", "|move|p1a: Lopunny|Fake Out", "|turn|2"]
    assert _parse_current_turn(log_lines) == 2

    assert _parse_current_turn([]) == 0
    assert _parse_current_turn(["|turn|1"]) == 1


def test_parse_switch_in_turn():
    """_parse_switch_in_turn returns the turn when active pokemon switched in."""
    from pokechamp.fast_battle import _parse_switch_in_turn

    log_lines = [
        "|turn|1",
        "|switch|p1a: Lopunny|Lopunny, L50, F|151/151",
        "|turn|2",
        "|move|p1a: Lopunny|Return",
        "|turn|3",
    ]
    assert _parse_switch_in_turn(log_lines, "p1") == 1


def test_parse_switch_in_turn_mid_battle():
    """Switch in during mid-battle tracks latest switch."""
    from pokechamp.fast_battle import _parse_switch_in_turn

    log_lines = [
        "|turn|1",
        "|switch|p1a: Garchomp|Garchomp, L50, M|183/183",
        "|turn|2",
        "|switch|p1a: Lopunny|Lopunny, L50, F|151/151",
        "|turn|3",
    ]
    assert _parse_switch_in_turn(log_lines, "p1") == 2


def test_parse_switch_in_turn_before_turn1():
    """Initial switch before turn 1 returns turn 0."""
    from pokechamp.fast_battle import _parse_switch_in_turn

    log_lines = [
        "|switch|p1a: Lopunny|Lopunny, L50, F|151/151",
        "|turn|1",
    ]
    assert _parse_switch_in_turn(log_lines, "p1") == 0


def test_choose_action_fake_out_only_on_switch_in_turn():
    """Fake Out should only be used on the turn the pokemon switched in."""
    from pokechamp.fast_battle import _choose_action

    base_request = {
        "active": [
            {
                "moves": [
                    {"move": "Fake Out", "id": "fakeout", "pp": 16, "maxpp": 16,
                     "basePower": 40, "type": "Normal", "category": "Physical",
                     "accuracy": 100, "priority": 3, "target": "normal", "disabled": False},
                    {"move": "Return", "id": "return", "pp": 32, "maxpp": 32,
                     "basePower": 102, "type": "Normal", "category": "Physical",
                     "accuracy": 100, "priority": 0, "target": "normal", "disabled": False},
                ],
            }
        ],
        "side": {
            "pokemon": [
                {
                    "ident": "p1: Lopunny",
                    "active": True,
                    "condition": "151/151",
                    "types": ["normal"],
                    "stats": {"atk": 150, "def": 94, "spa": 54, "spd": 96, "spe": 170},
                    "boosts": {},
                }
            ]
        },
    }

    # Turn 2, Lopunny switched in before turn 1 → NOT switch-in turn → Fake Out filtered
    log_turn2 = [
        "|switch|p1a: Lopunny|Lopunny, L50, F|151/151",
        "|switch|p2a: Gengar|Gengar, L50, M|135/135",
        "|turn|1",
        "|move|p1a: Lopunny|Fake Out|p2a: Gengar",
        "|turn|2",
    ]
    action = _choose_action(base_request, log_turn2, "p1")
    # Should pick Return (move 2), not Fake Out
    assert action.startswith("move 2"), f"Expected 'move 2...', got '{action}'"
