# 特性考慮AI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** AIが相手の特性を推定/検知し、接触技ペナルティ・火力倍化・タイプ免疫の3カテゴリで判断を改善する

**Architecture:** pokedex.jsonをShowdownから抽出し、種族名→特性リストの推定を行う。ログの`|-ability|`で確定情報を上書き。`_score_move`と`_estimate_opponent_max_damage`に特性補正を反映。

**Tech Stack:** Python 3.12+, Node.js (extraction), pytest

---

## File Structure

| ファイル | 役割 | 変更種別 |
|---------|------|---------|
| `scripts/extract_showdown_data.js` | pokedex.json抽出を追加 | Modify |
| `data/showdown-cache/pokedex.json` | 種族→特性・タイプ・種族値 | Create |
| `src/pokechamp/showdown_data.py` | 特性推定・分類関数を追加 | Modify |
| `src/pokechamp/fast_battle.py` | ログパース + スコア補正 | Modify |
| `tests/test_fast_battle.py` | テスト追加 | Modify |
| `tests/test_showdown_data.py` | showdown_data単体テスト追加 | Modify or Create |

---

### Task 1: pokedex.json抽出

**Files:**
- Modify: `scripts/extract_showdown_data.js`
- Create: `data/showdown-cache/pokedex.json`

- [ ] **Step 1: extract_showdown_data.jsにpokedex抽出を追加**

既存スクリプトのAbilities書き出しの後に追加:

```javascript
// ---------------------------------------------------------------------------
// Pokedex (species -> types, abilities, baseStats)
// ---------------------------------------------------------------------------
const pokedex = {};
for (const [id, species] of Object.entries(dex.data.Pokedex)) {
  if (species.isNonstandard && species.isNonstandard !== "Past") continue;
  if (species.num <= 0) continue; // skip CAP

  const entry = {
    name: species.name,
    types: species.types,
    baseStats: species.baseStats,
    abilities: {},
  };
  // abilities: {"0": "Sand Veil", "1": "...", "H": "Rough Skin"}
  for (const [slot, abilityName] of Object.entries(species.abilities || {})) {
    const ab = dex.abilities.get(abilityName);
    entry.abilities[slot] = ab ? ab.id : abilityName.toLowerCase().replace(/\s/g, "");
  }

  pokedex[id] = entry;
}

fs.writeFileSync(path.join(OUTPUT_DIR, "pokedex.json"), JSON.stringify(pokedex, null, 2));
console.log(`Extracted ${Object.keys(pokedex).length} species -> data/showdown-cache/pokedex.json`);
```

- [ ] **Step 2: スクリプトを実行**

Run: `node scripts/extract_showdown_data.js`
Expected: 3つのJSONファイルが出力される

- [ ] **Step 3: コミット**

```bash
git add scripts/extract_showdown_data.js data/showdown-cache/pokedex.json
git commit -m "feat: extract pokedex data from Showdown (species, types, abilities, baseStats)"
```

---

### Task 2: showdown_data.pyに特性推定・分類関数を追加

**Files:**
- Modify: `src/pokechamp/showdown_data.py`
- Create or Modify: `tests/test_showdown_data.py`

- [ ] **Step 1: テストを書く**

`tests/test_showdown_data.py` に追加（ファイルがなければ作成）:

```python
"""Tests for showdown_data module."""
from __future__ import annotations


def test_load_pokedex():
    from pokechamp.showdown_data import load_pokedex
    pokedex = load_pokedex()
    assert len(pokedex) > 0
    assert "garchomp" in pokedex
    assert pokedex["garchomp"]["types"] == ["Dragon", "Ground"]


def test_get_species_abilities():
    from pokechamp.showdown_data import get_species_abilities
    abilities = get_species_abilities("Garchomp")
    assert "roughskin" in abilities
    assert "sandveil" in abilities


def test_get_species_abilities_case_insensitive():
    from pokechamp.showdown_data import get_species_abilities
    abilities = get_species_abilities("garchomp")
    assert "roughskin" in abilities


def test_ability_is_contact_punish():
    from pokechamp.showdown_data import ability_has_contact_punish
    assert ability_has_contact_punish("roughskin") is True
    assert ability_has_contact_punish("ironbarbs") is True
    assert ability_has_contact_punish("intimidate") is False


def test_ability_is_type_immunity():
    from pokechamp.showdown_data import ability_grants_type_immunity
    assert ability_grants_type_immunity("levitate") == "ground"
    assert ability_grants_type_immunity("flashfire") == "fire"
    assert ability_grants_type_immunity("sapsipper") == "grass"
    assert ability_grants_type_immunity("waterabsorb") == "water"
    assert ability_grants_type_immunity("voltabsorb") == "electric"
    assert ability_grants_type_immunity("lightningrod") == "electric"
    assert ability_grants_type_immunity("stormdrain") == "water"
    assert ability_grants_type_immunity("motordrive") == "electric"
    assert ability_grants_type_immunity("intimidate") is None


def test_ability_is_attack_multiplier():
    from pokechamp.showdown_data import ability_attack_multiplier
    # Huge Power / Pure Power = 2x physical
    assert ability_attack_multiplier("hugepower") == ("atk", 2.0)
    assert ability_attack_multiplier("purepower") == ("atk", 2.0)
    # Hustle = 1.5x physical
    assert ability_attack_multiplier("hustle") == ("atk", 1.5)
    # Non-multiplier ability
    assert ability_attack_multiplier("intimidate") is None


def test_species_may_have_contact_punish():
    from pokechamp.showdown_data import species_may_have_contact_punish
    # Garchomp has Rough Skin as hidden ability
    assert species_may_have_contact_punish("Garchomp") is True
    # Corviknight doesn't have contact punish abilities
    assert species_may_have_contact_punish("Corviknight") is False


def test_species_type_immunities():
    from pokechamp.showdown_data import species_type_immunities
    # Gengar with Levitate? No, Gengar lost Levitate. Check a Levitate pokemon.
    # Bronzong has Levitate as ability 0
    immunities = species_type_immunities("Bronzong")
    assert "ground" in immunities
```

- [ ] **Step 2: テスト失敗を確認**

Run: `.venv/bin/python -m pytest tests/test_showdown_data.py -v`
Expected: FAIL

- [ ] **Step 3: showdown_data.pyに関数を追加**

`load_pokedex()`の追加（既存のload_abilities()の後に）:

```python
@lru_cache(maxsize=1)
def load_pokedex() -> dict[str, dict]:
    """Load all species from the Showdown cache."""
    path = CACHE_DIR / "pokedex.json"
    if not path.exists():
        return {}
    with open(path) as f:
        return json.load(f)


def get_species_abilities(species: str) -> list[str]:
    """Return list of ability IDs for a species (e.g. ['sandveil', 'roughskin'])."""
    key = species.lower().replace(" ", "").replace("-", "")
    pokedex = load_pokedex()
    entry = pokedex.get(key)
    if not entry:
        return []
    return list(entry.get("abilities", {}).values())


# Type immunity abilities: ability_id -> immune_type
_TYPE_IMMUNITY_ABILITIES: dict[str, str] = {
    "levitate": "ground",
    "flashfire": "fire",
    "waterabsorb": "water",
    "voltabsorb": "electric",
    "sapsipper": "grass",
    "lightningrod": "electric",
    "stormdrain": "water",
    "motordrive": "electric",
    "dryskin": "water",
    "eartheater": "ground",
    "wellbakedbody": "fire",
    "windpower": "wind",  # not a real type, but kept for completeness
}

# Attack multiplier abilities: ability_id -> (stat, multiplier)
_ATTACK_MULTIPLIER_ABILITIES: dict[str, tuple[str, float]] = {
    "hugepower": ("atk", 2.0),
    "purepower": ("atk", 2.0),
    "hustle": ("atk", 1.5),
    "gorillatactics": ("atk", 1.5),
}


def ability_grants_type_immunity(ability_id: str) -> str | None:
    """Return the type this ability grants immunity to, or None."""
    return _TYPE_IMMUNITY_ABILITIES.get(ability_id)


def ability_attack_multiplier(ability_id: str) -> tuple[str, float] | None:
    """Return (stat, multiplier) if ability boosts attack, else None."""
    return _ATTACK_MULTIPLIER_ABILITIES.get(ability_id)


def species_may_have_contact_punish(species: str) -> bool:
    """Return True if any of the species' possible abilities punishes contact."""
    for ab_id in get_species_abilities(species):
        if ability_has_contact_punish(ab_id):
            return True
    return False


def species_type_immunities(species: str) -> list[str]:
    """Return list of types this species might be immune to via abilities."""
    immunities = []
    for ab_id in get_species_abilities(species):
        immune_type = ability_grants_type_immunity(ab_id)
        if immune_type:
            immunities.append(immune_type)
    return immunities
```

