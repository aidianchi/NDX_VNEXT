from __future__ import annotations

from typing import Dict

"""Evidence-family map for DataIntegrity's family-weighted confidence score.

Background (investigation_reports/20260711_first_principles, finding GOV-04,
P0): DataIntegrity used to score "confidence" by counting each collector
function as one equal vote. That over-counts evidence diversity wherever
several functions merely re-transform the same underlying data feed (all 11
Layer 5 technical indicators read the same QQQ OHLCV history) and
under-counts it wherever one function quietly synthesizes several
independent official series into a single number (get_net_liquidity_momentum
combines three FRED series -- WALCL, WTREGEN, RRPONTSYD -- into one vote).

The fix: group function_ids into "evidence families" -- independent
underlying evidence streams -- and let DataIntegrity score at the family
level (each family contributes at most one full point, shared equally among
its present members) while still reporting the old function-level number
alongside it for transparency. See core.checker.DataIntegrity.run for the
math; this module only owns the mapping.

Grouping principle: a family is one independent underlying evidence stream.
- Different mathematical transforms of the *same* underlying series/dataset
  (e.g. RSI, ATR, MACD all computed from the same QQQ daily OHLCV) must share
  a family -- they are not independent confirmations of anything.
- Different series with different economic content stay in separate
  families even when they share a data provider (e.g. Wind's NDX valuation
  snapshot vs. Wind's NDX earnings-revision vintages: same provider, but one
  is a valuation-multiple level and the other is an earnings-revision trend
  -- genuinely different evidence).
- When it is unclear whether two functions share an underlying stream, this
  map defaults to keeping them in separate (singleton) families. A singleton
  family behaves exactly like the old function-level scoring for that one
  function, so guessing "separate" never fabricates diversity that isn't
  there; guessing "merged" could.

Every function_id in core.collector.DataCollector.LAYER_FUNCTIONS must have
an explicit entry here (enforced by tests/test_evidence_families.py's
mapping-completeness check) -- no function is allowed to rely silently on
the family_of() singleton fallback below.
"""

