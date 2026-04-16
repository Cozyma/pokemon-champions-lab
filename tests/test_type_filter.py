"""Tests for type-based party builder filter (type_filter.py)."""
from __future__ import annotations

import pytest

from pokechamp.type_filter import (
    _best_stab_effectiveness,
    _worst_incoming_stab,
    analyze_team,
    find_threats,
    suggest_additions,
)
from pokechamp.models import TypeName


# ---------------------------------------------------------------------------
# Unit tests for internal helpers
# ---------------------------------------------------------------------------


class TestBestStabEffectiveness:
    def test_ice_vs_dragon_ground(self):
        """Ice vs Dragon/Ground (Garchomp) → 4× from Ice on Ground side."""
        result = _best_stab_effectiveness(
            [TypeName.ICE], [TypeName.DRAGON, TypeName.GROUND]
        )
        assert result == 4.0

    def test_fire_vs_steel(self):
        """Fire vs Steel → 2×."""
        result = _best_stab_effectiveness([TypeName.FIRE], [TypeName.STEEL])
        assert result == 2.0

    def test_normal_vs_ghost(self):
        """Normal vs Ghost → 0× (immune)."""
        result = _best_stab_effectiveness([TypeName.NORMAL], [TypeName.GHOST])
        assert result == 0.0

    def test_fire_water_vs_water(self):
        """Fire/Water attacker vs Water defender — best is Water 0.5, Fire 0.5 → max 0.5."""
        result = _best_stab_effectiveness(
            [TypeName.FIRE, TypeName.WATER], [TypeName.WATER]
        )
        assert result == 0.5

    def test_multiple_attack_types_picks_best(self):
        """Fire/Ground attacker vs Steel/Flying — Fire hits Steel 2×, Ground hits Flying 0×."""
        # Fire vs Steel = 2.0, Fire vs Flying = 1.0 → Fire: 2.0×1.0 = 2.0
        # Ground vs Steel = 2.0, Ground vs Flying = 0.0 → Ground: 2.0×0.0 = 0.0
        # best overall = 2.0
        result = _best_stab_effectiveness(
            [TypeName.FIRE, TypeName.GROUND], [TypeName.STEEL, TypeName.FLYING]
        )
        assert result == 2.0


class TestWorstIncomingStab:
    def test_ice_vs_dragon_ground(self):
        """Ice attack vs Dragon/Ground defender — 4× incoming."""
        result = _worst_incoming_stab(
            [TypeName.DRAGON, TypeName.GROUND], [TypeName.ICE]
        )
        assert result == 4.0

    def test_ghost_vs_normal_attacker(self):
        """Ghost type defender vs Normal attacker — 0× (immune)."""
        result = _worst_incoming_stab([TypeName.GHOST], [TypeName.NORMAL])
        assert result == 0.0

    def test_water_vs_fire_water_attacker(self):
        """Water/Fire attacker vs Water defender — worst = max(0.5, 0.5) = 0.5."""
        result = _worst_incoming_stab(
            [TypeName.WATER], [TypeName.FIRE, TypeName.WATER]
        )
        assert result == 0.5


# ---------------------------------------------------------------------------
# Integration tests using real pokemon data
# ---------------------------------------------------------------------------

# All 210 pokemon in the pool
ALL_POKEMON = None  # loaded lazily


def _all_pokemon():
    from pokechamp.loader import list_pokemon
    return list_pokemon()


