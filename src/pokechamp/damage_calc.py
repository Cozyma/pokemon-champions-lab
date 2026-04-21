"""ダメージ計算クエリ & 逆算推定

damage_query(): 順方向ダメージ計算 — ビルド指定でダメージ範囲を算出
estimate_attacker(): 逆方向 — 被ダメージから相手の性格・EV・アイテムを推定
"""
from __future__ import annotations

import math

from pokechamp.damage import calc_damage_range, calc_stat, type_effectiveness
from pokechamp.loader import load_move, load_pokemon
from pokechamp.models import (
    AttackerEstimate,
    BaseStats,
    BuildCandidate,
    DamageReport,
    DefenderCandidate,
    DefenderEstimate,
    Move,
    Nature,
    TypeName,
)
from pokechamp.showdown_data import get_species_base_stats, get_species_types

LEVEL = 50

# ---------------------------------------------------------------------------
# 配分の基本法則 (チャンピオンズ仕様)
# 各EV 0〜32, 合計66。H32 を先に確保するのが定石。
# 推定時、H32 前提の配分を「標準」、それ以外を「特殊」として重み付けする。
# ---------------------------------------------------------------------------
HP_EV_STANDARD = 32  # 標準的な HP EV

# EV 略称マップ
_STAT_ABBREV: dict[str, str] = {
    "h": "hp", "a": "attack", "b": "defense",
    "c": "sp_attack", "d": "sp_defense", "s": "speed",
}

# ---------------------------------------------------------------------------
# 攻撃側アイテム候補 (逆算で列挙)
# ---------------------------------------------------------------------------
_OFFENSIVE_ITEM_SCENARIOS: list[tuple[str, str, float, float, str]] = [
    # (key, label, stat_mult, dmg_mult, category_constraint)
    # category_constraint: "" = any, "physical"/"special" = that only
    ("", "なし", 1.0, 1.0, ""),
    ("life-orb", "いのちのたま", 1.0, 1.3, ""),
    ("choice-band", "こだわりハチマキ", 1.5, 1.0, "physical"),
    ("choice-specs", "こだわりメガネ", 1.5, 1.0, "special"),
]

# タイプ強化アイテム (逆算で追加)
_TYPE_BOOST_ITEMS: dict[str, tuple[str, str]] = {
    "fire": ("charcoal", "もくたん"),
    "water": ("mystic-water", "しんぴのしずく"),
    "electric": ("magnet", "じしゃく"),
    "grass": ("miracle-seed", "きせきのタネ"),
    "ice": ("never-melt-ice", "とけないこおり"),
    "fighting": ("black-belt", "くろおび"),
    "poison": ("poison-barb", "どくバリ"),
    "ground": ("soft-sand", "やわらかいすな"),
    "flying": ("sharp-beak", "するどいくちばし"),
    "psychic": ("twisted-spoon", "まがったスプーン"),
    "bug": ("silver-powder", "ぎんのこな"),
    "rock": ("hard-stone", "かたいいし"),
    "ghost": ("spell-tag", "のろいのおふだ"),
    "dragon": ("dragon-fang", "りゅうのキバ"),
    "dark": ("black-glasses", "くろいメガネ"),
    "steel": ("metal-coat", "メタルコート"),
    "fairy": ("fairy-feather", "フェアリーフェザー"),
    "normal": ("silk-scarf", "シルクのスカーフ"),
}


# ---------------------------------------------------------------------------
# ヘルパー
# ---------------------------------------------------------------------------


def parse_evs(ev_str: str) -> dict[str, int]:
    """EV 文字列 'h32,c32,s2' を dict に変換する。"""
    evs: dict[str, int] = {
        "hp": 0, "attack": 0, "defense": 0,
        "sp_attack": 0, "sp_defense": 0, "speed": 0,
    }
    if not ev_str:
        return evs
    for part in ev_str.lower().split(","):
        part = part.strip()
        if not part:
            continue
        key = part[0]
        if key in _STAT_ABBREV and len(part) > 1:
            evs[_STAT_ABBREV[key]] = int(part[1:])
    return evs


