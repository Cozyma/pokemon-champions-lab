"""AI判断ロジック

ターンごとの最適な技選択を行う _choose_move を提供する。
"""
from __future__ import annotations

import math
from typing import TYPE_CHECKING

from pokechamp.models import Move

if TYPE_CHECKING:
    from pokechamp.battle import BattlePokemon


def _choose_move(
    attacker: "BattlePokemon",
    opponent: "BattlePokemon",
    cur_hp_opponent: int,
    my_speed: int,
    opp_speed: int,
    all_moves: list[tuple[Move, list[int]]],
    max_incoming_dmg: int,
    cur_hp_self: int,
    max_hp_self: int,
    turn_number: int = 1,
    setup_used: bool = False,
    atk_boost: int = 0,
    spa_boost: int = 0,
) -> tuple[Move | None, list[int]]:
    """ターンごとの状況に応じて最適な技を選択する。

    ロジック:
    1. 全有効技のダメージ範囲はall_movesから取得（事前計算済み）
    2. ターン1かつ未セットアップ: セットアップ技使用の是非を判断
    3. 自分が速い → 最大ダメージ技を選択
    4. 自分が遅い場合:
       a. 先制技でKOできるなら使用
       b. 被弾で倒れる場合: 先制技+急所でKO可能なら先制技（博打）、不可なら最大ダメージ
       c. 生存可能 → 最大ダメージ技

    atk_boost/spa_boost: 現在の攻撃/特攻ランク補正（自己デバフ等で変動）。
    ダメージ推定に反映してデバフ後の実ダメージで技選択する。
    """
    if not all_moves:
        return None, [0] * 16

    def _adjusted_avg(move: Move, dmg_range: list[int]) -> float:
        """現在のブーストを反映した平均ダメージを返す。"""
        avg = sum(dmg_range) / len(dmg_range)
        if move.category == "physical" and atk_boost != 0:
            if atk_boost > 0:
                avg *= (2 + atk_boost) / 2
            else:
                avg *= 2 / (2 + abs(atk_boost))
        elif move.category == "special" and spa_boost != 0:
            if spa_boost > 0:
                avg *= (2 + spa_boost) / 2
            else:
                avg *= 2 / (2 + abs(spa_boost))
        return avg

    # ねこだまし: ターン1で使用（優先度+3先制＋ひるみで相手1ターン封じ）
    # 速い/遅い問わずねこだましのダメージ＋相手の行動封じ分が常に得。
    # ただし最大火力技で確1の場合はそちらを優先（ねこだまし不要）。
    if turn_number == 1:
        for move, dmg_range in all_moves:
            if move.name_en == "fake-out":
                # 他の技で確1なら不要
                best = max(all_moves, key=lambda x: _adjusted_avg(x[0], x[1]))
                if min(best[1]) >= cur_hp_opponent:
                    break  # 確1あるのでねこだまし不要
                return move, dmg_range

    # セットアップ技検討 (ターン1のみ、未使用時のみ)
    if turn_number == 1 and not setup_used:
        setup_moves = [m for m in attacker.moves if m.stat_changes and m.category == "status"]
        if setup_moves:
            will_survive = max_incoming_dmg < cur_hp_self
            has_sash = attacker.item == "focus-sash"
            has_sturdy = attacker.ability == "sturdy"

            if will_survive or has_sash or has_sturdy:
                # セットアップが有効かを推定する
                best_atk_move = max(all_moves, key=lambda x: _adjusted_avg(x[0], x[1]))
                best_avg_dmg = _adjusted_avg(best_atk_move[0], best_atk_move[1])

                if best_avg_dmg > 0:
                    # ブーストによるダメージ増加率を推定
                    boost_factor = 1.0
                    for change in setup_moves[0].stat_changes:
                        stages = int(change["stages"])
                        if str(change["stat"]) in ("attack", "sp_attack"):
                            boost_factor *= (2 + stages) / 2  # +2 → ×2.0, +1 → ×1.5

                    if boost_factor > 1.0:
                        boosted_avg = best_avg_dmg * boost_factor
                        turns_without = math.ceil(cur_hp_opponent / best_avg_dmg)
                        turns_with = math.ceil(cur_hp_opponent / boosted_avg)

                        # セットアップで1ターン以上節約できるなら積む
                        if turns_without - turns_with >= 1:
                            return setup_moves[0], [0] * 16

    # 先制技と通常技に分類
    priority_moves = [(m, dr) for m, dr in all_moves if m.priority > 0]

    # 最大ダメージ技（ブースト調整済み平均ダメージ最大）
    best_normal = max(all_moves, key=lambda x: _adjusted_avg(x[0], x[1]))

    i_am_faster = my_speed > opp_speed

    if i_am_faster or not priority_moves:
        # 速い、または先制技なし → 最大ダメージ技
        return best_normal

    # 遅い & 先制技あり
    for pmove, pdmg in priority_moves:
        # 先制技でKO可能？
        if min(pdmg) >= cur_hp_opponent:
            return pmove, pdmg  # 確定KO

    # このターン被弾で倒れるか？（相手が先攻なので）
    will_die = max_incoming_dmg >= cur_hp_self

    if will_die:
        # 倒れる前提 → 先制技+急所でKO可能か博打
        for pmove, pdmg in priority_moves:
            crit_max = math.floor(max(pdmg) * 1.5)
            if crit_max >= cur_hp_opponent:
                return pmove, pdmg  # 急所博打
        # 急所KOも不可 → 最大ダメージで削る
        return best_normal

    # 生存可能 → 最大ダメージ技（被弾後に攻撃できる）
    return best_normal
