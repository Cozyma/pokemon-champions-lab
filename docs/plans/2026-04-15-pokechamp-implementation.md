# Pokemon Champions Lab 実装計画

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** ポケモンチャンピオンの構築考察・1v1対面シミュレーションCLIツールを構築する

**Architecture:** Pydanticモデルでポケモン・技・構築を定義し、本編準拠のダメージ計算エンジンで1v1対面シミュを行う。貪欲AI（毎ターン最高ダメージ技選択）+ 展開評価（積み技バリエーション）で勝率を算出。6×6マッチアップ評価と選出推奨を提供する。

**Tech Stack:** Python 3.12+, Pydantic v2, Typer, PyYAML, httpx, pytest

**Design spec:** `docs/design/pokechamp-design.md`

---

## File Structure

| ファイル | 責務 |
|---------|------|
| `pyproject.toml` | パッケージ定義・依存関係・CLIエントリポイント |
| `src/pokechamp/__init__.py` | パッケージ初期化 |
| `src/pokechamp/models.py` | Pydanticモデル（BaseStats, Move, Pokemon, TeamMember, Team, BattleResult, MatchupResult） |
| `src/pokechamp/damage.py` | ダメージ計算エンジン（タイプ相性テーブル、STAB、性格補正、持ち物補正、乱数） |
| `src/pokechamp/battle.py` | 1v1対面シミュレーション（実数値計算、貪欲AI、展開評価） |
| `src/pokechamp/matchup.py` | 構築マッチアップ評価（6×6マトリクス、選出ランキング） |
| `src/pokechamp/importer.py` | PokeAPIインポート + overrides適用 |
| `src/pokechamp/output.py` | テーブル表示 / JSON出力フォーマッタ |
| `src/pokechamp/cli.py` | Typer CLIエントリポイント |
| `tests/test_models.py` | モデルのバリデーションテスト |
| `tests/test_damage.py` | ダメージ計算テスト |
| `tests/test_battle.py` | 対面シミュレーションテスト |
| `tests/test_matchup.py` | マッチアップ評価テスト |
| `data/pokemon/` | ポケモンYAMLデータ |
| `data/moves/` | 技YAMLデータ |
| `data/abilities/` | 特性YAMLデータ |
| `data/items/` | 持ち物YAMLデータ |
| `data/overrides/` | ポケチャン独自調整差分 |
| `teams/example-team/team.yaml` | サンプル構築定義 |
| `teams/example-team/notes.md` | サンプル考察メモ |

---

## Task 1: プロジェクト初期化

**Files:**
- Create: `pyproject.toml`
- Create: `src/pokechamp/__init__.py`
- Create: `.gitignore`

- [ ] **Step 1: Gitリポジトリ初期化**

```bash
cd /home/deploy/pokemon-champions-lab
git init
```

- [ ] **Step 2: .gitignore作成**

```gitignore
__pycache__/
*.pyc
*.egg-info/
dist/
.venv/
.ruff_cache/
```

- [ ] **Step 3: pyproject.toml作成**

```toml
[project]
name = "pokechamp"
version = "0.1.0"
description = "Pokemon Champions team builder & battle simulator"
requires-python = ">=3.12"
dependencies = [
    "pydantic>=2.0",
    "pyyaml>=6.0",
    "typer>=0.12",
    "httpx>=0.27",
    "rich>=13.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "ruff>=0.5",
]

[project.scripts]
pokechamp = "pokechamp.cli:app"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/pokechamp"]

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["src"]

[tool.ruff]
src = ["src"]
target-version = "py312"
```

- [ ] **Step 4: __init__.py作成**

```python
"""Pokemon Champions team builder & battle simulator."""
```

- [ ] **Step 5: venv作成・依存インストール**

```bash
cd /home/deploy/pokemon-champions-lab
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

- [ ] **Step 6: pytest動作確認**

Run: `cd /home/deploy/pokemon-champions-lab && source .venv/bin/activate && pytest --co`
Expected: "no tests ran" (収集のみ、エラーなし)

- [ ] **Step 7: コミット**

```bash
git add pyproject.toml src/pokechamp/__init__.py .gitignore
git commit -m "chore: initialize project with pyproject.toml and package structure"
```

---

## Task 2: データモデル (models.py)

**Files:**
- Create: `src/pokechamp/models.py`
- Create: `tests/test_models.py`

- [ ] **Step 1: テスト作成 — BaseStats, Move, Pokemon**

```python
# tests/test_models.py
import pytest
from pokechamp.models import BaseStats, Move, Pokemon, Nature, TypeName


class TestBaseStats:
    def test_create_valid(self):
        stats = BaseStats(hp=108, attack=130, defense=95, sp_attack=80, sp_defense=85, speed=102)
        assert stats.hp == 108
        assert stats.speed == 102

    def test_reject_negative(self):
        with pytest.raises(ValueError):
            BaseStats(hp=-1, attack=130, defense=95, sp_attack=80, sp_defense=85, speed=102)


class TestMove:
    def test_attack_move(self):
        move = Move(
            name="じしん", name_en="earthquake", type=TypeName.GROUND,
            category="physical", power=100, accuracy=100, pp=10, priority=0,
        )
        assert move.power == 100
        assert move.category == "physical"

    def test_status_move_no_power(self):
        move = Move(
            name="つるぎのまい", name_en="swords-dance", type=TypeName.NORMAL,
            category="status", power=0, accuracy=100, pp=20, priority=0,
            stat_changes=[{"stat": "attack", "stages": 2}],
        )
        assert move.stat_changes[0]["stat"] == "attack"


class TestPokemon:
    def test_create_pokemon(self):
        pokemon = Pokemon(
            name="ガブリアス", name_en="garchomp",
            types=[TypeName.GROUND, TypeName.DRAGON],
            base_stats=BaseStats(hp=108, attack=130, defense=95, sp_attack=80, sp_defense=85, speed=102),
            abilities=["sand-veil", "rough-skin"],
            learnable_moves=["earthquake", "outrage"],
        )
        assert pokemon.name_en == "garchomp"
        assert len(pokemon.types) == 2
```

- [ ] **Step 2: テスト実行 — 失敗確認**

Run: `pytest tests/test_models.py -v`
Expected: FAIL (ModuleNotFoundError: pokechamp.models)

- [ ] **Step 3: models.py実装 — 基本型**

```python
# src/pokechamp/models.py
from __future__ import annotations

from enum import Enum
from pathlib import Path

from pydantic import BaseModel, Field


class TypeName(str, Enum):
    NORMAL = "normal"
    FIRE = "fire"
    WATER = "water"
    ELECTRIC = "electric"
    GRASS = "grass"
    ICE = "ice"
    FIGHTING = "fighting"
    POISON = "poison"
    GROUND = "ground"
    FLYING = "flying"
    PSYCHIC = "psychic"
    BUG = "bug"
    ROCK = "rock"
    GHOST = "ghost"
    DRAGON = "dragon"
    DARK = "dark"
    STEEL = "steel"
    FAIRY = "fairy"


class Nature(str, Enum):
    HARDY = "hardy"
    LONELY = "lonely"
    BRAVE = "brave"
    ADAMANT = "adamant"
    NAUGHTY = "naughty"
    BOLD = "bold"
    DOCILE = "docile"
    RELAXED = "relaxed"
    IMPISH = "impish"
    LAX = "lax"
    TIMID = "timid"
    HASTY = "hasty"
    SERIOUS = "serious"
    JOLLY = "jolly"
    NAIVE = "naive"
    MODEST = "modest"
    MILD = "mild"
    QUIET = "quiet"
    BASHFUL = "bashful"
    RASH = "rash"
    CALM = "calm"
    GENTLE = "gentle"
    SASSY = "sassy"
    CAREFUL = "careful"
    QUIRKY = "quirky"


# 性格補正テーブル: {性格: (上昇ステータス, 下降ステータス)}  無補正はNone
NATURE_MODIFIERS: dict[Nature, tuple[str | None, str | None]] = {
    Nature.HARDY: (None, None),
    Nature.LONELY: ("attack", "defense"),
    Nature.BRAVE: ("attack", "speed"),
    Nature.ADAMANT: ("attack", "sp_attack"),
    Nature.NAUGHTY: ("attack", "sp_defense"),
    Nature.BOLD: ("defense", "attack"),
    Nature.DOCILE: (None, None),
    Nature.RELAXED: ("defense", "speed"),
    Nature.IMPISH: ("defense", "sp_attack"),
    Nature.LAX: ("defense", "sp_defense"),
    Nature.TIMID: ("speed", "attack"),
    Nature.HASTY: ("speed", "defense"),
    Nature.SERIOUS: (None, None),
    Nature.JOLLY: ("speed", "sp_attack"),
    Nature.NAIVE: ("speed", "sp_defense"),
    Nature.MODEST: ("sp_attack", "attack"),
    Nature.MILD: ("sp_attack", "defense"),
    Nature.QUIET: ("sp_attack", "speed"),
    Nature.BASHFUL: (None, None),
    Nature.RASH: ("sp_attack", "sp_defense"),
    Nature.CALM: ("sp_defense", "attack"),
    Nature.GENTLE: ("sp_defense", "defense"),
    Nature.SASSY: ("sp_defense", "speed"),
    Nature.CAREFUL: ("sp_defense", "sp_attack"),
    Nature.QUIRKY: (None, None),
}


