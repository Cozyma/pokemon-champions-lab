---
title: pokechamp ユーザーガイド
description: 構築定義・シミュレーション・考察の進め方
tags: [guide, usage]
---

# pokechamp ユーザーガイド

ポケモンチャンピオンズの構築考察・対面シミュレーションCLIツール。
エージェントからの利用を想定（全コマンドに `--json` 対応）。

---

## クイックスタート

```bash
cd /home/deploy/pokemon-champions-lab
source .venv/bin/activate

# 構築を定義
mkdir teams/my-team
# teams/my-team/team.yaml を作成（下記フォーマット参照）

# 対面シミュ
pokechamp battle my-team garchomp vs my-team dragonite

# 構築マッチアップ
pokechamp matchup my-team vs rival-team

# 展開評価込み
pokechamp matchup my-team vs rival-team --with-setup
```

---

## 構築定義 (team.yaml)

```yaml
name: 構築名
pokemon:
  - species: garchomp         # data/pokemon/ 内のファイル名
    ability: rough-skin        # 使用特性（1つ選択）
    item: choice-scarf         # 持ち物
    nature: jolly              # 性格
    evs:                       # チャンピオンズ式: 各0〜32, 合計66
      hp: 2
      attack: 32
      speed: 32
    moves:                     # 技4つ（data/moves/ 内のファイル名）
      - earthquake
      - outrage
      - iron-head
      - stone-edge

  - species: dragonite
    ability: multiscale
    item: dragonite-mega-stone  # メガストーン持ち → 自動メガシンカ
    nature: modest
    evs: {sp_attack: 32, speed: 32, hp: 2}
    moves: [hurricane, draco-meteor, flamethrower, roost]

  # ... 最大6体
```

### ポイント

- **EVs**: チャンピオンズ仕様。各0〜32、合計66。EV1=実数値1
- **IVs**: 常に31固定（指定不要）
- **メガシンカ**: メガストーンを `item` に指定すれば自動適用。種族値・特性・タイプが変わる
- **メガ制約**: 選出3体中メガは最大1体（matchup評価で自動制約）
- **特性**: ポケモンの所持特性から1つ選択。`pokechamp show <pokemon>` で確認可能

---

## CLIコマンド一覧

### データ参照

```bash
# 登録済みポケモン一覧（210体）
pokechamp list pokemon

# 登録済みチーム一覧
pokechamp list teams

# ポケモン詳細（種族値・特性・習得技）
pokechamp show garchomp
pokechamp show garchomp --json
```

### 1v1 対面シミュレーション

```bash
# 基本: チーム内のポケモン同士
pokechamp battle my-team garchomp vs rival-team dragonite

# インデックス指定（0始まり）
pokechamp battle my-team 0 vs rival-team 2

# 積み技あり（1ターン積んでから殴る）
pokechamp battle my-team garchomp vs rival-team dragonite --setup swords-dance

# JSON出力（エージェント向け）
pokechamp battle my-team garchomp vs rival-team dragonite --json
```

**出力内容:**
- 勝率（A側/B側）
- 平均残HP

### 構築マッチアップ評価

```bash
# 基本: 6×6対面マトリクス + 選出推奨
pokechamp matchup my-team vs rival-team

# 展開評価込み（積み技持ちの勝率変化を分析）
pokechamp matchup my-team vs rival-team --with-setup

# JSON出力
pokechamp matchup my-team vs rival-team --json
```

**出力内容:**
- 対面マトリクス（NxM勝率表）
- 展開評価（積み前後の勝率差分）
- 推奨選出ランキング（上位5件、メガ1体制約付き）
- 総合スコア

---

## シミュレーションの仕組み

### 貪欲AI（フェーズ2）

各ターン、**相手に最も高ダメージの技を選択**して攻撃する。
交代・補助技の判断はしない（フェーズ3以降）。

### 計算精度

| 要素 | 実装状況 |
|------|---------|
| ダメージ計算 | 本編準拠（乱数16段階） |
| タイプ相性 | 18タイプ完全対応 |
| STAB | 1.5倍（てきおうりょくは2.0倍） |
| 性格補正 | 全25性格 |
| 努力値 | チャンピオンズ式（EV1=実数値1） |
| 持ち物 | こだわりスカーフ、タイプ強化18種、きあいのタスキ、たべのこし、オボンのみ |
| メガシンカ | 59形態対応（自動適用） |
| 特性 | 42特性対応（下記参照） |
| 乱数処理 | モンテカルロ（N=1000） |

