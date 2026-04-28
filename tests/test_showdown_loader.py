"""Tests for Showdown paste loader."""
from __future__ import annotations

import pytest
from pokechamp.showdown_loader import (
    list_showdown_teams,
    load_showdown_team,
    parse_showdown_paste,
    showdown_to_team_model,
)


SAMPLE_PASTE = """\
Garchomp @ Choice Scarf
Ability: Rough Skin
EVs: 2 HP / 32 Atk / 32 Spe
Jolly Nature
- Earthquake
- Outrage
- Iron Head
- Stone Edge

Gengar @ Gengarite
Ability: Levitate
EVs: 2 HP / 32 SpA / 32 Spe
IVs: 0 Atk
Timid Nature
- Shadow Ball
- Sludge Wave
- Focus Blast
- Protect
"""


class TestParseShowdownPaste:
    def test_parses_two_pokemon(self):
        result = parse_showdown_paste(SAMPLE_PASTE)
        assert len(result) == 2

    def test_first_pokemon_species(self):
        result = parse_showdown_paste(SAMPLE_PASTE)
        assert result[0]["species"] == "Garchomp"

    def test_first_pokemon_item(self):
        result = parse_showdown_paste(SAMPLE_PASTE)
        assert result[0]["item"] == "Choice Scarf"

    def test_first_pokemon_ability(self):
        result = parse_showdown_paste(SAMPLE_PASTE)
        assert result[0]["ability"] == "Rough Skin"

    def test_first_pokemon_nature(self):
        result = parse_showdown_paste(SAMPLE_PASTE)
        assert result[0]["nature"] == "Jolly"

    def test_first_pokemon_evs(self):
        result = parse_showdown_paste(SAMPLE_PASTE)
        evs = result[0]["evs"]
        assert evs["hp"] == 2
        assert evs["atk"] == 32
        assert evs["spe"] == 32
        assert evs.get("def", 0) == 0

    def test_first_pokemon_moves(self):
        result = parse_showdown_paste(SAMPLE_PASTE)
        assert result[0]["moves"] == ["Earthquake", "Outrage", "Iron Head", "Stone Edge"]

    def test_second_pokemon_iv_override(self):
        result = parse_showdown_paste(SAMPLE_PASTE)
        # IVs line "IVs: 0 Atk" should override atk IV to 0, rest stay 31
        assert result[1]["ivs"]["atk"] == 0
        assert result[1]["ivs"]["hp"] == 31

    def test_second_pokemon_item_megastone(self):
        result = parse_showdown_paste(SAMPLE_PASTE)
        assert result[1]["item"] == "Gengarite"

    def test_pokemon_without_item(self):
        paste = "Eevee\nAbility: Run Away\nTimid Nature\n- Tackle\n"
        result = parse_showdown_paste(paste)
        assert len(result) == 1
        assert result[0]["species"] == "Eevee"
        assert result[0]["item"] == ""

    def test_empty_paste_returns_empty(self):
        assert parse_showdown_paste("") == []
        assert parse_showdown_paste("   \n\n   ") == []


class TestLoadShowdownTeam:
    def test_load_screenshot_team(self):
        result = load_showdown_team("screenshot-team")
        assert len(result) >= 1
        assert result[0]["species"] == "Lopunny"

    def test_load_mega_gengar_team(self):
        result = load_showdown_team("mega-gengar-team")
        species_list = [e["species"] for e in result]
        assert "Gengar" in species_list

    def test_load_nonexistent_raises(self):
        with pytest.raises(FileNotFoundError):
            load_showdown_team("nonexistent-team")

    def test_mega_stone_item_name(self):
        """Mega stone names should use Showdown format (e.g. Gengarite, not Gengar Mega Stone)."""
        result = load_showdown_team("mega-gengar-team")
        gengar = next(e for e in result if e["species"] == "Gengar")
        assert gengar["item"] == "Gengarite"

    def test_mega_venusaur_stone(self):
        result = load_showdown_team("mega-venusaur-charizardx")
        venusaur = next(e for e in result if e["species"] == "Venusaur")
        assert venusaur["item"] == "Venusaurite"

    def test_charizardite_x(self):
        result = load_showdown_team("mega-venusaur-charizardx")
        charizard = next(e for e in result if e["species"] == "Charizard")
        assert charizard["item"] == "Charizardite X"


class TestListShowdownTeams:
    def test_lists_teams_with_txt(self):
        teams = list_showdown_teams()
        assert "screenshot-team" in teams
        assert "mega-gengar-team" in teams
        assert "mega-scizor-team" in teams

    def test_returns_sorted(self):
        teams = list_showdown_teams()
        assert teams == sorted(teams)


class TestShowdownToTeamModel:
    def test_converts_to_team_model(self):
        parsed = parse_showdown_paste(SAMPLE_PASTE)
        team = showdown_to_team_model(parsed, name="test-team")
        assert team.name == "test-team"
        assert len(team.pokemon) == 2

    def test_species_slug(self):
        parsed = parse_showdown_paste(SAMPLE_PASTE)
        team = showdown_to_team_model(parsed, name="test-team")
        assert team.pokemon[0].species == "garchomp"

    def test_item_slug(self):
        parsed = parse_showdown_paste(SAMPLE_PASTE)
        team = showdown_to_team_model(parsed, name="test-team")
        assert team.pokemon[0].item == "choice-scarf"

    def test_ability_slug(self):
        parsed = parse_showdown_paste(SAMPLE_PASTE)
        team = showdown_to_team_model(parsed, name="test-team")
        assert team.pokemon[0].ability == "rough-skin"

    def test_nature_enum(self):
        from pokechamp.models import Nature
        parsed = parse_showdown_paste(SAMPLE_PASTE)
        team = showdown_to_team_model(parsed, name="test-team")
        assert team.pokemon[0].nature == Nature.JOLLY

    def test_evs(self):
        parsed = parse_showdown_paste(SAMPLE_PASTE)
        team = showdown_to_team_model(parsed, name="test-team")
        evs = team.pokemon[0].evs
        assert evs.hp == 2
        assert evs.attack == 32
        assert evs.speed == 32

    def test_moves_slug(self):
        parsed = parse_showdown_paste(SAMPLE_PASTE)
        team = showdown_to_team_model(parsed, name="test-team")
        assert team.pokemon[0].moves == ["earthquake", "outrage", "iron-head", "stone-edge"]

    def test_aegislash_shield_species(self):
        paste = "Aegislash-Shield @ Spell Tag\nAbility: Stance Change\nJolly Nature\n- Poltergeist\n"
        parsed = parse_showdown_paste(paste)
        team = showdown_to_team_model(parsed, name="t")
        assert team.pokemon[0].species == "aegislash-shield"

    def test_mega_stone_item_slug(self):
        paste = "Gengar @ Gengarite\nAbility: Levitate\nTimid Nature\n- Shadow Ball\n"
        parsed = parse_showdown_paste(paste)
        team = showdown_to_team_model(parsed, name="t")
        # Gengarite should become "gengarite" slug
        assert team.pokemon[0].item == "gengarite"
