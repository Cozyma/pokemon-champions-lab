from pokechamp.battle import BattlePokemon, simulate_1v1
from pokechamp.models import Nature


class TestBattlePokemon:
    def test_from_team_member(self):
        """ガブリアス(ようき AS252 H4)の実数値を検証"""
        bp = BattlePokemon.from_data(
            species="garchomp", nature=Nature.JOLLY,
            evs={"hp": 4, "attack": 252, "speed": 252},
            ivs={}, item="choice-scarf",
            move_names=["earthquake", "outrage", "iron-head", "stone-edge"],
        )
        assert bp.name == "garchomp"
        assert bp.stats["hp"] == 184
        assert bp.stats["speed"] == 169

    def test_garchomp_vs_magikarp(self):
        """ガブリアスはコイキング(はねるのみ)に100%勝つ"""
        garchomp = BattlePokemon.from_data(
            species="garchomp", nature=Nature.JOLLY,
            evs={"hp": 4, "attack": 252, "speed": 252},
            ivs={}, item="choice-scarf",
            move_names=["earthquake"],
        )
        magikarp = BattlePokemon.from_data(
            species="magikarp", nature=Nature.JOLLY,
            evs={}, ivs={}, item="",
            move_names=["splash"],
        )
        result = simulate_1v1(garchomp, magikarp)
        assert result.win_rate_a == 1.0
        assert result.win_rate_b == 0.0


class TestSetupEvaluation:
    def test_swords_dance_improves_win_rate(self):
        """剣舞1積みで勝率が上がることを確認"""
        garchomp_base = BattlePokemon.from_data(
            species="garchomp", nature=Nature.JOLLY,
            evs={"hp": 4, "attack": 252, "speed": 252},
            ivs={}, item="",
            move_names=["earthquake", "outrage"],
        )
        garchomp_opponent_base = BattlePokemon.from_data(
            species="garchomp", nature=Nature.JOLLY,
            evs={"hp": 4, "attack": 252, "speed": 252},
            ivs={}, item="",
            move_names=["earthquake", "outrage"],
        )
        base_result = simulate_1v1(garchomp_base, garchomp_opponent_base)

        garchomp_setup = BattlePokemon.from_data(
            species="garchomp", nature=Nature.JOLLY,
            evs={"hp": 4, "attack": 252, "speed": 252},
            ivs={}, item="",
            move_names=["earthquake", "outrage"],
        )
        garchomp_opponent_setup = BattlePokemon.from_data(
            species="garchomp", nature=Nature.JOLLY,
            evs={"hp": 4, "attack": 252, "speed": 252},
            ivs={}, item="",
            move_names=["earthquake", "outrage"],
        )
        setup_result = simulate_1v1(
            garchomp_setup, garchomp_opponent_setup,
            setup_move="swords-dance", setup_turns=1,
        )
        assert setup_result.win_rate_a > base_result.win_rate_a