class BaseStats(BaseModel):
    hp: int = Field(ge=1)
    attack: int = Field(ge=1)
    defense: int = Field(ge=1)
    sp_attack: int = Field(ge=1)
    sp_defense: int = Field(ge=1)
    speed: int = Field(ge=1)


class StatChange(BaseModel):
    stat: str  # "attack", "defense", "sp_attack", "sp_defense", "speed"
    stages: int  # +2 for swords dance, etc.


class Move(BaseModel):
    name: str
    name_en: str
    type: TypeName
    category: str  # "physical", "special", "status"
    power: int = Field(ge=0)
    accuracy: int = Field(ge=0, le=100)
    pp: int = Field(ge=1)
    priority: int = 0
    effects: list[str] = Field(default_factory=list)
    stat_changes: list[dict[str, int | str]] = Field(default_factory=list)


class Pokemon(BaseModel):
    name: str
    name_en: str
    types: list[TypeName]
    base_stats: BaseStats
    abilities: list[str]
    learnable_moves: list[str]


class EVs(BaseModel):
    hp: int = Field(default=0, ge=0, le=252)
    attack: int = Field(default=0, ge=0, le=252)
    defense: int = Field(default=0, ge=0, le=252)
    sp_attack: int = Field(default=0, ge=0, le=252)
    sp_defense: int = Field(default=0, ge=0, le=252)
    speed: int = Field(default=0, ge=0, le=252)


class IVs(BaseModel):
    hp: int = Field(default=31, ge=0, le=31)
    attack: int = Field(default=31, ge=0, le=31)
    defense: int = Field(default=31, ge=0, le=31)
    sp_attack: int = Field(default=31, ge=0, le=31)
    sp_defense: int = Field(default=31, ge=0, le=31)
    speed: int = Field(default=31, ge=0, le=31)


class TeamMember(BaseModel):
    species: str  # references pokemon name_en
    ability: str
    item: str
    nature: Nature
    evs: EVs = Field(default_factory=EVs)
    ivs: IVs = Field(default_factory=IVs)
    moves: list[str]  # references move name_en, max 4


class Team(BaseModel):
    name: str
    pokemon: list[TeamMember]


class BattleResult(BaseModel):
    pokemon_a: str
    pokemon_b: str
    win_rate_a: float
    win_rate_b: float
    avg_remaining_hp_a: float
    avg_remaining_hp_b: float


class MatchupMatrix(BaseModel):
    team_a_names: list[str]
    team_b_names: list[str]
    matrix: list[list[float]]  # win_rate_a[i][j]


class SelectionScore(BaseModel):
    team_a_selection: list[str]  # 3体
    team_b_selection: list[str]  # 3体
    score: float


class SetupEvaluation(BaseModel):
    pokemon: str
    move: str
    base_win_rate: float
    setup_win_rate: float
    delta: float


class MatchupResult(BaseModel):
    team_a: str
    team_b: str
    matrix: MatchupMatrix
    setup_evaluations: list[SetupEvaluation]
    selection_ranking: list[SelectionScore]
    overall_score: float
```

- [ ] **Step 4: テスト実行 — 成功確認**

Run: `pytest tests/test_models.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: テスト追加 — TeamMember, Team**

```python
# tests/test_models.py に追記

from pokechamp.models import TeamMember, Team, EVs, IVs


class TestTeamMember:
    def test_create_with_defaults(self):
        member = TeamMember(
            species="garchomp", ability="rough-skin", item="choice-scarf",
            nature=Nature.JOLLY, moves=["earthquake", "outrage", "iron-head", "stone-edge"],
        )
        assert member.ivs.attack == 31  # デフォルト全31
        assert member.evs.hp == 0  # デフォルト全0

    def test_create_with_custom_evs(self):
        member = TeamMember(
            species="garchomp", ability="rough-skin", item="choice-scarf",
            nature=Nature.JOLLY,
            evs=EVs(hp=4, attack=252, speed=252),
            moves=["earthquake", "outrage", "iron-head", "stone-edge"],
        )
        assert member.evs.attack == 252
        assert member.evs.defense == 0


class TestTeam:
    def test_create_team(self):
        members = [
            TeamMember(
                species=f"pokemon-{i}", ability="ability", item="item",
                nature=Nature.ADAMANT, moves=["move-a", "move-b"],
            )
            for i in range(6)
        ]
        team = Team(name="テストチーム", pokemon=members)
        assert len(team.pokemon) == 6
```

- [ ] **Step 6: テスト実行 — 成功確認**

Run: `pytest tests/test_models.py -v`
Expected: PASS (6 tests)

- [ ] **Step 7: コミット**

```bash
git add src/pokechamp/models.py tests/test_models.py
git commit -m "feat: add Pydantic data models for pokemon, moves, teams, and battle results"
```

---

## Task 3: YAML データローダー + サンプルデータ

**Files:**
- Create: `src/pokechamp/loader.py`
- Create: `tests/test_loader.py`
- Create: `data/pokemon/garchomp.yaml`
- Create: `data/moves/earthquake.yaml`
- Create: `data/moves/swords-dance.yaml`
- Create: `data/items/choice-scarf.yaml`
- Create: `data/items/life-orb.yaml`
- Create: `data/overrides/.gitkeep`
- Create: `teams/example-team/team.yaml`
- Create: `teams/example-team/notes.md`

- [ ] **Step 1: テスト作成 — YAMLロード**

```python
# tests/test_loader.py
from pathlib import Path
from pokechamp.loader import load_pokemon, load_move, load_team, load_item, get_data_dir


class TestLoadPokemon:
    def test_load_garchomp(self):
        pokemon = load_pokemon("garchomp")
        assert pokemon.name_en == "garchomp"
        assert pokemon.base_stats.attack == 130
        assert "ground" in [t.value for t in pokemon.types]

    def test_load_nonexistent_raises(self):
        import pytest
        with pytest.raises(FileNotFoundError):
            load_pokemon("missingno")


class TestLoadMove:
    def test_load_earthquake(self):
        move = load_move("earthquake")
        assert move.power == 100
        assert move.category == "physical"

    def test_load_status_move(self):
        move = load_move("swords-dance")
        assert move.category == "status"
        assert move.power == 0
        assert len(move.stat_changes) > 0


class TestLoadItem:
    def test_load_choice_scarf(self):
        item = load_item("choice-scarf")
        assert item["effect"] == "speed_multiply"
        assert item["value"] == 1.5


class TestLoadTeam:
    def test_load_example_team(self):
        team = load_team("example-team")
        assert team.name is not None
        assert len(team.pokemon) >= 1
```

- [ ] **Step 2: テスト実行 — 失敗確認**

Run: `pytest tests/test_loader.py -v`
Expected: FAIL (ModuleNotFoundError: pokechamp.loader)

- [ ] **Step 3: サンプルYAMLデータ作成**

`data/pokemon/garchomp.yaml`:
```yaml
name: ガブリアス
name_en: garchomp
types: [ground, dragon]
base_stats:
  hp: 108
  attack: 130
  defense: 95
  sp_attack: 80
  sp_defense: 85
  speed: 102
abilities: [sand-veil, rough-skin]
learnable_moves: [earthquake, outrage, swords-dance, scale-shot, iron-head, stone-edge, fire-fang, dragon-claw]
```

`data/moves/earthquake.yaml`:
```yaml
name: じしん
name_en: earthquake
type: ground
category: physical
power: 100
accuracy: 100
pp: 10
priority: 0
effects: []
stat_changes: []
```

`data/moves/swords-dance.yaml`:
```yaml
name: つるぎのまい
name_en: swords-dance
type: normal
category: status
power: 0
accuracy: 100
pp: 20
priority: 0
effects: []
stat_changes:
  - stat: attack
    stages: 2
```

`data/items/choice-scarf.yaml`:
```yaml
name: こだわりスカーフ
name_en: choice-scarf
effect: speed_multiply
value: 1.5
```

`data/items/life-orb.yaml`:
```yaml
name: いのちのたま
name_en: life-orb
effect: damage_multiply
value: 1.3
```

`data/overrides/.gitkeep`: (空ファイル)

`teams/example-team/team.yaml`:
```yaml
name: サンプル構築
pokemon:
  - species: garchomp
    ability: rough-skin
    item: choice-scarf
    nature: jolly
    evs: {hp: 4, attack: 252, speed: 252}
    moves: [earthquake, outrage, iron-head, stone-edge]
```

`teams/example-team/notes.md`:
```markdown
# サンプル構築 考察メモ

## 戦略方針
- 対面構築

## 基本選出
- (考察中)

## メタ考察
- (考察中)
```

- [ ] **Step 4: loader.py実装**

