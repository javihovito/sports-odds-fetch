#!/usr/bin/env python3
"""
sports-odds-fetch: Fetch live sports betting odds from DraftKings.

Usage:
  python3 fetch-odds.py --sport nba --market series-winner
  python3 fetch-odds.py --sport nba --market series-winner --json-only > odds.json
  python3 fetch-odds.py --url "https://sportsbook-nash.draftkings.com/..."
  python3 fetch-odds.py --file saved-response.json
  python3 fetch-odds.py --sport nba --market series-winner --show-url

Outputs clean JSON to stdout. Human-readable table to stderr.

⚠️ Uses unofficial, publicly available DraftKings endpoints.
    Not affiliated with or endorsed by DraftKings.
    Endpoints may change without notice.
"""

import argparse
import json
import os
import sys
import urllib.request
import urllib.error
import urllib.parse
from datetime import datetime, timezone, timedelta

# ============================================
# DRAFTKINGS ENDPOINT CONFIGURATION
# ============================================

DK_BASE = "https://sportsbook-nash.draftkings.com/sites/US-IL-SB/api/sportscontent/controldata/league/leagueSubcategory/v1/markets"

LEAGUES = {
    "nba": "42648",
    "nfl": "88808",
    "nhl": "42133",
    "mlb": "84240",
}

# Subcategory IDs — these may change between seasons.
# If a fetch returns empty, run endpoint discovery to find the current ID.
# To discover: open DK page in Chrome DevTools > Network > look for subcategory ID in the API URL.
SUBCATEGORIES = {
    "nba": {
        "series-winner": "18082",
        "game-lines": "4511",
    },
    # Discover these during their respective playoffs:
    # "nfl": { "series-winner": "XXXXX" },
    # "nhl": { "series-winner": "XXXXX" },
}


def build_dk_url(league_id: str, subcategory_id: str) -> str:
    """Construct a DraftKings API URL from league and subcategory IDs."""
    params = {
        "isBatchable": "false",
        "templateVars": f"{league_id},{subcategory_id}",
        "eventsQuery": f"$filter=leagueId eq '{league_id}' AND clientMetadata/Subcategories/any(s: s/Id eq '{subcategory_id}')",
        "marketsQuery": f"$filter=clientMetadata/subCategoryId eq '{subcategory_id}' AND tags/all(t: t ne 'SportcastBetBuilder')",
        "include": "Events",
        "entity": "events",
    }
    return f"{DK_BASE}?{urllib.parse.urlencode(params, quote_via=urllib.parse.quote)}"


# ============================================
# ODDS PARSING
# ============================================

def parse_american_odds(odds_str: str) -> int:
    """Parse DK American odds string to integer.
    DK uses Unicode minus (U+2212), not ASCII hyphen (U+002D).
    """
    cleaned = odds_str.replace("\u2212", "-").replace("+", "").strip()
    try:
        return int(cleaned)
    except ValueError:
        return 0


def implied_probability(american: int) -> float:
    if american < 0:
        return abs(american) / (abs(american) + 100)
    elif american > 0:
        return 100 / (american + 100)
    return 0.5


def utc_to_local(utc_str: str) -> str:
    """Convert DK UTC timestamp to the system's local timezone.
    For CLI display only — JSON output keeps raw UTC for frontend conversion.
    """
    try:
        clean = utc_str.split(".")[0]  # strip fractional seconds
        dt_utc = datetime.strptime(clean, "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)
        dt_local = dt_utc.astimezone()
        tz_name = dt_local.strftime("%Z")  # e.g. CDT, EDT, PST
        return dt_local.strftime(f"%Y-%m-%d %I:%M%p {tz_name}").lstrip("0")
    except Exception:
        return utc_str


def parse_dk_response(data: dict) -> list[dict]:
    """Parse a DraftKings API response into clean odds objects."""
    events = {e["id"]: e for e in data.get("events", [])}

    selections_by_market: dict[str, list] = {}
    for sel in data.get("selections", []):
        selections_by_market.setdefault(sel["marketId"], []).append(sel)

    results = []
    for market in data.get("markets", []):
        event = events.get(market.get("eventId"))
        if not event:
            continue

        market_name = market.get("marketType", {}).get("name", market.get("name", "Unknown"))
        sels = selections_by_market.get(market["id"], [])
        if len(sels) < 2:
            continue

        participant_map = {p["id"]: p for p in event.get("participants", [])}
        teams = []
        for sel in sels:
            pid = sel.get("participants", [{}])[0].get("id", "")
            participant = participant_map.get(pid, {})
            metadata = participant.get("metadata", {})
            american = parse_american_odds(sel["displayOdds"]["american"])
            team_data = {
                "name": sel["label"],
                "abbreviation": metadata.get("shortName", ""),
                "color": metadata.get("teamColor", ""),
                "odds": {
                    "american": american,
                    "decimal": sel.get("trueOdds", 0),
                    "display": sel["displayOdds"]["american"],
                    "implied_probability": round(implied_probability(american), 4),
                },
                "is_favorite": american < 0,
            }
            if "points" in sel:
                team_data["points"] = sel["points"]
            teams.append(team_data)

        teams.sort(key=lambda t: t["odds"]["american"])
        start_utc = event.get("startEventDate", "")
        results.append({
            "event_id": event["id"],
            "name": event.get("name", ""),
            "start_time": start_utc,
            "start_time_local": utc_to_local(start_utc),
            "status": event.get("status", ""),
            "market": market_name,
            "teams": teams,
        })
    return results


# ============================================
# FETCH
# ============================================

def fetch_url(url: str) -> dict:
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36",
        "Accept": "*/*",
        "Origin": "https://sportsbook.draftkings.com",
        "Referer": "https://sportsbook.draftkings.com/",
    })
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        print(f"HTTP Error {e.code}: {e.reason}", file=sys.stderr)
        if e.code == 403:
            print("  DraftKings may have changed their API. Run endpoint discovery.", file=sys.stderr)
        sys.exit(1)
    except urllib.error.URLError as e:
        print(f"URL Error: {e.reason}", file=sys.stderr)
        sys.exit(1)