def _resolve_form(
    pokemon_data: object,
    item: str,
    ability_hint: str,
) -> tuple[object, list[TypeName], str]:
    """メガシンカ判定して (base_stats, types, ability) を返す。

    pokemon_data は loader.load_pokemon() の戻り値。
    """
    item_lower = item.lower().replace(" ", "").replace("-", "") if item else ""

    for mega_field in (pokemon_data.mega, pokemon_data.mega_x, pokemon_data.mega_y):  # type: ignore[attr-defined]
        if mega_field is None:
            continue
        stone_lower = mega_field.stone.lower().replace(" ", "").replace("-", "")
        if item_lower == stone_lower:
            return mega_field.base_stats, mega_field.types, mega_field.ability

    # Showdown 形式のメガストーン名マッチ
    if item_lower:
        species_key = pokemon_data.name_en.lower().replace("-", "")  # type: ignore[attr-defined]
        for mega_field in (pokemon_data.mega, pokemon_data.mega_x, pokemon_data.mega_y):  # type: ignore[attr-defined]
            if mega_field is None:
                continue
            if item_lower.startswith(species_key[:5]):
                return mega_field.base_stats, mega_field.types, mega_field.ability

    # 通常フォーム
    abilities = pokemon_data.abilities  # type: ignore[attr-defined]
    resolved_ability = ability_hint if ability_hint else (abilities[0] if abilities else "")
    return pokemon_data.base_stats, pokemon_data.types, resolved_ability  # type: ignore[attr-defined]


def _load_species(species: str) -> tuple[object, str]:
    """種族名からポケモンデータを読み込む。

    フォーム付き名 (例: aegislash-blade) の場合、YAML に無ければ
    Showdown pokedex.json にフォールバックする。

    Returns:
        (pokemon_data_or_proxy, base_species_name)
    """
    try:
        return load_pokemon(species), species
    except FileNotFoundError:
        pass
    # Showdown pokedex.json にフォールバック
    sd_stats = get_species_base_stats(species)
    sd_types = get_species_types(species)
    if sd_stats is None:
        raise FileNotFoundError(f"Species not found: {species}")
    # ベース種族名を推定 (aegislash-blade → aegislash)
    base_name = species.rsplit("-", 1)[0] if "-" in species else species
    try:
        base_poke = load_pokemon(base_name)
    except FileNotFoundError:
        base_poke = None
    # プロキシオブジェクトを構築
    proxy = _ShowdownSpeciesProxy(
        name_en=species,
        base_stats=BaseStats(**sd_stats),
        types=[TypeName(t) for t in (sd_types or [])],
        abilities=base_poke.abilities if base_poke else [],
        mega=None, mega_x=None, mega_y=None,
    )
    return proxy, species


class _ShowdownSpeciesProxy:
    """Showdown pokedex.json から構築した軽量ポケモンデータ。"""
    __slots__ = ("name_en", "base_stats", "types", "abilities", "mega", "mega_x", "mega_y")

    def __init__(
        self,
        name_en: str,
        base_stats: BaseStats,
        types: list[TypeName],
        abilities: list[str],
        mega: object | None,
        mega_x: object | None,
        mega_y: object | None,
    ) -> None:
        self.name_en = name_en
        self.base_stats = base_stats
        self.types = types
        self.abilities = abilities
        self.mega = mega
        self.mega_x = mega_x
        self.mega_y = mega_y


def _compute_all_stats(
    base_stats: object,
    original_hp_base: int,
    evs: dict[str, int],
    nature: Nature,
    level: int,
    *,
    is_mega: bool = False,
) -> dict[str, int]:
    """全6ステータスの実数値を計算する。"""
    stat_names = ["hp", "attack", "defense", "sp_attack", "sp_defense", "speed"]
    stats: dict[str, int] = {}
    for sn in stat_names:
        if is_mega and sn == "hp":
            base = original_hp_base
        else:
            base = getattr(base_stats, sn)
        stats[sn] = calc_stat(
            base=base, iv=31, ev=evs.get(sn, 0),
            level=level, nature=nature, stat_name=sn,
        )
    return stats


