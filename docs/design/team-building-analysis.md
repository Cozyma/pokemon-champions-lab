---
title: チャンピオンズ Reg M-A 構築分析
description: 1,136件のリプレイから抽出した構築・選出・先発・設置の詳細分析
tags: [design, meta, champions, analysis, team-building]
---

# チャンピオンズ Reg M-A 構築分析

**データソース**: Showdownリプレイ API 1,136件（レート1200-1475）
**分析日**: 2026-04-23
**前提**: 本分析は `docs/design/meta-analysis-reg-ma.md` の使用率・勝率分析を前提とし、構築（パーティ構成・選出・先発・行動シーケンス）に踏み込む。

---

## 1. 鋼枠の構造

### 採用率

- **85%以上のパーティが鋼を1体以上採用**（0体は12-14%）
- **1体が最多（59%）**、2体が25%
- **2体採用がR1300+で勝率53%と最適**。3体はWR25%で過剰

### 鋼枠の棲み分け（R1300+）

| 役割 | ポケモン | 採用率 | 選出率 | 選出WR | 特徴 |
|------|---------|--------|--------|--------|------|
| 主軸アタッカー | Archaludon | 19.1% | **59.0%** | 47.2% | 選出率最高。出す前提 |
| 裏エース | Aegislash | 24.5% | 32.7% | **56.9%** | 採用1位だが選出絞る。出せば勝つ |
| 物理受け | Corviknight | 25.7% | 23.8% | 38.5% | **見せポケ運用が主流** |
| 崩し | Kingambit | 18.3% | 29.1% | **55.9%** | ふいうちの圧力 |
| テクニカル | Scizor | 11.6% | 37.8% | 39.3% | バレパン要員 |
| 格闘複合 | Lucario | 8.2% | 42.3% | 50.0% | メガ込みで安定 |

### 鋼2枚の最適組み合わせ（R1300+）

| 組み合わせ | 採用 | 勝率 | 同時選出率 | 運用 |
|-----------|------|------|-----------|------|
| **Archaludon + Corviknight** | 15 | **73%** | 13% | Corviは見せポケ。Archで殴る |
| **Archaludon + Lucario** | 10 | **70%** | 30% | 攻撃的2鋼 |
| **Corviknight + Scizor** | 9 | **67%** | 0% | 片方のみ。対面使い分け |
| **Corviknight + Kingambit** | 28 | **54%** | 7% | 最多採用。受け+崩し |
| Aegislash + Corviknight | 13 | **23%** | 8% | 最悪。両方受け寄りで火力不足 |

**法則**: 「片方は見せポケ」が基本。Archaludon + 物理鋼が上位独占。

---

## 2. 先発ランキング（R1300+）

### Tier表

| Tier | 先発 | 回数 | 勝率 | 最強T1行動 |
|------|------|------|------|-----------|
| **S** | Meowscarada | 31 | **68%** | Knock Off(83%) |
| **S** | Archaludon | 27 | **63%** | Stealth Rock(80%) |
| **S** | Dragonite | 13 | **62%** | Air Slash(80%) |
| **A** | Venusaur | 15 | **60%** | Sludge Wave(100%) |
| **A** | Sneasler | 14 | **57%** | Close Combat(80%) |
| **A** | Greninja | 41 | **56%** | Taunt(80%) |
| **A** | Rotom | 27 | **56%** | Volt Switch(70%) |
| **B** | Gengar | 20 | **55%** | 択が多い |
| **B** | Garchomp | 56 | **54%** | Rock Tomb(67%) |
| **C** | Glimmora | 30 | **50%** | Stealth Rock(64%) |
| **C** | Hippowdon | 24 | **46%** | Yawn(60%) |
| **D** | Primarina | 31 | **42%** | 先発不向き |
| **D** | Starmie | 17 | **29%** | |

### T1行動の法則

- **猫騙し系は軒並み低勝率**: Lopunny Fake Out(33%)、Sneasler Fake Out(25%)
- **対面操作(U-turn/Volt Switch)が強い**: Meowscarada U-turn(67%)、Rotom Volt Switch(70%)
- **Garchomp先発は最多だが最適ではない**: 56回で54%。MeowscaradaやArchaludonの方が強い

