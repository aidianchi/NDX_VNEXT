# prompt_examples.py
"""
本文件存储用于“少样本提示”的高质量范例。
v2.0版本采用“4C精炼框架”（语境化、精炼化、典范化、因果化），
旨在将AI对核心指标的认知从“博学”提升至“智慧”。
"""
import json
from typing import TypedDict, List, Dict, Union, Optional
import logging

# 关键导入：从“感知”层导入注册表，用于交叉校验
try:
    try:
        from .tools import TOOLS_REGISTRY
    except ImportError:
        from tools import TOOLS_REGISTRY
except ImportError:
    TOOLS_REGISTRY = {}
    logging.error("无法导入 TOOLS_REGISTRY。校验功能将受限。")

# --- 数据合约 (Schema) 定义开始 ---

class ExampleInputSchema(TypedDict, total=False):
    """
    定义范例中 'input' 字段的结构。
    它必须包含 function_id 或 comment 之一。
    """
    function_id: str  # 对应 tools.py 中的函数名
    comment: str      # 用于逻辑组合或非指标性范例
    raw_data: Dict    # 模拟的原始数据输入
    #... 其他用于逻辑组合范例的键

class ExampleSchema(TypedDict):
    """
    定义单个少样本范例的结构。
    此 Schema 强制执行“4C原则”。
    """
    context: str  # 强制执行“语境化” (Contextualization)
    input: ExampleInputSchema
    reasoning: str  # 强制执行“因果化” (Causality)
    output_narrative: str  # 强制执行“精炼化” (Conciseness)

# 定义主注册表的类型，键是 function_id (来自 tools.py)
PromptExamplesRegistry = Dict[str, List[ExampleSchema]]

# --- 数据合约 (Schema) 定义结束 ---

# --- 认知范例：大师视角 (V9.2 新增) ---

MASTERS_PERSPECTIVE_EXAMPLES = [
    # 范例 1: 锁定“德鲁肯米勒（镜头3）”的非对称性优化
    {
        "context": "这是一个‘德鲁肯米勒镜头’的典范。当L5（趋势）强劲，但L1（宏观）和L2（信贷）出现背离时，AI必须识别出L2（VIX）提供的‘非对称’对冲机会。",
        "input": {
            "comment": "大师视角(德鲁肯米勒)范例 - L5与L1/L2背离，VIX提供非对称机会",
            "L1_data": { "get_10y_real_rate": { "value": { "level": 1.8, "trend": "Rising" } } },
            "L2_data": { "get_vix": { "value": { "level": 12.5 } } },
            "L5_data": { "get_qqq_technical_indicators": { "value": { "QQQ_vs_200MA": "Above (Strong)" } } }
        },
        "reasoning": """
德鲁肯米勒镜头寻找流动性、情绪和价格信号的印证或背离。L5 价格强劲，但 L1 实际利率正在攀升，这是一个核心背离。L2 的 VIX 处于 12.5 的极低水平，既意味着市场自满，也意味着下行保护（如看跌期权）极其廉价。支撑市场的核心驱动力（低利率）正在撤退，但市场仍在惯性上涨——这是极其危险的信号，同时低 VIX 为建立非对称的空头头寸（廉价对冲）提供了时机。
""",
        "output_narrative": " **全球宏观投机之王 (如 斯坦利·德鲁肯米勒):** 我看到了一个巨大的背离：L5的价格正在创下新高，但L1的实际利率正在攀升。这表明支撑市场的核心驱动力（流动性）正在撤退。这是一个极其危险的信号。同时，L2的VIX处于极低水平，为建立非对称的空头头寸（如廉价的看跌期权）提供了完美时机。"
    },
    
    # 范例 2: 锁定“核心哲学整合者（镜头5）”的“情景B”裁决
    {
        "context": "这是‘核心哲学整合者’（镜头5）的**最重要典范**。它演示了如何在‘价值’与‘趋势’发生核心冲突时（情景B），严格执行‘价值买入，趋势卖出’的纪律。",
        "input": {
            "comment": "大师视角(整合者-情景B)范例 - 价值(×) vs 趋势(√)",
            "lens_1_output": "巴菲特: L4的简式收益差距为负，当前安全垫薄，不把它当作完整 implied ERP。",
            "lens_2_output": "利弗莫尔: L5趋势完好，L3未背离，‘未’触发卖出。"
        },
        "reasoning": """
整合者镜头的纪律是价值买入、趋势卖出。巴菲特之魂（镜头1）的结论是不批准买入，利弗莫尔之手（镜头2）的结论是未触发卖出，于是落入情景 B，也就是价值不达标、趋势仍然完好的组合。'价值买入'纪律禁止任何新仓位，'趋势卖出'纪律尚未触发，最终裁决为'高风险持有，绝对禁止新购入'。
""",
        "output_narrative": " **核心哲学整合者 (NDX-Command 之魂):** 这是一个经典的市场冲突（情景B）：**巴菲特之魂（L4）说‘不’**（因价值昂贵），因此‘价值买入’的纪律**禁止**任何新的多头仓位。与此同时，**利弗莫尔之手（L5）说‘持有’**（因趋势未破）。最终裁决：这是一个高风险的‘持有’或‘逐步减仓’阶段，绝对禁止新购入。"
    }
]