def _compute_type_eff(move_type: TypeName, defender_types: list[TypeName]) -> float:
    """複合タイプ対応のタイプ相性を計算する。"""
    eff = 1.0
    for dt in defender_types:
        eff *= type_effectiveness(move_type, dt)
    return eff


def _apply_stat_item(
    stat_value: int,
    item: str,
    stat_name: str,
    move_category: str,
) -> int:
    """アイテムによるステータス補正を適用する。

    - こだわりハチマキ: 物理攻撃 ×1.5
    - こだわりメガネ: 特殊攻撃 ×1.5
    - こだわりスカーフ: 素早さ ×1.5
    - とつげきチョッキ: 特防 ×1.5 (特殊技を受ける場合)
    """
    if item == "choice-band" and stat_name == "attack" and move_category == "physical":
        return math.floor(stat_value * 1.5)
    if item == "choice-specs" and stat_name == "sp_attack" and move_category == "special":
        return math.floor(stat_value * 1.5)
    if item == "choice-scarf" and stat_name == "speed":
        return math.floor(stat_value * 1.5)
    if item == "assault-vest" and stat_name == "sp_defense" and move_category == "special":
        return math.floor(stat_value * 1.5)
    return stat_value


def _get_item_damage_mult(item: str, move_type: TypeName) -> float:
    """アイテムによるダメージ補正倍率を返す。"""
    if item == "life-orb":
        return 1.3
    # タイプ強化アイテム (1.2倍)
    type_key = move_type.value
    if type_key in _TYPE_BOOST_ITEMS:
        item_name, _ = _TYPE_BOOST_ITEMS[type_key]
        if item == item_name:
            return 1.2
    return 1.0


def _get_ability_atk_modifier(ability: str, move_category: str) -> float:
    """攻撃側アビリティによる攻撃実数値補正。"""
    mod = 1.0
    if ability in ("huge-power", "pure-power") and move_category == "physical":
        mod *= 2.0
    if ability == "hustle" and move_category == "physical":
        mod *= 1.5
    return mod


def _get_ability_damage_modifier(
    atk_ability: str,
    def_ability: str,
    move: Move,
    type_eff: float,
) -> float:
    """アビリティによるダメージ倍率 (攻撃側 + 防御側)。"""
    mod = 1.0
    # 攻撃側
    if atk_ability == "water-bubble" and move.type == TypeName.WATER:
        mod *= 2.0
    if atk_ability == "technician" and move.power <= 60:
        mod *= 1.5
    if atk_ability == "sheer-force":
        mod *= 1.3
    if atk_ability == "strong-jaw" and move.name_en in {
        "crunch", "bite", "fire-fang", "ice-fang", "thunder-fang",
        "poison-fang", "psychic-fangs", "hyper-fang", "jaw-lock", "fishious-rend",
    }:
        mod *= 1.5
    if atk_ability == "iron-fist" and move.name_en in {
        "mach-punch", "mega-punch", "fire-punch", "ice-punch", "thunder-punch",
        "drain-punch", "focus-punch", "hammer-arm", "shadow-punch", "sky-uppercut",
        "dynamic-punch", "power-up-punch", "bullet-punch", "meteor-mash",
    }:
        mod *= 1.2
    if atk_ability == "tough-claws" and move.category == "physical":
        mod *= 1.3
    if atk_ability == "mega-launcher" and move.name_en in {
        "aura-sphere", "dark-pulse", "dragon-pulse", "water-pulse",
        "origin-pulse", "heal-pulse", "terrain-pulse",
    }:
        mod *= 1.5
    if atk_ability == "sharpness" and move.name_en in {
        "sacred-sword", "leaf-blade", "psycho-cut", "night-slash",
        "x-scissor", "cross-poison", "air-slash", "razor-shell",
        "secret-sword", "ceaseless-edge", "stone-axe", "bitter-blade", "kowtow-cleave",
    }:
        mod *= 1.5
    # adaptability: STAB 2.0 → 差分を乗算 (2.0/1.5)
    if atk_ability == "adaptability" and move.type in _get_types_placeholder():
        pass  # handled via stab logic in caller
    # 防御側
    if def_ability == "fur-coat" and move.category == "physical":
        mod *= 0.5
    if def_ability == "water-bubble" and move.type == TypeName.FIRE:
        mod *= 0.5
    if def_ability == "dry-skin" and move.type == TypeName.FIRE:
        mod *= 1.25
    if def_ability == "thick-fat" and move.type in (TypeName.FIRE, TypeName.ICE):
        mod *= 0.5
    if def_ability in ("solid-rock", "filter") and type_eff > 1.0:
        mod *= 0.75
    if def_ability == "purifying-salt" and move.type == TypeName.GHOST:
        mod *= 0.5
    return mod


