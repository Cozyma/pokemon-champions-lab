"""matchup.py のテスト"""
from pokechamp.matchup import evaluate_matchup, build_battle_pokemon_from_team, _rank_selections, _is_mega_member
from pokechamp.loader import load_team
from pokechamp.models import TeamMember, Nature


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


class TestMegaSelectionConstraint:
    def test_is_mega_member_with_mega_stone(self):
        """メガストーン持ちは is_mega_member=True を返す"""
        member = TeamMember(
            species="garchomp",
            ability="sand-veil",
            item="garchomp-mega-stone",
            nature=Nature.JOLLY,
            moves=["earthquake"],
        )
        assert _is_mega_member(member) is True

    def test_is_mega_member_without_mega_stone(self):
        """メガストーンなしは is_mega_member=False を返す"""
        member = TeamMember(
            species="garchomp",
            ability="sand-veil",
            item="choice-scarf",
            nature=Nature.JOLLY,
            moves=["earthquake"],
        )
        assert _is_mega_member(member) is False

    def test_selection_ranking_limits_mega(self):
        """選出ランキングでメガは1体まで"""
        names = ["a", "b", "c", "d"]
        is_mega = [True, True, False, False]
        # 4x4 の均等マトリクス
        matrix = [[0.5] * 4 for _ in range(4)]
        selections = _rank_selections(
            names, names, matrix, is_mega_a=is_mega, is_mega_b=is_mega
        )
        for sel in selections:
            mega_count_a = sum(1 for name in sel.team_a_selection if is_mega[names.index(name)])
            mega_count_b = sum(1 for name in sel.team_b_selection if is_mega[names.index(name)])
            assert mega_count_a <= 1, f"チームAの選出にメガが2体以上: {sel.team_a_selection}"
            assert mega_count_b <= 1, f"チームBの選出にメガが2体以上: {sel.team_b_selection}"

    def test_selection_ranking_no_mega_constraint_when_none(self):
        """is_mega フラグがない場合は制約なしで動作する"""
        names = ["a", "b", "c"]
        matrix = [[0.5] * 3 for _ in range(3)]
        selections = _rank_selections(names, names, matrix)
        # 3体チームなら選出は1通りのみ
        assert len(selections) == 1
