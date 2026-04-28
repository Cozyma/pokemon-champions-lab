from pokechamp.loader import load_pokemon, load_move, load_team, load_item


class TestLoadPokemon:
    def test_load_garchomp(self):
        pokemon = load_pokemon("garchomp")
        assert pokemon.name_en == "garchomp"
        assert pokemon.base_stats.attack == 130
        assert "ground" in [t.value for t in pokemon.types]

    def test_load_nonexistent_raises(self):
        import pytest
        with pytest.raises(FileNotFoundError):
            load_pokemon("missingno")


class TestLoadMove:
    def test_load_earthquake(self):
        move = load_move("earthquake")
        assert move.power == 100
        assert move.category == "physical"

    def test_load_status_move(self):
        move = load_move("swords-dance")
        assert move.category == "status"
        assert move.power == 0
        assert len(move.stat_changes) > 0


class TestLoadItem:
    def test_load_choice_scarf(self):
        item = load_item("choice-scarf")
        assert item["effect"] == "speed_multiply"
        assert item["value"] == 1.5


class TestLoadTeam:
    def test_load_screenshot_team(self):
        team = load_team("screenshot-team")
        assert team.name is not None
        assert len(team.pokemon) >= 1