# ============================================
# DISPLAY
# ============================================

def print_table(results: list[dict]):
    if not results:
        print("\nNo odds data found. Possible reasons:", file=sys.stderr)
        print("  - Market not yet available (waiting for play-in/wild card results)", file=sys.stderr)
        print("  - Subcategory ID changed (run endpoint discovery)", file=sys.stderr)
        print("  - Season over / no active series\n", file=sys.stderr)
        return

    print(f"\n{'='*70}", file=sys.stderr)
    print(f"  {len(results)} matchup(s) found", file=sys.stderr)
    print(f"{'='*70}", file=sys.stderr)

    for r in results:
        print(f"\n  {r['name']}", file=sys.stderr)
        time_display = r.get("start_time_local", r['start_time'][:16].replace('T', ' ') + " UTC")
        print(f"  Start: {time_display}  |  {r['status']}", file=sys.stderr)
        print(f"  {'─'*50}", file=sys.stderr)
        for team in r["teams"]:
            odds = team["odds"]
            role = "FAV" if team["is_favorite"] else "DOG"
            prob = f"{odds['implied_probability']:.1%}"
            pts = ""
            if "points" in team:
                p = team["points"]
                pts = f"  ({'+' if p > 0 else ''}{p})"
            print(f"    [{role}] {team['name']:<25} {odds['display']:>8}  ({prob}){pts}", file=sys.stderr)

    print(f"\n{'='*70}\n", file=sys.stderr)


# ============================================
# MAIN
# ============================================

def main():
    parser = argparse.ArgumentParser(description="Fetch live sports odds from DraftKings")
    parser.add_argument("--sport", choices=list(LEAGUES.keys()), help="Sport")
    parser.add_argument("--market", default="series-winner", help="Market type (default: series-winner)")
    parser.add_argument("--url", help="Direct DraftKings API URL override")
    parser.add_argument("--file", help="Parse a local JSON file instead of fetching")
    parser.add_argument("--json-only", action="store_true", help="JSON output only, no table")
    parser.add_argument("--show-url", action="store_true", help="Print constructed URL and exit")
    args = parser.parse_args()

    # Parse local file
    if args.file:
        with open(args.file) as f:
            data = json.load(f)
        results = parse_dk_response(data)
        if not args.json_only:
            print_table(results)
        print(json.dumps(results, indent=2))
        return

    # Determine URL
    url = args.url or os.environ.get("DK_ODDS_ENDPOINT")
    if not url:
        if not args.sport:
            parser.error("Provide --sport, --url, --file, or set DK_ODDS_ENDPOINT env var")
        sport_subcats = SUBCATEGORIES.get(args.sport, {})
        subcat_id = sport_subcats.get(args.market)
        if not subcat_id:
            print(f"Subcategory ID not known for {args.sport}/{args.market}.", file=sys.stderr)
            print(f"Run endpoint discovery (see references/endpoint-discovery.md)", file=sys.stderr)
            sys.exit(1)
        url = build_dk_url(LEAGUES[args.sport], subcat_id)

    if args.show_url:
        print(url)
        return

    # Fetch and parse
    print(f"Fetching: {args.sport or 'custom'} / {args.market}", file=sys.stderr)
    data = fetch_url(url)
    results = parse_dk_response(data)
    if not args.json_only:
        print_table(results)
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
