---
name: sports-odds-fetch
description: Fetch live sports betting odds (moneylines, spreads, series winners, futures) for NBA, NFL, and other major sports. Use this skill whenever the task involves getting sports odds data, building a sports betting or fantasy app, creating a pick'em pool, displaying sportsbook lines, or integrating odds into any application. Triggers on mentions of odds, moneylines, spreads, point spreads, series odds, playoff odds, betting lines, sportsbook data, DraftKings, FanDuel, pick'em, bracket pool, or fantasy sports that need live odds data.
---

# Sports Odds Fetch

A skill for reliably fetching live sports betting odds from public sportsbook endpoints. Covers series winner odds, game moneylines, spreads, totals, and futures for NBA, NFL, and other major leagues.

## ⚠️ Disclaimer

This skill uses publicly available, unofficial sportsbook endpoints. It is not affiliated with or endorsed by DraftKings, FanDuel, ESPN, or any sportsbook. Intended for personal and educational use. Endpoints may change without notice. Always build a manual fallback.

## Quick Start — Fetching Odds

This skill includes a runnable script that auto-constructs the DraftKings API URL. No manual URL needed for supported markets.

**When someone asks for odds, Claude Code should RUN this script:**

```bash
# NBA playoff series winner odds — works out of the box
python3 {skill_directory}/scripts/fetch-odds.py --sport nba --market series-winner

# Save as JSON for use in an app
python3 {skill_directory}/scripts/fetch-odds.py --sport nba --market series-winner --json-only > odds.json

# Parse a previously saved DraftKings response
python3 {skill_directory}/scripts/fetch-odds.py --file dk-response.json

# Show the constructed URL without fetching
python3 {skill_directory}/scripts/fetch-odds.py --sport nba --market series-winner --show-url
```

**Currently supported (auto-constructed URL):**
- `--sport nba --market series-winner` ✅ NBA playoff series odds

**Not yet discovered (need endpoint discovery first):**
- `--sport nfl --market series-winner` — discover during NFL playoffs (January)
- `--sport nhl --market series-winner` — discover during NHL playoffs

To add a new sport/market: open the DraftKings page in Chrome DevTools → Network → find the subcategory ID → add it to the `SUBCATEGORIES` dict in `scripts/fetch-odds.py`. See `references/endpoint-discovery.md`.

**The script outputs:**
- **stderr:** Human-readable table with team names, odds, and implied probabilities
- **stdout:** Clean JSON array — pipe this to your app, save to file, or parse in code

## Line Shopping and +EV (multi-book)

`--source oddsapi` pulls every US book from The Odds API (works from cloud IPs, unlike DraftKings direct). For each outcome it reports the best price and book, the no-vig fair line, and EV% of the best price against that fair line.

```bash
export ODDS_API_KEY=...   # free key: https://the-odds-api.com (500 requests/month)

# Best price per side across books, game lines
python3 {skill_directory}/scripts/fetch-odds.py --source oddsapi --sport nfl --market game-lines

# Only +EV prices at books you can bet, Pinnacle as the fair line
python3 {skill_directory}/scripts/fetch-odds.py --source oddsapi --sport nba --sharp pinnacle \
  --books draftkings,fanduel,betmgm --min-ev 1
```

- Markets: `game-lines` (h2h,spreads,totals), `moneyline`, `spreads`, `totals`, `futures`.
- Sports: nba, nfl, nhl, mlb, ncaaf, ncaab.
- Fair line: median no-vig price across books, or `--sharp <book>` (adds the `eu` region for Pinnacle).
- Spreads/totals compare only books at the most common line, so points match.
- Each call costs one request per market per region; remaining quota prints to stderr.

DraftKings output now also includes `fair_probability` and `fair_american` (vig removed).

## When to Use

- Building a playoff pick'em or bracket pool app
- Displaying live odds in a sports dashboard
- Fetching series winner odds for NBA/NFL playoffs
- Getting game moneylines, spreads, or totals
- Building a fantasy sports tool that needs real odds
- Any project where you need structured betting data

## Architecture Pattern

Every project using this skill should follow the **three-layer pattern**:

```
┌─────────────────────────────────────────────┐
│ Layer 1: DraftKings API (primary source)    │
│ - Series odds, game lines, futures          │
│ - Free, no auth, real-time                  │
│ - Cron job: fetch every 4-6 hours           │
├─────────────────────────────────────────────┤
│ Layer 2: The Odds API (supplementary)       │
│ - Game schedules and start times            │
│ - Multi-book odds comparison                │
│ - 500 free requests/month                   │
├─────────────────────────────────────────────┤
│ Layer 3: Admin manual entry (fallback)      │
│ - Always build this                         │
│ - If any API breaks, 2 min manual update    │
│ - Source of truth for the database          │
└─────────────────────────────────────────────┘
```

**Critical rule:** Never depend on a single odds source. Always build the admin/manual entry layer. APIs change. The manual fallback guarantees your app works regardless.

## Workflow

### Step 1: Identify What Odds You Need

Read `references/draftkings-endpoints.md` to find the right endpoint for your use case:

| Need | DraftKings Endpoint Pattern | Notes |
|------|---------------------------|-------|
| Series winner (who wins best-of-7) | `markets` with series props subcategory | NBA/NFL playoffs only, appears once matchups are set |
| Game moneyline (who wins single game) | `markets` with game lines category | Available year-round for scheduled games |
| Championship futures (who wins title) | `markets` with team futures subcategory | Available year-round |
| Spreads and totals | `markets` with game lines category | Game-level, includes alternate lines |

### Step 2: Fetch and Parse

The DraftKings API returns a consistent structure across all sports:

```
Response {
  events[]     → matchups (teams, start times, event IDs)
  markets[]    → bet types per event (linked by eventId)
  selections[] → actual odds per market (linked by marketId)
}
```

Always join the data through these keys:
- `events[].id` → `markets[].eventId`
- `markets[].id` → `selections[].marketId`
- `selections[].participants[].id` → `events[].participants[].id`

See `references/parsing-guide.md` for complete TypeScript/Python parsers with all edge cases.

### Step 3: Store and Serve

Write parsed odds to your database. The schema should always include:
- The raw moneyline (American format integer, e.g. -600, +425)
- The decimal odds (e.g. 1.167, 5.25) — useful for probability calculations
- A timestamp of when odds were last fetched
- A boolean `odds_locked` flag (lock when event starts)
- An `odds_source` field ('draftkings_api' | 'manual' | etc.)

### Step 4: Set Up Cron

For a Vercel/Next.js project:
```typescript
// app/api/cron/update-odds/route.ts
// Vercel cron: runs every 6 hours
// vercel.json: { "crons": [{ "path": "/api/cron/update-odds", "schedule": "0 */6 * * *" }] }
```

For other platforms, any scheduler that hits your update endpoint on an interval works.

### Step 5: Build the Fallback

Always build an admin page where odds can be manually entered/overridden. This is non-negotiable. The admin page should:
- Show all active series/games with current odds
- Allow editing moneyline values directly
- Show when odds were last auto-updated
- Show the source (API vs manual)

## Key Gotchas

1. **Unicode minus sign:** DraftKings uses `−` (U+2212) not `-` (U+002D) for negative odds. Always `.replace("−", "-")` before parsing.

2. **Endpoint discovery:** DraftKings endpoints change. If your endpoint stops working, open the DraftKings page in Chrome DevTools → Network → Fetch/XHR, filter for `sportsbook-nas`, and find the new URL. See `references/endpoint-discovery.md`.

3. **Timing:** Series odds only appear once matchups are confirmed. For NBA/NFL, this means after play-in/wild card games. Your app should handle "TBD" matchups gracefully.

4. **Rate limiting:** DraftKings doesn't publish rate limits, but stay under 100 requests/hour to be safe. For a typical sports app, 4-6 requests/day is plenty.

5. **Odds format conversion:** See `references/odds-math.md` for converting between American, decimal, and implied probability formats.

## Reference Files

| File | Contents |
|------|----------|
| `references/draftkings-endpoints.md` | League IDs, subcategory IDs, endpoint URL patterns, sport-specific notes |
| `references/parsing-guide.md` | Complete TypeScript parser with all edge cases, example responses |
| `references/odds-math.md` | American ↔ decimal ↔ probability conversion, point value calculations for pick'em pools |
| `references/endpoint-discovery.md` | How to find/update DraftKings endpoints when they change |
