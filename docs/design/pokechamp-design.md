---
title: Pokemon Champions Lab 設計書
description: 構築考察・対面シミュレーションCLIツールの設計仕様
tags: [design, spec]
---

# Pokemon Champions Lab - 設計書

## 概要

ポケモンチャンピオン（対戦専用プラットフォーム）の構築考察・シミュレーションツール。
自分専用のCLIツールとして構築し、リポジトリクローンで共有可能にする。

## ゴール

- ポケモンの1v1対面シミュレーション（貪欲AI）で勝率を算出する
- 展開（積み技）を考慮したバリエーション評価を行う
- 構築（6体）同士のマッチアップを統計的に評価する
- 構築定義と考察メモを構造的に管理する

## スコープ

### フェーズ2（今回の実装範囲）

- PokeAPIからのベースデータインポート
- ポケチャン独自バランス調整の差分管理（overrides）
- 本編準拠のダメージ計算エンジン
- 1v1対面シミュレーション（貪欲AI: 毎ターン最高ダメージの技を選択）
- 展開評価（積み技Nターン後の勝率変化）
- 構築マッチアップ評価（6×6対面マトリクス + 選出推奨ランキング）
- CLIインターフェース（人間向けテーブル表示 + エージェント向けJSON出力）
- 構築定義（YAML）+ 考察メモ（Markdown）の管理構造

### スコープ外（フェーズ3以降）

- 交代を含むターン進行シミュレーション
- 天候・フィールド・状態異常の継続ダメージ
- 起点作り・壁貼りのターン管理
- 戦略方針（対面/展開/サイクル）の構造化定義
- 基本選出パターンの構造化定義
- WebUI / API

## アーキテクチャ

### プロジェクト構成

```
pokemon-champions-lab/
├── pyproject.toml          # パッケージ定義 (typer, pydantic, pyyaml, httpx)
├── src/
│   └── pokechamp/
│       ├── __init__.py
│       ├── cli.py           # typer CLIエントリポイント
│       ├── models.py        # Pydanticモデル (Pokemon, Move, Team等)
│       ├── damage.py        # ダメージ計算エンジン
│       ├── battle.py        # 1v1対面シミュレーション (貪欲AI + 展開評価)
│       ├── matchup.py       # 構築マッチアップ評価 (6×6 + 選出ランキング)
│       ├── importer.py      # PokeAPIインポート + overrides適用
│       └── output.py        # テーブル表示 / JSON出力
├── data/
│   ├── pokemon/             # ポケモンYAML (1体1ファイル)
│   ├── moves/               # 技YAML (1技1ファイル)
│   ├── abilities/           # 特性YAML
│   ├── items/               # 持ち物YAML
│   └── overrides/           # ポケチャン独自調整の差分YAML
├── teams/                   # 構築定義 + 考察メモ
│   └── example-team/
│       ├── team.yaml
│       └── notes.md
├── tests/
│   ├── test_damage.py
│   ├── test_battle.py
│   └── test_matchup.py
└── docs/
```

### 技術スタック

- **Python 3.12+**
- **Pydantic v2**: データモデル定義・バリデーション
- **PyYAML**: データファイルの読み書き
- **Typer**: CLIフレームワーク
- **httpx**: PokeAPI呼び出し
- **pytest**: テスト

## データモデル

### ポケモン (`data/pokemon/<name>.yaml`)

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
learnable_moves: [earthquake, outrage, swords-dance, scale-shot, iron-head, stone-edge]
```

### 技 (`data/moves/<name>.yaml`)

```yaml
name: じしん
name_en: earthquake
type: ground
category: physical   # physical / special / status
power: 100
accuracy: 100
pp: 10
priority: 0
effects: []          # 追加効果 (将来拡張用)
stat_changes: []     # 積み技の場合: [{stat: attack, stages: 2}]
```

### 特性 (`data/abilities/<name>.yaml`)

```yaml
name: さめはだ
name_en: rough-skin
description: 接触技を受けたとき相手に最大HPの1/8ダメージ
```

### 持ち物 (`data/items/<name>.yaml`)

```yaml
name: こだわりスカーフ
name_en: choice-scarf
effect: speed_multiply
value: 1.5
```

### overrides (`data/overrides/<name>.yaml`)

PokeAPIベースデータとの差分のみ記述。フィールドは部分上書き。

```yaml
target: pokemon/garchomp
changes:
  base_stats:
    attack: 125    # ポケチャンでは130→125に調整された場合
