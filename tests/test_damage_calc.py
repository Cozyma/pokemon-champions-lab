"""damage_calc モジュールのテスト

順方向 damage_query() と逆方向 estimate_attacker() の両方をテスト。
会話中に手計算した メガゲンガー vs ラウドボーン のシナリオを検証ケースに使用。
"""
import pytest

from pokechamp.damage_calc import damage_query, estimate_attacker, parse_evs
from pokechamp.models import Nature


# ---------------------------------------------------------------------------
# parse_evs
# ---------------------------------------------------------------------------


class TestParseEvs:
    def test_basic(self):
        evs = parse_evs("h32,c32,s2")
        assert evs["hp"] == 32
        assert evs["sp_attack"] == 32
        assert evs["speed"] == 2
        assert evs["attack"] == 0

    def test_empty(self):
        evs = parse_evs("")
        assert all(v == 0 for v in evs.values())

    def test_single(self):
        evs = parse_evs("d32")
        assert evs["sp_defense"] == 32


# ---------------------------------------------------------------------------
# damage_query: メガゲンガー → ラウドボーン (会話中の検証ケース)
# ---------------------------------------------------------------------------


class TestDamageQueryMegaGengarVsSkeledirge:
    """おくびょう CS メガゲンガーのシャドーボール → ラウドボーン各型。"""

    def test_hd_calm_survives(self):
        """おだやか H32D32 ラウドボーン → 確定耐え。"""
        report = damage_query(
            attacker_species="gengar",
            attacker_nature=Nature.TIMID,
            attacker_evs=parse_evs("c32,s32"),
            attacker_item="gengar-mega-stone",
            move_name="shadow-ball",
            defender_species="skeledirge",
            defender_nature=Nature.CALM,
            defender_evs=parse_evs("h32,d32"),
        )
        # メガゲンガー C206
        assert report.attack_stat == 206
        # ラウドボーン HP195, D122
        assert report.defender_hp == 195
        assert report.defense_stat == 122
        # タイプ相性: ゴースト → 炎/ゴースト = ×2.0
        assert report.type_eff == 2.0
        assert report.stab is True
        # 確定耐え: max_damage < HP
        assert report.max_damage < report.defender_hp
        # 確定2発
        assert report.nhko_guaranteed == 2

    def test_hd_neutral_nature(self):
        """性格補正なし H32D32 → 高乱数耐え (max_damage >= HP の可能性)。"""
        report = damage_query(
            attacker_species="gengar",
            attacker_nature=Nature.TIMID,
            attacker_evs=parse_evs("c32,s32"),
            attacker_item="gengar-mega-stone",
            move_name="shadow-ball",
            defender_species="skeledirge",
            defender_nature=Nature.MODEST,  # C↑A↓, D補正なし
            defender_evs=parse_evs("h32,d32"),
        )
        assert report.defender_hp == 195
        assert report.defense_stat == 111
        # 高乱数: 一部の乱数で落ちる
        assert report.min_damage < report.defender_hp
        assert report.max_damage >= report.defender_hp

    def test_assault_vest(self):
        """ひかえめ HC32 + チョッキ → 確定耐え。"""
        report = damage_query(
            attacker_species="gengar",
            attacker_nature=Nature.TIMID,
            attacker_evs=parse_evs("c32,s32"),
            attacker_item="gengar-mega-stone",
            move_name="shadow-ball",
            defender_species="skeledirge",
            defender_nature=Nature.MODEST,
            defender_evs=parse_evs("h32,c32"),
            defender_item="assault-vest",
        )
        # チョッキで D95 → floor(95 * 1.5) = 142
        assert report.defense_stat == 142
        assert report.max_damage < report.defender_hp


class TestDamageQuerySkeledirgeVsMegaGengar:
    """ラウドボーンのシャドーボール → メガゲンガー (返しのダメージ)。"""

    def test_assault_vest_modest_hc32(self):
        """ひかえめ HC32 チョッキ型 → メガゲンガーに乱数1発。"""
        report = damage_query(
            attacker_species="skeledirge",
            attacker_nature=Nature.MODEST,
            attacker_evs=parse_evs("h32,c32"),
            move_name="shadow-ball",
            defender_species="gengar",
            defender_nature=Nature.TIMID,
            defender_evs=parse_evs("c32,s32"),
            defender_item="gengar-mega-stone",
        )
        # メガゲンガー HP135 D115
        assert report.defender_hp == 135
        assert report.defense_stat == 115
        # ゴースト → ゴースト/毒 = ×2.0 (ゴースト→ゴースト=2, ゴースト→毒=1)
        assert report.type_eff == 2.0
        assert report.stab is True
        # 乱数1発: 一部のロールで落ちる
        assert report.min_damage < report.defender_hp
        assert report.max_damage >= report.defender_hp


