#!/usr/bin/env python3
"""Analyze team compositions from replay data.

Extracts full 6-pokemon teams from replay logs and analyzes:
- Team archetypes (common 6-pokemon shells)
- Selection rates (which 3 from 6 are chosen)
- Win rates by team and selection
- Co-occurrence matrix (which pokemon appear together)
- Mega usage patterns per team

Usage:
    python3 scripts/analyze_teams.py
    python3 scripts/analyze_teams.py --min-rating 1300
"""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

REPLAY_DIR = Path(__file__).resolve().parent.parent / "data" / "replays"


def extract_team_data(replay: dict) -> list[dict] | None:
    """Extract team + selection + result from a replay."""
    log = replay.get("log", "")
    lines = log.split("\n")

    team_preview: dict[str, list[str]] = {"p1": [], "p2": []}
    selected: dict[str, list[str]] = {"p1": [], "p2": []}
    winner: str | None = None
    player_names: dict[str, str] = {}
    mega_used: dict[str, str | None] = {"p1": None, "p2": None}

    for line in lines:
        # Team preview
        m = re.match(r"\|poke\|(p[12])\|([^,|]+)", line)
        if m:
            team_preview[m.group(1)].append(m.group(2).strip())

        # Player names
        m = re.match(r"\|player\|(p[12])\|(.+?)\|", line)
        if m:
            player_names[m.group(1)] = m.group(2).strip()

        # Switch = selection tracking
        m = re.match(r"\|switch\|(p[12])a: ([^|]+)\|", line)
        if m:
            player = m.group(1)
            species = m.group(2).strip()
            if species not in selected[player]:
                selected[player].append(species)

        # Mega evolution
        m = re.match(r"\|-mega\|(p[12])a: ([^|]+)\|([^|]+)", line)
        if m:
            mega_used[m.group(1)] = m.group(3).strip()

        # Winner
        if line.startswith("|win|"):
            winner_name = line.split("|")[2].strip()
            for pid, pname in player_names.items():
                if pname == winner_name:
                    winner = pid
                    break

    results = []
    for p in ("p1", "p2"):
        if len(team_preview[p]) >= 6 and len(selected[p]) >= 3:
            results.append({
                "team": sorted(team_preview[p]),
                "team_unsorted": team_preview[p],
                "selected": selected[p][:3],
                "mega": mega_used[p],
                "won": winner == p,
                "player": p,
            })
    return results if results else None