---

## 3. Meowscarada先発の運用

### T1行動優先順位

| T1行動 | 回数 | 勝率 | 狙い |
|--------|------|------|------|
| **Knock Off** | 6 | **83%** | 持ち物破壊。最強T1 |
| **Taunt** | 2 | **100%** | 設置系を止める |
| **U-turn** | 6 | **67%** | 情報取り+エース着地 |
| Flower Trick | 10 | 60% | 確定急所だが次善手 |

### 運用3型

1. **Knock Off → 引き（WR83%）**: 持ち物落として裏の負担軽減
2. **U-turn → 裏エース展開（WR67%）**: Gyarados等のエースを安全着地
3. **Flower Trick即殴り（WR60%）**: 水/地面に刺さるが返しで落ちるリスク

### 交代先

| 交代タイプ | 主な交代先 | 勝率 |
|-----------|-----------|------|
| **U-turn** | Gyarados(75%), Delphox, Polteageist | 60% |
| **通常交代** | Hippowdon(62%), Garchomp(67%), Primarina(100%) | 62% |

**U-turnは攻めの交代（エース着地）、通常交代は守りの交代（受け立て直し）**。

---

## 4. Garchomp先発の運用

### 全体: 127試合 WR45%（先発としては弱い）

| パターン | 割合 | 勝率 |
|---------|------|------|
| 即攻撃 | 50% | 43% |
| ステロ始動 | 25% | 47% |
| 即引き | 21% | 41% |

### 二重設置型（SR+Spikes）が最強

R1300+ **7試合 WR71%**。通常型(54%)より大幅に高い。

```
確定技: Stealth Rock / Spikes / Dragon Tail
行動: T1 SR → T2 Spikes → T3+ Dragon Tail流し → T3-4退場OK
```

| シーケンス | 勝率 |
|-----------|------|
| SR → Spikes（2層完了で退場） | **100%** |
| SR → Spikes → Dragon Tail | **67%** |
| SR → EQ（殴り） | **33%** |

**「ステロ1枚で殴りに行く」は中途半端。設置マシンか即退場の二択。**

---

## 5. Archaludon構築

### 先発WR61%。2型に分かれる

| 型 | T1行動 | 狙い |
|----|--------|------|
| **アタッカー型** | Flash Cannon / Draco Meteor | 有利対面で即殴り |
| **起点型** | Stealth Rock(WR80%) | 設置後Dragon Tail流し |

### 対面別の確定行動

| 対面 | 行動 | 理由 |
|------|------|------|
| vs Glimmora | Flash Cannon | 鋼抜群 |
| vs Garchomp | Draco Meteor | ドラゴン同士 |
| vs Bellibolt | Draco Meteor(9/11) | ほぼ確定 |
| vs Clefable | Flash Cannon(10/11) | 鋼でフェアリー処理 |

### 高勝率パートナー

| パートナー | 同居 | 勝率 |
|-----------|------|------|
| Corviknight | 22 | **68%** |
| Kangaskhan | 27 | **63%** |
| Primarina | 46 | **57%** |
| Dragonite | 23 | **57%** |

**避けるべき**: Hydreigon(32%), Meganium(41%), Delphox(40%)

---

## 6. Meowscarada + Gyarados コア

### 29チーム WR72%（R1300+: 13試合 WR77%）

| 役割 | Meowscarada | Gyarados |
|------|------------|---------|
| 選出率 | 38% | 55% |
| 役割 | 削り+情報収集 | **Mega竜舞エース** |
| Mega | — | **88%使用** |

**両方選出は24%のみ。片方をメタに合わせて出す柔軟性が強み。**

### 最強テンプレート（Keyan_Sans: 3戦全勝）

```
Meowscarada  — Knock Off / U-turn / Flower Trick / Play Rough
Gyarados     — [Mega] Dragon Dance / Waterfall / Crunch / EQ
Gengar       — [Mega択②] Shadow Ball / Hypnosis / ...
Primarina    — Calm Mind / Moonblast / Sparkling Aria / ...
Aegislash    — King's Shield / Shadow Sneak / ...
Garchomp     — Stealth Rock / EQ / Rock Tomb / ...
```

