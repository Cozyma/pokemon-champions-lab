# CLAUDE.md

## エージェント行動規約

- 作業開始前に `docs/INDEX.md` → `docs/POLICY.md` の順に読むこと
- ドキュメント追加・変更時は `docs/INDEX.md` を必ず更新すること
- 設計判断を下した場合は ADR を `docs/design/decisions/` に作成すること
- SSOT原則: ドキュメントが正。コードと矛盾したらドキュメントを更新する

## 規約の参照先

| 項目 | 参照先 |
|------|--------|
| 開発フロー・コミット・ブランチ規約 | `docs/POLICY.md` |
| プロジェクト設計 | `docs/design/pokechamp-design.md` |

## 品質チェック（コミット前）

```
ruff check src/ && pytest
```

## 技術スタック

- **Language**: Python 3.12+
- **Models**: Pydantic v2
- **CLI**: Typer
- **Data**: PyYAML
- **HTTP**: httpx (PokeAPI)
- **Test**: pytest

## 参照スキル

実装時に以下のスキルを活用すること:

| スキル | 用途 |
|-------|------|
| `python-best-practices` | 型駆動開発、Protocol、dataclassパターン |
| `pytest` | fixtures、parametrize、テスト設計 |
| `python-testing` | TDD、mock、カバレッジ方針 |
| `bobmatnyc/claude-mpm-skills@pydantic` | Pydantic v2ベストプラクティス |
| `narumiruna/agent-skills@python-cli-typer` | Typer CLIパターン |
