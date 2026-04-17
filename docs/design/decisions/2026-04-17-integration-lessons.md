---
title: 外部プロセス統合の教訓（Showdown連携から）
description: Showdown統合で発生したバグ群の根本原因分析と、今後の外部システム連携における事前戦略の提言
tags: [ADR, lessons-learned, integration, showdown]
---

# 外部プロセス統合の教訓（Showdown連携から）

## 経緯

2026-04-16にpokechampの自前バトルエンジンからPokemon Showdownへの移行を決定。判断自体は正しかったが、**統合戦略が不在**のまま実装に入ったことで、4/17に大量のバグが発生した。

## 何が起きたか

4/17のAI改善で発見されたバグの大半は、ShowdownのI/Oプロトコルの誤解に起因:

| バグ | 根本原因 | 事前調査で防げたか |
|------|---------|------------------|
| 全技スコア0 → 201ターンtie | request JSONにbasePower/type/categoryが含まれない | **初回ダンプで即発見** |
| 控えのタイプ不明 → 交代評価不能 | request JSONにtypesが含まれない | **初回ダンプで即発見** |
| 自己デバフ未追跡 → りゅうせいぐん連打 | boostsに技の自己デバフが反映されない | **2ターン観察で発見** |
| かげふみでスタック | trapped フラグの存在を知らなかった | **trapped発生時のダンプで発見** |
| pp=Noneクラッシュ | ppがnullで返されるケースがある | **初回ダンプで発見** |
| switchInOnly誤判定 | Roostのcondition.duration=1を誤解 | Showdownデータ構造の理解不足 |
| ステロ設置済み不一致 | `"move: Stealth Rock"`のプレフィックス | **ログ1行の確認で発見** |
| Rough Skin特性の誤帰属 | `[of]`タグの意味を知らなかった | **ログ仕様の事前把握で防止** |

**11件中8件が、1戦分のI/Oダンプで事前に防止可能だった。**

## 判断のどこが欠けていたか

### 4/16のADRに書かれた内容

```
判断: 自前エンジンの限界 → Showdownをバトルエンジンとして採用
役割分担:
  Showdown = バトルエンジン（完全な技効果・状態異常・交代）
  pokechamp = 分析ツール（構築評価・マッチアップ・パーティビルダー）
```

### 書かれるべきだったが欠けていた内容

```
## 統合戦略

### I/Oプロトコルの把握
- [ ] request JSONの全フィールドをダンプ・文書化
- [ ] バトルログの全行種別を列挙
- [ ] 自前データモデルとのマッピング表を作成

### データ補完方針
- [ ] request JSONに含まれない情報の特定
- [ ] 補完元（Showdownキャッシュ / pokechampデータ / ログパース）の決定

### テスト戦略
- [ ] ユニットテストのmockデータは実request JSONから生成
- [ ] 統合テスト: 実Showdownプロセスとの1戦E2Eを最初に実行
```

## なぜ欠けたか

1. **「ライブラリ導入」と「外部プロセス委譲」の区別がなかった**
   - ライブラリ: 型定義やドキュメントがある。import して使えば動く
   - 外部プロセス: プロトコルの理解が全て。ドキュメントは存在しない場合が多い
   - Showdownは後者だが、前者のように扱ってしまった

2. **「動いているコード」への過信**
   - テストが通っている = 正しい、と暗黙に仮定
   - テストデータが手書き（basePowerを含む）であり、実データと乖離していた
   - 「テストが通る」と「実戦で動く」は別

3. **設計判断の粒度が粗かった**
   - 「Showdownに移行する」は戦略的判断（What）
   - 「Showdownの出力をどう消費するか」は戦術的判断（How）
   - Whatだけ記録してHowをスキップした

## 原則: Contract-First Integration

外部システムと連携する際の手順:

```
1. DUMP — 実I/Oを1件取得してフルダンプ
2. SPEC — 全フィールドを文書化（含まれるもの / 含まれないもの）
3. MAP  — 自分のデータモデルとの対応表を作成
4. GAP  — 補完が必要な情報と補完元を特定
5. TEST — テストデータは実データから生成（手書きしない）
```

これは以下全てに適用される:
- 外部プロセスのstdin/stdout連携（今回のShowdown）
- REST/GraphQL API連携
- データベーススキーマ移行
- RL環境のobservation space設計（次のPhase 0）

## 今後への適用

### RL Phase 0 環境設計

Gymnasium環境のobservation spaceを設計する前に:
1. Showdownの1エピソード分の全request JSONとログを保存
2. 各フィールドの値の範囲・型・欠損パターンを文書化
3. observation vectorの各次元が何のフィールドに対応するかのマッピング表を作成
4. 補完が必要な情報（キャッシュ参照）を明示

### 新しいShowdown modへの対応

Champions modが更新された場合:
1. `scripts/extract_showdown_data.js`を再実行
2. 差分を確認（新技・特性・ポケモン・PP変更等）
3. AI参照テーブル（免疫特性、火力倍化等）に追加が必要か確認

## 成果物

この教訓から生まれた成果物:
- [showdown-request-spec.md](showdown-request-spec.md) — request JSONの全フィールド仕様書
- `data/showdown-cache/` — Showdownデータの事前抽出キャッシュ
- `src/pokechamp/showdown_data.py` — キャッシュ参照のPythonインターフェース
