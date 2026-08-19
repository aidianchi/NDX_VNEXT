"""T36：metric_authority / MetricAuthority 登记表键名对齐真实顶层字段名。

真实事故背景（investigation_reports/20260728_single_source_audit/FINDINGS.md）：
子引用（`L4.func#field`）的合法名单来自各数据函数自报的 metric_authority 登记表，
但登记表历史上用的是"概念分组名"（如 path_0_6m、companies_sec_xbrl、
estimated_blackout_state、m7_aggregate_and_yoy），跟函数 value 里真实的顶层
字段名（path、companies、per_ticker、m7_quarterly_total...）是两套词汇。模型
照着原始数据诚实写出真实字段名，反而会被 `_validate_stage_evidence_refs`
（thesis / reviser / final 走 `synthesis_packet.evidence_index` 白名单）判定
"证据缺失"——底层数据完好，只是登记表的名字对不上。T35 先修了 bridge 段走的
`_run_schema_guard`；这份文件锁住 T36 修的另一半：thesis/final/reviser 走的
`evidence_index` 白名单，其 `#field` 条目由 `_field_authority_from_payload`
（读 value["MetricAuthority"] / data_quality["metric_authority"]）构造。

本文件锁住三件事（对应 T36 验收清单）：
1. 对齐断言：每个改过的函数，调用真实函数产出的 metric_authority 的键，必须能
   在该函数真实返回的 value 顶层键里找到（除非有下面文档化的例外）。
2. 不回归：这些函数的 field_usages 集合（usage 种类）不因本次改动引入新的
   mixed_field_authority——通过直接断言 metric_authority 的键集合和每个 usage
   保持预期值来锁定，而不是重新发明一套判定。
3. 端到端：`L4.get_m7_buyback_flow#m7_quarterly_total` 这条 ref 现在能通过
   evidence_index 白名单闸门（`_validate_stage_evidence_refs` 路径）——这正是
   FINDINGS.md 记录的真实事故复现（模型写的是 m7_quarterly_total，登记表当时
   叫 m7_aggregate_and_yoy，被误判违规）。

文档化例外（不是本次要修的错位，是结构性限制，不是遗漏）：
- `L4.get_m7_capex_cycle` 的 `yoy_acceleration`：真实路径是
  `value["m7_aggregate"]["yoy_acceleration"]`，是嵌套字段而不是顶层键。子引用
  体系（`_field_authority_from_payload` / `evidence_index`）只认顶层键。把它
  折进已经存在的顶层键 "m7_aggregate" 会产生两难：全 SEC 场景下 m7_aggregate
  本身可以是 core_allowed，但 yoy_acceleration 的语义要求它恒为
  supporting_only——折进去要么错误放宽 yoy_acceleration，要么错误拖累
  m7_aggregate 的原始聚合数字，两种都违反"usage 逐条原样沿用"的红线。保留原样，
  不发明一个不存在的顶层键（tools_L4.py 里这一行本次未改动）。
- `L2.get_crowdedness_dashboard` 的 `status`：登记表在 `src/data_evidence.py`
  的 `WEAK_METRIC_AUTHORITY_POLICIES` 里（不是 tools_L1/L2/L4.py 的领地），且
  该函数当前实现的 value 里没有任何叫 status 的字段（顶层、嵌套都没有）——不是
  "名字起错了"，是这个概念目前根本没有对应的真实产出。凭空发明一个顶层键会
  违反"不得编造不存在的字段"，因此本次不改，留档待后续评估（本文件不覆盖这个
  函数，因为它不在本次改动范围内，没有代码变化可供红灯/绿灯对照）。
"""

import os
import sys
from datetime import date, datetime, timedelta

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import tools_L1 as l1
import tools_L2 as l2
import tools_L4
from agent_analysis.contracts import (
    AnalysisPacket,
    Confidence,
    ContextBrief,
    CoreFact,
    IndicatorAnalysis,
    LayerCard,
)
from agent_analysis.orchestrator import VNextOrchestrator


