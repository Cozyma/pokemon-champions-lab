"""技評価・ダメージ計算ヘルパー

_calc_all_moves と _apply_setup を提供する。
"""
from __future__ import annotations

import math
from typing import TYPE_CHECKING

from pokechamp.damage import calc_damage_range, type_effectiveness
from pokechamp.loader import load_move
from pokechamp.models import Move, TypeName
from pokechamp.abilities import (
    _ITEM_EFFECTS,
    _SKIN_ABILITIES,
    _get_attack_modifier,
    _get_damage_modifier,
    _is_type_immune,
    _is_type_immune_by_type,
)

if TYPE_CHECKING:
    from pokechamp.battle import BattlePokemon


def _calc_all_moves(
    attacker: "BattlePokemon",
    opponent: "BattlePokemon",
    weather: str = "none",
) -> list[tuple[Move, list[int]]]:
    """攻撃側の全有効技とダメージ乱数リストを返す。

    ステータス技・完全無効技を除く全技を計算して返す。
    """
    results: list[tuple[Move, list[int]]] = []

    for move in attacker.moves:
        if move.category == "status":
            continue
        if move.power == 0:
            continue

        # スキン系アビリティ: ノーマル技を別タイプに変換
        effective_type = move.type
        skin_boost = 1.0
        if attacker.ability in _SKIN_ABILITIES and move.type == TypeName.NORMAL:
            effective_type = _SKIN_ABILITIES[attacker.ability]
            skin_boost = 1.2

        # アビリティによるタイプ無効チェック
        if effective_type == move.type:
            if _is_type_immune(opponent, move):
                continue
        else:
            if _is_type_immune_by_type(opponent, effective_type):
                continue

        # タイプ相性を計算（複合タイプ対応）
        eff = 1.0
        for defend_type in opponent.types:
            mult = type_effectiveness(effective_type, defend_type)
            # きもったま: ノーマル・格闘技がゴーストに無効化されない（0.0→1.0）
            if mult == 0.0 and attacker.ability == "scrappy":
                if effective_type in (TypeName.NORMAL, TypeName.FIGHTING) and defend_type == TypeName.GHOST:
                    mult = 1.0
            eff *= mult

        if eff == 0.0:
            continue

        # STAB判定 (adaptabilityは2.0、スキン変換後タイプで判定)
        if effective_type in attacker.types:
            stab_mult = 2.0 if attacker.ability == "adaptability" else 1.5
        else:
            stab_mult = 1.0
        stab = stab_mult > 1.0

        # 攻撃/特攻の選択
        if move.category == "physical":
            ignore_opp_def = attacker.ability == "unaware"
            ignore_my_atk = opponent.ability == "unaware"
            atk_stat = attacker.get_effective_stat("attack", ignore_stages=ignore_my_atk)
            def_stat = opponent.get_effective_stat("defense", ignore_stages=ignore_opp_def)
        else:  # special
            ignore_opp_def = attacker.ability == "unaware"
            ignore_my_atk = opponent.ability == "unaware"
            atk_stat = attacker.get_effective_stat("sp_attack", ignore_stages=ignore_my_atk)
            def_stat = opponent.get_effective_stat("sp_defense", ignore_stages=ignore_opp_def)
            # 砂嵐時の岩タイプ特防1.5倍（mega-solarは天候をsun扱いにするため適用外）
            sand_active = weather == "sand" and attacker.ability != "mega-solar"
            if sand_active and TypeName.ROCK in opponent.types:
                def_stat = math.floor(def_stat * 1.5)

        # アビリティによる攻撃補正をatk_statに乗算
        atk_mod = _get_attack_modifier(attacker, move)
        atk_stat = math.floor(atk_stat * atk_mod)

        # タイプ強化アイテムの補正
        item_mod = 1.0
        if attacker.item in _ITEM_EFFECTS:
            effect = _ITEM_EFFECTS[attacker.item]
            if effect["type"] == "type_boost" and effective_type.value == effect["boost_type"]:
                item_mod = effect["value"]

        # スキン系アビリティの1.2倍補正
        item_mod *= skin_boost

        # アビリティによるダメージ補正をitem_modに乗算
        item_mod *= _get_damage_modifier(attacker, move, opponent)

        # 天候によるダメージ補正
        weather_mod = 1.0
        effective_weather = weather
        # mega-solar: 攻撃側はいつも晴れ扱い
        if attacker.ability == "mega-solar":
            effective_weather = "sun"

        move_type_value = effective_type.value
        if effective_weather == "sun":
            if move_type_value == "fire":
                weather_mod = 1.5
            elif move_type_value == "water":
                weather_mod = 0.5
        elif effective_weather == "rain":
            if move_type_value == "water":
                weather_mod = 1.5
            elif move_type_value == "fire":
                weather_mod = 0.5

        # すなのちから: 砂嵐時に岩/地面/鋼技が×1.3
        if weather == "sand" and attacker.ability == "sand-force":
            if move_type_value in ("rock", "ground", "steel"):
                weather_mod *= 1.3

        item_mod *= weather_mod

        # adaptability: stab=Trueで1.5倍、差分(2.0/1.5)をitem_modに乗算
        if stab and stab_mult == 2.0:
            item_mod *= 2.0 / 1.5

        dmg_range = calc_damage_range(
            level=50,
            power=move.power,
            attack_stat=atk_stat,
            defense_stat=def_stat,
            stab=stab,
            type_eff=eff,
            item_modifier=item_mod,
        )

        results.append((move, dmg_range))

    return results


def _apply_setup(pokemon: "BattlePokemon", setup_move_name: str, turns: int) -> None:
    """setup_move_nameの技をturns回分だけステージ補正に適用する（±6でキャップ）。"""
    move = load_move(setup_move_name)
    for _ in range(turns):
        for change in move.stat_changes:
            stat = str(change["stat"])
            stages = int(change["stages"])
            current = pokemon.stage_modifiers.get(stat, 0)
            pokemon.stage_modifiers[stat] = max(-6, min(6, current + stages))
