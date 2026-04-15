from pokechamp.battle import BattlePokemon, simulate_1v1
from pokechamp.models import Nature


class TestBattlePokemon:
    def test_from_team_member(self):
        """ガブリアス(ようき A32 S32 H2)の実数値を検証"""
        bp = BattlePokemon.from_data(
            species="garchomp", nature=Nature.JOLLY,
            evs={"hp": 2, "attack": 32, "speed": 32},
            ivs={}, item="choice-scarf",
            move_names=["earthquake", "outrage", "iron-head", "stone-edge"],
        )
        assert bp.name == "garchomp"
        assert bp.stats["hp"] == 184
        assert bp.stats["speed"] == 151

    def test_garchomp_vs_magikarp(self):
        """ガブリアスはコイキング(はねるのみ)に100%勝つ"""
        garchomp = BattlePokemon.from_data(
            species="garchomp", nature=Nature.JOLLY,
            evs={"hp": 2, "attack": 32, "speed": 32},
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
            evs={"hp": 2, "attack": 32, "speed": 32},
            ivs={}, item="",
            move_names=["earthquake", "outrage"],
        )
        garchomp_opponent_base = BattlePokemon.from_data(
            species="garchomp", nature=Nature.JOLLY,
            evs={"hp": 2, "attack": 32, "speed": 32},
            ivs={}, item="",
            move_names=["earthquake", "outrage"],
        )
        base_result = simulate_1v1(garchomp_base, garchomp_opponent_base)

        garchomp_setup = BattlePokemon.from_data(
            species="garchomp", nature=Nature.JOLLY,
            evs={"hp": 2, "attack": 32, "speed": 32},
            ivs={}, item="",
            move_names=["earthquake", "outrage"],
        )
        garchomp_opponent_setup = BattlePokemon.from_data(
            species="garchomp", nature=Nature.JOLLY,
            evs={"hp": 2, "attack": 32, "speed": 32},
            ivs={}, item="",
            move_names=["earthquake", "outrage"],
        )
        setup_result = simulate_1v1(
            garchomp_setup, garchomp_opponent_setup,
            setup_move="swords-dance", setup_turns=1,
        )
        assert setup_result.win_rate_a > base_result.win_rate_a


class TestItemEffects:
    def test_focus_sash_survives_ohko(self):
        """きあいのタスキ持ちコイキングはガブリアスの一撃を耐える"""
        garchomp = BattlePokemon.from_data(
            species="garchomp", nature=Nature.JOLLY,
            evs={"hp": 2, "attack": 32, "speed": 32},
            ivs={}, item="",
            move_names=["earthquake"],
        )
        # コイキングにタスキ + たいあたり
        magikarp = BattlePokemon.from_data(
            species="magikarp", nature=Nature.JOLLY,
            evs={}, ivs={}, item="focus-sash",
            move_names=["tackle"],
        )
        result = simulate_1v1(garchomp, magikarp)
        # タスキで1発耐えてたいあたりを1回は撃てる → ガブリアス100%勝ちだが残HPが減る
        assert result.win_rate_a == 1.0
        assert result.avg_remaining_hp_a < garchomp.stats["hp"]

    def test_leftovers_heals_each_turn(self):
        """たべのこし持ちは毎ターンHP回復する"""
        # 2体の同じポケモンで、片方だけたべのこし持ち → 勝率が上がる
        garchomp_leftovers = BattlePokemon.from_data(
            species="garchomp", nature=Nature.JOLLY,
            evs={"hp": 2, "attack": 32, "speed": 32},
            ivs={}, item="leftovers",
            move_names=["earthquake", "iron-head"],
        )
        garchomp_naked = BattlePokemon.from_data(
            species="garchomp", nature=Nature.JOLLY,
            evs={"hp": 2, "attack": 32, "speed": 32},
            ivs={}, item="",
            move_names=["earthquake", "iron-head"],
        )
        result = simulate_1v1(garchomp_leftovers, garchomp_naked)
        assert result.win_rate_a > 0.5

    def test_oran_berry_heals_below_half(self):
        """オボンのみ持ちはHP半分以下で回復する"""
        garchomp_oran = BattlePokemon.from_data(
            species="garchomp", nature=Nature.JOLLY,
            evs={"hp": 2, "attack": 32, "speed": 32},
            ivs={}, item="sitrus-berry",
            move_names=["earthquake", "iron-head"],
        )
        garchomp_naked = BattlePokemon.from_data(
            species="garchomp", nature=Nature.JOLLY,
            evs={"hp": 2, "attack": 32, "speed": 32},
            ivs={}, item="",
            move_names=["earthquake", "iron-head"],
        )
        result = simulate_1v1(garchomp_oran, garchomp_naked)
        assert result.win_rate_a > 0.5