```python
# src/pokechamp/loader.py
from __future__ import annotations

from pathlib import Path

import yaml

from pokechamp.models import Move, Pokemon, Team


def get_data_dir() -> Path:
    """Return the data/ directory at project root."""
    return Path(__file__).resolve().parent.parent.parent / "data"


def get_teams_dir() -> Path:
    """Return the teams/ directory at project root."""
    return Path(__file__).resolve().parent.parent.parent / "teams"


def _load_yaml(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"Data file not found: {path}")
    with open(path) as f:
        return yaml.safe_load(f)


def _apply_overrides(data: dict, category: str, name: str) -> dict:
    """Apply overrides from data/overrides/ if they exist."""
    overrides_dir = get_data_dir() / "overrides"
    for override_file in overrides_dir.glob("*.yaml"):
        override = _load_yaml(override_file)
        if override.get("target") == f"{category}/{name}":
            changes = override.get("changes", {})
            _deep_merge(data, changes)
    return data


def _deep_merge(base: dict, override: dict) -> None:
    """Recursively merge override into base dict."""
    for key, value in override.items():
        if key in base and isinstance(base[key], dict) and isinstance(value, dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value


def load_pokemon(name_en: str) -> Pokemon:
    path = get_data_dir() / "pokemon" / f"{name_en}.yaml"
    data = _load_yaml(path)
    data = _apply_overrides(data, "pokemon", name_en)
    return Pokemon(**data)


def load_move(name_en: str) -> Move:
    path = get_data_dir() / "moves" / f"{name_en}.yaml"
    data = _load_yaml(path)
    data = _apply_overrides(data, "moves", name_en)
    return Move(**data)


def load_item(name_en: str) -> dict:
    path = get_data_dir() / "items" / f"{name_en}.yaml"
    return _load_yaml(path)


def load_team(team_name: str) -> Team:
    path = get_teams_dir() / team_name / "team.yaml"
    data = _load_yaml(path)
    return Team(**data)


def list_pokemon() -> list[str]:
    return sorted(p.stem for p in (get_data_dir() / "pokemon").glob("*.yaml"))


def list_teams() -> list[str]:
    teams_dir = get_teams_dir()
    return sorted(d.name for d in teams_dir.iterdir() if d.is_dir() and (d / "team.yaml").exists())
```

- [ ] **Step 5: テスト実行 — 成功確認**

Run: `pytest tests/test_loader.py -v`
Expected: PASS (5 tests)

- [ ] **Step 6: コミット**

```bash
git add src/pokechamp/loader.py tests/test_loader.py data/ teams/
git commit -m "feat: add YAML data loader with sample pokemon, moves, items, and team data"
```

---

## Task 4: ダメージ計算エンジン (damage.py)

**Files:**
- Create: `src/pokechamp/damage.py`
- Create: `tests/test_damage.py`

- [ ] **Step 1: テスト作成 — タイプ相性**

```python
# tests/test_damage.py
from pokechamp.damage import type_effectiveness, calc_stat, calc_damage_range
from pokechamp.models import TypeName, Nature


class TestTypeEffectiveness:
    def test_super_effective(self):
        assert type_effectiveness(TypeName.FIRE, TypeName.GRASS) == 2.0

    def test_not_very_effective(self):
        assert type_effectiveness(TypeName.FIRE, TypeName.WATER) == 0.5

    def test_immune(self):
        assert type_effectiveness(TypeName.NORMAL, TypeName.GHOST) == 0.0

    def test_neutral(self):
        assert type_effectiveness(TypeName.FIRE, TypeName.FIGHTING) == 1.0

    def test_multi_type_super_effective(self):
        # ground vs fire/steel = 2 * 2 = 4
        eff = type_effectiveness(TypeName.GROUND, TypeName.FIRE) * type_effectiveness(TypeName.GROUND, TypeName.STEEL)
        assert eff == 4.0
```

- [ ] **Step 2: テスト実行 — 失敗確認**

Run: `pytest tests/test_damage.py::TestTypeEffectiveness -v`
Expected: FAIL

- [ ] **Step 3: damage.py実装 — タイプ相性テーブル**

```python
# src/pokechamp/damage.py
from __future__ import annotations

import math

from pokechamp.models import TypeName, Nature, NATURE_MODIFIERS

# タイプ相性テーブル: EFFECTIVENESS[攻撃タイプ][防御タイプ]
# 1.0 = 等倍のみ省略し、デフォルト1.0
_SE = 2.0  # 効果抜群
_NE = 0.5  # 今ひとつ
_IM = 0.0  # 無効

_TYPE_CHART: dict[TypeName, dict[TypeName, float]] = {
    TypeName.NORMAL: {TypeName.ROCK: _NE, TypeName.GHOST: _IM, TypeName.STEEL: _NE},
    TypeName.FIRE: {TypeName.FIRE: _NE, TypeName.WATER: _NE, TypeName.GRASS: _SE, TypeName.ICE: _SE, TypeName.BUG: _SE, TypeName.ROCK: _NE, TypeName.DRAGON: _NE, TypeName.STEEL: _SE},
    TypeName.WATER: {TypeName.FIRE: _SE, TypeName.WATER: _NE, TypeName.GRASS: _NE, TypeName.GROUND: _SE, TypeName.ROCK: _SE, TypeName.DRAGON: _NE},
    TypeName.ELECTRIC: {TypeName.WATER: _SE, TypeName.ELECTRIC: _NE, TypeName.GRASS: _NE, TypeName.GROUND: _IM, TypeName.FLYING: _SE, TypeName.DRAGON: _NE},
    TypeName.GRASS: {TypeName.FIRE: _NE, TypeName.WATER: _SE, TypeName.GRASS: _NE, TypeName.POISON: _NE, TypeName.GROUND: _SE, TypeName.FLYING: _NE, TypeName.BUG: _NE, TypeName.ROCK: _SE, TypeName.DRAGON: _NE, TypeName.STEEL: _NE},
    TypeName.ICE: {TypeName.FIRE: _NE, TypeName.WATER: _NE, TypeName.GRASS: _SE, TypeName.ICE: _NE, TypeName.GROUND: _SE, TypeName.FLYING: _SE, TypeName.DRAGON: _SE, TypeName.STEEL: _NE},
    TypeName.FIGHTING: {TypeName.NORMAL: _SE, TypeName.ICE: _SE, TypeName.POISON: _NE, TypeName.FLYING: _NE, TypeName.PSYCHIC: _NE, TypeName.BUG: _NE, TypeName.ROCK: _SE, TypeName.GHOST: _IM, TypeName.DARK: _SE, TypeName.STEEL: _SE, TypeName.FAIRY: _NE},
    TypeName.POISON: {TypeName.GRASS: _SE, TypeName.POISON: _NE, TypeName.GROUND: _NE, TypeName.ROCK: _NE, TypeName.GHOST: _NE, TypeName.STEEL: _IM, TypeName.FAIRY: _SE},
    TypeName.GROUND: {TypeName.FIRE: _SE, TypeName.ELECTRIC: _SE, TypeName.GRASS: _NE, TypeName.POISON: _SE, TypeName.FLYING: _IM, TypeName.BUG: _NE, TypeName.ROCK: _SE, TypeName.STEEL: _SE},
    TypeName.FLYING: {TypeName.ELECTRIC: _NE, TypeName.GRASS: _SE, TypeName.FIGHTING: _SE, TypeName.BUG: _SE, TypeName.ROCK: _NE, TypeName.STEEL: _NE},
    TypeName.PSYCHIC: {TypeName.FIGHTING: _SE, TypeName.POISON: _SE, TypeName.PSYCHIC: _NE, TypeName.DARK: _IM, TypeName.STEEL: _NE},
    TypeName.BUG: {TypeName.FIRE: _NE, TypeName.GRASS: _SE, TypeName.FIGHTING: _NE, TypeName.POISON: _NE, TypeName.FLYING: _NE, TypeName.PSYCHIC: _SE, TypeName.GHOST: _NE, TypeName.DARK: _SE, TypeName.STEEL: _NE, TypeName.FAIRY: _NE},
    TypeName.ROCK: {TypeName.FIRE: _SE, TypeName.ICE: _SE, TypeName.FIGHTING: _NE, TypeName.GROUND: _NE, TypeName.FLYING: _SE, TypeName.BUG: _SE, TypeName.STEEL: _NE},
    TypeName.GHOST: {TypeName.NORMAL: _IM, TypeName.PSYCHIC: _SE, TypeName.GHOST: _SE, TypeName.DARK: _NE},
    TypeName.DRAGON: {TypeName.DRAGON: _SE, TypeName.STEEL: _NE, TypeName.FAIRY: _IM},
    TypeName.DARK: {TypeName.FIGHTING: _NE, TypeName.PSYCHIC: _SE, TypeName.GHOST: _SE, TypeName.DARK: _NE, TypeName.FAIRY: _NE},
    TypeName.STEEL: {TypeName.FIRE: _NE, TypeName.WATER: _NE, TypeName.ELECTRIC: _NE, TypeName.ICE: _SE, TypeName.ROCK: _SE, TypeName.STEEL: _NE, TypeName.FAIRY: _SE},
    TypeName.FAIRY: {TypeName.FIRE: _NE, TypeName.POISON: _NE, TypeName.FIGHTING: _SE, TypeName.DRAGON: _SE, TypeName.DARK: _SE, TypeName.STEEL: _NE},
}


def type_effectiveness(attack_type: TypeName, defend_type: TypeName) -> float:
    """Return type effectiveness multiplier for a single attacking type vs single defending type."""
    return _TYPE_CHART.get(attack_type, {}).get(defend_type, 1.0)


def calc_stat(
    base: int, iv: int, ev: int, level: int, nature: Nature, stat_name: str,
) -> int:
    """Calculate actual stat value. HP uses a different formula."""
    if stat_name == "hp":
        return math.floor((2 * base + iv + math.floor(ev / 4)) * level / 100) + level + 10

    raw = math.floor((2 * base + iv + math.floor(ev / 4)) * level / 100) + 5
    up, down = NATURE_MODIFIERS[nature]
    if up == stat_name:
        raw = math.floor(raw * 1.1)
    elif down == stat_name:
        raw = math.floor(raw * 0.9)
    return raw


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
    """Calculate all 16 possible damage values (random factor 85-100)."""
    if power == 0 or type_eff == 0.0:
        return [0] * 16

    base = math.floor(math.floor(math.floor(2 * level / 5 + 2) * power * attack_stat / defense_stat) / 50 + 2)

    results = []
    for roll in range(85, 101):
        damage = math.floor(base * roll / 100)
        if stab:
            damage = math.floor(damage * 1.5)
        damage = math.floor(damage * type_eff)
        damage = math.floor(damage * item_modifier)
        damage = max(1, damage)  # 最低1ダメージ (無効を除く)
        results.append(damage)
    return results
```

