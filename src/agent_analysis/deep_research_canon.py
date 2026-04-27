from __future__ import annotations

import json
from typing import Any, Dict, Iterable, List

try:
    from .contracts import IndicatorCanon, Layer, ObjectCanon, PermissionType, RegimeScenarioCanon
except ImportError:
    from contracts import IndicatorCanon, Layer, ObjectCanon, PermissionType, RegimeScenarioCanon


L3_STRUCTURAL_PRIORITY_FUNCTIONS = {
    "get_advance_decline_line",
    "get_percent_above_ma",
    "get_qqq_qqew_ratio",
    "get_new_highs_lows",
}


def _dump_model(value: Any) -> Dict[str, Any]:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if hasattr(value, "dict"):
        return value.dict()
    return dict(value)


def build_object_canon() -> ObjectCanon:
    """Return the static object definition shared by all layer analysts."""
    return ObjectCanon(
        primary_object="NDX",
        tradable_proxy="QQQ",
        equal_weight_reference="NDXE / QEW",
        object_summary=(
            "本系统主要判断 Nasdaq-100 指数 NDX 的研究状态；QQQ 只是常用可交易代理，"
            "NDXE/QEW 用来帮助观察等权口径下的集中度和广度。"
        ),
        methodology_boundaries=[
            "QQQ 不是所有科技股，也不是整个美股成长风格；它是 Nasdaq-100 的可交易 ETF 代理。",
            "NDX 是市值加权指数，头部公司权重很高；NDXE 或 QEW 更适合观察等权广度和集中度。",
            "QQQ/等权代理的强弱差异主要说明集中度和领导力质量，不直接说明宏观流动性或估值是否合理。",
            "指数规则、成分权重和 Top10 集中度会影响所有跨期比较，不能把指数表现等同于普通科技股篮子。",
        ],
        analysis_boundaries=[
            "L1-L5 只能使用本层运行时数据；ObjectCanon 只提供对象定义和静态口径。",
            "最终结论必须说明判断对象是 NDX、QQQ 暴露，还是等权 Nasdaq-100 口径。",
            "当 NDX 与等权口径明显背离时，系统必须保留集中度张力。",
        ],
        falsifiers=[
            "如果输入数据实际覆盖的不是 NDX/QQQ，而是其他宽基或行业篮子，需要重新定义对象。",
            "如果等权参考缺失，关于广度和集中度的判断必须降置信度。",
        ],
    )


def _indicator(
    function_id: str,
    metric_name: str,
    layer: Layer,
    permission_type: PermissionType,
    canonical_question: str,
    interpretation_rules: Iterable[str],
    misread_guards: Iterable[str],
    cross_validation_targets: Iterable[str],
    falsifiers: Iterable[str],
    core_vs_tactical_boundary: str,
    b_prompt: str,
    *,
    source_hint: str = "",
    frequency_hint: str = "",
) -> IndicatorCanon:
    return IndicatorCanon(
        function_id=function_id,
        metric_name=metric_name,
        layer=layer,
        permission_type=permission_type,
        source_hint=source_hint,
        frequency_hint=frequency_hint,
        canonical_question=canonical_question,
        interpretation_rules=list(interpretation_rules),
        misread_guards=list(misread_guards),
        cross_validation_targets=list(cross_validation_targets),
        falsifiers=list(falsifiers),
        core_vs_tactical_boundary=core_vs_tactical_boundary,
        b_prompt=b_prompt,
    )


