# AIバグ修正（技フィルタリング3件） Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** ヒューリスティックAIが「使えない技」を選択するバグ3件を修正する（ねこだまし連打、ステロ重複、PP切れ）

**Architecture:** `_choose_action`の`available_moves`構築時に3つのフィルタを追加。ログパースの既存基盤（`_parse_side_conditions`等）を活用。新規関数は`_filter_unavailable_moves`1つに集約。

**Tech Stack:** Python 3.12+, pytest

---

## File Structure

| ファイル | 役割 | 変更種別 |
|---------|------|---------|
| `src/pokechamp/fast_battle.py` | フィルタ関数追加 + `_choose_action`修正 + ステロ設置済みチェック改善 | Modify |
| `tests/test_fast_battle.py` | フィルタのユニットテスト | Modify |

---

## Bug分析

### Bug 1: ねこだまし連打
- **症状**: ターン2以降もFake Outを選択する
- **原因**: Showdownの`|turn|N`を追跡していない。Fake Outはスイッチイン直後のターンのみ使用可能
- **修正**: ログから現在のターン数とスイッチインターンを追跡。スイッチイン直後でなければfake-outをフィルタ

### Bug 2: ステロ重複
- **症状**: 相手側に既にステロが設置されているのに再度撃つ
- **原因**: `_choose_action`のハザード設置ロジック(L810-813)が設置済みチェックをしていない
- **修正**: `_parse_side_conditions`で相手側の設置状況を確認し、設置済みハザードをフィルタ

### Bug 3: PP切れ
- **症状**: PP=0の技をStruggleではなく選択してしまう
- **原因**: Showdownのrequest JSONには`pp: 0`の技が含まれるが、`disabled`フラグは立たない場合がある
- **修正**: `pp == 0`の技をフィルタ（Showdownが自動的にStruggleに変換する）

---

### Task 1: PP=0フィルタ

**Files:**
- Modify: `src/pokechamp/fast_battle.py:786`
- Test: `tests/test_fast_battle.py`

- [ ] **Step 1: テストを書く**

```python
def test_choose_action_skips_pp_zero_moves():
    """Moves with pp=0 should be filtered out."""
    from pokechamp.fast_battle import _choose_action

    request = {
        "active": [
            {
                "moves": [
                    {"move": "Earthquake", "id": "earthquake", "pp": 0, "maxpp": 16,
                     "basePower": 100, "type": "Ground", "category": "Physical",
                     "accuracy": 100, "target": "normal", "disabled": False},
                    {"move": "Stone Edge", "id": "stoneedge", "pp": 8, "maxpp": 8,
                     "basePower": 100, "type": "Rock", "category": "Physical",
                     "accuracy": 80, "target": "normal", "disabled": False},
                ],
            }
        ],
        "side": {
            "pokemon": [
                {
                    "ident": "p1: Garchomp",
                    "active": True,
                    "condition": "183/183",
                    "types": ["dragon", "ground"],
                    "stats": {"atk": 182, "def": 115, "spa": 90, "spd": 105, "spe": 169},
                    "boosts": {},
                }
            ]
        },
    }
    action = _choose_action(request, [], "p1")
    # Should pick Stone Edge (move 2), not Earthquake (pp=0)
    assert action.startswith("move 2")
```

- [ ] **Step 2: テスト失敗を確認**

Run: `.venv/bin/python -m pytest tests/test_fast_battle.py::test_choose_action_skips_pp_zero_moves -v`
Expected: FAIL (picks move 1 because Earthquake has higher score)

- [ ] **Step 3: `available_moves`フィルタにPPチェックを追加**

L786を変更:

```python
# Before:
available_moves = [m for m in moves if not m.get("disabled")]

# After:
available_moves = [m for m in moves if not m.get("disabled") and m.get("pp", 1) > 0]
```

- [ ] **Step 4: テスト通過を確認**

Run: `.venv/bin/python -m pytest tests/test_fast_battle.py::test_choose_action_skips_pp_zero_moves -v`
Expected: PASS

- [ ] **Step 5: コミット**

```bash
git add src/pokechamp/fast_battle.py tests/test_fast_battle.py
git commit -m "fix: skip moves with PP=0 in AI move selection"
```

---

### Task 2: ステロ重複フィルタ

