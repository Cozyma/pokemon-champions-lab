"""1v1対面シミュレーション

BattlePokemon dataclass と simulate_1v1 関数を提供する。
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Optional

from pokechamp.abilities import (
    _HP_THRESHOLD_ABILITIES,
    _ITEM_EFFECTS,
    _MOLD_BREAKER_ABILITIES,
    _SAND_IMMUNE_ABILITIES,
    _SAND_IMMUNE_TYPES,
    _SELF_DEBUFF_MOVES,
    _WEATHER_ABILITIES,
    _WEATHER_SPEED_ABILITIES,
    _is_contact_move,
)
from pokechamp.ai import _choose_move
from pokechamp.calc import _apply_setup, _calc_all_moves
from pokechamp.damage import calc_stat
from pokechamp.loader import load_move, load_pokemon
from pokechamp.models import BattleResult, Move, Nature, TypeName


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
    ability: str = ""
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
        ability: Optional[str] = None,
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

        # メガシンカ判定: メガストーンを持っている場合はメガシンカ種族値・タイプ・アビリティを使用
        # リザードン等の複数メガ形態にも対応 (mega, mega_x, mega_y)
        # アイテム名はpokechamp形式(garchomp-mega-stone)とShowdown形式(garchompite等)の両方に対応
        mega = None
        item_lower = item.lower().replace(" ", "").replace("-", "")
        for mega_field in (pokemon.mega, pokemon.mega_x, pokemon.mega_y):
            if mega_field is None:
                continue
            stone_lower = mega_field.stone.lower().replace(" ", "").replace("-", "")
            if item_lower == stone_lower or item_lower.rstrip("e") + "ite" == item_lower:
                mega = mega_field
                break
        # Showdown形式のメガストーン名でもヒットさせる（species名 + ite/inite 等）
        if mega is None and item:
            species_key = species.lower().replace("-", "")
            for mega_field in (pokemon.mega, pokemon.mega_x, pokemon.mega_y):
                if mega_field is None:
                    continue
                # garchompite, lopunnite, dragoninite 等のパターンマッチ
                if item_lower.startswith(species_key[:5]):
                    mega = mega_field
                    break
        is_mega = mega is not None
        if is_mega:
            stat_source = mega.base_stats  # type: ignore[union-attr]
            types_to_use = mega.types  # type: ignore[union-attr]
            # メガシンカ時: HP は元の種族値を使用（メガデータの hp は元と同値のはずだが念のため）
            resolved_ability = mega.ability  # type: ignore[union-attr]
        else:
            stat_source = pokemon.base_stats
            types_to_use = pokemon.types
            resolved_ability = ability if ability is not None else (pokemon.abilities[0] if pokemon.abilities else "")

        # 各ステータス実数値を計算
        stat_names = ["hp", "attack", "defense", "sp_attack", "sp_defense", "speed"]
        stats: dict[str, int] = {}
        for stat_name in stat_names:
            if is_mega and stat_name == "hp":
                # HPは元の種族値で計算
                base = pokemon.base_stats.hp
            else:
                base = getattr(stat_source, stat_name)
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
        # メガストーン持ちはアイテムスロットをメガストーンが占有するため _ITEM_EFFECTS は適用しない

        # 技を読み込む
        moves = []
        for name in move_names:
            try:
                moves.append(load_move(name))
            except FileNotFoundError:
                continue  # 技データがない場合はスキップ

        return cls(
            name=species,
            types=types_to_use,
            stats=stats,
            moves=moves,
            item=item,
            nature=nature,
            evs=ev_defaults,
            ability=resolved_ability,
        )

    def get_effective_stat(self, stat_name: str, ignore_stages: bool = False) -> int:
        """ランク補正・アイテム補正を適用した実効ステータスを返す。

        正のランク: (2+stage)/2
        負のランク: 2/(2-stage) → 実際には 2/(2+abs(stage))
        アイテム効果 (choice-scarf等) もここで乗算する。
        ignore_stages=True の場合、ランク補正を無視する (てんねん用)。
        """
        base = self.stats[stat_name]

        # アイテムによるステータス補正
        if self.item in _ITEM_EFFECTS:
            effect = _ITEM_EFFECTS[self.item]
            if effect["type"] == "speed_multiply" and stat_name == "speed":
                base = math.floor(base * effect["value"])

        if ignore_stages:
            return base

        stage = self.stage_modifiers.get(stat_name, 0)
        if stage >= 0:
            multiplier = (2 + stage) / 2
        else:
            multiplier = 2 / (2 - stage)
        return math.floor(base * multiplier)

    def best_move_against(self, opponent: "BattlePokemon", weather: str = "none") -> tuple[Move | None, list[int]]:
        """相手に対して最も高い平均ダメージを与える技と乱数リストを返す。

        ステータス技および完全無効な技はスキップ。
        全技がステータスか無効の場合は (None, [0]*16) を返す。
        """
        all_moves = _calc_all_moves(self, opponent, weather=weather)
        if not all_moves:
            return None, [0] * 16
        best = max(all_moves, key=lambda x: sum(x[1]) / len(x[1]))
        return best


# ---------------------------------------------------------------------------
# モンテカルロ用内部データクラスとヘルパー
# ---------------------------------------------------------------------------

@dataclass
class _FighterState:
    """1試行中の一方のポケモンの可変状態。"""

    pokemon: BattlePokemon
    cur_hp: int
    max_hp: int
    start_hp: int          # 試行開始時HP (タスキ/がんじょう判定用)
    sash: bool
    sitrus: bool
    sitrus_heal: int
    disguise: bool
    sturdy: bool
    flash_fire_active: bool
    stamina_boosts: int
    berserk_triggered: bool
    berserk_mult: float
    speed_boost_active: bool
    atk_boost: int
    spa_boost: int
    def_boost: int
    spd_boost: int
    spe_boost: int
    setup_used: bool
    leftovers: bool
    leftovers_heal: int


def _apply_attack(
    atk: _FighterState,
    dfn: _FighterState,
    move: Move | None,
    damage: int,
    hit: bool,
) -> tuple[bool, bool]:
    """攻撃を1回適用する。

    マルチスケイル・ばけのかわ・もらいび・ダメージ適用・タスキ/がんじょう・
    さめはだ・じきゅうりょく・ぎゃくじょう・オボンのみ・自己デバフを処理する。

    Returns:
        (defender_fainted, attacker_fainted)
    """
    da = damage

    if not hit or move is None:
        da = 0

    # マルチスケイル: HP満タン時に被ダメージ半減 (かたやぶりで無効)
    if (
        dfn.pokemon.ability == "multiscale"
        and dfn.cur_hp == dfn.max_hp
        and dfn.cur_hp == dfn.start_hp  # 満タン判定
        and atk.pokemon.ability not in _MOLD_BREAKER_ABILITIES
    ):
        da = math.floor(da * 0.5)

    # ばけのかわ: 最初の1発を無効化 (かたやぶりで無効)
    if dfn.disguise and atk.pokemon.ability not in _MOLD_BREAKER_ABILITIES:
        da = 0
        dfn.disguise = False
        dfn.cur_hp -= max(1, dfn.max_hp // 8)
        if dfn.cur_hp <= 0:
            return True, False
    elif dfn.disguise:
        # かたやぶりで貫通: フラグ消費するが無効化しない
        dfn.disguise = False

    # もらいびチェック: 炎技を受けると炎技が1.5倍に (炎は無効化)
    if dfn.pokemon.ability == "flash-fire" and move is not None and move.type == TypeName.FIRE:
        da = 0
        dfn.flash_fire_active = True

    # ダメージ適用
    prev_hp = dfn.cur_hp
    dfn.cur_hp -= da

    # きあいのタスキ: HP満タンから一撃で倒される場合HP1で耐える
    if dfn.cur_hp <= 0 and dfn.sash and prev_hp == dfn.max_hp and prev_hp == dfn.start_hp:
        dfn.cur_hp = 1
        dfn.sash = False

    # がんじょう: HP満タンから一撃KOを耐える (かたやぶりで無効)
    if (
        dfn.cur_hp <= 0
        and dfn.sturdy
        and prev_hp == dfn.max_hp
        and prev_hp == dfn.start_hp
        and atk.pokemon.ability not in _MOLD_BREAKER_ABILITIES
    ):
        dfn.cur_hp = 1
        dfn.sturdy = False

    if dfn.cur_hp <= 0:
        return True, False  # defender fainted

    # さめはだ: 接触技を受けたら攻撃側に1/8反動
    if dfn.pokemon.ability == "rough-skin" and move is not None and _is_contact_move(move) and da > 0:
        atk.cur_hp -= max(1, atk.max_hp // 8)
        if atk.cur_hp <= 0:
            return False, True  # attacker fainted from recoil

    # じきゅうりょく: 被弾後に防御+1
    if dfn.pokemon.ability == "stamina" and da > 0:
        dfn.stamina_boosts = min(6, dfn.stamina_boosts + 1)

    # ぎゃくじょう: HP1/2以下で特攻+1 (一度のみ)
    if (
        dfn.pokemon.ability == "berserk"
        and not dfn.berserk_triggered
        and dfn.cur_hp <= dfn.max_hp // 2
        and dfn.cur_hp > 0
    ):
        dfn.berserk_triggered = True
        # ぎゃくじょう発動後に特殊技を持っている場合のみ倍率適用
        # 注: 現在使用予定の技カテゴリで判定する (呼び出し側から move を受け取る)
        # 元のコードと同じく「defender 自身の次に使う技」は不明なので、
        # 元実装と同様に dfn が special 技を持つかどうかで判定する
        if any(m.category == "special" for m in dfn.pokemon.moves):
            dfn.berserk_mult = 1.5

    # オボンのみ: HP半分以下で最大HPの1/4回復
    if dfn.sitrus and dfn.cur_hp <= dfn.max_hp // 2:
        dfn.cur_hp = min(dfn.max_hp, dfn.cur_hp + dfn.sitrus_heal)
        dfn.sitrus = False

    # 確定自己デバフ技: 命中後に攻撃側ステータス低下
    if hit and move is not None and move.name_en in _SELF_DEBUFF_MOVES:
        for _stat, _stages in _SELF_DEBUFF_MOVES[move.name_en]:
            if _stat == "attack":
                atk.atk_boost = max(-6, atk.atk_boost + _stages)
            elif _stat == "sp_attack":
                atk.spa_boost = max(-6, atk.spa_boost + _stages)
            elif _stat == "defense":
                atk.def_boost = max(-6, atk.def_boost + _stages)
            elif _stat == "sp_defense":
                atk.spd_boost = max(-6, atk.spd_boost + _stages)
            elif _stat == "speed":
                atk.spe_boost = max(-6, atk.spe_boost + _stages)

    return False, False  # both alive


def _apply_damage_modifiers(
    atk: _FighterState,
    move: Move | None,
    damage: int,
    dfn: _FighterState,
) -> int:
    """ダメージにインライン補正を適用して返す。

    もらいび発動中・HP閾値アビリティ・ぎゃくじょう・じきゅうりょく・
    セットアップによる攻撃/防御ブーストを適用する。
    """
    da = damage

    # もらいび発動中なら炎技ダメージを1.5倍に
    if atk.flash_fire_active and move is not None and move.type == TypeName.FIRE:
        da = math.floor(da * 1.5)

    # HP閾値アビリティ (もうか/しんりょく/げきりゅう/むしのしらせ): HP1/3以下で技ダメージ1.5倍
    if atk.pokemon.ability in _HP_THRESHOLD_ABILITIES:
        if atk.cur_hp <= atk.max_hp // 3 and move is not None and move.type == _HP_THRESHOLD_ABILITIES[atk.pokemon.ability]:
            da = math.floor(da * 1.5)

    # ぎゃくじょう: 発動済みなら特攻技ダメージに倍率適用
    if atk.berserk_mult > 1.0 and move is not None and move.category == "special":
        da = math.floor(da * atk.berserk_mult)

    # じきゅうりょく: 蓄積した防御ブーストを軽減率として適用
    # N回被弾後: 防御ステージ+N → 軽減率 2/(2+N)
    if dfn.stamina_boosts > 0:
        da = math.floor(da * 2 / (2 + dfn.stamina_boosts))

    # セットアップ技による攻撃ブーストを適用 (正負両対応)
    if atk.atk_boost != 0 and move is not None and move.category == "physical":
        if atk.atk_boost > 0:
            da = math.floor(da * (2 + atk.atk_boost) / 2)
        else:
            da = math.floor(da * 2 / (2 + abs(atk.atk_boost)))
    if atk.spa_boost != 0 and move is not None and move.category == "special":
        if atk.spa_boost > 0:
            da = math.floor(da * (2 + atk.spa_boost) / 2)
        else:
            da = math.floor(da * 2 / (2 + abs(atk.spa_boost)))

    # セットアップ技による防御ブーストを適用 (被弾ダメージ増減、正負両対応)
    if dfn.def_boost != 0 and move is not None and move.category == "physical":
        if dfn.def_boost > 0:
            da = math.floor(da * 2 / (2 + dfn.def_boost))
        else:
            da = math.floor(da * (2 + abs(dfn.def_boost)) / 2)
    if dfn.spd_boost != 0 and move is not None and move.category == "special":
        if dfn.spd_boost > 0:
            da = math.floor(da * 2 / (2 + dfn.spd_boost))
        else:
            da = math.floor(da * (2 + abs(dfn.spd_boost)) / 2)

    return da


def _end_of_turn(
    state_a: _FighterState,
    state_b: _FighterState,
    weather: str,
) -> bool:
    """ターン終了処理: たべのこし・砂嵐・かそく。

    Returns True if either pokemon fainted from end-of-turn effects.
    """
    # たべのこし回復
    if state_a.leftovers and state_a.cur_hp > 0:
        state_a.cur_hp = min(state_a.max_hp, state_a.cur_hp + state_a.leftovers_heal)
    if state_b.leftovers and state_b.cur_hp > 0:
        state_b.cur_hp = min(state_b.max_hp, state_b.cur_hp + state_b.leftovers_heal)

    # 砂嵐ダメージ (非岩・地・鋼タイプに最大HPの1/16)
    if weather == "sand":
        if state_a.cur_hp > 0 and not (set(state_a.pokemon.types) & _SAND_IMMUNE_TYPES) and state_a.pokemon.ability not in _SAND_IMMUNE_ABILITIES:
            state_a.cur_hp -= max(1, state_a.max_hp // 16)
            if state_a.cur_hp <= 0:
                return True
        if state_b.cur_hp > 0 and not (set(state_b.pokemon.types) & _SAND_IMMUNE_TYPES) and state_b.pokemon.ability not in _SAND_IMMUNE_ABILITIES:
            state_b.cur_hp -= max(1, state_b.max_hp // 16)
            if state_b.cur_hp <= 0:
                return True

    # かそく: ターン終了時に素早さ上昇 → 次ターンから速度ブースト発動
    if state_a.pokemon.ability == "speed-boost":
        state_a.speed_boost_active = True
    if state_b.pokemon.ability == "speed-boost":
        state_b.speed_boost_active = True

    return False


def _process_setup_move(
    move: Move | None,
    state: _FighterState,
) -> tuple[bool, int]:
    """セットアップ技の処理: ステージを記録してダメージ0を返す。

    Returns:
        (is_setup_move, damage)  — is_setup_move が True なら damage は 0
    """
    if move and move.category == "status" and move.stat_changes:
        for change in move.stat_changes:
            stat = str(change["stat"])
            stages = int(change["stages"])
            if stat == "attack":
                state.atk_boost = max(-6, min(6, state.atk_boost + stages))
            elif stat == "sp_attack":
                state.spa_boost = max(-6, min(6, state.spa_boost + stages))
            elif stat == "defense":
                state.def_boost = max(-6, min(6, state.def_boost + stages))
            elif stat == "sp_defense":
                state.spd_boost = max(-6, min(6, state.spd_boost + stages))
            elif stat == "speed":
                state.spe_boost = max(-6, min(6, state.spe_boost + stages))
        state.setup_used = True
        return True, 0
    return False, 0


def simulate_1v1(
    a: BattlePokemon,
    b: BattlePokemon,
    setup_move: Optional[str] = None,
    setup_turns: int = 0,
    n_trials: int = 1000,
    hp_a: int | None = None,  # NEW: starting HP for a (None = full)
    hp_b: int | None = None,  # NEW: starting HP for b (None = full)
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

    # いかく: 対戦開始時に相手の攻撃ランクを-1
    # まけんき/かちきはいかくに反応して攻撃/特攻+2（いかく後に発動）
    if a.ability == "intimidate":
        b.stage_modifiers["attack"] = max(-6, b.stage_modifiers["attack"] - 1)
        if b.ability == "defiant":
            b.stage_modifiers["attack"] = min(6, b.stage_modifiers["attack"] + 2)
        elif b.ability == "competitive":
            b.stage_modifiers["sp_attack"] = min(6, b.stage_modifiers["sp_attack"] + 2)
    if b.ability == "intimidate":
        a.stage_modifiers["attack"] = max(-6, a.stage_modifiers["attack"] - 1)
        if a.ability == "defiant":
            a.stage_modifiers["attack"] = min(6, a.stage_modifiers["attack"] + 2)
        elif a.ability == "competitive":
            a.stage_modifiers["sp_attack"] = min(6, a.stage_modifiers["sp_attack"] + 2)

    # 天候決定: 天候アビリティを持つポケモンが天候をセット
    # 両者が天候アビリティを持つ場合は遅い方の天候が優先（後から発動）
    weather = "none"
    if a.ability in _WEATHER_ABILITIES:
        weather = _WEATHER_ABILITIES[a.ability]
    if b.ability in _WEATHER_ABILITIES:
        if a.ability in _WEATHER_ABILITIES:
            # 両者が天候アビリティを持つ場合: 遅い方の天候が優先
            sa = a.get_effective_stat("speed")
            sb = b.get_effective_stat("speed")
            if sb < sa:
                weather = _WEATHER_ABILITIES[b.ability]
            # aが遅い、または同速の場合はaの天候のまま
        else:
            weather = _WEATHER_ABILITIES[b.ability]

    # 全技の事前計算（かたやぶり系対応）
    # かたやぶり: 攻撃側がかたやぶりなら防御側のアビリティを一時無効化してダメージ計算
    if a.ability in _MOLD_BREAKER_ABILITIES:
        saved_ability_b = b.ability
        b.ability = ""
        all_moves_a = _calc_all_moves(a, b, weather=weather)
        b.ability = saved_ability_b
    else:
        all_moves_a = _calc_all_moves(a, b, weather=weather)

    if b.ability in _MOLD_BREAKER_ABILITIES:
        saved_ability_a = a.ability
        a.ability = ""
        all_moves_b = _calc_all_moves(b, a, weather=weather)
        a.ability = saved_ability_a
    else:
        all_moves_b = _calc_all_moves(b, a, weather=weather)

    # 素早さ計算（天候依存アビリティを考慮）
    speed_a = a.get_effective_stat("speed")
    speed_b = b.get_effective_stat("speed")

    if a.ability in _WEATHER_SPEED_ABILITIES and weather == _WEATHER_SPEED_ABILITIES[a.ability]:
        speed_a *= 2
    if b.ability in _WEATHER_SPEED_ABILITIES and weather == _WEATHER_SPEED_ABILITIES[b.ability]:
        speed_b *= 2

    # 事前の最大ダメージ（優先技選択の判断用）
    max_dmg_from_b = max(max(dr) for _, dr in all_moves_b) if all_moves_b else 0
    max_dmg_from_a = max(max(dr) for _, dr in all_moves_a) if all_moves_a else 0

    # 0ダメージ判定用に全技の最大ダメージを確認
    max_hp_a = a.stats["hp"]
    max_hp_b = b.stats["hp"]
    # カスタム開始HPが指定されていれば使用 (Noneなら満タン)
    hp_a = hp_a if hp_a is not None else max_hp_a
    hp_b = hp_b if hp_b is not None else max_hp_b

    if max_dmg_from_a == 0 and max_dmg_from_b == 0:
        # 両者とも0ダメージ → 引き分けを50:50とする
        return BattleResult(
            pokemon_a=a.name,
            pokemon_b=b.name,
            win_rate_a=0.5,
            win_rate_b=0.5,
            avg_remaining_hp_a=float(hp_a),
            avg_remaining_hp_b=float(hp_b),
        )

    if max_dmg_from_a == 0:
        # aは何もできない → bが100%勝つ
        return BattleResult(
            pokemon_a=a.name,
            pokemon_b=b.name,
            win_rate_a=0.0,
            win_rate_b=1.0,
            avg_remaining_hp_a=0.0,
            avg_remaining_hp_b=float(hp_b),
        )

    if max_dmg_from_b == 0:
        # bは何もできない → aが100%勝つ
        return BattleResult(
            pokemon_a=a.name,
            pokemon_b=b.name,
            win_rate_a=1.0,
            win_rate_b=0.0,
            avg_remaining_hp_a=float(hp_a),
            avg_remaining_hp_b=0.0,
        )

    # セットアップ先攻判定: セットアップ積み時は同速でもaが先攻
    # (ターンごとに _choose_move + 優先度で再判定するが、同速タイブレーク用に保持)

    # モンテカルロシミュレーション
    wins_a = 0
    wins_b = 0
    total_remaining_hp_a = 0.0
    total_remaining_hp_b = 0.0

    for _ in range(n_trials):
        sa = _FighterState(
            pokemon=a,
            cur_hp=hp_a,
            max_hp=max_hp_a,
            start_hp=hp_a,
            sash=a.item == "focus-sash",
            sitrus=a.item == "sitrus-berry",
            sitrus_heal=max(1, max_hp_a // 4),
            disguise=a.ability == "disguise",
            sturdy=a.ability == "sturdy",
            flash_fire_active=False,
            stamina_boosts=0,
            berserk_triggered=False,
            berserk_mult=1.0,
            speed_boost_active=False,
            atk_boost=0,
            spa_boost=0,
            def_boost=0,
            spd_boost=0,
            spe_boost=0,
            setup_used=False,
            leftovers=a.item == "leftovers",
            leftovers_heal=max(1, max_hp_a // 16),
        )
        sb = _FighterState(
            pokemon=b,
            cur_hp=hp_b,
            max_hp=max_hp_b,
            start_hp=hp_b,
            sash=b.item == "focus-sash",
            sitrus=b.item == "sitrus-berry",
            sitrus_heal=max(1, max_hp_b // 4),
            disguise=b.ability == "disguise",
            sturdy=b.ability == "sturdy",
            flash_fire_active=False,
            stamina_boosts=0,
            berserk_triggered=False,
            berserk_mult=1.0,
            speed_boost_active=False,
            atk_boost=0,
            spa_boost=0,
            def_boost=0,
            spd_boost=0,
            spe_boost=0,
            setup_used=False,
            leftovers=b.item == "leftovers",
            leftovers_heal=max(1, max_hp_b // 16),
        )

        turn_number = 0

        while sa.cur_hp > 0 and sb.cur_hp > 0:
            turn_number += 1

            # ターンごとに最適な技を選択
            # 素早さはセットアップによる速度ブーストを考慮
            eff_speed_a = 999999 if sa.speed_boost_active else speed_a
            eff_speed_b = 999999 if sb.speed_boost_active else speed_b
            if sa.spe_boost > 0:
                eff_speed_a = math.floor(eff_speed_a * (2 + sa.spe_boost) / 2)
            if sb.spe_boost > 0:
                eff_speed_b = math.floor(eff_speed_b * (2 + sb.spe_boost) / 2)

            move_a, dmg_range_a_cur = _choose_move(
                a, b, sb.cur_hp, eff_speed_a, eff_speed_b,
                all_moves_a, max_dmg_from_b, sa.cur_hp, max_hp_a,
                turn_number=turn_number, setup_used=sa.setup_used,
                atk_boost=sa.atk_boost, spa_boost=sa.spa_boost,
            )
            move_b, dmg_range_b_cur = _choose_move(
                b, a, sa.cur_hp, eff_speed_b, eff_speed_a,
                all_moves_b, max_dmg_from_a, sb.cur_hp, max_hp_b,
                turn_number=turn_number, setup_used=sb.setup_used,
                atk_boost=sb.atk_boost, spa_boost=sb.spa_boost,
            )

            # セットアップ技の処理: ステージを記録しda/db=0に設定
            is_setup_a, _ = _process_setup_move(move_a, sa)
            if is_setup_a:
                da = 0
            else:
                da = random.choice(dmg_range_a_cur)

            is_setup_b, _ = _process_setup_move(move_b, sb)
            if is_setup_b:
                db = 0
            else:
                db = random.choice(dmg_range_b_cur)

            # 命中チェック (accuracy=100は常に命中)
            hit_a = True
            if move_a and da > 0 and move_a.accuracy < 100 and random.random() * 100 >= move_a.accuracy:
                da = 0
                hit_a = False

            hit_b = True
            if move_b and db > 0 and move_b.accuracy < 100 and random.random() * 100 >= move_b.accuracy:
                db = 0
                hit_b = False

            # 急所: 6.25%の確率でダメージ×1.5
            CRIT_RATE = 0.0625
            if da > 0 and random.random() < CRIT_RATE:
                da = math.floor(da * 1.5)
            if db > 0 and random.random() < CRIT_RATE:
                db = math.floor(db * 1.5)

            # インライン補正 (命中時のみ)
            if hit_a:
                da = _apply_damage_modifiers(sa, move_a, da, sb)
            if hit_b:
                db = _apply_damage_modifiers(sb, move_b, db, sa)

            # ねこだまし: 命中すればひるみ100%（相手はそのターン行動不可）
            flinch_b = hit_a and move_a is not None and move_a.name_en == "fake-out"
            flinch_a = hit_b and move_b is not None and move_b.name_en == "fake-out"

            # 先攻判定: ターンごとに優先度と素早さで決定
            # かそくが発動済みなら素早さを上書き (2ターン目以降)
            cur_speed_a = 999999 if sa.speed_boost_active else eff_speed_a
            cur_speed_b = 999999 if sb.speed_boost_active else eff_speed_b

            priority_a_cur = move_a.priority if move_a else 0
            priority_b_cur = move_b.priority if move_b else 0

            if priority_a_cur != priority_b_cur:
                first_is_a = priority_a_cur > priority_b_cur
            elif cur_speed_a != cur_speed_b:
                first_is_a = cur_speed_a > cur_speed_b
            elif setup_applied:
                first_is_a = True  # 積みによる先攻イニシアチブ
            else:
                first_is_a = random.random() < 0.5

            if first_is_a:
                # a が先攻
                dfnt, atkt = _apply_attack(sa, sb, move_a, da, hit_a)
                if dfnt or atkt:
                    break
                if flinch_b:
                    db = 0
                dfnt, atkt = _apply_attack(sb, sa, move_b, db, hit_b)
                if dfnt or atkt:
                    break
            else:
                # b が先攻
                dfnt, atkt = _apply_attack(sb, sa, move_b, db, hit_b)
                if dfnt or atkt:
                    break
                if flinch_a:
                    da = 0
                dfnt, atkt = _apply_attack(sa, sb, move_a, da, hit_a)
                if dfnt or atkt:
                    break

            # ターン終了処理
            if _end_of_turn(sa, sb, weather):
                break

        if sa.cur_hp <= 0:
            wins_b += 1
            total_remaining_hp_b += max(0, sb.cur_hp)
        else:
            wins_a += 1
            total_remaining_hp_a += max(0, sa.cur_hp)

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