INDICATOR_CANONS: Dict[str, IndicatorCanon] = {
    "get_10y_real_rate": _indicator(
        "get_10y_real_rate",
        "10Y Real Rate",
        Layer.L1,
        PermissionType.FACT,
        "真实贴现率是否正在给 NDX 的高久期盈利估值施压？",
        [
            "看水平、方向和历史分位；高位且上行通常压制成长股估值倍数。",
            "把它理解为未来现金流折现率的地心引力，而不是单日交易信号。",
        ],
        [
            "它不是单纯的政策变量，也不能独立证明股价必须下跌。",
            "不要用真实利率一个指标直接推出最终买卖建议。",
        ],
        ["get_ndx_pe_and_earnings_yield", "get_equity_risk_premium", "get_qqq_qqew_ratio"],
        [
            "盈利上修足以抵消折现率压力。",
            "市场广度改善且估值风险溢价同步修复。",
        ],
        "核心框架指标，主要约束估值承受力。",
        "真实利率高位=估值地心引力增强；必须看盈利和广度是否能抵消。",
        source_hint="Treasury/FRED real yield proxy",
        frequency_hint="daily",
    ),
    "get_fed_funds_rate": _indicator(
        "get_fed_funds_rate",
        "Fed Funds Rate",
        Layer.L1,
        PermissionType.FACT,
        "政策利率是否仍处于限制性区间，压制风险资产估值？",
        ["关注水平、政策方向和市场降息预期的差异。"],
        ["降息预期不是自动利好；需要区分软着陆降息和衰退式降息。"],
        ["get_10y_treasury", "get_10y_real_rate", "get_hy_oas_bp"],
        ["长端利率明显回落且信用利差未恶化。"],
        "核心框架指标，影响无风险收益率和流动性条件。",
        "政策利率说明资金价格，不直接给出 NDX 买卖点。",
    ),
    "get_10y_treasury": _indicator(
        "get_10y_treasury",
        "10Y Treasury Yield",
        Layer.L1,
        PermissionType.FACT,
        "名义长端利率是否改变股债相对吸引力和估值折现压力？",
        ["同时拆成真实利率和通胀预期，避免把名义利率当单一信号。"],
        ["名义利率上行可能来自增长，也可能来自通胀风险，含义不同。"],
        ["get_10y_real_rate", "get_10y_breakeven", "get_equity_risk_premium"],
        ["真实利率回落或盈利增长加速吸收利率压力。"],
        "核心框架指标，需与真实利率和盈余收益率一起看。",
        "十年期利率是资金价格温度计；要拆来源，不要只看涨跌。",
    ),
    "get_10y_breakeven": _indicator(
        "get_10y_breakeven",
        "10Y Breakeven Inflation",
        Layer.L1,
        PermissionType.PROXY,
        "通胀预期是否正在改变名义利率和政策约束的解释？",
        ["与真实利率组合判断：名义利率上行到底来自增长、通胀还是真实回报要求。"],
        ["它是市场隐含通胀代理，不是官方通胀事实。"],
        ["get_10y_treasury", "get_10y_real_rate", "get_fed_funds_rate"],
        ["真实利率稳定而盈亏平衡通胀回落，说明压力来源变化。"],
        "核心框架辅助指标，负责拆解利率来源。",
        "盈亏平衡通胀只回答通胀预期，不回答估值是否便宜。",
    ),
    "get_net_liquidity_momentum": _indicator(
        "get_net_liquidity_momentum",
        "Net Liquidity Momentum",
        Layer.L1,
        PermissionType.PROXY,
        "边际流动性是否正在改善或收紧风险资产的资金环境？",
        ["看边际变化比看绝对值更重要；需要与信用和波动确认。"],
        ["净流动性是代理指标，不是官方真理；不能压倒信用和价格证据。"],
        ["get_hy_oas_bp", "get_vix", "get_qqq_technical_indicators"],
        ["信用利差恶化或价格趋势破位抵消流动性改善。"],
        "核心框架辅助指标，主要描述资金环境边际变化。",
        "净流动性改善是顺风，不是免死金牌。",
    ),
    "get_hy_oas_bp": _indicator(
        "get_hy_oas_bp",
        "HY OAS",
        Layer.L2,
        PermissionType.FACT,
        "信用市场是否开始给风险偏好亮黄灯？",
        ["高收益利差走阔通常说明融资压力和风险补偿需求上升。"],
        ["股市波动低不能覆盖信用恶化；信用通常是更硬的风险约束。"],
        ["get_vix", "get_net_liquidity_momentum", "get_advance_decline_line"],
        ["利差收窄且广度改善，削弱风险退潮判断。"],
        "核心风险指标，优先级高于纯情绪读数。",
        "HY OAS 是信用压力表；走阔时要降低风险偏好结论的自信。",
    ),
    "get_vix": _indicator(
        "get_vix",
        "VIX",
        Layer.L2,
        PermissionType.PROXY,
        "标普期权市场的保险价格是否显示恐慌或过度平静？",
        ["高 VIX 是保险贵，低 VIX 是保险便宜；都需要信用和广度确认。"],
        ["VIX 高本身不是买入信号，VIX 低也不自动等于安全。"],
        ["get_hy_oas_bp", "get_vxn", "get_advance_decline_line"],
        ["信用利差同步恶化时，高 VIX 可能不是可买恐慌。"],
        "风险提醒指标，不能单独定义 regime。",
        "VIX 只说保险价格，不说资产价值。",
    ),
    "get_vxn": _indicator(
        "get_vxn",
        "VXN",
        Layer.L2,
        PermissionType.PROXY,
        "Nasdaq 相关波动是否比宽基市场更紧张？",
        ["与 VIX 比较可观察科技/成长暴露的相对压力。"],
        ["不能用 VXN 单独证明 NDX 基本面恶化。"],
        ["get_vix", "get_qqq_technical_indicators", "get_atr_qqq"],
        ["VXN 回落且趋势恢复，削弱短线压力判断。"],
        "风险提醒和短线执行指标。",
        "VXN 是 Nasdaq 保险价格；必须与 VIX 和价格结构一起看。",
    ),
    "get_advance_decline_line": _indicator(
        "get_advance_decline_line",
        "Advance Decline Line",
        Layer.L3,
        PermissionType.STRUCTURAL,
        "上涨是否由足够多的成分共同参与？",
        ["价格创新高但 A/D 走弱，说明领导力可能变窄。"],
        ["广度弱不等于立刻下跌，但会降低趋势质量。"],
        ["get_qqq_qqew_ratio", "get_qqq_technical_indicators", "get_hy_oas_bp"],
        ["A/D 修复且等权口径跟上，削弱窄幅领导风险。"],
        "结构健康指标，负责判断趋势质量。",
        "A/D 线回答参与度，不回答估值。",
    ),
    "get_qqq_qqew_ratio": _indicator(
        "get_qqq_qqew_ratio",
        "QQQ/QEW Ratio",
        Layer.L3,
        PermissionType.STRUCTURAL,
        "市值加权相对等权是否显示集中度风险上升？",
        ["比值上行说明头部权重贡献更大；要结合 Top10 和广度判断。"],
        ["集中度高不必然看空，但必须保留指数脆弱性。"],
        ["get_advance_decline_line", "get_qqq_technical_indicators", "get_ndx_pe_and_earnings_yield"],
        ["等权口径补涨且 A/D 改善，削弱集中度风险。"],
        "结构指标，负责 NDX 与等权 Nasdaq-100 的差异。",
        "QQQ/QEW 上行=头部更强；不是宏观宽松，也不是估值便宜。",
    ),
    "get_ndx_pe_and_earnings_yield": _indicator(
        "get_ndx_pe_and_earnings_yield",
        "NDX Valuation",
        Layer.L4,
        PermissionType.FACT,
        "NDX 当前估值是否给未来回报留下足够安全边际？",
        ["同时看 PE、盈利收益率、历史分位和盈利增长预期。"],
        ["高估值不是自动做空信号；它提高对盈利和利率环境的要求。"],
        ["get_10y_real_rate", "get_equity_risk_premium", "get_qqq_qqew_ratio"],
        ["盈利强劲上修或真实利率明显下行。"],
        "核心估值指标，负责判断价格相对盈利的要求有多高。",
        "高 PE 不是卖出理由；高 PE 加高真实利率才是核心冲突。",
    ),
    "get_equity_risk_premium": _indicator(
        "get_equity_risk_premium",
        "Equity Risk Premium",
        Layer.L4,
        PermissionType.COMPOSITE,
        "相对债券，持有 NDX 权益风险是否获得足够补偿？",
        ["ERP 低说明风险补偿薄，需要更强盈利和更低利率支持。"],
        ["ERP 是合成指标，对盈利收益率和利率输入很敏感。"],
        ["get_10y_treasury", "get_ndx_pe_and_earnings_yield", "get_hy_oas_bp"],
        ["盈利收益率改善或长端利率回落提升风险补偿。"],
        "核心估值-利率桥梁指标。",
        "ERP 低=安全垫薄；需要跨层确认风险是否值得承担。",
    ),
    "get_qqq_technical_indicators": _indicator(
        "get_qqq_technical_indicators",
        "QQQ Technical",
        Layer.L5,
        PermissionType.TECHNICAL,
        "价格趋势是否仍然完整，关键均线和动量是否支持执行？",
        ["均线、MACD 和价格结构用于判断执行节奏，不负责估值。"],
        ["技术趋势强不能证明基本面便宜或宏观顺风。"],
        ["get_advance_decline_line", "get_atr_qqq", "get_ndx_pe_and_earnings_yield"],
        ["跌破关键均线、动量转弱或广度无法确认。"],
        "短线执行和趋势状态指标。",
        "技术面回答何时做，不回答值不值得。",
    ),
    "get_rsi_qqq": _indicator(
        "get_rsi_qqq",
        "QQQ RSI",
        Layer.L5,
        PermissionType.TECHNICAL,
        "短线交易节奏是否过热或过冷？",
        ["RSI 高低只描述短线拥挤度，需要趋势和波动确认。"],
        ["不能用 RSI 证明估值便宜，也不能单独证明顶部。"],
        ["get_qqq_technical_indicators", "get_atr_qqq", "get_adx_qqq"],
        ["强趋势中 RSI 可长期维持高位；广度改善会削弱超买担忧。"],
        "短线执行指标，不负责长期框架。",
        "RSI 是节奏表，不是价值秤。",
    ),
    "get_macd_qqq": _indicator(
        "get_macd_qqq",
        "QQQ MACD",
        Layer.L5,
        PermissionType.TECHNICAL,
        "中短期动量是否正在转强或转弱？",
        ["关注信号线、柱状图和价格位置的组合。"],
        ["MACD 金叉不是基本面改善；死叉也不是估值结论。"],
        ["get_qqq_technical_indicators", "get_adx_qqq", "get_advance_decline_line"],
        ["价格创新高且广度同步扩散，削弱负动量担忧。"],
        "短线执行和动量指标。",
        "MACD 只管动量，不管估值。",
    ),
    "get_atr_qqq": _indicator(
        "get_atr_qqq",
        "QQQ ATR",
        Layer.L5,
        PermissionType.TECHNICAL,
        "波动幅度是否正在扩大，仓位和止损距离是否需要调整？",
        ["ATR 上升说明实现波动扩大，需要降低杠杆或放宽止损距离。"],
        ["ATR 高不是方向信号。"],
        ["get_vxn", "get_qqq_technical_indicators", "get_hy_oas_bp"],
        ["ATR 回落且趋势恢复，削弱波动冲击判断。"],
        "风险控制和执行指标。",
        "ATR 说波动大小，不说方向。",
    ),
    "get_adx_qqq": _indicator(
        "get_adx_qqq",
        "QQQ ADX",
        Layer.L5,
        PermissionType.TECHNICAL,
        "趋势强度是否足以支持顺势执行？",
        ["ADX 看趋势强度，PDI/MDI 辅助判断方向。"],
        ["ADX 高只说明趋势强，不保证趋势向上。"],
        ["get_qqq_technical_indicators", "get_macd_qqq", "get_advance_decline_line"],
        ["ADX 回落且动量走弱，削弱趋势延续判断。"],
        "趋势执行指标。",
        "ADX 是趋势强度计，不是多空结论本身。",
    ),
}