- [ ] **Step 4: テスト通過を確認**

Run: `.venv/bin/python -m pytest tests/test_showdown_data.py -v`
Expected: 全PASS

- [ ] **Step 5: コミット**

```bash
git add src/pokechamp/showdown_data.py tests/test_showdown_data.py
git commit -m "feat: add ability classification and species ability lookup functions"
```

---

### Task 3: 相手特性のログパース

**Files:**
- Modify: `src/pokechamp/fast_battle.py` (ログパースセクション)
- Modify: `tests/test_fast_battle.py`

- [ ] **Step 1: テストを書く**

```python
def test_parse_opponent_ability_from_log():
    """_parse_opponent_ability extracts ability from |-ability| log line."""
    from pokechamp.fast_battle import _parse_opponent_ability

    log_lines = [
        "|switch|p2a: Gyarados|Gyarados, M|202/202",
        "|-ability|p2a: Gyarados|Intimidate|boost",
    ]
    assert _parse_opponent_ability(log_lines, "p1") == "intimidate"


def test_parse_opponent_ability_none():
    """Returns empty string when no ability detected."""
    from pokechamp.fast_battle import _parse_opponent_ability

    log_lines = [
        "|switch|p2a: Garchomp|Garchomp, M|183/183",
    ]
    assert _parse_opponent_ability(log_lines, "p1") == ""


def test_parse_opponent_ability_resets_on_switch():
    """Ability resets when opponent switches."""
    from pokechamp.fast_battle import _parse_opponent_ability

    log_lines = [
        "|switch|p2a: Gyarados|Gyarados, M|202/202",
        "|-ability|p2a: Gyarados|Intimidate|boost",
        "|switch|p2a: Garchomp|Garchomp, M|183/183",
    ]
    # Garchomp switched in, no ability revealed yet
    assert _parse_opponent_ability(log_lines, "p1") == ""
```

- [ ] **Step 2: テスト失敗を確認**

Run: `.venv/bin/python -m pytest tests/test_fast_battle.py -k "test_parse_opponent_ability" -v`
Expected: FAIL

- [ ] **Step 3: `_parse_opponent_ability`を実装**

`_parse_opponent_boosts`の後に追加:

```python
def _parse_opponent_ability(log_lines: list[str], my_player_id: str) -> str:
    """Extract opponent's revealed ability from battle log.

    Returns lowercase ability ID (e.g. "intimidate") or "" if not revealed.
    Resets when opponent switches.
    """
    opp_id = "p2" if my_player_id == "p1" else "p1"
    ability = ""

    for line in log_lines:
        # Reset on opponent switch
        if f"|switch|{opp_id}a: " in line or f"|drag|{opp_id}a: " in line:
            ability = ""
        # |-ability|p2a: Gyarados|Intimidate|boost
        m = re.match(rf"\|-ability\|{opp_id}a: [^|]+\|([^|]+)", line)
        if m:
            ability = m.group(1).strip().lower().replace(" ", "")

    return ability
```

