# sports-odds-fetch

A Claude Code skill that fetches live sports betting odds from DraftKings. One command to get NBA/NFL playoff series odds, game lines, spreads, and totals.

![Claude Code fetching NBA series odds](https://img.shields.io/badge/Claude_Code-Skill-blue) ![NBA](https://img.shields.io/badge/NBA-Odds-orange) ![NFL](https://img.shields.io/badge/NFL-Odds-green)

## Demo

```
> Get me the current NBA playoff series odds

● Skill(sports-odds-fetch)
  └ Successfully loaded skill

● Bash(python3 scripts/fetch-odds.py --sport nba --market series-winner)

| Series     | Favorite       | Odds  | Underdog         | Odds  |
|------------|---------------|-------|------------------|-------|
| HOU vs LAL | HOU Rockets   | -750  | LA Lakers        | +550  |
| CLE vs TOR | CLE Cavaliers | -600  | TOR Raptors      | +425  |
| DEN vs MIN | DEN Nuggets   | -350  | MIN Timberwolves | +280  |
| NY vs ATL  | NY Knicks     | -290  | ATL Hawks        | +230  |
```

## Install

```bash
# Clone into your Claude Code skills directory
git clone https://github.com/nchemb/sports-odds-fetch.git ~/.claude/skills/sports-odds-fetch
```

## Usage

Just ask Claude Code:

```
Get me the current NBA playoff series odds
Get me today's NBA game lines
```

Or run the script directly:

```bash
# NBA series winner odds
python3 scripts/fetch-odds.py --sport nba --market series-winner

# NBA game lines (moneylines, spreads, totals)
python3 scripts/fetch-odds.py --sport nba --market game-lines

# Output JSON only (for piping to your app)
python3 scripts/fetch-odds.py --sport nba --market series-winner --json-only

# Parse a saved response file
python3 scripts/fetch-odds.py --file saved-response.json

# Show the constructed API URL
python3 scripts/fetch-odds.py --sport nba --market series-winner --show-url
```

## Line Shopping and +EV (multi-book)

`--source oddsapi` pulls every US book from The Odds API (works from cloud IPs, unlike DraftKings direct). For each outcome it reports the best price and book, the no-vig fair line, and EV% of the best price against that fair line.

```bash
export ODDS_API_KEY=...   # free key: https://the-odds-api.com (500 requests/month)

# Best price per side across books, game lines
python3 scripts/fetch-odds.py --source oddsapi --sport nfl --market game-lines

# Only +EV prices at books you can bet, Pinnacle as the fair line
python3 scripts/fetch-odds.py --source oddsapi --sport nba --sharp pinnacle \
  --books draftkings,fanduel,betmgm --min-ev 1
```

- Markets: `game-lines` (h2h,spreads,totals), `moneyline`, `spreads`, `totals`, `futures`.
- Sports: nba, nfl, nhl, mlb, ncaaf, ncaab.
- Fair line: median no-vig price across books, or `--sharp <book>` (adds the `eu` region for Pinnacle).
- Spreads/totals compare only books at the most common line, so points match.
- Each call costs one request per market per region; remaining quota prints to stderr.

DraftKings output now also includes `fair_probability` and `fair_american` (vig removed).

## Supported Markets

| Sport | Market | Status |
|-------|--------|--------|
| NBA | Series Winner (playoff) | ✅ Working |
| NBA | Game Lines (moneyline, spread, total) | ✅ Working |
| NFL | Series Winner (playoff) | 🔜 Discover during NFL playoffs |
| NFL | Game Lines | 🔜 Discover during NFL season |
| NHL | Series Winner (playoff) | 🔜 Discover during NHL playoffs |

Adding a new sport/market takes 30 seconds — see [Endpoint Discovery](references/endpoint-discovery.md).

## How It Works

The skill uses DraftKings' publicly available sportsbook API (no authentication required). It constructs API URLs from league IDs and subcategory IDs, fetches JSON, and parses the odds into a clean format.

```
DraftKings API → events (matchups) → markets (bet types) → selections (odds)
```

The script handles DraftKings' Unicode minus sign gotcha (U+2212 vs U+002D) and outputs both a human-readable table and clean JSON.

## Architecture for Apps

If you're building a sports app, the skill recommends a three-layer pattern:

1. **DraftKings API** — Primary odds source (free, real-time, no auth)
2. **The Odds API** — Game schedules and multi-book comparison (free tier: 500 req/month)
3. **Admin manual entry** — Fallback if any API breaks

Always store UTC. Convert to local timezone on the frontend.

## File Structure

```
sports-odds-fetch/
├── SKILL.md                           # Claude Code skill definition
├── scripts/
│   └── fetch-odds.py                  # Executable fetcher + parser
├── references/
│   ├── draftkings-endpoints.md        # League IDs, subcategory IDs, URL patterns
│   ├── parsing-guide.md               # TypeScript + Python parsers
│   ├── odds-math.md                   # American ↔ decimal ↔ probability math
│   └── endpoint-discovery.md          # How to find new endpoints via DevTools
└── README.md
```

## Adding New Markets

1. Open DraftKings page for the market you want (e.g., NFL series props)
2. Chrome DevTools → Network → filter `sportsbook-nas`
3. Find `templateVars` or subcategory ID in the API URL
4. Add one line to `SUBCATEGORIES` in `scripts/fetch-odds.py`

See [endpoint-discovery.md](references/endpoint-discovery.md) for the full walkthrough.

## Disclaimer

This skill uses publicly available, unofficial DraftKings endpoints. It is **not affiliated with or endorsed by DraftKings**. Intended for personal and educational use. Endpoints may change without notice — the skill includes a discovery process for when that happens.

No authentication or DraftKings account is required.

## Built by

[@buildwithneej](https://tiktok.com/@buildwithneej) — AI/dev tools content

Built with [Claude Code](https://claude.ai)

## License

MIT
