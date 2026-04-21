#!/usr/bin/env python3
"""Fetch Pokemon Champions replays from Showdown's replay API.

Usage:
    python scripts/fetch_replays.py --pages 20 --min-rating 1300
    python scripts/fetch_replays.py --pages 50 --min-rating 1200

Output: data/replays/*.json (one file per replay)
Also creates data/replays/index.json with metadata.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "data" / "replays"
FORMAT = "gen9championsbssregma"
SEARCH_URL = f"https://replay.pokemonshowdown.com/search.json?format={FORMAT}"
REPLAY_URL = "https://replay.pokemonshowdown.com"


def curl_json(url: str) -> dict | list | None:
    """Fetch JSON via curl (avoids Python urllib 403 issues)."""
    try:
        result = subprocess.run(
            ["curl", "-s", "--max-time", "10", url],
            capture_output=True, text=True, timeout=15,
        )
        if result.returncode != 0:
            return None
        return json.loads(result.stdout)
    except (subprocess.TimeoutExpired, json.JSONDecodeError):
        return None


def fetch_replay_list(page: int) -> list[dict]:
    """Fetch a page of replay metadata."""
    data = curl_json(f"{SEARCH_URL}&page={page}")
    if isinstance(data, list):
        return data
    return []


def fetch_replay_log(replay_id: str) -> dict | None:
    """Fetch a single replay's full log."""
    data = curl_json(f"{REPLAY_URL}/{replay_id}.json")
    if isinstance(data, dict) and "log" in data:
        return data
    return None


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch Champions replays")
    parser.add_argument("--pages", type=int, default=20, help="Number of search pages to fetch")
    parser.add_argument("--min-rating", type=int, default=1300, help="Minimum rating filter")
    parser.add_argument("--delay", type=float, default=0.5, help="Delay between requests (seconds)")
    args = parser.parse_args()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Phase 1: Collect replay IDs from search
    print(f"Fetching {args.pages} pages of replays (min rating: {args.min_rating})...")
    all_replays: list[dict] = []
    seen_ids: set[str] = set()

    for page in range(1, args.pages + 1):
        results = fetch_replay_list(page)
        if not results:
            print(f"  Page {page}: empty or error, stopping")
            break

        filtered = [
            r for r in results
            if r.get("rating") and r["rating"] >= args.min_rating
            and r["id"] not in seen_ids
        ]
        for r in filtered:
            seen_ids.add(r["id"])
        all_replays.extend(filtered)

        print(f"  Page {page}: {len(results)} total, {len(filtered)} at {args.min_rating}+ rating")
        time.sleep(args.delay)

    print(f"\nFound {len(all_replays)} replays at rating {args.min_rating}+")

    # Phase 2: Download individual replay logs
    print(f"\nDownloading replay logs...")
    downloaded = 0
    skipped = 0
    errors = 0
    index: list[dict] = []

    for i, replay_meta in enumerate(all_replays):
        replay_id = replay_meta["id"]
        out_path = OUTPUT_DIR / f"{replay_id}.json"

        # Skip if already downloaded
        if out_path.exists():
            skipped += 1
            # Still add to index
            index.append({
                "id": replay_id,
                "rating": replay_meta.get("rating"),
                "players": replay_meta.get("players", []),
                "uploadtime": replay_meta.get("uploadtime"),
            })
            continue

        replay_data = fetch_replay_log(replay_id)
        if replay_data:
            out_path.write_text(json.dumps(replay_data))
            downloaded += 1
            index.append({
                "id": replay_id,
                "rating": replay_meta.get("rating"),
                "players": replay_meta.get("players", []),
                "uploadtime": replay_meta.get("uploadtime"),
            })
        else:
            errors += 1

        if (i + 1) % 10 == 0:
            print(f"  {i+1}/{len(all_replays)}: {downloaded} downloaded, {skipped} cached, {errors} errors")

        time.sleep(args.delay)

    # Write index
    index_path = OUTPUT_DIR / "index.json"
    index_path.write_text(json.dumps(index, indent=2))

    print(f"\nDone: {downloaded} downloaded, {skipped} cached, {errors} errors")
    print(f"Total replays: {len(index)}")
    print(f"Index: {index_path}")
    print(f"Replays: {OUTPUT_DIR}/")


if __name__ == "__main__":
    main()