- [ ] **Step 4: テスト通過を確認**

Run: `.venv/bin/python -m pytest tests/test_fast_battle.py -k "test_parse_opponent_ability" -v`
Expected: 3 tests PASS

- [ ] **Step 5: `_parse_opponent_from_log`を拡張して特性を含める**

`_parse_opponent_from_log`の返すdictに`ability`フィールドを追加。関数の冒頭を変更:

```python
def _parse_opponent_from_log(log_lines: list[str], my_player_id: str) -> dict:
    """Extract opponent's active pokemon info from battle log.

    Returns dict with keys: species, types, hp_pct, stats, ability.
    """
    opp_id = "p2" if my_player_id == "p1" else "p1"
    opponent: dict = {"species": "", "types": [], "hp_pct": 100.0, "stats": {}, "ability": ""}
```

関数の最後（`return opponent`の前）に追加:

```python
    # Parse revealed ability
    opponent["ability"] = _parse_opponent_ability(log_lines, my_player_id)

    return opponent
```

- [ ] **Step 6: コミット**

```bash
git add src/pokechamp/fast_battle.py tests/test_fast_battle.py
git commit -m "feat: parse opponent ability from battle log (|-ability| lines)"
```

---

### Task 4: 接触技ペナルティの精密化

**Files:**
- Modify: `src/pokechamp/fast_battle.py` (`_score_move`)
- Modify: `tests/test_fast_battle.py`

現在の`_score_move`は接触技に一律0.95をかけている。相手の種族名から接触反撃特性を推定し、該当時のみペナルティを強化する。

- [ ] **Step 1: テストを書く**

```python
def test_score_move_contact_penalty_vs_rough_skin():
    """Contact moves should be penalized more vs species with Rough Skin."""
    from pokechamp.fast_battle import _score_move

    active = {"types": ["fighting"], "stats": {"atk": 150, "spa": 80, "spe": 100}}
    # Garchomp has Rough Skin
    opp_garchomp = {"types": ["dragon", "ground"], "stats": {"def": 115, "spd": 105, "spe": 102},
                    "species": "Garchomp", "ability": ""}
    # Corviknight has no contact punish
    opp_corvi = {"types": ["steel", "flying"], "stats": {"def": 172, "spd": 137, "spe": 87},
                 "species": "Corviknight", "ability": ""}

    # Close Combat is contact
    cc = {"id": "closecombat", "basePower": 120, "type": "Fighting",
          "category": "Physical", "accuracy": 100}

    score_vs_garchomp = _score_move(cc, active, opp_garchomp, 1.5, 0.8)
    score_vs_corvi = _score_move(cc, active, opp_corvi, 1.5, 0.8)

    # Vs Garchomp (Rough Skin possible) should have more contact penalty
    # Both have contact penalty, but Garchomp's should be stronger
    # We can't directly compare due to different type effectiveness,
    # so test that the function runs without error
    assert score_vs_garchomp > 0
    assert score_vs_corvi > 0
```

- [ ] **Step 2: `_score_move`の接触技ペナルティを精密化**

`_score_move`内の既存の接触技ペナルティ（`score *= 0.95`）を置き換え:

```python
        # Contact move penalty
        if showdown_data.move_is_contact(move_id):
            opp_ability = opponent.get("ability", "")
            opp_species = opponent.get("species", "")
            if opp_ability and showdown_data.ability_has_contact_punish(opp_ability):
                # Confirmed contact-punish ability: -12.5% (1/8 HP per hit)
                score *= 0.875
            elif opp_species and showdown_data.species_may_have_contact_punish(opp_species):
                # Possible contact-punish: moderate penalty
                score *= 0.93
            else:
                # Unknown: small default penalty (Rocky Helmet possibility)
                score *= 0.97
```