def _get_types_placeholder() -> list:
    """adaptability のプレースホルダ (呼び出し元で処理するため空)。"""
    return []


def _calc_nhko(damage_range: list[int], hp: int) -> tuple[int, int | None, int]:
    """n発情報を計算する。

    Returns:
        (guaranteed_n, random_n | None, random_count)
        - guaranteed_n: 確定n発 (最低乱数 ×n >= HP)
        - random_n: 乱数n発 (None なら確定と同じ)
        - random_count: 乱数n発時の KO ロール数 (/16)
    """
    min_d = min(damage_range)
    max_d = max(damage_range)

    if max_d <= 0:
        return (99, None, 0)

    # 確定n発: 最低乱数で n回当てれば落ちる
    g_n = math.ceil(hp / min_d) if min_d > 0 else 99

    # 乱数n発: 最高乱数なら何回で落ちるか
    p_n = math.ceil(hp / max_d) if max_d > 0 else 99

    if p_n == g_n:
        return (g_n, None, 16)

    # p_n < g_n: 高乱数なら p_n 発で落ちるが、低乱数だと g_n 発必要
    threshold = math.ceil(hp / p_n)
    count = sum(1 for d in damage_range if d >= threshold)
    return (g_n, p_n, count)


# ---------------------------------------------------------------------------
# 順方向: damage_query
# ---------------------------------------------------------------------------