# ---------------------------------------------------------------------------
# damage_query: 基本ケース
# ---------------------------------------------------------------------------


class TestDamageQueryBasic:
    def test_immune(self):
        """ノーマル技 → ゴーストタイプ = 無効。"""
        report = damage_query(
            attacker_species="garchomp",
            attacker_nature=Nature.ADAMANT,
            attacker_evs=parse_evs("a32"),
            move_name="mega-kick",
            defender_species="gengar",
            defender_nature=Nature.TIMID,
            defender_evs={},
        )
        assert report.type_eff == 0.0
        assert report.max_damage == 0

    def test_stab_detection(self):
        """ガブリアスの地震 = 地面一致。"""
        report = damage_query(
            attacker_species="garchomp",
            attacker_nature=Nature.JOLLY,
            attacker_evs=parse_evs("a32,s32"),
            move_name="earthquake",
            defender_species="snorlax",
            defender_nature=Nature.CAREFUL,
            defender_evs=parse_evs("h32,d32"),
        )
        assert report.stab is True
        assert report.min_damage > 0


# ---------------------------------------------------------------------------
# estimate_attacker
# ---------------------------------------------------------------------------


class TestEstimateAttacker:
    def test_finds_timid_cs_mega_gengar(self):
        """既知のダメージ値から おくびょう C32 メガゲンガーを候補に含むこと。"""
        # まず順方向で正解のダメージを取得
        report = damage_query(
            attacker_species="gengar",
            attacker_nature=Nature.TIMID,
            attacker_evs=parse_evs("c32,s32"),
            attacker_item="gengar-mega-stone",
            move_name="shadow-ball",
            defender_species="skeledirge",
            defender_nature=Nature.CALM,
            defender_evs=parse_evs("h32,d32"),
        )
        # 中央付近の乱数を使う
        mid_damage = report.damage_all[8]

        result = estimate_attacker(
            observed_damage=mid_damage,
            defender_species="skeledirge",
            defender_nature=Nature.CALM,
            defender_evs=parse_evs("h32,d32"),
            attacker_species="gengar",
            move_name="shadow-ball",
            attacker_is_mega=True,
        )

        assert result.stat_name == "sp_attack"
        assert result.type_eff == 2.0
        assert result.stab is True
        assert len(result.candidates) > 0

        # おくびょう C32 (stat_value=206) が候補に含まれるか
        matching = [
            c for c in result.candidates
            if c.nature == Nature.TIMID and c.ev == 32
        ]
        assert len(matching) > 0
        assert matching[0].stat_value == 206

    def test_no_candidates_for_impossible_damage(self):
        """ありえないダメージ値には候補が出ないこと。"""
        result = estimate_attacker(
            observed_damage=999,
            defender_species="skeledirge",
            defender_nature=Nature.CALM,
            defender_evs=parse_evs("h32,d32"),
            attacker_species="gengar",
            move_name="shadow-ball",
            attacker_is_mega=True,
        )
        assert len(result.candidates) == 0

    def test_multiple_item_scenarios(self):
        """メガでない場合、複数アイテム候補が出ること。"""
        report = damage_query(
            attacker_species="garchomp",
            attacker_nature=Nature.JOLLY,
            attacker_evs=parse_evs("a32,s32"),
            move_name="earthquake",
            defender_species="snorlax",
            defender_nature=Nature.CAREFUL,
            defender_evs=parse_evs("h32,d32"),
        )
        mid_damage = report.damage_all[8]

        result = estimate_attacker(
            observed_damage=mid_damage,
            defender_species="snorlax",
            defender_nature=Nature.CAREFUL,
            defender_evs=parse_evs("h32,d32"),
            attacker_species="garchomp",
            move_name="earthquake",
        )

        items_found = set(c.item for c in result.candidates)
        # アイテムなし以外にも候補が出る可能性
        assert len(result.candidates) > 0
        # 正解 (アイテムなし、ようき A32) が含まれる
        matching = [
            c for c in result.candidates
            if c.nature == Nature.JOLLY and c.ev == 32 and c.item == ""
        ]
        assert len(matching) > 0