def _assert_metric_authority_aligned(value, metric_authority, *, known_exceptions=frozenset()):
    """metric_authority 的每个键，要么是 value 的真实顶层键，要么是文档化例外。

    这是防止"登记表词汇 != 真实字段词汇"复发的核心闸门：任何新引入的错位键都会
    在这里立刻显形，而不是等到某次真实 thesis/reviser run 里才被 evidence_index
    白名单挡下。
    """
    top_level_keys = set(value)
    registered_keys = set(metric_authority)
    unaligned = (registered_keys - top_level_keys) - set(known_exceptions)
    assert not unaligned, (
        f"metric_authority keys not found among real top-level value keys "
        f"(and not a documented exception): {sorted(unaligned)}; "
        f"real top-level keys were: {sorted(top_level_keys)}"
    )


# ---------------------------------------------------------------------------
# L1.get_fed_funds_rate_path
# ---------------------------------------------------------------------------

FED_FUNDS_END_DATE = "2026-07-10"


def _fed_funds_contract_map(end_date=FED_FUNDS_END_DATE):
    anchor = datetime.strptime(end_date, "%Y-%m-%d")
    result = {}
    for months_ahead in range(13):
        year, month = l1._fed_funds_month_at_offset(anchor, months_ahead)
        result[months_ahead] = l1._fed_funds_contract_for_month(year, month)
    return result


def _fed_funds_daily_frame(close, volume, end_date=FED_FUNDS_END_DATE):
    end = datetime.strptime(end_date, "%Y-%m-%d")
    dates = [end - timedelta(days=offset) for offset in range(9, -1, -1)]
    return pd.DataFrame(
        {"Close": [close] * 10, "Volume": [volume] * 10},
        index=pd.DatetimeIndex(dates, name="Date"),
    )


def _install_fed_funds_mocks(monkeypatch, end_date=FED_FUNDS_END_DATE):
    contracts = _fed_funds_contract_map(end_date)
    frames = {
        contract: _fed_funds_daily_frame(96.0 - offset * 0.01, 1000.0, end_date=end_date)
        for offset, contract in contracts.items()
    }

    def fake_download(ticker, **_kwargs):
        frame = frames.get(ticker)
        return frame.copy() if frame is not None else pd.DataFrame()

    def fake_fred(series_id, days=60, end_date=None):
        assert series_id == "EFFR"
        return pd.DataFrame({"date": [pd.Timestamp(end_date or FED_FUNDS_END_DATE)], "value": [4.0]})

    monkeypatch.setattr(l1, "cached_yf_download", fake_download)
    monkeypatch.setattr(l1, "get_fred_series", fake_fred)


def test_fed_funds_rate_path_metric_authority_keys_match_real_value_fields(monkeypatch):
    """红灯锚点（改前失败原因）：metric_authority 里的 path_0_6m / path_7_12m /
    slope_12m_and_cuts_priced_bps 在 value 顶层查不到——真实顶层键是
    path / slope_12m / cuts_priced_bps。"""
    _install_fed_funds_mocks(monkeypatch)
    result = l1.get_fed_funds_rate_path(FED_FUNDS_END_DATE)

    assert result["availability"] == "available"
    value = result["value"]
    metric_authority = result["data_quality"]["metric_authority"]

    _assert_metric_authority_aligned(value, metric_authority)
    assert set(metric_authority) == {"path", "state", "slope_12m", "cuts_priced_bps", "effr_anchor"}
    # usage 集合改动前后不变：{supporting_only, cross_check_only}，两档，不是新引入的 mixed。
    assert {rule["usage"] for rule in metric_authority.values()} == {"supporting_only", "cross_check_only"}


# ---------------------------------------------------------------------------
# L2.get_vix_term_structure (defined in tools_L2.py; L2 is the evidence-ref
# layer label per core.collector.DataCollector.LAYER_FUNCTIONS[2])
# ---------------------------------------------------------------------------

def _vix_series(dates, values):
    return pd.DataFrame({"date": [pd.to_datetime(d) for d in dates], "value": list(values)})


def _vix_daily_dates(start, n):
    start_dt = date.fromisoformat(start)
    return [(start_dt + timedelta(days=i)).isoformat() for i in range(n)]


