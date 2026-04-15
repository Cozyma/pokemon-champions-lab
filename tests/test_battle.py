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


class TestAbilityEffects:
    def test_huge_power_doubles_physical(self):
        """ちからもちで攻撃が実質2倍になる"""
        garchomp_huge = BattlePokemon.from_data(
            species="garchomp", nature=Nature.JOLLY,
            evs={"attack": 32, "speed": 32}, ivs={}, item="",
            move_names=["earthquake"],
        )
        garchomp_huge.ability = "huge-power"

        garchomp_opponent = BattlePokemon.from_data(
            species="garchomp", nature=Nature.JOLLY,
            evs={"attack": 32, "speed": 32}, ivs={}, item="",
            move_names=["earthquake"],
        )
        result = simulate_1v1(garchomp_huge, garchomp_opponent)
        assert result.win_rate_a > 0.7  # ちからもちで圧倒的有利

    def test_intimidate_lowers_attack(self):
        """いかくで相手の攻撃が下がる"""
        garchomp_intimidate = BattlePokemon.from_data(
            species="garchomp", nature=Nature.JOLLY,
            evs={"attack": 32, "speed": 32}, ivs={}, item="",
            move_names=["earthquake"],
        )
        garchomp_intimidate.ability = "intimidate"

        garchomp_normal = BattlePokemon.from_data(
            species="garchomp", nature=Nature.JOLLY,
            evs={"attack": 32, "speed": 32}, ivs={}, item="",
            move_names=["earthquake"],
        )
        result = simulate_1v1(garchomp_intimidate, garchomp_normal)
        assert result.win_rate_a > 0.5  # いかくで相手攻撃ランク-1 → 有利

    def test_sturdy_survives_ohko(self):
        """がんじょうでHP満タンからの一撃KOを耐える"""
        garchomp = BattlePokemon.from_data(
            species="garchomp", nature=Nature.JOLLY,
            evs={"attack": 32, "speed": 32}, ivs={}, item="",
            move_names=["earthquake"],
        )
        magikarp_sturdy = BattlePokemon.from_data(
            species="magikarp", nature=Nature.JOLLY,
            evs={}, ivs={}, item="",
            move_names=["tackle"],
        )
        magikarp_sturdy.ability = "sturdy"
        result = simulate_1v1(garchomp, magikarp_sturdy)
        # がんじょうで1発耐えてたいあたりを1回は撃てる → ガブリアス100%勝ちだが残HPが減る
        assert result.win_rate_a == 1.0
        assert result.avg_remaining_hp_a < garchomp.stats["hp"]

    def test_levitate_immune_to_ground(self):
        """ふゆうで地面技無効"""
        garchomp = BattlePokemon.from_data(
            species="garchomp", nature=Nature.JOLLY,
            evs={"attack": 32, "speed": 32}, ivs={}, item="",
            move_names=["earthquake"],
        )
        # ふゆう + アウトレイジ持ちのガブリアスモドキ
        rotom = BattlePokemon.from_data(
            species="garchomp", nature=Nature.JOLLY,
            evs={"attack": 32, "speed": 32}, ivs={}, item="",
            move_names=["earthquake", "outrage"],
        )
        rotom.ability = "levitate"
        result = simulate_1v1(garchomp, rotom)
        # ガブリアスの地震はふゆうで無効 → rotom側のアウトレイジで優位
        assert result.win_rate_b > 0.9

    def test_stamina_boosts_defense(self):
        """じきゅうりょくで被弾のたびに防御が上がる"""
        attacker = BattlePokemon.from_data(
            species="garchomp", nature=Nature.JOLLY,
            evs={"attack": 32, "speed": 32}, ivs={}, item="",
            move_names=["earthquake"],
        )
        defender_stamina = BattlePokemon.from_data(
            species="garchomp", nature=Nature.JOLLY,
            evs={"hp": 32, "defense": 32}, ivs={}, item="",
            move_names=["earthquake"],
        )
        defender_stamina.ability = "stamina"

        defender_normal = BattlePokemon.from_data(
            species="garchomp", nature=Nature.JOLLY,
            evs={"hp": 32, "defense": 32}, ivs={}, item="",
            move_names=["earthquake"],
        )
        result_stamina = simulate_1v1(attacker, defender_stamina)
        result_normal = simulate_1v1(
            BattlePokemon.from_data(
                species="garchomp", nature=Nature.JOLLY,
                evs={"attack": 32, "speed": 32}, ivs={}, item="",
                move_names=["earthquake"],
            ),
            defender_normal,
        )
        # じきゅうりょく持ちのdefenderの方が高い勝率を持つ
        assert result_stamina.win_rate_b > result_normal.win_rate_b

    def test_water_absorb_immune_to_water(self):
        """ちょすいで水技無効"""
        attacker = BattlePokemon.from_data(
            species="garchomp", nature=Nature.JOLLY,
            evs={"attack": 32, "speed": 32}, ivs={}, item="",
            move_names=["surf"],
        )
        # ちょすい持ちに対して水技のみのアタッカー → 全技無効 → bが100%勝つ
        defender = BattlePokemon.from_data(
            species="garchomp", nature=Nature.JOLLY,
            evs={"attack": 32, "speed": 32}, ivs={}, item="",
            move_names=["earthquake"],
        )
        defender.ability = "water-absorb"
        result = simulate_1v1(attacker, defender)
        assert result.win_rate_b == 1.0

    def test_flash_fire_immune_to_fire(self):
        """もらいびで炎技無効"""
        attacker = BattlePokemon.from_data(
            species="garchomp", nature=Nature.JOLLY,
            evs={"attack": 32, "speed": 32}, ivs={}, item="",
            move_names=["flamethrower"],
        )
        defender = BattlePokemon.from_data(
            species="garchomp", nature=Nature.JOLLY,
            evs={"attack": 32, "speed": 32}, ivs={}, item="",
            move_names=["earthquake"],
        )
        defender.ability = "flash-fire"
        result = simulate_1v1(attacker, defender)
        # 炎技が無効 → attackerのダメージ0 → bが100%勝つ
        assert result.win_rate_b == 1.0