def damage_query(
    *,
    attacker_species: str,
    attacker_nature: Nature,
    attacker_evs: dict[str, int],
    attacker_item: str = "",
    attacker_ability: str = "",
    move_name: str,
    defender_species: str,
    defender_nature: Nature,
    defender_evs: dict[str, int],
    defender_item: str = "",
    defender_ability: str = "",
    level: int = LEVEL,
) -> DamageReport:
    """順方向ダメージ計算。ビルドを指定してダメージ範囲を算出する。"""
    # データ読み込み (_load_species はフォーム名に対応)
    atk_poke, _ = _load_species(attacker_species)
    def_poke, _ = _load_species(defender_species)
    move = load_move(move_name)

    # フォーム解決 (メガシンカ含む)
    atk_base, atk_types, atk_ability = _resolve_form(atk_poke, attacker_item, attacker_ability)
    def_base, def_types, def_ability = _resolve_form(def_poke, defender_item, defender_ability)

    is_atk_mega = atk_base is not atk_poke.base_stats
    is_def_mega = def_base is not def_poke.base_stats

    # 実数値計算
    atk_stats = _compute_all_stats(
        atk_base, atk_poke.base_stats.hp, attacker_evs, attacker_nature, level,
        is_mega=is_atk_mega,
    )
    def_stats = _compute_all_stats(
        def_base, def_poke.base_stats.hp, defender_evs, defender_nature, level,
        is_mega=is_def_mega,
    )

    # 攻撃/防御ステータス選択
    if move.category == "physical":
        a_stat_name, d_stat_name = "attack", "defense"
    else:
        a_stat_name, d_stat_name = "sp_attack", "sp_defense"

    a_stat = atk_stats[a_stat_name]
    d_stat = def_stats[d_stat_name]

    # アイテムによるステータス補正
    a_stat = _apply_stat_item(a_stat, attacker_item, a_stat_name, move.category)
    d_stat = _apply_stat_item(d_stat, defender_item, d_stat_name, move.category)

    # アビリティによる攻撃補正
    a_stat = math.floor(a_stat * _get_ability_atk_modifier(atk_ability, move.category))

    # タイプ相性
    eff = _compute_type_eff(move.type, def_types)

    # STAB
    stab = move.type in atk_types

    # アイテムダメージ補正
    item_mod = _get_item_damage_mult(attacker_item, move.type)

    # アビリティダメージ補正
    item_mod *= _get_ability_damage_modifier(atk_ability, def_ability, move, eff)

    # adaptability の差分補正
    if stab and atk_ability == "adaptability":
        item_mod *= 2.0 / 1.5

    # ダメージ計算
    dmg = calc_damage_range(
        level=level,
        power=move.power,
        attack_stat=a_stat,
        defense_stat=d_stat,
        stab=stab,
        type_eff=eff,
        item_modifier=item_mod,
    )

    defender_hp = def_stats["hp"]
    min_d, max_d = min(dmg), max(dmg)
    g_n, r_n, r_count = _calc_nhko(dmg, defender_hp)

    return DamageReport(
        attacker_name=attacker_species,
        defender_name=defender_species,
        move_name=move_name,
        move_type=move.type,
        move_category=move.category,
        attack_stat=a_stat,
        defense_stat=d_stat,
        defender_hp=defender_hp,
        damage_all=dmg,
        min_damage=min_d,
        max_damage=max_d,
        min_percent=round(min_d / defender_hp * 100, 1) if defender_hp > 0 else 0.0,
        max_percent=round(max_d / defender_hp * 100, 1) if defender_hp > 0 else 0.0,
        type_eff=eff,
        stab=stab,
        nhko_guaranteed=g_n,
        nhko_random=r_n,
        nhko_random_count=r_count,
    )


# ---------------------------------------------------------------------------
# 逆方向: estimate_attacker
# ---------------------------------------------------------------------------


