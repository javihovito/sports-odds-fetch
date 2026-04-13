# Endpoint Discovery Guide

When a DraftKings endpoint stops working (404, schema change, empty response), follow this process to find the current one.

## Step-by-Step Discovery

### 1. Open the DraftKings Page

Navigate to the relevant page in Chrome:

```
# NBA Series Winner
https://sportsbook.draftkings.com/leagues/basketball/nba?category=series-props&subcategory=winner

# NFL Series Winner (during playoffs)
https://sportsbook.draftkings.com/leagues/football/nfl?category=series-props&subcategory=winner

# NBA Game Lines
https://sportsbook.draftkings.com/leagues/basketball/nba?category=game-lines&subcategory=game

# NFL Game Lines
https://sportsbook.draftkings.com/leagues/football/nfl?category=game-lines&subcategory=game
```

### 2. Open Chrome DevTools

- Press `Cmd+Option+I` (Mac) or `F12` (Windows)
- Go to the **Network** tab
- Filter by **Fetch/XHR**

### 3. Filter for DraftKings API Calls

In the Network tab filter box, type: `sportsbook-nas`

This filters for the DraftKings sportsbook API domain (e.g., `sportsbook-nash-usm.draftkings.com`).

### 4. Refresh the Page

Hard refresh with `Cmd+Shift+R`. Watch for the API call that loads the odds data.

### 5. Identify the Right Request

Look for a request that:
- Returns JSON (check the Preview tab)
- Contains `events`, `markets`, and `selections` arrays
- Has odds data in `selections[].displayOdds`

### 6. Copy the URL

Right-click the request → **Copy** → **Copy URL**

### 7. Test the URL

```bash
curl -s "PASTE_URL_HERE" | python3 -m json.tool | head -50
```

Verify it returns the expected data structure.

### 8. Store as Environment Variable

```env
DRAFTKINGS_SERIES_ODDS_ENDPOINT=https://sportsbook-nash-usm.draftkings.com/...
```

## Known URL Patterns

DraftKings API URLs typically contain these components:

```
https://{sportsbook-domain}/sites/US-DK/api/v{version}/{endpoint}?{params}
```

The domain has been observed as:
- `sportsbook-nash-usm.draftkings.com`
- `sportsbook-nash.draftkings.com`
- `sportsbook-api.draftkings.com`

The `markets` endpoint URL often includes:
- `isBatchable=false`
- `eventGroupId` (same as league ID, e.g., 42648)
- Filter parameters for subcategory

## Monitoring for Breakage

Set up a simple health check in your cron:

```typescript
const response = await fetch(endpoint);
const data = await response.json();

if (!data.events?.length || !data.selections?.length) {
  // Endpoint may have changed — alert the admin
  await sendAlert("DraftKings odds endpoint returned empty. Re-run endpoint discovery.");
  // Fall back to showing last cached odds with "last updated" timestamp
}
```

## Frequency of Changes

Based on community observation:
- **Domain changes:** Rare (~once per year)
- **URL parameter changes:** Occasional (~1-2x per year)
- **Response schema changes:** Very rare (structure has been stable since 2022+)
- **Subcategory ID changes:** Possible between seasons

The most common failure mode is the endpoint URL changing, not the response format. The discovery process takes 60 seconds to find the new URL.