INDICATOR_CANONS.update(
    {
        "get_10y2y_spread_bp": _indicator(
            "get_10y2y_spread_bp",
            "10Y-2Y Spread",
            Layer.L1,
            PermissionType.FACT,
            "期限结构是否暗示增长压力或政策约束正在变化？",
            ["倒挂通常说明市场预期未来增长/政策会走弱；修复方向要区分牛陡和熊陡。"],
            ["曲线变陡不一定利好，可能来自长端风险补偿上升。"],
            ["get_10y_treasury", "get_fed_funds_rate", "get_hy_oas_bp"],
            ["信用未恶化且真实利率回落，削弱衰退式解释。"],
            "宏观框架指标，负责解释增长和政策预期，不负责短线买卖。",
            "期限利差是增长预期温度计；先问为什么变陡/变平。",
        ),
        "get_m2_yoy": _indicator(
            "get_m2_yoy",
            "M2 YoY",
            Layer.L1,
            PermissionType.FACT,
            "货币供应增速是否为风险资产提供宽松背景？",
            ["同比改善是流动性背景好转线索，但传导到股价存在滞后。"],
            ["M2 不是交易信号，也不能覆盖信用恶化。"],
            ["get_net_liquidity_momentum", "get_hy_oas_bp", "get_qqq_technical_indicators"],
            ["信用利差走阔或趋势破位抵消 M2 改善。"],
            "宏观背景指标，主要影响中期流动性判断。",
            "M2 是背景光，不是买卖按钮。",
        ),
        "get_copper_gold_ratio": _indicator(
            "get_copper_gold_ratio",
            "Copper/Gold Ratio",
            Layer.L1,
            PermissionType.PROXY,
            "增长敏感资产相对避险资产是否确认经济风险偏好？",
            ["铜金比上行通常偏增长/周期乐观，下行通常偏避险。"],
            ["它是宏观增长代理，不是 NDX 盈利事实。"],
            ["get_10y_treasury", "get_xly_xlp_ratio", "get_hy_oas_bp"],
            ["信用和广度改善可削弱铜金比走弱的负面含义。"],
            "宏观代理指标，只用于交叉验证增长风险偏好。",
            "铜金比说增长风险偏好，不说科技估值便宜。",
        ),
        "get_ig_oas_bp": _indicator(
            "get_ig_oas_bp",
            "IG OAS",
            Layer.L2,
            PermissionType.FACT,
            "投资级信用是否出现系统性融资压力？",
            ["IG 利差走阔说明高质量信用也要求更多补偿，风险更硬。"],
            ["IG 稳定不能证明股票安全，只能说明信用底层未明显恶化。"],
            ["get_hy_oas_bp", "get_vix", "get_net_liquidity_momentum"],
            ["IG/HY 同步收窄且波动回落。"],
            "核心风险指标，用于确认信用压力是否系统化。",
            "IG OAS 是信用底板；走阔时风险偏好要降权。",
        ),
        "get_hyg_momentum": _indicator(
            "get_hyg_momentum",
            "HYG Momentum",
            Layer.L2,
            PermissionType.PROXY,
            "高收益债 ETF 的价格动量是否确认信用风险偏好？",
            ["HYG 走弱常领先或同步反映信用风险偏好下降。"],
            ["ETF 动量是市场价格代理，不能替代 OAS 事实。"],
            ["get_hy_oas_bp", "get_ig_oas_bp", "get_vix"],
            ["OAS 收窄且 HYG 修复。"],
            "风险偏好代理指标，需与 OAS 互证。",
            "HYG 动量是信用风险偏好的市场投票，不是信用事实本身。",
        ),
        "get_xly_xlp_ratio": _indicator(
            "get_xly_xlp_ratio",
            "XLY/XLP Ratio",
            Layer.L2,
            PermissionType.PROXY,
            "周期/消费偏好是否支持风险资产扩散？",
            ["XLY 相对 XLP 走强通常说明风险偏好和消费周期预期改善。"],
            ["它不是 NDX 内部广度指标，不能替代 L3。"],
            ["get_copper_gold_ratio", "get_advance_decline_line", "get_vix"],
            ["防御板块重新跑赢且信用走弱。"],
            "风险偏好代理指标，负责观察风格风险偏好。",
            "XLY/XLP 说风险偏好，不说 NDX 成分健康。",
        ),
        "get_crowdedness_dashboard": _indicator(
            "get_crowdedness_dashboard",
            "Crowdedness Dashboard",
            Layer.L2,
            PermissionType.COMPOSITE,
            "风险资产仓位或交易是否已经拥挤？",
            ["拥挤高说明正向惊喜门槛提高，负面冲击更容易放大。"],
            ["拥挤不是做空理由，需要价格、波动和信用触发。"],
            ["get_vix", "get_vxn", "get_qqq_qqew_ratio"],
            ["拥挤回落且趋势仍稳。"],
            "风险提醒指标，主要约束仓位和结论强度。",
            "拥挤度高=容错率低，不等于顶部已到。",
        ),
        "get_vxn_vix_ratio": _indicator(
            "get_vxn_vix_ratio",
            "VXN/VIX Ratio",
            Layer.L2,
            PermissionType.COMPOSITE,
            "Nasdaq 波动溢价是否相对宽基市场异常上升？",
            ["比值上行说明 NDX/成长暴露的保险价格相对更贵。"],
            ["相对波动上升不自动证明基本面恶化。"],
            ["get_vxn", "get_vix", "get_atr_qqq"],
            ["VXN/VIX 回落且 QQQ 价格结构稳定。"],
            "风险提醒指标，帮助识别 Nasdaq 特有压力。",
            "VXN/VIX 是相对保险价，不是方向结论。",
        ),
        "get_cnn_fear_greed_index": _indicator(
            "get_cnn_fear_greed_index",
            "CNN Fear & Greed",
            Layer.L2,
            PermissionType.COMPOSITE,
            "大众风险情绪是否处于极端区间？",
            ["极端贪婪降低正向风险回报，极端恐惧可能提示反身性机会。"],
            ["情绪指标必须被信用、广度和价格确认。"],
            ["get_vix", "get_hy_oas_bp", "get_advance_decline_line"],
            ["信用恶化时，恐惧不是买入理由。"],
            "弱发言权情绪指标，只能作为风险提醒。",
            "恐惧贪婪指数是情绪表，不能压倒信用和广度。",
        ),
        "get_percent_above_ma": _indicator(
            "get_percent_above_ma",
            "Percent Above Moving Average",
            Layer.L3,
            PermissionType.STRUCTURAL,
            "有多少成分股仍处在健康趋势结构中？",
            ["百分比下降而指数上涨，说明趋势参与度变窄。"],
            ["它说明内部结构，不说明宏观或估值。"],
            ["get_advance_decline_line", "get_qqq_qqew_ratio", "get_multi_scale_ma_position"],
            ["百分比回升并与指数趋势同步。"],
            "结构健康指标，审慎上调优先级。",
            "成分股在均线上方比例=趋势参与度，不是买卖点。",
        ),
        "get_m7_fundamentals": _indicator(
            "get_m7_fundamentals",
            "M7 Fundamentals",
            Layer.L3,
            PermissionType.STRUCTURAL,
            "头部权重股基本面是否足以解释 NDX 集中表现？",
            ["M7 强能解释指数韧性，但也会提高集中度依赖。"],
            ["不能把 M7 强势直接外推为整个 NDX 健康。"],
            ["get_qqq_qqew_ratio", "get_advance_decline_line", "get_ndx_pe_and_earnings_yield"],
            ["等权口径跟上或头部盈利预期下修。"],
            "对象结构指标，用来解释头部贡献和集中度风险。",
            "M7 强=指数可被头部支撑，也=对头部更依赖。",
        ),
        "get_new_highs_lows": _indicator(
            "get_new_highs_lows",
            "New Highs/Lows",
            Layer.L3,
            PermissionType.STRUCTURAL,
            "创新高和创新低的扩散是否支持健康趋势？",
            ["新高扩散支持趋势质量，新低扩大提示内部恶化。"],
            ["单日新高新低噪声较大，需要趋势确认。"],
            ["get_advance_decline_line", "get_percent_above_ma", "get_qqq_technical_indicators"],
            ["新低收缩且 A/D 修复。"],
            "结构健康指标，用于确认广度扩散或恶化。",
            "新高新低看扩散，不看估值。",
        ),
        "get_mcclellan_oscillator_nasdaq_or_nyse": _indicator(
            "get_mcclellan_oscillator_nasdaq_or_nyse",
            "McClellan Oscillator",
            Layer.L3,
            PermissionType.STRUCTURAL,
            "市场广度动量是否进入短线过热或过冷？",
            ["极端读数提示广度动量拐点，但需与 A/D 和价格确认。"],
            ["它偏短线广度动量，不能独立判断长期 regime。"],
            ["get_advance_decline_line", "get_new_highs_lows", "get_rsi_qqq"],
            ["A/D 趋势不确认或价格结构相反。"],
            "结构和短线广度指标，作为 L3 内部辅助。",
            "McClellan 是广度动量，不是最终市场状态。",
        ),
        "get_obv_qqq": _indicator(
            "get_obv_qqq",
            "QQQ OBV",
            Layer.L5,
            PermissionType.TECHNICAL,
            "成交量累积是否确认价格趋势？",
            ["价格上涨但 OBV 不确认，趋势质量要降权。"],
            ["OBV 是技术确认，不说明估值或宏观。"],
            ["get_volume_analysis_qqq", "get_qqq_technical_indicators", "get_advance_decline_line"],
            ["OBV 创新高且价格趋势同步。"],
            "技术确认指标，服务趋势质量判断。",
            "OBV 说量价确认，不说价值。",
        ),
        "get_volume_analysis_qqq": _indicator(
            "get_volume_analysis_qqq",
            "QQQ Volume Analysis",
            Layer.L5,
            PermissionType.TECHNICAL,
            "成交量是否支持突破、回撤或分歧判断？",
            ["放量突破更可信，放量下跌提示供给压力。"],
            ["成交量需要和价格位置一起读，不能单独下方向结论。"],
            ["get_obv_qqq", "get_qqq_technical_indicators", "get_atr_qqq"],
            ["价格修复且成交量结构改善。"],
            "短线执行指标。",
            "成交量是确认器，不是方向本身。",
        ),
        "get_donchian_channels_qqq": _indicator(
            "get_donchian_channels_qqq",
            "QQQ Donchian Channels",
            Layer.L5,
            PermissionType.TECHNICAL,
            "价格是否突破或跌破最近区间边界？",
            ["突破上轨说明趋势延续，跌破下轨说明区间破坏。"],
            ["区间突破需要成交量和广度确认，避免假突破。"],
            ["get_volume_analysis_qqq", "get_adx_qqq", "get_advance_decline_line"],
            ["突破后迅速回落区间内。"],
            "短线执行和止损指标。",
            "Donchian 看区间边界，不看基本面。",
        ),
        "get_multi_scale_ma_position": _indicator(
            "get_multi_scale_ma_position",
            "Multi-Scale MA Position",
            Layer.L5,
            PermissionType.TECHNICAL,
            "价格相对多周期均线的位置是否支持趋势延续？",
            ["短中长期均线同向排列，趋势质量更高；分歧时降低执行自信。"],
            ["均线多头排列不能证明估值合理。"],
            ["get_qqq_technical_indicators", "get_percent_above_ma", "get_adx_qqq"],
            ["跌破关键中长期均线或广度无法确认。"],
            "趋势执行指标，也为 L3 广度提供验证问题。",
            "多周期均线回答趋势结构，不回答价值。",
        ),
    }
)