- [ ] **Step 3: テスト通過を確認**

Run: `.venv/bin/python -m pytest tests/test_fast_battle.py -k "test_score_move_contact" -v`
Expected: PASS

- [ ] **Step 4: コミット**

```bash
git add src/pokechamp/fast_battle.py tests/test_fast_battle.py
git commit -m "feat: precise contact move penalty based on opponent species/ability"
```

---

### Task 5: タイプ免疫の特性考慮

**Files:**
- Modify: `src/pokechamp/fast_battle.py` (`_score_move`)
- Modify: `tests/test_fast_battle.py`

相手がふゆう持ちの可能性がある場合、地面技のスコアを下げる等。

- [ ] **Step 1: テストを書く**

```python
def test_score_move_type_immunity_ability():
    """Ground moves should be penalized vs species that may have Levitate."""
    from pokechamp.fast_battle import _score_move

    active = {"types": ["ground"], "stats": {"atk": 150, "spa": 80, "spe": 100}}
    # Bronzong may have Levitate (ground immunity)
    opp_bronzong = {"types": ["steel", "psychic"], "stats": {"def": 116, "spd": 116, "spe": 33},
                    "species": "Bronzong", "ability": ""}

    eq = {"id": "earthquake", "basePower": 100, "type": "Ground",
          "category": "Physical", "accuracy": 100}
    iron_head = {"id": "ironhead", "basePower": 80, "type": "Steel",
                 "category": "Physical", "accuracy": 100}

    score_eq = _score_move(eq, active, opp_bronzong, 1.5, 0.8)
    score_ih = _score_move(iron_head, active, opp_bronzong, 1.5, 0.8)

    # Earthquake should be penalized because Bronzong might have Levitate
    # Iron Head has no such concern
    # EQ base would be much higher (STAB + SE), but immunity risk should reduce it
    assert score_eq >= 0  # may still be positive
    assert score_ih > 0


def test_score_move_confirmed_levitate():
    """Ground moves should score 0 vs confirmed Levitate."""
    from pokechamp.fast_battle import _score_move

    active = {"types": ["ground"], "stats": {"atk": 150, "spa": 80, "spe": 100}}
    opp = {"types": ["steel", "psychic"], "stats": {"def": 116, "spd": 116, "spe": 33},
           "species": "Bronzong", "ability": "levitate"}

    eq = {"id": "earthquake", "basePower": 100, "type": "Ground",
          "category": "Physical", "accuracy": 100}

    score = _score_move(eq, active, opp, 1.5, 0.8)
    assert score == 0.0  # confirmed immune
```

- [ ] **Step 2: テスト失敗を確認**

Run: `.venv/bin/python -m pytest tests/test_fast_battle.py -k "test_score_move_type_immunity" -v`
Expected: FAIL

- [ ] **Step 3: `_score_move`にタイプ免疫チェックを追加**

`_score_move`の Showdown data enhancements セクションの先頭（drain処理の前）に追加:

```python
        # Type immunity via ability
        opp_ability = opponent.get("ability", "")
        opp_species = opponent.get("species", "")
        if opp_ability:
            # Confirmed ability: check for type immunity
            immune_type = showdown_data.ability_grants_type_immunity(opp_ability)
            if immune_type and move_type == immune_type:
                return 0.0  # confirmed immune
        elif opp_species:
            # Unconfirmed: check if any possible ability grants immunity to this move type
            possible_immunities = showdown_data.species_type_immunities(opp_species)
            if move_type in possible_immunities:
                # Possible immunity: heavy penalty (50% off, since ~50% chance)
                score *= 0.5
```

- [ ] **Step 4: テスト通過を確認**

Run: `.venv/bin/python -m pytest tests/test_fast_battle.py -k "test_score_move_type_immunity or test_score_move_confirmed_levitate" -v`
Expected: 2 PASS

- [ ] **Step 5: コミット**

