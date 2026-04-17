# メガシンカAI判定 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** ヒューリスティックAIがメガシンカ可能時に適切に判断し、基本的にメガシンカを選択しつつ、不利になるケースのみ見送る

**Architecture:** `fast_battle.py`の`_choose_action()`にメガシンカ判定を追加。軽量ルックアップテーブル(`MEGA_TYPE_CHANGES`, `MEGA_VALUABLE_ABILITIES`)で対象ポケモンを管理し、対象外は即メガ。対象は被ダメ・火力の比較で判定。

**Tech Stack:** Python 3.12+, pytest

---

## File Structure

| ファイル | 役割 | 変更種別 |
|---------|------|---------|
| `src/pokechamp/fast_battle.py` | メガ判定ロジック + ログパース拡張 | Modify |
| `tests/test_fast_battle.py` | メガ判定のユニットテスト | Modify |

全てのロジックは`fast_battle.py`内に追加する（既存のAIロジックと同じファイル）。新規ファイルは作らない。

---

### Task 1: メガシンカ タイプ変化ルックアップテーブル

**Files:**
- Modify: `src/pokechamp/fast_battle.py` (定数定義セクション、L19付近)
- Test: `tests/test_fast_battle.py`

- [ ] **Step 1: テーブル定数のテストを書く**

```python
def test_mega_type_changes_table():
    """MEGA_TYPE_CHANGES has correct entries for all type-changing megas."""
    from pokechamp.fast_battle import MEGA_TYPE_CHANGES

    # 10体がエントリされている
    assert len(MEGA_TYPE_CHANGES) == 10

    # Charizard-X: Fire/Flying -> Fire/Dragon
    assert MEGA_TYPE_CHANGES["charizard"] == {
        "base_types": ["fire", "flying"],
        "mega_types": ["fire", "dragon"],
    }
    # Aggron: Steel/Rock -> Steel (単タイプ化)
    assert MEGA_TYPE_CHANGES["aggron"] == {
        "base_types": ["steel", "rock"],
        "mega_types": ["steel"],
    }
    # Altaria: Dragon/Flying -> Dragon/Fairy
    assert MEGA_TYPE_CHANGES["altaria"] == {
        "base_types": ["dragon", "flying"],
        "mega_types": ["dragon", "fairy"],
    }
```

- [ ] **Step 2: テスト失敗を確認**

Run: `pytest tests/test_fast_battle.py::test_mega_type_changes_table -v`
Expected: FAIL with `ImportError` or `AttributeError`

- [ ] **Step 3: テーブル定数を実装**

`fast_battle.py`の`SHOWDOWN_DIR`定義の後（L19付近）に追加:

```python
# ---------------------------------------------------------------------------
# Mega Evolution lookup tables
# ---------------------------------------------------------------------------

# Type-changing megas: species -> {base_types, mega_types}
# Only the 10 megas whose types change on evolution.
MEGA_TYPE_CHANGES: dict[str, dict[str, list[str]]] = {
    "charizard": {"base_types": ["fire", "flying"], "mega_types": ["fire", "dragon"]},  # X
    "pinsir": {"base_types": ["bug"], "mega_types": ["bug", "flying"]},
    "gyarados": {"base_types": ["water", "flying"], "mega_types": ["water", "dark"]},
    "ampharos": {"base_types": ["electric"], "mega_types": ["electric", "dragon"]},
    "aggron": {"base_types": ["steel", "rock"], "mega_types": ["steel"]},
    "altaria": {"base_types": ["dragon", "flying"], "mega_types": ["dragon", "fairy"]},
    "chimecho": {"base_types": ["psychic"], "mega_types": ["psychic", "steel"]},
    "audino": {"base_types": ["normal"], "mega_types": ["normal", "fairy"]},
    "feraligatr": {"base_types": ["water"], "mega_types": ["water", "dragon"]},
    "meganium": {"base_types": ["grass"], "mega_types": ["grass", "fairy"]},
}

# Pre-mega abilities that are situationally valuable.
# species -> {ability, check} where check is the condition type.
MEGA_VALUABLE_ABILITIES: dict[str, dict[str, str]] = {
    "clefable": {"ability": "unaware", "check": "opponent_has_boosts"},
    "venusaur": {"ability": "chlorophyll", "check": "weather_is_sun"},
}
```

- [ ] **Step 4: テスト通過を確認**

Run: `pytest tests/test_fast_battle.py::test_mega_type_changes_table -v`
Expected: PASS

