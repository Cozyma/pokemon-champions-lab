"""Tests for showdown_data module."""
from __future__ import annotations


def test_load_pokedex():
    from pokechamp.showdown_data import load_pokedex
    pokedex = load_pokedex()
    assert len(pokedex) > 0
    assert "garchomp" in pokedex
    assert pokedex["garchomp"]["types"] == ["Dragon", "Ground"]


def test_get_species_abilities():
    from pokechamp.showdown_data import get_species_abilities
    abilities = get_species_abilities("Garchomp")
    assert "roughskin" in abilities
    assert "sandveil" in abilities


def test_get_species_abilities_case_insensitive():
    from pokechamp.showdown_data import get_species_abilities
    abilities = get_species_abilities("garchomp")
    assert "roughskin" in abilities


def test_ability_is_contact_punish():
    from pokechamp.showdown_data import ability_has_contact_punish
    assert ability_has_contact_punish("roughskin") is True
    assert ability_has_contact_punish("ironbarbs") is True
    assert ability_has_contact_punish("intimidate") is False


def test_ability_is_type_immunity():
    from pokechamp.showdown_data import ability_grants_type_immunity
    assert ability_grants_type_immunity("levitate") == "ground"
    assert ability_grants_type_immunity("flashfire") == "fire"
    assert ability_grants_type_immunity("sapsipper") == "grass"
    assert ability_grants_type_immunity("waterabsorb") == "water"
    assert ability_grants_type_immunity("voltabsorb") == "electric"
    assert ability_grants_type_immunity("lightningrod") == "electric"
    assert ability_grants_type_immunity("stormdrain") == "water"
    assert ability_grants_type_immunity("motordrive") == "electric"
    assert ability_grants_type_immunity("intimidate") is None


def test_ability_is_attack_multiplier():
    from pokechamp.showdown_data import ability_attack_multiplier
    assert ability_attack_multiplier("hugepower") == ("atk", 2.0)
    assert ability_attack_multiplier("purepower") == ("atk", 2.0)
    assert ability_attack_multiplier("hustle") == ("atk", 1.5)
    assert ability_attack_multiplier("intimidate") is None


def test_species_may_have_contact_punish():
    from pokechamp.showdown_data import species_may_have_contact_punish
    assert species_may_have_contact_punish("Garchomp") is True
    assert species_may_have_contact_punish("Corviknight") is False


def test_species_type_immunities():
    from pokechamp.showdown_data import species_type_immunities
    immunities = species_type_immunities("Bronzong")
    assert "ground" in immunities