REGIME_SCENARIO_CANONS: List[RegimeScenarioCanon] = [
    RegimeScenarioCanon(
        scenario_id="soft_landing_extension",
        scenario_name="软着陆延续",
        indicator_combo=["get_hy_oas_bp", "get_10y_real_rate", "get_advance_decline_line"],
        causal_logic="信用未恶化、利率压力可控、广度改善时，成长股趋势更容易延续。",
        main_assumption="盈利和信用能吸收估值偏高带来的脆弱性。",
        falsifiers=["HY OAS 快速走阔", "真实利率重新上行", "A/D 线走弱"],
        risk_triggers=["高估值与高真实利率同时出现", "VXN 快速上升"],
        must_preserve_evidence=["L1/L4 估值-利率冲突", "L3/L5 广度-趋势确认"],
    ),
    RegimeScenarioCanon(
        scenario_id="narrow_leadership",
        scenario_name="狭窄龙头牛市",
        indicator_combo=["get_qqq_qqew_ratio", "get_advance_decline_line", "get_qqq_technical_indicators"],
        causal_logic="市值加权指数上行但等权和广度落后时，指数表现依赖少数龙头。",
        main_assumption="头部盈利与资金集中足以继续支撑指数。",
        falsifiers=["等权口径补涨", "A/D 线改善", "Top10 集中度压力缓解"],
        risk_triggers=["头部技术破位", "VXN 相对 VIX 快速上升"],
        must_preserve_evidence=["NDX 与等权口径背离", "价格趋势与结构健康度张力"],
    ),
]