def test_vix_term_structure_metric_authority_keys_match_real_value_fields(monkeypatch):
    """红灯锚点（改前失败原因）：metric_authority 里的 vix6m_leg 在 value 顶层查不到
    ——真实顶层键是 vix6m。"""
    n = 40
    dates = _vix_daily_dates("2024-01-01", n)
    vix_df = _vix_series(dates, [20.0] * n)
    vix3m_df = _vix_series(dates, [20.0 + i * 0.05 for i in range(n)])
    vix6m_df = _vix_series(dates, [22.0 + i * 0.05 for i in range(n)])

    def fake_get_series(series_id, update_func, end_date):
        return {"VIX": vix_df, "VIX3M": vix3m_df, "VIX6M": vix6m_df}[series_id].copy()

    monkeypatch.setattr(l2, "_get_series_for_effective_date", fake_get_series)
    monkeypatch.setattr(
        l2,
        "VIX_TERM_STRUCTURE_PERCENTILE_WINDOWS",
        {
            "5y": {"years": 5, "min_observations": 20, "min_span_days": 10},
            "10y": {"years": 10, "min_observations": 20, "min_span_days": 10},
        },
    )

    result = l2.get_vix_term_structure(end_date=None)

    assert result["availability"] == "available"
    value = result["value"]
    metric_authority = result["data_quality"]["metric_authority"]

    _assert_metric_authority_aligned(value, metric_authority)
    assert set(metric_authority) == {"term_structure_state", "percentile_context", "vix6m"}
    assert {rule["usage"] for rule in metric_authority.values()} == {"supporting_only", "supplementary_only"}


# ---------------------------------------------------------------------------
# L4.get_m7_capex_cycle
# ---------------------------------------------------------------------------

def _capex_quarter_fact(period_end, value):
    end_dt = date.fromisoformat(period_end)
    start_dt = end_dt - timedelta(days=90)
    return {
        "start": start_dt.isoformat(),
        "end": period_end,
        "val": value,
        "filed": (end_dt + timedelta(days=25)).isoformat(),
        "form": "10-K" if end_dt.month == 12 else "10-Q",
        "fy": None,
        "fp": None,
        "accn": f"acc-{period_end}",
    }


def _capex_series(quarters):
    return {"units": {"USD": [_capex_quarter_fact(period_end, value) for period_end, value in quarters]}}


AAPL_CAPEX_QUARTERS = [
    ("2024-03-31", 10_000_000_000), ("2024-06-30", 12_000_000_000),
    ("2024-09-30", 14_000_000_000), ("2024-12-31", 16_000_000_000),
    ("2025-03-31", 13_000_000_000), ("2025-06-30", 15_000_000_000),
    ("2025-09-30", 17_000_000_000), ("2025-12-31", 18_000_000_000),
]


def test_m7_capex_cycle_metric_authority_keys_match_real_value_fields_sec_only(monkeypatch):
    """红灯锚点（改前失败原因）：metric_authority 里的 companies_sec_xbrl 在 value
    顶层查不到——真实顶层键是 companies。yoy_acceleration 是文档化例外（见模块
    docstring），本测试显式声明它，不让它悄悄通过。"""
    tag = tools_L4.M7_CAPEX_XBRL_TAG_CANDIDATES[0]
    monkeypatch.setattr(tools_L4, "_sec_cik_map", lambda: {"AAPL": "0000320193"})

    def fake_fetch(cik, requested_tag):
        if (cik, requested_tag) == ("0000320193", tag):
            return _capex_series(AAPL_CAPEX_QUARTERS), None
        return {}, "tag_not_reported"

    monkeypatch.setattr(tools_L4, "_fetch_sec_xbrl_companyconcept", fake_fetch)

    result = tools_L4.get_m7_capex_cycle(end_date="2026-07-10")

    assert result["availability"] == "available"
    value = result["value"]
    metric_authority = result["data_quality"]["metric_authority"]

    known_nested_exceptions = {"yoy_acceleration"}
    _assert_metric_authority_aligned(value, metric_authority, known_exceptions=known_nested_exceptions)
    assert set(metric_authority) == {"companies", "m7_aggregate", "yoy_acceleration"}
    assert metric_authority["companies"]["usage"] == "core_allowed"
    assert metric_authority["m7_aggregate"]["usage"] == "core_allowed"
    assert metric_authority["yoy_acceleration"]["usage"] == "supporting_only"


