---
title: 開発ポリシー
description: SSOT原則・コミット規約の定義
tags: [policy, workflow, SSOT]
---

# 開発ポリシー

## 基本原則: SSOT（Single Source of Truth）

| 区分 | 役割 | 例 |
|------|------|-----|
| **状態（State）** | 正（権威ある情報源） | `docs/`, データモデル定義 |
| **遷移（Transition）** | 作業記録（一時的） | Issue, PR, コミットメッセージ |

- ドキュメントが「今の正」。コードと矛盾したらドキュメントを更新する。

## コミット規約

[Conventional Commits](https://www.conventionalcommits.org/) に準拠:

```
feat: 新機能の説明
fix: バグ修正の説明
docs: ドキュメント変更
chore: 雑務（CI, 依存更新等）
refactor: リファクタリング
test: テストの追加・修正
```

## ドキュメント規約

### フロントマター（必須）

`docs/` 配下の全 `.md` ファイルにYAMLフロントマターを付ける:

```yaml
---
title: ドキュメントタイトル
description: 1行の概要
tags: [タグ1, タグ2]
---
```

### ファイル命名

| 対象 | 規則 | 例 |
|------|------|-----|
| ディレクトリ | 英語 kebab-case | `design/` |
| ファイル | 英語 kebab-case | `pokechamp-design.md` |
| ADR | `YYYY-MM-DD-{topic}.md` | `2026-04-15-greedy-ai.md` |
| 内容 | 日本語 | — |