def get_indicator_canon(function_id: str) -> IndicatorCanon:
    """Return one indicator canon by function_id."""
    try:
        return INDICATOR_CANONS[function_id]
    except KeyError as exc:
        raise KeyError(f"No IndicatorCanon registered for {function_id!r}") from exc


def get_layer_indicator_canons(layer: str | Layer, layer_raw_data: Any) -> List[IndicatorCanon]:
    """Select static indicator canon entries for the current layer input only."""
    layer_value = layer.value if isinstance(layer, Layer) else str(layer).upper()
    if not isinstance(layer_raw_data, dict):
        return []

    selected: List[IndicatorCanon] = []
    for key, payload in layer_raw_data.items():
        function_id = key
        if isinstance(payload, dict):
            function_id = str(payload.get("function_id") or key)
        canon = INDICATOR_CANONS.get(function_id)
        if canon and canon.layer.value == layer_value:
            selected.append(canon)
    return selected


def build_layer_canon_prompt(layer: str | Layer, layer_raw_data: Any) -> str:
    """
    Build a concise static canon block for one layer prompt.

    This block is safe for L1-L5 because it contains object definitions and
    indicator rules only; it never includes another layer's runtime readings.
    """
    object_canon = build_object_canon()
    indicator_canons = get_layer_indicator_canons(layer, layer_raw_data)
    layer_value = layer.value if isinstance(layer, Layer) else str(layer).upper()

    return (
        "## Deep Research Canon\n"
        "本段只提供静态规则，不提供其他层的运行时数据、结论或候选跨层判断。\n"
        "请用它约束指标发言权：每个指标能证明什么、不能证明什么、需要谁验证、什么会反证它。\n\n"
        "### ObjectCanon\n"
        f"{json.dumps(_dump_model(object_canon), ensure_ascii=False, indent=2)}\n\n"
        f"### IndicatorCanon for {layer_value}\n"
        f"{json.dumps([_dump_model(item) for item in indicator_canons], ensure_ascii=False, indent=2)}\n\n"
        "### Canon Output Hints\n"
        "- 在 indicator_analyses 中尽量填写 permission_type、canonical_question、misread_guards、"
        "cross_validation_targets、falsifiers、core_vs_tactical_boundary。\n"
        "- 如果某项 canon 缺失，不要编造；只基于本层输入完成原生分析，并在 quality_self_check 中说明边界。\n"
    )
