# yfinance Component Model Root Cause Audit

Date: 2026-06-07

## Scope

This audit investigates why the NDX component-model PB showed `41.18x` while DanjuanFunds showed `10.02x`, and whether similar component-ratio aggregation errors affect other L4 yfinance-derived valuation and earnings-quality metrics.

## Finding 1: PB 41.18x Root Cause

The root cause was aggregation math, not a single bad yfinance field.

The old code computed:

```text
sum(component_market_cap_weight * component_price_to_book)
```

That arithmetic weighted average is not an index PB. For ratios like PB, the aggregate index-level ratio should be:

```text
covered_market_cap / sum(component_market_cap / component_price_to_book)
```

Using the same current yfinance component data:

- Old arithmetic weighted component PB: `41.18`
- Correct aggregate PB: `10.11`
- DanjuanFunds PB: `10.02`

The old `41.18` can be reproduced exactly from current yfinance data by applying the old formula. That means the extreme number came from an invalid ratio aggregation method.

The largest old-formula contributor was ASML:

- ASML market-cap weight: about `1.49%`
- ASML component PB: about `1453.31`
- Old-formula PB contribution: about `21.59` points

This is mathematically expected under the old formula, but it is not an index PB interpretation.

## Finding 2: Forward EPS Growth Proxy Had a Similar Aggregation Risk

The previous `ForwardEPSGrowthProxyPct` used a market-cap weighted average of each component's forward EPS growth:

```text
average(weight * (forward_eps / trailing_eps - 1))
```

That can overstate an index-level earnings growth proxy when low-base companies have extreme per-share growth rates.

Using the same current yfinance component data:

- Old component-weighted forward EPS growth proxy: `74.63%`
- Aggregate earnings proxy: `48.15%`

The corrected formula is:

```text
sum(market_cap / forward_pe) / sum(market_cap / trailing_pe) - 1
```

This remains a proxy, not an official NDX aggregate earnings-growth estimate.

## Finding 3: Similar L4 Component Metrics

Current status after review:

- `PE`: uses `covered_market_cap / covered_trailing_earnings`; cross-checked against WorldPERatio, Trendonify and DanjuanFunds; may be core only while the cross-check is clean.
- `ForwardPE`: uses `covered_market_cap / covered_forward_earnings`; cross-checked against Trendonify forward PE; may be core only while the cross-check is clean.
- `EarningsYield` and `ForwardEarningsYield`: derived from the cross-checked PE/Forward PE aggregates.
- `FCFYield`: uses `covered_fcf / covered_market_cap`; no official NDX aggregate or third-party cross-check; supporting-only.
- `PriceToBook`: now uses `covered_market_cap / covered_implied_book_equity`; supporting-only and shown through third-party PB when available.
- `ForwardEPSGrowthProxyPct`: now uses aggregate forward/trailing earnings proxy; supporting-only.
- `WeightedEarningsGrowthPct`, `WeightedRevenueGrowthPct`, margin fields: yfinance component proxy fields; supporting-only because they may mix quarterly/annual conventions, accounting regimes and sector structures.

## Follow-Up Risk

The L4 yfinance component path is still slow and repeated within one run. Three functions currently call the same 101-component fundamentals collection path. That increases runtime and can increase intra-run inconsistency if provider data or cache state changes during the run. A later improvement should cache the component fundamentals snapshot once per run and share it across L4 functions.

