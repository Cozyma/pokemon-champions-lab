"""1v1対面シミュレーション

BattlePokemon dataclass と simulate_1v1 関数を提供する。
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Optional

from pokechamp.damage import calc_damage_range, calc_stat, type_effectiveness
from pokechamp.loader import load_move, load_pokemon
from pokechamp.models import BattleResult, Move, Nature, TypeName


# ---------------------------------------------------------------------------
# アイテム効果テーブル
# ---------------------------------------------------------------------------
_ITEM_EFFECTS: dict[str, dict] = {
    # ステータス補正
    "choice-scarf": {"type": "speed_multiply", "value": 1.5},
    # タイプ強化アイテム (1.2倍)
    "silver-powder": {"type": "type_boost", "boost_type": "bug", "value": 1.2},
    "metal-coat": {"type": "type_boost", "boost_type": "steel", "value": 1.2},
    "soft-sand": {"type": "type_boost", "boost_type": "ground", "value": 1.2},
    "hard-stone": {"type": "type_boost", "boost_type": "rock", "value": 1.2},
    "miracle-seed": {"type": "type_boost", "boost_type": "grass", "value": 1.2},
    "black-glasses": {"type": "type_boost", "boost_type": "dark", "value": 1.2},
    "black-belt": {"type": "type_boost", "boost_type": "fighting", "value": 1.2},
    "magnet": {"type": "type_boost", "boost_type": "electric", "value": 1.2},
    "mystic-water": {"type": "type_boost", "boost_type": "water", "value": 1.2},
    "sharp-beak": {"type": "type_boost", "boost_type": "flying", "value": 1.2},
    "poison-barb": {"type": "type_boost", "boost_type": "poison", "value": 1.2},
    "never-melt-ice": {"type": "type_boost", "boost_type": "ice", "value": 1.2},
    "spell-tag": {"type": "type_boost", "boost_type": "ghost", "value": 1.2},
    "twisted-spoon": {"type": "type_boost", "boost_type": "psychic", "value": 1.2},
    "charcoal": {"type": "type_boost", "boost_type": "fire", "value": 1.2},
    "dragon-fang": {"type": "type_boost", "boost_type": "dragon", "value": 1.2},
    "silk-scarf": {"type": "type_boost", "boost_type": "normal", "value": 1.2},
    "fairy-feather": {"type": "type_boost", "boost_type": "fairy", "value": 1.2},
}


@dataclass
class BattlePokemon:
    """バトル用ポケモンデータ。実数値・技・アイテムを保持する。"""

    name: str
    types: list[TypeName]
    stats: dict[str, int]  # {"hp": ..., "attack": ..., ...}
    moves: list[Move]
    item: str
    nature: Nature
    evs: dict[str, int]
    stage_modifiers: dict[str, int] = field(default_factory=lambda: {
        "attack": 0,
        "defense": 0,
        "sp_attack": 0,
        "sp_defense": 0,
        "speed": 0,
    })

    @classmethod
    def from_data(
        cls,
        species: str,
        nature: Nature,
        evs: dict[str, int],
        ivs: dict[str, int],
        item: str,
        move_names: list[str],
        level: int = 50,
    ) -> "BattlePokemon":
        """ポケモン名・性格・努力値などからBattlePokemonを生成する。"""
        pokemon = load_pokemon(species)

        # デフォルト個体値は31
        iv_defaults = {
            "hp": 31, "attack": 31, "defense": 31,
            "sp_attack": 31, "sp_defense": 31, "speed": 31,
        }
        iv_defaults.update(ivs)

        ev_defaults = {
            "hp": 0, "attack": 0, "defense": 0,
            "sp_attack": 0, "sp_defense": 0, "speed": 0,
        }
        ev_defaults.update(evs)

        # 各ステータス実数値を計算
        stat_names = ["hp", "attack", "defense", "sp_attack", "sp_defense", "speed"]
        stats: dict[str, int] = {}
        for stat_name in stat_names:
            base = getattr(pokemon.base_stats, stat_name)
            stats[stat_name] = calc_stat(
                base=base,
                iv=iv_defaults[stat_name],
                ev=ev_defaults[stat_name],
                level=level,
                nature=nature,
                stat_name=stat_name,
            )

        # アイテムによるステータス補正はget_effective_stat()で動的に適用する
        # (stats辞書には補正前の値を格納し、実効値計算時にアイテム効果を乗算)

        # 技を読み込む
        moves = [load_move(name) for name in move_names]

        return cls(
            name=species,
            types=pokemon.types,
            stats=stats,
            moves=moves,
            item=item,
            nature=nature,
            evs=ev_defaults,
        )

    def get_effective_stat(self, stat_name: str) -> int:
        """ランク補正・アイテム補正を適用した実効ステータスを返す。

        正のランク: (2+stage)/2
        負のランク: 2/(2-stage) → 実際には 2/(2+abs(stage))
        アイテム効果 (choice-scarf等) もここで乗算する。
        """
        base = self.stats[stat_name]

        # アイテムによるステータス補正
        if self.item in _ITEM_EFFECTS:
            effect = _ITEM_EFFECTS[self.item]
            if effect["type"] == "speed_multiply" and stat_name == "speed":
                base = math.floor(base * effect["value"])

        stage = self.stage_modifiers.get(stat_name, 0)
        if stage >= 0:
            multiplier = (2 + stage) / 2
        else:
            multiplier = 2 / (2 - stage)
        return math.floor(base * multiplier)

    def best_move_against(self, opponent: "BattlePokemon") -> tuple[Move | None, list[int]]:
        """相手に対して最も高い平均ダメージを与える技と乱数リストを返す。

        ステータス技および完全無効な技はスキップ。
        全技がステータスか無効の場合は (None, [0]*16) を返す。
        """
        best_move: Optional[Move] = None
        best_dmg: list[int] = [0] * 16
        best_avg = 0.0

        for move in self.moves:
            if move.category == "status":
                continue
            if move.power == 0:
                continue

            # タイプ相性を計算（複合タイプ対応）
            eff = 1.0
            for defend_type in opponent.types:
                eff *= type_effectiveness(move.type, defend_type)

            if eff == 0.0:
                continue

            # STAB判定
            stab = move.type in self.types

            # 攻撃/特攻の選択
            if move.category == "physical":
                atk_stat = self.get_effective_stat("attack")
                def_stat = opponent.get_effective_stat("defense")
            else:  # special
                atk_stat = self.get_effective_stat("sp_attack")
                def_stat = opponent.get_effective_stat("sp_defense")

            # タイプ強化アイテムの補正
            item_mod = 1.0
            if self.item in _ITEM_EFFECTS:
                effect = _ITEM_EFFECTS[self.item]
                if effect["type"] == "type_boost" and move.type.value == effect["boost_type"]:
                    item_mod = effect["value"]

            dmg_range = calc_damage_range(
                level=50,
                power=move.power,
                attack_stat=atk_stat,
                defense_stat=def_stat,
                stab=stab,
                type_eff=eff,
                item_modifier=item_mod,
            )

            avg = sum(dmg_range) / len(dmg_range)
            if avg > best_avg:
                best_avg = avg
                best_move = move
                best_dmg = dmg_range

        return best_move, best_dmg


def _apply_setup(pokemon: BattlePokemon, setup_move_name: str, turns: int) -> None:
    """setup_move_nameの技をturns回分だけステージ補正に適用する（±6でキャップ）。"""
    move = load_move(setup_move_name)
    for _ in range(turns):
        for change in move.stat_changes:
            stat = str(change["stat"])
            stages = int(change["stages"])
            current = pokemon.stage_modifiers.get(stat, 0)
            pokemon.stage_modifiers[stat] = max(-6, min(6, current + stages))


def simulate_1v1(
    a: BattlePokemon,
    b: BattlePokemon,
    setup_move: Optional[str] = None,
    setup_turns: int = 0,
    n_trials: int = 1000,
) -> BattleResult:
    """1v1シミュレーションを実行し、勝率と平均残HPを返す。

    Args:
        a: 先攻候補のBattlePokemon
        b: 後攻候補のBattlePokemon
        setup_move: セットアップ技名（Noneなら積みなし）
        setup_turns: セットアップ回数。積んだ分だけ先手補正が付く
        n_trials: モンテカルロ試行回数（速度差が決め手の場合は乱数16×16で全列挙）

    Returns:
        BattleResult (win_rate_a + win_rate_b == 1.0 を保証)
    """
    # セットアップ適用（aのみ）
    # セットアップを積むと、積んだターン分だけ初手の先攻権を得る（準備ターンでイニシアチブを掴む）
    setup_applied = False
    if setup_move and setup_turns > 0:
        _apply_setup(a, setup_move, setup_turns)
        setup_applied = True

    # 各側の最善技・ダメージ乱数を取得
    move_a, dmg_range_a = a.best_move_against(b)
    move_b, dmg_range_b = b.best_move_against(a)

    # 先攻判定
    priority_a = move_a.priority if move_a else 0
    priority_b = move_b.priority if move_b else 0
    speed_a = a.get_effective_stat("speed")
    speed_b = b.get_effective_stat("speed")

    # 先攻: 優先度が高い、同じなら素早さが高い方（同値は50%ずつ）
    # セットアップ積み時は速度同値でもaが先攻（準備ターンでイニシアチブを掴む）
    a_goes_first: Optional[bool]
    if priority_a != priority_b:
        a_goes_first = priority_a > priority_b
    elif speed_a != speed_b:
        a_goes_first = speed_a > speed_b
    elif setup_applied:
        a_goes_first = True  # 積みによる先攻イニシアチブ
    else:
        a_goes_first = None  # 同速: 試行ごとにランダム

    # どちらかが0ダメージしか与えられない場合の特別処理
    a_max_dmg = max(dmg_range_a)
    b_max_dmg = max(dmg_range_b)
    hp_a = a.stats["hp"]
    hp_b = b.stats["hp"]

    if a_max_dmg == 0 and b_max_dmg == 0:
        # 両者とも0ダメージ → 引き分けを50:50とする
        return BattleResult(
            pokemon_a=a.name,
            pokemon_b=b.name,
            win_rate_a=0.5,
            win_rate_b=0.5,
            avg_remaining_hp_a=float(hp_a),
            avg_remaining_hp_b=float(hp_b),
        )

    if a_max_dmg == 0:
        # aは何もできない → bが100%勝つ
        return BattleResult(
            pokemon_a=a.name,
            pokemon_b=b.name,
            win_rate_a=0.0,
            win_rate_b=1.0,
            avg_remaining_hp_a=0.0,
            avg_remaining_hp_b=float(hp_b),
        )

    if b_max_dmg == 0:
        # bは何もできない → aが100%勝つ
        return BattleResult(
            pokemon_a=a.name,
            pokemon_b=b.name,
            win_rate_a=1.0,
            win_rate_b=0.0,
            avg_remaining_hp_a=float(hp_a),
            avg_remaining_hp_b=0.0,
        )

    # アイテム効果があるためモンテカルロに一本化
    # （全列挙は高速だがタスキ・たべのこし等の処理が複雑になるため）
    if False:
        # 16x16全列挙
        wins_a = 0
        wins_b = 0
        total_remaining_hp_a = 0.0
        total_remaining_hp_b = 0.0
        n_combinations = len(dmg_range_a) * len(dmg_range_b)

        for da in dmg_range_a:
            for db in dmg_range_b:
                if a_goes_first:
                    # aが先攻
                    remaining_b = hp_b - da
                    if remaining_b <= 0:
                        wins_a += 1
                        total_remaining_hp_a += hp_a
                        total_remaining_hp_b += 0
                    else:
                        remaining_a = hp_a - db
                        if remaining_a <= 0:
                            wins_b += 1
                            total_remaining_hp_a += 0
                            total_remaining_hp_b += remaining_b
                        else:
                            # 1ターン目で決着がつかない場合はモンテカルロで継続
                            # ここでは単純に残HPを蓄積して引き分けとして処理
                            # (1ターンで決着しなければ乱数の期待値で処理)
                            # 厳密性よりシンプルさを優先: 継続ターンは期待値ベースで計算
                            avg_a_dmg = sum(dmg_range_a) / len(dmg_range_a)
                            avg_b_dmg = sum(dmg_range_b) / len(dmg_range_b)
                            # 残りターン数(期待値)でどちらが先に倒れるか
                            turns_to_ko_b = math.ceil(remaining_b / avg_a_dmg) if avg_a_dmg > 0 else float('inf')
                            turns_to_ko_a = math.ceil(remaining_a / avg_b_dmg) if avg_b_dmg > 0 else float('inf')
                            if turns_to_ko_b <= turns_to_ko_a:
                                wins_a += 1
                                remaining_after = max(0, remaining_a - avg_b_dmg * (turns_to_ko_b - 1))
                                total_remaining_hp_a += remaining_after
                                total_remaining_hp_b += 0
                            else:
                                wins_b += 1
                                remaining_after = max(0, remaining_b - avg_a_dmg * (turns_to_ko_a - 1))
                                total_remaining_hp_a += 0
                                total_remaining_hp_b += remaining_after
                else:
                    # bが先攻
                    remaining_a = hp_a - db
                    if remaining_a <= 0:
                        wins_b += 1
                        total_remaining_hp_a += 0
                        total_remaining_hp_b += hp_b
                    else:
                        remaining_b = hp_b - da
                        if remaining_b <= 0:
                            wins_a += 1
                            total_remaining_hp_a += remaining_a
                            total_remaining_hp_b += 0
                        else:
                            avg_a_dmg = sum(dmg_range_a) / len(dmg_range_a)
                            avg_b_dmg = sum(dmg_range_b) / len(dmg_range_b)
                            turns_to_ko_b = math.ceil(remaining_b / avg_a_dmg) if avg_a_dmg > 0 else float('inf')
                            turns_to_ko_a = math.ceil(remaining_a / avg_b_dmg) if avg_b_dmg > 0 else float('inf')
                            if turns_to_ko_b < turns_to_ko_a:
                                wins_a += 1
                                remaining_after = max(0, remaining_a - avg_b_dmg * (turns_to_ko_b - 1))
                                total_remaining_hp_a += remaining_after
                                total_remaining_hp_b += 0
                            else:
                                wins_b += 1
                                remaining_after = max(0, remaining_b - avg_a_dmg * (turns_to_ko_a - 1))
                                total_remaining_hp_a += 0
                                total_remaining_hp_b += remaining_after

        win_rate_a = wins_a / n_combinations
        win_rate_b = wins_b / n_combinations
        avg_hp_a = total_remaining_hp_a / n_combinations
        avg_hp_b = total_remaining_hp_b / n_combinations

    else:
        # モンテカルロシミュレーション
        wins_a = 0
        wins_b = 0
        total_remaining_hp_a = 0.0
        total_remaining_hp_b = 0.0

        # アイテムフラグ
        leftovers_a = a.item == "leftovers"
        leftovers_b = b.item == "leftovers"
        leftovers_heal_a = max(1, hp_a // 16)
        leftovers_heal_b = max(1, hp_b // 16)

        for _ in range(n_trials):
            cur_hp_a = hp_a
            cur_hp_b = hp_b
            sash_a = a.item == "focus-sash"
            sash_b = b.item == "focus-sash"
            sitrus_a = a.item == "sitrus-berry"
            sitrus_b = b.item == "sitrus-berry"
            sitrus_heal_a = max(1, hp_a // 4)
            sitrus_heal_b = max(1, hp_b // 4)

            # 同速の場合は試行ごとにランダム決定
            if a_goes_first is None:
                first_is_a = random.random() < 0.5
            else:
                first_is_a = a_goes_first

            while cur_hp_a > 0 and cur_hp_b > 0:
                da = random.choice(dmg_range_a)
                db = random.choice(dmg_range_b)

                if first_is_a:
                    prev_hp_b = cur_hp_b
                    cur_hp_b -= da
                    # きあいのタスキ: HP満タンから一撃で倒される場合HP1で耐える
                    if cur_hp_b <= 0 and sash_b and prev_hp_b == hp_b:
                        cur_hp_b = 1
                        sash_b = False
                    if cur_hp_b <= 0:
                        break
                    # オボンのみ: HP半分以下で最大HPの1/4回復
                    if sitrus_b and cur_hp_b <= hp_b // 2:
                        cur_hp_b = min(hp_b, cur_hp_b + sitrus_heal_b)
                        sitrus_b = False

                    prev_hp_a = cur_hp_a
                    cur_hp_a -= db
                    if cur_hp_a <= 0 and sash_a and prev_hp_a == hp_a:
                        cur_hp_a = 1
                        sash_a = False
                    if cur_hp_a <= 0:
                        break
                    if sitrus_a and cur_hp_a <= hp_a // 2:
                        cur_hp_a = min(hp_a, cur_hp_a + sitrus_heal_a)
                        sitrus_a = False
                else:
                    prev_hp_a = cur_hp_a
                    cur_hp_a -= db
                    if cur_hp_a <= 0 and sash_a and prev_hp_a == hp_a:
                        cur_hp_a = 1
                        sash_a = False
                    if cur_hp_a <= 0:
                        break
                    if sitrus_a and cur_hp_a <= hp_a // 2:
                        cur_hp_a = min(hp_a, cur_hp_a + sitrus_heal_a)
                        sitrus_a = False

                    cur_hp_b -= da
                    if cur_hp_b <= 0 and sash_b and cur_hp_b + da == hp_b:
                        cur_hp_b = 1
                        sash_b = False
                    if cur_hp_b <= 0:
                        break
                    if sitrus_b and cur_hp_b <= hp_b // 2:
                        cur_hp_b = min(hp_b, cur_hp_b + sitrus_heal_b)
                        sitrus_b = False

                # ターン終了時: たべのこし回復
                if leftovers_a and cur_hp_a > 0:
                    cur_hp_a = min(hp_a, cur_hp_a + leftovers_heal_a)
                if leftovers_b and cur_hp_b > 0:
                    cur_hp_b = min(hp_b, cur_hp_b + leftovers_heal_b)

            if cur_hp_a <= 0:
                wins_b += 1
                total_remaining_hp_b += max(0, cur_hp_b)
            else:
                wins_a += 1
                total_remaining_hp_a += max(0, cur_hp_a)

        win_rate_a = wins_a / n_trials
        win_rate_b = wins_b / n_trials
        avg_hp_a = total_remaining_hp_a / n_trials
        avg_hp_b = total_remaining_hp_b / n_trials

    return BattleResult(
        pokemon_a=a.name,
        pokemon_b=b.name,
        win_rate_a=win_rate_a,
        win_rate_b=win_rate_b,
        avg_remaining_hp_a=avg_hp_a,
        avg_remaining_hp_b=avg_hp_b,
    )
