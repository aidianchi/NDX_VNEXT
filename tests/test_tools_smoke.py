# tests/test_tools_smoke.py
"""Smoke tests for tools_L1.py ~ tools_L5.py — verify imports, signatures, and registry coverage."""

import sys
import os
import inspect

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))


# ---------------------------------------------------------------------------
# Registry completeness
# ---------------------------------------------------------------------------

def test_tools_registry_has_all_layer_functions():
    from core.collector import DataCollector
    from tools import TOOLS_REGISTRY

    collector = DataCollector()
    missing = []
    for layer_num, functions in collector.LAYER_FUNCTIONS.items():
        for func_name in functions:
            if func_name not in TOOLS_REGISTRY:
                missing.append(func_name)
    assert not missing, f"Missing from TOOLS_REGISTRY: {missing}"


def test_tools_registry_entries_are_callable():
    from tools import TOOLS_REGISTRY

    non_callable = []
    for name, fn in TOOLS_REGISTRY.items():
        if fn is None:
            continue  # conceptual keys like "masters_perspective"
        if not callable(fn):
            non_callable.append(name)
    assert not non_callable, f"Non-callable registry entries: {non_callable}"


# ---------------------------------------------------------------------------
# Importability: key functions per file (file-based, not layer-based)
# ---------------------------------------------------------------------------

def test_l1_file_functions_importable():
    """tools_L1.py contains L1 macro + L2 sentiment functions."""
    from tools_L1 import (
        get_fed_funds_rate,
        get_10y_real_rate,
        get_10y_treasury,
        get_vix,
        get_hy_oas_bp,
        get_copper_gold_ratio,
    )
    assert callable(get_fed_funds_rate)
    assert callable(get_vix)


def test_l2_file_functions_importable():
    """tools_L2.py contains L3 breadth / internals functions."""
    from tools_L2 import (
        get_advance_decline_line,
        get_percent_above_ma,
        get_ndx_ndxe_ratio,
        get_qqq_qqew_ratio,
        get_new_highs_lows,
        get_cnn_fear_greed_index,
    )
    assert callable(get_advance_decline_line)
    assert callable(get_percent_above_ma)
    assert callable(get_ndx_ndxe_ratio)


def test_l3_file_functions_importable():
    """tools_L3.py contains concentration / top10 functions."""
    from tools_L3 import (
        get_qqq_top10_concentration,
        get_m7_fundamentals,
    )
    assert callable(get_qqq_top10_concentration)
    assert callable(get_m7_fundamentals)


def test_l4_file_functions_importable():
    """tools_L4.py contains valuation functions."""
    from tools_L4 import (
        get_ndx_pe_and_earnings_yield,
        get_equity_risk_premium,
        get_damodaran_us_implied_erp,
    )
    assert callable(get_ndx_pe_and_earnings_yield)
    assert callable(get_equity_risk_premium)


def test_l5_file_functions_importable():
    """tools_L5.py contains technical indicator functions."""
    from tools_L5 import (
        get_qqq_technical_indicators,
        get_rsi_qqq,
        get_atr_qqq,
        get_adx_qqq,
        get_macd_qqq,
    )
    assert callable(get_qqq_technical_indicators)
    assert callable(get_rsi_qqq)


# ---------------------------------------------------------------------------
# Signature: all registry functions accept end_date
# ---------------------------------------------------------------------------

def test_registry_functions_accept_end_date():
    from tools import TOOLS_REGISTRY

    missing_end_date = []
    for name, fn in TOOLS_REGISTRY.items():
        if fn is None:
            continue
        sig = inspect.signature(fn)
        params = list(sig.parameters.keys())
        if "end_date" not in params:
            missing_end_date.append(name)
    # Functions that legitimately do not accept end_date:
    # - get_ndx_valuation_third_party_checks: no-arg helper
    expected_exceptions = {
        "get_ndx_valuation_third_party_checks",
    }
    unexpected = [name for name in missing_end_date if name not in expected_exceptions]
    assert not unexpected, f"Functions missing end_date param: {unexpected}"
