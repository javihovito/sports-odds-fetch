# Parsing Guide

Complete parsers for extracting odds from the DraftKings API response.

## TypeScript Parser

```typescript
// lib/draftkings-odds.ts

// ============================================
// TYPES
// ============================================

interface DKParticipant {
  id: string;
  name: string;
  type: string;
  metadata: {
    rosettaTeamId?: string;
    rosettaTeamName?: string;
    shortName: string;
    teamColor?: string;
  };
  seoIdentifier: string;
  countryCode?: string;
}

interface DKEvent {
  id: string;
  seoIdentifier: string;
  leagueId: string;
  name: string;
  startEventDate: string;
  participants: DKParticipant[];
  status: string;
}

interface DKMarket {
  id: string;
  eventId: string;
  name: string;
  marketType: {
    id: string;
    name: string;
  };
}

interface DKSelection {
  id: string;
  marketId: string;
  label: string;
  displayOdds: {
    american: string;
    decimal: string;
    fractional: string;
  };
  trueOdds: number;
  participants: { id: string; name: string }[];
}

interface DKResponse {
  events: DKEvent[];
  markets: DKMarket[];
  selections: DKSelection[];
}

// ============================================
// PARSED OUTPUT TYPE
// ============================================

export interface SeriesOdds {
  eventId: string;
  seriesName: string;
  startTime: string;          // ISO 8601
  status: string;
  teams: {
    abbrev: string;           // e.g. "CLE"
    name: string;             // e.g. "CLE Cavaliers"  
    color: string;            // e.g. "#860038"
    americanOdds: number;     // e.g. -600
    decimalOdds: number;      // e.g. 1.167
    impliedProbability: number; // e.g. 0.857
    isFavorite: boolean;
  }[];
}

// ============================================
// PARSER
// ============================================

/**
 * Parse a DraftKings series props API response into clean SeriesOdds objects.
 * Works for NBA series winner, NFL series winner, and similar markets.
 */
export function parseSeriesOdds(data: DKResponse): SeriesOdds[] {
  return data.events
    .map((event) => {
      // Find the "Series Winner" market for this event
      const market = data.markets.find(
        (m) => m.eventId === event.id && m.marketType.name === "Series Winner"
      );
      if (!market) return null;

      // Find selections for this market
      const selections = data.selections.filter(
        (s) => s.marketId === market.id
      );
      if (selections.length < 2) return null;

      // Build team odds by matching selections to participants
      const teams = event.participants.map((participant) => {
        const selection = selections.find((s) =>
          s.participants.some((p) => p.id === participant.id)
        );

        const americanOdds = selection
          ? parseAmericanOdds(selection.displayOdds.american)
          : 0;
        const decimalOdds = selection?.trueOdds ?? 0;

        return {
          abbrev: participant.metadata.shortName,
          name: participant.name,
          color: participant.metadata.teamColor ?? "#000000",
          americanOdds,
          decimalOdds,
          impliedProbability: decimalToImpliedProbability(decimalOdds),
          isFavorite: americanOdds < 0,
        };
      });

      return {
        eventId: event.id,
        seriesName: event.name,
        startTime: event.startEventDate,
        status: event.status,
        teams,
      };
    })
    .filter((x): x is SeriesOdds => x !== null);
}

// ============================================
// ODDS CONVERSION UTILITIES
// ============================================

/**
 * Parse DraftKings American odds string to integer.
 * ⚠️ CRITICAL: DK uses Unicode minus "−" (U+2212), not hyphen "-" (U+002D).
 */
export function parseAmericanOdds(oddsStr: string): number {
  // Replace Unicode minus with standard minus, strip plus sign
  const cleaned = oddsStr
    .replace(/\u2212/g, "-")  // Unicode minus → hyphen
    .replace(/[^0-9\-]/g, ""); // Strip everything except digits and hyphen
  return parseInt(cleaned, 10);
}

/**
 * Convert decimal odds to implied probability.
 */
export function decimalToImpliedProbability(decimal: number): number {
  if (decimal <= 0) return 0;
  return 1 / decimal;
}

/**
 * Convert American odds to implied probability.
 */
export function americanToImpliedProbability(american: number): number {
  if (american < 0) {
    return Math.abs(american) / (Math.abs(american) + 100);
  }
  return 100 / (american + 100);
}

/**
 * Convert implied probability to American odds.
 */
export function probabilityToAmerican(prob: number): number {
  if (prob >= 0.5) {
    return Math.round((-100 * prob) / (1 - prob));
  }
  return Math.round((100 * (1 - prob)) / prob);
}

// ============================================
// FETCH FUNCTION
// ============================================

/**
 * Fetch series odds from DraftKings.
 * @param endpoint - The full DraftKings API URL (from endpoint discovery)
 */
export async function fetchDraftKingsSeriesOdds(
  endpoint: string
): Promise<SeriesOdds[]> {
  try {
    const response = await fetch(endpoint, {
      headers: {
        "User-Agent": "Mozilla/5.0",
        Accept: "application/json",
      },
      // No auth needed — endpoint is public
    });

    if (!response.ok) {
      throw new Error(`DraftKings API returned ${response.status}`);
    }

    const data: DKResponse = await response.json();
    return parseSeriesOdds(data);
  } catch (error) {
    console.error("Failed to fetch DraftKings odds:", error);
    return [];
  }
}

// ============================================
// EXAMPLE: VERCEL CRON JOB
// ============================================

/*
// app/api/cron/update-odds/route.ts

import { createClient } from "@supabase/supabase-js";
import { fetchDraftKingsSeriesOdds, parseAmericanOdds } from "@/lib/draftkings-odds";

const supabase = createClient(
  process.env.NEXT_PUBLIC_SUPABASE_URL!,
  process.env.SUPABASE_SERVICE_ROLE_KEY!
);

export async function GET(request: Request) {
  // Verify cron secret
  const authHeader = request.headers.get("authorization");
  if (authHeader !== `Bearer ${process.env.CRON_SECRET}`) {
    return new Response("Unauthorized", { status: 401 });
  }

  const endpoint = process.env.DRAFTKINGS_SERIES_ODDS_ENDPOINT!;
  const seriesOdds = await fetchDraftKingsSeriesOdds(endpoint);

  if (seriesOdds.length === 0) {
    return Response.json({ error: "No odds returned" }, { status: 500 });
  }

  // Update each series in the database
  for (const series of seriesOdds) {
    const favorite = series.teams.find((t) => t.isFavorite);
    const underdog = series.teams.find((t) => !t.isFavorite);

    if (!favorite || !underdog) continue;

    // Match series by team abbreviations
    const { error } = await supabase
      .from("series")
      .update({
        higher_seed_moneyline: favorite.americanOdds,
        lower_seed_moneyline: underdog.americanOdds,
        pick_deadline: series.startTime,
        odds_updated_at: new Date().toISOString(),
        odds_source: "draftkings_api",
      })
      .or(
        `higher_seed_team.eq.${favorite.abbrev},lower_seed_team.eq.${favorite.abbrev}`
      );

    if (error) console.error(`Failed to update ${series.seriesName}:`, error);
  }

  return Response.json({
    updated: seriesOdds.length,
    series: seriesOdds.map((s) => s.seriesName),
  });
}
*/
```