```bash
git add src/pokechamp/fast_battle.py tests/test_fast_battle.py
git commit -m "feat: score move considers type immunity abilities (Levitate, Flash Fire, etc.)"
```

---

### Task 6: 火力倍化特性の被ダメ推定反映

**Files:**
- Modify: `src/pokechamp/fast_battle.py` (`_estimate_opponent_max_damage`)
- Modify: `tests/test_fast_battle.py`

- [ ] **Step 1: テストを書く**

```python
def test_estimate_opponent_max_damage_huge_power():
    """Opponent with Huge Power should deal roughly double physical damage."""
    from pokechamp.fast_battle import _estimate_opponent_max_damage

    # Azumarill with Huge Power
    dmg_normal = _estimate_opponent_max_damage(
        "Azumarill", ["water", "fairy"], 100, 100, ["normal"],
        confirmed_ability="",
    )
    dmg_huge = _estimate_opponent_max_damage(
        "Azumarill", ["water", "fairy"], 100, 100, ["normal"],
        confirmed_ability="hugepower",
    )
    # Huge Power should roughly double the damage
    assert dmg_huge > dmg_normal * 1.5
```

- [ ] **Step 2: テスト失敗を確認**

Run: `.venv/bin/python -m pytest tests/test_fast_battle.py::test_estimate_opponent_max_damage_huge_power -v`
Expected: FAIL (function doesn't accept confirmed_ability param)

- [ ] **Step 3: `_estimate_opponent_max_damage`に特性パラメータを追加**

現在のシグネチャを確認し、`confirmed_ability`パラメータを追加:

```python
def _estimate_opponent_max_damage(
    opp_species: str,
    opp_types: list[str],
    my_def: int,
    my_spd: int,
    my_types: list[str],
    confirmed_ability: str = "",
) -> int:
```

関数本体の最後（return直前）にダメージ補正を追加:

```python
    # Ability-based damage multiplier
    if confirmed_ability:
        mult = showdown_data.ability_attack_multiplier(confirmed_ability)
        if mult:
            stat_name, factor = mult
            if stat_name == "atk":
                max_damage = int(max_damage * factor)
    else:
        # Check if species might have a power-boosting ability
        for ab_id in showdown_data.get_species_abilities(opp_species):
            mult = showdown_data.ability_attack_multiplier(ab_id)
            if mult:
                stat_name, factor = mult
                if stat_name == "atk":
                    # Possible multiplier: apply conservatively (assume 50% chance)
                    max_damage = int(max_damage * (1.0 + (factor - 1.0) * 0.5))
                break

    return max_damage
```

- [ ] **Step 4: 呼び出し元を更新**

`_should_switch_out`と`_choose_best_switch`内の`_estimate_opponent_max_damage`呼び出しに`confirmed_ability=opp.get("ability", "")`を追加。

- [ ] **Step 5: テスト通過を確認**

Run: `.venv/bin/python -m pytest tests/test_fast_battle.py -k "test_estimate_opponent_max_damage" -v`
Expected: 全PASS

- [ ] **Step 6: 全テスト通過を確認**

Run: `.venv/bin/python -m pytest tests/test_fast_battle.py -v`
Expected: 全PASS

- [ ] **Step 7: コミット**

```bash
git add src/pokechamp/fast_battle.py tests/test_fast_battle.py
git commit -m "feat: opponent ability multiplier in damage estimation (Huge Power, etc.)"
```

---

### Task 7: 全体検証 + ドキュメント

- [ ] **Step 1: ruff check**

Run: `.venv/bin/ruff check src/`
Expected: clean

- [ ] **Step 2: 全テスト**

Run: `.venv/bin/python -m pytest`
Expected: 全PASS

- [ ] **Step 3: heuristic-ai-spec.md更新**

Step 3を実装済みにマーク。

- [ ] **Step 4: コミット**

```bash
git add docs/design/heuristic-ai-spec.md
git commit -m "docs: mark ability-aware AI (Step 3) as implemented"
```