---

## 7. メガシンカ勝率ランキング（R1300+）

| メガ | 回数 | 勝率 |
|------|------|------|
| **Mega Dragonite** | 24 | **62%** |
| **Mega Kangaskhan** | 28 | **57%** |
| **Mega Charizard** | 52 | **56%** |
| Mega Venusaur | 23 | 43% |
| Mega Gengar | 42 | 43% |
| Mega Gyarados | 24 | 46% |
| Mega Lopunny | 20 | **30%** |
| Mega Scizor | 20 | **25%** |
| **Mega Meganium** | 20 | **10%** |

---

## 8. 高レートプレイヤーの構築

### TOP 3

| # | プレイヤー | 試合 | 勝率 | 最高R | 構築スタイル |
|---|-----------|------|------|-------|------------|
| 1 | 4jyoudebu | 10 | 60% | **1513** | Garchomp設置 → Mega Dragonite |
| 2 | karbain | 55 | 53% | **1509** | Greninja先発 → Mega Charizard |
| 3 | DiceyRice | 18 | **78%** | **1505** | Hippowdon起点 → Mega Floette/Blastoise |

### DiceyRice構築（WR90%, 10試合9勝）

```
Hippowdon / Aegislash / Floette-Eternal / Blastoise / Hydreigon / Volcarona
メガ択: Floette(5) vs Blastoise(4)
先発: Hippowdon(7/10)
```

環境と全く被らない独自路線で最高勝率。

### Keyan_Sans構築（WR100%, 9連勝）

```
Gyarados / Aegislash / Garchomp / Meowscarada / Gengar / Primarina
メガ択: Gyarados(5) vs Gengar(2)
先発: Meowscarada(5/9)
```

### karbain最強版（WR80%, 5試合）

```
Aegislash / Charizard / Gengar / Greninja / Meowscarada / Mimikyu
メガ: Mega Charizard(4)
先発: Greninja(5/5)
```

**共通点: 高勝率構築は全てAegislashを採用している。**

---

## 9. 設置技担当の比較

### 設置役Tier（R1300+）

| Tier | 設置役 | 試合 | 勝率 | 設置技 | 特徴 |
|------|--------|------|------|--------|------|
| **S** | Samurott | 6 | **83%** | Ceaseless Edge | 攻撃と設置を兼ねる |
| **S** | Archaludon | 15 | **67%** | Stealth Rock | 設置後そのまま殴れる |
| **A** | Glimmora | 21 | **62%** | Stealth Rock | 先発専用（先発率100%） |
| **B** | Garchomp | 43 | 53% | SR + Spikes | 2層時WR71%。1層は平凡 |
| **B** | Hippowdon | 39 | 49% | Stealth Rock | あくび併用 |
| **C** | Kleavor | 16 | 44% | Stone Axe | 弱い |

### 設置役 × メガエース 最適組み合わせ

| 組み合わせ | 回数 | 勝率 |
|-----------|------|------|
| **Garchomp → Mega Kangaskhan** | 3 | **100%** |
| **Samurott → Mega Froslass** | 3 | **100%** |
| **Glimmora → Mega Clefable** | 3 | **100%** |
| **Glimmora → Mega Dragonite** | 5 | **80%** |
| **Garchomp → Mega Gengar** | 7 | **71%** |
| Hippowdon → Mega Charizard | 9 | 56% |

### 設置技の種類数

| 種類 | 割合 | 勝率 |
|------|------|------|
| 1種（ステロのみ） | 95% | 50% |
| **2種（SR+Spikes等）** | 5% | **61%** |

---

## 10. Mega Floette 対策

### Floette勝率48%。倒せるかが分岐点

| 状態 | Floette側WR |
|------|-----------|
| Floette生存 | **71%** |
| Floette撃破 | **20%** |

### 有効な対策