EVIDENCE_FAMILIES: Dict[str, str] = {
    # ============================================================
    # Layer 1 -- macro-economic conditions
    # ============================================================
    # FRED publishes T10Y2Y as its own series (a yield-curve-slope /
    # recession signal); it is not this module's derivation of DGS10 minus
    # DGS2, and it answers a different question than the level series below,
    # so it gets its own family even though both ultimately touch Treasury
    # yields.
    "get_10y2y_spread_bp": "treasury_10y_2y_curve_spread",
    # FRED FEDFUNDS -- the already-realized official policy rate.
    "get_fed_funds_rate": "fed_funds_rate_official",
    # Anchored by the work order: CME Fed funds futures implied-rate path is
    # a forward-looking market-pricing voice, independent of the realized
    # official rate above -- must not be merged with get_fed_funds_rate.
    "get_fed_funds_rate_path": "fed_funds_futures",
    "get_m2_yoy": "m2_money_supply",  # FRED M2SL
    # WALCL - WTREGEN - RRPONTSYD: three independent FRED series synthesized
    # into one function. It stays a singleton family here because no other
    # LAYER_FUNCTIONS entry re-uses any of its three components -- the
    # function-level *under*-counting GOV-04 flagged for this function is a
    # known limitation of a function->family (not series->family) map, and
    # is out of scope for this ticket.
    "get_net_liquidity_momentum": "fed_net_liquidity_composite",
    "get_copper_gold_ratio": "copper_gold_commodity_ratio",  # yfinance HG=F / GC=F
    "get_10y_treasury": "treasury_10y_nominal_yield",  # FRED DGS10
    "get_10y_real_rate": "treasury_10y_real_yield",  # FRED DFII10
    "get_10y_breakeven": "treasury_10y_breakeven_inflation",  # FRED T10YIE

    # ============================================================
    # Layer 2 -- market risk appetite
    # ============================================================
    # Anchored: VIX, VXN, their ratio, and the VIX3M/VIX term structure all
    # read the same underlying CBOE volatility-index surface
    # (^VIX/^VXN/^VIX3M/^VIX6M) -- different transforms of one volatility
    # evidence stream, not independent confirmations.
    "get_vix": "volatility_indices",
    "get_vxn": "volatility_indices",
    "get_vxn_vix_ratio": "volatility_indices",
    "get_vix_term_structure": "volatility_indices",
    "get_hy_oas_bp": "hy_credit_oas",  # FRED BAMLH0A0HYM2
    "get_ig_oas_bp": "ig_credit_oas",  # FRED BAMLC0A0CM
    # CCC-and-lower vs. BB OAS reads two different FRED series
    # (BAMLH0A3HYC, BAMLH0A1HYBB) than either OAS level above -- a distinct
    # credit-quality-tiering signal, not a repeat of HY/IG OAS.
    "get_hy_quality_spread_bp": "hy_credit_quality_spread",
    # HYG is a tradable ETF price used as a real-time credit proxy, sourced
    # from yfinance rather than FRED OAS. It answers a similar economic
    # question to the OAS families but through a structurally different
    # (price-based, not spread-based) instrument, so it is kept separate.
    "get_hyg_momentum": "hyg_price_momentum_proxy",
    "get_xly_xlp_ratio": "xly_xlp_consumer_ratio",  # yfinance XLY / XLP
    # SKEW index + QQQ put/call OI + QQQ short interest are bundled inside
    # one function; kept a singleton family (default per the module
    # docstring) since no sibling LAYER_FUNCTIONS entry re-uses any of its
    # three internal legs.
    "get_crowdedness_dashboard": "positioning_crowdedness_dashboard",
    "get_cftc_nq_positioning": "cftc_nasdaq100_futures_positioning",
    "get_finra_margin_debt": "finra_broad_market_margin_leverage",
    "get_cnn_fear_greed_index": "cnn_fear_greed_composite",

    # ============================================================
    # Layer 3 -- index internal health
    # ============================================================
    # Anchored: the breadth quartet all derive from the same NDX100
    # constituent daily-close price panel
    # (_get_ndx100_common_price_data / yfinance), differing only in which
    # aggregation (advance/decline, % above MA, new highs/lows, McClellan)
    # they compute from it.
    "get_advance_decline_line": "ndx_constituent_price_panel",
    "get_percent_above_ma": "ndx_constituent_price_panel",
    "get_new_highs_lows": "ndx_constituent_price_panel",
    "get_mcclellan_oscillator_nasdaq_or_nyse": "ndx_constituent_price_panel",
    # ^NDX / ^NDXE are index-level tickers (cap-weighted vs. equal-weighted
    # NDX100 index levels), not the per-constituent breadth panel above --
    # a different fetch and a different economic reading (concentration
    # skew, not participation breadth).
    "get_ndx_ndxe_ratio": "ndx_ndxe_cap_equal_weight_ratio",
    # Invesco's official QQQ holdings API -- a licensed-provider snapshot,
    # unrelated to the yfinance constituent price panel above.
    "get_qqq_top10_concentration": "qqq_invesco_official_holdings",

    # ============================================================
    # Layer 4 -- index fundamental valuation
    # ============================================================
    # Wind's NDX valuation snapshot (PE/PB/PS/risk-premium *level* at a
    # point in time) and Wind's NDX point-in-time consensus EPS-revision
    # vintages are both Wind-sourced but answer different economic
    # questions (valuation level vs. earnings-revision dynamics) -- kept
    # separate per the module docstring's "same provider can still be
    # different families" rule.
    "get_ndx_wind_valuation_snapshot": "ndx_wind_valuation_snapshot",
    "get_ndx_wind_point_in_time_earnings_expectations": "ndx_wind_earnings_expectations",
    # Split ruling (2026-07-14 主审裁决): in production-default configuration
    # get_ndx_pe_and_earnings_yield anchors on History-of-Market (Bloomberg
    # BEst attribution) while get_ndx_forward_earnings_quality self-computes
    # from the shared NDX-constituent fundamentals snapshot
    # (get_ndx_components_data_yf_v5) -- two genuinely different evidence
    # streams (the 20260712 live run proved it: one survived via HoM while
    # the other failed via the component snapshot). They only converge when
    # NDX_ENABLE_COMPONENT_MODEL=1 is explicitly set, which is not the
    # production default, so the static mapping follows the default paths.
    "get_ndx_pe_and_earnings_yield": "ndx_history_of_market_valuation",
    "get_ndx_forward_earnings_quality": "ndx_component_self_computed_valuation",
    # Anchored: one of the three independent ERP voices -- NDX's own simple
    # yield gap (earnings/FCF yield minus 10Y Treasury). Kept independent of
    # the Wind snapshot's risk_premium field and of Damodaran's academic
    # estimate below even though it consumes both as internal inputs, per
    # the work order's explicit "三个 ERP 声部各自独立家族" instruction.
    "get_equity_risk_premium": "ndx_simple_yield_gap_erp",
    "get_m7_capex_cycle": "m7_capex_cycle",  # SEC XBRL / Yahoo fallback
    # Anchored: second independent ERP voice -- external NYU Stern academic
    # implied-ERP estimate, not NDX-specific.
    "get_damodaran_us_implied_erp": "damodaran_implied_erp",
    # Not yet present in collector.LAYER_FUNCTIONS as of this ticket (a
    # parallel work stream is adding these two L4 functions). Mapped ahead
    # of time per the work order so the completeness test keeps passing the
    # moment they land; harmless no-op until then.
    "get_m7_earnings_blackout_calendar": "corporate_earnings_calendar",
    "get_m7_buyback_flow": "corporate_buyback_flow",

    # ============================================================
    # Layer 5 -- price trend & volatility
    # ============================================================
    # Anchored: all 11 functions read the same QQQ OHLCV history
    # (_fetch_qqq_history / TimeSeriesManager) and differ only in which
    # technical transform (RSI, ATR, ADX, MACD, OBV, ...) they apply to it
    # -- the textbook same-underlying-series case this rework exists to fix.
    "get_l5_deterministic_snapshot": "qqq_ohlcv_technical",
    "get_qqq_technical_indicators": "qqq_ohlcv_technical",
    "get_rsi_qqq": "qqq_ohlcv_technical",
    "get_atr_qqq": "qqq_ohlcv_technical",
    "get_adx_qqq": "qqq_ohlcv_technical",
    "get_macd_qqq": "qqq_ohlcv_technical",
    "get_obv_qqq": "qqq_ohlcv_technical",
    "get_volume_analysis_qqq": "qqq_ohlcv_technical",
    "get_price_volume_quality_qqq": "qqq_ohlcv_technical",
    "get_donchian_channels_qqq": "qqq_ohlcv_technical",
    "get_multi_scale_ma_position": "qqq_ohlcv_technical",
}


def family_of(function_id: str) -> str:
    """Return the evidence family for a function_id.

    Unmapped function_ids (a future indicator added without an explicit
    mapping here, or a synthetic/test function_id) fall back to a singleton
    family keyed by the function_id itself. This keeps every existing
    synthetic test fixture's expected confidence number unchanged (an
    unmapped id counts as its own one-member family, identical to the old
    function-level denominator for that item) and fails safe: an unmapped
    indicator is never silently folded into someone else's family and
    diluted there.
    """
    return EVIDENCE_FAMILIES.get(function_id, function_id)