- [ ] **Step 5: コミット**

```bash
git add src/pokechamp/fast_battle.py tests/test_fast_battle.py
git commit -m "feat: add mega evolution lookup tables for type changes and valuable abilities"
```

---

### Task 2: 相手ブーストのログパース（Clefable Unaware判定用）

**Files:**
- Modify: `src/pokechamp/fast_battle.py` (ログパースセクション、`_parse_opponent_from_log`付近)
- Test: `tests/test_fast_battle.py`

- [ ] **Step 1: ブーストパースのテストを書く**

```python
def test_parse_opponent_boosts():
    """_parse_opponent_boosts extracts stat boosts from log."""
    from pokechamp.fast_battle import _parse_opponent_boosts

    log_lines = [
        "|switch|p2a: Garchomp|Garchomp, L50, M|183/183",
        "|-boost|p2a: Garchomp|atk|2",
        "|-boost|p2a: Garchomp|spe|1",
    ]
    boosts = _parse_opponent_boosts(log_lines, "p1")
    assert boosts.get("atk", 0) == 2
    assert boosts.get("spe", 0) == 1
    assert boosts.get("def", 0) == 0


def test_parse_opponent_boosts_unboost():
    """_parse_opponent_boosts handles unboost correctly."""
    from pokechamp.fast_battle import _parse_opponent_boosts

    log_lines = [
        "|switch|p2a: Garchomp|Garchomp, L50, M|183/183",
        "|-boost|p2a: Garchomp|atk|2",
        "|-unboost|p2a: Garchomp|atk|1",
    ]
    boosts = _parse_opponent_boosts(log_lines, "p1")
    assert boosts.get("atk", 0) == 1


def test_parse_opponent_boosts_reset_on_switch():
    """Boosts reset when opponent switches."""
    from pokechamp.fast_battle import _parse_opponent_boosts

    log_lines = [
        "|switch|p2a: Garchomp|Garchomp, L50, M|183/183",
        "|-boost|p2a: Garchomp|atk|2",
        "|switch|p2a: Corviknight|Corviknight, L50, F|173/173",
        "|-boost|p2a: Corviknight|def|1",
    ]
    boosts = _parse_opponent_boosts(log_lines, "p1")
    # Garchomp's boosts should be gone; only Corviknight's remain
    assert boosts.get("atk", 0) == 0
    assert boosts.get("def", 0) == 1
```

- [ ] **Step 2: テスト失敗を確認**

Run: `pytest tests/test_fast_battle.py::test_parse_opponent_boosts -v`
Expected: FAIL with `ImportError`

- [ ] **Step 3: `_parse_opponent_boosts`を実装**

`_parse_opponent_from_log`の後（L204付近）に追加:

```python
def _parse_opponent_boosts(log_lines: list[str], my_player_id: str) -> dict[str, int]:
    """Extract current opponent's stat boosts from battle log.

    Boosts reset on switch. Returns dict like {"atk": 2, "spe": 1}.
    """
    opp_id = "p2" if my_player_id == "p1" else "p1"
    boosts: dict[str, int] = {}

    for line in log_lines:
        # Reset boosts on opponent switch
        if f"|switch|{opp_id}a: " in line or f"|drag|{opp_id}a: " in line:
            boosts.clear()
        # |-boost|p2a: Garchomp|atk|2
        m = re.match(rf"\|-boost\|{opp_id}a: [^|]+\|(\w+)\|(\d+)", line)
        if m:
            stat, stages = m.group(1), int(m.group(2))
            boosts[stat] = boosts.get(stat, 0) + stages
        # |-unboost|p2a: Garchomp|atk|1
        m = re.match(rf"\|-unboost\|{opp_id}a: [^|]+\|(\w+)\|(\d+)", line)
        if m:
            stat, stages = m.group(1), int(m.group(2))
            boosts[stat] = boosts.get(stat, 0) - stages

    return boosts
```

- [ ] **Step 4: テスト通過を確認**

Run: `pytest tests/test_fast_battle.py -k "test_parse_opponent_boosts" -v`
Expected: 3 tests PASS

- [ ] **Step 5: コミット**

```bash
git add src/pokechamp/fast_battle.py tests/test_fast_battle.py
git commit -m "feat: add opponent boost parsing from battle log"
```

---

### Task 3: 天候のログパース（Venusaur Chlorophyll判定用）

**Files:**
- Modify: `src/pokechamp/fast_battle.py`
- Test: `tests/test_fast_battle.py`