```

### 構築 (`teams/<team-name>/team.yaml`)

```yaml
name: ドラゴン軸サイクル
pokemon:
  - species: garchomp
    ability: rough-skin
    item: choice-scarf
    nature: jolly
    evs: {hp: 4, attack: 252, speed: 252}
    ivs: {hp: 31, attack: 31, defense: 31, sp_attack: 31, sp_defense: 31, speed: 31}  # 省略時は全31
    moves: [earthquake, outrage, iron-head, stone-edge]
  - species: dragapult
    ability: clear-body
    item: life-orb
    nature: timid
    evs: {sp_attack: 252, speed: 252, hp: 4}
    moves: [shadow-ball, draco-meteor, fire-blast, thunderbolt]
  # ... (6体)
```

### 考察メモ (`teams/<team-name>/notes.md`)

自由記述。戦略方針・基本選出・メタ考察を記録。
フェーズ3で構造化フィールドに移行する候補：

- 戦略方針（対面/展開/サイクル）
- 基本選出パターン
- 環境メタ読み

## シミュレーションエンジン

### ダメージ計算 (`damage.py`)

本編準拠のダメージ計算式:

```
damage = floor(floor(floor(2 * level / 5 + 2) * power * A / D) / 50 + 2) * modifier
```

modifier = タイプ一致(1.5) × タイプ相性(0/0.25/0.5/1/2/4) × 乱数(0.85-1.0, 16段階) × その他

実装する補正:
- タイプ一致ボーナス (STAB)
- タイプ相性
- 性格補正 (ステータス計算時)
- 努力値反映
- 持ち物補正 (こだわりハチマキ/メガネ: 1.5倍, いのちのたま: 1.3倍 等)
- 乱数 (0.85〜1.00の16段階)

実装しない補正（フェーズ3以降）:
- 天候・フィールド補正
- 状態異常による攻撃力低下
- 壁（リフレクター/ひかりのかべ）

### 1v1対面シミュレーション (`battle.py`)

```
Input:  ポケモンA(型) vs ポケモンB(型), options: {setup_turns: 0, setup_move: null}
Process:
  1. 実数値計算 (種族値+個体値+努力値+性格)
  2. 先攻判定 (素早さ比較, 先制技の優先度考慮)
  3. 展開ターン (setup_turns > 0 の場合、先に積み技を使用)
  4. 各ターン: 相手に最も高ダメージの技を選択して攻撃
  5. どちらかのHP <= 0 になるまでループ
  6. 乱数処理: 1ターンで決着する対面は16段階全列挙、複数ターンはモンテカルロ(N=1000)で勝率算出
Output: {winner_rate_a: float, winner_rate_b: float, avg_remaining_hp_a: float, avg_remaining_hp_b: float}
```

### 構築マッチアップ評価 (`matchup.py`)

```
Input:  チームA(6体) vs チームB(6体)
Process:
  1. 6×6 = 36通りの1v1対面シミュ → 対面相性マトリクス
  2. 展開評価: 積み技持ちのポケモンについて setup_turns=1 での勝率も算出
  3. 選出候補: C(6,3) × C(6,3) = 400通りの選出組み合わせ
  4. 各選出の相性スコア = 対面マトリクスの勝率合計 (加重平均)
  5. スコア上位の選出をランキング
Output:
  - 対面相性マトリクス (6×6)
  - 展開評価 (積み前後の勝率差分)
  - 選出推奨ランキング (上位5件)
  - 構築全体の相性スコア
```

## CLIインターフェース (`cli.py`)

Typerベース。全コマンドに `--json` フラグでJSON出力対応（エージェント利用を想定）。

### コマンド一覧

| コマンド | 説明 |
|---------|------|
| `pokechamp battle <pokemon_a> vs <pokemon_b>` | 1v1対面シミュ |
| `pokechamp battle <a> vs <b> --setup <move>` | 積み技ありの対面シミュ |
| `pokechamp matchup <team_a> vs <team_b>` | 構築マッチアップ評価 |
| `pokechamp matchup <a> vs <b> --with-setup` | 展開評価込みマッチアップ |
| `pokechamp matchup <a> vs <b> --matrix` | 対面相性マトリクス表示 |
| `pokechamp import --gen <n>` | PokeAPIからデータインポート |
| `pokechamp list pokemon` | 登録済みポケモン一覧 |
| `pokechamp list teams` | 構築一覧 |
| `pokechamp show <pokemon>` | ポケモン詳細表示 |

### 出力形式

- デフォルト: テーブル表示（人間向け）
- `--json`: 構造化JSON出力（エージェント向け）

## テスト方針

- `test_damage.py`: 既知のダメージ計算結果との突合（Smogon計算ツール等を参照）
- `test_battle.py`: 明確に勝敗が決まる対面での正しい判定
- `test_matchup.py`: 小規模な構築（2-3体）でのマトリクス・選出評価

## 将来の拡張（フェーズ3）

- 交代を含むターン進行シミュレーション（ミニマックス or モンテカルロ木探索）
- 天候・フィールド・状態異常の継続効果
- 戦略方針・基本選出の構造化定義（team.yamlへのフィールド追加）
- 対戦ログ記録・分析機能