| 優先度 | 対策 | ポケモン |
|--------|------|---------|
| **S** | 炎特殊で積み返す | **Skeledirge**(Torch Song) |
| **S** | 毒技で弱点 | **Mega Venusaur**(Sludge Bomb) |
| **A** | Encoreで積みロック | Primarina, Samurott |
| **A** | ゴースト高火力 | Aegislash(Poltergeist) |
| **×** | 物理積みエース | Swords Dance系 → Charmで完封される |

---

## 11. Mega Venusaur

### R1300+: 選出率56%・勝率56%

| 強み | 詳細 |
|------|------|
| カバレッジ | Earth Power/Giga Drain/Sludge Bomb/Synthesis |
| Floette完封 | Sludge Bomb 7/9で即殴り |
| 耐久 | あついしぼう+Synthesis。85%が生存 |

### 対面確定行動

| 対面 | 技 |
|------|-----|
| vs Garchomp | **Giga Drain(10/11)** 草4倍 |
| vs Aegislash | **Earth Power(10/17)** 地面弱点 |
| vs Floette | **Sludge Bomb(7/9)** 毒確殺 |

### 最適運用

Mega択のもう一方（Gyarados/Dragonite等）と共存させ、相手にFloette/水/地面が多い時だけMega Venusaurを出す。**先発固定は非推奨**。

---

## 12. R1200+ vs R1300+ の差分

### 勝率が変わる構築軸

| コア | R1200+ | R1300+ |
|------|--------|--------|
| Aegislash+Garchomp+Primarina | 55% | **70%** |
| Garchomp+Kangaskhan+Primarina | — | **62%** |
| Archaludon+Garchomp | 41% | **62%** |

### 選出時勝率の逆転

| ポケモン | R1200+ | R1300+ |
|---------|--------|--------|
| **Kingambit** | 45.2% | **58.3%** |
| **Charizard** | 43.9% | **58.0%** |
| **Meowscarada** | 44.6% | **55.3%** |
| Clefable | 43.5% | 38.1%（対策される） |

---

## 13. 構築テンプレート

### テンプレートA: 設置+Mega Dragonite（4jyoudebu型）

```
Garchomp     — SR / Spikes / Dragon Tail / EQ
Dragonite    — [Mega] Air Slash / Flamethrower / Draco Meteor / Extreme Speed
Skeledirge   — Torch Song / Yawn / Slack Off / ...
Meowscarada  — Knock Off / U-turn / Flower Trick / Play Rough
Aegislash    — King's Shield / Shadow Sneak / Poltergeist / ...
Primarina    — Calm Mind / Moonblast / Sparkling Aria / ...
```

### テンプレートB: Meowscarada+Mega Gyarados（Keyan_Sans型）

```
Meowscarada  — Knock Off / U-turn / Flower Trick / Play Rough
Gyarados     — [Mega①] Dragon Dance / Waterfall / Crunch / EQ
Gengar       — [Mega②] Shadow Ball / Hypnosis / ...
Garchomp     — Stealth Rock / EQ / Rock Tomb / ...
Aegislash    — King's Shield / Shadow Sneak / ...
Primarina    — Calm Mind / Moonblast / Sparkling Aria / ...
```

### テンプレートC: 耐久設置（DiceyRice型）

```
Hippowdon    — Stealth Rock / Yawn / EQ / ...
Floette      — [Mega①] Calm Mind / Draining Kiss / Moonblast / Synthesis
Blastoise    — [Mega②] Shell Smash / ...
Aegislash    — King's Shield / Shadow Sneak / ...
Hydreigon    — Dark Pulse / U-turn / ...
Volcarona    — Quiver Dance / Fiery Dance / ...（保険枠）
```

### テンプレートD: Greninja先発（karbain型）

```
Greninja     — Surf / Taunt / Dark Pulse / ...
Charizard    — [Mega] Flamethrower / ...
Meowscarada  — Knock Off / U-turn / ...
Aegislash    — King's Shield / Shadow Sneak / ...
Mimikyu      — Swords Dance / Shadow Sneak / Play Rough / ...
Gengar       — Shadow Ball / ...
```