def analyze(min_rating: int = 1200) -> None:
    index_path = REPLAY_DIR / "index.json"
    if not index_path.exists():
        # Build index from all replay files
        all_files = sorted(REPLAY_DIR.glob("gen9champions*.json"))
        index = []
        for f in all_files:
            data = json.loads(f.read_text())
            index.append({
                "id": f.stem,
                "rating": data.get("rating", 0),
            })
    else:
        index = json.loads(index_path.read_text())

    # Also load replays not in index but on disk
    indexed_ids = {r["id"] for r in index}
    extra_files = [
        f for f in REPLAY_DIR.glob("gen9champions*.json")
        if f.stem not in indexed_ids
    ]
    for f in extra_files:
        try:
            data = json.loads(f.read_text())
            index.append({
                "id": f.stem,
                "rating": data.get("rating", 0),
            })
        except Exception:
            pass

    filtered = [r for r in index if r.get("rating", 0) >= min_rating]
    print(f"Analyzing {len(filtered)} replays (rating {min_rating}+)...")

    all_teams: list[dict] = []
    errors = 0

    for meta in filtered:
        replay_path = REPLAY_DIR / f"{meta['id']}.json"
        if not replay_path.exists():
            errors += 1
            continue
        try:
            replay = json.loads(replay_path.read_text())
            results = extract_team_data(replay)
            if results:
                for r in results:
                    r["replay_id"] = meta["id"]
                    r["rating"] = meta.get("rating", 0)
                all_teams.extend(results)
        except Exception:
            errors += 1

    print(f"Extracted {len(all_teams)} team records ({errors} errors)\n")

    # === 1. Pokemon usage rate ===
    total_teams = len(all_teams)
    pokemon_count: Counter[str] = Counter()
    for t in all_teams:
        for mon in t["team"]:
            pokemon_count[mon] += 1

    print("=" * 60)
    print("1. ポケモン使用率 TOP 30 (パーティ登録)")
    print("=" * 60)
    for i, (mon, cnt) in enumerate(pokemon_count.most_common(30), 1):
        pct = cnt / total_teams * 100
        print(f"  {i:2d}. {mon:<20s} {pct:5.1f}% ({cnt})")

    # === 2. Selection rate (chosen in 3 when on team) ===
    print(f"\n{'=' * 60}")
    print("2. 選出率 (パーティにいる時に選出される率) TOP 30")
    print("=" * 60)
    on_team: Counter[str] = Counter()
    in_selection: Counter[str] = Counter()
    selected_wins: Counter[str] = Counter()
    selected_total: Counter[str] = Counter()

    for t in all_teams:
        for mon in t["team"]:
            on_team[mon] += 1
        for mon in t["selected"]:
            in_selection[mon] += 1
            selected_total[mon] += 1
            if t["won"]:
                selected_wins[mon] += 1

    selection_rates = {}
    for mon in on_team:
        if on_team[mon] >= 10:
            selection_rates[mon] = in_selection[mon] / on_team[mon]

    sorted_sel = sorted(selection_rates.items(), key=lambda x: -x[1])
    for i, (mon, rate) in enumerate(sorted_sel[:30], 1):
        cnt = on_team[mon]
        sel = in_selection[mon]
        print(f"  {i:2d}. {mon:<20s} {rate*100:5.1f}% ({sel}/{cnt})")

    # === 3. Selection win rate ===
    print(f"\n{'=' * 60}")
    print("3. 選出時勝率 (選出された時の勝率) TOP 30 (n>=20)")
    print("=" * 60)
    sel_winrates = {}
    for mon in selected_total:
        if selected_total[mon] >= 20:
            sel_winrates[mon] = selected_wins[mon] / selected_total[mon]

    sorted_wr = sorted(sel_winrates.items(), key=lambda x: -x[1])
    for i, (mon, wr) in enumerate(sorted_wr[:30], 1):
        n = selected_total[mon]
        print(f"  {i:2d}. {mon:<20s} {wr*100:5.1f}% ({selected_wins[mon]}/{n})")

    # === 4. Co-occurrence (2-pokemon cores on same team) ===
    print(f"\n{'=' * 60}")
    print("4. 同居率 TOP 30 (同じパーティに登録される組み合わせ)")
    print("=" * 60)
    pair_count: Counter[tuple[str, str]] = Counter()
    pair_wins: Counter[tuple[str, str]] = Counter()

    for t in all_teams:
        team = sorted(t["team"])
        for i in range(len(team)):
            for j in range(i + 1, len(team)):
                pair = (team[i], team[j])
                pair_count[pair] += 1
                if t["won"]:
                    pair_wins[pair] += 1

    for i, (pair, cnt) in enumerate(pair_count.most_common(30), 1):
        pct = cnt / total_teams * 100
        wr = pair_wins[pair] / cnt * 100 if cnt > 0 else 0
        print(f"  {i:2d}. {pair[0]:<18s} + {pair[1]:<18s} {pct:5.1f}% ({cnt}) WR={wr:.0f}%")

    # === 5. Mega evolution patterns ===
    print(f"\n{'=' * 60}")
    print("5. メガシンカ使用パターン")
    print("=" * 60)
    mega_count: Counter[str] = Counter()
    mega_wins: Counter[str] = Counter()
    mega_total: Counter[str] = Counter()
    no_mega = 0

    for t in all_teams:
        if t["mega"]:
            mega_count[t["mega"]] += 1
            mega_total[t["mega"]] += 1
            if t["won"]:
                mega_wins[t["mega"]] += 1
        else:
            no_mega += 1

    print(f"  メガシンカなし: {no_mega} ({no_mega/total_teams*100:.1f}%)")
    for i, (mega, cnt) in enumerate(mega_count.most_common(20), 1):
        wr = mega_wins[mega] / mega_total[mega] * 100 if mega_total[mega] > 0 else 0
        print(f"  {i:2d}. Mega {mega:<16s} {cnt:4d} ({cnt/total_teams*100:5.1f}%) WR={wr:.0f}%")

    # === 6. Team shells (3+ pokemon cores) ===
    print(f"\n{'=' * 60}")
    print("6. チーム骨格 (3体以上の頻出コア)")
    print("=" * 60)
    triple_count: Counter[tuple[str, ...]] = Counter()
    triple_wins: Counter[tuple[str, ...]] = Counter()

    for t in all_teams:
        team = sorted(t["team"])
        for i in range(len(team)):
            for j in range(i + 1, len(team)):
                for k in range(j + 1, len(team)):
                    triple = (team[i], team[j], team[k])
                    triple_count[triple] += 1
                    if t["won"]:
                        triple_wins[triple] += 1

    for i, (triple, cnt) in enumerate(triple_count.most_common(20), 1):
        if cnt < 10:
            break
        wr = triple_wins[triple] / cnt * 100 if cnt > 0 else 0
        print(f"  {i:2d}. {' / '.join(triple)}")
        print(f"      {cnt} teams ({cnt/total_teams*100:.1f}%) WR={wr:.0f}%")

    # === 7. Selection patterns (which 3 from 6 given a core) ===
    print(f"\n{'=' * 60}")
    print("7. 選出パターン (頻出選出3体)")
    print("=" * 60)
    selection_pattern: Counter[tuple[str, ...]] = Counter()
    selection_pattern_wins: Counter[tuple[str, ...]] = Counter()

    for t in all_teams:
        sel = tuple(sorted(t["selected"][:3]))
        if len(sel) == 3:
            selection_pattern[sel] += 1
            if t["won"]:
                selection_pattern_wins[sel] += 1

    for i, (sel, cnt) in enumerate(selection_pattern.most_common(20), 1):
        if cnt < 5:
            break
        wr = selection_pattern_wins[sel] / cnt * 100 if cnt > 0 else 0
        print(f"  {i:2d}. {' / '.join(sel)}")
        print(f"      {cnt} times WR={wr:.0f}%")

    # === 8. Lead pokemon ===
    print(f"\n{'=' * 60}")
    print("8. 先発ポケモン TOP 20")
    print("=" * 60)
    lead_count: Counter[str] = Counter()
    lead_wins: Counter[str] = Counter()

    for t in all_teams:
        if t["selected"]:
            lead = t["selected"][0]
            lead_count[lead] += 1
            if t["won"]:
                lead_wins[lead] += 1

    for i, (mon, cnt) in enumerate(lead_count.most_common(20), 1):
        wr = lead_wins[mon] / cnt * 100 if cnt > 0 else 0
        print(f"  {i:2d}. {mon:<20s} {cnt:4d} ({cnt/total_teams*100:5.1f}%) WR={wr:.0f}%")

    # === Summary stats ===
    wins = sum(1 for t in all_teams if t["won"])
    print(f"\n{'=' * 60}")
    print("サマリー")
    print("=" * 60)
    print(f"  チーム数: {total_teams}")
    print(f"  ユニークポケモン: {len(pokemon_count)}")
    print(f"  勝利数: {wins} ({wins/total_teams*100:.1f}%)")
    print(f"  レーティング分布: {min(t['rating'] for t in all_teams)}-{max(t['rating'] for t in all_teams)}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--min-rating", type=int, default=1200)
    args = parser.parse_args()
    analyze(args.min_rating)