# PROMPT_EXAMPLES 变量现在应符合 PromptExamplesRegistry 类型
PROMPT_EXAMPLES: PromptExamplesRegistry = {

    # =================================================================
    # Layer 1: 宏观经济状况 (L1)
    # =================================================================

    # "yield_curve_spread" -> 重命名为 "get_10y2y_spread_bp"
    "get_10y2y_spread_bp": [
        {
            "context": "【典范化解读 + 剔除日常波动】10Y-2Y收益率曲线是全球最重要的经济衰退领先指标。L1宏观层用 MA20 乖离率衡量趋势，替代日度动量。",
            "input": {"function_id": "get_10y2y_spread_bp", "raw_data": {"value": {"level": -55.2, "deviation_pct": -8.5, "position_vs_ma": "below", "ma": -50.8, "relativity": {"percentile_10y": 5.2}}}},
            "reasoning": "负值水平(-55.2bp)意味着曲线处于深度倒挂状态，而 10Y-2Y 利差是历史上可靠的衰退领先指标。当前水平显著低于 MA20(-50.8bp)，乖离率 -8.5% 表明倒挂仍在趋势性加深。市场不仅发出了衰退警报，且趋势尚未见底，对未来 6-18 个月经济前景的悲观预期正在固化。",
            "output_narrative": "作为最可靠的经济衰退领先指标，10Y-2Y收益率曲线处于-55.2个基点的深度倒挂状态，且显著低于其20日均线-50.8bp（乖离率-8.5%），发出了明确且强烈的经济衰退预警。趋势尚未见底，市场的悲观预期正在强化。"
        },
        {
            "context": "【典范化解读】10Y-2Y收益率曲线是全球最重要的经济衰退领先指标。其正值形态是经济健康的标志。",
            "input": {"function_id": "get_10y2y_spread_bp", "raw_data": {"value": {"level": 75.8, "position_vs_ma": "above", "ma": 68.5}}},
            "reasoning": "正值水平(75.8bp)意味着曲线处于'陡峭化'形态，且高于MA20(68.5bp)，趋势向上。这通常出现在经济复苏或扩张周期的早期，反映出债券市场预计未来经济增长强劲，通胀可能回升，因此要求更高的长期风险补偿。",
            "output_narrative": "10Y-2Y收益率曲线呈现75.8个基点的陡峭形态，且高于其20日均线，趋势向上，这是经济健康和市场对长期增长保持乐观的积极信号。"
        }
    ],

    # "real_rate" -> 重命名为 "get_10y_real_rate"
    "get_10y_real_rate": [
        {
            "context": "【因果化解读 + 剔除日常波动】10年期实际利率是成长股估值的核心折现约束。L1宏观层使用MA20乖离率替代日度动量。",
            "input": {"function_id": "get_10y_real_rate", "raw_data": {"value": {"level": 2.5, "deviation_pct": 8.3, "position_vs_ma": "above", "ma": 2.31}}},
            "reasoning": "实际利率是无风险资产的真实回报率，代表所有风险资产的机会成本。实际利率上升时，计算未来现金流现值的贴现率随之提高，依赖遥远未来现金流的成长股（如纳斯达克100）的内在价值会被系统性地向下重估。当前水平(2.5%)显著高于 MA20(2.31%)，乖离率 +8.3% 表明利率仍在趋势性上行，这种压力正在持续增加。",
            "output_narrative": "作为成长股估值的核心驱动力，10年期实际利率已上升至2.5%的高位，显著高于其20日均线（乖离率+8.3%），表明利率在趋势上仍处于上行通道，直接提高了未来现金流的贴现率，对纳斯达克100的估值倍数构成了强大的、系统性的下行压力。"
        }
    ],

    # =================================================================
    # Layer 2: 市场风险偏好 (L2)
    # =================================================================

    # "high_yield_oas" -> 重命名为 "get_hy_oas_bp"
    "get_hy_oas_bp": [
        {
            "context": "【语境化解读 + 剔除日常波动】高收益信用利差(OAS)是'聪明钱'对风险的真实定价。L1宏观层用 MA5 与 MA20 的趋势方向替代日度动量。注意：输入中的利差读数与长短均线数值，单位均为百分比（FRED 原始口径），行文引用时须写成 X.XX%（约 XXX 个基点）的形式，禁止把百分比数值直接当成基点数来写。",
            "input": {"function_id": "get_hy_oas_bp", "raw_data": {"value": {"level": 6.20, "trend": "short_above_long", "short_ma": 6.18, "long_ma": 5.95, "relativity": {"percentile_10y": 92.3}}}},
            "reasoning": "高收益信用利差反映金融体系中最专业的资本（债券市场）对风险的真实态度。当前读数为 6.20%（约 620 个基点），远高于历史均值，已经进入经济衰退或金融压力时期才会出现的危险区域，92.3% 的十年历史百分位确认了这种极端性。短期均线读数（6.18%）高于长期均线读数（5.95%），表明利差在周度趋势上仍在扩大，信贷环境正在收紧。'聪明钱'不仅在大声呼喊风险，趋势方向也支持风险正在上升的判断，股票市场的乐观情绪在这种背景下极其脆弱。",
            "output_narrative": "作为'聪明钱'风险偏好的领先指标，高收益信用利差已飙升至6.20%（约620个基点）的危机水平（10年百分位92.3%），且短均线高于长均线，趋势方向表明利差仍在扩大。信贷市场正在对严重的经济衰退风险进行定价，金融系统压力急剧升高。"
        }
    ],

    # "cnn_fear_greed_index" -> 新增 CNN恐贪指数
    "get_cnn_fear_greed_index": [
        {
            "context": "【反向指标典范 · 极度恐惧】CNN恐贪指数是综合性市场情绪指标，整合7个子指标（市场动量、股价强度、广度、Put/Call比率、VIX、垃圾债需求、避险需求）。核心逻辑：极端值是有效的反向信号。",
            "input": {
                "function_id": "get_cnn_fear_greed_index",
                "raw_data": {
                    "value": {
                        "score": 14.59,
                        "rating": "extreme fear",
                        "trend": "extreme_fear",
                        "previous_close": 17.17,
                        "previous_1_week": 22.63,
                        "previous_1_month": 44.41,
                        "previous_1_year": 21.69,
                        "sub_metrics": {
                            "Market Momentum (S&P500)": {"score": 1.2, "rating": "extreme fear"},
                            "Stock Price Strength": {"score": 18, "rating": "extreme fear"},
                            "Put/Call Options": {"score": 3.6, "rating": "extreme fear"},
                            "Market Volatility (VIX)": {"score": 40.7, "rating": "fear"}
                        }
                    }
                }
            },
            "reasoning": "得分 14.59 落在低于 25 的'极度恐惧'区间，说明市场情绪已跌至极端悲观水平。相比一周前的 22.63，情绪在短短一周内急剧恶化；相比一个月前的 44.41（中性偏恐惧），市场情绪发生了根本性逆转。7 个子指标中有多个也处于'极度恐惧'档，尤其是市场动量（得分 1.2）和 Put/Call 比率（得分 3.6），确认了恐慌的广泛性。极端恐惧在历史上常对应逆向买入机会，但必须结合信用利差、广度和趋势确认，不能仅凭情绪指标做判断。VIX 子指标得分 40.7，处于'恐惧'档，与整体指数形成印证，增强了信号的可靠性。",
            "output_narrative": "CNN恐贪指数已跌至14.59的'极度恐惧'区间，在过去一周内从22.63急剧恶化，市场情绪发生了根本性逆转。7个子指标中多个确认了恐慌的广泛性。极端恐惧在历史上常对应逆向买入机会，但需结合信用、广度和趋势确认，不能仅凭情绪指标做判断。"
        },
        {
            "context": "【反向指标典范 · 极度贪婪】当恐贪指数处于高于 75 的极度贪婪区间时，市场过度乐观，需要警惕均值回归风险。",
            "input": {
                "function_id": "get_cnn_fear_greed_index",
                "raw_data": {
                    "value": {
                        "score": 82.5,
                        "rating": "extreme greed",
                        "trend": "extreme_greed",
                        "previous_close": 78.3,
                        "previous_1_week": 72.1,
                        "previous_1_month": 65.2,
                        "sub_metrics": {
                            "Market Momentum (S&P500)": {"score": 88, "rating": "extreme greed"},
                            "Stock Price Strength": {"score": 92, "rating": "extreme greed"},
                            "Put/Call Options": {"score": 78, "rating": "extreme greed"}
                        }
                    }
                }
            },
            "reasoning": "得分 82.5 落在高于 75 的'极度贪婪'区间，说明市场情绪已达到极端乐观水平。相比一周前的 72.1，情绪的贪婪程度在加速加深，这个变化方向不利于风险控制。市场动量（得分 88）和股价强度（得分 92）均处于'极度贪婪'档，说明市场上涨高度依赖情绪驱动。极度贪婪在历史上常预示均值回归风险，但不能仅凭情绪指标判定顶部，必须结合信用利差、广度恶化和趋势衰减信号确认。若 VIX 子指标仍处于低位，则确认市场对风险毫无防备，脆弱性极高。",
            "output_narrative": "CNN恐贪指数已飙升至82.5的'极度贪婪'区间，过去一周内从72.1加速上行。多个子指标确认市场情绪全面过热。极度贪婪在历史上常预示均值回归风险，但需结合信用、广度和趋势确认，不能仅凭情绪指标判定顶部。"
        }
    ],

    # "consumer_risk_appetite_ratio" -> 重命名为 "get_xly_xlp_ratio"
    "get_xly_xlp_ratio": [
        {
            "context": "【典范化解读】XLY/XLP比率是消费者风险偏好指标。剔除日常波动：用比值相对 MA20 的位置替代日度动量。",
            "input": {"function_id": "get_xly_xlp_ratio", "raw_data": {"value": {"level": 1.5, "position_vs_ma20": "below", "ma20": 1.58}}},
            "reasoning": "XLY 代表消费者的乐观支出意愿，XLP 代表避险需求，所以这一比值衡量的是真实世界的风险偏好。当比值落到 20 日均线下方时，说明消费者行为模式正从'进攻'转向'防御'。这种行为模式的转变是消费者信心恶化的证据，通常领先于官方经济数据的下滑，因此它是经济即将放缓的可靠预警。",
            "output_narrative": "作为衡量真实世界风险偏好的关键代理，XLY/XLP（非必需/必需消费品）比率已回落至20日均线下方，表明消费者信心正在减弱，支出行为模式正转向防御，这是经济放缓的早期预警信号。"
        },
        {
            "context": "【10年历史极值 · 典范】本示例演示一种极端位置：当风险偏好比率（XLY/XLP）处于十年历史百分位的极端高位时，分析应当强调赔率已经严重失衡，不鼓励在极端高位继续追多。",
            "input": {
                "function_id": "get_xly_xlp_ratio",
                "raw_data": {
                    "value": {
                        "level": 2.1,
                        "relativity": {
                            "percentile_10y": 99.2,
                            "percentile_1y": 95.0
                        }
                    }
                }
            },
            "reasoning": (
                "1. 当前读数为 2.1，已经处在历史相对高位，说明非必需消费品（XLY）相对必需消费品（XLP）的强势极为明显。\n"
                "2. 更关键的是它的十年历史百分位达到 99.2%：在十年样本中，这一位置几乎是顶部区域，历史上只有极少数时点能达到或超过这一分位。\n"
                "3. 从统计学角度看，这种极端百分位意味着两件事：一是继续向上走出同量级空间的概率很低；二是向下均值回归的概率和空间都很大，赔率结构已经明显向“减仓风险偏好”一侧倾斜。\n"
                "4. 因此，在十年历史百分位 99.2% 的位置上继续追多风险偏好，是一笔赢面很小、潜在亏损尾部很重的坏赔率交易，不符合专业风控纪律。"
            ),
            "output_narrative": (
                "风险偏好比率 XLY/XLP 已经冲到十年历史分布的 99.2% 极端高位，"
                "历史上只有极少数时点达到过这一水平。"
                "在这样的位置继续追多风险资产，向上的空间已经很小，"
                "向下的回撤却可能异常陡峭——胜率与赔率都严重倒向不利一侧，"
                "均值回归的压力占据主导。"
            )
        }
    ],
    
    # "qqq_net_liquidity_ratio" -> 新增 get_qqq_net_liquidity_ratio
    "get_qqq_net_liquidity_ratio": [
        {
            "context": "【流动性 vs 估值 · 背离典范】本示例演示一种背离：当净流动性走平甚至下滑、而 QQQ 价格大涨把比率推高时，这轮上涨就不是流动性驱动的，而是缺乏流动性支撑的估值倍数扩张。",
            "input": {
                "function_id": "get_qqq_net_liquidity_ratio",
                "raw_data": {
                    "value": {
                        "level": 3.25,
                        "historical_stats": {
                            "percentile_5y": 96.8,
                            "percentile_10y": 94.3,
                            "z_score_10y": 1.9
                        },
                        "date": "2024-11-15"
                    },
                    "contextual_components": {
                        "net_liquidity_trend": "flat to down",
                        "qqq_price_action": "sharp_rally"
                    }
                }
            },
            "reasoning": (
                "1. 先看分子与分母：净流动性并未上升、甚至在下降，但 QQQ 价格大幅飙升，把这一比率推到了 3.25。\n"
                "2. 这说明本轮上涨不是由货币投放驱动的，而是单纯依靠估值倍数的抬升。\n"
                "3. 五年与十年历史分位都在 94% 以上，说明这种流动性与价格的背离在历史上非常少见。\n"
                "4. 因果关系是清楚的：因为缺乏增量流动性的支撑，价格上涨只能依赖情绪与估值扩张，所以泡沫化特征加剧，一旦开始回撤，下跌的幅度会更大。"
            ),
            "output_narrative": (
                "QQQ/净流动性比率在净流动性走平甚至下滑的环境下却升到 3.25，"
                "处于五年与十年历史分位 94% 以上的极端区域，说明这轮上涨不是流动性推动的，"
                "而是缺乏货币支撑的估值倍数扩张。"
                "这种流动性与价格的背离是典型的泡沫化特征——缺乏货币支撑的价格上冲，"
                "回撤时往往更脆弱，持有人得到的风险补偿显著恶化。"
            )
        },
        {
            "context": "【历史统计极值 · 10年99分位】本示例演示：当任何指标的十年历史百分位接近 99% 时，分析应当强调均值回归的压力已经占据主导。",
            "input": {
                "function_id": "get_qqq_net_liquidity_ratio",
                "raw_data": {
                    "value": {
                        "level": 3.80,
                        "historical_stats": {
                            "percentile_10y": 99.1,
                            "percentile_5y": 98.4,
                            "z_score_10y": 2.6
                        },
                        "date": "2025-02-10"
                    }
                }
            },
            "reasoning": (
                "1. 十年历史百分位达到 99.1%，处于十年分布的极端高位，属于统计学上的尾部区域。\n"
                "2. 在这种尾部区域，继续向上获得同量级涨幅的概率很低，而向下均值回归的概率和幅度都在显著放大。\n"
                "3. Z 分数达到 2.6，进一步量化了当前读数偏离长期均值的程度。\n"
                "4. 结论是：赔率结构严重失衡，继续追多是一笔赢面很小、潜在亏损很重的坏交易，"
                "均值回归的力量将主导未来的价格路径。"
            ),
            "output_narrative": (
                "QQQ/净流动性比率已站上十年样本 99% 的极值区间，这种水平在历史上难以持续。"
                "在这种尾部区域，继续向上获得同等幅度涨幅的概率很低，而向下均值回归的空间和概率都在放大。"
                "这是一笔典型的坏赔率交易：赢面很小，潜在亏损很重，均值回归的力量几乎占据主导。"
            )
        }
    ],

    # =================================================================
    # Layer 3: 指数内部健康度 (L3)
    # =================================================================

    # "market_breadth_ratio" -> 重命名为 "get_ndx_ndxe_ratio" (这是其对应的function_id)
    "get_ndx_ndxe_ratio": [
        {
            "context": "【典范化解读】NDX/NDXE 比率最核心应用是识别'熊市背离'。剔除日常波动：用比值趋势(MA20)与价格趋势(MA60)双重过滤器。",
            "input": {
                "function_id": "get_ndx_ndxe_ratio",
                "raw_data": {
                    "value": {
                        "level": 2.9,
                        "ratio_trend_vs_ma20": "below",
                        "cap_weight_price_vs_ma60": "above",
                        "ratio_ma20": 2.95,
                        "cap_weight_ma60": 21500.0
                    }
                }
            },
            "reasoning": "这是一个经典的顶部警报。从价格看，NDX 仍在 60 日均线上方，指数的表面趋势尚可。但 NDX/NDXE 比率已回落到 20 日均线下方，说明市值加权的少数巨头相对等权指数的领先优势正在收窄。这轮上涨缺乏多数成分股的参与，趋势的内部结构因此变得脆弱，一旦少数领涨股回调，指数很容易跟随下跌。",
            "output_narrative": "市场广度出现经典的熊市背离：尽管 NDX 价格仍在 60 日均线之上，但其与等权指数 NDXE 的比率已回落至 20 日均线之下，表明这轮上涨仅由少数巨头支撑，趋势的内在健康度严重恶化，根基极其脆弱。"
        }
    ],

    # =================================================================
    # Layer 1 (扩展): 流动性三剑客 · 美元净流动性 (Net Liquidity)
    # =================================================================
    "get_net_liquidity_momentum": [
        {
            "context": "【净流动性拆解 · 双重紧缩场景】本示例演示：当美联储缩表与财政部发债补充账户余额叠加时，两条抽水管同时工作，市场遭遇的估值压力会远超“只是缩表”的表面印象。",
            "input": {
                "function_id": "get_net_liquidity_momentum",
                "raw_data": {
                    "value": {
                        "level": 5200.0,
                        "momentum_4w": -120.5,
                        "components": {
                            "fed_assets": 7800.0,
                            "tga": 950.0,
                            "rrp": 1800.0
                        }
                    }
                }
            },
            "reasoning": (
                "1. 首先看动量读数：四周滚动净流动性动量为 -120.5，属于幅度极大的负值，"
                "这种量级对应的是系统性抽水，而不是日常波动。\n"
                "2. 然后拆解三个组成部分：美联储资产相比前期明显下降，说明美联储正在持续缩表；"
                "财政部一般账户（TGA）余额在高位继续抬升，意味着财政部正通过加大发债把银行体系的流动性锁回财政账户，"
                "相当于第二条抽水管；隔夜逆回购（RRP）余额大致稳定，既没有释放流动性，也没有提供缓冲。\n"
                "3. 把三部分合起来看：缩表在抽水，财政补库也在抽水，逆回购又没有释放资金来对冲，"
                "三个组成部分里只有紧缩力量，没有对冲力量。\n"
                "4. 因此，这不是普通的缩表环境，而是宏观层面的双重紧缩，"
                "高估值资产和杠杆头寸承受的压力远超单一缩表所能解释的程度。"
            ),
            "output_narrative": (
                "净流动性的三个组成部分共同发出了一个少见的双重紧缩信号："
                "过去四周，四周滚动净流动性动量大幅滑至 -120.5 的深负值，其背后是美联储持续缩表，"
                "叠加财政部发债补充账户余额、把银行体系的现金锁回财政账户，而隔夜逆回购余额一直停在高位、没有释放缓冲。"
                "换言之，货币端和财政端正从同一侧同时抽水，这种组合给估值和风险资产带来的宏观逆风极为严峻。"
            )
        },
        {
            "context": "【净流动性拆解 · 隐形放水场景】本示例演示：在名义上的缩表周期里，隔夜逆回购余额的释放可以对冲甚至部分逆转缩表的效果。",
            "input": {
                "function_id": "get_net_liquidity_momentum",
                "raw_data": {
                    "value": {
                        "level": 5350.0,
                        "momentum_4w": 10.2,
                        "components": {
                            "fed_assets": 7750.0,
                            "tga": 500.0,
                            "rrp": 1200.0
                        }
                    }
                }
            },
            "reasoning": (
                "1. 表面上看，美联储资产较前期仍在下降，美联储名义上处于持续缩表状态。\n"
                "2. 但四周滚动净流动性动量读数为 10.2 的正值，说明平滑后的净流动性在过去四周略有上升，"
                "这与“只要缩表就是持续抽水”的直觉相反。\n"
                "3. 关键在于隔夜逆回购：它的余额从更高水平显著回落，意味着原本停泊在美联储资产负债表之外的资金"
                "正在被释放回银行和货币市场体系，对冲甚至部分逆转了缩表的紧缩效应。\n"
                "4. 财政部一般账户基本稳定，没有额外的财政抽水动作，因此三个组成部分里的主要变化是："
                "资产端小幅缩表，而隔夜逆回购大幅释放资金，两者相抵之后净流动性总体微升。\n"
                "5. 结论是：这是一个典型的隐形放水场景——名义上在缩表，实质上净流动性并未恶化，"
                "甚至为风险资产提供了缓冲环境。"
            ),
            "output_narrative": (
                "把净流动性的三个组成部分合起来看，这是一次典型的隐形对冲："
                "美联储账面上仍在温和缩表，但隔夜逆回购余额的大幅回落把此前冻结在逆回购池中的现金重新释放回市场，"
                "使过去四周的净流动性动量反而小幅转正。"
                "在这种格局下，表面上的紧缩叙事与资产价格的相对坚挺并不矛盾——"
                "名义上在缩表，实质上仍有一条通过隔夜逆回购缓慢释放流动性的通道，这正是当前环境的核心。"
            )
        }
    ],

    # =================================================================
    # Layer 4: 指数基本面估值 (L4)
    # =================================================================

    # Historical function name kept for compatibility; output is now the NDX simple yield gap.
    "get_equity_risk_premium": [
        {
            "context": "【语境化解读】简式收益差距是盈利收益率或自由现金流收益率减去十年期美债收益率，它只能衡量当前收益率的安全垫，不能写成 Damodaran 式的隐含股权风险溢价。",
            "input": {"function_id": "get_equity_risk_premium", "raw_data": {"value": {"level": -0.5, "relativity": {"percentile_1y": 5.0}}}},
            "reasoning": "简式收益差距只比较当前的盈利/现金流收益率与十年期美债收益率。读数为 -0.5%，说明当期收益率安全垫为负，高估值要依靠未来增长、质量溢价或风险偏好来维持。它处于一年期低分位，说明这一安全垫在近期样本中也偏薄。它不是完整的隐含股权风险溢价，也不是单独的交易信号；它要求 L1 至 L5 各层验证利率、情绪、广度和趋势是否足以支撑估值。",
            "output_narrative": "NDX 简式收益差距为 -0.5%，说明当前盈利/现金流收益率相对十年期美债缺少正安全垫。该指标不是 Damodaran 式的隐含股权风险溢价，只能作为估值脆弱性与跨层验证需求的提示。"
        }
    ],

    # =================================================================
    # Layer 5: 价格趋势与波动率 (L5)
    # =================================================================

    # "adx_trend_strength" -> 重命名为 "get_adx_qqq"
    "get_adx_qqq": [
        {
            "context": "【典范化解读】ADX是一个无方向性的趋势强度指标。其唯一典范应用是判断趋势是否存在，而非判断趋势方向。",
            "input": {"function_id": "get_adx_qqq", "raw_data": {"value": {"level": {"adx": 48.0, "pdi": 12.0, "mdi": 45.0}}}},
            "reasoning": "ADX 数值为 48.0，远高于 25 的强弱分界线，表明市场正处于一段强劲的趋势中。向下方向的 DI（45.0）远高于向上方向的 DI（12.0），指明这段强劲趋势的方向是向下的。市场并非在震荡或盘整，而是处于一段主导性的、能量十足的下跌趋势之中。",
            "output_narrative": "ADX数值为48.0，远超25的强趋势阈值，表明市场存在一段强劲的趋势。向下方向的DI数值（45.0）远高于向上方向（12.0），明确指示当前市场正处于一段由空头主导的、强劲的下跌趋势中。"
        }
    ],

    # 【新增】将“大师视角”范例列表注册到“masters_perspective”这个概念键上
    "masters_perspective": MASTERS_PERSPECTIVE_EXAMPLES
}