def test_m7_capex_cycle_metric_authority_companies_key_downgrades_when_fallback_only(monkeypatch):
    """companies_sec_xbrl / companies_yfinance_fallback 合并进单一顶层键 "companies"
    后，当唯一可用渠道是 Yahoo fallback 时，合并后的 "companies" 必须继承原
    companies_yfinance_fallback 的 supporting_only/third-party 措辞，不能悄悄
    冒充 core_allowed。"""
    monkeypatch.setattr(tools_L4, "_sec_cik_map", lambda: {})

    def fake_yfinance(ticker):
        if ticker != "MSFT":
            return [], "yfinance_quarterly_cashflow_empty"
        return [
            {"period_end": "2024-12-31", "value": 16_000_000_000.0},
            {"period_end": "2025-12-31", "value": 20_000_000_000.0},
        ], None

    monkeypatch.setattr(tools_L4, "_fetch_yfinance_capex_quarterly", fake_yfinance)

    result = tools_L4.get_m7_capex_cycle(end_date=None)
    value = result["value"]
    metric_authority = result["data_quality"]["metric_authority"]

    known_nested_exceptions = {"yoy_acceleration"}
    _assert_metric_authority_aligned(value, metric_authority, known_exceptions=known_nested_exceptions)
    assert metric_authority["companies"]["usage"] == "supporting_only"
    assert metric_authority["companies"]["authority"] == "yahoo_normalized_cashflow_third_party_unofficial"


def test_m7_capex_cycle_mixed_channel_collapses_to_one_usage_tier_without_granting_authority(monkeypatch):
    """钉住合并 companies_sec_xbrl/companies_yfinance_fallback 带来的**行为变化**，
    使它是一个被记录的选择，而不是一次没人发现的副作用。

    改动前：混合渠道（部分公司走 SEC、部分回落 Yahoo）会同时登记 core_allowed 的
    `companies_sec_xbrl` 和 supporting_only 的 `companies_yfinance_fallback`
    → usage 两档 → `orchestrator.py` 的 `mixed_field_authority` 命中 → 父级 passport
    `verified=False` 并追加降级规则。
    改动后：只有一条 `companies`，取更保守的一档，混合渠道下全站 usage 收敛为一档
    → 那面 mixed 旗不再升起。

    **为什么判定这不是放松**：真正要防的是"弱字段冒充强证据"。混合渠道下现在
    **没有任何字段是 core_allowed**（旧写法里 `#companies_sec_xbrl` 反而可以被当作
    core 引用）。字段级更严了，只有容器那面旗降了——而那面旗本来就是同一个真实字段
    被登记两次、两个 usage 撞出来的假阳性。本测试同时断言这两件事，任何一条被改动
    都会红。
    """
    tag = tools_L4.M7_CAPEX_XBRL_TAG_CANDIDATES[0]
    monkeypatch.setattr(tools_L4, "_sec_cik_map", lambda: {"AAPL": "0000320193"})

    def fake_fetch(cik, requested_tag):
        if (cik, requested_tag) == ("0000320193", tag):
            return _capex_series(AAPL_CAPEX_QUARTERS), None
        return {}, "tag_not_reported"

    def fake_yfinance(ticker):
        if ticker != "MSFT":
            return [], "yfinance_quarterly_cashflow_empty"
        return [
            {"period_end": "2024-12-31", "value": 16_000_000_000.0},
            {"period_end": "2025-12-31", "value": 20_000_000_000.0},
        ], None

    monkeypatch.setattr(tools_L4, "_fetch_sec_xbrl_companyconcept", fake_fetch)
    monkeypatch.setattr(tools_L4, "_fetch_yfinance_capex_quarterly", fake_yfinance)

    # end_date=None 才是 live context——yfinance 回落只在 live 下触发（见
    # tools_L4.py 的 `if not sec_series: if is_live_context:` 分支）；传历史日期
    # 会走回测路径、根本不回落，那样就构造不出"混合渠道"这个待钉住的场景。
    result = tools_L4.get_m7_capex_cycle(end_date=None)
    metric_authority = result["data_quality"]["metric_authority"]
    usages = {rule["usage"] for rule in metric_authority.values()}
    sources = {c.get("primary_source") for c in result["value"]["companies"].values()}
    assert "yfinance_fallback" in sources, f"前提没成立：这一跑并没有回落渠道，实际 {sources}"
    assert "sec_xbrl" in sources, f"前提没成立：这一跑没有 SEC 渠道公司，实际 {sources}"

    assert "core_allowed" not in usages, (
        f"混合渠道下不许有任何字段是 core_allowed，实际：{ {k: v['usage'] for k, v in metric_authority.items()} }"
    )
    assert usages == {"supporting_only"}, (
        f"混合渠道下 usage 应收敛为一档 supporting_only，实际：{sorted(usages)}"
    )


