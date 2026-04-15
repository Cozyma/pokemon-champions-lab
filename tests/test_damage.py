from pokechamp.damage import type_effectiveness, calc_stat, calc_damage_range
from pokechamp.models import TypeName, Nature


class TestTypeEffectiveness:
    def test_super_effective(self):
        assert type_effectiveness(TypeName.FIRE, TypeName.GRASS) == 2.0

    def test_not_very_effective(self):
        assert type_effectiveness(TypeName.FIRE, TypeName.WATER) == 0.5

    def test_immune(self):
        assert type_effectiveness(TypeName.NORMAL, TypeName.GHOST) == 0.0

    def test_neutral(self):
        assert type_effectiveness(TypeName.FIRE, TypeName.FIGHTING) == 1.0

    def test_multi_type_super_effective(self):
        eff = type_effectiveness(TypeName.GROUND, TypeName.FIRE) * type_effectiveness(TypeName.GROUND, TypeName.STEEL)
        assert eff == 4.0


class TestCalcStat:
    def test_hp_stat(self):
        # ガブリアスHP: base108, IV31, EV4, Lv50
        # inner=2*108+31+4=251, floor(251*50/100)+50+10=185
        hp = calc_stat(base=108, iv=31, ev=4, level=50, nature=Nature.JOLLY, stat_name="hp")
        assert hp == 185

    def test_attack_with_nature_boost(self):
        # ガブリアス攻撃: base130, IV31, EV32, Lv50, いじっぱり(attack↑)
        # inner=2*130+31+32=323, floor(323*50/100)+5=166, floor(166*1.1)=182
        atk = calc_stat(base=130, iv=31, ev=32, level=50, nature=Nature.ADAMANT, stat_name="attack")
        assert atk == 182

    def test_speed_with_nature_boost(self):
        # ガブリアス素早さ: base102, IV31, EV32, Lv50, ようき(speed↑)
        # inner=2*102+31+32=267, floor(267*50/100)+5=138, floor(138*1.1)=151
        spe = calc_stat(base=102, iv=31, ev=32, level=50, nature=Nature.JOLLY, stat_name="speed")
        assert spe == 151


class TestCalcDamageRange:
    def test_earthquake_damage(self):
        # Lv50 A200 地震(100) vs D100 等倍 タイプ一致
        damages = calc_damage_range(
            level=50, power=100, attack_stat=200, defense_stat=100,
            stab=True, type_eff=1.0,
        )
        assert len(damages) == 16
        assert damages[0] < damages[-1]
        assert all(d > 0 for d in damages)

    def test_immune_does_zero(self):
        damages = calc_damage_range(
            level=50, power=100, attack_stat=200, defense_stat=100,
            stab=False, type_eff=0.0,
        )
        assert all(d == 0 for d in damages)

    def test_item_modifier(self):
        base = calc_damage_range(
            level=50, power=100, attack_stat=150, defense_stat=100,
            stab=False, type_eff=1.0, item_modifier=1.0,
        )
        boosted = calc_damage_range(
            level=50, power=100, attack_stat=150, defense_stat=100,
            stab=False, type_eff=1.0, item_modifier=1.3,
        )
        assert boosted[-1] > base[-1]
