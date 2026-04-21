"""ダメージ計算エンジン

タイプ相性・ステータス計算・ダメージ範囲計算を提供する。
タイプ相性テーブルは data/showdown-cache/typechart.json (SSOT) から自動構築する。
"""
from __future__ import annotations

import json
import math
from pathlib import Path

from pokechamp.models import Nature, TypeName, NATURE_MODIFIERS

# ---------------------------------------------------------------------------
# タイプ相性テーブル (18×18)
# data/showdown-cache/typechart.json を SSOT として読み込む。
# フォールバック: JSON が見つからない場合は空テーブル (全て等倍) になるため、
# 必ず extract_showdown_data.js を事前に実行すること。
# _TYPE_CHART[attack_type][defend_type] = multiplier
# ---------------------------------------------------------------------------
_TYPECHART_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "showdown-cache" / "typechart.json"


def _load_type_chart() -> dict[TypeName, dict[TypeName, float]]:
    """typechart.json からタイプ相性テーブルを構築する。"""
    if not _TYPECHART_PATH.exists():
        return {}
    with open(_TYPECHART_PATH) as f:
        raw: dict[str, dict[str, float]] = json.load(f)
    chart: dict[TypeName, dict[TypeName, float]] = {}
    for atk_str, defenses in raw.items():
        try:
            atk_type = TypeName(atk_str)
        except ValueError:
            continue
        inner: dict[TypeName, float] = {}
        for def_str, mult in defenses.items():
            try:
                inner[TypeName(def_str)] = float(mult)
            except ValueError:
                continue
        chart[atk_type] = inner
    return chart


_TYPE_CHART: dict[TypeName, dict[TypeName, float]] = _load_type_chart()


def type_effectiveness(attack_type: TypeName, defend_type: TypeName) -> float:
    """攻撃タイプ → 防御タイプへの相性倍率を返す。

    テーブルに登録されていない組み合わせはデフォルト 1.0。
    """
    return _TYPE_CHART.get(attack_type, {}).get(defend_type, 1.0)


def calc_stat(
    base: int,
    iv: int,
    ev: int,
    level: int,
    nature: Nature,
    stat_name: str,
) -> int:
    """ポケモンの実数値を計算する。

    HPは専用公式、それ以外は共通公式 + 性格補正を適用。

    Args:
        base: 種族値
        iv: 個体値 (0–31)
        ev: 努力値 (0–252)
        level: レベル (1–100)
        nature: 性格
        stat_name: "hp" | "attack" | "defense" | "sp_attack" | "sp_defense" | "speed"

    Returns:
        実数値 (int)
    """
    # チャンピオンズ仕様: EV1=実数値1（本編のfloor(ev/4)ではない）
    inner = 2 * base + iv + ev

    if stat_name == "hp":
        return math.floor(inner * level / 100) + level + 10

    raw = math.floor(inner * level / 100) + 5

    # 性格補正
    up_stat, down_stat = NATURE_MODIFIERS[nature]
    if up_stat == stat_name:
        modifier = 1.1
    elif down_stat == stat_name:
        modifier = 0.9
    else:
        modifier = 1.0

    return math.floor(raw * modifier)


def calc_damage_range(
    *,
    level: int,
    power: int,
    attack_stat: int,
    defense_stat: int,
    stab: bool,
    type_eff: float,
    item_modifier: float = 1.0,
) -> list[int]:
    """ダメージ乱数16通りを計算して返す。

    公式:
        base = floor(floor(floor(2*level/5+2) * power * A / D) / 50 + 2)
        damage[roll] = floor(floor(floor(base * roll/100) * stab) * type_eff) * item_modifier)

    タイプ無効 (type_eff == 0) の場合は [0]*16 を返す。
    最小ダメージは 1 (無効以外)。

    Args:
        level: 攻撃側レベル
        power: 技の威力
        attack_stat: 攻撃側の攻撃/特攻実数値
        defense_stat: 防御側の防御/特防実数値
        stab: タイプ一致ボーナス適用の有無
        type_eff: タイプ相性倍率 (0.0 / 0.25 / 0.5 / 1.0 / 2.0 / 4.0)
        item_modifier: もちもの補正 (default 1.0)

    Returns:
        16要素のダメージリスト (乱数 85..100 に対応)
    """
    if type_eff == 0.0:
        return [0] * 16

    base = math.floor(
        math.floor(math.floor(2 * level / 5 + 2) * power * attack_stat / defense_stat) / 50 + 2
    )

    damages: list[int] = []
    for roll in range(85, 101):
        damage = math.floor(base * roll / 100)
        if stab:
            damage = math.floor(damage * 1.5)
        damage = math.floor(damage * type_eff)
        damage = math.floor(damage * item_modifier)
        damage = max(damage, 1)
        damages.append(damage)

    return damages