- [ ] **Step 4: テスト実行 — タイプ相性テスト成功確認**

Run: `pytest tests/test_damage.py::TestTypeEffectiveness -v`
Expected: PASS

- [ ] **Step 5: テスト追加 — ステータス計算**

```python
# tests/test_damage.py に追記

class TestCalcStat:
    def test_hp_stat(self):
        # ガブリアスHP: base108, IV31, EV4, Lv50 = 183
        hp = calc_stat(base=108, iv=31, ev=4, level=50, nature=Nature.JOLLY, stat_name="hp")
        assert hp == 184

    def test_attack_with_nature_boost(self):
        # ガブリアス攻撃: base130, IV31, EV252, Lv50, いじっぱり(attack↑)
        atk = calc_stat(base=130, iv=31, ev=252, level=50, nature=Nature.ADAMANT, stat_name="attack")
        assert atk == 200

    def test_speed_with_nature_boost(self):
        # ガブリアス素早さ: base102, IV31, EV252, Lv50, ようき(speed↑)
        spe = calc_stat(base=102, iv=31, ev=252, level=50, nature=Nature.JOLLY, stat_name="speed")
        assert spe == 169
```

- [ ] **Step 6: テスト実行 — 成功確認**

Run: `pytest tests/test_damage.py -v`
Expected: PASS (8 tests)

- [ ] **Step 7: テスト追加 — ダメージ計算**

```python
# tests/test_damage.py に追記

class TestCalcDamageRange:
    def test_earthquake_damage(self):
        # Lv50 A200 地震(100) vs D100 等倍 タイプ一致
        damages = calc_damage_range(
            level=50, power=100, attack_stat=200, defense_stat=100,
            stab=True, type_eff=1.0,
        )
        assert len(damages) == 16
        assert damages[0] < damages[-1]  # 最小 < 最大
        assert all(d > 0 for d in damages)

    def test_immune_does_zero(self):
        damages = calc_damage_range(
            level=50, power=100, attack_stat=200, defense_stat=100,
            stab=False, type_eff=0.0,
        )
        assert all(d == 0 for d in damages)

    def test_item_modifier(self):
        base = calc_damage_range(
            level=50, power=100, attack_stat=150, defense_stat=100,
            stab=False, type_eff=1.0, item_modifier=1.0,
        )
        boosted = calc_damage_range(
            level=50, power=100, attack_stat=150, defense_stat=100,
            stab=False, type_eff=1.0, item_modifier=1.3,
        )
        assert boosted[-1] > base[-1]
```

- [ ] **Step 8: テスト実行 — 成功確認**

Run: `pytest tests/test_damage.py -v`
Expected: PASS (11 tests)

- [ ] **Step 9: コミット**

```bash
git add src/pokechamp/damage.py tests/test_damage.py
git commit -m "feat: add damage calculation engine with type chart, stat calc, and damage range"
```

---

## Task 5: 1v1対面シミュレーション (battle.py)

**Files:**
- Create: `src/pokechamp/battle.py`
- Create: `tests/test_battle.py`
- Create: `data/pokemon/magikarp.yaml`
- Create: `data/moves/splash.yaml`
- Create: `data/moves/outrage.yaml`
- Create: `data/moves/iron-head.yaml`
- Create: `data/moves/stone-edge.yaml`

- [ ] **Step 1: テスト用の追加データ作成**

`data/pokemon/magikarp.yaml`:
```yaml
name: コイキング
name_en: magikarp
types: [water]
base_stats:
  hp: 20
  attack: 10
  defense: 55
  sp_attack: 15
  sp_defense: 20
  speed: 80
abilities: [swift-swim, rattled]
learnable_moves: [splash, tackle, flail]
```

`data/moves/splash.yaml`:
```yaml
name: はねる
name_en: splash
type: normal
category: status
power: 0
accuracy: 100
pp: 40
priority: 0
effects: []
stat_changes: []
```

`data/moves/outrage.yaml`:
```yaml
name: げきりん
name_en: outrage
type: dragon
category: physical
power: 120
accuracy: 100
pp: 10
priority: 0
effects: []
stat_changes: []
```

`data/moves/iron-head.yaml`:
```yaml
name: アイアンヘッド
name_en: iron-head
type: steel
category: physical
power: 80
accuracy: 100
pp: 15
priority: 0
effects: []
stat_changes: []
```

`data/moves/stone-edge.yaml`:
```yaml
name: ストーンエッジ
name_en: stone-edge
type: rock
category: physical
power: 100
accuracy: 80
pp: 5
priority: 0
effects: []
stat_changes: []
```

- [ ] **Step 2: テスト作成 — BattlePokemon実数値, 1v1バトル**

```python
# tests/test_battle.py
from pokechamp.battle import BattlePokemon, simulate_1v1
from pokechamp.models import Nature


class TestBattlePokemon:
    def test_from_team_member(self):
        """ガブリアス(ようき AS252 H4)の実数値を検証"""
        bp = BattlePokemon.from_data(
            species="garchomp", nature=Nature.JOLLY,
            evs={"hp": 4, "attack": 252, "speed": 252},
            ivs={}, item="choice-scarf",
            move_names=["earthquake", "outrage", "iron-head", "stone-edge"],
        )
        assert bp.name == "garchomp"
        assert bp.stats["hp"] == 184
        assert bp.stats["speed"] == 169

    def test_garchomp_vs_magikarp(self):
        """ガブリアスはコイキング(はねるのみ)に100%勝つ"""
        garchomp = BattlePokemon.from_data(
            species="garchomp", nature=Nature.JOLLY,
            evs={"hp": 4, "attack": 252, "speed": 252},
            ivs={}, item="choice-scarf",
            move_names=["earthquake"],
        )
        magikarp = BattlePokemon.from_data(
            species="magikarp", nature=Nature.JOLLY,
            evs={}, ivs={}, item="",
            move_names=["splash"],
        )
        result = simulate_1v1(garchomp, magikarp)
        assert result.win_rate_a == 1.0
        assert result.win_rate_b == 0.0
```

- [ ] **Step 3: テスト実行 — 失敗確認**

Run: `pytest tests/test_battle.py -v`
Expected: FAIL

- [ ] **Step 4: battle.py実装**