def estimate_attacker(
    *,
    observed_damage: int,
    defender_species: str,
    defender_nature: Nature,
    defender_evs: dict[str, int],
    defender_item: str = "",
    defender_ability: str = "",
    attacker_species: str,
    move_name: str,
    attacker_ability: str = "",
    attacker_is_mega: bool = False,
    level: int = LEVEL,
) -> AttackerEstimate:
    """被ダメージから相手の性格・EV・アイテムを推定する。

    Args:
        observed_damage: 実際に受けたダメージ値
        defender_*: 自分のポケモン (完全既知)
        attacker_species: 相手の種族名
        move_name: 使われた技名
        attacker_ability: 相手の特性 (分かっていれば)
        attacker_is_mega: メガシンカしているか
    """
    # 防御側 (自分) のデータ
    def_poke, _ = _load_species(defender_species)
    def_base, def_types, def_ability = _resolve_form(def_poke, defender_item, defender_ability)
    is_def_mega = def_base is not def_poke.base_stats
    def_stats = _compute_all_stats(
        def_base, def_poke.base_stats.hp, defender_evs, defender_nature, level,
        is_mega=is_def_mega,
    )

    # 技
    move = load_move(move_name)
    stat_name = "attack" if move.category == "physical" else "sp_attack"
    d_stat_name = "defense" if move.category == "physical" else "sp_defense"
    d_stat = def_stats[d_stat_name]
    d_stat = _apply_stat_item(d_stat, defender_item, d_stat_name, move.category)

    # 攻撃側の種族データ
    atk_poke, _ = _load_species(attacker_species)

    # メガ判定
    if attacker_is_mega:
        # メガ形態を探す
        for mega_field in (atk_poke.mega, atk_poke.mega_x, atk_poke.mega_y):
            if mega_field is not None:
                atk_base_stat_val = getattr(mega_field.base_stats, stat_name)
                atk_types = mega_field.types
                if not attacker_ability:
                    attacker_ability = mega_field.ability
                break
        else:
            atk_base_stat_val = getattr(atk_poke.base_stats, stat_name)
            atk_types = atk_poke.types
    else:
        atk_base_stat_val = getattr(atk_poke.base_stats, stat_name)
        atk_types = atk_poke.types

    if not attacker_ability:
        attacker_ability = atk_poke.abilities[0] if atk_poke.abilities else ""

    # タイプ相性
    type_eff = _compute_type_eff(move.type, def_types)
    stab = move.type in atk_types

    # アビリティ補正 (既知なら反映)
    ability_atk_mod = _get_ability_atk_modifier(attacker_ability, move.category)
    ability_dmg_mod = _get_ability_damage_modifier(
        attacker_ability, def_ability, move, type_eff,
    )
    if stab and attacker_ability == "adaptability":
        ability_dmg_mod *= 2.0 / 1.5

    # アイテム候補の構築
    item_scenarios: list[tuple[str, str, float, float]] = []

    if attacker_is_mega:
        # メガなのでアイテムはメガストーン固定 → 補正なし
        item_scenarios.append(("mega-stone", "メガストーン", 1.0, 1.0))
    else:
        for key, label, s_mult, d_mult, cat_constraint in _OFFENSIVE_ITEM_SCENARIOS:
            if cat_constraint and cat_constraint != move.category:
                continue
            item_scenarios.append((key, label, s_mult, d_mult))
        # タイプ強化アイテム
        type_key = move.type.value
        if type_key in _TYPE_BOOST_ITEMS:
            item_name, item_label = _TYPE_BOOST_ITEMS[type_key]
            item_scenarios.append((item_name, item_label, 1.0, 1.2))

    # 全候補を列挙
    candidates: list[BuildCandidate] = []
    defender_hp = def_stats["hp"]

    for item_key, item_label, stat_mult, dmg_mult in item_scenarios:
        total_dmg_mult = dmg_mult * ability_dmg_mod
        for nature in Nature:
            for ev in range(0, 33):
                raw_stat = calc_stat(
                    base=atk_base_stat_val, iv=31, ev=ev,
                    level=level, nature=nature, stat_name=stat_name,
                )
                effective_stat = math.floor(
                    math.floor(raw_stat * stat_mult) * ability_atk_mod,
                )

                dmg_range = calc_damage_range(
                    level=level,
                    power=move.power,
                    attack_stat=effective_stat,
                    defense_stat=d_stat,
                    stab=stab,
                    type_eff=type_eff,
                    item_modifier=total_dmg_mult,
                )

                if min(dmg_range) <= observed_damage <= max(dmg_range):
                    candidates.append(BuildCandidate(
                        nature=nature,
                        ev=ev,
                        item=item_key,
                        item_label=item_label,
                        stat_value=raw_stat,
                    ))

    return AttackerEstimate(
        attacker_species=attacker_species,
        move_name=move_name,
        stat_name=stat_name,
        observed_damage=observed_damage,
        defender_hp=defender_hp,
        defender_stat=d_stat,
        type_eff=type_eff,
        stab=stab,
        candidates=candidates,
    )


# ---------------------------------------------------------------------------
# 逆方向: estimate_defender
# ---------------------------------------------------------------------------


