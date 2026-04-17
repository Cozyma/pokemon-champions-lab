---
title: ヒューリスティックAI大幅改善（2026-04-17）
description: メガシンカ判定、Showdownデータ統合、バグ修正、選出AI、回復/壁判断の一日の開発経緯
tags: [ADR, development-log, AI, heuristic]
---

# ヒューリスティックAI大幅改善（2026-04-17）

## 背景

前日（4/16）にShowdown統合・RL環境構築・ヒューリスティックAI改善を完了。テスト175本。
バトルログ分析で5つのAIバグ（メガシンカ未選択、ねこだまし連打、ステロ重複、PP切れ、タイプ無効技選択）が判明していた。

## 実装の時系列

### Phase 1: メガシンカAI判定

タイプ変化メガ10体 + 特性保持メガ2体（Clefable/Unaware、Venusaur/Chlorophyll）のルックアップテーブルを作成。
`_should_mega_evolve`で被ダメ増/火力減を判定し、`_choose_action`が`move N mega`を送信。

副産物として相手ブーストのログパース（`_parse_opponent_boosts`）と天候パース（`_parse_weather`）も実装。

### Phase 2: AIバグ修正3件

| バグ | 修正 |
|------|------|
| ねこだまし連打 | `_parse_switch_in_turn`でスイッチインターン追跡、直後以外はフィルタ |
| ステロ重複 | `_parse_side_conditions`で相手側の設置状況を確認 |
| PP切れ | `pp not in (0, None)`フィルタ |

### Phase 3: Showdownデータ統合

`scripts/extract_showdown_data.js`でShowdown Dex API（Champions mod適用）から技902件・特性315件・種族1417件をJSON抽出。

`_score_move`を拡張:
- ドレイン技: +回復量×0.5
- 反動技: -反動量×0.75
- 自己デバフ: ペナルティ乗算（C-2蓄積で追加減衰）
- 溜め/反動ターン: ×0.5
- 接触技: 相手特性に応じた段階的ペナルティ
- ひるみ: 先攻時にボーナス
- 状態異常: 確率×効果値のボーナス

技フィルタ拡張:
- であいがしら等のスイッチイン限定技
- 自爆技（残り2体以上&相手HP30%超なら除外）

### Phase 4: 特性データ統合

相手の特性を「ログ確定」と「種族推定」の2段階で取得:
- `|-ability|`行パース
- `|-immune|...|[from] ability:`行パース（Levitate等）
- `|-activate|`行パース（Flash Fire等）
- `[of]`タグで特性の所有者を正しく判別（Rough Skinの誤帰属バグ修正）

AI判断への反映:
| カテゴリ | 確定時 | 推定時 |
|---------|--------|--------|
| 接触反撃 | スコア×0.875 | スコア×0.93 |
| タイプ免疫 | スコア=0 | スコア×0.5 |
| 火力倍化 | 被ダメ×2.0 | 被ダメ×1.5 |

### Phase 5: 速度推定改善

- `_parse_opponent_from_log`で種族値ベースの速度推定を全箇所に統一
- `_parse_move_order`で先手後手実績をログから検出
- 相手が推定より速い場合、Choice Scarf推定（速度×1.5）

### Phase 6: バトルログ分析 → バグ発見・修正

5チームのテストチーム（Levitate/Flash Fire/Huge Power/Contrary/壁）を作成し、全対戦をログ分析。

発見・修正したバグ:

| バグ | 原因 | 修正 |
|------|------|------|
| ステロ連打（再発） | `_parse_side_conditions`が`"move: Stealth Rock"`を返し不一致 | `"move: "`プレフィックス除去 |
| pp=Noneクラッシュ | ShowdownがppをNullで返すケース | Noneハンドリング |
| Draco Meteor連打 | 自己デバフがrequest JSONのboostsに未反映 | `_parse_self_boosts`でログから追跡 |
| かげふみでスタック | trapped error未処理 | request JSONの`trapped`フラグ + errorログ検出 |
| 「It's not your turn」エラー | 不要なコマンド送信 | `wait`リクエストスキップ |
| Mega Sol Solar Beam | 溜め不要特性を未考慮 | `megasol`特性チェック |
| |-immune|後もEQ連打 | Rough Skinの[of]タグで特性誤帰属 | [of]のプレイヤーID判定 |
| Choiceロックで無効技居座り | スコア0でも技選択 | スコア0なら交代 |
| switchInOnly誤判定 | Roost等のcondition.duration=1を誤検出 | hardcoded判定に変更 |
| **全技スコア0（交代ループ）** | request JSONにbasePower/type/category未含有 | Showdownキャッシュから補完 |
| 控えのtypes不明 | request JSONにtypes未含有 | `_get_pokemon_types`でpokedex補完 |

最後の2件が最も深刻で、**全技スコアが0になる**→技を一切撃たず201ターンtieという状態だった。

### Phase 7: 回復技・壁判断

回復技評価:
- HP < 50%、確1されない、回復後に確2圏外 → 回復
- 壁マッチアップ（被ダメ < 回復量）: HP < 70%でも回復

崩せない判定:
- 相手が回復技使用 + 自分の最大スコア < 80 → 交代

交代先の壁ボーナス:
- 被ダメ < 15%HP: マッチアップスコア+1.0
- 被ダメ < 25%HP: マッチアップスコア+0.5

### Phase 8: 選出AI

固定選出（`team 123`）から相性ベース選出に変更:
- 相手6体のタイプを`|poke|`行からパース
- C(6,3)=20通りの選出を攻撃カバー率でスコアリング
- 弱点一貫ペナルティ: 相手1体が3体全員に抜群 → ペナルティ
- 半減ボーナス: 3体の中に半減以下で受けられるポケモン → ボーナス
- 上位3候補から決定的ランダム選択

### Phase 9: チームデータ修正

全12チームの技合法性をShowdown learnsetで検証。6件の違法技を修正:
- Hippowdon: Roost → Slack Off
- Umbreon: Moonblast → Moonlight
- Charizard: Nitro Charge → Flame Charge
- Arcanine: Roost → Extreme Speed
- Volcarona: Roost → Morning Sun
- Meganium: Dragon Pulse → Earth Power
- Garchomp: U-turn → Iron Head

## 数値まとめ

| 指標 | Before | After |
|------|--------|-------|
| コミット数（今日） | 0 | 40 |
| テスト数 | 175 | 244 |
| ソースコード | fast_battle.py 982行 | fast_battle.py 1,688行 + showdown_data.py 288行 |
| Showdownデータ | 未活用 | 902技 + 315特性 + 1,417種族 |
| 全マッチアップ決着率 | 86% (54/63) | **100% (63/63)** |
| 選出 | 固定 (team 123) | 相性ベース (C(6,3)スコアリング) |

## 残課題

| 課題 | 優先度 |
|------|--------|
| fast_battle.py分割リファクタリング（1,688行） | 高 |
| アイテムデータ参照（Step 4） | 中 |
| JSONキャッシュのPP値がChampions変換前 | 低 |
| 1.2xアイテム検出（実測ダメージベース） | 低 |
| 使用率ベース特性推定（ふゆう50%→95%等） | Phase 3.5 |
| RLロードマップ Phase 0 | 次フェーズ |
