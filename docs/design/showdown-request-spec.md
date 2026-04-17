---
title: Showdown Request JSON 仕様書
description: pokemon-showdown simulate-battle が返す |request| JSON の全フィールド仕様。AI・RL環境設計の基盤資料。
tags: [design, showdown, protocol, spec]
---

# Showdown Request JSON 仕様書

`node pokemon-showdown simulate-battle` のstdoutに `|request|{JSON}` として送られるリクエスト。
AIはこのJSONを解析して `>p1 move 1` や `>p1 switch 2` 等のコマンドを返す。

---

## リクエストの種類

| 種類 | 判定フィールド | AIの応答 |
|------|--------------|---------|
| **Team Preview** | `teamPreview: true` | `team 135`（選出する3体を1-indexed） |
| **Normal Turn** | `active` が存在、`forceSwitch`/`wait` なし | `move N` / `move N mega` / `switch N` |
| **Force Switch** | `forceSwitch: [true]` | `switch N` |
| **Wait** | `wait: true` | **応答不要**（相手が先に行動選択中） |

---

## Team Preview リクエスト

```json
{
  "teamPreview": true,
  "maxChosenTeamSize": 3,
  "side": { ... }
}
```

| フィールド | 型 | 説明 |
|-----------|-----|------|
| `teamPreview` | bool | Team Preview フェーズである |
| `maxChosenTeamSize` | int | 選出する体数（チャンピオンズ: 3） |
| `side` | object | 自分のチーム情報（後述） |

相手のチームは `|poke|` 行で確認（後述「バトルログ」参照）。

---

## Normal Turn リクエスト

```json
{
  "active": [{ ... }],
  "side": { ... }
}
```

### active[0] — 場のポケモンの行動選択肢

| フィールド | 型 | 説明 | 注意 |
|-----------|-----|------|------|
| `moves` | array | 選択可能な技リスト | **basePower/type/category を含まない** |
| `canMegaEvo` | bool? | メガシンカ可能か | 存在しない場合もある |
| `trapped` | bool? | 交代不可（かげふみ、溜め技ロック等） | 存在しない場合は交代可能 |

### active[0].moves[N] — 技情報

| フィールド | 型 | 説明 | 注意 |
|-----------|-----|------|------|
| `move` | string | 技の表示名 ("Earthquake") | |
| `id` | string | 技ID ("earthquake") | Showdownデータ参照キー |
| `pp` | int \| null | 残りPP | **nullになる場合がある**（Transform等） |
| `maxpp` | int | 最大PP | チャンピオンズ式 `(base_pp/5+1)*4` 適用済み |
| `target` | string | 対象 ("normal", "self", "allAdjacent" 等) | |
| `disabled` | bool | 使用不可（こだわりロック、アンコール等） | |

**含まれないフィールド**: `basePower`, `type`, `category`, `accuracy`, `priority`, `flags`
→ `data/showdown-cache/moves.json` から `id` で補完が必要。

### Choice ロック時

こだわりアイテム使用後、選択した技以外は `disabled: true` になる:

```json
{
  "moves": [
    {"move": "Earthquake", "id": "earthquake", "disabled": false},
    {"move": "Outrage", "id": "outrage", "disabled": true},
    {"move": "Iron Head", "id": "ironhead", "disabled": true},
    {"move": "Stone Edge", "id": "stoneedge", "disabled": true}
  ]
}
```

### Trapped 時

かげふみ・ありじごく・溜め技ロック中:

```json
{
  "moves": [{"move": "Solar Beam", "id": "solarbeam"}],
  "trapped": true
}
```

溜め技ロック中は `moves` が溜め中の1技のみになる。

---

## side — チーム情報

```json
{
  "name": "p1",
  "id": "p1",
  "pokemon": [...]
}
```

### side.pokemon[N] — 各ポケモン情報

| フィールド | 型 | 説明 | Active | Bench |
|-----------|-----|------|--------|-------|
| `ident` | string | "p1: Garchomp" | ✅ | ✅ |
| `details` | string | "Garchomp, L50, M" / "Garchomp-Mega, L50, M" | ✅ | ✅ |
| `condition` | string | "183/183" / "50/183" / "0 fnt" | ✅ | ✅ |
| `active` | bool | 場に出ているか | true | false |
| `stats` | object | `{atk, def, spa, spd, spe}` 実数値 | ✅ | ✅ |
| `moves` | array | 技ID一覧 `["earthquake", "outrage", ...]` | ✅ | ✅ |
| `baseAbility` | string | 素の特性ID ("roughskin") | ✅ | ✅ |
| `ability` | string | 現在の特性ID（メガ後は変化） | ✅ | ✅ |
| `item` | string | 持ち物ID ("choicescarf") / "" (消費済み) | ✅ | ✅ |
| `pokeball` | string | ボール種 | ✅ | ✅ |
| `commanding` | bool | 指揮状態（シングルでは常にfalse） | ✅ | ✅ |
| `reviving` | bool | 復活待ち（シングルでは常にfalse） | ✅ | ✅ |

**含まれないフィールド:**
- `types` — **タイプ情報なし**。`details` から種族名を抽出して `pokedex.json` で補完が必要
- `boosts` — Team Preview 時は含まれない。Normal Turn でも**技の自己デバフ（りゅうせいぐん等）は反映されない**。ログの `|-boost|`/`|-unboost|` で追跡が必要