def estimate_defender(
    *,
    survived: bool = True,
    attacker_species: str,
    attacker_nature: Nature,
    attacker_evs: dict[str, int],
    attacker_item: str = "",
    attacker_ability: str = "",
    move_name: str,
    defender_species: str,
    defender_ability: str = "",
    level: int = LEVEL,
) -> DefenderEstimate:
    """攻撃を耐えた/耐えなかった事実から防御側の配分を推定する。

    H32 を前提とする標準配分を優先的に返す。

    Args:
        survived: True=耐えた (推定対象は「耐えうる配分」)
        attacker_*: 攻撃側 (自分 = 完全既知)
        move_name: 使った技
        defender_species: 相手のポケモン (フォーム名対応)
        defender_ability: 相手の特性 (分かっていれば)
    """
    # 攻撃側 (自分)
    atk_poke, _ = _load_species(attacker_species)
    move = load_move(move_name)

    atk_base, atk_types, atk_ability = _resolve_form(
        atk_poke, attacker_item, attacker_ability,
    )
    is_atk_mega = atk_base is not atk_poke.base_stats
    atk_stats = _compute_all_stats(
        atk_base, atk_poke.base_stats.hp, attacker_evs, attacker_nature, level,
        is_mega=is_atk_mega,
    )

    if move.category == "physical":
        a_stat_name, d_stat_name = "attack", "defense"
    else:
        a_stat_name, d_stat_name = "sp_attack", "sp_defense"

    a_stat = atk_stats[a_stat_name]
    a_stat = _apply_stat_item(a_stat, attacker_item, a_stat_name, move.category)
    a_stat = math.floor(a_stat * _get_ability_atk_modifier(atk_ability, move.category))

    # 防御側の種族データ
    def_poke, _ = _load_species(defender_species)
    def_base, def_types, def_ability_resolved = _resolve_form(
        def_poke, "", defender_ability,
    )

    hp_base = def_poke.base_stats.hp
    d_base_val = getattr(def_base, d_stat_name)

    # タイプ相性
    type_eff = _compute_type_eff(move.type, def_types)
    stab = move.type in atk_types

    # アイテムダメージ補正
    item_mod = _get_item_damage_mult(attacker_item, move.type)
    item_mod *= _get_ability_damage_modifier(
        atk_ability, def_ability_resolved, move, type_eff,
    )
    if stab and atk_ability == "adaptability":
        item_mod *= 2.0 / 1.5

    # 全 (性格, H EV, D EV) を探索
    candidates: list[DefenderCandidate] = []

    for nature in Nature:
        for h_ev in range(0, 33):
            for d_ev in range(0, 33):
                if h_ev + d_ev > 66:
                    continue

                hp = calc_stat(hp_base, 31, h_ev, level, nature, "hp")
                d_stat = calc_stat(d_base_val, 31, d_ev, level, nature, d_stat_name)

                dmg = calc_damage_range(
                    level=level,
                    power=move.power,
                    attack_stat=a_stat,
                    defense_stat=d_stat,
                    stab=stab,
                    type_eff=type_eff,
                    item_modifier=item_mod,
                )

                max_d = max(dmg)
                min_d = min(dmg)

                if survived:
                    # 耐えた: 少なくとも一部のロールで HP > damage
                    if min_d >= hp:
                        continue  # 全ロールで落ちる → この配分はありえない
                    survive_count = sum(1 for d in dmg if d < hp)
                else:
                    # 落ちた: 少なくとも一部のロールで HP <= damage
                    if max_d < hp:
                        continue  # 全ロールで耐える → この配分はありえない
                    survive_count = sum(1 for d in dmg if d < hp)

                remaining = 66 - h_ev - d_ev
                is_standard = h_ev == HP_EV_STANDARD

                candidates.append(DefenderCandidate(
                    nature=nature,
                    hp_ev=h_ev,
                    def_ev=d_ev,
                    hp=hp,
                    def_stat=d_stat,
                    damage_min=min_d,
                    damage_max=max_d,
                    survive_count=survive_count,
                    remaining_ev=remaining,
                    is_standard=is_standard,
                ))

    # ソート: 標準配分 (H32) を先に、次に確定耐え (16/16) 優先、残りEV 多い順
    candidates.sort(
        key=lambda c: (not c.is_standard, -c.survive_count, -c.remaining_ev),
    )

    return DefenderEstimate(
        defender_species=defender_species,
        attacker_species=attacker_species,
        move_name=move_name,
        attacker_stat=a_stat,
        type_eff=type_eff,
        stab=stab,
        candidates=candidates,
    )