- [ ] **Step 1: 天候パースのテストを書く**

```python
def test_parse_weather_sun():
    """_parse_weather detects sun from log."""
    from pokechamp.fast_battle import _parse_weather

    log_lines = [
        "|-weather|SunnyDay|[from] ability: Drought|[of] p1a: Torkoal",
        "|turn|2",
    ]
    assert _parse_weather(log_lines) == "sunnyday"


def test_parse_weather_none():
    """_parse_weather returns empty string when no weather."""
    from pokechamp.fast_battle import _parse_weather

    log_lines = [
        "|turn|1",
        "|move|p1a: Garchomp|Earthquake|p2a: Corviknight",
    ]
    assert _parse_weather(log_lines) == ""


def test_parse_weather_ends():
    """_parse_weather detects weather ending."""
    from pokechamp.fast_battle import _parse_weather

    log_lines = [
        "|-weather|SunnyDay|[from] ability: Drought|[of] p1a: Torkoal",
        "|turn|2",
        "|-weather|none",
    ]
    assert _parse_weather(log_lines) == ""
```

- [ ] **Step 2: テスト失敗を確認**

Run: `pytest tests/test_fast_battle.py::test_parse_weather_sun -v`
Expected: FAIL with `ImportError`

- [ ] **Step 3: `_parse_weather`を実装**

`_parse_opponent_boosts`の後に追加:

```python
def _parse_weather(log_lines: list[str]) -> str:
    """Return current weather from battle log.

    Returns lowercase weather id (e.g. "sunnyday", "sandstorm") or "" if none.
    """
    weather = ""
    for line in log_lines:
        m = re.match(r"\|-weather\|(\w+)", line)
        if m:
            w = m.group(1).lower()
            weather = "" if w == "none" else w
    return weather
```

- [ ] **Step 4: テスト通過を確認**

Run: `pytest tests/test_fast_battle.py -k "test_parse_weather" -v`
Expected: 3 tests PASS

- [ ] **Step 5: コミット**

```bash
git add src/pokechamp/fast_battle.py tests/test_fast_battle.py
git commit -m "feat: add weather parsing from battle log"
```

---

### Task 4: `_should_mega_evolve`判定関数

**Files:**
- Modify: `src/pokechamp/fast_battle.py`
- Test: `tests/test_fast_battle.py`

- [ ] **Step 1: テーブルにないポケモン（即メガ）のテストを書く**

```python
def test_should_mega_evolve_default_true():
    """Pokemon not in any lookup table should always mega evolve."""
    from pokechamp.fast_battle import _should_mega_evolve

    # Lopunny: no type change, no valuable ability -> always mega
    assert _should_mega_evolve(
        species="Lopunny",
        active_types=["normal"],
        opp_types=["dragon", "ground"],
        opp_boosts={},
        weather="",
        moves=[{"id": "return", "basePower": 102, "type": "Normal", "category": "Physical"}],
    ) is True
```

- [ ] **Step 2: タイプ変化で被ダメ増のテスト（メガしない）**

```python
def test_should_mega_evolve_type_change_increases_incoming_damage():
    """Charizard-X gains Dragon type, making it weak to Dragon moves from Dragon opponent."""
    from pokechamp.fast_battle import _should_mega_evolve

    # vs Dragon opponent: Fire/Flying takes 1x from Dragon, Fire/Dragon takes 2x
    assert _should_mega_evolve(
        species="Charizard",
        active_types=["fire", "flying"],
        opp_types=["dragon"],
        opp_boosts={},
        weather="",
        moves=[{"id": "flareblitz", "basePower": 120, "type": "Fire", "category": "Physical"}],
    ) is False
```

- [ ] **Step 3: タイプ変化で被ダメ減のテスト（メガする）**

```python
def test_should_mega_evolve_type_change_reduces_incoming_damage():
    """Aggron loses Rock type (Steel/Rock -> Steel), reducing weaknesses."""
    from pokechamp.fast_battle import _should_mega_evolve

    # vs Water opponent: Steel/Rock takes 2x from Water, pure Steel takes 1x
    assert _should_mega_evolve(
        species="Aggron",
        active_types=["steel", "rock"],
        opp_types=["water"],
        opp_boosts={},
        weather="",
        moves=[{"id": "ironhead", "basePower": 80, "type": "Steel", "category": "Physical"}],
    ) is True
```

- [ ] **Step 4: タイプ変化で火力減のテスト（メガしない）**

