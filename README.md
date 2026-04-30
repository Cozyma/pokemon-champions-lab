# Pokemon Champions Lab

**ポケモンチャンピオンズ**の対戦AI開発プロジェクト。ヒューリスティクスAIと強化学習(RL)を組み合わせて、3on3シングルバトル(Reg M-A)で戦えるAIを目指す。

## プロジェクト概要

ポケモンチャンピオンズは対戦専用プラットフォームで、6体持ち込み3体選出のシングルバトル(BSS形式)にメガシンカを加えた独自ルール。このプロジェクトでは:

1. **構築分析ツール** — ダメージ計算、対面シミュ、マッチアップ評価
2. **ヒューリスティクスAI** — タイプ相性・行動回数理論ベースの行動判断
3. **強化学習AI** — PPO(MaskablePPO)による選出・バトル行動の学習

を段階的に開発している。

## アーキテクチャ

```
pokemon-champions-lab/
├── engines/showdown/          # バトルエンジン (Pokemon Showdown + Champions mod)
├── src/pokechamp/
│   ├── fast_env.py            # Gymnasium RL環境 (278dim obs, 9 actions)
│   ├── selection_env.py       # 選出RL環境 (360dim obs, 20 actions)
│   ├── ai_decision.py         # ヒューリスティクスAI (技選択・交代・積み判断)
│   ├── ai_scoring.py          # 技スコアリング・ダメージ推定
│   ├── fast_battle.py         # Showdownサブプロセス管理・バトル実行
│   ├── damage.py              # ダメージ計算エンジン
│   └── showdown_data.py       # 種族値・技・特性データ参照
├── scripts/
│   ├── train_selection.py     # 選出RL訓練 (MaskablePPO)
│   ├── train_longrun.py       # バトルRL訓練
│   ├── train_selfplay.py      # Self-Play訓練
│   ├── fetch_replays.py       # Showdownリプレイ収集
│   └── convert_collection_teams.py  # 上位構築→team.txt変換
├── teams/                     # 32チームの構築データ (Showdown paste形式)
├── models/                    # 訓練済みモデル (.zip)
├── data/
│   ├── replays/               # Showdownリプレイ (~1,340件)
│   └── showdown-cache/        # 種族値・技・特性のJSON
├── docs/
│   ├── design/                # 設計ドキュメント・メタ分析
│   └── design/decisions/      # ADR (Architecture Decision Records)
└── tests/                     # pytest (253テスト)
```

## 開発経緯

### Phase 1-2: 構築分析ツール (4/15)
- PokeAPIからデータインポート、ダメージ計算エンジン、1v1対面シミュ
- チーム定義(YAML/Showdown paste)、マッチアップ評価CLI

### Phase 2.5: Showdown移行 (4/16-17)
- バトルエンジンを自前シミュからPokemon Showdown(Championsmod実装済み)に移行
- Gymnasium RL環境構築、ヒューリスティクスAI初版

### Phase 3: RL訓練 (4/21-23)
- リプレイ収集(1,340件)、模倣学習(82%)
- PPO訓練11世代: 0% → 83% → **100%**(全7チームに完勝)
- 選出RL: ヒューリスティクス64% → **90%**(2,000ステップ)
- Self-Play: Round 1でpolicy forgetting → 中断

### Phase 4: メタ分析・理論構築 (4/22-24)
- 1,136リプレイから使用率・勝率・構築パターンを分析
- **行動回数の収支理論**を定式化: サイクル↔起点スペクトラム
- 上位構築コレクション(R2000-2500の28件)を収集

### Phase 5: 基盤強化 (4/28-30)
- 対戦相手チームプール: 11 → **32チーム**
- 観測空間再設計:
  - 選出obs: 216 → **360dim** (基礎ステ・役割・特性追加)
  - バトルobs: 101 → **278dim** (控え全情報・持ち物・判明技・行動順推測)
- ヒューリスティクスバグ修正5件 + **行動回数理論で積み判定を統一**
- ベースライン: 49% → **71%**

## 主要な技術的判断

### 行動回数の収支理論
全ての行動を「行動回数の収支」で統一的に評価:
- **攻撃**: 相手を倒すまでのターン数(行動回数の消費)
- **積み技**: 1ターン投資 → 以降の効率UP(回収できるなら正の収支)
- **回復**: 自分の行動回数を回復
- **交代**: 有利対面で行動回数を稼ぐ

この理論でヒューリスティクスの積み判定を110行の分岐→70行のスコア計算に簡素化。

### 2モデル分離アーキテクチャ
SB3のMaskablePPOが固定obs/action空間を要求するため:
- **SelectionAgent**: 360dim obs → Discrete(20) [C(6,3)の選出]
- **BattleAgent**: 278dim obs → Discrete(9) [4技+5交代]

### 観測空間の設計思想
「人間が見ている情報と同等の情報をRLに渡す」方針:
- 自チーム: アクティブ(34dim) + 控え2体(74dim) + 技(20dim)
- 相手: アクティブ(36dim) + 判明技(16dim) + チーム6体(48dim)
- 状況: ブースト(14dim) + 天候/テレイン(12dim) + 設置技(6dim)
- 推測材料: 行動順履歴(5dim)

## セットアップ

```bash
# Python 3.12+
git clone https://github.com/Cozyma/pokemon-champions-lab.git
cd pokemon-champions-lab

# 依存インストール
pip install -e ".[dev]"

# Showdownエンジンのセットアップ
cd engines/showdown && npm install && cd ../..

# テスト実行
pytest

# バトル実行(ヒューリスティクス同士)
python -c "
from pokechamp.fast_battle import run_battle
from pathlib import Path
p1 = Path('teams/screenshot-team/team.txt').read_text()
p2 = Path('teams/mega-gengar-team/team.txt').read_text()
result = run_battle(p1, p2)
print(result)
"
```

## 訓練

```bash
# 選出RL訓練
python scripts/train_selection.py --steps 5000

# バトルRL訓練
python scripts/train_longrun.py --timesteps 10000

# Self-Play
python scripts/train_selfplay.py
```

## ドキュメント

- [docs/INDEX.md](docs/INDEX.md) — ドキュメント索引
- [docs/design/pokechamp-design.md](docs/design/pokechamp-design.md) — プロジェクト設計書
- [docs/design/decisions/](docs/design/decisions/) — ADR(設計判断記録)
- [docs/design/top-team-collection.md](docs/design/top-team-collection.md) — 上位構築コレクション
- [docs/design/meta-analysis-reg-ma.md](docs/design/meta-analysis-reg-ma.md) — メタ分析

## 今後のロードマップ

1. **バトルRL再訓練** — 新obs(278dim) + 32チームプールで訓練
2. **Self-Play再挑戦** — 改善ヒューリスティクス + 多様な対戦相手
3. **Showdownラダー実戦投入** — R1200帯での実力測定
4. **使用率データ統合** — 不完全情報の補完、相手の型推測
5. **ReBeL** — 不完全情報ゲームの最適戦略

## 技術スタック

- **Python 3.12+**, Pydantic v2, Typer
- **Pokemon Showdown** (Node.js, Champions mod)
- **Gymnasium** + **Stable-Baselines3** (MaskablePPO)
- **pytest** (253テスト), **ruff**

## License

Private research project.
