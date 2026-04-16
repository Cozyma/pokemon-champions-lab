---
title: 強化学習ロードマップ
description: Pokemon Champions対戦AIの学習環境構築から不完全情報ゲーム対応までの段階的計画
tags: [ADR, RL, roadmap]
---

# 強化学習ロードマップ

## 背景

pokechampの構築評価ツールとしての開発を経て、バトルエンジンをPokemon Showdown（チャンピオンズmod実装済み）に移行。poke-env + Gymnasium環境の接続を確立し、RL訓練の基盤が整った。

参考文献: [自己対戦ログで学習したReBeLベースのポケモン対戦ボットで遊ぼう](https://zenn.dev/fufufukakaka/articles/0f9edbb85e5990)

## 現在の構成

```
pokemon-champions-lab/
├── engines/showdown/              # バトルエンジン (Showdown + Champions mod)
│   └── data/mods/champions/       # チャンピオンズ対応 (21,432行、本家マージ済み)
├── src/pokechamp/
│   ├── env.py                     # Gymnasium RL環境 (76次元観測, 9行動)
│   ├── team_converter.py          # team.yaml → Showdown形式
│   ├── battle.py                  # 自前シミュ (分析用、93テスト)
│   ├── matchup.py / sequence.py   # 構築マッチアップ評価
│   └── ...
└── scripts/
    ├── test_poke_env.py           # Showdown接続テスト ✓
    └── test_gym_env.py            # Gymnasium動作テスト ✓
```

## ロードマップ

### Phase 1: シンプルなRL（PPO/DQN）

**目的**: Gymnasium環境で基礎的なRLエージェントを訓練し、ランダムプレイヤーに安定して勝てるようにする。

**やること**:
- stable-baselines3 でPPOエージェントを訓練
- 対戦相手: RandomPlayer → MaxBasePowerPlayer（poke-env組み込み）
- 固定チームで訓練（チーム選択は後）

**観測空間（現在）**: 76次元
- 自分/相手のアクティブポケモン（HP%, タイプ, 状態, ランク補正）
- 技4枠（タイプ, 威力, 命中, PP）
- チームHP%（6体分）
- 天候, フィールド
- 有効行動マスク

**行動空間**: Discrete(9) — 技4択 + 交代5択

**報酬関数（現在）**:
- 勝利: +1.0 / 敗北: -1.0
- 相手ポケモン瀕死: +0.3 / 自分ポケモン瀕死: -0.3
- ターンごとHP差分: ±0.1

**成功基準**: RandomPlayerに勝率80%以上

**見積もり**: 小

---

### Phase 2: Self-Play

**目的**: 自分自身と対戦させることで、固定相手への過学習を防ぎ、汎用的な対戦能力を獲得する。

**やること**:
- poke-envの `battle_against` で2つのエージェントを対戦させる
- 訓練ループ: 現モデル vs 現モデル → 勝敗からモデル更新
- 過去のチェックポイントとも対戦（League Training）
- 複数チームでの訓練（チームプールからランダム選択）

**技術要素**:
- Self-Play用の対戦スケジューラ
- モデルのバージョン管理（チェックポイント保存）
- Elo評価（世代間の強さ推移を追跡）

**成功基準**: Self-Play世代が進むごとにEloが上昇。MaxBasePowerPlayerに勝率90%以上

**見積もり**: 中

---

### Phase 3: 選出AI

**目的**: 6体のチームから対戦に出す3体の選出を学習する。

**やること**:
- 選出フェーズをGymnasium環境に追加（相手チームが見える状態で3体選択）
- pokechampのマッチアップ評価をヒューリスティックとして活用可能
- 選出+対戦を一貫して学習

**参考**: 記事のSelection BERTアプローチ
- BERT（Masked LM）で選出予測を学習
- 上位構築のデータから教師あり学習 → Self-Playで微調整

**チャンピオンズ固有の利点**:
- 選出画面で相手のタイプが見える → 選出判断の情報量が本編より多い
- メガシンカ制約（選出3体中1体まで）が明確なルール

**成功基準**: ランダム選出 vs 学習済み選出で勝率に有意差

**見積もり**: 中

---

### Phase 4: 不完全情報対応（信念状態）

**目的**: 相手の持ち物・技構成・努力値が見えない状況で最適行動を選択する。

**やること**:
- 信念状態（Belief State）の導入
  - 相手ポケモンの「型仮説」を確率分布で管理
  - 観測（技使用、持ち物発動、特性発動）に基づくベイズ更新
- pokechampのポケモンデータ（210体 + 59メガ）を型仮説の事前分布に活用

**ベイズ更新トリガー**:
| 観測 | 更新内容 |
|------|---------|
| 技使用 | その技を覚えない型仮説を除外 |
| 持ち物発動 | 持ち物が確定、他の持ち物仮説を除外 |
| メガシンカ | メガストーン確定、特性・種族値確定 |
| ダメージ量 | 努力値振りの推定 |
| 先制技の有無 | 素早さ関係の推定 |

**チャンピオンズ固有の考慮**:
- EVが0〜32（本編の0〜252より狭い）→ 型仮説の空間が小さい
- アイテムプールが30種+きのみ28種+メガストーン → 本編より推定しやすい

**成功基準**: 信念状態ありvsなしで勝率に有意差

**見積もり**: 大

---

### Phase 5: CFR / ReBeLへの移行

**目的**: 不完全情報ゲームを理論的に最適に解く。

**やること**:
- CFR（Counterfactual Regret Minimization）の実装
  - 各ターンの行動選択を後悔最小化で計算
  - 信念状態に基づくゲームツリー探索
- Value Networkの学習（盤面→勝率の予測）
- ReBeLフレームワーク（CFR + Value Network + Self-Play）

**参考記事のアーキテクチャ**:
```
対戦ループ:
  1. 盤面状態を取得
  2. 信念状態をベイズ更新
  3. CFRで最適戦略を計算（Value Networkで末端評価）
  4. 戦略に従って行動
  5. 対戦結果を記録 → Value Network更新
```

**成功基準**: Self-Play RL（Phase 2）を超える勝率

**見積もり**: 大

---

## 技術的な判断ポイント

### pokechamp（自前シミュ）vs Showdown（バトルエンジン）の役割分担

| 用途 | 使用エンジン |
|------|------------|
| RL訓練 | **Showdown** — 完全な技効果・状態異常・交代処理 |
| 構築考察・マッチアップ分析 | **pokechamp** — 高速な対面評価・選出推奨 |
| 型仮説の事前分布 | **pokechampのデータ** — 210体のYAML + 59メガ |
| チーム定義・管理 | **pokechamp** — team.yaml + team_converter |

pokechampは「分析ツール」として残し、訓練はShowdownで行う。

### 観測空間の拡張予定

| Phase | 追加する観測 |
|-------|------------|
| 1 | 現在の76次元のまま |
| 2 | 相手の過去の行動履歴 |
| 3 | 相手チーム6体の情報（選出フェーズ用） |
| 4 | 信念状態（型仮説の確率分布） |

### チャンピオンズ固有の優位性

本編（SV等）と比較して、チャンピオンズは学習しやすい：
- ポケモンプール186種（本編1000+種より大幅に少ない）
- アイテムプール117種（本編より少ない）
- EV範囲が狭い（0〜32 vs 0〜252）
- 選出画面でタイプ確認可能（情報量が多い）
- シングルバトルのみ（ダブルの複雑さなし）

→ 型仮説の空間が小さく、信念状態の収束が早い。学習環境として理想的。

---

## 参考資料

- [ReBeL: A general game-playing AI bot](https://ai.meta.com/blog/rebel-a-general-game-playing-ai-bot-that-excels-at-poker-and-more/) — Meta AI
- [自己対戦ログで学習したReBeLベースのポケモン対戦ボット](https://zenn.dev/fufufukakaka/articles/0f9edbb85e5990) — fufufukakaka
- [poke-env](https://github.com/hsahovic/poke-env) — Python RL環境
- [Pokemon Showdown](https://github.com/smogon/pokemon-showdown) — バトルエンジン