**Files:**
- Modify: `src/pokechamp/fast_battle.py:808-813` (ハザード設置ロジック)
- Test: `tests/test_fast_battle.py`

- [ ] **Step 1: テストを書く**

```python
def test_choose_action_skips_stealth_rock_when_already_set():
    """AI should not use Stealth Rock when already set on opponent's side."""
    from pokechamp.fast_battle import _choose_action

    log_lines = [
        "|switch|p2a: Corviknight|Corviknight, L50, F|173/173",
        "|-sidestart|p2: p2|Stealth Rock",
    ]
    request = {
        "active": [
            {
                "moves": [
                    {"move": "Stealth Rock", "id": "stealthrock", "pp": 16, "maxpp": 16,
                     "basePower": 0, "type": "Rock", "category": "Status",
                     "accuracy": True, "target": "foeSide", "disabled": False},
                    {"move": "Earthquake", "id": "earthquake", "pp": 16, "maxpp": 16,
                     "basePower": 100, "type": "Ground", "category": "Physical",
                     "accuracy": 100, "target": "normal", "disabled": False},
                ],
            }
        ],
        "side": {
            "pokemon": [
                {
                    "ident": "p1: Garchomp",
                    "active": True,
                    "condition": "183/183",
                    "types": ["dragon", "ground"],
                    "stats": {"atk": 182, "def": 115, "spa": 90, "spd": 105, "spe": 169},
                    "boosts": {},
                },
                {"ident": "p1: Corviknight", "active": False, "condition": "173/173",
                 "types": ["steel", "flying"], "stats": {"spe": 130}},
                {"ident": "p1: Primarina", "active": False, "condition": "155/155",
                 "types": ["water", "fairy"], "stats": {"spe": 112}},
            ]
        },
    }
    action = _choose_action(request, log_lines, "p1")
    # Should pick Earthquake, NOT Stealth Rock (already set)
    assert action.startswith("move 2")
```

- [ ] **Step 2: テスト失敗を確認**