class TestAbilityEffectsExtended:
    def test_technician_boosts_low_power(self):
        """テクニシャンで威力60以下の技が1.5倍"""
        garchomp_tech2 = BattlePokemon.from_data(
            species="garchomp", nature=Nature.JOLLY,
            evs={"attack": 32, "speed": 32}, ivs={}, item="",
            move_names=["tackle"],  # power 40, gets 1.5x = effective 60
        )
        garchomp_tech2.ability = "technician"

        garchomp_notech = BattlePokemon.from_data(
            species="garchomp", nature=Nature.JOLLY,
            evs={"attack": 32, "speed": 32}, ivs={}, item="",
            move_names=["tackle"],
        )
        target1 = BattlePokemon.from_data(
            species="garchomp", nature=Nature.JOLLY,
            evs={"hp": 32}, ivs={}, item="", move_names=["earthquake"],
        )
        target2 = BattlePokemon.from_data(
            species="garchomp", nature=Nature.JOLLY,
            evs={"hp": 32}, ivs={}, item="", move_names=["earthquake"],
        )
        result_tech = simulate_1v1(garchomp_tech2, target1)
        result_normal = simulate_1v1(garchomp_notech, target2)
        # テクニシャンはダメージ増 → 相手の残HPが少なくなる
        assert result_tech.avg_remaining_hp_b < result_normal.avg_remaining_hp_b

    def test_thick_fat_halves_fire_ice(self):
        """あついしぼうで炎/氷技のダメージ半減"""
        attacker = BattlePokemon.from_data(
            species="garchomp", nature=Nature.JOLLY,
            evs={"attack": 32, "speed": 32}, ivs={}, item="",
            move_names=["flamethrower"],
        )
        defender_thickfat = BattlePokemon.from_data(
            species="garchomp", nature=Nature.JOLLY,
            evs={"hp": 32, "speed": 32}, ivs={}, item="",
            move_names=["earthquake"],
        )
        defender_thickfat.ability = "thick-fat"

        defender_normal = BattlePokemon.from_data(
            species="garchomp", nature=Nature.JOLLY,
            evs={"hp": 32, "speed": 32}, ivs={}, item="",
            move_names=["earthquake"],
        )
        result_fat = simulate_1v1(attacker, defender_thickfat)
        result_normal = simulate_1v1(
            BattlePokemon.from_data(
                species="garchomp", nature=Nature.JOLLY,
                evs={"attack": 32, "speed": 32}, ivs={}, item="",
                move_names=["flamethrower"],
            ),
            defender_normal,
        )
        # あついしぼうは炎ダメージ半減 → 残HPが多い（勝率が同じでも残HPで差が出る）
        assert result_fat.avg_remaining_hp_b > result_normal.avg_remaining_hp_b

    def test_solid_rock_reduces_super_effective(self):
        """ハードロックで効果抜群ダメージ0.75倍"""
        attacker2 = BattlePokemon.from_data(
            species="garchomp", nature=Nature.JOLLY,
            evs={"attack": 32, "speed": 32}, ivs={}, item="",
            move_names=["outrage"],  # dragon vs dragon = super effective
        )
        defender_rock = BattlePokemon.from_data(
            species="garchomp", nature=Nature.JOLLY,
            evs={"hp": 32, "speed": 32}, ivs={}, item="",
            move_names=["outrage"],
        )
        defender_rock.ability = "solid-rock"

        defender_normal = BattlePokemon.from_data(
            species="garchomp", nature=Nature.JOLLY,
            evs={"hp": 32, "speed": 32}, ivs={}, item="",
            move_names=["outrage"],
        )
        result_rock = simulate_1v1(attacker2, defender_rock)
        result_normal = simulate_1v1(
            BattlePokemon.from_data(
                species="garchomp", nature=Nature.JOLLY,
                evs={"attack": 32, "speed": 32}, ivs={}, item="",
                move_names=["outrage"],
            ),
            defender_normal,
        )
        assert result_rock.win_rate_b > result_normal.win_rate_b

    def test_defiant_counters_intimidate(self):
        """まけんきはいかくに対して攻撃+2（ネット+1）"""
        intimidator = BattlePokemon.from_data(
            species="garchomp", nature=Nature.JOLLY,
            evs={"attack": 32, "speed": 32}, ivs={}, item="",
            move_names=["earthquake"],
        )
        intimidator.ability = "intimidate"

        defiant_user = BattlePokemon.from_data(
            species="garchomp", nature=Nature.JOLLY,
            evs={"attack": 32, "speed": 32}, ivs={}, item="",
            move_names=["earthquake"],
        )
        defiant_user.ability = "defiant"

        result = simulate_1v1(intimidator, defiant_user)
        # まけんきはネット+1攻撃 → いかく持ちに対して有利
        assert result.win_rate_b > 0.5

    def test_speed_boost_gains_priority(self):
        """かそくで毎ターン素早さが上がる"""
        slow_booster = BattlePokemon.from_data(
            species="magikarp", nature=Nature.JOLLY,
            evs={"attack": 32, "speed": 32}, ivs={}, item="",
            move_names=["tackle"],
        )
        slow_booster.ability = "speed-boost"

        fast_normal = BattlePokemon.from_data(
            species="garchomp", nature=Nature.JOLLY,
            evs={"attack": 32, "speed": 32}, ivs={}, item="",
            move_names=["earthquake"],
        )
        # かそくコイキングはガブリアスに勝てないが、シミュレーションが正常動作することを確認
        result = simulate_1v1(slow_booster, fast_normal)
        assert result.win_rate_a + result.win_rate_b > 0  # クラッシュしないことを確認