```python
# src/pokechamp/battle.py
from __future__ import annotations

import random
from dataclasses import dataclass, field

from pokechamp.damage import calc_stat, calc_damage_range, type_effectiveness
from pokechamp.loader import load_pokemon, load_move, load_item
from pokechamp.models import (
    BattleResult,
    Move,
    Nature,
    TypeName,
)

# 持ち物の効果マッピング
_ITEM_EFFECTS: dict[str, dict] = {
    "choice-band": {"type": "attack_multiply", "value": 1.5},
    "choice-specs": {"type": "sp_attack_multiply", "value": 1.5},
    "choice-scarf": {"type": "speed_multiply", "value": 1.5},
    "life-orb": {"type": "damage_multiply", "value": 1.3},
}


@dataclass
class BattlePokemon:
    name: str
    types: list[TypeName]
    stats: dict[str, int]  # actual stats (hp, attack, defense, sp_attack, sp_defense, speed)
    moves: list[Move]
    item: str
    stage_modifiers: dict[str, int] = field(default_factory=lambda: {
        "attack": 0, "defense": 0, "sp_attack": 0, "sp_defense": 0, "speed": 0,
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
    ) -> BattlePokemon:
        pokemon = load_pokemon(species)
        base = pokemon.base_stats

        default_iv = 31
        stat_names = ["hp", "attack", "defense", "sp_attack", "sp_defense", "speed"]
        base_values = {
            "hp": base.hp, "attack": base.attack, "defense": base.defense,
            "sp_attack": base.sp_attack, "sp_defense": base.sp_defense, "speed": base.speed,
        }

        stats = {}
        for s in stat_names:
            stats[s] = calc_stat(
                base=base_values[s],
                iv=ivs.get(s, default_iv),
                ev=evs.get(s, 0),
                level=level,
                nature=nature,
                stat_name=s,
            )

        # 持ち物によるステータス補正（スカーフ等）
        item_effect = _ITEM_EFFECTS.get(item, {})
        if item_effect.get("type") == "speed_multiply":
            stats["speed"] = int(stats["speed"] * item_effect["value"])
        elif item_effect.get("type") == "attack_multiply":
            stats["attack"] = int(stats["attack"] * item_effect["value"])
        elif item_effect.get("type") == "sp_attack_multiply":
            stats["sp_attack"] = int(stats["sp_attack"] * item_effect["value"])

        moves = [load_move(m) for m in move_names]
        return cls(name=species, types=pokemon.types, stats=stats, moves=moves, item=item)

    def get_effective_stat(self, stat_name: str) -> int:
        """ランク補正を加味した実効ステータス値を返す."""
        base_val = self.stats[stat_name]
        stage = self.stage_modifiers.get(stat_name, 0)
        if stage >= 0:
            return int(base_val * (2 + stage) / 2)
        else:
            return int(base_val * 2 / (2 - stage))

    def best_move_against(self, opponent: BattlePokemon) -> tuple[Move, float, list[int]]:
        """相手に対して最もダメージの大きい技を選択。(技, タイプ相性倍率, ダメージ範囲)を返す."""
        best: tuple[Move, float, list[int]] | None = None
        best_avg = 0.0

        for move in self.moves:
            if move.category == "status":
                continue

            # タイプ相性
            eff = 1.0
            for def_type in opponent.types:
                eff *= type_effectiveness(move.type, def_type)

            if eff == 0.0:
                continue

            # 攻撃/防御ステータス決定
            if move.category == "physical":
                atk = self.get_effective_stat("attack")
                dfn = opponent.get_effective_stat("defense")
            else:
                atk = self.get_effective_stat("sp_attack")
                dfn = opponent.get_effective_stat("sp_defense")

            stab = move.type in self.types

            # 持ち物ダメージ補正
            item_mod = 1.0
            item_effect = _ITEM_EFFECTS.get(self.item, {})
            if item_effect.get("type") == "damage_multiply":
                item_mod = item_effect["value"]

            damages = calc_damage_range(
                level=50, power=move.power, attack_stat=atk, defense_stat=dfn,
                stab=stab, type_eff=eff, item_modifier=item_mod,
            )
            avg = sum(damages) / len(damages)
            if avg > best_avg:
                best_avg = avg
                best = (move, eff, damages)

        if best is None:
            # 全技が無効 → ダメージ0
            return self.moves[0], 0.0, [0] * 16

        return best


def _apply_setup(pokemon: BattlePokemon, setup_move_name: str, turns: int) -> None:
    """積み技を適用してランク補正を更新."""
    move = load_move(setup_move_name)
    for _ in range(turns):
        for change in move.stat_changes:
            stat = change["stat"]
            stages = change["stages"]
            current = pokemon.stage_modifiers.get(stat, 0)
            pokemon.stage_modifiers[stat] = min(6, max(-6, current + stages))


def simulate_1v1(
    a: BattlePokemon,
    b: BattlePokemon,
    setup_move: str | None = None,
    setup_turns: int = 0,
    n_trials: int = 1000,
) -> BattleResult:
    """1v1対面シミュレーション。勝率を算出して返す."""
    # 展開ターン適用
    if setup_move and setup_turns > 0:
        _apply_setup(a, setup_move, setup_turns)

    # 最適技とダメージ範囲を取得
    move_a, _, damages_a = a.best_move_against(b)
    move_b, _, damages_b = b.best_move_against(a)

    hp_a_max = a.stats["hp"]
    hp_b_max = b.stats["hp"]

    # 先攻判定（同速は50%ずつ）
    speed_a = a.get_effective_stat("speed")
    speed_b = b.get_effective_stat("speed")

    # 先制技の優先度チェック
    priority_a = move_a.priority
    priority_b = move_b.priority

    # 1ターンで決着するか判定（全列挙可能か）
    max_dmg_a = max(damages_a) if any(d > 0 for d in damages_a) else 0
    max_dmg_b = max(damages_b) if any(d > 0 for d in damages_b) else 0
    min_dmg_a = min(damages_a) if any(d > 0 for d in damages_a) else 0
    min_dmg_b = min(damages_b) if any(d > 0 for d in damages_b) else 0

    one_turn_ko = (min_dmg_a >= hp_b_max) or (min_dmg_b >= hp_a_max) or (max_dmg_a >= hp_b_max and max_dmg_b >= hp_a_max)

    if one_turn_ko and speed_a != speed_b:
        # 全列挙: 16*16 = 256パターン
        wins_a = 0
        wins_b = 0
        total = 0
        remaining_hp_a_sum = 0.0
        remaining_hp_b_sum = 0.0

        for da in damages_a:
            for db in damages_b:
                total += 1
                if priority_a > priority_b or (priority_a == priority_b and speed_a > speed_b):
                    # A先攻
                    if da >= hp_b_max:
                        wins_a += 1
                        remaining_hp_a_sum += hp_a_max
                    else:
                        hp_b_after = hp_b_max - da
                        if db >= hp_a_max:
                            wins_b += 1
                            remaining_hp_b_sum += hp_b_after
                        else:
                            # 1ターンで決着しないパターン（理論上ここには来ない）
                            wins_a += 0.5
                            wins_b += 0.5
                else:
                    # B先攻
                    if db >= hp_a_max:
                        wins_b += 1
                        remaining_hp_b_sum += hp_b_max
                    else:
                        hp_a_after = hp_a_max - db
                        if da >= hp_b_max:
                            wins_a += 1
                            remaining_hp_a_sum += hp_a_after
                        else:
                            wins_a += 0.5
                            wins_b += 0.5

        return BattleResult(
            pokemon_a=a.name, pokemon_b=b.name,
            win_rate_a=wins_a / total, win_rate_b=wins_b / total,
            avg_remaining_hp_a=remaining_hp_a_sum / total,
            avg_remaining_hp_b=remaining_hp_b_sum / total,
        )

    # モンテカルロシミュレーション
    wins_a = 0
    wins_b = 0
    remaining_hp_a_sum = 0.0
    remaining_hp_b_sum = 0.0

    for _ in range(n_trials):
        hp_a = hp_a_max
        hp_b = hp_b_max

        while hp_a > 0 and hp_b > 0:
            da = random.choice(damages_a)
            db = random.choice(damages_b)

            # 先攻判定
            if priority_a > priority_b:
                a_first = True
            elif priority_b > priority_a:
                a_first = False
            elif speed_a > speed_b:
                a_first = True
            elif speed_b > speed_a:
                a_first = False
            else:
                a_first = random.random() < 0.5

            if a_first:
                hp_b -= da
                if hp_b <= 0:
                    break
                hp_a -= db
            else:
                hp_a -= db
                if hp_a <= 0:
                    break
                hp_b -= da

        if hp_a > 0 and hp_b <= 0:
            wins_a += 1
            remaining_hp_a_sum += hp_a
        elif hp_b > 0 and hp_a <= 0:
            wins_b += 1
            remaining_hp_b_sum += hp_b
        else:
            # 同時に倒れた場合は先攻側の勝ち扱い（ゲーム準拠）
            wins_a += 0.5
            wins_b += 0.5

    return BattleResult(
        pokemon_a=a.name, pokemon_b=b.name,
        win_rate_a=wins_a / n_trials, win_rate_b=wins_b / n_trials,
        avg_remaining_hp_a=remaining_hp_a_sum / n_trials,
        avg_remaining_hp_b=remaining_hp_b_sum / n_trials,
    )
```

- [ ] **Step 5: テスト実行 — 成功確認**

Run: `pytest tests/test_battle.py -v`
Expected: PASS (2 tests)

- [ ] **Step 6: テスト追加 — 展開評価**

```python
# tests/test_battle.py に追記

class TestSetupEvaluation:
    def test_swords_dance_improves_win_rate(self):
        """剣舞1積みで勝率が上がることを確認"""
        garchomp = BattlePokemon.from_data(
            species="garchomp", nature=Nature.JOLLY,
            evs={"hp": 4, "attack": 252, "speed": 252},
            ivs={}, item="",
            move_names=["earthquake", "outrage"],
        )
        # 同じガブリアスで積みなし
        base_result = simulate_1v1(
            garchomp,
            BattlePokemon.from_data(
                species="garchomp", nature=Nature.JOLLY,
                evs={"hp": 4, "attack": 252, "speed": 252},
                ivs={}, item="",
                move_names=["earthquake", "outrage"],
            ),
        )
        # 積みあり（別インスタンスで）
        garchomp_setup = BattlePokemon.from_data(
            species="garchomp", nature=Nature.JOLLY,
            evs={"hp": 4, "attack": 252, "speed": 252},
            ivs={}, item="",
            move_names=["earthquake", "outrage"],
        )
        setup_result = simulate_1v1(
            garchomp_setup,
            BattlePokemon.from_data(
                species="garchomp", nature=Nature.JOLLY,
                evs={"hp": 4, "attack": 252, "speed": 252},
                ivs={}, item="",
                move_names=["earthquake", "outrage"],
            ),
            setup_move="swords-dance",
            setup_turns=1,
        )
        # 同速なのでミラーは50%前後だが、積み後は有利になるはず
        assert setup_result.win_rate_a > base_result.win_rate_a
```