_VNEXT_CONTEXT_FIRST_EXAMPLES: PromptExamplesRegistry = {
    "get_fed_funds_rate": [
        {
            "context": "【政策利率约束】联邦基金利率不是短期噪声，而是风险资产机会成本的地板。高位政策利率会提高现金和短债吸引力，压制高久期资产估值。",
            "input": {"function_id": "get_fed_funds_rate", "raw_data": {"value": {"level": 5.25, "trend": "stable", "relativity": {"percentile_10y": 94.0}}}},
            "reasoning": "1. 从水平看，5.25% 的政策利率处于十年高分位，说明政策利率仍在限制性区间。2. 从趋势看，读数保持稳定，意味着压力没有继续加速，但也没有解除。3. 机制是这样的：现金收益率升高时，投资者会要求更高的股票风险溢价，高估值成长股因此需要更强的盈利才能维持当前估值倍数。4. 层内结论是：这不是立即看空价格的信号，而是 L4 层估值分析必须面对的折现率约束。",
            "output_narrative": "联邦基金利率维持在5.25%的限制性高位，虽然没有继续上行，但现金和短债的机会成本仍然很高。对纳斯达克100而言，这意味着高估值资产需要用更强盈利来抵消折现率压力。"
        }
    ],
    "get_10y_treasury": [
        {
            "context": "【名义长端利率拆解】10年期美债收益率同时包含真实利率、通胀补偿和增长预期，不能只把上行机械解释为利空。",
            "input": {"function_id": "get_10y_treasury", "raw_data": {"value": {"level": 4.55, "trend": "rising", "position_vs_ma": "above"}}},
            "reasoning": "1. 从水平看，4.55% 的十年期收益率会抬高长期现金流的折现率。2. 从趋势看，收益率高于其均线且继续上行，说明长端折现压力在边际增强。3. 从构成看，如果上行主要来自真实利率，对估值最不利；如果主要来自增长预期，压力可能部分被盈利预期的改善抵消。4. 结论是：该指标应作为 L4 层估值压力和 L1 层内部利率结构的确认信号，不应单独用来给市场定性。",
            "output_narrative": "10年期美债收益率升至4.55%并处于上行趋势，长端折现率压力边际增强。其含义取决于真实利率与通胀预期的拆分：真实利率驱动更压估值，增长预期驱动则可能被盈利改善部分抵消。"
        }
    ],
    "get_10y_breakeven": [
        {
            "context": "【通胀预期分解】盈亏平衡通胀用于判断名义利率变化是否来自通胀补偿。它决定市场是否担心通胀重新约束美联储。",
            "input": {"function_id": "get_10y_breakeven", "raw_data": {"value": {"level": 2.42, "trend": "rising", "relativity": {"percentile_10y": 63.0}}}},
            "reasoning": "1. 从水平看，2.42% 的盈亏平衡通胀率不算极端，但高于美联储的通胀目标。2. 从趋势看，读数上行代表市场重新要求通胀补偿。3. 机制是这样的：通胀预期升温时，美联储的降息空间会受限，政策利率因此维持更久，成长股估值承受的折现压力随之延续。4. 结论是：该指标的核心作用是解释长端利率上行是否会延长 L1 层的限制性状态。",
            "output_narrative": "10年期盈亏平衡通胀处于2.42%并边际上行，显示市场对通胀补偿的要求有所抬升。它不直接决定股价，但会限制政策转松空间，使高利率对估值的约束更难快速解除。"
        }
    ],
    "get_m2_yoy": [
        {
            "context": "【货币量慢变量】M2同比不是交易触发器，而是中期流动性土壤。负增长或低增长说明货币扩张不能为估值扩张提供宽松背景。",
            "input": {"function_id": "get_m2_yoy", "raw_data": {"value": {"level": -1.8, "trend": "falling", "relativity": {"percentile_10y": 8.0}}}},
            "reasoning": "1. 从水平看，M2 同比为负，属于历史罕见的货币收缩状态。2. 从趋势看，读数继续下行，说明中期流动性环境没有改善。3. 机制是这样的：货币增速收缩时，金融体系的风险承受能力会下降，估值扩张因此缺少宏观层面的燃料。4. 结论是：它强化 L1 层偏紧的判断，但因为传导较慢，需要与净流动性和风险偏好交叉验证。",
            "output_narrative": "M2同比为-1.8%且仍在下行，说明货币层面的中期流动性土壤偏紧。它不是短线择时信号，但会降低市场持续估值扩张的宏观容错率。"
        }
    ],
    "get_copper_gold_ratio": [
        {
            "context": "【增长预期代理】铜金比衡量周期增长偏好相对避险需求。上行代表增长预期改善，下行代表增长担忧或避险升温。",
            "input": {"function_id": "get_copper_gold_ratio", "raw_data": {"value": {"level": 0.21, "position_vs_ma": "below", "trend": "falling"}}},
            "reasoning": "1. 铜金比的绝对水平本身意义有限，关键看它相对均线的位置和运行方向。2. 当前读数低于均线且继续下行，说明铜相对黄金正在走弱。3. 机制是这样的：增长敏感资产弱于避险资产时，说明市场在下调周期增长预期，企业盈利和风险偏好因此承压。4. 结论是：如果该指标与期限利差或信用利差互相印证，宏观增长压力的判断会得到强化。",
            "output_narrative": "铜金比低于均线并继续下行，说明增长敏感资产相对避险资产走弱。这个信号指向增长预期降温，会削弱盈利韧性叙事，并需要与信用和期限结构共同验证。"
        }
    ],
    "get_vix": [
        {
            "context": "【低波动不等于低风险】VIX 低不等于风险低。低 VIX 可能代表环境平稳，也可能代表市场对尾部风险定价过低。",
            "input": {"function_id": "get_vix", "raw_data": {"value": {"level": 12.8, "relativity": {"percentile_10y": 12.0}, "trend": "falling"}}},
            "reasoning": "1. 从水平看，12.8 的 VIX 处于历史低分位，说明市场为隐含波动定出的价格很低。2. 从趋势看，VIX 继续下行，说明风险定价被进一步压缩。3. 机制是这样的：当保护性头寸很便宜时，市场容易陷入自满，一旦宏观或盈利冲击出现，波动率的回升会放大价格回撤。4. 结论是：低 VIX 表面上是风险偏好旺盛的信号，同时也是非对称下行风险的来源。",
            "output_narrative": "VIX处于12.8的低位并继续下行，表面上显示市场环境平稳、风险偏好较强；但低波动也意味着保护成本便宜和自满风险上升，一旦出现宏观或盈利冲击，波动率回补会放大回撤。"
        }
    ],
    "get_vxn": [
        {
            "context": "【科技股波动率】VXN是纳指专属隐含波动率，能识别科技股内部压力是否高于大盘。",
            "input": {"function_id": "get_vxn", "raw_data": {"value": {"level": 18.5, "trend": "rising", "relativity": {"percentile_10y": 45.0}}}},
            "reasoning": "1. 从水平看，18.5 的 VXN 处于历史中位附近，尚不构成恐慌。2. 从趋势看，读数上行，说明科技股的隐含波动在边际升温。3. 机制是这样的：科技股波动预期上升时，投资者会对高估值、高久期资产要求更高的风险折价，NDX 相对大盘因此更加脆弱。4. 结论是：该指标需要与 VXN/VIX 比率一起使用，才能判断压力是否为科技股特有。",
            "output_narrative": "VXN处于18.5的中性区间但边际上行，说明科技股隐含波动开始升温。它尚未构成恐慌，但提示NDX对估值、利率或盈利冲击的敏感度正在提高。"
        }
    ],
    "get_vxn_vix_ratio": [
        {
            "context": "【科技相对压力】VXN/VIX比率用于判断科技股波动风险是否相对大盘异常升温。",
            "input": {"function_id": "get_vxn_vix_ratio", "raw_data": {"value": {"level": 1.35, "trend": "rising", "relativity": {"percentile_10y": 82.0}}}},
            "reasoning": "1. 从水平看，1.35 的比率处于历史高分位，说明纳指的波动溢价高于大盘常态。2. 从趋势看，比率继续上行，说明科技股要求的风险补偿在边际抬升。3. 机制是这样的：科技股特有的波动升温时，NDX 的相对风险随之上升，高估值与拥挤持仓的组合会变得更加脆弱。4. 结论是：这是 L2 层传递给 L4 层与 L5 层的重要压力线索。",
            "output_narrative": "VXN/VIX比率升至1.35并处于高分位，说明科技股相对大盘的隐含波动溢价正在抬升。市场并非只是在定价系统性风险，也开始给NDX自身脆弱性要求更高补偿。"
        }
    ],
    "get_ig_oas_bp": [
        {
            "context": "【高质量信用环境观察】投资级OAS反映高质量企业融资环境。它通常比高收益利差更温和，但一旦走阔说明压力开始扩散。注意：输入中的利差读数单位为百分比（FRED 原始口径），行文引用时须写成 X.XX%（约 XXX 个基点）的形式，禁止把百分比数值直接当成基点数来写。",
            "input": {"function_id": "get_ig_oas_bp", "raw_data": {"value": {"level": 1.45, "trend": "short_above_long", "relativity": {"percentile_10y": 72.0}}}},
            "reasoning": "1. 从水平看，当前读数为 1.45%（约 145 个基点），处于偏高分位，说明投资级债券要求的信用补偿不低。2. 从趋势看，短期均线高于长期均线，利差在边际走阔。3. 机制是这样的：当高质量信用债也要求更高补偿时，说明融资条件收紧的范围正在扩大，股权市场的风险偏好因此承压。4. 结论是：如果投资级利差与高收益利差同步扩大，风险偏好恶化的置信度会明显提高。",
            "output_narrative": "投资级信用利差已达1.45%（约145个基点），处于偏高分位且边际走阔，说明融资压力并非只局限在高风险债券。若这一信号与高收益利差同步恶化，股权风险偏好会面临更系统性的压力。"
        }
    ],
    "get_hyg_momentum": [
        {
            "context": "【信用价格确认】HYG（高收益债ETF）的动量把信用风险从利差数值转化为可交易的价格信号，用于确认信用市场是否真的在追逐风险。",
            "input": {"function_id": "get_hyg_momentum", "raw_data": {"value": {"level": 76.2, "trend": "below_ma", "momentum_20d": -2.4}}},
            "reasoning": "1. 价格低于均线且 20 日动量为负，说明高收益债的价格正在走弱。2. 机制是这样的：HYG 下跌说明信用类风险资产正在被卖出，风险偏好从债券一端开始降温。3. 从与股市的关系看，如果股票仍强而 HYG 转弱，通常是信用市场先行发出的警告。4. 结论是：该指标用于检查 L2 层是否存在股票乐观、信用谨慎的背离。",
            "output_narrative": "HYG价格低于均线且20日动量为负，说明高收益信用资产已经出现交易层面的走弱。如果同期股票指数仍维持强势，这会形成信用市场先行谨慎、股票市场滞后乐观的背离。"
        }
    ],
    "get_crowdedness_dashboard": [
        {
            "context": "【拥挤度脆弱性】拥挤交易不是方向判断，而是脆弱性判断。越拥挤，越依赖单一叙事继续成立。",
            "input": {"function_id": "get_crowdedness_dashboard", "raw_data": {"value": {"skew_percentile": 91.0, "put_call_percentile": 12.0, "status": "crowded_long"}}},
            "reasoning": "1. SKEW（偏度指数，反映尾部风险保护的需求）处于高分位，说明尾部保护需求偏高。2. Put/Call 比率（看跌期权与看涨期权的成交比）处于低分位，说明看跌保护购买不足、投机性看涨较多。3. 组合起来的机制是：仓位偏多的同时尾部风险溢价在抬升，说明市场表面乐观、内部结构却脆弱。4. 结论是：拥挤度不必然触发下跌，但会放大坏消息的冲击。",
            "output_narrative": "拥挤度面板显示多头交易偏拥挤，同时尾部风险溢价处于高位。这个组合说明市场仍押注上涨叙事，但一旦宏观或盈利预期被打破，拥挤仓位可能放大回撤。"
        }
    ],
    "get_advance_decline_line": [
        {
            "context": "【广度确认】腾落线是判断指数上涨是否获得多数成分股支持的基础指标。价格创新高但腾落线不确认，是经典结构背离。",
            "input": {"function_id": "get_advance_decline_line", "raw_data": {"value": {"trend": "falling", "index_trend": "rising", "divergence": "bearish"}}},
            "reasoning": "1. 指数趋势向上但腾落线下降，说明上涨股票的数量没有同步扩张。2. 机制是这样的：市场参与度收缩时，指数上涨会更依赖少数权重股，趋势的抗冲击能力随之下降。3. 结论是：这不是直接卖出信号，而是 L5 层的趋势质量必须被打折的结构性警告。",
            "output_narrative": "腾落线下降而指数仍在上行，说明价格强势没有获得多数成分股确认。上涨参与度收缩使指数更依赖少数权重股，趋势的内部根基变得脆弱。"
        }
    ],
    "get_percent_above_ma": [
        {
            "context": "【参与度量化】成分股高于均线比例衡量趋势扩散程度。比例下降但指数上涨，说明上涨越来越集中。",
            "input": {"function_id": "get_percent_above_ma", "raw_data": {"value": {"percent_above_50d": 42.0, "percent_above_200d": 55.0}}},
            "reasoning": "1. 位于 50 日均线上方的成分股比例低于一半，说明短中期参与度偏弱。2. 位于 200 日均线上方的比例仍过半，说明长期结构尚未被全面破坏。3. 机制是这样的：短期广度先走弱，如果这种走弱持续下去，会逐步传导到长期趋势。4. 结论是：这是早期脆弱性信号，需要 L5 层验证价格是否开始失速。",
            "output_narrative": "只有42%的成分股位于50日均线上方，而200日比例仍有55%，说明短中期广度已经走弱但长期结构尚未全面破坏。该信号提示趋势质量正在下降。"
        }
    ],
    "get_m7_fundamentals": [
        {
            "context": "【集中度质量检验】M7（七巨头，指数中市值最大的七家公司）的基本面用于区分“少数巨头有盈利支撑的集中上涨”和“纯粹拥挤炒作”。",
            "input": {"function_id": "get_m7_fundamentals", "raw_data": {"value": {"earnings_growth": 18.0, "revenue_growth": 12.0, "margin_trend": "stable", "beat_rate": 0.75}}},
            "reasoning": "1. 盈利和收入增长仍强，说明巨头的领先有基本面支撑。2. 利润率稳定，未显示盈利质量在快速恶化。3. 机制是这样的：强劲的基本面可以解释集中度的来源，也能延缓市场对广度恶化的惩罚。4. 但集中度风险依然存在：指数对少数公司的业绩失误更加敏感。5. 结论是：这是一种“集中但有基本面支撑”的结构，而不是完全健康的广度结构。",
            "output_narrative": "七巨头仍保持较强收入和盈利增长，说明头部集中并非完全脱离基本面。但这只能解释集中度，不能消除集中风险；指数仍会对少数公司的业绩失误高度敏感。"
        }
    ],
    "get_new_highs_lows": [
        {
            "context": "【动能扩散】新高新低指标衡量上涨是否扩散到更多股票。指数新高但新高股票减少，说明动能变窄。",
            "input": {"function_id": "get_new_highs_lows", "raw_data": {"value": {"new_highs": 18, "new_lows": 32, "trend": "deteriorating"}}},
            "reasoning": "1. 创出新低的股票多于创出新高的股票，说明市场内部动能偏弱。2. 该指标的趋势在恶化，代表上涨未能扩散到更多股票。3. 机制是这样的：创出新高的股票减少时，指数的上涨会更加依赖少数权重股。4. 结论是：如果 L5 层的价格仍然强势，这会构成趋势质量上的背离。",
            "output_narrative": "新低股票数量超过新高股票，且趋势继续恶化，说明市场内部动能没有扩散。即便指数表面强势，其上涨质量也在下降。"
        }
    ],
    "get_mcclellan_oscillator_nasdaq_or_nyse": [
        {
            "context": "【广度动能】McClellan Oscillator衡量上涨/下跌家数的短中期动能，适合识别广度快速恶化或修复。",
            "input": {"function_id": "get_mcclellan_oscillator_nasdaq_or_nyse", "raw_data": {"value": {"level": -68.0, "trend": "falling", "status": "negative"}}},
            "reasoning": "1. 数值为负且继续下行，说明广度动能偏弱。2. 机制是这样的：下跌家数的动能占优时，参与下行的股票会增多，指数的抗跌能力随之下降。3. 从与价格的关系看，如果价格仍在高位，这是短期结构背离；如果价格也转弱，则是确认信号。4. 结论是：应把这个信号传递给 L5 层，检查趋势是否已进入脆弱阶段。",
            "output_narrative": "McClellan Oscillator为负且继续下行，说明广度动能正在恶化。若指数价格仍维持高位，这构成短期结构背离；若价格随后转弱，则会确认趋势质量恶化。"
        }
    ],
    "get_ndx_pe_and_earnings_yield": [
        {
            "context": "【百分位优先】市盈率必须区分当前值和真实历史分位。只有人工/Wind 或 Trendonify 等来源明确给出历史分位时，才能支持“估值处于历史高低分位”的判断；WorldPERatio 给出的相对滚动区间位置只能做交叉校验，yfinance 成分股模型只提供当前值和覆盖率。",
            "input": {
                "function_id": "get_ndx_pe_and_earnings_yield",
                "raw_data": {
                    "value": {
                        "PE": 33.0,
                        "EarningsYield": 3.03,
                        "ThirdPartyChecks": [
                            {"source_name": "Trendonify", "metric": "ndx_trailing_pe", "value": 34.1, "percentile_10y": 86.0},
                            {
                                "source_name": "WorldPERatio",
                                "metric": "ndx_trailing_pe",
                                "value": 32.3,
                                "historical_percentile": None,
                                "relative_position": {
                                    "position_type": "std_dev_context_not_percentile",
                                    "valuation_windows": {"10y": {"deviation_vs_mean_sigma": 1.7, "valuation_label": "Overvalued"}},
                                },
                            },
                        ],
                    },
                    "data_quality": {"source_tier": "component_model", "coverage": {"market_cap_coverage_pct": 92.5}},
                },
            },
            "reasoning": "1. yfinance 成分股模型给出的是当前市盈率和覆盖率，它不能单独承担“估值在历史上处于什么位置”的判断。2. Trendonify 明确给出 86% 的历史分位，因此可以说当前估值处于历史偏高区域。3. WorldPERatio 的市盈率读数与当前值接近，其十年窗口标记为相对滚动均值偏高；但它给出的是相对均值的标准差位置，不是历史分位，不能用它的估值标签冒充分位。4. 盈利收益率约为 3.03%，仍需要和十年期美债收益率以及简式收益差距放在一起看安全垫。5. 结论是：历史分位判断只能来自明确给出分位的来源，WorldPERatio 只负责提供当前值与相对均值位置的辅助描述。",
            "output_narrative": "NDX当前PE约33倍，Trendonify给出的历史分位为86%，支持“估值处于历史偏高位置”的判断。WorldPERatio的PE数值接近，且10年窗口显示相对滚动均值偏高，可辅助描述估值位置，但它没有明确历史分位，不能替代Trendonify或人工/Wind的历史分位。"
        }
    ],
    "get_damodaran_us_implied_erp": [
        {
            "context": "【月度优先】Damodaran 数据是美国市场隐含股权风险溢价的背景参考。只有 ERPbymonth.xlsx 或当月月度文件才能代表最新月度数据，histimpl.xls 只能作为年度历史数据的备选来源。风险溢价的分位方向不能读反：分位越高通常表示风险补偿相对历史越厚，分位越低才表示相对补偿偏薄。",
            "input": {
                "function_id": "get_damodaran_us_implied_erp",
                "raw_data": {
                    "value": {
                        "data_date": "2026-05-01",
                        "erp_t12m_adjusted_payout": 4.24,
                        "erp_t12m_cash_yield": 4.36,
                        "erp_avg_cf_yield_10y": 6.36,
                        "erp_net_cash_yield": 4.15,
                        "erp_normalized_earnings_payout": 3.73,
                        "us_10y_treasury_rate": 4.40,
                        "default_spread": 0.26,
                        "adjusted_riskfree_rate": 4.14,
                        "expected_return": 8.55,
                        "source_file": "ERPbymonth.xlsx",
                        "damodaran_erp_percentile_5y": 42.7,
                        "damodaran_erp_percentile_10y": 37.5,
                        "damodaran_erp_historical_percentiles": {
                            "metric": "Damodaran US implied ERP historical percentile",
                            "scope": "US equity market reference, not NDX PE/PB/Forward PE historical percentile",
                            "windows": {
                                "5y": {"percentile": 42.7, "status": "available", "sample_count": 60, "window_start": "2021-06-01", "window_end": "2026-05-01", "data_cutoff_date": "2026-05-01"},
                                "10y": {"percentile": 37.5, "status": "available", "sample_count": 120, "window_start": "2016-06-01", "window_end": "2026-05-01", "data_cutoff_date": "2026-05-01"},
                            },
                        },
                    }
                },
            },
            "reasoning": "1. 这组数据来自 Damodaran 的月度口径，可以代表当前美国市场的风险补偿背景。2. 多个风险溢价口径分别回答不同的现金流假设，不能只拿一个数字当作唯一真值。3. Damodaran 风险溢价的分位越高，通常说明美国市场风险补偿相对历史越厚，不能把高分位解释成估值风险更高。4. 它不是 NDX 专属估值，也不能替代 NDX 自身的市盈率、前瞻市盈率、市净率或简式收益差距。5. 如果只拿到 histimpl.xls 年度历史表，或分位窗口被标记为历史不足、不可用，就只能把它降级为年度背景或样本不足来处理，不能写成官方月度口径的分位。",
            "output_narrative": "Damodaran 2026-05-01 月度数据给出的美国市场隐含股权风险溢价为 4.24%，官方月度序列计算的五年与十年分位分别为 42.7% 和 37.5%。这组数据说明的是美国市场风险补偿的历史位置，不是 NDX 市盈率、前瞻市盈率或市净率的历史分位，也不能替代 NDX 自身估值或简式收益差距。"
        }
    ],
    "get_qqq_technical_indicators": [
        {
            "context": "【综合技术状态】综合技术面用于建立趋势背景，但不能替代RSI、ADX、成交量等分项确认。",
            "input": {"function_id": "get_qqq_technical_indicators", "raw_data": {"value": {"sma_position": "above_200", "macd_status": "bullish", "bb_position": "near_upper"}}},
            "reasoning": "1. 价格在 200 日均线上方，确认中期上升趋势。2. MACD 偏多，说明短中期动量仍支持趋势。3. 价格接近布林带上轨，说明当前位置偏高，短期追涨的风险上升。4. 结论是：趋势有效但位置不便宜，需要 RSI 与 ATR 进一步判断是否过热。",
            "output_narrative": "QQQ价格位于200日均线上方且MACD偏多，中期趋势仍有效；但价格接近布林带上轨，说明短期位置偏高，追涨的战术风险上升。"
        }
    ],
    "get_rsi_qqq": [
        {
            "context": "【动能过热】RSI 用于识别短期买盘拥挤和动能衰竭的风险。强趋势中 RSI 可以长期停留在高位，但读到极端值时，仍要把它当作降低风险敞口的提醒。",
            "input": {"function_id": "get_rsi_qqq", "raw_data": {"value": {"level": 82.0, "status": "overbought", "divergence": "none"}}},
            "reasoning": "1. RSI 读数 82 处于明显的超买区间。2. RSI 与价格尚未出现背离，说明动能还没有确认衰竭。3. 机制是这样的：RSI 走到极端位置代表短期买盘拥挤，均值回归的风险随之升高，但在强趋势中 RSI 可能在高位继续钝化。4. 结论是：这是战术过热警告，不等同于中期趋势反转。",
            "output_narrative": "RSI升至82的超买区间，提示短期买盘拥挤和均值回归风险上升。由于尚未出现明确背离，它更像战术过热警告，而不是中期趋势已经反转的证据。"
        }
    ],
    "get_atr_qqq": [
        {
            "context": "【波动尺度】ATR 不是方向指标，而是风险边界指标。输入会给出当前读数与 2.5 倍 ATR 止损参考位；波动是否在扩张需要序列或分位证据，输入没有给出时就必须明说。",
            "input": {"function_id": "get_atr_qqq", "raw_data": {"value": {"level": 9.45, "stop_loss_2_5x": 695.34, "date": "2026-09-04"}}},
            "reasoning": "1. ATR 读数 9.45 是日间波动尺度，2.5 倍 ATR 止损参考约为 695.34，可直接用于定义风险边界。2. 本次输入没有给出趋势或历史分位，因此波动是在扩张还是在压缩，无法从这一个读数判断——要如实说明这个边界，不能编造数值。3. 结论是：该指标用于定义 L5 层的风险边界，不承担方向判断。",
            "output_narrative": "QQQ 的 ATR 读到 9.45，对应约 695 的 2.5 倍止损参考位，这是仓位风险边界的直接依据。本次输入没有给出 ATR 的趋势或历史分位，波动算不算扩张需要另外的证据，这里不下结论。"
        }
    ],
    "get_macd_qqq": [
        {
            "context": "【动量边际】MACD用于观察中短期动量的边际变化。趋势强弱要看交叉、柱体和零轴位置。",
            "input": {"function_id": "get_macd_qqq", "raw_data": {"value": {"status": "bullish", "histogram_trend": "falling", "cross_signal": "above_signal"}}},
            "reasoning": "1. MACD 仍在信号线上方，说明动量方向偏多。2. 柱体下降，说明多头动能在边际放缓。3. 机制是这样的：动量方向仍然偏多、但加速度在下降时，趋势本身尚未被破坏，只是追涨的效率在下降。4. 结论是：这是强趋势后段的常见信号，需要价格和均线来确认是否恶化。",
            "output_narrative": "MACD仍保持多头结构，但柱体开始回落，说明趋势方向尚未破坏，动量加速度却在下降。该信号提示追涨效率变低，需要观察价格是否跌破关键均线来确认转弱。"
        }
    ],
    "get_obv_qqq": [
        {
            "context": "【量价确认】OBV（能量潮指标，用成交量累积衡量资金进出）用于判断价格趋势是否获得成交量确认。价格创出新高但 OBV 不确认，就构成量价背离。",
            "input": {"function_id": "get_obv_qqq", "raw_data": {"value": {"obv_trend": "falling", "price_trend": "rising", "divergence": "bearish"}}},
            "reasoning": "1. 价格上行但 OBV 下降，说明成交量累积没有确认价格的强势。2. 机制是这样的：上涨缺少资金净流入的确认时，趋势会更依赖价格惯性，遇到回撤时更加脆弱。3. 结论是：该指标应与 L3 层的广度指标一起使用，共同判断趋势是否空心化。",
            "output_narrative": "OBV下行而价格仍在上涨，形成量价背离。它说明价格强势缺少成交量累积确认，趋势可能更多依赖惯性而非新增资金推动。"
        }
    ],
    "get_volume_analysis_qqq": [
        {
            "context": "【成交量结构】成交量分析区分放量突破、缩量上涨和放量下跌。量能是趋势质量的确认项。",
            "input": {"function_id": "get_volume_analysis_qqq", "raw_data": {"value": {"volume_status": "declining", "price_trend": "rising", "volume_price_relationship": "bearish_divergence"}}},
            "reasoning": "1. 价格上涨但成交量下降，属于缩量上涨。2. 机制是这样的：新增买盘不足时，上涨的质量会下降，价格对坏消息会更加敏感。3. 结论是：这不是趋势反转的确认，但会降低 L5 层对上升趋势的质量评分。",
            "output_narrative": "QQQ呈现缩量上涨结构，说明价格继续走强但新增买盘确认不足。该信号不会单独推翻趋势，却会降低上升趋势的质量和抗冲击能力。"
        }
    ],
    "get_price_volume_quality_qqq": [
        {
            "context": "【量价质量验证】VWAP/MFI/CMF 只回答趋势是否获得成交量加权成本、带量动能和资金流压力确认，不能单独给买卖结论。",
            "input": {"function_id": "get_price_volume_quality_qqq", "raw_data": {"value": {"price_vs_vwap_20": "above", "vwap_deviation_pct": 1.2, "mfi_14": 72.0, "mfi_status": "neutral", "cmf_20": 0.08, "cmf_status": "accumulation"}}},
            "reasoning": "1. 价格位于20日VWAP上方，说明短期价格仍在成交量加权成本之上。2. MFI 72 属于偏强但未到极端超买，带量动能没有明显拥挤失控。3. CMF 为正且处于积累区间，说明收盘位置与成交量共同支持资金流确认。4. 结论：这组指标提高趋势质量置信度，但它不能替代OBV、成交量结构和L3广度确认，更不能推出估值合理。",
            "output_narrative": "VWAP/MFI/CMF 对当前趋势形成温和确认：价格仍在20日成交量加权成本上方，MFI偏强但未极端，CMF显示一定积累压力。它提高L5趋势质量置信度，但不能单独构成买入或长期价值判断。"
        }
    ],
    "get_donchian_channels_qqq": [
        {
            "context": "【通道边界】唐奇安通道用于识别趋势突破和回撤边界。接近上轨代表强势位置，也代表追涨赔率变差。",
            "input": {"function_id": "get_donchian_channels_qqq", "raw_data": {"value": {"donchian_signal": "near_upper", "upper_breakout": False, "distance_to_lower_pct": 7.5}}},
            "reasoning": "1. 价格接近通道上轨，说明当前处于强势区间。2. 价格尚未有效突破上轨，说明还没有形成新的通道突破信号。3. 价格距离下轨较远，意味着一旦发生回撤，下方的技术调整空间较大。4. 结论是：这是趋势强但短期赔率下降的信号。",
            "output_narrative": "价格接近唐奇安通道上轨但尚未有效突破，显示趋势位置强势但追涨赔率下降。由于距离下轨较远，一旦回撤，技术调整空间并不小。"
        }
    ],
    "get_multi_scale_ma_position": [
        {
            "context": "【多周期趋势结构】多周期均线用于判断趋势是否在短期、中期、长期保持一致。短期与长期同强时趋势最稳，短期转弱而长期仍强时是趋势的早期降温。",
            "input": {"function_id": "get_multi_scale_ma_position", "raw_data": {"value": {"short_term": "above", "medium_term": "above", "long_term": "above", "alignment": "bullish"}}},
            "reasoning": "1. 短、中、长期均线均位于价格下方，多周期结构一致偏多。2. 机制是这样的：多个周期的趋势互相印证时，价格回撤会遇到较多层级的支撑，中期趋势的韧性因此较强。3. 风险在于：一致多头也可能意味着趋势已经成熟，需要结合 RSI 与 ATR 判断是否过热。4. 结论是：该指标确认趋势结构，但不单独解决过热问题。",
            "output_narrative": "多周期均线结构一致偏多，价格同时站在短、中、长期均线上方，说明中期趋势韧性较强、支撑层级较多。但一致多头也可能意味着趋势成熟，需要结合RSI和ATR判断过热程度。"
        }
    ],
}

