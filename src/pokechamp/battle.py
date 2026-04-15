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
        mega = None
        for mega_field in (pokemon.mega, pokemon.mega_x, pokemon.mega_y):
            if mega_field is not None and item == mega_field.stone:
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
        moves = [load_move(name) for name in move_names]

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
# アビリティ効果ヘルパー
# ---------------------------------------------------------------------------

_MOLD_BREAKER_ABILITIES: set[str] = {"mold-breaker", "turboblaze", "teravolt"}


def _get_attack_modifier(attacker: "BattlePokemon", move: Move) -> float:
    """攻撃側アビリティによる攻撃倍率を返す。"""
    mod = 1.0
    if attacker.ability in ("huge-power", "pure-power") and move.category == "physical":
        mod *= 2.0
    if attacker.ability == "hustle" and move.category == "physical":
        mod *= 1.5
    return mod


def _get_stab_multiplier(attacker: "BattlePokemon", move: Move) -> float:
    """STAB倍率を返す (adaptabilityは2.0)。"""
    if move.type in attacker.types:
        return 2.0 if attacker.ability == "adaptability" else 1.5
    return 1.0


def _get_damage_modifier(attacker: "BattlePokemon", move: Move, defender: "BattlePokemon") -> float:
    """アビリティによるダメージ倍率を返す（両側）。"""
    mod = 1.0
    # 攻撃側アビリティ
    if attacker.ability == "water-bubble" and move.type == TypeName.WATER:
        mod *= 2.0
    if attacker.ability == "technician" and move.power <= 60:
        mod *= 1.5
    if attacker.ability == "sheer-force":
        mod *= 1.3
    if attacker.ability == "strong-jaw" and _is_biting_move(move):
        mod *= 1.5
    if attacker.ability == "iron-fist" and _is_punching_move(move):
        mod *= 1.2
    if attacker.ability == "tough-claws" and _is_contact_move(move):
        mod *= 1.3
    if attacker.ability == "mega-launcher" and _is_pulse_move(move):
        mod *= 1.5
    if attacker.ability == "sharpness" and move.name_en in _SLASHING_MOVES:
        mod *= 1.5
    # 防御側アビリティ
    if defender.ability == "fur-coat" and move.category == "physical":
        mod *= 0.5
    if defender.ability == "water-bubble" and move.type == TypeName.FIRE:
        mod *= 0.5
    if defender.ability == "dry-skin" and move.type == TypeName.FIRE:
        mod *= 1.25
    if defender.ability == "thick-fat" and move.type in (TypeName.FIRE, TypeName.ICE):
        mod *= 0.5
    if defender.ability in ("solid-rock", "filter") and _is_super_effective(move, defender):
        mod *= 0.75
    if defender.ability == "purifying-salt" and move.type == TypeName.GHOST:
        mod *= 0.5
    return mod


# ---------------------------------------------------------------------------
# 技カテゴリ判定ヘルパー
# ---------------------------------------------------------------------------

_BITING_MOVES: set[str] = {
    "crunch", "bite", "fire-fang", "ice-fang", "thunder-fang", "poison-fang",
    "psychic-fangs", "hyper-fang", "jaw-lock", "fishious-rend",
}

_PUNCHING_MOVES: set[str] = {
    "mach-punch", "mega-punch", "fire-punch", "ice-punch", "thunder-punch",
    "drain-punch", "focus-punch", "hammer-arm", "shadow-punch", "sky-uppercut",
    "dynamic-punch", "power-up-punch", "bullet-punch", "meteor-mash",
    "comet-punch", "dizzy-punch",
}

_PULSE_MOVES: set[str] = {
    "aura-sphere", "dark-pulse", "dragon-pulse", "water-pulse", "origin-pulse",
    "heal-pulse", "terrain-pulse",
}

_BALL_BOMB_MOVES: set[str] = {
    "shadow-ball", "energy-ball", "sludge-bomb", "focus-blast", "weather-ball",
    "electro-ball", "gyro-ball", "acid-spray", "aura-sphere", "seed-bomb",
    "mud-bomb", "barrage", "bullet-seed", "egg-bomb", "ice-ball",
    "magnet-bomb", "mist-ball", "rock-blast", "zap-cannon",
}

_SLASHING_MOVES: set[str] = {
    "sacred-sword", "leaf-blade", "psycho-cut", "night-slash",
    "x-scissor", "cross-poison", "air-slash", "razor-shell",
    "secret-sword", "ceaseless-edge", "stone-axe", "bitter-blade",
    "kowtow-cleave",
}