```python
def test_should_mega_evolve_type_change_reduces_stab():
    """Gyarados loses Flying STAB (Water/Flying -> Water/Dark)."""
    from pokechamp.fast_battle import _should_mega_evolve

    # Using Bounce (Flying) vs Grass opponent: loses STAB + worse effectiveness
    # Flying is 2x vs Grass with STAB; after mega Dark type doesn't help vs Grass
    assert _should_mega_evolve(
        species="Gyarados",
        active_types=["water", "flying"],
        opp_types=["grass"],
        opp_boosts={},
        weather="",
        moves=[
            {"id": "bounce", "basePower": 85, "type": "Flying", "category": "Physical"},
            {"id": "waterfall", "basePower": 80, "type": "Water", "category": "Physical"},
        ],
    ) is False
```

- [ ] **Step 5: テスト失敗を確認**

Run: `pytest tests/test_fast_battle.py -k "test_should_mega_evolve" -v`
Expected: 4 tests FAIL

- [ ] **Step 6: `_should_mega_evolve`を実装**

`_parse_weather`の後に追加:

```python
def _extract_species_key(species: str) -> str:
    """Normalize species name to lookup key (e.g. 'Charizard' -> 'charizard')."""
    return species.split("-")[0].strip().lower()


def _should_mega_evolve(
    species: str,
    active_types: list[str],
    opp_types: list[str],
    opp_boosts: dict[str, int],
    weather: str,
    moves: list[dict],
) -> bool:
    """Decide whether to mega evolve this turn.

    Default: True (always mega).
    Exceptions:
      - Category A: Type change increases opponent's max damage against us,
        OR type change reduces our best move's effective score.
      - Category B: Pre-mega ability is situationally valuable
        (Clefable/Unaware when opponent has boosts, Venusaur/Chlorophyll in sun).
    """
    key = _extract_species_key(species)

    # --- Category B: valuable pre-mega ability ---
    if key in MEGA_VALUABLE_ABILITIES:
        entry = MEGA_VALUABLE_ABILITIES[key]
        check = entry["check"]
        if check == "opponent_has_boosts":
            # Don't mega if opponent has any positive offensive boosts
            if any(v > 0 for v in opp_boosts.values()):
                return False
        elif check == "weather_is_sun":
            if weather == "sunnyday":
                return False

    # --- Category A: type change evaluation ---
    if key not in MEGA_TYPE_CHANGES:
        return True

    info = MEGA_TYPE_CHANGES[key]
    base_types = info["base_types"]
    mega_types = info["mega_types"]

    # 1. Defensive check: does mega increase max incoming damage?
    base_incoming = max(
        (_calc_type_effectiveness(t, base_types) for t in opp_types),
        default=1.0,
    )
    mega_incoming = max(
        (_calc_type_effectiveness(t, mega_types) for t in opp_types),
        default=1.0,
    )
    if mega_incoming > base_incoming:
        return False

    # 2. Offensive check: does mega reduce our best move score?
    #    Compare best move STAB effectiveness before/after mega.
    base_best = 0.0
    mega_best = 0.0
    for move in moves:
        bp = move.get("basePower", 0) or 0
        if bp == 0:
            continue
        move_type = (move.get("type") or "").lower()
        eff = _calc_type_effectiveness(move_type, opp_types)
        base_stab = 1.5 if move_type in [t.lower() for t in base_types] else 1.0
        mega_stab = 1.5 if move_type in [t.lower() for t in mega_types] else 1.0
        base_best = max(base_best, bp * base_stab * eff)
        mega_best = max(mega_best, bp * mega_stab * eff)

    if mega_best < base_best:
        return False

    return True
```

- [ ] **Step 7: テスト通過を確認**

Run: `pytest tests/test_fast_battle.py -k "test_should_mega_evolve" -v`
Expected: 4 tests PASS

- [ ] **Step 8: コミット**

```bash
git add src/pokechamp/fast_battle.py tests/test_fast_battle.py
git commit -m "feat: add _should_mega_evolve decision function with type and ability checks"
```

---

### Task 5: Category B テスト追加（Clefable・Venusaur）

**Files:**
- Test: `tests/test_fast_battle.py`

- [ ] **Step 1: Clefable Unaware テストを書く**