for _function_id, _examples in _VNEXT_CONTEXT_FIRST_EXAMPLES.items():
    PROMPT_EXAMPLES.setdefault(_function_id, _examples)

# --- 架构校验函数 ---

def validate_prompt_examples(registry: PromptExamplesRegistry) -> bool:
    """
    执行双重校验：
    1. 内部Schema校验 (确保4C字段存在)。
    2. 外部注册表交叉校验 (确保 function_id 存在于 tools.py)。
    """
    if not TOOLS_REGISTRY:
        logging.error("TOOLS_REGISTRY 为空，无法执行外部校验。")
        return False

    logging.info("正在启动 [4C-Prompting] 架构完整性校验...")
    
    example_keys = set(registry.keys())
    tool_keys = set(TOOLS_REGISTRY.keys())
    
    # 1. 外部交叉校验 (确保 PROMPT_EXAMPLES 的键都在 TOOLS_REGISTRY 中)
    missing_in_tools = example_keys - tool_keys
    if missing_in_tools:
        logging.critical("!!! 架构违规：发现未在 'tools.py' 中注册的范例键!!!")
        for key in missing_in_tools:
            logging.error(f"  -> '{key}' 存在于 'prompt_examples.py' 但未在 'tools.py' 的 TOOLS_REGISTRY 中找到。")
        return False # 快速失败

    # 2. 内部Schema校验
    for func_id, examples in registry.items():
        if not isinstance(examples, list) or not examples:
            logging.error(f"架构违规: '{func_id}' 的范例必须是一个非空列表。")
            return False
        
        for i, ex in enumerate(examples):
            # 2a. 检查4C原则的强制字段
            required_keys = {"context", "input", "reasoning", "output_narrative"}
            missing_keys = required_keys - set(ex.keys())
            if missing_keys:
                logging.error(f"Schema违规: '{func_id}' 的范例 {i+1} 缺失4C原则字段: {missing_keys}")
                return False
            
            # 2b. 检查 input 内部的逻辑 (必须有 'function_id' 或 'comment')
            input_data = ex.get("input", {})
            if "function_id" not in input_data and "comment" not in input_data:
                logging.error(f"Schema违规: '{func_id}' 的范例 {i+1} 的 'input' 字段必须包含 'function_id' 或 'comment'。")
                return False

    logging.info("...[4C-Prompting] 架构完整性校验通过。所有认知范例均已正确绑定至感知层。")
    return True

# --- 校验函数结束 ---


def _format_examples(example_list: list) -> list:
    """(内部辅助函数) 将范例字典格式化为字符串列表"""
    example_str_list = []
    for ex in example_list:
        # 对于逻辑组合输入，我们只展示其comment
        if ex['input'].get('comment'):
            input_str = f"INPUT: {ex['input']['comment']}"
        else:
            input_str = f"INPUT: {json.dumps(ex['input'])}"
            
        example_str_list.append(
            f"  - CONTEXT: {ex['context']}\n"
            f"    {input_str}\n"
            f"    REASONING: {ex['reasoning']}\n"
            f"    CORRECT OUTPUT: {ex['output_narrative']}"
        )
    return example_str_list