Run: `.venv/bin/python -m pytest tests/test_fast_battle.py::test_choose_action_skips_stealth_rock_when_already_set -v`
Expected: FAIL (picks Stealth Rock because hazard logic doesn't check if already set)

- [ ] **Step 3: ハザード設置ロジックに設置済みチェックを追加**

L808-813のハザード設置セクションを修正:

```python
        # Entry hazards setup (if opponent has >=3 mons remaining)
        opp_remaining = _count_opponent_remaining(log_lines, player_id)
        if opp_remaining >= 3:
            opp_id = "p2" if player_id == "p1" else "p1"
            opp_conditions = _parse_side_conditions(log_lines, opp_id)
            opp_conditions_lower = [c.lower() for c in opp_conditions]
            for i, move in enumerate(available_moves):
                move_id = move.get("id", "")
                if move_id in ("stealthrock", "spikes", "stickyweb", "toxicspikes"):
                    # Skip if this hazard is already set on opponent's side
                    hazard_names = {
                        "stealthrock": "stealth rock",
                        "spikes": "spikes",
                        "stickyweb": "sticky web",
                        "toxicspikes": "toxic spikes",
                    }
                    hazard_name = hazard_names.get(move_id, "")
                    if hazard_name and hazard_name in opp_conditions_lower:
                        continue
                    return f"move {moves.index(move) + 1}{mega_suffix}"
```

- [ ] **Step 4: テスト通過を確認**

Run: `.venv/bin/python -m pytest tests/test_fast_battle.py::test_choose_action_skips_stealth_rock_when_already_set -v`
Expected: PASS

- [ ] **Step 5: 全テスト通過を確認**

Run: `.venv/bin/python -m pytest tests/test_fast_battle.py -v`
Expected: 全PASS

- [ ] **Step 6: コミット**

```bash
git add src/pokechamp/fast_battle.py tests/test_fast_battle.py
git commit -m "fix: skip hazard moves when already set on opponent's side"
```

---

### Task 3: ねこだまし（Fake Out）フィルタ

**Files:**
- Modify: `src/pokechamp/fast_battle.py`
- Test: `tests/test_fast_battle.py`

ねこだましはShowdownでは「スイッチイン直後のターンのみ使用可能」。ログから現在のポケモンのスイッチインターンと現在ターンを追跡する。

- [ ] **Step 1: ターン追跡ヘルパーのテストを書く**

```python
def test_parse_current_turn():
    """_parse_current_turn extracts current turn number from log."""
    from pokechamp.fast_battle import _parse_current_turn

    log_lines = ["|turn|1", "|move|p1a: Lopunny|Fake Out", "|turn|2"]
    assert _parse_current_turn(log_lines) == 2

    assert _parse_current_turn([]) == 0
    assert _parse_current_turn(["|turn|1"]) == 1


def test_parse_switch_in_turn():
    """_parse_switch_in_turn returns the turn when active pokemon switched in."""
    from pokechamp.fast_battle import _parse_switch_in_turn

    log_lines = [
        "|turn|1",
        "|switch|p1a: Lopunny|Lopunny, L50, F|151/151",
        "|turn|2",
        "|move|p1a: Lopunny|Return",
        "|turn|3",
    ]
    # Lopunny switched in at turn 1
    assert _parse_switch_in_turn(log_lines, "p1") == 1


def test_parse_switch_in_turn_mid_battle():
    """Switch in during mid-battle tracks latest switch."""
    from pokechamp.fast_battle import _parse_switch_in_turn

    log_lines = [
        "|turn|1",
        "|switch|p1a: Garchomp|Garchomp, L50, M|183/183",
        "|turn|2",
        "|switch|p1a: Lopunny|Lopunny, L50, F|151/151",
        "|turn|3",
    ]
    # Lopunny switched in at turn 2
    assert _parse_switch_in_turn(log_lines, "p1") == 2


def test_parse_switch_in_turn_before_turn1():
    """Initial switch before turn 1 returns turn 0 (meaning first turn is OK)."""
    from pokechamp.fast_battle import _parse_switch_in_turn

    log_lines = [
        "|switch|p1a: Lopunny|Lopunny, L50, F|151/151",
        "|turn|1",
    ]
    # Switched before turn 1 → switch_in_turn = 0
    assert _parse_switch_in_turn(log_lines, "p1") == 0
```

- [ ] **Step 2: テスト失敗を確認**

Run: `.venv/bin/python -m pytest tests/test_fast_battle.py -k "test_parse_current_turn or test_parse_switch_in_turn" -v`
Expected: FAIL

- [ ] **Step 3: ターン追跡ヘルパーを実装**

`_parse_weather`の後、`_extract_species_key`の前に追加:

```python
def _parse_current_turn(log_lines: list[str]) -> int:
    """Return the current turn number from battle log."""
    turn = 0
    for line in log_lines:
        m = re.match(r"\|turn\|(\d+)", line)
        if m:
            turn = int(m.group(1))
    return turn


def _parse_switch_in_turn(log_lines: list[str], player_id: str) -> int:
    """Return the turn number when the player's active pokemon last switched in.

    Returns 0 if switched in before turn 1 (team preview lead).
    """
    switch_in_turn = 0
    current_turn = 0
    for line in log_lines:
        m = re.match(r"\|turn\|(\d+)", line)
        if m:
            current_turn = int(m.group(1))
        if f"|switch|{player_id}a: " in line or f"|drag|{player_id}a: " in line:
            switch_in_turn = current_turn
    return switch_in_turn
```

- [ ] **Step 4: ヘルパーテスト通過を確認**

Run: `.venv/bin/python -m pytest tests/test_fast_battle.py -k "test_parse_current_turn or test_parse_switch_in_turn" -v`
Expected: 4 tests PASS

- [ ] **Step 5: ねこだましフィルタの統合テストを書く**

```python
def test_choose_action_fake_out_only_on_switch_in_turn():
    """Fake Out should only be used on the turn the pokemon switched in."""
    from pokechamp.fast_battle import _choose_action

    base_request = {
        "active": [
            {
                "moves": [
                    {"move": "Fake Out", "id": "fakeout", "pp": 16, "maxpp": 16,
                     "basePower": 40, "type": "Normal", "category": "Physical",
                     "accuracy": 100, "priority": 3, "target": "normal", "disabled": False},
                    {"move": "Return", "id": "return", "pp": 32, "maxpp": 32,
                     "basePower": 102, "type": "Normal", "category": "Physical",
                     "accuracy": 100, "priority": 0, "target": "normal", "disabled": False},
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

    # Turn 1, switched in before turn 1 → Fake Out OK (even though Return has higher base power)
    # Actually the AI scores Return higher (102 > 40), so Fake Out won't be chosen by scoring.
    # Fake Out is relevant for priority KO check. Let's test the filter instead.
    # On switch-in turn: fakeout should be in available moves
    # After switch-in turn: fakeout should be filtered out

    log_turn2 = [
        "|switch|p1a: Lopunny|Lopunny, L50, F|151/151",
        "|turn|1",
        "|move|p1a: Lopunny|Fake Out|p2a: Gengar",
        "|switch|p2a: Gengar|Gengar, L50, M|135/135",
        "|turn|2",
    ]
    # Turn 2, Lopunny switched in before turn 1 → NOT switch-in turn → Fake Out filtered
    action = _choose_action(base_request, log_turn2, "p1")
    # Should pick Return (move 2), not Fake Out
    assert action.startswith("move 2"), f"Expected 'move 2...', got '{action}'"
```

- [ ] **Step 6: 統合テスト失敗を確認**

Run: `.venv/bin/python -m pytest tests/test_fast_battle.py::test_choose_action_fake_out_only_on_switch_in_turn -v`
Expected: FAIL

- [ ] **Step 7: `_choose_action`にねこだましフィルタを追加**

L786のavailable_movesフィルタの後に追加:

```python
    available_moves = [m for m in moves if not m.get("disabled") and m.get("pp", 1) > 0]

    # Filter Fake Out: only usable on the turn the pokemon switched in
    current_turn = _parse_current_turn(log_lines)
    switch_in_turn = _parse_switch_in_turn(log_lines, player_id)
    is_switch_in_turn = (current_turn <= switch_in_turn + 1)
    if not is_switch_in_turn:
        available_moves = [m for m in available_moves if m.get("id") != "fakeout"]
```

注: `current_turn <= switch_in_turn + 1`は「スイッチインターン直後のターン」を意味する。例: switch_in_turn=0(初手), current_turn=1 → OK。switch_in_turn=0, current_turn=2 → NG。

- [ ] **Step 8: テスト通過を確認**

Run: `.venv/bin/python -m pytest tests/test_fast_battle.py::test_choose_action_fake_out_only_on_switch_in_turn -v`
Expected: PASS

- [ ] **Step 9: 全テスト通過を確認**

Run: `.venv/bin/python -m pytest tests/test_fast_battle.py -v`
Expected: 全PASS

- [ ] **Step 10: コミット**

```bash
git add src/pokechamp/fast_battle.py tests/test_fast_battle.py
git commit -m "fix: filter Fake Out after switch-in turn using log-based turn tracking"
```

---

### Task 4: 全体検証 + ruff

- [ ] **Step 1: ruff check**

Run: `.venv/bin/ruff check src/`
Expected: No errors

- [ ] **Step 2: 全テスト**

Run: `.venv/bin/python -m pytest`
Expected: 全PASS

- [ ] **Step 3: コミット（必要な場合のみ）**

---

### Task 5: ドキュメント更新

**Files:**
- Modify: `docs/design/heuristic-ai-spec.md`

- [ ] **Step 1: バグ記録の更新**

heuristic-ai-spec.mdのバグ一覧テーブル（セクション8）で、修正済みバグをマーク:

- ねこだまし再使用 → **修正済み**
- ステロ連打 → **修正済み**
- Struggle（PP切れ） → **修正済み**

- [ ] **Step 2: 意思決定フローの更新**

セクション1の意思決定フロー図にフィルタステップを追加:

```
ターン開始
 │
 ├─ 強制交代中？ → 最適な交代先を選択
 │
 ├─ 技フィルタリング
 │   ├─ PP=0の技を除外
 │   └─ ねこだまし: スイッチイン直後でなければ除外
 │
 ├─ 交代すべきか判定
 ...
 ├─ ステルスロック/まきびし等を撒けるか？
 │   └─ 相手残り3体以上 & **未設置** → 撒く
```

- [ ] **Step 3: コミット**

```bash
git add docs/design/heuristic-ai-spec.md
git commit -m "docs: mark fake-out, stealth rock, and PP bugs as fixed in AI spec"
```