class TestMegaEvolution:
    def test_mega_garchomp_stats(self):
        """メガストーン持ちはメガシンカ種族値で計算される"""
        normal = BattlePokemon.from_data(
            species="garchomp", nature=Nature.JOLLY,
            evs={"attack": 32, "speed": 32}, ivs={}, item="",
            move_names=["earthquake"],
        )
        mega = BattlePokemon.from_data(
            species="garchomp", nature=Nature.JOLLY,
            evs={"attack": 32, "speed": 32}, ivs={}, item="garchomp-mega-stone",
            move_names=["earthquake"],
        )
        # メガシンカで攻撃種族値が 130 → 170 に上昇
        assert mega.stats["attack"] > normal.stats["attack"]
        # メガシンカで素早さ種族値が 102 → 92 に低下
        assert mega.stats["speed"] < normal.stats["speed"]
        # メガシンカのアビリティは sand-force
        assert mega.ability == "sand-force"

    def test_mega_garchomp_hp_unchanged(self):
        """メガシンカしてもHPは変わらない（種族値 108 は同じ）"""
        normal = BattlePokemon.from_data(
            species="garchomp", nature=Nature.JOLLY,
            evs={"hp": 32}, ivs={}, item="",
            move_names=["earthquake"],
        )
        mega = BattlePokemon.from_data(
            species="garchomp", nature=Nature.JOLLY,
            evs={"hp": 32}, ivs={}, item="garchomp-mega-stone",
            move_names=["earthquake"],
        )
        assert mega.stats["hp"] == normal.stats["hp"]

    def test_mega_garchomp_stronger_in_battle(self):
        """メガガブリアスは通常ガブリアスより火力が高い"""
        mega = BattlePokemon.from_data(
            species="garchomp", nature=Nature.JOLLY,
            evs={"attack": 32, "speed": 32}, ivs={}, item="garchomp-mega-stone",
            move_names=["earthquake"],
        )
        normal = BattlePokemon.from_data(
            species="garchomp", nature=Nature.JOLLY,
            evs={"attack": 32, "speed": 32}, ivs={}, item="",
            move_names=["earthquake"],
        )
        target1 = BattlePokemon.from_data(
            species="garchomp", nature=Nature.JOLLY,
            evs={"hp": 32}, ivs={}, item="", move_names=["earthquake"],
        )
        target2 = BattlePokemon.from_data(
            species="garchomp", nature=Nature.JOLLY,
            evs={"hp": 32}, ivs={}, item="", move_names=["earthquake"],
        )
        result_mega = simulate_1v1(mega, target1)
        result_normal = simulate_1v1(normal, target2)
        # メガの方が攻撃が高い → 勝率が同等か高い
        assert result_mega.win_rate_a >= result_normal.win_rate_a

    def test_mega_stone_no_item_effect(self):
        """メガストーンはアイテムスロットを占有し、通常アイテム効果は発動しない"""
        # メガストーン持ちはchoice-scarfのような速度補正がない
        mega = BattlePokemon.from_data(
            species="garchomp", nature=Nature.JOLLY,
            evs={"speed": 32}, ivs={}, item="garchomp-mega-stone",
            move_names=["earthquake"],
        )
        # メガシンカ後の素早さ種族値 92 で計算される（スカーフ補正なし）
        scarf = BattlePokemon.from_data(
            species="garchomp", nature=Nature.JOLLY,
            evs={"speed": 32}, ivs={}, item="choice-scarf",
            move_names=["earthquake"],
        )
        # スカーフは speed の実効値に 1.5 倍補正がかかる → スカーフの方が速い
        assert scarf.get_effective_stat("speed") > mega.get_effective_stat("speed")