# ---------------------------------------------------------------------------
# L4.get_m7_earnings_blackout_calendar
# ---------------------------------------------------------------------------

def _blackout_mock_dates(monkeypatch, dates_by_ticker):
    def fake_fetch(ticker):
        dates = dates_by_ticker.get(ticker, [])
        return (
            [{"date": item, "endpoint": "get_earnings_dates"} for item in dates],
            {"attempted_endpoints": ["mock"]},
            None,
        )

    monkeypatch.setattr(tools_L4, "_fetch_yfinance_earnings_dates", fake_fetch)


def test_m7_earnings_blackout_calendar_metric_authority_keys_match_real_value_fields(monkeypatch):
    """红灯锚点（改前失败原因）：metric_authority 里唯一的键 estimated_blackout_state
    在 value 顶层查不到——真实顶层键拆成 per_ticker / m7_in_blackout_count /
    m7_in_blackout_share_equal_weight / upcoming_28d_calendar 四个。"""
    _blackout_mock_dates(monkeypatch, {ticker: ["2026-07-14"] for ticker in tools_L4.M7_TICKERS})

    result = tools_L4.get_m7_earnings_blackout_calendar("2026-06-23")

    assert result["availability"] == "available"
    value = result["value"]
    metric_authority = result["data_quality"]["metric_authority"]

    _assert_metric_authority_aligned(value, metric_authority)
    assert set(metric_authority) == {
        "per_ticker",
        "m7_in_blackout_count",
        "m7_in_blackout_share_equal_weight",
        "upcoming_28d_calendar",
    }
    # usage 集合改动前后不变：拆分前后都只有一档 supporting_only，不引入 mixed。
    assert {rule["usage"] for rule in metric_authority.values()} == {"supporting_only"}


# ---------------------------------------------------------------------------
# L4.get_m7_buyback_flow
# ---------------------------------------------------------------------------

def _buyback_fact(period_end, value):
    end_dt = date.fromisoformat(period_end)
    return {
        "start": (end_dt - timedelta(days=90)).isoformat(),
        "end": period_end,
        "val": value,
        "filed": (end_dt + timedelta(days=25)).isoformat(),
        "form": "10-K" if end_dt.month == 12 else "10-Q",
        "accn": f"acc-{period_end}",
    }


def _buyback_payload(quarters):
    return {"units": {"USD": [_buyback_fact(period_end, value) for period_end, value in quarters]}}


def _install_buyback_sec(monkeypatch, quarters_by_ticker):
    cik_map = {ticker: f"{idx:010d}" for idx, ticker in enumerate(quarters_by_ticker, start=1)}
    tag = tools_L4.M7_BUYBACK_XBRL_TAG_CANDIDATES[0]
    payloads = {
        (cik_map[ticker], tag): _buyback_payload(quarters) for ticker, quarters in quarters_by_ticker.items()
    }
    monkeypatch.setattr(tools_L4, "_sec_cik_map", lambda: cik_map)

    def fake_fetch(cik, requested_tag):
        payload = payloads.get((cik, requested_tag))
        return (payload, None) if payload is not None else ({}, "tag_not_reported")

    monkeypatch.setattr(tools_L4, "_fetch_sec_xbrl_companyconcept", fake_fetch)


BUYBACK_EIGHT_QUARTERS = [
    ("2024-03-31", 1_000_000_000), ("2024-06-30", 2_000_000_000),
    ("2024-09-30", 3_000_000_000), ("2024-12-31", 4_000_000_000),
    ("2025-03-31", 2_000_000_000), ("2025-06-30", 3_000_000_000),
    ("2025-09-30", 4_000_000_000), ("2025-12-31", 5_000_000_000),
]


