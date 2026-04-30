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
| [team-building-analysis.md](design/team-building-analysis.md) | チャンピオンズ Reg M-A 構築分析（1,136リプレイから構築・選出・先発・設置の詳細分析） | design, meta, analysis, team-building |
| [top-team-collection.md](design/top-team-collection.md) | 上位構築コレクション（チャンピオン級/マスター級到達構築+攻略サイト推奨） | design, meta, collection |

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
| [2026-04-22-rl-iteration.md](design/decisions/2026-04-22-rl-iteration.md) | RL訓練イテレーション（MaskablePPO、lr decay、78.6%→83%達成） | ADR, log, RL, PPO |
| [2026-04-23-selection-rl-and-selfplay.md](design/decisions/2026-04-23-selection-rl-and-selfplay.md) | 選出RL実装・Self-Play設計（Body Press修正、選出RL 90%、Gen11 100%） | ADR, log, RL, selection, self-play |
| [2026-04-24-action-theory.md](design/decisions/2026-04-24-action-theory.md) | 行動回数の収支理論と戦略フレーム（サイクル↔起点スペクトラム、リプレイ検証） | ADR, theory, strategy |
| [2026-04-28-team-pool-and-obs-redesign.md](design/decisions/2026-04-28-team-pool-and-obs-redesign.md) | 対戦相手プール拡大(11→32)+観測空間再設計(選出360dim/バトル186dim) | ADR, log, RL, observation |
| [2026-04-28-heuristic-bugfix-and-action-turn.md](design/decisions/2026-04-28-heuristic-bugfix-and-action-turn.md) | ヒューリスティクスバグ修正+行動回数理論で積み判定を統一(49%→63%) | ADR, log, heuristic, action-turn |
| [2026-04-30-heuristic-status-moves.md](design/decisions/2026-04-30-heuristic-status-moves.md) | 状態技(Toxic/回復/Haze)対応+全チーム横断スキャン(71%ベースライン確認) | ADR, log, heuristic, status |
| [2026-04-30-battle-rl-and-quality-metrics.md](design/decisions/2026-04-30-battle-rl-and-quality-metrics.md) | バトルRL再訓練(57%頭打ち)・品質指標導入・報酬設計 | ADR, log, RL, metrics, reward |
| [2026-04-30-obs-move-features-and-reward-issues.md](design/decisions/2026-04-30-obs-move-features-and-reward-issues.md) | 技obsの情報欠落修正(294dim)・報酬設計の課題整理 | ADR, log, RL, obs, reward, open-issues |

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
