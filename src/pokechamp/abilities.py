"""アビリティ・アイテム定数とヘルパー関数

ダメージ計算に使うアビリティ・アイテムテーブルと、タイプ無効/倍率判定の純粋関数を提供する。
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from pokechamp.damage import type_effectiveness
from pokechamp.models import Move, TypeName

if TYPE_CHECKING:
    from pokechamp.battle import BattlePokemon


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


# ---------------------------------------------------------------------------
# アビリティ効果ヘルパー
# ---------------------------------------------------------------------------

_MOLD_BREAKER_ABILITIES: set[str] = {"mold-breaker", "turboblaze", "teravolt"}


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


# ---------------------------------------------------------------------------
# 技判定関数
# ---------------------------------------------------------------------------

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