### condition の形式

| 値 | 意味 |
|----|------|
| `"183/183"` | HP 183 / 最大183 |
| `"50/183"` | HP 50 / 最大183 |
| `"0 fnt"` | ひんし |
| `"100/183 par"` | HP 100、まひ状態 |
| `"100/183 brn"` | HP 100、やけど状態 |
| `"100/183 slp"` | HP 100、ねむり状態 |
| `"100/183 psn"` | HP 100、どく状態 |
| `"100/183 tox"` | HP 100、もうどく状態 |

### stats の注意点

- **実数値**（種族値+個体値+努力値+性格+レベルの計算済み）
- HPは含まれない（`condition` から取得）
- メガシンカ後は**メガ後の実数値に更新される**
- ランク補正（`boosts`）は **含まれない** — statsは素の実数値

---

## Force Switch リクエスト

```json
{
  "forceSwitch": [true],
  "side": { ... }
}
```

`active` は含まれない。`side.pokemon` から生存している控えを選んで `switch N` を返す。

---

## Wait リクエスト

```json
{
  "wait": true,
  "side": { ... }
}
```

**応答不要。** 相手が先に選択する必要がある場合に送られる。コマンドを送るとエラー。

---

## コマンド形式

| コマンド | 説明 | 例 |
|---------|------|-----|
| `team NNN` | Team Preview 選出 (1-indexed) | `team 135` |
| `move N` | N番目の技を使用 (1-indexed) | `move 1` |
| `move N mega` | N番目の技 + メガシンカ | `move 1 mega` |
| `switch N` | N番目のポケモンに交代 (1-indexed, side.pokemon基準) | `switch 2` |

---

## バトルログの主要行

リクエストとは別に、バトルの経過がstdoutに `|tag|data` 形式で出力される。

### AI判断に使用するログ行

| 行 | 説明 | AIの用途 |
|----|------|---------|
| `\|poke\|p2\|Garchomp, L50, M\|` | Team Preview時の相手チーム | 選出判断 |
| `\|turn\|N` | ターン開始 | ターン追跡 |
| `\|switch\|p2a: Garchomp\|Garchomp, L50, M\|183/183` | 交代 | 相手の種族・HP取得 |
| `\|move\|p1a: Garchomp\|Earthquake\|p2a: Lopunny` | 技使用（先攻→後攻順） | 速度判定 |
| `\|-damage\|p2a: Lopunny\|50/140` | ダメージ | 相手HP更新 |
| `\|-heal\|p2a: Lopunny\|100/140` | 回復 | 相手HP更新 |
| `\|-boost\|p2a: Garchomp\|atk\|2` | 能力上昇 | 相手/自分ブースト追跡 |
| `\|-unboost\|p1a: Dragonite\|spa\|2` | 能力下降 | 自己デバフ追跡 |
| `\|-ability\|p2a: Gyarados\|Intimidate\|boost` | 特性発動 | 相手特性確定 |
| `\|-immune\|p2a: Bronzong\|[from] ability: Levitate` | 特性による無効 | 相手特性確定 |
| `\|-activate\|p2a: Heatran\|ability: Flash Fire` | 特性発動 | 相手特性確定 |
| `\|-sidestart\|p1: p1\|move: Stealth Rock` | サイド状態開始 | 設置技管理 |
| `\|-sideend\|p1: p1\|move: Stealth Rock` | サイド状態終了 | 設置技管理 |
| `\|-weather\|SunnyDay` | 天候変化 | 天候追跡 |
| `\|-mega\|p1a: Lopunny\|Lopunny\|Lopunnite` | メガシンカ実行 | メガ状態追跡 |
| `\|faint\|p2a: Garchomp` | ひんし | 残数管理 |
| `\|win\|p1` | 勝利 | 試合終了 |
| `\|tie\|` | 引き分け | 試合終了 |
| `\|error\|[message]` | エラー | エラーハンドリング |

### ログの注意点

- `|-damage|...|[from] ability: Rough Skin|[of] p1a: Garchomp` — `[of]` は特性の**所有者**。ダメージを受けたポケモン（p2a）ではなく、特性を持つポケモン（p1a）を指す
- `|-sidestart|` のcondition名は `"move: Stealth Rock"` のように `"move: "` プレフィックスが付く場合がある
- `|move|` 行は先攻→後攻の順で出力される（速度判定に利用可能）
- `condition` の状態異常（`par`, `brn` 等）はHP表記の後にスペース区切りで付加される

---

## Showdownキャッシュで補完が必要な情報

| 情報 | request JSON | 補完元 |
|------|-------------|--------|
| 技のbasePower/type/category | ❌ 含まれない | `moves.json` (id検索) |
| ポケモンのタイプ | ❌ 含まれない | `pokedex.json` (種族名検索) |
| 技の自己デバフ（selfBoosts） | ❌ boostsに未反映 | ログ `\|-unboost\|` + `moves.json` |
| 技の追加効果（ひるみ/状態異常） | ❌ 含まれない | `moves.json` |
| 技のフラグ（contact/recharge等） | ❌ 含まれない | `moves.json` |
| 特性の効果分類 | 含まれるが効果不明 | `abilities.json` |
| PP計算式 | maxppは変換済み | ppのbase値は `(pp/5+1)*4` で変換済み |
