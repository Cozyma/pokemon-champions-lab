# 新規メガシンカ データ収集プロンプト

以下の23体はポケモンチャンピオンズ（Pokemon Champions / Z-A）で初登場したメガシンカです。
PokeAPIには存在しないため、公式情報・攻略サイトから種族値配分を収集してください。

## 調査対象

種族値合計・特性・タイプは判明済み。**各ステータスの配分（H/A/B/C/D/S）** が必要です。

| No. | メガシンカ名 | ベース種族 | 特性 | BST | タイプ |
|-----|------------|-----------|------|-----|--------|
| 37 | メガピクシー | clefable | マジックミラー (magic-bounce) | 583 | fairy |
| 38 | メガウツボット | victreebel | とびだすなかみ (innards-out) | 590 | grass/poison |
| 39 | メガスターミー | starmie | ちからもち (huge-power) | 620 | water/psychic |
| 40 | メガカイリュー | dragonite | マルチスケイル (multiscale) | 700 | dragon/flying |
| 41 | メガメガニウム | meganium | メガソーラー (mega-solar) ※新特性 | 625 | grass |
| 42 | メガオーダイル | feraligatr | ドラゴンスキン (dragon-skin) ※新特性 | 630 | water |
| 43 | メガエアームド | skarmory | すじがねいり (stalwart) | 565 | steel/flying |
| 44 | メガチリーン | chimecho | ふゆう (levitate) | 555 | psychic |
| 45 | メガユキメノコ | froslass | ゆきふらし (snow-warning) | 580 | ice/ghost |
| 46 | メガエンブオー | emboar | かたやぶり (mold-breaker) | 628 | fire/fighting |
| 47 | メガドリュウズ | excadrill | かんつうドリル (piercing-drill) ※新特性 | 608 | ground/steel |
| 48 | メガシャンデラ | chandelure | すりぬけ (infiltrator) | 620 | ghost/fire |
| 49 | メガゴルーグ | golurk | ふかしのこぶし (unseen-fist) | 583 | ground/ghost |
| 50 | メガブリガロン | chesnaught | ぼうだん (bulletproof) | 630 | grass/fighting |
| 51 | メガマフォクシー | delphox | ふゆう (levitate) | 634 | fire/psychic |
| 52 | メガゲッコウガ | greninja | へんげんじざい (protean) | 630 | water/dark |
| 53 | メガフラエッテ(えいえんのはな) | floette-eternal | フェアリーオーラ (fairy-aura) ※新特性 | 651 | fairy |
| 54 | メガニャオニクス♂ | meowstic-male | トレース (trace) | 566 | psychic |
| 55 | メガニャオニクス♀ | meowstic-female | トレース (trace) | 566 | psychic |
| 56 | メガルチャブル | hawlucha | ノーガード (no-guard) | 600 | fighting/flying |
| 57 | メガケケンカニ | crabominable | てつのこぶし (iron-fist) | 578 | fighting/ice |
| 58 | メガジジーロン | drampa | ぎゃくじょう (berserk) | 585 | normal/dragon |
| 59 | メガスコヴィラン | scovillain | とびだすハバネロ (popping-habanero) ※新特性 | 586 | grass/fire |
| 60 | メガキラフロル | glimmora | てきおうりょく (adaptability) | 625 | rock/poison |

## 調査方法

以下のサイトを確認してください（優先順）：

1. **ゲームエイト** — https://game8.jp/pokemon-champions/763000
   「メガシンカ一覧と種族値・特性」ページ
2. **GameWith** — https://gamewith.jp/pokemon-champions/ 内の各ポケモンページ
3. **ポケモン徹底攻略** — https://yakkun.com/ch/
4. **Serebii** — https://www.serebii.net/pokemonchampions/pokemon.shtml

## 回答フォーマット

以下のYAML形式で回答してください。これをそのままスクリプトに食わせます。

```yaml
new_megas:
  - base_species: clefable
    stone: clefable-mega-stone
    stone_ja: ピクシナイト
    types: [fairy]
    ability: magic-bounce
    base_stats:
      hp: ???
      attack: ???
      defense: ???
      sp_attack: ???
      sp_defense: ???
      speed: ???

  - base_species: victreebel
    stone: victreebel-mega-stone
    stone_ja: ウツボットナイト
    types: [grass, poison]
    ability: innards-out
    base_stats:
      hp: ???
      ...
```

## 注意事項

- **HPはメガシンカ前後で変化しない**（ベース種族のHPをそのまま使う）
- 各ステータスの合計が上記BST列と一致することを確認してください
- タイプが変わるメガシンカに注意（例: メガリザードンXは炎/ドラゴン）
- 新特性（太字のもの）は効果も調べてください：
  - **メガソーラー**: 不明（晴れ関連？）
  - **ドラゴンスキン**: 不明（ドラゴンタイプ追加？）
  - **かんつうドリル**: 不明（まもる貫通？）
  - **フェアリーオーラ**: フェアリー技1.33倍？（カロスの伝説特性の流用？）
  - **とびだすハバネロ**: 不明（接触時に反撃ダメージ？）

## 元データのHP値（メガでも不変）

| ベース種族 | HP |
|-----------|-----|
| clefable | 95 |
| victreebel | 80 |
| starmie | 60 |
| dragonite | 91 |
| meganium | 80 |
| feraligatr | 85 |
| skarmory | 65 |
| chimecho | 75 |
| froslass | 70 |
| emboar | 110 |
| excadrill | 110 |
| chandelure | 60 |
| golurk | 89 |
| chesnaught | 88 |
| delphox | 75 |
| greninja | 72 |
| floette-eternal | 74 |
| meowstic-male | 74 |
| meowstic-female | 74 |
| hawlucha | 78 |
| crabominable | 97 |
| drampa | 78 |
| scovillain | 65 |
| glimmora | 83 |
