#!/usr/bin/env python3
"""
sports-odds-fetch: Fetch live sports betting odds from DraftKings.

Usage:
  python3 fetch-odds.py --sport nba --market series-winner
  python3 fetch-odds.py --sport nba --market series-winner --json-only > odds.json
  python3 fetch-odds.py --url "https://sportsbook-nash.draftkings.com/..."
  python3 fetch-odds.py --file saved-response.json
  python3 fetch-odds.py --sport nba --market series-winner --show-url
  python3 fetch-odds.py --source oddsapi --sport nfl --market game-lines
  python3 fetch-odds.py --source oddsapi --sport nba --min-ev 1.5 --sharp pinnacle

--source oddsapi uses The Odds API (multi-book, works from cloud IPs).
Needs ODDS_API_KEY env var (free key: https://the-odds-api.com).

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


def american_to_decimal(american: int) -> float:
    if american < 0:
        return 1 + 100 / abs(american)
    return 1 + american / 100


def prob_to_american(prob: float) -> int:
    if prob <= 0 or prob >= 1:
        return 0
    if prob >= 0.5:
        return round(-100 * prob / (1 - prob))
    return round(100 * (1 - prob) / prob)


def no_vig(probs: list[float]) -> list[float]:
    """Remove the vig by normalizing implied probabilities to sum to 1."""
    total = sum(probs)
    return [p / total for p in probs] if total > 0 else probs


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
            if american == 0:
                continue  # suspended/unparseable price
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

        if len(teams) < 2:
            continue
        fair = no_vig([t["odds"]["implied_probability"] for t in teams])
        for t, fp in zip(teams, fair):
            t["odds"]["fair_probability"] = round(fp, 4)
            t["odds"]["fair_american"] = prob_to_american(fp)
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
# THE ODDS API (multi-book line shopping)
# ============================================

ODDS_API_BASE = "https://api.the-odds-api.com/v4/sports"

ODDS_API_SPORTS = {
    "nba": "basketball_nba",
    "nfl": "americanfootball_nfl",
    "nhl": "icehockey_nhl",
    "mlb": "baseball_mlb",
    "ncaaf": "americanfootball_ncaaf",
    "ncaab": "basketball_ncaab",
}

ODDS_API_MARKETS = {
    "game-lines": "h2h,spreads,totals",
    "moneyline": "h2h",
    "spreads": "spreads",
    "totals": "totals",
    "futures": "outrights",
}


def build_oddsapi_url(sport: str, market: str, api_key: str, regions: str) -> str:
    sport_key = ODDS_API_SPORTS[sport]
    markets = ODDS_API_MARKETS.get(market, market)
    if markets == "outrights":
        # Futures live under their own sport key, e.g. basketball_nba_championship_winner
        sport_key = f"{sport_key}_championship_winner"
        markets = "outrights"
    params = {
        "apiKey": api_key,
        "regions": regions,
        "markets": markets,
        "oddsFormat": "american",
    }
    return f"{ODDS_API_BASE}/{sport_key}/odds?{urllib.parse.urlencode(params)}"


def _median(xs: list[float]) -> float:
    xs = sorted(xs)
    n = len(xs)
    return xs[n // 2] if n % 2 else (xs[n // 2 - 1] + xs[n // 2]) / 2


def parse_oddsapi_response(data: list, sharp: str | None = None, books: set[str] | None = None) -> list[dict]:
    """Shop lines across books for each event/market.

    For each outcome: best price (and which book), no-vig fair probability, and EV% of
    the best price against that fair line. Fair line = the sharp book's no-vig price when
    --sharp is given and it posted the market, otherwise the median no-vig price across books.
    Spreads/totals are compared only at the most common line so points match.
    """
    results = []
    for event in data:
        # market_key -> point_signature -> book -> {outcome_name: (price, point)}
        by_market: dict[str, dict[tuple, dict[str, dict]]] = {}
        for bk in event.get("bookmakers", []):
            for mkt in bk.get("markets", []):
                outs = {o["name"]: (o["price"], o.get("point")) for o in mkt.get("outcomes", [])}
                if len(outs) < 2:
                    continue
                # Totals share one point; spreads are +x/-x. abs() groups both sides of a spread.
                sig = tuple(sorted({abs(pt) for _, pt in outs.values() if pt is not None}))
                by_market.setdefault(mkt["key"], {}).setdefault(sig, {})[bk["key"]] = {
                    "title": bk.get("title", bk["key"]), "outcomes": outs,
                }

        for mkt_key, by_sig in by_market.items():
            sig, line_books = max(by_sig.items(), key=lambda kv: len(kv[1]))
            # Fair probabilities per book (no-vig within each book)
            fair_by_book: dict[str, dict[str, float]] = {}
            for bkey, b in line_books.items():
                names = list(b["outcomes"])
                fair = no_vig([implied_probability(b["outcomes"][n][0]) for n in names])
                fair_by_book[bkey] = dict(zip(names, fair))

            sharp_used = sharp if sharp and sharp in fair_by_book else None
            shoppable = {k: v for k, v in line_books.items() if not books or k in books}
            if not shoppable:
                continue
            names = sorted({n for b in line_books.values() for n in b["outcomes"]})

            outcomes = []
            for name in names:
                if sharp_used:
                    fp = fair_by_book[sharp_used].get(name)
                else:
                    vals = [f[name] for f in fair_by_book.values() if name in f]
                    fp = _median(vals) if vals else None
                prices = [(b["outcomes"][name][0], b["outcomes"][name][1], b["title"])
                          for k, b in shoppable.items() if name in b["outcomes"] and k != sharp_used]
                if not prices or fp is None:
                    continue
                best_price, point, best_book = max(prices, key=lambda x: american_to_decimal(x[0]))
                ev = fp * american_to_decimal(best_price) - 1
                outcomes.append({
                    "name": name,
                    "point": point,
                    "best_price": best_price,
                    "best_book": best_book,
                    "books_quoting": len(prices),
                    "fair_probability": round(fp, 4),
                    "fair_american": prob_to_american(fp),
                    "ev_pct": round(ev * 100, 2),
                    "all_prices": {t: p for p, _, t in sorted(prices, key=lambda x: -american_to_decimal(x[0]))},
                })
            if not outcomes:
                continue
            start_utc = event.get("commence_time", "").replace("Z", "")
            results.append({
                "event_id": event.get("id", ""),
                "name": f"{event.get('away_team', '')} @ {event.get('home_team', '')}".strip(" @") or event.get("sport_title", ""),
                "start_time": event.get("commence_time", ""),
                "start_time_local": utc_to_local(start_utc),
                "market": mkt_key,
                "fair_source": sharp_used or f"median of {len(fair_by_book)} books",
                "outcomes": outcomes,
            })
    return results


def fetch_oddsapi(url: str) -> list:
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            remaining = resp.headers.get("x-requests-remaining")
            if remaining is not None:
                print(f"Odds API requests remaining this month: {remaining}", file=sys.stderr)
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        print(f"HTTP Error {e.code}: {e.reason}", file=sys.stderr)
        if e.code == 401:
            print("  Check ODDS_API_KEY.", file=sys.stderr)
        elif e.code == 429:
            print("  Odds API quota or rate limit hit.", file=sys.stderr)
        sys.exit(1)
    except urllib.error.URLError as e:
        print(f"URL Error: {e.reason}", file=sys.stderr)
        sys.exit(1)


def print_shop_table(results: list[dict], min_ev: float | None):
    if not results:
        print("\nNo odds data found (off-season, wrong market, or no books posted it).\n", file=sys.stderr)
        return
    print(f"\n{'='*78}", file=sys.stderr)
    hdr = f"  {len(results)} market(s)"
    if min_ev is not None:
        hdr += f"  |  showing outcomes with EV >= {min_ev}%"
    print(hdr, file=sys.stderr)
    print(f"{'='*78}", file=sys.stderr)
    for r in results:
        print(f"\n  {r['name']}  [{r['market']}]", file=sys.stderr)
        print(f"  Start: {r['start_time_local']}  |  fair: {r['fair_source']}", file=sys.stderr)
        print(f"  {'─'*60}", file=sys.stderr)
        for o in r["outcomes"]:
            pt = "" if o["point"] is None else f" {'+' if o['point'] > 0 else ''}{o['point']}"
            flag = "  <-- +EV" if o["ev_pct"] > 0 else ""
            print(f"    {(o['name'] + pt):<30} best {o['best_price']:>+5} @ {o['best_book']:<14} "
                  f"fair {o['fair_american']:>+5}  EV {o['ev_pct']:>+6.2f}%{flag}", file=sys.stderr)
    print(f"\n{'='*78}\n", file=sys.stderr)


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
            if "fair_probability" in odds:
                prob += f", fair {odds['fair_probability']:.1%}"
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
    parser.add_argument("--source", choices=["draftkings", "oddsapi"], default="draftkings",
                        help="draftkings (single book, blocked from cloud IPs) or oddsapi (multi-book)")
    parser.add_argument("--sport", choices=sorted(set(LEAGUES) | set(ODDS_API_SPORTS)), help="Sport")
    parser.add_argument("--market", default="series-winner", help="Market type (default: series-winner)")
    parser.add_argument("--url", help="Direct DraftKings API URL override")
    parser.add_argument("--file", help="Parse a local JSON file instead of fetching")
    parser.add_argument("--json-only", action="store_true", help="JSON output only, no table")
    parser.add_argument("--show-url", action="store_true", help="Print constructed URL and exit")
    parser.add_argument("--regions", default="us", help="oddsapi: book regions, e.g. us,us2,eu (default: us)")
    parser.add_argument("--sharp", help="oddsapi: book key to use as the fair line, e.g. pinnacle (add eu to --regions)")
    parser.add_argument("--books", help="oddsapi: comma-separated book keys you can bet at, e.g. draftkings,fanduel")
    parser.add_argument("--min-ev", type=float, help="oddsapi: only show outcomes with EV%% >= this")
    args = parser.parse_args()

    if args.source == "oddsapi":
        run_oddsapi(args, parser)
        return

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


def run_oddsapi(args, parser):
    if args.file:
        with open(args.file) as f:
            data = json.load(f)
    else:
        if not args.sport:
            parser.error("--source oddsapi needs --sport (or --file)")
        if args.sport not in ODDS_API_SPORTS:
            parser.error(f"--sport {args.sport} not mapped for oddsapi")
        api_key = os.environ.get("ODDS_API_KEY")
        if not api_key:
            parser.error("Set ODDS_API_KEY (free key: https://the-odds-api.com)")
        market = "game-lines" if args.market == "series-winner" else args.market
        regions = args.regions
        if args.sharp == "pinnacle" and "eu" not in regions.split(","):
            regions += ",eu"
        url = build_oddsapi_url(args.sport, market, api_key, regions)
        if args.show_url:
            print(url.replace(api_key, "<ODDS_API_KEY>"))
            return
        print(f"Fetching: oddsapi / {args.sport} / {market}", file=sys.stderr)
        data = fetch_oddsapi(url)

    books = {b.strip() for b in args.books.split(",")} if args.books else None
    results = parse_oddsapi_response(data, sharp=args.sharp, books=books)
    if args.min_ev is not None:
        for r in results:
            r["outcomes"] = [o for o in r["outcomes"] if o["ev_pct"] >= args.min_ev]
        results = [r for r in results if r["outcomes"]]
    if not args.json_only:
        print_shop_table(results, args.min_ev)
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
