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
1. 触发镜头: 斯坦利·德鲁肯米勒。
2. 核心哲学: 寻找流动性、情绪和价格信号的共振或背离。
3. 数据质询(L1/L5): L5价格强劲，但L1实际利率正在攀升。这是一个核心背离。
4. 数据质询(L2-VIX): L2的VIX处于12.5的极低水平。
5. [战术优化：非对称性]: VIX极低意味着市场自满，同时也意味着下行保护（如看跌期权）极其廉价。
6. 结论: 支撑市场的核心驱动力（低利率）正在撤退，但市场（L5）仍在惯性上涨。这是一个极其危险的信号，同时低VIX为建立非对称的空头头寸（廉价对冲）提供了完美时机。
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
1. 触发镜头: NDX-Command 之魂。
2. 核心哲学: 价值买入，趋势卖出。
3. 数据质询(巴菲特之魂): 回顾镜头1，结论是‘不’批准买入。
4. 数据质询(利弗莫尔之手): 回顾镜头2，结论是‘未’触发卖出。
5. 裁决: 触发情景B (价值×, 趋势√)。
6. 结论: ‘价值买入’纪律禁止任何新仓位。‘趋势卖出’纪律尚未触发。最终裁决为‘高风险持有，绝对禁止新购入’。
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
            "context": "【典范化解读 + 分层降噪V5.8】10Y-2Y收益率曲线是全球最重要的经济衰退领先指标。L1宏观层用 MA20 乖离率衡量趋势，替代日度动量。",
            "input": {"function_id": "get_10y2y_spread_bp", "raw_data": {"value": {"level": -55.2, "deviation_pct": -8.5, "position_vs_ma": "below", "ma": -50.8, "relativity": {"percentile_10y": 5.2}}}},
            "reasoning": "1. **典范识别**: 负值水平(-55.2bp)意味着曲线处于'深度倒挂'状态，这是历史上最高胜率的经济衰退预警信号。2. **分层降噪**: 当前水平显著低于MA20(-50.8bp)，乖离率-8.5%表明利差在趋势上仍在加深倒挂。3. **专业结论**: 市场不仅发出了衰退警报，且趋势尚未见底，反映出对未来6-18个月经济前景的极度悲观预期正在固化。",
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
            "context": "【因果化解读 + 分层降噪】10年期实际利率是成长股估值的真正'地心引力'。L1宏观层使用MA20乖离率替代日度动量。",
            "input": {"function_id": "get_10y_real_rate", "raw_data": {"value": {"level": 2.5, "deviation_pct": 8.3, "position_vs_ma": "above", "ma": 2.31}}},
            "reasoning": "因果链如下：[因] 实际利率是无风险资产的真实回报率，代表了所有风险资产的机会成本 -> [逻辑推导] 当实际利率上升时，用于计算未来现金流现值的贴现率随之提高 -> [结果] 对于依赖遥远未来现金流的成长股（如纳斯达克100），其内在价值会受到系统性的、数学上的向下重估。分层降噪：当前水平(2.5%)显著高于MA20(2.31%)，乖离率+8.3%表明利率在趋势上仍在上行通道，这种压力正在持续增加。",
            "output_narrative": "作为成长股估值的核心驱动力，10年期实际利率已上升至2.5%的高位，显著高于其20日均线（乖离率+8.3%），表明利率在趋势上仍处于上行通道，直接提高了未来现金流的贴现率，对纳斯达克100的估值倍数构成了强大的、系统性的下行压力。"
        }
    ],

    # =================================================================
    # Layer 2: 市场风险偏好 (L2)
    # =================================================================

    # "high_yield_oas" -> 重命名为 "get_hy_oas_bp"
    "get_hy_oas_bp": [
        {
            "context": "【语境化解读 + 分层降噪V5.8】高收益信用利差(OAS)是'聪明钱'对风险的真实定价。L1宏观层用 MA5 vs MA20 趋势方向替代日度动量。",
            "input": {"function_id": "get_hy_oas_bp", "raw_data": {"value": {"level": 620.0, "trend": "short_above_long", "short_ma": 618.0, "long_ma": 595.0, "relativity": {"percentile_10y": 92.3}}}},
            "reasoning": "1. **语境定位**: 这个指标反映金融体系中最专业资本（债券市场）的态度。2. **水平解读**: 620个基点远高于历史均值，进入经济衰退或金融压力时期的危险区域，10年百分位92.3%确认了极端性。3. **趋势解读**: MA5(618.0)高于MA20(595.0)，trend='short_above_long'表明利差在周度趋势上仍在扩大，信贷环境正在收紧。4. **综合叙事**: '聪明钱'不仅在大声呼喊风险，且趋势方向支持风险正在上升，股市的乐观情绪极其脆弱。",
            "output_narrative": "作为'聪明钱'风险偏好的领先指标，高收益信用利差已飙升至620个基点的危机水平（10年百分位92.3%），且MA5高于MA20，趋势方向表明利差仍在扩大。信贷市场正在对严重的经济衰退风险进行定价，金融系统压力急剧升高。"
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
            "reasoning": "1. **水平解读**: 得分14.59处于'极度恐惧'区间（<25），市场情绪已跌至历史极端悲观水平。2. **历史对比**: 相比一周前的22.63，情绪在短短一周内急剧恶化，变化速度极快。相比一个月前的44.41（中性偏恐惧），市场情绪发生了根本性逆转。3. **子指标验证**: 7个子指标中多个处于'extreme fear'，尤其是市场动量(1.2)和Put/Call比率(3.6)，确认了恐慌的广泛性。4. **反向信号**: 历史上，FGI<20时的6个月后市场平均收益约+24%，极端恐惧往往对应逆向买入机会。5. **与VIX交叉验证**: VIX子指标得分40.7（恐惧），与整体指数形成共振，增强了信号的可靠性。",
            "output_narrative": "CNN恐贪指数已跌至14.59的'极度恐惧'区间，在过去一周内从22.63急剧恶化，市场情绪发生了根本性逆转。7个子指标中多个确认了恐慌的广泛性。作为反向指标，历史上FGI<20时的6个月后市场平均收益约+24%，当前极端恐惧水平可能意味着逆向买入机会。"
        },
        {
            "context": "【反向指标典范 · 极度贪婪】当恐贪指数处于极度贪婪区间（>75），市场过度乐观，需警惕均值回归风险。",
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
            "reasoning": "1. **水平解读**: 得分82.5处于'极度贪婪'区间（>75），市场情绪已达到历史极端乐观水平。2. **趋势加速**: 相比一周前的72.1，情绪在加速贪婪化，变化方向不利于风险控制。3. **子指标验证**: 市场动量(88)和股价强度(92)均处于极度贪婪，市场上涨完全依赖情绪驱动。4. **风险警示**: 历史上，FGI>80时的3个月后市场平均收益为负，极度贪婪往往预示着均值回归风险。5. **与VIX背离检查**: 若VIX子指标仍处于低位，则确认市场对风险毫无防备，脆弱性极高。",
            "output_narrative": "CNN恐贪指数已飙升至82.5的'极度贪婪'区间，过去一周内从72.1加速上行。多个子指标确认市场情绪全面过热。历史上FGI>80后的3个月市场平均收益为负，当前极度贪婪水平意味着均值回归风险显著升高，需高度警惕潜在回调。"
        }
    ],

    # "consumer_risk_appetite_ratio" -> 重命名为 "get_xly_xlp_ratio"
    "get_xly_xlp_ratio": [
        {
            "context": "【典范化解读】XLY/XLP比率是消费者风险偏好指标。分层降噪：用比值相对 MA20 的位置替代日度动量。",
            "input": {"function_id": "get_xly_xlp_ratio", "raw_data": {"value": {"level": 1.5, "position_vs_ma20": "below", "ma20": 1.58}}},
            "reasoning": "逻辑链：[因] XLY代表消费者乐观，XLP代表避险需求 -> [逻辑推导] 当比值处于MA20下方(position_vs_ma20=below)，说明消费者行为模式正从'进攻'转向'防御' -> [结果] 这种行为模式转变是消费者信心恶化的证据，通常领先于官方经济数据下滑，是经济即将放缓的可靠预警。",
            "output_narrative": "作为衡量真实世界风险偏好的关键代理，XLY/XLP（非必需/必需消费品）比率已回落至20日均线下方，典范性地表明消费者信心正在减弱，支出行为模式正转向防御，这是经济放缓的早期预警信号。"
        },
        {
            "context": "【10年历史极值 · 典范】教会模型在风险偏好比率(XLY/XLP)处于 10年百分位极端时，使用“统计学非对称性”的语言，强调赔率已严重失衡，不鼓励在极端高位继续追多。",
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
                "1. `level=2.1` 已经处在历史相对高位，意味着非必需消费(XLY)相对于必需消费(XLP)的相对强势极为明显。\n"
                "2. 关键在 `percentile_10y=99.2`：在十年样本中，这一位置几乎是“天花板级别”的极值，历史上只有极少数时点能达到或超过这一分位。\n"
                "3. 从统计学角度看，这种极端百分位意味着：\n"
                "   - 向上再走同量级空间的概率极低；\n"
                "   - 而向下向均值回归的概率和空间都极具吸引力，赔率结构已经明显向“减仓风险偏好”一侧倾斜。\n"
                "4. 因此，在 99.2% 的 10年历史百分位上继续追多风险偏好，本质上是“赢面极小、亏损尾部极肥”的坏赔率交易，不符合专业风控纪律。"
            ),
            "output_narrative": (
                "风险偏好比率 XLY/XLP 已经冲到 10年历史分布的 99.2% 极端高位，"
                "这在统计学上几乎可以视作长期样本的“天花板区间”。"
                "在这样的历史极值附近继续无脑追多风险资产，胜率和赔率空间都已被严重压缩，"
                "均值回归的引力几乎拉满——向上的“惊喜”极其有限，而向下的回撤却可能异常陡峭，"
                "这是一个典型的“统计学非对称性”场景：赢面极小、风险尾部极肥。"
            )
        }
    ],
    
    # "qqq_net_liquidity_ratio" -> 新增 get_qqq_net_liquidity_ratio
    "get_qqq_net_liquidity_ratio": [
        {
            "context": "【流动性 vs 估值 · 背离典范】教会模型识别：当净流动性走平/下滑，而QQQ大涨导致比率飙升时，这不是“流动性驱动”，而是“估值倍数扩张”在裸奔。",
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
                "1. 先看分子分母：净流动性并未上升（flat/down），但QQQ价格飙升，导致比率跳升至 3.25。\n"
                "2. 这意味着上涨不是货币投放驱动，而是单纯依靠估值倍数抬升（multiple expansion）。\n"
                "3. 历史分位 5y/10y > 94% 强化了“极端拉伸”属性：这是少见的流动性/价格背离。\n"
                "4. 因果链：缺乏增量流动性支撑 → 价格依赖情绪与估值扩张 → 泡沫化特征加剧，回撤弹性增大。"
            ),
            "output_narrative": (
                "QQQ/净流动性比率在流动性走平甚至下滑的环境下却飙到历史高分位，"
                "这不是“水多船高”，而是“缺水但船硬被抬高”的估值倍数扩张。"
                "这种流动性与估值的背离属于典型泡沫化特征——缺乏货币支撑的价格上冲，"
                "回撤时往往更脆弱，风险补偿显著恶化。"
            )
        },
        {
            "context": "【历史统计极值 · 10年99分位】教会模型在任何指标的 10y 百分位接近 99% 时，使用“统计学非对称性”框架强调均值回归引力。",
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
                "1. `percentile_10y=99.1` 处于十年分布的极端高位，属于统计学“尾部”区域。\n"
                "2. 在这种尾部，向上再获得同量级正向超额的概率极低；向均值回归的概率和幅度则显著放大。\n"
                "3. Z分数>2 进一步量化了偏离均值的程度，说明当前水平与长期均衡存在显著“张力”。\n"
                "4. 因果结论：赔率结构严重失衡，继续追多是“赢面极小、亏损尾部极肥”的坏交易，"
                "均值回归的引力主导未来路径。"
            ),
            "output_narrative": (
                "该指标已站上 10年样本的 99% 极值区间，属于统计学上的“不可持续”水平。"
                "在这种尾部区域，继续向上获得同等幅度超额的概率极低，而向下向均值回归的空间和概率都在放大。"
                "这是典型的坏赔率交易：赢面极小，风险尾部极肥，均值回归的引力几乎占据主导。"
            )
        }
    ],

    # =================================================================
    # Layer 3: 指数内部健康度 (L3)
    # =================================================================

    # "market_breadth_ratio" -> 重命名为 "get_qqq_qqew_ratio" (这是其对应的function_id)
    "get_qqq_qqew_ratio": [
        {
            "context": "【典范化解读】QQQ/QQEW比率最核心应用是识别'熊市背离'。分层降噪：用比值趋势(MA20)与价格趋势(MA60)双重过滤器。",
            "input": {
                "function_id": "get_qqq_qqew_ratio",
                "raw_data": {
                    "value": {
                        "level": 1.85,
                        "ratio_trend_vs_ma20": "below",
                        "qqq_price_vs_ma60": "above",
                        "ratio_ma20": 1.88,
                        "qqq_ma60": 485.0
                    }
                }
            },
            "reasoning": "这是一个经典的顶部警报。现象：QQQ价格在MA60上方(above)，指数趋势尚可。本质：但QQQ/QQEW比率已回落至MA20下方(below)，说明'将军'相对'士兵'的领先优势正在收窄。结论：上涨缺乏广泛群众基础，是'空心胜利'。领导力收窄的背离表明趋势内在结构脆弱，极易因少数领头羊回调而崩溃。",
            "output_narrative": "市场广度出现经典的熊市背离：尽管QQQ价格仍在60日均线之上，但其与等权重指数(QQEW)的比率已回落至20日均线之下，典范性地表明上涨仅由少数巨头支撑，趋势的内在健康度严重恶化，根基极其脆弱。"
        }
    ],

    # =================================================================
    # Layer 1 (扩展): 流动性三剑客 · 美元净流动性 (Net Liquidity)
    # =================================================================
    "get_net_liquidity_momentum": [
        {
            "context": "【流动性三剑客 · 典范 1】教会模型识别“Fed 缩表 + TGA 补库”叠加导致的双重紧缩 (Double Tightening) 场景，用于解释为什么在表面只是QT的环境下，市场会遭遇远超预期的估值压力。",
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
                "1. 首先聚焦 `momentum_4w=-120.5`：4周滚动净流动性动量为 -120.5B，属于幅度极大的负值，"
                "典型地对应“系统性抽水”而非日常波动。\n"
                "2. 然后拆解 components：\n"
                "   - `fed_assets` 相比前期明显下降，说明美联储正在持续缩表（QT）。\n"
                "   - `tga` 余额在高位继续抬升，意味着财政部通过加大发债、补库，把银行体系的流动性锁回财政账户，"
                "     相当于第二条抽水管。\n"
                "   - `rrp` 大致稳定，既没有释放流动性，也没有提供缓冲。\n"
                "3. 因果链条为：Fed 资产缩表抽水 + TGA 补库再抽水 + RRP 不释放冗余资金 -> "
                "三剑客中只有“紧缩力量”，没有“对冲力量”。\n"
                "4. 因此，这不是普通的QT，而是宏观层面的“双重紧缩 (Double Tightening)”，"
                "对高估值资产和杠杆头寸的压力远超单一缩表所能解释的程度。"
            ),
            "output_narrative": (
                "流动性三剑客给出了一个极其罕见的“双重紧缩”信号："
                "在过去四周，净流动性动量已经急剧下滑约 120.5 亿美元，其背后是美联储持续缩表，"
                "叠加财政部大幅补库存、把银行体系的现金锁回 TGA 账户，而 RRP 一直高位僵持、并未释放缓冲。"
                "换言之，货币端和财政端正从同一侧同时抽水，这种组合为估值和风险资产带来的宏观逆风极为严峻。"
            )
        },
        {
            "context": "【流动性三剑客 · 典范 2】教会模型识别“隐形对冲 / 隐形放水 (Stealth Liquidity)”：在名义上处于QT周期，但通过RRP释放，对冲甚至部分逆转缩表效果。",
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
                "1. 表面上看，`fed_assets` 较前期仍在下行，美联储名义上处于持续缩表(QT)状态。\n"
                "2. 但 `momentum_4w=10.2` 表明，经过 20 日平滑后的净流动性在过去四周整体是略有上升的，"
                "这与“单纯缩表=持续抽水”的直觉相反。\n"
                "3. 关键在于 `rrp`：隔夜逆回购余额从更高水平显著回落，意味着原本停泊在美联储资产负债表之外的“冷冻现金”"
                "正在被释放回银行和货币市场体系，对冲甚至部分逆转了资产端缩表的紧缩效应。\n"
                "4. `tga` 账户基本稳定，没有额外财政补库抽水动作，因此三剑客中的主要变量是："
                "“资产端略缩表 + RRP 大幅释放” → 净流动性总体微升。\n"
                "5. 因果结论：这是一个典型的“隐形对冲 / 隐形放水 (Stealth Liquidity)”场景，"
                "名义上在QT，实质上净流动性并未恶化，甚至为风险资产提供了缓冲环境。"
            ),
            "output_narrative": (
                "从三剑客的组合来看，这是一次典型的“隐形对冲”："
                "美联储账面上仍在温和缩表，但大规模的 RRP 回落将此前被冻结在逆回购池中的现金重新释放回市场，"
                "使得过去四周的净流动性动量反而小幅转正。"
                "在这种格局下，表面上的“紧缩叙事”与资产价格的相对坚挺并不矛盾——"
                "名义上是QT，实质上却存在一条通过RRP缓慢放水的暗渠，这正是当前“隐形放水”配置环境的核心。"
            )
        }
    ],

    # =================================================================
    # Layer 4: 指数基本面估值 (L4)
    # =================================================================

    # Historical function name kept for compatibility; output is now the NDX simple yield gap.
    "get_equity_risk_premium": [
        {
            "context": "【语境化解读】简式收益差距是 earnings_yield 或 fcf_yield 减去10年期美债收益率，只能衡量当前收益率安全垫，不能写成 Damodaran 式 implied ERP。",
            "input": {"function_id": "get_equity_risk_premium", "raw_data": {"value": {"level": -0.5, "relativity": {"percentile_1y": 5.0}}}},
            "reasoning": "1. **核心语境**: 简式收益差距只比较当前盈利/现金流收益率与10年期美债收益率。2. **水平解读**: -0.5%说明当期收益率垫子为负，高估值更依赖未来增长、质量溢价或风险偏好维持。3. **相对性解读**: 处于1年期低分位，说明这一安全垫在近期样本中也偏薄。4. **专业结论**: 这不是完整 implied ERP，也不是单独交易信号；它要求 L1/L2/L3/L5 验证利率、情绪、广度和趋势是否足以支撑估值。",
            "output_narrative": "NDX简式收益差距为-0.5%，说明当前盈利/现金流收益率相对10年期美债缺少正安全垫。该指标不是 Damodaran 式 implied ERP，只能作为估值脆弱性和跨层验证需求的锚点。"
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
            "reasoning": "1. **强度判断(ADX)**: ADX读数为48.0，远高于25的强弱分界线，这典范性地表明市场正处于一段**强劲的趋势**中。2. **方向判断(+DI/-DI)**: -DI(mdi=45.0)远高于+DI(pdi=12.0)，这清晰地指明了当前这段强劲趋势的**方向是'向下'的**。3. **综合结论**: 市场并非在'震荡'或'盘整'，而是处于一段主导性的、能量十足的下跌趋势之中。",
            "output_narrative": "ADX读数为48.0，远超25的强趋势阈值，典范性地表明市场存在强劲趋势。结合-DI(45.0)远高于+DI(12.0)，明确指示当前市场正处于一段由空头主导的、强劲的下跌趋势中。"
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
            "reasoning": "1. 水平：5.25%处于10年高分位，说明政策利率仍在限制性区间。2. 趋势：stable意味着压力没有继续加速，但也没有解除。3. 机制：现金收益率高 -> 股票风险溢价要求上升 -> 高估值成长股需要更强盈利才能维持倍数。4. 层内结论：这不是立即看空价格的信号，而是L4估值必须面对的折现率约束。",
            "output_narrative": "联邦基金利率维持在5.25%的限制性高位，虽然没有继续上行，但现金和短债的机会成本仍然很高。对纳斯达克100而言，这意味着高估值资产需要用更强盈利来抵消折现率压力。"
        }
    ],
    "get_10y_treasury": [
        {
            "context": "【名义长端利率拆解】10年期美债收益率同时包含真实利率、通胀补偿和增长预期，不能只把上行机械解释为利空。",
            "input": {"function_id": "get_10y_treasury", "raw_data": {"value": {"level": 4.55, "trend": "rising", "position_vs_ma": "above"}}},
            "reasoning": "1. 水平：4.55%的10年期利率会抬高长期现金流折现率。2. 趋势：高于均线且上行，说明长端折现压力边际增强。3. 分解：若上行主要来自真实利率，对估值最不利；若来自增长预期，则可能部分被盈利预期抵消。4. 结论：该指标应作为L4估值压力和L1内部利率结构的确认信号，而非单独定性。",
            "output_narrative": "10年期美债收益率升至4.55%并处于上行趋势，长端折现率压力边际增强。其含义取决于真实利率与通胀预期的拆分：真实利率驱动更压估值，增长预期驱动则可能被盈利改善部分抵消。"
        }
    ],
    "get_10y_breakeven": [
        {
            "context": "【通胀预期分解】盈亏平衡通胀用于判断名义利率变化是否来自通胀补偿。它决定市场是否担心通胀重新约束美联储。",
            "input": {"function_id": "get_10y_breakeven", "raw_data": {"value": {"level": 2.42, "trend": "rising", "relativity": {"percentile_10y": 63.0}}}},
            "reasoning": "1. 水平：2.42%不算极端，但高于美联储目标。2. 趋势：上行代表市场重新要求通胀补偿。3. 机制：通胀预期升温 -> 降息空间受限 -> 政策利率维持更久 -> 成长股估值折现压力延续。4. 结论：该指标的核心作用是解释长端利率上行是否会延长L1限制性状态。",
            "output_narrative": "10年期盈亏平衡通胀处于2.42%并边际上行，显示市场对通胀补偿的要求有所抬升。它不直接决定股价，但会限制政策转松空间，使高利率对估值的约束更难快速解除。"
        }
    ],
    "get_m2_yoy": [
        {
            "context": "【货币量慢变量】M2同比不是交易触发器，而是中期流动性土壤。负增长或低增长说明货币扩张不能为估值扩张提供宽松背景。",
            "input": {"function_id": "get_m2_yoy", "raw_data": {"value": {"level": -1.8, "trend": "falling", "relativity": {"percentile_10y": 8.0}}}},
            "reasoning": "1. 水平：M2同比为负，属于历史罕见的货币收缩状态。2. 趋势：继续下行说明中期流动性环境没有改善。3. 机制：货币增速收缩 -> 金融体系风险承受能力下降 -> 估值扩张缺少宏观燃料。4. 结论：它强化L1偏紧判断，但因传导慢，需要与净流动性和风险偏好交叉验证。",
            "output_narrative": "M2同比为-1.8%且仍在下行，说明货币层面的中期流动性土壤偏紧。它不是短线择时信号，但会降低市场持续估值扩张的宏观容错率。"
        }
    ],
    "get_copper_gold_ratio": [
        {
            "context": "【增长预期代理】铜金比衡量周期增长偏好相对避险需求。上行代表增长预期改善，下行代表增长担忧或避险升温。",
            "input": {"function_id": "get_copper_gold_ratio", "raw_data": {"value": {"level": 0.21, "position_vs_ma": "below", "trend": "falling"}}},
            "reasoning": "1. 水平本身意义有限，关键看相对均线和方向。2. 低于均线且下行，说明铜相对黄金走弱。3. 机制：增长敏感资产弱于避险资产 -> 市场降低周期增长预期 -> 盈利和风险偏好承压。4. 结论：该指标若与期限利差或信用利差共振，会强化宏观增长压力判断。",
            "output_narrative": "铜金比低于均线并继续下行，说明增长敏感资产相对避险资产走弱。这个信号指向增长预期降温，会削弱盈利韧性叙事，并需要与信用和期限结构共同验证。"
        }
    ],
    "get_vix": [
        {
            "context": "【波动率反身性】VIX低不等于风险低。低VIX可能代表环境平稳，也可能代表市场对尾部风险定价过低。",
            "input": {"function_id": "get_vix", "raw_data": {"value": {"level": 12.8, "relativity": {"percentile_10y": 12.0}, "trend": "falling"}}},
            "reasoning": "1. 水平：12.8处于历史低分位，市场隐含波动很便宜。2. 趋势：继续下行说明风险定价进一步压缩。3. 机制：保护便宜 -> 市场自满 -> 一旦宏观或盈利冲击出现，波动率回升会放大价格回撤。4. 结论：这是risk-on的表象，同时也是非对称下行风险的来源。",
            "output_narrative": "VIX处于12.8的低位并继续下行，表面上显示市场环境平稳、风险偏好较强；但低波动也意味着保护成本便宜和自满风险上升，一旦出现宏观或盈利冲击，波动率回补会放大回撤。"
        }
    ],
    "get_vxn": [
        {
            "context": "【科技股波动率】VXN是纳指专属隐含波动率，能识别科技股内部压力是否高于大盘。",
            "input": {"function_id": "get_vxn", "raw_data": {"value": {"level": 18.5, "trend": "rising", "relativity": {"percentile_10y": 45.0}}}},
            "reasoning": "1. 水平：18.5处于中位附近，不是恐慌。2. 趋势：上行说明科技股隐含波动边际升温。3. 机制：科技股波动预期上升 -> 对高估值/高久期资产的风险折价提高 -> NDX相对大盘更脆弱。4. 结论：需要与VIX比率共同判断是否为科技特异性压力。",
            "output_narrative": "VXN处于18.5的中性区间但边际上行，说明科技股隐含波动开始升温。它尚未构成恐慌，但提示NDX对估值、利率或盈利冲击的敏感度正在提高。"
        }
    ],
    "get_vxn_vix_ratio": [
        {
            "context": "【科技相对压力】VXN/VIX比率用于判断科技股波动风险是否相对大盘异常升温。",
            "input": {"function_id": "get_vxn_vix_ratio", "raw_data": {"value": {"level": 1.35, "trend": "rising", "relativity": {"percentile_10y": 82.0}}}},
            "reasoning": "1. 水平：1.35且处于高分位，说明纳指波动溢价高于大盘常态。2. 趋势：继续上行，科技股风险补偿边际抬升。3. 机制：科技特异性波动升温 -> NDX相对风险上升 -> 高估值和拥挤持仓更脆弱。4. 结论：这是L2传递给L4/L5的重要压力线索。",
            "output_narrative": "VXN/VIX比率升至1.35并处于高分位，说明科技股相对大盘的隐含波动溢价正在抬升。市场并非只是在定价系统性风险，也开始给NDX自身脆弱性要求更高补偿。"
        }
    ],
    "get_ig_oas_bp": [
        {
            "context": "【高质量信用温度计】投资级OAS反映高质量企业融资环境。它通常比高收益利差更温和，但一旦走阔说明压力开始扩散。",
            "input": {"function_id": "get_ig_oas_bp", "raw_data": {"value": {"level": 145.0, "trend": "short_above_long", "relativity": {"percentile_10y": 72.0}}}},
            "reasoning": "1. 水平：145bp处于偏高分位，投资级信用补偿要求不低。2. 趋势：短均线高于长均线，利差边际走阔。3. 机制：高质量信用也要求更高补偿 -> 融资条件收紧范围扩大 -> 股权风险偏好承压。4. 结论：若与HY OAS同步扩大，风险偏好恶化置信度明显提高。",
            "output_narrative": "投资级信用利差处于偏高分位且边际走阔，说明融资压力并非只局限在高风险债券。若这一信号与高收益利差同步恶化，股权风险偏好会面临更系统性的压力。"
        }
    ],
    "get_hyg_momentum": [
        {
            "context": "【信用价格确认】HYG动量把信用风险从利差读数转化为可交易价格信号，用于确认信用市场是否真正risk-on。",
            "input": {"function_id": "get_hyg_momentum", "raw_data": {"value": {"level": 76.2, "trend": "below_ma", "momentum_20d": -2.4}}},
            "reasoning": "1. 价格低于均线且20日动量为负，说明高收益债价格走弱。2. 机制：HYG下跌 -> 信用风险资产被卖出 -> 风险偏好从债券端降温。3. 与股市关系：如果股票仍强而HYG转弱，通常是信用先行警告。4. 结论：该指标用于检查L2是否存在股票乐观、信用谨慎的背离。",
            "output_narrative": "HYG价格低于均线且20日动量为负，说明高收益信用资产已经出现交易层面的走弱。如果同期股票指数仍维持强势，这会形成信用市场先行谨慎、股票市场滞后乐观的背离。"
        }
    ],
    "get_crowdedness_dashboard": [
        {
            "context": "【拥挤度脆弱性】拥挤交易不是方向判断，而是脆弱性判断。越拥挤，越依赖单一叙事继续成立。",
            "input": {"function_id": "get_crowdedness_dashboard", "raw_data": {"value": {"skew_percentile": 91.0, "put_call_percentile": 12.0, "status": "crowded_long"}}},
            "reasoning": "1. SKEW高分位说明尾部保护需求偏高。2. Put/Call低分位说明看跌保护购买不足或投机看涨较多。3. 组合机制：仓位偏多 + 尾部风险溢价抬升 -> 市场表面乐观但结构脆弱。4. 结论：拥挤度不必然触发下跌，但会放大坏消息冲击。",
            "output_narrative": "拥挤度面板显示多头交易偏拥挤，同时尾部风险溢价处于高位。这个组合说明市场仍押注上涨叙事，但一旦宏观或盈利预期被打破，拥挤仓位可能放大回撤。"
        }
    ],
    "get_advance_decline_line": [
        {
            "context": "【广度确认】腾落线是判断指数上涨是否获得多数成分股支持的基础指标。价格创新高但腾落线不确认，是经典结构背离。",
            "input": {"function_id": "get_advance_decline_line", "raw_data": {"value": {"trend": "falling", "index_trend": "rising", "divergence": "bearish"}}},
            "reasoning": "1. 指数趋势向上但腾落线下降，说明上涨股票数量没有同步扩张。2. 机制：参与度收缩 -> 指数依赖少数权重 -> 趋势抗冲击能力下降。3. 结论：这不是直接卖出信号，而是L5趋势质量必须被打折的结构性警告。",
            "output_narrative": "腾落线下降而指数仍在上行，说明价格强势没有获得多数成分股确认。上涨参与度收缩使指数更依赖少数权重股，趋势的内部根基变得脆弱。"
        }
    ],
    "get_percent_above_ma": [
        {
            "context": "【参与度量化】成分股高于均线比例衡量趋势扩散程度。比例下降但指数上涨，说明上涨越来越集中。",
            "input": {"function_id": "get_percent_above_ma", "raw_data": {"value": {"percent_above_50ma": 42.0, "percent_above_200ma": 55.0, "trend": "falling"}}},
            "reasoning": "1. 50日均线上方比例低于一半，短中期参与度偏弱。2. 200日比例仍过半，长期结构尚未全面破坏。3. 机制：短期广度先走弱 -> 若持续会传导到长期趋势。4. 结论：这是早期脆弱性信号，需要L5验证价格是否开始失速。",
            "output_narrative": "只有42%的成分股位于50日均线上方，而200日比例仍有55%，说明短中期广度已经走弱但长期结构尚未全面破坏。该信号提示趋势质量正在下降。"
        }
    ],
    "get_m7_fundamentals": [
        {
            "context": "【集中度质量检验】M7基本面用于区分“少数巨头有盈利支撑的集中上涨”和“纯粹拥挤炒作”。",
            "input": {"function_id": "get_m7_fundamentals", "raw_data": {"value": {"earnings_growth": 18.0, "revenue_growth": 12.0, "margin_trend": "stable", "beat_rate": 0.75}}},
            "reasoning": "1. 盈利和收入增长仍强，说明巨头领先有基本面支撑。2. 利润率稳定，未显示盈利质量快速恶化。3. 机制：强基本面可解释集中度，也能延缓广度恶化的惩罚。4. 但集中度风险仍存在：指数对少数公司业绩失误更敏感。5. 结论：这是concentrated-but-supported，而不是完全健康的广度结构。",
            "output_narrative": "七巨头仍保持较强收入和盈利增长，说明头部集中并非完全脱离基本面。但这只能解释集中度，不能消除集中风险；指数仍会对少数公司的业绩失误高度敏感。"
        }
    ],
    "get_new_highs_lows": [
        {
            "context": "【动能扩散】新高新低指标衡量上涨是否扩散到更多股票。指数新高但新高股票减少，说明动能变窄。",
            "input": {"function_id": "get_new_highs_lows", "raw_data": {"value": {"new_highs": 18, "new_lows": 32, "trend": "deteriorating"}}},
            "reasoning": "1. 新低多于新高，说明内部动能偏弱。2. 趋势恶化代表扩散失败。3. 机制：新高股票减少 -> 领导力收窄 -> 指数上行更依赖少数权重。4. 结论：若L5价格仍强，这会构成趋势质量背离。",
            "output_narrative": "新低股票数量超过新高股票，且趋势继续恶化，说明市场内部动能没有扩散。即便指数表面强势，其上涨质量也在下降。"
        }
    ],
    "get_mcclellan_oscillator_nasdaq_or_nyse": [
        {
            "context": "【广度动能】McClellan Oscillator衡量上涨/下跌家数的短中期动能，适合识别广度快速恶化或修复。",
            "input": {"function_id": "get_mcclellan_oscillator_nasdaq_or_nyse", "raw_data": {"value": {"level": -68.0, "trend": "falling", "status": "negative"}}},
            "reasoning": "1. 读数为负且继续下行，说明广度动能偏弱。2. 机制：下跌家数动能占优 -> 更多股票参与下行 -> 指数抗跌性下降。3. 与价格关系：若价格仍在高位，这是短期结构背离；若价格也转弱，则是确认信号。4. 结论：应传递给L5检查趋势是否已进入脆弱阶段。",
            "output_narrative": "McClellan Oscillator为负且继续下行，说明广度动能正在恶化。若指数价格仍维持高位，这构成短期结构背离；若价格随后转弱，则会确认趋势质量恶化。"
        }
    ],
    "get_ndx_pe_and_earnings_yield": [
        {
            "context": "【百分位优先】PE必须区分当前值和真实历史分位。只有人工/Wind 或 Trendonify 等明确给出的 percentile/rank 才能支持“历史高低分位”判断；WorldPERatio 的 rolling range 只能做交叉校验，yfinance 成分股模型只提供当前值和覆盖率。",
            "input": {
                "function_id": "get_ndx_pe_and_earnings_yield",
                "raw_data": {
                    "value": {
                        "PE": 33.0,
                        "EarningsYield": 3.03,
                        "ThirdPartyChecks": [
                            {"source_name": "Trendonify", "metric": "ndx_trailing_pe", "value": 34.1, "percentile_10y": 86.0},
                            {"source_name": "WorldPERatio", "metric": "ndx_trailing_pe", "value": 32.3, "historical_percentile": None, "methodology": "rolling average / outlier notes"},
                        ],
                    },
                    "data_quality": {"source_tier": "component_model", "coverage": {"market_cap_coverage_pct": 92.5}},
                },
            },
            "reasoning": "1. yfinance 成分股模型给出的是当前PE和覆盖率，不能单独承担历史估值 regime 判断。2. Trendonify 明确给出86%的估值分位，因此可以说当前估值处于历史偏高区域。3. WorldPERatio PE与当前PE接近，说明当前值方向上可互相校验；但它没有明确 percentile，不能用 rolling range 冒充分位。4. 盈利收益率约3.03%，仍需要和10年期美债以及简式收益差距一起看安全垫。5. 结论：历史分位判断来自真实 percentile，当前值判断来自多源交叉校验。",
            "output_narrative": "NDX当前PE约33倍，Trendonify给出的历史分位为86%，支持“估值处于历史偏高位置”的判断。WorldPERatio的PE读数接近，可作为当前值校验，但它没有明确历史分位，不能替代Trendonify或人工/Wind的分位锚。"
        }
    ],
    "get_qqq_technical_indicators": [
        {
            "context": "【综合技术状态】综合技术面用于建立趋势背景，但不能替代RSI、ADX、成交量等分项确认。",
            "input": {"function_id": "get_qqq_technical_indicators", "raw_data": {"value": {"sma_position": "above_200", "macd_status": "bullish", "bb_position": "near_upper"}}},
            "reasoning": "1. 价格在200日均线上方，确认中期上升趋势。2. MACD偏多，短中期动量仍支持趋势。3. 接近布林带上轨，说明价格位置偏高，短期追涨风险上升。4. 结论：趋势有效但位置不便宜，需要RSI/ATR进一步判断是否过热。",
            "output_narrative": "QQQ价格位于200日均线上方且MACD偏多，中期趋势仍有效；但价格接近布林带上轨，说明短期位置偏高，追涨的战术风险上升。"
        }
    ],
    "get_rsi_qqq": [
        {
            "context": "【动能过热】RSI用于识别短期买盘拥挤和动能衰竭风险。强趋势中RSI可长期高位，但极端值仍需降杠杆思维。",
            "input": {"function_id": "get_rsi_qqq", "raw_data": {"value": {"level": 82.0, "status": "overbought", "divergence": "none"}}},
            "reasoning": "1. RSI 82处于明显超买区间。2. 未出现背离，说明动能尚未确认衰竭。3. 机制：极端RSI代表短期买盘拥挤 -> 均值回归风险升高，但强趋势可能继续钝化。4. 结论：这是战术过热警告，不等同于中期趋势反转。",
            "output_narrative": "RSI升至82的超买区间，提示短期买盘拥挤和均值回归风险上升。由于尚未出现明确背离，它更像战术过热警告，而不是中期趋势已经反转的证据。"
        }
    ],
    "get_atr_qqq": [
        {
            "context": "【波动尺度】ATR不是方向指标，而是风险边界指标。ATR扩张意味着同样的趋势信号需要更宽的风险容忍。",
            "input": {"function_id": "get_atr_qqq", "raw_data": {"value": {"level": 8.4, "trend": "rising", "percentile_1y": 78.0}}},
            "reasoning": "1. ATR处于偏高分位且上行，说明日内/日间波动扩大。2. 机制：波动扩张 -> 止损距离和仓位风险上升 -> 趋势持有难度增加。3. 与方向关系：ATR上升本身不看空，但若与价格转弱共振，会放大下跌。4. 结论：该指标主要用于定义L5风险边界。",
            "output_narrative": "ATR处于偏高分位并继续上行，说明QQQ波动尺度正在扩大。这不是方向性看空信号，但意味着趋势持有的风险边界变宽，价格一旦转弱，回撤幅度可能被放大。"
        }
    ],
    "get_macd_qqq": [
        {
            "context": "【动量边际】MACD用于观察中短期动量的边际变化。趋势强弱要看交叉、柱体和零轴位置。",
            "input": {"function_id": "get_macd_qqq", "raw_data": {"value": {"status": "bullish", "histogram_trend": "falling", "cross_signal": "above_signal"}}},
            "reasoning": "1. MACD仍在信号线上方，动量方向偏多。2. 柱体下降，说明多头动能边际放缓。3. 机制：方向仍多但加速度下降 -> 趋势未破坏，但追涨效率下降。4. 结论：这是强趋势后段常见信号，需要价格和均线确认是否恶化。",
            "output_narrative": "MACD仍保持多头结构，但柱体开始回落，说明趋势方向尚未破坏，动量加速度却在下降。该信号提示追涨效率变低，需要观察价格是否跌破关键均线来确认转弱。"
        }
    ],
    "get_obv_qqq": [
        {
            "context": "【量价确认】OBV判断价格趋势是否获得成交量累积确认。价格新高但OBV不确认，是量价背离。",
            "input": {"function_id": "get_obv_qqq", "raw_data": {"value": {"obv_trend": "falling", "price_trend": "rising", "divergence": "bearish"}}},
            "reasoning": "1. 价格上行但OBV下降，说明成交量累积没有确认价格强势。2. 机制：上涨缺少资金净流入确认 -> 趋势更依赖价格惯性 -> 回撤脆弱性上升。3. 结论：该指标应与L3广度共同判断趋势是否空心化。",
            "output_narrative": "OBV下行而价格仍在上涨，形成量价背离。它说明价格强势缺少成交量累积确认，趋势可能更多依赖惯性而非新增资金推动。"
        }
    ],
    "get_volume_analysis_qqq": [
        {
            "context": "【成交量结构】成交量分析区分放量突破、缩量上涨和放量下跌。量能是趋势质量的确认项。",
            "input": {"function_id": "get_volume_analysis_qqq", "raw_data": {"value": {"volume_status": "declining", "price_trend": "rising", "volume_price_relationship": "bearish_divergence"}}},
            "reasoning": "1. 价格上涨但成交量下降，属于缩量上涨。2. 机制：新增买盘不足 -> 上涨质量下降 -> 对坏消息更敏感。3. 结论：这不是趋势反转确认，但会降低L5上升趋势的质量评分。",
            "output_narrative": "QQQ呈现缩量上涨结构，说明价格继续走强但新增买盘确认不足。该信号不会单独推翻趋势，却会降低上升趋势的质量和抗冲击能力。"
        }
    ],
    "get_donchian_channels_qqq": [
        {
            "context": "【通道边界】唐奇安通道用于识别趋势突破和回撤边界。接近上轨代表强势位置，也代表追涨赔率变差。",
            "input": {"function_id": "get_donchian_channels_qqq", "raw_data": {"value": {"donchian_signal": "near_upper", "upper_breakout": False, "distance_to_lower_pct": 7.5}}},
            "reasoning": "1. 价格接近上轨，说明处于强势区间。2. 未有效突破上轨，说明尚未形成新的通道突破信号。3. 距离下轨较远，意味着一旦回撤，技术空间较大。4. 结论：这是趋势强但短期赔率下降的信号。",
            "output_narrative": "价格接近唐奇安通道上轨但尚未有效突破，显示趋势位置强势但追涨赔率下降。由于距离下轨较远，一旦回撤，技术调整空间并不小。"
        }
    ],
    "get_multi_scale_ma_position": [
        {
            "context": "【多周期趋势结构】多周期均线用于判断趋势是否在短、中、长期一致。短强长强最稳，短弱长强是早期降温。",
            "input": {"function_id": "get_multi_scale_ma_position", "raw_data": {"value": {"short_term": "above", "medium_term": "above", "long_term": "above", "alignment": "bullish"}}},
            "reasoning": "1. 短中长期均线均位于价格下方，多周期结构一致偏多。2. 机制：多周期趋势共振 -> 回撤时支撑层级较多 -> 中期趋势韧性较强。3. 风险：一致多头也可能意味着趋势成熟，需结合RSI/ATR判断是否过热。4. 结论：该指标确认趋势结构，但不单独解决过热问题。",
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
