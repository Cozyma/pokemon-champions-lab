---
title: ドキュメント一覧
description: プロジェクトドキュメントの索引。AIエージェントはここを最初に読む。
tags: [index, docs]
---

# ドキュメント一覧

> **AIエージェントへ**: 作業開始前にこのファイルと `POLICY.md` を必ず読んでください。
> ドキュメントの追加・変更時はこの INDEX を更新してください。

## トップレベル

| ファイル | 概要 | タグ |
|---------|------|------|
| [POLICY.md](POLICY.md) | 開発ポリシー（SSOT方針・コミット規約） | policy |
| [guide.md](guide.md) | ユーザーガイド（構築定義・シミュ・考察の進め方） | guide, usage |

## design/ — 設計ドキュメント

| ファイル | 概要 | タグ |
|---------|------|------|
| [pokechamp-design.md](design/pokechamp-design.md) | プロジェクト設計書（データモデル・シミュエンジン・CLI） | design, spec |
| [champions-rules.md](design/champions-rules.md) | ポケモンチャンピ���ンズ固有仕様（本編との差分） | design, rules, champions |
| [pool-m-a-1.md](design/pool-m-a-1.md) | 使用可能プール一覧 M-A-1（ポケモン186種・メガシンカ59形態・アイテム117種） | design, pool, regulation |
| [heuristic-ai-spec.md](design/heuristic-ai-spec.md) | ヒューリスティックAI行動原則（技選択・交代判定・積み判断と改善候補） | design, AI, heuristic |
| [showdown-request-spec.md](design/showdown-request-spec.md) | Showdown Request JSON 仕様書（全フィールド・ログ行・補完要件） | design, showdown, protocol |
| [meta-analysis-reg-ma.md](design/meta-analysis-reg-ma.md) | チャンピオンズ Reg M-A メタ分析（1,092リプレイから使用率・勝率・コア分析） | design, meta, analysis |

### design/decisions/ — ADR（Architecture Decision Records）

| ファイル | 概要 | タグ |
|---------|------|------|
| [_template.md](design/decisions/_template.md) | ADRテンプレート | ADR, template |
| [2026-04-15-initial-development.md](design/decisions/2026-04-15-initial-development.md) | 初期開発経緯（設計判断・実装時系列・フェーズ2→2.5） | ADR, log |
| [2026-04-16-rl-roadmap.md](design/decisions/2026-04-16-rl-roadmap.md) | 強化学習ロードマップ（PPO→Self-Play→選出AI→信念状態→ReBeL） | ADR, RL, roadmap |
| [2026-04-16-showdown-migration-and-ai.md](design/decisions/2026-04-16-showdown-migration-and-ai.md) | Showdown移行・RL環境構築・AI改善の開発経緯 | ADR, log, showdown, AI |
| [2026-04-17-ai-overhaul.md](design/decisions/2026-04-17-ai-overhaul.md) | ヒューリスティックAI大幅改善（メガシンカ・Showdownデータ・選出・回復/壁） | ADR, log, AI, heuristic |
| [2026-04-17-integration-lessons.md](design/decisions/2026-04-17-integration-lessons.md) | 外部プロセス統合の教訓（Contract-First Integration原則） | ADR, lessons-learned, integration |
| [2026-04-21-rl-phase0-start.md](design/decisions/2026-04-21-rl-phase0-start.md) | RL Phase 0開始（リファクタリング・リプレイ収集・模倣学習Stage 1） | ADR, log, RL, imitation-learning |

> 設計判断が発生したら `design/decisions/YYYY-MM-DD-{topic}.md` に記録する。

## plans/ — 実装計画

| ファイル | 概要 | タグ |
|---------|------|------|
| [2026-04-15-pokechamp-implementation.md](plans/2026-04-15-pokechamp-implementation.md) | フェーズ2実装計画（全10タスク） | plan, implementation |

## src/pokechamp/ — 主要モジュール

| ファイル | 概要 |
|---------|------|
| `damage.py` | ダメージ計算エンジン — タイプ相性テーブル(`typechart.json` SSOT)・ステータス計算・ダメージ範囲計算 |
| `damage_calc.py` | ダメージ計算��エリ (`damage_query`) & 逆算推定 (`estimate_attacker`)。フォーム名対応 |
| `env.py` | Gymnasium RL環境 (ChampionsEnv) — バトル状態の観測エンコード・報酬計算 |
| `showdown_data.py` | Showdownデー���JSONローダー — 技・特性・種族値(フォーム別)のAI参照用関数群 |
| `team_converter.py` | チームYAML → Showdown paste 変換 |
| `type_filter.py` | タイプ相性ベース高速フィルタ — 脅威分析・カバー候補提案 (パーティ構築補助) |