# 確定自己デバフ技: 攻撃後に自分のステータスが下がる（確率ではなく確定）
# key=技名, value=[(stat, stages), ...]
_SELF_DEBUFF_MOVES: dict[str, list[tuple[str, int]]] = {
    "draco-meteor": [("sp_attack", -2)],
    "overheat": [("sp_attack", -2)],
    "leaf-storm": [("sp_attack", -2)],
    "fleur-cannon": [("sp_attack", -2)],
    "close-combat": [("defense", -1), ("sp_defense", -1)],
    "superpower": [("attack", -1), ("defense", -1)],
    "hammer-arm": [("speed", -1)],  # 厳密にはステ変化ではなくS低下だが同様に扱う
    "v-create": [("defense", -1), ("sp_defense", -1), ("speed", -1)],
}

_SKIN_ABILITIES: dict[str, TypeName] = {
    "pixilate": TypeName.FAIRY,
    "aerilate": TypeName.FLYING,
    "refrigerate": TypeName.ICE,
    "dragon-skin": TypeName.DRAGON,
}

_HP_THRESHOLD_ABILITIES: dict[str, TypeName] = {
    "blaze": TypeName.FIRE,
    "overgrow": TypeName.GRASS,
    "torrent": TypeName.WATER,
    "swarm": TypeName.BUG,
}


def _is_biting_move(move: Move) -> bool:
    return move.name_en in _BITING_MOVES


def _is_punching_move(move: Move) -> bool:
    return move.name_en in _PUNCHING_MOVES


def _is_contact_move(move: Move) -> bool:
    """物理技を接触技として近似する（ほとんどの物理技は接触技）。"""
    return move.category == "physical"


def _is_pulse_move(move: Move) -> bool:
    return move.name_en in _PULSE_MOVES


def _is_ball_bomb_move(move: Move) -> bool:
    return move.name_en in _BALL_BOMB_MOVES


def _is_super_effective(move: Move, defender: "BattlePokemon") -> bool:
    eff = 1.0
    for def_type in defender.types:
        eff *= type_effectiveness(move.type, def_type)
    return eff > 1.0


def _is_type_immune_by_type(defender: "BattlePokemon", move_type: TypeName) -> bool:
    """防御側アビリティによるタイプ無効を判定する（タイプ名直接指定版）。"""
    ability = defender.ability
    if ability in ("water-absorb", "dry-skin") and move_type == TypeName.WATER:
        return True
    if ability in ("volt-absorb", "lightning-rod") and move_type == TypeName.ELECTRIC:
        return True
    if ability == "levitate" and move_type == TypeName.GROUND:
        return True
    if ability == "flash-fire" and move_type == TypeName.FIRE:
        return True
    if ability == "earth-eater" and move_type == TypeName.GROUND:
        return True
    if ability == "sap-sipper" and move_type == TypeName.GRASS:
        return True
    if ability == "motor-drive" and move_type == TypeName.ELECTRIC:
        return True
    return False


def _is_type_immune(defender: "BattlePokemon", move: Move) -> bool:
    """防御側アビリティによるタイプ無効を判定する。"""
    ability = defender.ability
    move_type = move.type
    if ability in ("water-absorb", "dry-skin") and move_type == TypeName.WATER:
        return True
    if ability in ("volt-absorb", "lightning-rod") and move_type == TypeName.ELECTRIC:
        return True
    if ability == "levitate" and move_type == TypeName.GROUND:
        return True
    if ability == "flash-fire" and move_type == TypeName.FIRE:
        return True
    if ability == "bulletproof" and _is_ball_bomb_move(move):
        return True
    if ability == "earth-eater" and move_type == TypeName.GROUND:
        return True
    if ability == "sap-sipper" and move_type == TypeName.GRASS:
        return True
    if ability == "motor-drive" and move_type == TypeName.ELECTRIC:
        return True
    return False


def _apply_setup(pokemon: BattlePokemon, setup_move_name: str, turns: int) -> None:
    """setup_move_nameの技をturns回分だけステージ補正に適用する（±6でキャップ）。"""
    move = load_move(setup_move_name)
    for _ in range(turns):
        for change in move.stat_changes:
            stat = str(change["stat"])
            stages = int(change["stages"])
            current = pokemon.stage_modifiers.get(stat, 0)
            pokemon.stage_modifiers[stat] = max(-6, min(6, current + stages))