- [ ] **Step 7: テスト実行 — 成功確認**

Run: `pytest tests/test_battle.py -v`
Expected: PASS (3 tests)

- [ ] **Step 8: コミット**

```bash
git add src/pokechamp/battle.py tests/test_battle.py data/pokemon/magikarp.yaml data/moves/splash.yaml data/moves/outrage.yaml data/moves/iron-head.yaml data/moves/stone-edge.yaml
git commit -m "feat: add 1v1 battle simulation with greedy AI and setup move evaluation"
```

---

## Task 6: 構築マッチアップ評価 (matchup.py)

**Files:**
- Create: `src/pokechamp/matchup.py`
- Create: `tests/test_matchup.py`

- [ ] **Step 1: テスト作成**

```python
# tests/test_matchup.py
from pokechamp.matchup import evaluate_matchup, build_battle_pokemon_from_team
from pokechamp.loader import load_team


class TestBuildBattlePokemon:
    def test_from_team(self):
        team = load_team("example-team")
        battle_pokemon = build_battle_pokemon_from_team(team)
        assert len(battle_pokemon) == len(team.pokemon)
        assert battle_pokemon[0].name == "garchomp"


class TestEvaluateMatchup:
    def test_mirror_matchup(self):
        """同じ構築同士のマッチアップはスコア約50%になる"""
        result = evaluate_matchup("example-team", "example-team")
        assert result.team_a == "サンプル構築"
        assert result.team_b == "サンプル構築"
        # ミラーなので全対角が ~50%
        for i, row in enumerate(result.matrix.matrix):
            for j, win_rate in enumerate(row):
                if i == j:
                    assert 0.3 <= win_rate <= 0.7  # 同速乱数で50%前後
```

- [ ] **Step 2: テスト実行 — 失敗確認**

Run: `pytest tests/test_matchup.py -v`
Expected: FAIL

- [ ] **Step 3: matchup.py実装**

```python
# src/pokechamp/matchup.py
from __future__ import annotations

from itertools import combinations

from pokechamp.battle import BattlePokemon, simulate_1v1
from pokechamp.loader import load_team, load_move
from pokechamp.models import (
    MatchupMatrix,
    MatchupResult,
    SelectionScore,
    SetupEvaluation,
    Team,
)


def build_battle_pokemon_from_team(team: Team) -> list[BattlePokemon]:
    """チーム定義からBattlePokemonリストを構築."""
    result = []
    for member in team.pokemon:
        bp = BattlePokemon.from_data(
            species=member.species,
            nature=member.nature,
            evs=member.evs.model_dump(),
            ivs=member.ivs.model_dump(),
            item=member.item,
            move_names=member.moves,
        )
        result.append(bp)
    return result


def _find_setup_moves(bp: BattlePokemon) -> list[str]:
    """積み技を持っているか判定."""
    setup = []
    for move in bp.moves:
        if move.stat_changes:
            setup.append(move.name_en)
    return setup


def evaluate_matchup(
    team_a_name: str,
    team_b_name: str,
    with_setup: bool = True,
    n_trials: int = 1000,
) -> MatchupResult:
    """構築マッチアップを評価."""
    team_a = load_team(team_a_name)
    team_b = load_team(team_b_name)
    bp_a = build_battle_pokemon_from_team(team_a)
    bp_b = build_battle_pokemon_from_team(team_b)

    names_a = [p.name for p in bp_a]
    names_b = [p.name for p in bp_b]

    # 1. 6×6 対面マトリクス
    matrix: list[list[float]] = []
    for pa in bp_a:
        row = []
        for pb in bp_b:
            # 新しいインスタンスで毎回シミュ（ランク補正リセット）
            a_fresh = BattlePokemon.from_data(
                species=pa.name, nature=_infer_nature(pa), evs=_infer_evs(pa),
                ivs={}, item=pa.item, move_names=[m.name_en for m in pa.moves],
            )
            b_fresh = BattlePokemon.from_data(
                species=pb.name, nature=_infer_nature(pb), evs=_infer_evs(pb),
                ivs={}, item=pb.item, move_names=[m.name_en for m in pb.moves],
            )
            result = simulate_1v1(a_fresh, b_fresh, n_trials=n_trials)
            row.append(result.win_rate_a)
        matrix.append(row)

    matchup_matrix = MatchupMatrix(
        team_a_names=names_a, team_b_names=names_b, matrix=matrix,
    )

    # 2. 展開評価
    setup_evals: list[SetupEvaluation] = []
    if with_setup:
        for i, pa in enumerate(bp_a):
            setup_moves = _find_setup_moves(pa)
            for setup_move in setup_moves:
                for j, pb in enumerate(bp_b):
                    base_rate = matrix[i][j]
                    a_setup = BattlePokemon.from_data(
                        species=pa.name, nature=_infer_nature(pa), evs=_infer_evs(pa),
                        ivs={}, item=pa.item, move_names=[m.name_en for m in pa.moves],
                    )
                    b_fresh = BattlePokemon.from_data(
                        species=pb.name, nature=_infer_nature(pb), evs=_infer_evs(pb),
                        ivs={}, item=pb.item, move_names=[m.name_en for m in pb.moves],
                    )
                    setup_result = simulate_1v1(
                        a_setup, b_fresh, setup_move=setup_move, setup_turns=1, n_trials=n_trials,
                    )
                    delta = setup_result.win_rate_a - base_rate
                    if abs(delta) > 0.01:  # 1%以上変化があるもののみ記録
                        setup_evals.append(SetupEvaluation(
                            pokemon=f"{pa.name} vs {pb.name}",
                            move=setup_move,
                            base_win_rate=base_rate,
                            setup_win_rate=setup_result.win_rate_a,
                            delta=delta,
                        ))

    # 3. 選出ランキング
    selection_ranking = _rank_selections(names_a, names_b, matrix)

    # 4. 全体スコア
    flat = [rate for row in matrix for rate in row]
    overall = sum(flat) / len(flat) if flat else 0.5

    return MatchupResult(
        team_a=team_a.name,
        team_b=team_b.name,
        matrix=matchup_matrix,
        setup_evaluations=setup_evals,
        selection_ranking=selection_ranking,
        overall_score=overall,
    )


def _rank_selections(
    names_a: list[str], names_b: list[str], matrix: list[list[float]], top_n: int = 5,
) -> list[SelectionScore]:
    """C(n,3) × C(m,3) の選出組み合わせをスコアリング."""
    idx_a = list(range(len(names_a)))
    idx_b = list(range(len(names_b)))

    # チームが3体未満の場合は全メンバーを選出
    pick_a = min(3, len(idx_a))
    pick_b = min(3, len(idx_b))

    scores: list[SelectionScore] = []
    for sel_a in combinations(idx_a, pick_a):
        for sel_b in combinations(idx_b, pick_b):
            total = 0.0
            count = 0
            for i in sel_a:
                for j in sel_b:
                    total += matrix[i][j]
                    count += 1
            avg = total / count if count > 0 else 0.5
            scores.append(SelectionScore(
                team_a_selection=[names_a[i] for i in sel_a],
                team_b_selection=[names_b[j] for j in sel_b],
                score=avg,
            ))

    scores.sort(key=lambda s: s.score, reverse=True)
    return scores[:top_n]


def _infer_nature(bp: BattlePokemon) -> str:
    """BattlePokemonから性格を推定（簡易: チームから再構築時に使用）."""
    # BattlePokemonは性格情報を直接保持しないため、
    # from_dataで再構築する際はTeamMemberの情報を使う。
    # ここではデフォルトとしてhardyを返すが、実際の運用では
    # TeamMemberから直接構築するのでこの関数は使わない想定。
    from pokechamp.models import Nature
    return Nature.HARDY


def _infer_evs(bp: BattlePokemon) -> dict[str, int]:
    """BattlePokemonから努力値を推定（簡易）."""
    return {}
```

**注意**: `_infer_nature` / `_infer_evs` は暫定実装。Step 5でBattlePokemonにnature/evsを保持させるリファクタリングを行う。

- [ ] **Step 4: テスト実行 — 確認**

Run: `pytest tests/test_matchup.py -v`
Expected: テストが通るか確認。_infer系の問題で落ちる場合はStep 5を先にやる。

- [ ] **Step 5: BattlePokemonにnature/evsを保持させるリファクタリング**

`src/pokechamp/battle.py` の `BattlePokemon` に `nature` と `evs` フィールドを追加:

```python
@dataclass
class BattlePokemon:
    name: str
    types: list[TypeName]
    stats: dict[str, int]
    moves: list[Move]
    item: str
    nature: Nature = Nature.HARDY
    evs: dict[str, int] = field(default_factory=dict)
    stage_modifiers: dict[str, int] = field(default_factory=lambda: {
        "attack": 0, "defense": 0, "sp_attack": 0, "sp_defense": 0, "speed": 0,
    })
```

`from_data` の return に `nature=nature, evs=evs` を追加。

`matchup.py` の `_infer_nature` → `bp.nature` を直接参照、`_infer_evs` → `bp.evs` を直接参照に変更。

- [ ] **Step 6: テスト実行 — 全テスト成功確認**

Run: `pytest -v`
Expected: ALL PASS

- [ ] **Step 7: コミット**

```bash
git add src/pokechamp/matchup.py src/pokechamp/battle.py tests/test_matchup.py
git commit -m "feat: add team matchup evaluation with 6x6 matrix, setup eval, and selection ranking"
```

---

## Task 7: 出力フォーマッタ (output.py)

**Files:**
- Create: `src/pokechamp/output.py`
- Create: `tests/test_output.py`

- [ ] **Step 1: テスト作成**

```python
# tests/test_output.py
import json
from pokechamp.output import format_battle_result, format_matchup_result
from pokechamp.models import BattleResult, MatchupResult, MatchupMatrix, SelectionScore, SetupEvaluation


class TestFormatBattleResult:
    def test_json_output(self):
        result = BattleResult(
            pokemon_a="garchomp", pokemon_b="magikarp",
            win_rate_a=1.0, win_rate_b=0.0,
            avg_remaining_hp_a=184.0, avg_remaining_hp_b=0.0,
        )
        output = format_battle_result(result, as_json=True)
        data = json.loads(output)
        assert data["pokemon_a"] == "garchomp"
        assert data["win_rate_a"] == 1.0

    def test_table_output(self):
        result = BattleResult(
            pokemon_a="garchomp", pokemon_b="magikarp",
            win_rate_a=1.0, win_rate_b=0.0,
            avg_remaining_hp_a=184.0, avg_remaining_hp_b=0.0,
        )
        output = format_battle_result(result, as_json=False)
        assert "garchomp" in output
        assert "100.0%" in output


class TestFormatMatchupResult:
    def test_json_output(self):
        result = MatchupResult(
            team_a="Team A", team_b="Team B",
            matrix=MatchupMatrix(
                team_a_names=["a1"], team_b_names=["b1"], matrix=[[0.75]],
            ),
            setup_evaluations=[],
            selection_ranking=[
                SelectionScore(team_a_selection=["a1"], team_b_selection=["b1"], score=0.75),
            ],
            overall_score=0.75,
        )
        output = format_matchup_result(result, as_json=True)
        data = json.loads(output)
        assert data["overall_score"] == 0.75

    def test_table_output_contains_matrix(self):
        result = MatchupResult(
            team_a="Team A", team_b="Team B",
            matrix=MatchupMatrix(
                team_a_names=["garchomp"], team_b_names=["magikarp"], matrix=[[1.0]],
            ),
            setup_evaluations=[],
            selection_ranking=[],
            overall_score=1.0,
        )
        output = format_matchup_result(result, as_json=False)
        assert "garchomp" in output
        assert "100.0%" in output
```

- [ ] **Step 2: テスト実行 — 失敗確認**

Run: `pytest tests/test_output.py -v`
Expected: FAIL

- [ ] **Step 3: output.py実装**

```python
# src/pokechamp/output.py
from __future__ import annotations

import json

from pokechamp.models import BattleResult, MatchupResult


def format_battle_result(result: BattleResult, as_json: bool = False) -> str:
    if as_json:
        return json.dumps(result.model_dump(), ensure_ascii=False, indent=2)

    lines = [
        f"=== {result.pokemon_a} vs {result.pokemon_b} ===",
        "",
        f"  {result.pokemon_a}: 勝率 {result.win_rate_a * 100:.1f}%  平均残HP {result.avg_remaining_hp_a:.1f}",
        f"  {result.pokemon_b}: 勝率 {result.win_rate_b * 100:.1f}%  平均残HP {result.avg_remaining_hp_b:.1f}",
    ]
    return "\n".join(lines)


def format_matchup_result(result: MatchupResult, as_json: bool = False) -> str:
    if as_json:
        return json.dumps(result.model_dump(), ensure_ascii=False, indent=2)

    lines = [
        f"=== {result.team_a} vs {result.team_b} ===",
        "",
        "【対面マトリクス】(A勝率%)",
    ]

    # ヘッダー行
    name_width = max(len(n) for n in result.matrix.team_a_names + result.matrix.team_b_names) + 2
    header = " " * name_width + "".join(f"{n:>{name_width}}" for n in result.matrix.team_b_names)
    lines.append(header)

    # データ行
    for i, name_a in enumerate(result.matrix.team_a_names):
        row_str = f"{name_a:<{name_width}}"
        for j in range(len(result.matrix.team_b_names)):
            rate = result.matrix.matrix[i][j]
            row_str += f"{rate * 100:>{name_width - 1}.1f}%"
        lines.append(row_str)

    # 展開評価
    if result.setup_evaluations:
        lines.append("")
        lines.append("【展開評価】")
        for se in result.setup_evaluations:
            sign = "+" if se.delta > 0 else ""
            lines.append(
                f"  {se.pokemon} ({se.move}): "
                f"{se.base_win_rate * 100:.1f}% → {se.setup_win_rate * 100:.1f}% "
                f"({sign}{se.delta * 100:.1f}%)"
            )

    # 選出推奨
    if result.selection_ranking:
        lines.append("")
        lines.append("【推奨選出】")
        for rank, sel in enumerate(result.selection_ranking, 1):
            a_str = " / ".join(sel.team_a_selection)
            lines.append(f"  {rank}. {a_str}  スコア: {sel.score * 100:.1f}")

    lines.append("")
    lines.append(f"総合スコア: {result.overall_score * 100:.1f}")

    return "\n".join(lines)
```

- [ ] **Step 4: テスト実行 — 成功確認**

Run: `pytest tests/test_output.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: コミット**

```bash
git add src/pokechamp/output.py tests/test_output.py
git commit -m "feat: add output formatter with table and JSON modes"
```

---

## Task 8: CLIインターフェース (cli.py)

**Files:**
- Create: `src/pokechamp/cli.py`

- [ ] **Step 1: cli.py実装**

```python
# src/pokechamp/cli.py
from __future__ import annotations

from pathlib import Path

import typer

from pokechamp.battle import BattlePokemon, simulate_1v1
from pokechamp.loader import list_pokemon, list_teams, load_pokemon, load_team
from pokechamp.matchup import evaluate_matchup
from pokechamp.models import Nature
from pokechamp.output import format_battle_result, format_matchup_result

app = typer.Typer(help="Pokemon Champions team builder & battle simulator")


@app.command()
def battle(
    pokemon_a: str = typer.Argument(help="1体目のポケモン (species name)"),
    vs: str = typer.Argument(help="'vs' (固定)"),
    pokemon_b: str = typer.Argument(help="2体目のポケモン (species name)"),
    setup: str | None = typer.Option(None, help="積み技名 (例: swords-dance)"),
    setup_turns: int = typer.Option(1, help="積みターン数"),
    nature_a: str = typer.Option("hardy", help="ポケモンAの性格"),
    nature_b: str = typer.Option("hardy", help="ポケモンBの性格"),
    json: bool = typer.Option(False, "--json", help="JSON出力"),
) -> None:
    """1v1対面シミュレーション"""
    poke_a_data = load_pokemon(pokemon_a)
    poke_b_data = load_pokemon(pokemon_b)

    bp_a = BattlePokemon.from_data(
        species=pokemon_a, nature=Nature(nature_a),
        evs={}, ivs={}, item="",
        move_names=poke_a_data.learnable_moves[:4],
    )
    bp_b = BattlePokemon.from_data(
        species=pokemon_b, nature=Nature(nature_b),
        evs={}, ivs={}, item="",
        move_names=poke_b_data.learnable_moves[:4],
    )

    result = simulate_1v1(
        bp_a, bp_b,
        setup_move=setup,
        setup_turns=setup_turns if setup else 0,
    )
    typer.echo(format_battle_result(result, as_json=json))


@app.command()
def matchup(
    team_a: str = typer.Argument(help="チームAのディレクトリ名"),
    vs: str = typer.Argument(help="'vs' (固定)"),
    team_b: str = typer.Argument(help="チームBのディレクトリ名"),
    with_setup: bool = typer.Option(False, "--with-setup", help="展開評価を含める"),
    matrix: bool = typer.Option(False, "--matrix", help="対面マトリクスのみ表示"),
    json: bool = typer.Option(False, "--json", help="JSON出力"),
) -> None:
    """構築マッチアップ評価"""
    result = evaluate_matchup(team_a, team_b, with_setup=with_setup)
    typer.echo(format_matchup_result(result, as_json=json))