```python
def test_should_mega_evolve_clefable_unaware_with_boosts():
    """Clefable should NOT mega when opponent has stat boosts (Unaware is valuable)."""
    from pokechamp.fast_battle import _should_mega_evolve

    assert _should_mega_evolve(
        species="Clefable",
        active_types=["fairy"],
        opp_types=["normal"],
        opp_boosts={"atk": 2},
        weather="",
        moves=[{"id": "moonblast", "basePower": 95, "type": "Fairy", "category": "Special"}],
    ) is False


def test_should_mega_evolve_clefable_unaware_no_boosts():
    """Clefable SHOULD mega when opponent has no boosts (Unaware not needed)."""
    from pokechamp.fast_battle import _should_mega_evolve

    assert _should_mega_evolve(
        species="Clefable",
        active_types=["fairy"],
        opp_types=["normal"],
        opp_boosts={},
        weather="",
        moves=[{"id": "moonblast", "basePower": 95, "type": "Fairy", "category": "Special"}],
    ) is True
```

- [ ] **Step 2: Venusaur Chlorophyll テストを書く**

```python
def test_should_mega_evolve_venusaur_in_sun():
    """Venusaur should NOT mega in sun (Chlorophyll doubles speed)."""
    from pokechamp.fast_battle import _should_mega_evolve

    assert _should_mega_evolve(
        species="Venusaur",
        active_types=["grass", "poison"],
        opp_types=["water"],
        opp_boosts={},
        weather="sunnyday",
        moves=[{"id": "sludgebomb", "basePower": 90, "type": "Poison", "category": "Special"}],
    ) is False


def test_should_mega_evolve_venusaur_no_sun():
    """Venusaur SHOULD mega when no sun (Chlorophyll not active)."""
    from pokechamp.fast_battle import _should_mega_evolve

    assert _should_mega_evolve(
        species="Venusaur",
        active_types=["grass", "poison"],
        opp_types=["water"],
        opp_boosts={},
        weather="",
        moves=[{"id": "sludgebomb", "basePower": 90, "type": "Poison", "category": "Special"}],
    ) is True
```

- [ ] **Step 3: テスト通過を確認**

Run: `pytest tests/test_fast_battle.py -k "test_should_mega_evolve" -v`
Expected: 8 tests PASS (Task 4の4 + Task 5の4)

- [ ] **Step 4: コミット**

```bash
git add tests/test_fast_battle.py
git commit -m "test: add Clefable Unaware and Venusaur Chlorophyll mega decision tests"
```

---

### Task 6: `_choose_action`にメガシンカ統合

**Files:**
- Modify: `src/pokechamp/fast_battle.py:584-707` (`_choose_action`関数)
- Test: `tests/test_fast_battle.py`

- [ ] **Step 1: メガ付きmoveコマンドのテストを書く**

```python
def test_choose_action_mega_evolves_by_default():
    """When canMegaEvo is true and no reason to skip, appends ' mega' to move."""
    from pokechamp.fast_battle import _choose_action

    request = {
        "active": [
            {
                "canMegaEvo": True,
                "moves": [
                    {"move": "Return", "id": "return", "pp": 32, "maxpp": 32,
                     "basePower": 102, "type": "Normal", "category": "Physical",
                     "accuracy": 100, "target": "normal", "disabled": False},
                ],
            }
        ],
        "side": {
            "pokemon": [
                {
                    "ident": "p1: Lopunny",
                    "active": True,
                    "condition": "151/151",
                    "types": ["normal"],
                    "stats": {"atk": 150, "def": 94, "spa": 54, "spd": 96, "spe": 170},
                    "boosts": {},
                }
            ]
        },
    }
    action = _choose_action(request, [], "p1")
    assert action.endswith(" mega"), f"Expected 'move N mega', got '{action}'"


def test_choose_action_no_mega_when_not_available():
    """When canMegaEvo is absent/false, no mega suffix."""
    from pokechamp.fast_battle import _choose_action

    request = {
        "active": [
            {
                "moves": [
                    {"move": "Return", "id": "return", "pp": 32, "maxpp": 32,
                     "basePower": 102, "type": "Normal", "category": "Physical",
                     "accuracy": 100, "target": "normal", "disabled": False},
                ],
            }
        ],
        "side": {
            "pokemon": [
                {
                    "ident": "p1: Lopunny",
                    "active": True,
                    "condition": "151/151",
                    "types": ["normal"],
                    "stats": {"atk": 150, "def": 94, "spa": 54, "spd": 96, "spe": 170},
                    "boosts": {},
                }
            ]
        },
    }
    action = _choose_action(request, [], "p1")
    assert "mega" not in action
```

- [ ] **Step 2: テスト失敗を確認**

Run: `pytest tests/test_fast_battle.py::test_choose_action_mega_evolves_by_default -v`
Expected: FAIL (no " mega" suffix yet)