## Python Parser

```python
# draftkings_odds.py

from typing import Optional


def parse_american_odds(odds_str: str) -> int:
    """Parse DraftKings American odds string to integer.
    DK uses Unicode minus '−' (U+2212), not hyphen '-' (U+002D).
    """
    cleaned = odds_str.replace("\u2212", "-").replace("+", "")
    return int(cleaned)


def decimal_to_implied_probability(decimal: float) -> float:
    if decimal <= 0:
        return 0
    return 1 / decimal


def parse_series_odds(data: dict) -> list[dict]:
    """Parse DraftKings API response into clean series odds."""
    events = {e["id"]: e for e in data.get("events", [])}
    markets = {m["id"]: m for m in data.get("markets", [])}
    selections = data.get("selections", [])

    # Group selections by marketId
    market_selections: dict[str, list] = {}
    for sel in selections:
        mid = sel["marketId"]
        market_selections.setdefault(mid, []).append(sel)

    results = []
    for market in data.get("markets", []):
        if market.get("marketType", {}).get("name") != "Series Winner":
            continue

        event = events.get(market["eventId"])
        if not event:
            continue

        sels = market_selections.get(market["id"], [])
        if len(sels) < 2:
            continue

        # Build participant lookup
        participant_map = {p["id"]: p for p in event["participants"]}

        teams = []
        for sel in sels:
            pid = sel["participants"][0]["id"]
            participant = participant_map.get(pid, {})
            american = parse_american_odds(sel["displayOdds"]["american"])

            teams.append({
                "abbrev": participant.get("metadata", {}).get("shortName", ""),
                "name": sel["label"],
                "color": participant.get("metadata", {}).get("teamColor", "#000"),
                "american_odds": american,
                "decimal_odds": sel["trueOdds"],
                "implied_probability": decimal_to_implied_probability(sel["trueOdds"]),
                "is_favorite": american < 0,
            })

        results.append({
            "event_id": event["id"],
            "series_name": event["name"],
            "start_time": event["startEventDate"],
            "status": event["status"],
            "teams": teams,
        })

    return results
```

## Edge Cases to Handle

1. **Missing selections:** A market may exist without selections if odds are temporarily suspended. Check `selections.length >= 2`.

2. **Even odds:** Both teams at -110 means both are slight favorites (vig). Neither will have `isFavorite = true` by the negative-odds check. Handle by comparing decimal odds.

3. **Odds movement:** Odds can change between fetches. Always store the fetch timestamp and show "last updated" in the UI.

4. **New series appearing:** After play-in/wild card games, new events appear in the response. Your cron should handle new events gracefully (insert if not exists, update if exists).

5. **Series completion:** Once a series ends, DraftKings removes it from the active response. Your app should track series status independently (via scores API or manual update).
