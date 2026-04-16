"""Tests for showdown_eval module (no Showdown server required)."""
from __future__ import annotations


def test_species_to_showdown_paste():
    from pokechamp.showdown_eval import _species_to_showdown_paste

    paste = _species_to_showdown_paste("garchomp")
    assert "Garchomp" in paste
    assert "Ability:" in paste


def test_species_to_showdown_paste_with_item():
    from pokechamp.showdown_eval import _species_to_showdown_paste

    paste = _species_to_showdown_paste("garchomp", item="focus-sash")
    assert "Garchomp @ Focus Sash" in paste


def test_build_showdown_team_padded_to_6():
    from pokechamp.showdown_eval import _build_showdown_team

    team = _build_showdown_team(["garchomp", "scizor"])
    # Should be padded to 6
    assert team.count("Ability:") == 6


def test_build_showdown_team_already_6():
    from pokechamp.showdown_eval import _build_showdown_team

    species = ["garchomp", "scizor", "primarina", "volcarona", "gengar", "hydreigon"]
    team = _build_showdown_team(species)
    assert team.count("Ability:") == 6


def test_build_showdown_team_no_duplicates():
    from pokechamp.showdown_eval import _build_showdown_team

    # garchomp is also a filler — make sure it's not added twice
    team = _build_showdown_team(["garchomp"])
    species_lines = [line for line in team.splitlines() if line and not line.startswith(("-", "Ability", "EVs", "Jolly", "Nature"))]
    # No species should appear more than once
    assert len(species_lines) == len(set(species_lines))


def test_species_to_showdown_paste_has_moves():
    from pokechamp.showdown_eval import _species_to_showdown_paste

    paste = _species_to_showdown_paste("garchomp")
    move_lines = [line for line in paste.splitlines() if line.startswith("- ")]
    assert len(move_lines) > 0


def test_species_to_showdown_paste_has_evs():
    from pokechamp.showdown_eval import _species_to_showdown_paste

    paste = _species_to_showdown_paste("corviknight")
    assert "EVs:" in paste
