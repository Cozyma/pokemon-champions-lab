import json
from pokechamp.output import format_battle_result, format_matchup_result
from pokechamp.models import BattleResult, MatchupResult, MatchupMatrix, SelectionScore


class TestFormatBattleResult:
    def test_json_output(self):
        result = BattleResult(
            pokemon_a="garchomp", pokemon_b="magikarp",
            win_rate_a=1.0, win_rate_b=0.0,
            avg_remaining_hp_a=184.0, avg_remaining_hp_b=0.0,
        )
        output = format_battle_result(result, as_json=True)
        data = json.loads(output)
        assert data["pokemon_a"] == "garchomp"
        assert data["win_rate_a"] == 1.0

    def test_table_output(self):
        result = BattleResult(
            pokemon_a="garchomp", pokemon_b="magikarp",
            win_rate_a=1.0, win_rate_b=0.0,
            avg_remaining_hp_a=184.0, avg_remaining_hp_b=0.0,
        )
        output = format_battle_result(result, as_json=False)
        assert "garchomp" in output
        assert "100.0%" in output


class TestFormatMatchupResult:
    def test_json_output(self):
        result = MatchupResult(
            team_a="Team A", team_b="Team B",
            matrix=MatchupMatrix(
                team_a_names=["a1"], team_b_names=["b1"], matrix=[[0.75]],
            ),
            setup_evaluations=[],
            selection_ranking=[
                SelectionScore(team_a_selection=["a1"], team_b_selection=["b1"], score=0.75),
            ],
            overall_score=0.75,
        )
        output = format_matchup_result(result, as_json=True)
        data = json.loads(output)
        assert data["overall_score"] == 0.75

    def test_table_output_contains_matrix(self):
        result = MatchupResult(
            team_a="Team A", team_b="Team B",
            matrix=MatchupMatrix(
                team_a_names=["garchomp"], team_b_names=["magikarp"], matrix=[[1.0]],
            ),
            setup_evaluations=[],
            selection_ranking=[],
            overall_score=1.0,
        )
        output = format_matchup_result(result, as_json=False)
        assert "garchomp" in output
        assert "100.0%" in output
