# DraftKings Endpoints Reference

## ⚠️ Disclaimer
These are unofficial, publicly available endpoints. Not affiliated with DraftKings. May change without notice.

## Base URL Pattern (Confirmed Working April 2026)

```
https://sportsbook-nash.draftkings.com/sites/US-IL-SB/api/sportscontent/controldata/league/leagueSubcategory/v1/markets
```

Full URL with parameters:
```
{base}?isBatchable=false
  &templateVars={leagueId},{subcategoryId}
  &eventsQuery=$filter=leagueId eq '{leagueId}' AND clientMetadata/Subcategories/any(s: s/Id eq '{subcategoryId}')
  &marketsQuery=$filter=clientMetadata/subCategoryId eq '{subcategoryId}' AND tags/all(t: t ne 'SportcastBetBuilder')
  &include=Events
  &entity=events
```

The site code `US-IL-SB` is Illinois-specific but works nationally. If it stops working, try `US-DK` or `US-NJ-SB`. The domain may also vary (e.g., `sportsbook-nash-usm.draftkings.com`). If requests fail, use the endpoint discovery process.

**The `scripts/fetch-odds.py` script constructs this URL automatically.** Just run:
```bash
python3 scripts/fetch-odds.py --sport nba --market series-winner
```

## League IDs

| Sport | League | DraftKings League ID |
|-------|--------|---------------------|
| Basketball | NBA | `42648` |
| Football | NFL | `88808` |
| Basketball | NCAAB | `42648` (different event group) |
| Football | NCAAF | `88808` (different event group) |
| Hockey | NHL | `42133` |
| Baseball | MLB | `84240` |
| Soccer | EPL | `40253` |
| Soccer | Champions League | `40685` |
| MMA | UFC | varies per event |

## Market Categories and Subcategories

Markets are organized by category and subcategory. The IDs below are known working values but may change.

### NBA Playoffs
| Market | Category | Subcategory | Notes |
|--------|----------|-------------|-------|
| Series Winner | series-props | `18082` | Only available once playoff matchups are set |
| Series Spread | series-props | varies | Series handicap |
| Series Total Games | series-props | varies | Over/under on games played |
| Series Correct Score | series-props | varies | Exact series result (e.g., 4-2) |
| Game Lines | game-lines | varies | Individual game moneylines |
| Team Futures | team-futures | varies | Championship winner |

### NFL Playoffs
| Market | Category | Subcategory | Notes |
|--------|----------|-------------|-------|
| Series Winner | series-props | TBD | Find via endpoint discovery during NFL playoffs |
| Game Lines | game-lines | varies | Individual game moneylines |
| Super Bowl Winner | team-futures | varies | Championship futures |

## How to Construct the URL

The primary endpoint for fetching odds is the `markets` endpoint. The URL pattern observed from the DraftKings SPA:

```
GET {base_url}/markets?isBatchable=false&...
```

However, the exact query parameters include internal IDs that may change. The most reliable approach is:

1. Use the **endpoint discovery process** (see endpoint-discovery.md) to capture the exact URL
2. Store the URL as an environment variable
3. Hit it from your cron job
4. If it fails, re-run endpoint discovery

## Alternatively: DraftKings Frontend URLs

These human-readable URLs load the same data via the SPA:

```
# NBA Series Props - Winner
https://sportsbook.draftkings.com/leagues/basketball/nba?category=series-props&subcategory=winner

# NBA Game Lines
https://sportsbook.draftkings.com/leagues/basketball/nba?category=game-lines&subcategory=game

# NBA Team Futures
https://sportsbook.draftkings.com/leagues/basketball/nba?category=team-futures&subcategory=championship

# NFL Series Props (during playoffs)
https://sportsbook.draftkings.com/leagues/football/nfl?category=series-props&subcategory=winner

# NFL Game Lines
https://sportsbook.draftkings.com/leagues/football/nfl?category=game-lines&subcategory=game
```

These are useful for the endpoint discovery process — open one in Chrome DevTools to find the underlying API call.

## Response Structure

Every DraftKings odds response follows this structure:

```json
{
  "sports": [...],          // Sport metadata
  "leagues": [...],         // League metadata  
  "events": [...],          // Matchups with teams, times, status
  "markets": [...],         // Bet types per event
  "selections": [...],      // Actual odds (the money data)
  "subscriptionPartials": { // WebSocket subscription info (can ignore)
    ...
  }
}
```

### Events
```json
{
  "id": "63e93231-f3e5-471a-26b3-08de970bad08",
  "seoIdentifier": "cle-cavaliers-vs-tor-raptors---series",
  "leagueId": "42648",
  "name": "CLE Cavaliers vs TOR Raptors - Series",
  "startEventDate": "2026-04-18T17:10:00.0000000Z",
  "participants": [
    {
      "id": "32957",
      "name": "TOR Raptors",
      "metadata": {
        "shortName": "TOR",
        "teamColor": "#ce1141"
      }
    },
    {
      "id": "32908",
      "name": "CLE Cavaliers",
      "metadata": {
        "shortName": "CLE",
        "teamColor": "#860038"
      }
    }
  ],
  "status": "NOT_STARTED"
}
```

### Markets
```json
{
  "id": "325321451",
  "eventId": "63e93231-f3e5-471a-26b3-08de970bad08",
  "name": "Series Winner",
  "marketType": {
    "id": "3352",
    "name": "Series Winner"
  }
}
```

### Selections (THE ODDS)
```json
{
  "marketId": "325321451",
  "label": "CLE Cavaliers",
  "displayOdds": {
    "american": "−600",     // ⚠️ Unicode minus U+2212, not hyphen
    "decimal": "1.16",
    "fractional": "1/6"
  },
  "trueOdds": 1.16666667,  // Decimal odds as a float
  "participants": [
    {
      "id": "32908",
      "name": "CLE Cavaliers"
    }
  ]
}
```

## Joining the Data

```
event.id ──────────→ market.eventId     (1 event has 1+ markets)
market.id ─────────→ selection.marketId  (1 market has 2+ selections)
selection.participants[0].id ──→ event.participants[].id  (which team)
```

## Team Abbreviation Mapping

DraftKings uses these `shortName` values in participant metadata:

### NBA
ATL, BOS, BKN, CHA, CHI, CLE, DAL, DEN, DET, GSW, HOU, IND, LAC, LAL, MEM, MIA, MIL, MIN, NO, NY, OKC, ORL, PHI, PHX, POR, SAC, SAS, TOR, UTA, WAS

Note: DraftKings uses `NY` for Knicks (not `NYK`) and `NO` for Pelicans (not `NOP`). Map these to your internal abbreviations.

### NFL
ARI, ATL, BAL, BUF, CAR, CHI, CIN, CLE, DAL, DEN, DET, GB, HOU, IND, JAX, KC, LAC, LAR, LV, MIA, MIN, NE, NO, NYG, NYJ, PHI, PIT, SEA, SF, TB, TEN, WAS
