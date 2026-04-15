from pokechamp.importer import parse_pokeapi_pokemon, parse_pokeapi_move


class TestParsePokeAPIPokemon:
    def test_parse_response(self):
        api_response = {
            "name": "garchomp",
            "types": [
                {"type": {"name": "dragon"}},
                {"type": {"name": "ground"}},
            ],
            "stats": [
                {"base_stat": 108, "stat": {"name": "hp"}},
                {"base_stat": 130, "stat": {"name": "attack"}},
                {"base_stat": 95, "stat": {"name": "defense"}},
                {"base_stat": 80, "stat": {"name": "special-attack"}},
                {"base_stat": 85, "stat": {"name": "special-defense"}},
                {"base_stat": 102, "stat": {"name": "speed"}},
            ],
            "abilities": [
                {"ability": {"name": "sand-veil"}},
                {"ability": {"name": "rough-skin"}},
            ],
            "moves": [
                {"move": {"name": "earthquake"}},
                {"move": {"name": "outrage"}},
            ],
        }
        result = parse_pokeapi_pokemon(api_response)
        assert result["name_en"] == "garchomp"
        assert result["base_stats"]["hp"] == 108
        assert result["base_stats"]["sp_attack"] == 80
        assert "ground" in result["types"]
        assert "dragon" in result["types"]


class TestParsePokeAPIMove:
    def test_parse_move(self):
        api_response = {
            "name": "earthquake",
            "type": {"name": "ground"},
            "damage_class": {"name": "physical"},
            "power": 100,
            "accuracy": 100,
            "pp": 10,
            "priority": 0,
            "stat_changes": [],
        }
        result = parse_pokeapi_move(api_response)
        assert result["name_en"] == "earthquake"
        assert result["category"] == "physical"
        assert result["power"] == 100