- [ ] **Step 3: `_choose_action`にメガ判定を統合**

`_choose_action`関数の`active_pokemon`取得後（L611付近）に種族名抽出とメガ判定を追加し、moveコマンド返却箇所全てに` mega`を付与する。

L611の後に追加:
```python
    # Mega evolution decision
    can_mega = active_req.get("canMegaEvo", False)
    mega_suffix = ""
    if can_mega:
        species_name = active_pokemon.get("ident", "").split(": ", 1)[-1] if active_pokemon else ""
        opp_boosts = _parse_opponent_boosts(log_lines, player_id)
        weather = _parse_weather(log_lines)
        if _should_mega_evolve(
            species=species_name,
            active_types=active_pokemon.get("types", []),
            opp_types=opp.get("types", []),
            opp_boosts=opp_boosts,
            weather=weather,
            moves=moves,
        ):
            mega_suffix = " mega"
```

次に、`_choose_action`内でmoveコマンドを返す全箇所に`mega_suffix`を付与する。対象箇所:

- L637: `return f"move {moves.index(priority_ko_move) + 1}"` → `return f"move {moves.index(priority_ko_move) + 1}{mega_suffix}"`
- L647: 同上
- L655: `return f"move {moves.index(move) + 1}"` → `return f"move {moves.index(move) + 1}{mega_suffix}"`
- L662: 同上
- L683: 同上
- L694: `return f"move {moves.index(best_move) + 1}"` → `return f"move {moves.index(best_move) + 1}{mega_suffix}"`
- L696: `return f"move {moves.index(available_moves[0]) + 1}"` → `return f"move {moves.index(available_moves[0]) + 1}{mega_suffix}"`
- L700: フォールバック行も同様

**注意**: `mega_suffix`は`can_mega`が`True`かつ`_should_mega_evolve`が`True`の場合のみ`" mega"`になる。switchコマンドには付けない。

- [ ] **Step 4: テスト通過を確認**

Run: `pytest tests/test_fast_battle.py -k "test_choose_action_mega" -v`
Expected: 2 tests PASS

- [ ] **Step 5: 既存テストが壊れていないことを確認**

Run: `pytest tests/test_fast_battle.py -v`
Expected: 全テストPASS（既存テストは`canMegaEvo`を持たないのでmega_suffixは空文字列）

- [ ] **Step 6: コミット**

```bash
git add src/pokechamp/fast_battle.py tests/test_fast_battle.py
git commit -m "feat: integrate mega evolution decision into _choose_action"
```

---

### Task 7: 全体テスト + ruff

**Files:**
- N/A (既存コード検証のみ)

- [ ] **Step 1: ruff check**

Run: `ruff check src/`
Expected: No errors

- [ ] **Step 2: 全テスト**

Run: `pytest`
Expected: 全テストPASS

- [ ] **Step 3: 問題があれば修正してコミット**

---

### Task 8: ドキュメント更新

**Files:**
- Modify: `docs/design/heuristic-ai-spec.md`
- Modify: `docs/INDEX.md`

- [ ] **Step 1: heuristic-ai-spec.mdにメガシンカ判定セクションを追加**

メガシンカ判定ロジックの概要を記述:

```markdown
## メガシンカ判定

基本方針: **メガシンカ可能なら行う**。以下の例外のみ見送る。

### 例外A: タイプ変化による不利（10体）

メガシンカでタイプが変わるポケモンについて、以下のいずれかが成立する場合はメガしない:
- 相手タイプからの被ダメ倍率がメガ後に増加する
- 自分の最高火力技のSTAB＋相性スコアがメガ後に低下する

対象: Charizard-X, Pinsir, Gyarados, Ampharos, Aggron, Altaria, Chimecho, Audino, Feraligatr, Meganium

### 例外B: メガ前特性が状況的に有効（2体）

| ポケモン | 特性 | メガしない条件 |
|---------|------|--------------|
| Clefable | Unaware (天然) | 相手に正のステータスブーストがある |
| Venusaur | Chlorophyll (葉緑素) | 天候が晴れ |
```

- [ ] **Step 2: docs/INDEX.mdを更新（必要に応じて）**

heuristic-ai-spec.mdは既にINDEXに記載済みのため、内容更新のみで追加不要。

- [ ] **Step 3: コミット**

```bash
git add docs/design/heuristic-ai-spec.md
git commit -m "docs: add mega evolution decision logic to heuristic AI spec"
```
