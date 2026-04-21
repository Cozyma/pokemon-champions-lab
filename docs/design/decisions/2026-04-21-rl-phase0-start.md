---
title: RL Phase 0 開始 — リファクタリング・リプレイ収集・模倣学習
description: fast_battle.py分割、Showdownリプレイ収集パイプライン構築、模倣学習Stage 1（74.8%精度）までの開発経緯
tags: [ADR, development-log, RL, imitation-learning, refactoring]
---

# RL Phase 0 開始（2026-04-21）

## 背景

4/17のAI大幅改善セッション後、以下の状態:
- ヒューリスティックAI: メガシンカ判定、Showdownデータ統合、選出AI、回復/壁判断を実装済み
- 全マッチアップ100%決着、244テスト
- fast_battle.py が1,688行に肥大化
- 次のステップとしてRL Phase 0（模倣学習）を計画

## 実装の時系列

### 1. fast_battle.py 分割リファクタリング

1,688行のfast_battle.pyを依存グラフ分析に基づき4モジュールに分割:

| ファイル | 行数 | 責務 |
|---------|------|------|
| `fast_battle.py` | 416 | Showdownプロセス管理 + packed変換 + リエクスポート |
| `ai_decision.py` | 675 | `_choose_action` + 交代/メガ/選出判定 |
| `ai_scoring.py` | 396 | 技スコアリング + ステータス推定 + マッチアップ評価 |
| `log_parser.py` | 323 | ログパース全般 |

依存方向: `log_parser → ai_scoring → ai_decision → fast_battle`（サイクルなし）

後方互換性: fast_battle.pyがリエクスポートを提供し、既存の244テストは変更なしで全PASS。

### 2. Contract-First Integration の教訓適用

4/17の反省（外部システム連携のI/Oダンプ不足）を文書化:
- `docs/design/showdown-request-spec.md` — request JSONの全フィールド仕様書
- `docs/design/decisions/2026-04-17-integration-lessons.md` — DUMP-SPEC-MAP-GAP-TEST原則

### 3. Showdownリプレイ収集

**発見**: Showdown公式のリプレイAPIが完全に動作。チャンピオンズ形式（gen9championsbssregma）のリプレイがレート付きで取得可能。

```
GET https://replay.pokemonshowdown.com/search.json?format=gen9championsbssregma&page=1
GET https://replay.pokemonshowdown.com/{id}.json
```

`scripts/fetch_replays.py`を作成:
- 20ページ×51件をスキャン
- レート1300+でフィルタ
- 個別リプレイログをJSON保存

結果: **193件のレート1300+リプレイ**を取得。最高レート1475。

リプレイログのフォーマットはfast_battle.pyで使っているShowdownプロトコルと完全に同一 — 既存のlog_parser.pyの知見がそのまま活用可能。

### 4. リプレイパーサー

`scripts/parse_replays.py`を作成。リプレイログから(状態, 行動)ペアを抽出:

| 指標 | 値 |
|------|-----|
| 入力 | 193リプレイ |
| 出力 | 3,989サンプル |
| 行動分布 | 技2,718 / メガ技285 / 交代986 |
| 勝者/敗者 | 2,030 / 1,959 |
| エラー | 0 |

各サンプルに含まれる情��:
- Team Preview（自分6体 + 相手6体）
- 選出情報（2種類）:
  - `selected_known`: その時点で判明している選出（不完全情報、Phase 3.5用）
  - `selected_full`: 事後補完した完全��出（模倣学習用）
  - `opp_selected_full`: 相手の完全選出
- アクティブポケモンの種族・HP%
- チーム全体のHP状態
- 天候
- 行動（技名 or 交代先種族名）
- 勝敗結果

**設計判断**: 選出情報を2フィールドに分けた理由:
- Phase 0（模倣学習）: `selected_full`で完全情報のもとで「正しい行動」を教師信号にする
- Phase 3.5（不完全情報）: `selected_known`で「序盤の推定能力」を訓練する

### 5. 模倣学習モデル（Stage 1）

**行動空間の設計判断**:

リプレイには技スロット番号（move 1〜4）の情報がない。技名は分かるが、4技のどの位置かは不明（4技全てが見えるのは6%のインスタンスのみ）。

→ **2段階予測アーキテクチャ**を採用:
- Stage 1: action_type分類（move / switch / mega_move）
- Stage 2: 候補スコアリング（具体的な技/交代先の選択）

**Stage 1の実装** (`src/pokechamp/imitation.py`):

特徴量（69次元）:
- アクティブポケモン: タイプ(18) + 種族値(6) + HP%(1) = 25
- 相手アクティブ: 同上 = 25
- チームHP: 選出3体のHP% = 3
- 相手チームHP: 3
- 天候: 8
- ターン数: 1
- タイプ相性: 攻撃/防御の最大倍率 = 2
- HP差 + チーム残数差 = 2

モデル: GradientBoostingClassifier（scikit-learn）

結果:

| 条件 | 精度 | Move F1 | Switch F1 | Mega F1 |
|------|------|---------|-----------|---------|
| 勝者のみ, 1300+ | 70.4% | 83% | 38% | 14% |
| 勝者のみ, 相性特徴追加 | 72.4% | 84% | 43% | 15% |
| 全プレイヤー, 1200+ | **74.8%** | **84%** | **54%** | **34%** |

サンプル��倍増（1,991→3,948）が精度向上に最も効いた。

## 今後の計画

### Stage 2 実装

Stage 1で「move/switch/mega」を判定した後、具体的な技/交代先を選択するスコアリングモデル:
- 各候補の特徴量（タイプ相性、威力、HP等）を計算
- 候補間のランキングを学習
- ��スロット番号不要 — 候補の特徴量ベースで汎化

### リプレイ追加収集

- ページ数を増やす（20→100）
- レート閾値を下げる（1200+）
- 推定1,000+サンプル追加

### fast_battleベースのGym環境

既存のenv.py（poke-env、15秒/戦）を、fast_battle.py（1秒/戦）ベースに置き換え:
- 観測空間: imitation.pyのencode_stateを流用
- 行動空間: ヒューリスティクスAIの_choose_actionと同じインターフェース
- 報酬: 勝利+1.0 / 敗北-1.0 + 中間報酬

### PPO強化

- ���倣学��モデルで初期方策を設定
- PPOで自己対戦 or ヒューリスティクスAI対戦
- stable-baselines3 or CleanRL

## 数値まとめ

| 指標 | 値 |
|------|-----|
| リファクタリング | 1,688行 → 4ファイル |
| リプレイ収集 | 193件（レート1300+、最高1475） |
| 訓練サンプル | 3,989（3,948使用） |
| Stage 1精度 | 74.8% |
| テスト数 | 244（変更なし） |