### 対応特性（42種）

**火力系:**
ちからもち / ヨガパワー / はりきり / てきおうりょく / すいほう /
テクニシャン / ちからずく / がんじょうあご / てつのこぶし / かたいツメ /
メガランチャー / きれあじ

**タイプ変換:**
フェアリースキン / スカイスキン / フリーズスキン / ドラゴンスキン

**HP閾値:**
もうか / しんりょく / げきりゅう / むしのしらせ / ぎゃくじょう

**耐久・軽減:**
ファーコート / あついしぼう / ハードロック / フィルター / きよめのしお /
マルチスケイル / ばけのかわ / がんじょう

**タイプ無効:**
ちょすい / かんそうはだ / ちくでん / ひらいしん / ふゆう / どしょく /
もらいび / ぼうだん / そうしょく / でんきエンジン

**バトル制御:**
いかく / まけんき / かちき / じきゅうりょく / かそく /
かたやぶり / てんねん / さめはだ

### 未対応（フェーズ3以降）

- 交代を含むターン進行
- 天候（晴れ/雨/砂/雪）と天候依存特性
- 状態異常（まひ/やけど/ねむり/こおり/どく）
- 命中率判定
- 補助技・変化技の評価
- へんげんじざい（タイプ変更追跡）
- おやこあい / スキルリンク（複数ヒット）

---

## 構築考察の進め方

### Step 1: 構築のコンセプトを決める

`teams/<team-name>/notes.md` に自由記述：

```markdown
# 構築名

## 戦略方針
- 対面 / 展開 / サイクル

## 基本選出
- vs 受けループ: A / B / C
- vs 積み展開: ...
```

### Step 2: 構築を定義

`teams/<team-name>/team.yaml` にポケモン6体を記述。

### Step 3: 環境の仮想敵を定義

想定される敵構築も `teams/` に定義：

```
teams/
├── my-team/
├── stall-archetype/      # 受けループ想定
├── hyper-offense/        # 積み展開想定
├── balance-standard/     # スタンダード想定
└── mega-lucario-offense/ # メガルカリオ軸想定
```

### Step 4: マッチアップ評価

```bash
pokechamp matchup my-team vs stall-archetype --with-setup
pokechamp matchup my-team vs hyper-offense --with-setup
pokechamp matchup my-team vs balance-standard --with-setup
```

### Step 5: 弱点分析

- 対面マトリクスで勝率が低い対面を特定
- 選出推奨と実際の想定選出を比較
- 展開評価で積みが刺さる/刺さらない相手を確認

### Step 6: 構築調整

- 弱点対面をカバーできるポケモンに入れ替え
- 技構成・持ち物・特性の調整
- 再度マッチアップ評価で改善を確認

---

## データの管理

### ポケモンデータ

```
data/
├── pokemon/     # 210体（PokeAPIインポート済み）
├── moves/       # 技データ（必要に応じて追加）
├── items/       # 持ち物（60個）
└── overrides/   # チャンピオンズ固有の調整差分
```

- PokeAPIからインポート済みだが、チャンピオンズ固有の変更は `data/overrides/` で差分管理
- 技データは使用する技のみ必要（未登録の技を使おうとするとエラー）

### overrides の使い方

```yaml
# data/overrides/iron-head-nerf.yaml
target: moves/iron-head
changes:
  # アイアンヘッドのひるみ率変更（30%→20%）は追加効果なのでフェーズ2では影響なし
  # 将来のために記録のみ
```

### 新しい技を追加する

```yaml
# data/moves/new-move.yaml
name: 技の日本語名
name_en: new-move
type: fire
category: special
power: 90
accuracy: 100
pp: 15
priority: 0
effects: []
stat_changes: []  # 積み技の場合: [{stat: attack, stages: 2}]
```

---

## 参照ドキュメント

| ドキュメント | 内容 |
|------------|------|
| [pokechamp-design.md](design/pokechamp-design.md) | プロジェクト設計書 |
| [champions-rules.md](design/champions-rules.md) | チャンピオンズ固有仕様（EV/IV、状態異常、技変更） |
| [pool-m-a-1.md](design/pool-m-a-1.md) | 使用可能プール一覧（ポケモン・メガシンカ・アイテム） |
| [abilities-phase2.md](plans/2026-04-15-abilities-phase2.md) | 特性実装計画 |