@app.command("list")
def list_cmd(
    resource: str = typer.Argument(help="'pokemon' or 'teams'"),
    json: bool = typer.Option(False, "--json", help="JSON出力"),
) -> None:
    """登録済みポケモンまたはチーム一覧"""
    import json as json_mod

    if resource == "pokemon":
        items = list_pokemon()
    elif resource == "teams":
        items = list_teams()
    else:
        typer.echo(f"Unknown resource: {resource}. Use 'pokemon' or 'teams'.", err=True)
        raise typer.Exit(1)

    if json:
        typer.echo(json_mod.dumps(items, ensure_ascii=False, indent=2))
    else:
        for item in items:
            typer.echo(f"  {item}")


@app.command()
def show(
    pokemon: str = typer.Argument(help="ポケモン名 (name_en)"),
    json: bool = typer.Option(False, "--json", help="JSON出力"),
) -> None:
    """ポケモン詳細表示"""
    import json as json_mod
    poke = load_pokemon(pokemon)
    if json:
        typer.echo(json_mod.dumps(poke.model_dump(), ensure_ascii=False, indent=2))
    else:
        typer.echo(f"=== {poke.name} ({poke.name_en}) ===")
        typer.echo(f"タイプ: {', '.join(t.value for t in poke.types)}")
        typer.echo(f"種族値: H{poke.base_stats.hp} A{poke.base_stats.attack} B{poke.base_stats.defense} "
                    f"C{poke.base_stats.sp_attack} D{poke.base_stats.sp_defense} S{poke.base_stats.speed}")
        typer.echo(f"特性: {', '.join(poke.abilities)}")
        typer.echo(f"習得技: {', '.join(poke.learnable_moves)}")


@app.command("import")
def import_cmd(
    gen: int = typer.Option(9, help="世代番号"),
) -> None:
    """PokeAPIからデータインポート（未実装）"""
    typer.echo(f"PokeAPI import for gen {gen} is not yet implemented.")
    typer.echo("Use data/pokemon/*.yaml to add pokemon data manually.")
```

- [ ] **Step 2: CLI動作確認**

```bash
cd /home/deploy/pokemon-champions-lab && source .venv/bin/activate
pokechamp list pokemon
pokechamp show garchomp
pokechamp battle garchomp vs magikarp
pokechamp matchup example-team vs example-team
pokechamp matchup example-team vs example-team --json
```

- [ ] **Step 3: コミット**

```bash
git add src/pokechamp/cli.py
git commit -m "feat: add Typer CLI with battle, matchup, list, show, and import commands"
```

---

## Task 9: PokeAPIインポーター (importer.py)

**Files:**
- Create: `src/pokechamp/importer.py`
- Create: `tests/test_importer.py`

- [ ] **Step 1: テスト作成**

```python
# tests/test_importer.py
import pytest
from pokechamp.importer import parse_pokeapi_pokemon, parse_pokeapi_move


class TestParsePokeAPIPokemon:
    def test_parse_response(self):
        """PokeAPIレスポンス形式からPokemon YAMLデータへの変換"""
        api_response = {
            "name": "garchomp",
            "types": [
                {"type": {"name": "dragon"}},
                {"type": {"name": "ground"}},
            ],
            "stats": [
                {"base_stat": 108, "stat": {"name": "hp"}},
                {"base_stat": 130, "stat": {"name": "attack"}},
                {"base_stat": 95, "stat": {"name": "defense"}},
                {"base_stat": 80, "stat": {"name": "special-attack"}},
                {"base_stat": 85, "stat": {"name": "special-defense"}},
                {"base_stat": 102, "stat": {"name": "speed"}},
            ],
            "abilities": [
                {"ability": {"name": "sand-veil"}},
                {"ability": {"name": "rough-skin"}},
            ],
            "moves": [
                {"move": {"name": "earthquake"}},
                {"move": {"name": "outrage"}},
            ],
        }
        result = parse_pokeapi_pokemon(api_response)
        assert result["name_en"] == "garchomp"
        assert result["base_stats"]["hp"] == 108
        assert result["base_stats"]["sp_attack"] == 80
        assert "ground" in result["types"]
        assert "dragon" in result["types"]


class TestParsePokeAPIMove:
    def test_parse_move(self):
        api_response = {
            "name": "earthquake",
            "type": {"name": "ground"},
            "damage_class": {"name": "physical"},
            "power": 100,
            "accuracy": 100,
            "pp": 10,
            "priority": 0,
            "stat_changes": [],
        }
        result = parse_pokeapi_move(api_response)
        assert result["name_en"] == "earthquake"
        assert result["category"] == "physical"
        assert result["power"] == 100
```

- [ ] **Step 2: テスト実行 — 失敗確認**

Run: `pytest tests/test_importer.py -v`
Expected: FAIL

- [ ] **Step 3: importer.py実装**

```python
# src/pokechamp/importer.py
from __future__ import annotations

from pathlib import Path

import httpx
import yaml

from pokechamp.loader import get_data_dir

POKEAPI_BASE = "https://pokeapi.co/api/v2"

# PokeAPIのステータス名 → 内部名マッピング
_STAT_MAP = {
    "hp": "hp",
    "attack": "attack",
    "defense": "defense",
    "special-attack": "sp_attack",
    "special-defense": "sp_defense",
    "speed": "speed",
}


def parse_pokeapi_pokemon(data: dict) -> dict:
    """PokeAPIのポケモンレスポンスをYAML用dictに変換."""
    types = [t["type"]["name"] for t in data["types"]]
    base_stats = {}
    for stat_entry in data["stats"]:
        api_name = stat_entry["stat"]["name"]
        internal_name = _STAT_MAP.get(api_name, api_name)
        base_stats[internal_name] = stat_entry["base_stat"]

    abilities = [a["ability"]["name"] for a in data["abilities"]]
    moves = [m["move"]["name"] for m in data["moves"]]

    return {
        "name": data["name"],  # 日本語名は別途取得が必要
        "name_en": data["name"],
        "types": types,
        "base_stats": base_stats,
        "abilities": abilities,
        "learnable_moves": moves,
    }


def parse_pokeapi_move(data: dict) -> dict:
    """PokeAPIの技レスポンスをYAML用dictに変換."""
    stat_changes = []
    for sc in data.get("stat_changes", []):
        stat_name = _STAT_MAP.get(sc.get("stat", {}).get("name", ""), "")
        change = sc.get("change", 0)
        if stat_name and change != 0:
            stat_changes.append({"stat": stat_name, "stages": change})

    return {
        "name": data["name"],
        "name_en": data["name"],
        "type": data["type"]["name"],
        "category": data["damage_class"]["name"],
        "power": data.get("power") or 0,
        "accuracy": data.get("accuracy") or 100,
        "pp": data.get("pp") or 1,
        "priority": data.get("priority", 0),
        "effects": [],
        "stat_changes": stat_changes,
    }


async def fetch_pokemon(name: str) -> dict:
    """PokeAPIからポケモンデータを取得."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"{POKEAPI_BASE}/pokemon/{name}")
        resp.raise_for_status()
        return parse_pokeapi_pokemon(resp.json())


async def fetch_move(name: str) -> dict:
    """PokeAPIから技データを取得."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"{POKEAPI_BASE}/move/{name}")
        resp.raise_for_status()
        return parse_pokeapi_move(resp.json())


def save_pokemon_yaml(data: dict) -> Path:
    """ポケモンデータをYAMLファイルに保存."""
    path = get_data_dir() / "pokemon" / f"{data['name_en']}.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        yaml.dump(data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
    return path


def save_move_yaml(data: dict) -> Path:
    """技データをYAMLファイルに保存."""
    path = get_data_dir() / "moves" / f"{data['name_en']}.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        yaml.dump(data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
    return path
```

- [ ] **Step 4: テスト実行 — 成功確認**

Run: `pytest tests/test_importer.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: コミット**

```bash
git add src/pokechamp/importer.py tests/test_importer.py
git commit -m "feat: add PokeAPI importer with response parsing and YAML export"
```

---

## Task 10: 全体テスト・最終調整

**Files:**
- Modify: various

- [ ] **Step 1: 全テスト実行**

Run: `cd /home/deploy/pokemon-champions-lab && source .venv/bin/activate && pytest -v`
Expected: ALL PASS

- [ ] **Step 2: ruffチェック**

Run: `ruff check src/ tests/`
Expected: エラーなし（あれば修正）

- [ ] **Step 3: CLI E2Eテスト**

```bash
pokechamp list pokemon
pokechamp list teams
pokechamp show garchomp
pokechamp show garchomp --json
pokechamp battle garchomp vs magikarp
pokechamp battle garchomp vs magikarp --json
pokechamp battle garchomp vs garchomp --setup swords-dance
pokechamp matchup example-team vs example-team
pokechamp matchup example-team vs example-team --with-setup
pokechamp matchup example-team vs example-team --json
```

- [ ] **Step 4: 修正があればコミット**

```bash
git add -A
git commit -m "fix: address issues found during integration testing"
```

- [ ] **Step 5: 最終コミット — docs更新**

INDEX.mdにplansを追加:

```bash
git add docs/
git commit -m "docs: add implementation plan and update INDEX"
```
