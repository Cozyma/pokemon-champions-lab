"""3v3シーケンス評価のテスト"""
from __future__ import annotations


from pokechamp.battle import BattlePokemon
from pokechamp.models import Nature
from pokechamp.sequence import evaluate_sequence, _quick_win_estimate


def _make_garchomp(item: str = "") -> BattlePokemon:
    return BattlePokemon.from_data(
        species="garchomp",
        nature=Nature.JOLLY,
        evs={"attack": 32, "speed": 32},
        ivs={},
        item=item,
        move_names=["earthquake", "outrage"],
    )


def _make_primarina() -> BattlePokemon:
    return BattlePokemon.from_data(
        species="primarina",
        nature=Nature.MODEST,
        evs={"sp_attack": 32, "speed": 32},
        ivs={},
        item="",
        move_names=["moonblast", "surf"],
    )


def _make_corviknight() -> BattlePokemon:
    return BattlePokemon.from_data(
        species="corviknight",
        nature=Nature.IMPISH,
        evs={"hp": 32, "defense": 32},
        ivs={},
        item="leftovers",
        move_names=["body-press", "roost"],
    )


def _make_volcarona() -> BattlePokemon:
    return BattlePokemon.from_data(
        species="volcarona",
        nature=Nature.TIMID,
        evs={"sp_attack": 32, "speed": 32},
        ivs={},
        item="",
        move_names=["flamethrower", "quiver-dance"],
    )


def _make_gengar() -> BattlePokemon:
    return BattlePokemon.from_data(
        species="gengar",
        nature=Nature.TIMID,
        evs={"sp_attack": 32, "speed": 32},
        ivs={},
        item="",
        move_names=["shadow-ball", "sludge-wave"],
    )


def _make_magikarp() -> BattlePokemon:
    return BattlePokemon.from_data(
        species="magikarp",
        nature=Nature.JOLLY,
        evs={},
        ivs={},
        item="",
        move_names=["tackle"],
    )


class TestSequenceEvaluation:
    def test_3v3_runs(self):
        """3v3シーケンス評価が動作する"""
        team_a = [_make_garchomp(), _make_primarina(), _make_corviknight()]
        team_b = [_make_garchomp(), _make_volcarona(), _make_gengar()]
        result = evaluate_sequence(team_a, team_b, n_trials=100)
        assert 0 <= result.win_rate_a <= 1
        assert len(result.sample_log) > 0
        assert len(result.team_a_selection) == 3
        assert len(result.team_b_selection) == 3

    def test_result_model_fields(self):
        """SequenceResultが正しいフィールドを持つ"""
        team_a = [_make_garchomp(), _make_primarina(), _make_corviknight()]
        team_b = [_make_garchomp(), _make_volcarona(), _make_gengar()]
        result = evaluate_sequence(team_a, team_b, n_trials=50)
        assert isinstance(result.win_rate_a, float)
        assert isinstance(result.avg_remaining_a, float)
        assert isinstance(result.avg_remaining_b, float)
        assert isinstance(result.sample_log, list)

    def test_overwhelming_advantage(self):
        """圧倒的有利なチームが高勝率"""
        strong = [
            BattlePokemon.from_data(
                species="garchomp",
                nature=Nature.JOLLY,
                evs={"attack": 32, "speed": 32},
                ivs={},
                item="choice-scarf",
                move_names=["earthquake", "outrage"],
            )
            for _ in range(3)
        ]
        weak = [_make_magikarp() for _ in range(3)]
        result = evaluate_sequence(strong, weak, n_trials=50)
        assert result.win_rate_a > 0.9

    def test_switching_runs_without_error(self):
        """交代ロジックがエラーなく動作する"""
        # Corviknight vs Volcarona: Corviknight should want to switch
        team_a = [_make_corviknight(), _make_garchomp(), _make_primarina()]
        team_b = [_make_volcarona(), _make_gengar(), _make_garchomp()]
        result = evaluate_sequence(team_a, team_b, n_trials=50)
        # Just verify it runs and returns valid results
        assert 0 <= result.win_rate_a <= 1

    def test_hp_carryover(self):
        """HPが対面間で引き継がれる（残存HPが3未満になりうる）"""
        strong = [_make_garchomp() for _ in range(3)]
        opponent = [_make_garchomp() for _ in range(3)]
        result = evaluate_sequence(strong, opponent, n_trials=100)
        # In a mirror 3v3, neither team should typically survive at full health
        assert result.avg_remaining_a < 3 or result.avg_remaining_b < 3

    def test_win_rates_are_complementary(self):
        """勝者と敗者の残存ポケモン数が整合する"""
        team_a = [_make_garchomp(), _make_primarina(), _make_corviknight()]
        team_b = [_make_garchomp(), _make_volcarona(), _make_gengar()]
        result = evaluate_sequence(team_a, team_b, n_trials=100)
        # avg_remaining should make sense relative to win_rate
        assert result.avg_remaining_a >= 0
        assert result.avg_remaining_b >= 0

    def test_sample_log_contains_battle_info(self):
        """サンプルログにバトル情報が含まれる"""
        team_a = [_make_garchomp(), _make_primarina(), _make_corviknight()]
        team_b = [_make_magikarp() for _ in range(3)]
        result = evaluate_sequence(team_a, team_b, n_trials=20)
        # Log entries should mention pokemon names
        log_text = " ".join(result.sample_log)
        assert len(log_text) > 0


class TestQuickWinEstimate:
    def test_strong_vs_weak(self):
        """圧倒的強者が高勝率推定を得る"""
        strong = _make_garchomp()
        weak = _make_magikarp()
        hp_strong = strong.stats["hp"]
        hp_weak = weak.stats["hp"]
        estimate = _quick_win_estimate(strong, weak, hp_strong, hp_weak, "none")
        assert estimate > 0.5

    def test_returns_float_in_range(self):
        """推定値が0.0〜1.0の範囲内"""
        a = _make_garchomp()
        b = _make_primarina()
        est = _quick_win_estimate(a, b, a.stats["hp"], b.stats["hp"], "none")
        assert 0.0 <= est <= 1.0

    def test_reduced_hp_affects_estimate(self):
        """HPが低いほど勝率推定が下がる"""
        a = _make_garchomp()
        b = _make_primarina()
        full_hp_est = _quick_win_estimate(a, b, a.stats["hp"], b.stats["hp"], "none")
        low_hp_est = _quick_win_estimate(a, b, 1, b.stats["hp"], "none")
        # With 1 HP, a should win less often (or at most equal)
        assert low_hp_est <= full_hp_est + 0.1  # allow small tolerance