class TestFindThreats:
    def test_ice_types_threaten_garchomp_team(self):
        """A team of Garchomp should be threatened by Ice-type pokemon."""
        pool = _all_pokemon()
        threats = find_threats(["garchomp"], pool=pool)
        threat_names = [t[0] for t in threats[:20]]

        # There should be ice-type pokemon near the top
        ice_found = False
        from pokechamp.loader import load_pokemon
        for name in threat_names:
            try:
                poke = load_pokemon(name)
                if TypeName.ICE in poke.types:
                    ice_found = True
                    break
            except FileNotFoundError:
                pass
        assert ice_found, f"Expected ice types in top threats, got: {threat_names[:5]}"

    def test_threat_score_positive(self):
        """All threat scores should be non-negative."""
        pool = _all_pokemon()
        threats = find_threats(["garchomp"], pool=pool)
        for _, score in threats:
            assert score >= 0.0

    def test_threat_sorted_descending(self):
        """Threats are sorted highest score first."""
        pool = _all_pokemon()
        threats = find_threats(["garchomp"], pool=pool)
        scores = [s for _, s in threats]
        assert scores == sorted(scores, reverse=True)

    def test_team_member_excluded(self):
        """Team members should not appear in threats list."""
        pool = _all_pokemon()
        threats = find_threats(["garchomp"], pool=pool)
        threat_names = [t[0] for t in threats]
        assert "garchomp" not in threat_names

    def test_multi_member_team(self):
        """Multi-member team doesn't crash and returns results."""
        pool = _all_pokemon()
        threats = find_threats(["garchomp", "corviknight", "primarina"], pool=pool)
        assert len(threats) > 0
        # None of the team members in threats
        for member in ["garchomp", "corviknight", "primarina"]:
            assert member not in [t[0] for t in threats]

    def test_fairy_threatens_dragon_team(self):
        """Fairy types should rank highly against a pure Dragon team."""
        pool = _all_pokemon()
        # Find dragon-type pokemon in the pool
        from pokechamp.loader import load_pokemon
        dragon_team = []
        for name in pool[:30]:  # sample first to avoid slow full scan
            try:
                p = load_pokemon(name)
                if TypeName.DRAGON in p.types:
                    dragon_team.append(name)
                if len(dragon_team) >= 2:
                    break
            except FileNotFoundError:
                pass

        if len(dragon_team) < 1:
            pytest.skip("No dragon-type pokemon found in pool sample")

        threats = find_threats(dragon_team, pool=pool)
        threat_names = [t[0] for t in threats[:20]]

        fairy_found = False
        for name in threat_names:
            try:
                p = load_pokemon(name)
                if TypeName.FAIRY in p.types:
                    fairy_found = True
                    break
            except FileNotFoundError:
                pass

        assert fairy_found, f"Expected fairy types in top threats vs dragon team, got: {threat_names[:5]}"


class TestSuggestAdditions:
    def test_returns_non_team_pokemon(self):
        """Suggestions should not include existing team members."""
        pool = _all_pokemon()
        threats = ["abomasnow", "aurorus"]  # Ice types
        suggestions = suggest_additions(["garchomp"], threats, pool=pool)
        assert "garchomp" not in [s[0] for s in suggestions]

    def test_sorted_descending(self):
        """Suggestions are sorted highest score first."""
        pool = _all_pokemon()
        threats_result = find_threats(["garchomp"], pool=pool)
        top_threats = [t[0] for t in threats_result[:5]]
        suggestions = suggest_additions(["garchomp"], top_threats, pool=pool)
        scores = [s for _, s in suggestions]
        assert scores == sorted(scores, reverse=True)

    def test_no_threats_returns_results(self):
        """Empty threat list returns zero-score results without crashing."""
        pool = _all_pokemon()
        suggestions = suggest_additions(["garchomp"], [], pool=pool)
        # All scores should be 0.0 when no threats provided
        for _, score in suggestions:
            assert score == 0.0

    def test_fire_type_covers_ice_threat(self):
        """Fire-type pokemon should score well as cover against ice threats."""
        pool = _all_pokemon()
        # Use ice-type threats
        ice_threats = []
        from pokechamp.loader import load_pokemon
        for name in pool:
            try:
                p = load_pokemon(name)
                if TypeName.ICE in p.types:
                    ice_threats.append(name)
            except FileNotFoundError:
                pass

        if not ice_threats:
            pytest.skip("No ice-type pokemon in pool")

        suggestions = suggest_additions(["garchomp"], ice_threats[:5], pool=pool)
        top_names = [s[0] for s in suggestions[:15]]

        fire_found = False
        for name in top_names:
            try:
                p = load_pokemon(name)
                if TypeName.FIRE in p.types or TypeName.STEEL in p.types:
                    fire_found = True
                    break
            except FileNotFoundError:
                pass

        assert fire_found, f"Expected fire/steel types in cover suggestions vs ice, got: {top_names[:5]}"


class TestAnalyzeTeam:
    def test_analyze_team_structure(self):
        """analyze_team returns expected keys."""
        pool = _all_pokemon()
        result = analyze_team(["garchomp"], pool=pool, top_n=5)
        assert "team" in result
        assert "top_threats" in result
        assert "suggested_additions" in result
        assert result["team"] == ["garchomp"]
        assert len(result["top_threats"]) <= 5
        assert len(result["suggested_additions"]) <= 5

    def test_analyze_team_top_n_respected(self):
        """top_n parameter limits output length."""
        pool = _all_pokemon()
        result = analyze_team(["garchomp"], pool=pool, top_n=3)
        assert len(result["top_threats"]) == 3
        assert len(result["suggested_additions"]) == 3

    def test_analyze_team_multi_members(self):
        """Multi-member team works end-to-end."""
        pool = _all_pokemon()
        result = analyze_team(
            ["garchomp", "corviknight"], pool=pool, top_n=5
        )
        assert len(result["top_threats"]) <= 5
        for species, _ in result["top_threats"]:
            assert species not in ["garchomp", "corviknight"]