def _build_buyback_result_sec_only(monkeypatch):
    quarters = {ticker: BUYBACK_EIGHT_QUARTERS for ticker in tools_L4.M7_TICKERS}
    _install_buyback_sec(monkeypatch, quarters)
    return tools_L4.get_m7_buyback_flow("2026-07-10")


def test_m7_buyback_flow_metric_authority_keys_match_real_value_fields(monkeypatch):
    """红灯锚点（改前失败原因，即 FINDINGS.md 记录的真实事故本身）：metric_authority
    里的 actual_buyback_spending / m7_aggregate_and_yoy 在 value 顶层都查不到——
    真实顶层键是 per_company / m7_quarterly_total / m7_ttm_total / yoy_pct。模型
    照实写出 m7_quarterly_total 反而被判violates evidence_index 白名单。"""
    result = _build_buyback_result_sec_only(monkeypatch)

    assert result["availability"] == "available"
    value = result["value"]
    metric_authority = result["data_quality"]["metric_authority"]

    _assert_metric_authority_aligned(value, metric_authority)
    assert set(metric_authority) == {"per_company", "m7_quarterly_total", "m7_ttm_total", "yoy_pct"}
    assert {rule["usage"] for rule in metric_authority.values()} == {"supporting_only"}


def _empty_layer_card_with_indicator(layer, function_id, metric):
    return LayerCard(
        layer=layer,
        core_facts=[CoreFact(metric="placeholder", value="n/a")],
        local_conclusion=f"{layer} placeholder",
        confidence=Confidence.MEDIUM,
        indicator_analyses=[
            IndicatorAnalysis(
                function_id=function_id,
                metric=metric,
                narrative="占位叙事，仅用于驱动 evidence_index 构造。",
                reasoning_process="占位推理过程。",
                evidence_refs=[f"{layer}.{function_id}"],
                permission_type="fact",
                canonical_question="占位典范问题。",
                misread_guards=["占位误读防护。"],
                cross_validation_targets=[],
                falsifiers=["占位失效条件。"],
                core_vs_tactical_boundary="占位边界说明。",
            )
        ],
    )


def test_m7_buyback_flow_evidence_index_accepts_real_field_subref_end_to_end(monkeypatch, tmp_path):
    """端到端复现 FINDINGS.md 记录的真实事故并证明它已被修复：把 get_m7_buyback_flow
    的真实产出接进 _build_synthesis_packet，取得真实构造出的 evidence_index，然后
    验证 thesis/reviser/final 实际会走的 `_validate_stage_evidence_refs` 闸门放行
    `L4.get_m7_buyback_flow#m7_quarterly_total`——这条 ref 是模型"照实抄"value 顶层
    字段名会写出来的东西，改前会被判 invalid（键名是 m7_aggregate_and_yoy）。
    """
    result = _build_buyback_result_sec_only(monkeypatch)

    orchestrator = VNextOrchestrator(
        available_models=["fake"],
        output_dir=str(tmp_path),
        llm_engine=object(),
    )
    packet = AnalysisPacket(
        meta={"data_date": "2026-07-10"},
        raw_data={"L4": {"get_m7_buyback_flow": result}},
    )
    context = ContextBrief(data_summary="data", task_description="task")
    layer_cards = [_empty_layer_card_with_indicator("L4", "get_m7_buyback_flow", "M7 Actual Buyback Flow")]

    synthesis = orchestrator._build_synthesis_packet(packet, context, layer_cards, [])
    allowed_refs = set(synthesis.evidence_index.keys())

    assert "L4.get_m7_buyback_flow#m7_quarterly_total" in allowed_refs
    # 改前的登记表键名（m7_aggregate_and_yoy）不该作为子引用出现在索引里。
    assert "L4.get_m7_buyback_flow#m7_aggregate_and_yoy" not in allowed_refs

    candidate = {"evidence_refs": ["L4.get_m7_buyback_flow#m7_quarterly_total"]}
    errors = orchestrator._validate_stage_evidence_refs(candidate, allowed_refs, "thesis")
    assert errors == []
