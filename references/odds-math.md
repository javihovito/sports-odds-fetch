# Odds Math Reference

## Format Conversion

### American → Decimal
```
If negative (favorite):  decimal = 1 + (100 / |american|)
If positive (underdog):  decimal = 1 + (american / 100)

Examples:
  -600 → 1 + (100/600) = 1.167
  +425 → 1 + (425/100) = 5.25
  -110 → 1 + (100/110) = 1.909
```

### American → Implied Probability
```
If negative:  prob = |american| / (|american| + 100)
If positive:  prob = 100 / (american + 100)

Examples:
  -600 → 600/700 = 85.7%
  +425 → 100/525 = 19.0%
  -350 → 350/450 = 77.8%
  +280 → 100/380 = 26.3%
```

### Implied Probability → American
```
If prob >= 50%:  american = -100 × prob / (1 - prob)
If prob < 50%:   american = 100 × (1 - prob) / prob

Examples:
  85% → -100 × 0.85 / 0.15 = -567
  20% → 100 × 0.80 / 0.20 = +400
```

### Note on Vig (Overround)
Sportsbook implied probabilities for both sides sum to MORE than 100%. The excess is the vig (sportsbook profit margin). For series odds, typical vig is 5-15%.

```
Example: CLE -600 (85.7%) + TOR +425 (19.0%) = 104.7%
The 4.7% is the vig.

To get "true" no-vig probabilities, normalize:
  CLE: 85.7 / 104.7 = 81.9%
  TOR: 19.0 / 104.7 = 18.1%
```

## Pick'em Pool Point Calculations

### Base Point Adjustment (Underdog Bonus System)

For bracket pick'em pools, the standard approach:

1. Start with a base point value (e.g., 10)
2. Adjust based on implied probability so favorites are worth less and underdogs are worth more
3. Scale the adjustment by an "underdog bonus" intensity setting

```typescript
function calculatePickPoints(
  americanOdds: number,
  basePoints: number = 10,
  intensity: 'none' | 'low' | 'medium' | 'high' = 'medium'
): number {
  if (intensity === 'none') return basePoints;

  const scale = { low: 0.5, medium: 1.0, high: 1.5 }[intensity];

  // Convert to implied probability
  let impliedProb: number;
  if (americanOdds < 0) {
    impliedProb = Math.abs(americanOdds) / (Math.abs(americanOdds) + 100);
  } else {
    impliedProb = 100 / (americanOdds + 100);
  }

  // Center around 0.5 — favorites get fewer points, underdogs get more
  const adjustment = (0.5 - impliedProb) * basePoints * scale;
  const points = Math.round(basePoints + adjustment);
  return Math.max(1, points); // minimum 1 point
}

// Examples with medium intensity, base 10:
// -600 (85.7% prob) → 10 + (0.5 - 0.857) × 10 × 1.0 = 10 - 3.57 = 6 pts
// +425 (19.0% prob) → 10 + (0.5 - 0.190) × 10 × 1.0 = 10 + 3.10 = 13 pts
// -290 (74.4% prob) → 10 + (0.5 - 0.744) × 10 × 1.0 = 10 - 2.44 = 8 pts
// +230 (30.3% prob) → 10 + (0.5 - 0.303) × 10 × 1.0 = 10 + 1.97 = 12 pts
```

### Round Multipliers

Points increase in later playoff rounds:

```
None:   [1, 1, 1, 1]  — flat scoring
Low:    [1, 2, 3, 4]  — gentle progression
Medium: [1, 2, 4, 6]  — standard
High:   [1, 2, 4, 8]  — finals picks are huge
```

Apply: `final_points = pick_points × round_multiplier[round - 1]`

### Game Count Bonus

Bonus for correctly predicting the number of games in a series:

```
None:   0%   bonus
Low:    25%  bonus
Medium: 50%  bonus
High:   100% bonus (double points)
```

Apply: `total = pick_points + (is_correct_games ? pick_points × bonus_pct : 0)`
