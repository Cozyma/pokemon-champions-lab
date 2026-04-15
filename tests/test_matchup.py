"""matchup.py のテスト"""
from pokechamp.matchup import evaluate_matchup, build_battle_pokemon_from_team
from pokechamp.loader import load_team


class TestBuildBattlePokemon:
    def test_from_team(self):
        team = load_team("example-team")
        battle_pokemon = build_battle_pokemon_from_team(team)
        assert len(battle_pokemon) == len(team.pokemon)
        assert battle_pokemon[0].name == "garchomp"


class TestEvaluateMatchup:
    def test_mirror_matchup(self):
        """同じ構築同士のマッチアップはスコア約50%になる"""
        result = evaluate_matchup("example-team", "example-team")
        assert result.team_a == "サンプル構築"
        assert result.team_b == "サンプル構築"
        for i, row in enumerate(result.matrix.matrix):
            for j, win_rate in enumerate(row):
                if i == j:
                    assert 0.3 <= win_rate <= 0.7  # 同速乱数で50%前後