# ---------------------------------------------------------------------------
# 天候定数
# ---------------------------------------------------------------------------

_WEATHER_ABILITIES: dict[str, str] = {
    "drought": "sun",
    "drizzle": "rain",
    "sand-stream": "sand",
    "snow-warning": "snow",
}

_WEATHER_SPEED_ABILITIES: dict[str, str] = {
    "swift-swim": "rain",
    "sand-rush": "sand",
    "chlorophyll": "sun",
    "slush-rush": "snow",
}

_SAND_IMMUNE_TYPES: set[TypeName] = {TypeName.ROCK, TypeName.GROUND, TypeName.STEEL}
_SAND_IMMUNE_ABILITIES: set[str] = {"magic-guard", "overcoat", "sand-force", "sand-rush", "sand-veil"}


def _calc_all_moves(
    attacker: BattlePokemon,
    opponent: BattlePokemon,
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


def _choose_move(
    attacker: BattlePokemon,
    opponent: BattlePokemon,
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

    # ねこだまし: ターン1で自分が遅い場合に使用
    # （先制+ひるみで相手の攻撃を1ターン封じる。自分が速い場合は最大火力のほうが得）
    if turn_number == 1 and my_speed <= opp_speed:
        for move, dmg_range in all_moves:
            if move.name_en == "fake-out":
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

    # アイテムフラグ
    leftovers_a = a.item == "leftovers"
    leftovers_b = b.item == "leftovers"
    leftovers_heal_a = max(1, max_hp_a // 16)
    leftovers_heal_b = max(1, max_hp_b // 16)

    for _ in range(n_trials):
        cur_hp_a = hp_a
        cur_hp_b = hp_b
        sash_a = a.item == "focus-sash"
        sash_b = b.item == "focus-sash"
        sitrus_a = a.item == "sitrus-berry"
        sitrus_b = b.item == "sitrus-berry"
        sitrus_heal_a = max(1, max_hp_a // 4)
        sitrus_heal_b = max(1, max_hp_b // 4)

        # アビリティフラグ (試行ごとにリセット)
        # マルチスケイル: HP満タン時に被ダメージ半減
        # ばけのかわ: 最初の1発を無効化
        disguise_a = a.ability == "disguise"
        disguise_b = b.ability == "disguise"
        # がんじょう: HP満タンから一撃KOを耐える (タスキと同様)
        sturdy_a = a.ability == "sturdy"
        sturdy_b = b.ability == "sturdy"
        # もらいび: 炎技を受けると炎技が1.5倍に (炎は無効化)
        flash_fire_active_a = False  # aのもらいびが発動中
        flash_fire_active_b = False  # bのもらいびが発動中
        # じきゅうりょく: 被弾のたびに防御+1 → ダメージ軽減として追跡
        stamina_boosts_a = 0
        stamina_boosts_b = 0
        # ぎゃくじょう: HP1/2以下で特攻+1 (一度のみ発動)
        berserk_triggered_a = False
        berserk_triggered_b = False
        # ぎゃくじょうの特攻ブーストによるダメージ倍率
        berserk_mult_a = 1.0
        berserk_mult_b = 1.0
        # かそく: ターン終了後に発動するフラグ (発動後は速度を無視して先攻)
        speed_boost_active_a = False
        speed_boost_active_b = False

        # セットアップ技の積みステージ追跡 (インライン計算用)
        atk_boost_a = 0    # 攻撃ランク補正
        spa_boost_a = 0    # 特攻ランク補正
        def_boost_a = 0    # 防御ランク補正
        spd_boost_a = 0    # 特防ランク補正
        spe_boost_a = 0    # 素早さランク補正
        atk_boost_b = 0
        spa_boost_b = 0
        def_boost_b = 0
        spd_boost_b = 0
        spe_boost_b = 0
        setup_used_a = False
        setup_used_b = False
        turn_number = 0

        while cur_hp_a > 0 and cur_hp_b > 0:
            turn_number += 1
            # ターンごとに最適な技を選択
            # 素早さはセットアップによる速度ブーストを考慮
            eff_speed_a = speed_a if not speed_boost_active_a else 999999
            eff_speed_b = speed_b if not speed_boost_active_b else 999999
            if spe_boost_a > 0:
                eff_speed_a = math.floor(eff_speed_a * (2 + spe_boost_a) / 2)
            if spe_boost_b > 0:
                eff_speed_b = math.floor(eff_speed_b * (2 + spe_boost_b) / 2)

            move_a, dmg_range_a_cur = _choose_move(
                a, b, cur_hp_b, eff_speed_a, eff_speed_b,
                all_moves_a, max_dmg_from_b, cur_hp_a, max_hp_a,
                turn_number=turn_number, setup_used=setup_used_a,
                atk_boost=atk_boost_a, spa_boost=spa_boost_a,
            )
            move_b, dmg_range_b_cur = _choose_move(
                b, a, cur_hp_a, eff_speed_b, eff_speed_a,
                all_moves_b, max_dmg_from_a, cur_hp_b, max_hp_b,
                turn_number=turn_number, setup_used=setup_used_b,
                atk_boost=atk_boost_b, spa_boost=spa_boost_b,
            )

            # セットアップ技の処理: ステージを記録しda/db=0に設定
            if move_a and move_a.category == "status" and move_a.stat_changes:
                for change in move_a.stat_changes:
                    stat = str(change["stat"])
                    stages = int(change["stages"])
                    if stat == "attack":
                        atk_boost_a = max(-6, min(6, atk_boost_a + stages))
                    elif stat == "sp_attack":
                        spa_boost_a = max(-6, min(6, spa_boost_a + stages))
                    elif stat == "defense":
                        def_boost_a = max(-6, min(6, def_boost_a + stages))
                    elif stat == "sp_defense":
                        spd_boost_a = max(-6, min(6, spd_boost_a + stages))
                    elif stat == "speed":
                        spe_boost_a = max(-6, min(6, spe_boost_a + stages))
                setup_used_a = True
                da = 0
            else:
                da = random.choice(dmg_range_a_cur)

            if move_b and move_b.category == "status" and move_b.stat_changes:
                for change in move_b.stat_changes:
                    stat = str(change["stat"])
                    stages = int(change["stages"])
                    if stat == "attack":
                        atk_boost_b = max(-6, min(6, atk_boost_b + stages))
                    elif stat == "sp_attack":
                        spa_boost_b = max(-6, min(6, spa_boost_b + stages))
                    elif stat == "defense":
                        def_boost_b = max(-6, min(6, def_boost_b + stages))
                    elif stat == "sp_defense":
                        spd_boost_b = max(-6, min(6, spd_boost_b + stages))
                    elif stat == "speed":
                        spe_boost_b = max(-6, min(6, spe_boost_b + stages))
                setup_used_b = True
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

            # もらいび発動中なら炎技ダメージを1.5倍に (命中時のみ)
            if hit_a and flash_fire_active_a and move_a and move_a.type == TypeName.FIRE:
                da = math.floor(da * 1.5)
            if hit_b and flash_fire_active_b and move_b and move_b.type == TypeName.FIRE:
                db = math.floor(db * 1.5)

            # HP閾値アビリティ (もうか/しんりょく/げきりゅう/むしのしらせ): HP1/3以下で技ダメージ1.5倍 (命中時のみ)
            if hit_a and a.ability in _HP_THRESHOLD_ABILITIES:
                if cur_hp_a <= max_hp_a // 3 and move_a and move_a.type == _HP_THRESHOLD_ABILITIES[a.ability]:
                    da = math.floor(da * 1.5)
            if hit_b and b.ability in _HP_THRESHOLD_ABILITIES:
                if cur_hp_b <= max_hp_b // 3 and move_b and move_b.type == _HP_THRESHOLD_ABILITIES[b.ability]:
                    db = math.floor(db * 1.5)

            # ぎゃくじょう: 発動済みなら特攻技ダメージに倍率適用 (命中時のみ)
            if hit_a and berserk_mult_a > 1.0 and move_a and move_a.category == "special":
                da = math.floor(da * berserk_mult_a)
            if hit_b and berserk_mult_b > 1.0 and move_b and move_b.category == "special":
                db = math.floor(db * berserk_mult_b)

            # じきゅうりょく: 蓄積した防御ブーストを軽減率として適用
            # N回被弾後: 防御ステージ+N → 軽減率 2/(2+N)
            if stamina_boosts_a > 0:
                db = math.floor(db * 2 / (2 + stamina_boosts_a))
            if stamina_boosts_b > 0:
                da = math.floor(da * 2 / (2 + stamina_boosts_b))

            # セットアップ技による攻撃ブーストを適用 (命中時のみ、正負両対応)
            if hit_a and da > 0:
                if atk_boost_a != 0 and move_a and move_a.category == "physical":
                    if atk_boost_a > 0:
                        da = math.floor(da * (2 + atk_boost_a) / 2)
                    else:
                        da = math.floor(da * 2 / (2 + abs(atk_boost_a)))
                if spa_boost_a != 0 and move_a and move_a.category == "special":
                    if spa_boost_a > 0:
                        da = math.floor(da * (2 + spa_boost_a) / 2)
                    else:
                        da = math.floor(da * 2 / (2 + abs(spa_boost_a)))
            if hit_b and db > 0:
                if atk_boost_b != 0 and move_b and move_b.category == "physical":
                    if atk_boost_b > 0:
                        db = math.floor(db * (2 + atk_boost_b) / 2)
                    else:
                        db = math.floor(db * 2 / (2 + abs(atk_boost_b)))
                if spa_boost_b != 0 and move_b and move_b.category == "special":
                    if spa_boost_b > 0:
                        db = math.floor(db * (2 + spa_boost_b) / 2)
                    else:
                        db = math.floor(db * 2 / (2 + abs(spa_boost_b)))

            # セットアップ技による防御ブーストを適用 (被弾ダメージ増減、正負両対応)
            if def_boost_a != 0 and move_b and move_b.category == "physical":
                if def_boost_a > 0:
                    db = math.floor(db * 2 / (2 + def_boost_a))
                else:
                    db = math.floor(db * (2 + abs(def_boost_a)) / 2)
            if spd_boost_a != 0 and move_b and move_b.category == "special":
                if spd_boost_a > 0:
                    db = math.floor(db * 2 / (2 + spd_boost_a))
                else:
                    db = math.floor(db * (2 + abs(spd_boost_a)) / 2)
            if def_boost_b != 0 and move_a and move_a.category == "physical":
                if def_boost_b > 0:
                    da = math.floor(da * 2 / (2 + def_boost_b))
                else:
                    da = math.floor(da * (2 + abs(def_boost_b)) / 2)
            if spd_boost_b != 0 and move_a and move_a.category == "special":
                if spd_boost_b > 0:
                    da = math.floor(da * 2 / (2 + spd_boost_b))
                else:
                    da = math.floor(da * (2 + abs(spd_boost_b)) / 2)

            # 先攻判定: ターンごとに優先度と素早さで決定
            # かそくが発動済みなら素早さを上書き (2ターン目以降)
            cur_speed_a = eff_speed_a if not speed_boost_active_a else 999999
            cur_speed_b = eff_speed_b if not speed_boost_active_b else 999999

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

            # ねこだまし: 命中すればひるみ100%（相手はそのターン行動不可）
            flinch_b = hit_a and move_a is not None and move_a.name_en == "fake-out"
            flinch_a = hit_b and move_b is not None and move_b.name_en == "fake-out"

            if first_is_a:
                prev_hp_b = cur_hp_b
                # マルチスケイル: HP満タン時に被ダメージ半減 (かたやぶりで無効)
                if b.ability == "multiscale" and cur_hp_b == hp_b and hp_b == max_hp_b and a.ability not in _MOLD_BREAKER_ABILITIES:
                    da = math.floor(da * 0.5)
                # ばけのかわ: 最初の1発を無効化 (かたやぶりで無効)
                if disguise_b and a.ability not in _MOLD_BREAKER_ABILITIES:
                    da = 0
                    disguise_b = False
                    # ばけのかわ破壊時に最大HPの1/8ダメージ
                    cur_hp_b -= max(1, max_hp_b // 8)
                    if cur_hp_b <= 0:
                        break
                elif disguise_b:
                    # かたやぶりでばけのかわを貫通: フラグ消費するが無効化しない
                    disguise_b = False
                # もらいびチェック: 炎技を受けた場合
                if b.ability == "flash-fire" and move_a and move_a.type == TypeName.FIRE:
                    da = 0
                    flash_fire_active_b = True
                cur_hp_b -= da
                # きあいのタスキ / がんじょう: HP満タンから一撃で倒される場合HP1で耐える
                # (がんじょうはかたやぶりで無効; タスキはアイテムなので無効にしない)
                if cur_hp_b <= 0 and sash_b and prev_hp_b == hp_b and hp_b == max_hp_b:
                    cur_hp_b = 1
                    sash_b = False
                if cur_hp_b <= 0 and sturdy_b and prev_hp_b == hp_b and hp_b == max_hp_b and a.ability not in _MOLD_BREAKER_ABILITIES:
                    cur_hp_b = 1
                    sturdy_b = False
                if cur_hp_b <= 0:
                    break
                # さめはだ: 接触技を受けたら攻撃側に1/8反動
                if b.ability == "rough-skin" and move_a and _is_contact_move(move_a) and da > 0:
                    cur_hp_a -= max(1, max_hp_a // 8)
                    if cur_hp_a <= 0:
                        break
                # じきゅうりょく: 被弾後に防御+1
                if b.ability == "stamina" and da > 0:
                    stamina_boosts_b = min(6, stamina_boosts_b + 1)
                # ぎゃくじょう: HP1/2以下で特攻+1 (一度のみ)
                if b.ability == "berserk" and not berserk_triggered_b and cur_hp_b <= max_hp_b // 2 and cur_hp_b > 0:
                    berserk_triggered_b = True
                    if move_b and move_b.category == "special":
                        berserk_mult_b = 1.5
                # オボンのみ: HP半分以下で最大HPの1/4回復
                if sitrus_b and cur_hp_b <= max_hp_b // 2:
                    cur_hp_b = min(max_hp_b, cur_hp_b + sitrus_heal_b)
                    sitrus_b = False
                # 確定自己デバフ技: 命中後に攻撃側ステータス低下
                if hit_a and move_a and move_a.name_en in _SELF_DEBUFF_MOVES:
                    for _stat, _stages in _SELF_DEBUFF_MOVES[move_a.name_en]:
                        if _stat == "attack":
                            atk_boost_a = max(-6, atk_boost_a + _stages)
                        elif _stat == "sp_attack":
                            spa_boost_a = max(-6, spa_boost_a + _stages)
                        elif _stat == "defense":
                            def_boost_a = max(-6, def_boost_a + _stages)
                        elif _stat == "sp_defense":
                            spd_boost_a = max(-6, spd_boost_a + _stages)
                        elif _stat == "speed":
                            spe_boost_a = max(-6, spe_boost_a + _stages)

                # ひるみ: 先攻のねこだましが当たったら後攻は行動不可
                if flinch_b:
                    db = 0

                prev_hp_a = cur_hp_a
                # マルチスケイル: HP満タン時に被ダメージ半減 (かたやぶりで無効)
                if a.ability == "multiscale" and cur_hp_a == hp_a and hp_a == max_hp_a and b.ability not in _MOLD_BREAKER_ABILITIES:
                    db = math.floor(db * 0.5)
                # ばけのかわ: 最初の1発を無効化 (かたやぶりで無効)
                if disguise_a and b.ability not in _MOLD_BREAKER_ABILITIES:
                    db = 0
                    disguise_a = False
                    cur_hp_a -= max(1, max_hp_a // 8)
                    if cur_hp_a <= 0:
                        break
                elif disguise_a:
                    disguise_a = False
                # もらいびチェック: 炎技を受けた場合
                if a.ability == "flash-fire" and move_b and move_b.type == TypeName.FIRE:
                    db = 0
                    flash_fire_active_a = True
                cur_hp_a -= db
                if cur_hp_a <= 0 and sash_a and prev_hp_a == hp_a and hp_a == max_hp_a:
                    cur_hp_a = 1
                    sash_a = False
                if cur_hp_a <= 0 and sturdy_a and prev_hp_a == hp_a and hp_a == max_hp_a and b.ability not in _MOLD_BREAKER_ABILITIES:
                    cur_hp_a = 1
                    sturdy_a = False
                if cur_hp_a <= 0:
                    break
                # さめはだ: 接触技を受けたら攻撃側に1/8反動
                if a.ability == "rough-skin" and move_b and _is_contact_move(move_b) and db > 0:
                    cur_hp_b -= max(1, max_hp_b // 8)
                    if cur_hp_b <= 0:
                        break
                # じきゅうりょく: 被弾後に防御+1
                if a.ability == "stamina" and db > 0:
                    stamina_boosts_a = min(6, stamina_boosts_a + 1)
                # ぎゃくじょう: HP1/2以下で特攻+1 (一度のみ)
                if a.ability == "berserk" and not berserk_triggered_a and cur_hp_a <= max_hp_a // 2 and cur_hp_a > 0:
                    berserk_triggered_a = True
                    if move_a and move_a.category == "special":
                        berserk_mult_a = 1.5
                if sitrus_a and cur_hp_a <= max_hp_a // 2:
                    cur_hp_a = min(max_hp_a, cur_hp_a + sitrus_heal_a)
                    sitrus_a = False
                # 確定自己デバフ技: 命中後に攻撃側ステータス低下
                if hit_b and move_b and move_b.name_en in _SELF_DEBUFF_MOVES:
                    for _stat, _stages in _SELF_DEBUFF_MOVES[move_b.name_en]:
                        if _stat == "attack":
                            atk_boost_b = max(-6, atk_boost_b + _stages)
                        elif _stat == "sp_attack":
                            spa_boost_b = max(-6, spa_boost_b + _stages)
                        elif _stat == "defense":
                            def_boost_b = max(-6, def_boost_b + _stages)
                        elif _stat == "sp_defense":
                            spd_boost_b = max(-6, spd_boost_b + _stages)
                        elif _stat == "speed":
                            spe_boost_b = max(-6, spe_boost_b + _stages)
            else:
                prev_hp_a = cur_hp_a
                # マルチスケイル (かたやぶりで無効)
                if a.ability == "multiscale" and cur_hp_a == hp_a and hp_a == max_hp_a and b.ability not in _MOLD_BREAKER_ABILITIES:
                    db = math.floor(db * 0.5)
                # ばけのかわ (かたやぶりで無効)
                if disguise_a and b.ability not in _MOLD_BREAKER_ABILITIES:
                    db = 0
                    disguise_a = False
                    cur_hp_a -= max(1, max_hp_a // 8)
                    if cur_hp_a <= 0:
                        break
                elif disguise_a:
                    disguise_a = False
                # もらいびチェック
                if a.ability == "flash-fire" and move_b and move_b.type == TypeName.FIRE:
                    db = 0
                    flash_fire_active_a = True
                cur_hp_a -= db
                if cur_hp_a <= 0 and sash_a and prev_hp_a == hp_a and hp_a == max_hp_a:
                    cur_hp_a = 1
                    sash_a = False
                if cur_hp_a <= 0 and sturdy_a and prev_hp_a == hp_a and hp_a == max_hp_a and b.ability not in _MOLD_BREAKER_ABILITIES:
                    cur_hp_a = 1
                    sturdy_a = False
                if cur_hp_a <= 0:
                    break
                # さめはだ: 接触技を受けたら攻撃側に1/8反動
                if a.ability == "rough-skin" and move_b and _is_contact_move(move_b) and db > 0:
                    cur_hp_b -= max(1, max_hp_b // 8)
                    if cur_hp_b <= 0:
                        break
                # じきゅうりょく
                if a.ability == "stamina" and db > 0:
                    stamina_boosts_a = min(6, stamina_boosts_a + 1)
                # ぎゃくじょう: HP1/2以下で特攻+1 (一度のみ)
                if a.ability == "berserk" and not berserk_triggered_a and cur_hp_a <= max_hp_a // 2 and cur_hp_a > 0:
                    berserk_triggered_a = True
                    if move_a and move_a.category == "special":
                        berserk_mult_a = 1.5
                if sitrus_a and cur_hp_a <= max_hp_a // 2:
                    cur_hp_a = min(max_hp_a, cur_hp_a + sitrus_heal_a)
                    sitrus_a = False
                # 確定自己デバフ技: 命中後に攻撃側ステータス低下
                if hit_b and move_b and move_b.name_en in _SELF_DEBUFF_MOVES:
                    for _stat, _stages in _SELF_DEBUFF_MOVES[move_b.name_en]:
                        if _stat == "attack":
                            atk_boost_b = max(-6, atk_boost_b + _stages)
                        elif _stat == "sp_attack":
                            spa_boost_b = max(-6, spa_boost_b + _stages)
                        elif _stat == "defense":
                            def_boost_b = max(-6, def_boost_b + _stages)
                        elif _stat == "sp_defense":
                            spd_boost_b = max(-6, spd_boost_b + _stages)
                        elif _stat == "speed":
                            spe_boost_b = max(-6, spe_boost_b + _stages)

                # ひるみ: bの先攻ねこだましが当たったらaは行動不可
                if flinch_a:
                    da = 0

                prev_hp_b = cur_hp_b
                # マルチスケイル (かたやぶりで無効)
                if b.ability == "multiscale" and cur_hp_b == hp_b and hp_b == max_hp_b and a.ability not in _MOLD_BREAKER_ABILITIES:
                    da = math.floor(da * 0.5)
                # ばけのかわ (かたやぶりで無効)
                if disguise_b and a.ability not in _MOLD_BREAKER_ABILITIES:
                    da = 0
                    disguise_b = False
                    cur_hp_b -= max(1, max_hp_b // 8)
                    if cur_hp_b <= 0:
                        break
                elif disguise_b:
                    disguise_b = False
                # もらいびチェック
                if b.ability == "flash-fire" and move_a and move_a.type == TypeName.FIRE:
                    da = 0
                    flash_fire_active_b = True
                cur_hp_b -= da
                if cur_hp_b <= 0 and sash_b and prev_hp_b == hp_b and hp_b == max_hp_b:
                    cur_hp_b = 1
                    sash_b = False
                if cur_hp_b <= 0 and sturdy_b and prev_hp_b == hp_b and hp_b == max_hp_b and a.ability not in _MOLD_BREAKER_ABILITIES:
                    cur_hp_b = 1
                    sturdy_b = False
                if cur_hp_b <= 0:
                    break
                # さめはだ: 接触技を受けたら攻撃側に1/8反動
                if b.ability == "rough-skin" and move_a and _is_contact_move(move_a) and da > 0:
                    cur_hp_a -= max(1, max_hp_a // 8)
                    if cur_hp_a <= 0:
                        break
                # じきゅうりょく
                if b.ability == "stamina" and da > 0:
                    stamina_boosts_b = min(6, stamina_boosts_b + 1)
                # ぎゃくじょう: HP1/2以下で特攻+1 (一度のみ)
                if b.ability == "berserk" and not berserk_triggered_b and cur_hp_b <= max_hp_b // 2 and cur_hp_b > 0:
                    berserk_triggered_b = True
                    if move_b and move_b.category == "special":
                        berserk_mult_b = 1.5
                if sitrus_b and cur_hp_b <= max_hp_b // 2:
                    cur_hp_b = min(max_hp_b, cur_hp_b + sitrus_heal_b)
                    sitrus_b = False
                # 確定自己デバフ技: 命中後に攻撃側ステータス低下
                if hit_a and move_a and move_a.name_en in _SELF_DEBUFF_MOVES:
                    for _stat, _stages in _SELF_DEBUFF_MOVES[move_a.name_en]:
                        if _stat == "attack":
                            atk_boost_a = max(-6, atk_boost_a + _stages)
                        elif _stat == "sp_attack":
                            spa_boost_a = max(-6, spa_boost_a + _stages)
                        elif _stat == "defense":
                            def_boost_a = max(-6, def_boost_a + _stages)
                        elif _stat == "sp_defense":
                            spd_boost_a = max(-6, spd_boost_a + _stages)
                        elif _stat == "speed":
                            spe_boost_a = max(-6, spe_boost_a + _stages)

            # ターン終了時: たべのこし回復
            if leftovers_a and cur_hp_a > 0:
                cur_hp_a = min(max_hp_a, cur_hp_a + leftovers_heal_a)
            if leftovers_b and cur_hp_b > 0:
                cur_hp_b = min(max_hp_b, cur_hp_b + leftovers_heal_b)

            # ターン終了時: 砂嵐ダメージ (非岩・地・鋼タイプに最大HPの1/16)
            if weather == "sand":
                if cur_hp_a > 0 and not (set(a.types) & _SAND_IMMUNE_TYPES) and a.ability not in _SAND_IMMUNE_ABILITIES:
                    sand_dmg_a = max(1, max_hp_a // 16)
                    cur_hp_a -= sand_dmg_a
                    if cur_hp_a <= 0:
                        break
                if cur_hp_b > 0 and not (set(b.types) & _SAND_IMMUNE_TYPES) and b.ability not in _SAND_IMMUNE_ABILITIES:
                    sand_dmg_b = max(1, max_hp_b // 16)
                    cur_hp_b -= sand_dmg_b
                    if cur_hp_b <= 0:
                        break

            # かそく: ターン終了時に素早さ上昇 → 次ターンから速度ブースト発動
            if a.ability == "speed-boost":
                speed_boost_active_a = True
            if b.ability == "speed-boost":
                speed_boost_active_b = True

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
