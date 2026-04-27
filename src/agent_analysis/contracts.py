# -*- coding: utf-8 -*-
"""
NDX Agent vNext SubAgent 架构 - 数据契约模块

本模块定义了整个 SubAgent 分析流程中使用的所有数据结构。
使用 Pydantic 进行运行时数据验证和序列化。

【白话解释】
这个文件就像是一份"合同"，规定了各个 Agent 之间传递的数据必须长什么样。
比如 Layer Analyst 必须输出什么字段，Bridge Agent 必须识别哪些关系，等等。

【投资逻辑映射】
- LayerCard: 五层框架的每一层证据
- BridgeMemo: 跨层关系显式建模（核心创新）
- FinalAdjudication: "能不能涨、该不该买、何时买卖"的最终裁决
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Literal, Optional, Union

try:
    from pydantic import BaseModel, Field, field_validator
except ImportError:
    # 降级方案：如果没有 pydantic，使用 dataclass
    from dataclasses import dataclass, field
    from typing import dataclass

    # 创建一个兼容的 BaseModel 模拟
    class BaseModel:
        def __init__(self, **data):
            for key, value in data.items():
                setattr(self, key, value)

        def dict(self):
            return self.__dict__

        def json(self, **kwargs):
            import json
            return json.dumps(self.dict(), ensure_ascii=False, default=str)


# ============================================================================
# 枚举类型定义
# ============================================================================

class Layer(str, Enum):
    """
    五层分析框架层级

    【投资含义】
    L1-L3: 环境层（能不能涨）
    L4: 价值层（该不该买）
    L5: 时机层（何时买卖）
    """
    L1 = "L1"  # 宏观流动性
    L2 = "L2"  # 市场风险偏好
    L3 = "L3"  # 指数内部健康度
    L4 = "L4"  # 基本面估值
    L5 = "L5"  # 价格趋势


class Confidence(str, Enum):
    """置信度等级"""
    HIGH = "high"       # 高置信度（数据充分，逻辑清晰）
    MEDIUM = "medium"   # 中等置信度（数据有限或存在不确定性）
    LOW = "low"         # 低置信度（数据缺失或高度不确定）


class ApprovalStatus(str, Enum):
    """最终裁决状态"""
    APPROVED = "approved"                           # 完全批准
    APPROVED_WITH_RESERVATIONS = "approved_with_reservations"  # 有条件批准
    NEEDS_REVISION = "needs_revision"               # 需要修订
    REJECTED = "rejected"                           # 拒绝


class ConflictSeverity(str, Enum):
    """冲突严重程度"""
    LOW = "low"         # 轻微冲突，不影响主结论
    MEDIUM = "medium"   # 中等冲突，需要在结论中提及
    HIGH = "high"       # 严重冲突，可能推翻主结论


class PermissionType(str, Enum):
    """
    指标发言权类型

    【白话解释】
    每个指标都有自己能说明的范围。技术指标不能证明估值便宜；
    代理指标不能被当成官方真理；结构指标主要说明成分和广度。
    """
    FACT = "fact"             # 事实型：较直接的市场/经济读数
    PROXY = "proxy"           # 代理型：用来近似观察无法直接观测的状态
    COMPOSITE = "composite"   # 合成型：由多个输入组合而来
    TECHNICAL = "technical"   # 技术型：价格、动量、波动和交易节奏
    STRUCTURAL = "structural" # 结构型：广度、集中度、领导力质量


# ============================================================================
# 基础数据结构
# ============================================================================


class ObjectCanon(BaseModel):
    """
    投资对象法典 - 在分析开始前说明“我们到底在分析什么”。

    它是静态上下文，可以给 L1-L5 使用；它不包含本次运行的其他层数据，
    因此不会破坏 layer-local context isolation。
    """
    model_config = {"extra": "allow"}

    primary_object: str = Field(..., description="主要判断对象，如 NDX")
    tradable_proxy: str = Field(..., description="常用可交易代理，如 QQQ")
    equal_weight_reference: Optional[str] = Field(None, description="等权参考，如 NDXE/QEW")
    object_summary: str = Field(..., description="对象的简明定义")
    methodology_boundaries: List[str] = Field(default_factory=list, description="方法学边界和常见误读")
    analysis_boundaries: List[str] = Field(default_factory=list, description="本系统不应越权判断的边界")
    falsifiers: List[str] = Field(default_factory=list, description="会削弱对象定义或比较口径的证据")


class IndicatorCanon(BaseModel):
    """
    指标法典 - 按 function_id 描述一个指标的发言权、误读护栏和反证条件。
    """
    model_config = {"extra": "allow"}

    function_id: str = Field(..., description="指标函数 ID")
    metric_name: str = Field(..., description="指标显示名")
    layer: Layer = Field(..., description="所属层级")
    permission_type: PermissionType = Field(..., description="指标发言权类型")
    source_hint: str = Field("", description="数据来源提示")
    frequency_hint: str = Field("", description="数据频率提示")
    canonical_question: str = Field(..., description="这个指标真正回答的问题")
    interpretation_rules: List[str] = Field(default_factory=list, description="判读规则")
    misread_guards: List[str] = Field(default_factory=list, description="常见误读提醒")
    cross_validation_targets: List[str] = Field(default_factory=list, description="需要互相验证的指标")
    falsifiers: List[str] = Field(default_factory=list, description="会削弱或推翻当前解读的证据")
    core_vs_tactical_boundary: str = Field("", description="长期框架、短线执行或风险提醒的边界")
    b_prompt: str = Field("", description="少文本提示卡")


class RegimeScenarioCanon(BaseModel):
    """
    市场状态情景法典 - 保存可复用的市场状态模板。

    情景只是候选模板，不是自动结论；必须由本次 evidence refs 验证。
    """
    model_config = {"extra": "allow"}

    scenario_id: str = Field(..., description="情景 ID")
    scenario_name: str = Field(..., description="情景名称")
    indicator_combo: List[str] = Field(default_factory=list, description="需要共同出现的指标组合")
    causal_logic: str = Field(..., description="主要因果逻辑")
    main_assumption: str = Field(..., description="情景成立的核心假设")
    falsifiers: List[str] = Field(default_factory=list, description="反证条件")
    risk_triggers: List[str] = Field(default_factory=list, description="风险触发器")
    must_preserve_evidence: List[str] = Field(default_factory=list, description="必须保留的证据或冲突")


class ObjectiveFirewallSummary(BaseModel):
    """
    客观性防火墙摘要 - 强结论前的越权与证据检查。
    """
    model_config = {"extra": "allow"}

    object_clear: bool = Field(False, description="投资对象是否清楚")
    authority_clear: bool = Field(False, description="指标发言权是否被正确使用")
    timing_clear: bool = Field(False, description="数据时间和频率是否大体匹配")
    cross_layer_verified: bool = Field(False, description="是否已有跨层验证")
    strongest_falsifier: str = Field("", description="最强反证条件")
    unresolved_tensions: List[str] = Field(default_factory=list, description="仍未解决的张力")
    warnings: List[str] = Field(default_factory=list, description="需要下游保留的警示")


class CoreFact(BaseModel):
    """
    核心事实 - 每个层级的关键指标数据

    【白话解释】
    这就像分析师看到的一个"事实片段"。
    比如 "PE Ratio = 32.5，处于历史 78.5% 分位"。
    """
    metric: str = Field(..., description="指标名称，如 'PE_Ratio'")
    value: Union[float, str, int, None] = Field(..., description="指标值")
    historical_percentile: Optional[float] = Field(
        None, description="历史百分位 (0-100)，用于判断相对水平"
    )
    trend: Optional[Literal["rising", "falling", "stable", "volatile"]] = Field(
        None, description="趋势方向"
    )
    magnitude: Optional[Literal["extreme", "high", "elevated", "normal", "low"]] = Field(
        None, description="绝对水平判断"
    )
    raw_data: Optional[Dict[str, Any]] = Field(
        None, description="原始数据，供后续验证使用"
    )


class CrossLayerHook(BaseModel):
    """
    跨层挂钩点 - Layer Analyst 标记的需要其他层验证的问题

    【白话解释】
    这就像分析师写的"待办事项"。
    比如 L4 分析师写："我需要验证 L1 的流动性是否支持当前高估值"。
    """
    target_layer: Layer = Field(..., description="需要验证的目标层级")
    question: str = Field(..., description="需要回答的具体问题")
    priority: Literal["high", "medium", "low"] = Field(
        "medium", description="优先级"
    )
    rationale: Optional[str] = Field(
        None, description="为什么这个问题很重要"
    )


class IndicatorAnalysis(BaseModel):
    """
    单指标原生分析 - vNext v2 的最小认知单元

    【设计原则】
    Agent 拆分的第一性原理不是“模仿人类职位”，而是隔离上下文。
    因此每个 Layer Analyst 必须在自己的干净上下文里，把本层每一个有效指标
    直接转化为可追溯的叙事、推理链与风险含义，而不是把这些工作留给后置 adapter 脑补。
    """
    model_config = {"extra": "allow"}

    function_id: str = Field(..., description="指标函数 ID，必须来自输入数据")
    metric: str = Field(..., description="报告展示用指标名，优先使用输入中的 metric_name")
    current_reading: Optional[str] = Field(
        None,
        description="对当前读数的简明描述，包含关键数值、分位或状态"
    )
    normalized_state: Optional[str] = Field(
        None,
        description="指标状态标签，如 restrictive / risk_on / expensive / uptrend"
    )
    narrative: str = Field(..., description="面向报告正文的典范化指标解读")
    reasoning_process: str = Field(..., description="从数据到结论的细密推理过程")
    first_principles_chain: List[str] = Field(
        default_factory=list,
        description="因果链条，强调机制而非口号"
    )
    evidence_refs: List[str] = Field(
        default_factory=list,
        description="证据引用，如 ['L1.get_10y_real_rate']"
    )
    cross_layer_implications: List[str] = Field(
        default_factory=list,
        description="该指标对其他层可能产生的约束、共振或冲突"
    )
    risk_flags: List[str] = Field(default_factory=list, description="该指标暴露的局部风险")
    permission_type: Optional[PermissionType] = Field(
        None,
        description="该指标在本次分析中的发言权类型，第一阶段为软字段"
    )
    canonical_question: Optional[str] = Field(
        None,
        description="该指标真正回答的问题"
    )
    misread_guards: List[str] = Field(
        default_factory=list,
        description="本指标最容易被误读或越权使用的位置"
    )
    cross_validation_targets: List[str] = Field(
        default_factory=list,
        description="需要哪些其他指标确认或挑战该解读"
    )
    falsifiers: List[str] = Field(
        default_factory=list,
        description="哪些可观察证据会削弱或推翻当前解读"
    )
    core_vs_tactical_boundary: Optional[str] = Field(
        None,
        description="该指标主要服务长期框架、短线执行还是风险提醒"
    )
    confidence: Confidence = Field(Confidence.MEDIUM, description="该单指标解读的置信度")


class QualitySelfCheck(BaseModel):
    """
    Layer 自检 - 开放式质量检查，而不是第二个模型调用

    【设计原则】
    自检保留在同一个干净上下文窗口中，避免额外 Agent 造成成本和同步复杂度。
    """
    model_config = {"extra": "allow"}

    coverage_complete: bool = Field(False, description="是否覆盖了所有有效输入指标")
    covered_function_ids: List[str] = Field(default_factory=list, description="已覆盖的 function_id")
    missing_or_weak_indicators: List[str] = Field(
        default_factory=list,
        description="缺失、数据异常或推理较弱的指标"
    )
    weak_reasoning_points: List[str] = Field(default_factory=list, description="推理链较弱的位置")
    unresolved_internal_tensions: List[str] = Field(default_factory=list, description="本层内部尚未化解的张力")
    confidence_limitations: List[str] = Field(default_factory=list, description="置信度边界")


# ============================================================================
# Layer Card - 层级分析师产出
# ============================================================================

class LayerCard(BaseModel):
    """
    层级分析卡 - 每个 Layer Analyst 的输出

    【白话解释】
    这是每个层级分析师的"工作报告"。
    包含：我看到了什么事实、我得出了什么局部结论、
    我需要其他层帮我验证什么。

    【投资逻辑】
    每个层级只负责把自己这层看清楚，不越权做最终判断。
    最终判断留给后面的 Bridge 和 Adjudicator。
    """
    model_config = {"extra": "allow"}

    layer: Layer = Field(..., description="所属层级")
    generated_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="生成时间戳"
    )

    # 核心证据
    core_facts: List[CoreFact] = Field(
        ...,
        description="该层级的核心事实数据",
        min_length=1
    )

    # 局部结论
    local_conclusion: str = Field(
        ...,
        description="该层级的局部结论（不是最终投资建议）",
        max_length=500
    )

    # 置信度
    confidence: Confidence = Field(
        ...,
        description="对该层分析的置信度"
    )

    # 风险标记
    risk_flags: List[str] = Field(
        default_factory=list,
        description="该层发现的风险信号，如 ['high_valuation', 'narrow_breadth']"
    )

    # 跨层挂钩点（关键字段）
    cross_layer_hooks: List[CrossLayerHook] = Field(
        default_factory=list,
        description="需要其他层级验证的问题"
    )

    # vNext v2 原生指标分析
    indicator_analyses: List[IndicatorAnalysis] = Field(
        default_factory=list,
        description="本层每一个有效指标的原生叙事与推理链"
    )

    layer_synthesis: Optional[str] = Field(
        None,
        description="本层综合叙事，必须由 indicator_analyses 推导而来"
    )

    internal_conflict_analysis: Optional[str] = Field(
        None,
        description="本层内部指标之间的矛盾、共振或降噪判断"
    )

    quality_self_check: Optional[QualitySelfCheck] = Field(
        None,
        description="本层输出质量自检"
    )

    # 补充说明
    notes: Optional[str] = Field(
        None,
        description="分析师的补充说明"
    )

    def get_hook_for_layer(self, target: Layer) -> List[CrossLayerHook]:
        """获取针对特定层的挂钩点"""
        return [h for h in self.cross_layer_hooks if h.target_layer == target]


# ============================================================================
# Bridge Memo - 跨层桥接分析
# ============================================================================

class CrossLayerClaim(BaseModel):
    """
    跨层主张 - Bridge Agent 识别的跨层关系

    【白话解释】
    这就像侦探发现的"线索关联"。
    比如 "L1 流动性宽松 支撑了 L4 估值扩张"。
    """
    claim: str = Field(..., description="跨层主张描述")
    supporting_facts: List[str] = Field(
        ...,
        description="支撑该主张的事实引用，如 ['L1.liquidity_loose', 'L4.pe_expansion']"
    )
    confidence: Confidence = Field(..., description="置信度")
    mechanism: str = Field(
        ...,
        description="因果机制解释（第一性原理）",
        max_length=300
    )


class Conflict(BaseModel):
    """
    跨层冲突 - Bridge Agent 或 Contradiction Hunter 识别的冲突

    【白话解释】
    这就像侦探发现的"矛盾线索"。
    比如 "L4 说估值偏高，但 L5 说趋势强劲"，这是一个潜在冲突。
    """
    conflict_type: str = Field(
        ...,
        description="冲突类型标识，如 'L4_expensive_vs_L5_strong_trend'"
    )
    severity: ConflictSeverity = Field(..., description="严重程度")
    description: str = Field(..., description="冲突描述")
    implication: str = Field(
        ...,
        description="对投资决策的影响",
        max_length=300
    )
    involved_layers: List[Layer] = Field(
        ...,
        description="涉及的层级"
    )


class TypedConflict(BaseModel):
    """Bridge v2 typed conflict - 更细粒度的跨层冲突建模。"""
    model_config = {"extra": "allow"}

    conflict_id: str = Field(..., description="稳定冲突 ID")
    conflict_type: str = Field(..., description="冲突类型，如 valuation_discount_rate")
    severity: ConflictSeverity = Field(..., description="严重程度")
    confidence: Confidence = Field(Confidence.MEDIUM, description="冲突判断置信度")
    description: str = Field(..., description="冲突描述")
    mechanism: str = Field("", description="冲突成立的因果机制")
    implication: str = Field(..., description="对 NDX 判断的影响")
    involved_layers: List[Layer] = Field(default_factory=list, description="涉及层级")
    evidence_refs: List[str] = Field(default_factory=list, description="支撑该冲突的 evidence refs")
    falsifiers: List[str] = Field(default_factory=list, description="会削弱或推翻该冲突的证据")
    status: Literal["unresolved", "confirmed", "weakened"] = Field(
        "unresolved",
        description="当前处理状态"
    )


class ResonanceChain(BaseModel):
    """Bridge v2 resonance chain - 跨层共振链。"""
    model_config = {"extra": "allow"}

    chain_id: str = Field(..., description="稳定共振链 ID")
    description: str = Field(..., description="共振描述")
    involved_layers: List[Layer] = Field(default_factory=list, description="涉及层级")
    evidence_refs: List[str] = Field(default_factory=list, description="证据引用")
    mechanism: str = Field("", description="共振成立的机制")
    implication: str = Field("", description="对 NDX 的含义")
    confidence: Confidence = Field(Confidence.MEDIUM, description="置信度")


class TransmissionPath(BaseModel):
    """Bridge v2 transmission path - 跨层传导路径。"""
    model_config = {"extra": "allow"}

    path_id: str = Field(..., description="稳定传导路径 ID")
    source_layer: Layer = Field(..., description="传导起点层级")
    target_layer: Layer = Field(..., description="传导终点层级")
    mechanism: str = Field(..., description="传导机制")
    evidence_refs: List[str] = Field(default_factory=list, description="证据引用")
    implication: str = Field("", description="对 NDX 的含义")
    confidence: Confidence = Field(Confidence.MEDIUM, description="置信度")
    lag_hint: Optional[str] = Field(None, description="传导可能的时间滞后")


class BridgeMemo(BaseModel):
    """
    跨层桥接备忘录 - Bridge Agent 的输出

    【白话解释】
    这是 Bridge Agent 的"关联分析报告"。
    它不重新分析各层数据，而是专门看层与层之间的关系。

    【投资逻辑 - 核心创新】
    传统多 Agent 系统的问题：让总管（thesis-builder）自己脑补跨层关系。
    我们的方案：Bridge Agent 显式建模跨层关系，总管只做整合。

    这样确保跨层联系不会被"平滑掉"。
    """
    model_config = {"extra": "allow"}

    bridge_type: str = Field(
        ...,
        description="桥接类型，如 'macro_valuation', 'breadth_trend', 'constraint'"
    )
    layers_connected: List[Layer] = Field(
        ...,
        description="连接的层级",
        min_length=2
    )
    generated_at: datetime = Field(default_factory=datetime.utcnow)

    # 跨层主张（支撑关系）
    cross_layer_claims: List[CrossLayerClaim] = Field(
        default_factory=list,
        description="识别出的跨层支撑关系"
    )

    # 冲突识别（关键字段）
    conflicts: List[Conflict] = Field(
        default_factory=list,
        description="识别出的跨层冲突"
    )

    typed_conflicts: List[TypedConflict] = Field(
        default_factory=list,
        description="Bridge v2 typed conflict map"
    )

    resonance_chains: List[ResonanceChain] = Field(
        default_factory=list,
        description="Bridge v2 resonance chains"
    )

    transmission_paths: List[TransmissionPath] = Field(
        default_factory=list,
        description="Bridge v2 transmission paths"
    )

    unresolved_questions: List[str] = Field(
        default_factory=list,
        description="仍需下游保留或验证的问题"
    )

    # 对 NDX 的综合影响
    implication_for_ndx: str = Field(
        ...,
        description="对纳斯达克100的综合影响评估",
        max_length=500
    )

    # 关键不确定性
    key_uncertainties: List[str] = Field(
        default_factory=list,
        description="关键不确定性因素"
    )


class LayerSynthesisItem(BaseModel):
    """Thesis 输入用的压缩层级摘要。"""
    model_config = {"extra": "allow"}

    layer: Layer = Field(..., description="层级")
    local_conclusion: str = Field(..., description="层级局部结论")
    layer_synthesis: Optional[str] = Field(None, description="层级综合叙事")
    indicator_refs: List[str] = Field(default_factory=list, description="保留到 evidence_index 的指标引用")
    key_evidence: List[str] = Field(default_factory=list, description="压缩后的关键证据")
    risk_flags: List[str] = Field(default_factory=list, description="层级风险标记")
    internal_conflict_analysis: Optional[str] = Field(None, description="层内冲突/共振判断")
    cross_layer_hooks: List[str] = Field(default_factory=list, description="层级主动提出的跨层问题")
    confidence: Confidence = Field(Confidence.MEDIUM, description="层级置信度")


class BridgeSynthesisItem(BaseModel):
    """Thesis 输入用的压缩 Bridge 摘要。"""
    model_config = {"extra": "allow"}

    bridge_type: str = Field(..., description="桥接类型")
    layers_connected: List[Layer] = Field(default_factory=list, description="涉及层级")
    key_claims: List[str] = Field(default_factory=list, description="关键跨层支撑关系")
    key_conflicts: List[str] = Field(default_factory=list, description="关键跨层冲突")
    typed_conflicts: List[Dict[str, Any]] = Field(default_factory=list, description="Bridge v2 typed conflicts")
    resonance_chains: List[Dict[str, Any]] = Field(default_factory=list, description="Bridge v2 resonance chains")
    transmission_paths: List[Dict[str, Any]] = Field(default_factory=list, description="Bridge v2 transmission paths")
    unresolved_questions: List[str] = Field(default_factory=list, description="Bridge v2 unresolved questions")
    implication_for_ndx: str = Field("", description="对 NDX 的综合影响")
    key_uncertainties: List[str] = Field(default_factory=list, description="关键不确定性")


class SynthesisPacket(BaseModel):
    """
    综合输入包 - Thesis Builder 的上下文隔离层

    【设计原则】
    Thesis 不应再次吞入全部原始数据，也不应替 Layer 补做指标分析。
    它只消费已经过 L1-L5 与 Bridge 压缩后的 evidence index 和 synthesis items。
    """
    model_config = {"extra": "allow"}

    generated_at: datetime = Field(default_factory=datetime.utcnow)
    packet_meta: Dict[str, Any] = Field(default_factory=dict, description="输入包元数据")
    context_summary: str = Field("", description="任务与数据摘要")
    layer_summaries: List[LayerSynthesisItem] = Field(default_factory=list, description="五层压缩摘要")
    bridge_summaries: List[BridgeSynthesisItem] = Field(default_factory=list, description="Bridge 压缩摘要")
    high_severity_conflicts: List[Conflict] = Field(default_factory=list, description="必须保留的高严重度冲突")
    high_severity_typed_conflicts: List[TypedConflict] = Field(
        default_factory=list,
        description="Bridge v2 必须保留的高严重度 typed conflicts"
    )
    objective_firewall_summary: Optional[ObjectiveFirewallSummary] = Field(
        None,
        description="强结论前的客观性防火墙摘要"
    )
    evidence_index: Dict[str, Dict[str, Any]] = Field(
        default_factory=dict,
        description="可追溯证据索引，键形如 L1.get_10y_real_rate"
    )
    synthesis_guidance: List[str] = Field(
        default_factory=list,
        description="给 Thesis 的约束：只能整合，不得重做指标分析或抹平冲突"
    )


# ============================================================================
# Thesis Draft - 综合论点构建
# ============================================================================

class KeySupportChain(BaseModel):
    """
    关键支撑链 - Thesis Builder 识别的支撑主论点的证据链

    【白话解释】
    这就像律师的"证据链条"。
    比如 "L3 广度健康 → L5 趋势可持续" 是一条支撑链。
    """
    chain_description: str = Field(..., description="链条描述")
    evidence_refs: List[str] = Field(
        ...,
        description="证据引用，如 ['L3.breadth_expansion', 'L5.trend_strength']"
    )
    weight: float = Field(
        ...,
        ge=0.0, le=1.0,
        description="权重 (0-1)"
    )


class ThesisDraft(BaseModel):
    """
    论点草稿 - Thesis Builder 的输出

    【白话解释】
    这是总管的"初稿"。
    它整合 layer cards 和 bridge memos，形成主论点。

    【关键约束】
    - 不是重新分析数据，而是整合已有分析
    - 必须保留 bridge memos 中识别的冲突
    - 不能为了"通顺"而抹平张力
    """
    model_config = {"extra": "allow"}

    generated_at: datetime = Field(default_factory=datetime.utcnow)

    # 环境判断（L1-L3）
    environment_assessment: str = Field(
        ...,
        description="宏观环境评估：能不能涨？",
        max_length=300
    )

    # 价值判断（L4）
    valuation_assessment: str = Field(
        ...,
        description="估值评估：该不该买？",
        max_length=300
    )

    # 时机判断（L5）
    timing_assessment: str = Field(
        ...,
        description="时机评估：何时买卖？",
        max_length=300
    )

    # 主论点
    main_thesis: str = Field(
        ...,
        description="主论点陈述",
        max_length=500
    )

    # 支撑链
    key_support_chains: List[KeySupportChain] = Field(
        default_factory=list,
        description="支撑主论点的关键证据链"
    )

    # 保留的冲突（关键字段）
    retained_conflicts: List[Conflict] = Field(
        default_factory=list,
        description="必须保留的未解决冲突"
    )

    # 依赖前提
    dependencies: List[str] = Field(
        default_factory=list,
        description="该论点依赖哪些前提条件"
    )

    # 置信度
    overall_confidence: Confidence = Field(..., description="整体置信度")


# ============================================================================
# 审查层输出
# ============================================================================

class CritiqueItem(BaseModel):
    """批评项 - Critic 的具体批评"""
    target: str = Field(..., description="批评目标，如 'main_thesis', 'support_chain_1'")
    issue: str = Field(..., description="问题描述")
    severity: Literal["major", "minor", "suggestion"] = Field(..., description="严重程度")
    suggestion: Optional[str] = Field(None, description="改进建议")


class Critique(BaseModel):
    """
    批评报告 - Critic 的输出

    【白话解释】
    这是"挑刺专家"的报告。
    专门攻击 thesis draft 的逻辑漏洞，尤其是跨层逻辑跳跃。
    """
    generated_at: datetime = Field(default_factory=datetime.utcnow)

    # 整体评估
    overall_assessment: str = Field(..., description="整体评估", max_length=200)

    # 具体批评项
    issues: List[CritiqueItem] = Field(default_factory=list, description="具体问题")

    # 跨层逻辑审查
    cross_layer_issues: List[str] = Field(
        default_factory=list,
        description="跨层逻辑问题"
    )

    # 建议修订方向
    revision_direction: str = Field(..., description="建议修订方向", max_length=300)


class RiskBoundaryReport(BaseModel):
    """
    风险边界报告 - Risk Sentinel 的输出

    【白话解释】
    这是"风险哨兵"的巡逻报告。
    专门检查是否触及了五层框架的 13 种冲突矩阵（A-M）。
    """
    generated_at: datetime = Field(default_factory=datetime.utcnow)

    # 失效条件检查
    failure_conditions: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="触发的失效条件"
    )

    # 风险边界状态
    boundary_status: Dict[str, Literal["safe", "warning", "breached"]] = Field(
        default_factory=dict,
        description="各风险边界状态"
    )

    # 必须保留的风险警示
    must_preserve_risks: List[str] = Field(
        default_factory=list,
        description="必须在最终报告中保留的风险警示"
    )

    # 冲突矩阵检查
    conflict_matrix_check: Dict[str, bool] = Field(
        default_factory=dict,
        description="13种冲突矩阵的检查结果"
    )


class SchemaGuardReport(BaseModel):
    """
    结构校验报告 - Schema Guard 的输出

    【白话解释】
    这是"数据质检员"的报告。
    检查 JSON 结构是否正确、字段是否完整、数值引用是否一致。
    """
    generated_at: datetime = Field(default_factory=datetime.utcnow)
    passed: bool = Field(..., description="是否通过校验")

    # 结构问题
    structural_issues: List[str] = Field(default_factory=list, description="结构问题")

    # 数据一致性问题
    consistency_issues: List[str] = Field(
        default_factory=list,
        description="数据一致性问题，如引用了不存在的指标"
    )

    # 缺失字段
    missing_fields: List[str] = Field(default_factory=list, description="缺失字段")

    # 建议修复
    suggested_fixes: List[str] = Field(default_factory=list, description="建议修复")


# ============================================================================
# 修订与裁决
# ============================================================================

class AnalysisRevised(BaseModel):
    """
    修订后的分析 - Reviser 的输出

    【白话解释】
    这是"修订者"的成稿。
    吸收 critic、risk-sentinel、schema-guard 的反馈，但不抹平冲突。
    """
    generated_at: datetime = Field(default_factory=datetime.utcnow)

    # 修订说明
    revision_summary: str = Field(..., description="修订说明", max_length=500)

    # 采纳的批评
    accepted_critiques: List[str] = Field(default_factory=list, description="采纳的批评")

    # 拒绝的批评及理由
    rejected_critiques: List[Dict[str, str]] = Field(
        default_factory=list,
        description="拒绝的批评及理由"
    )

    # 修订后的论点
    revised_thesis: ThesisDraft = Field(..., description="修订后的论点")

    # 仍然保留的冲突
    remaining_conflicts: List[Conflict] = Field(
        default_factory=list,
        description="仍然保留的冲突（未解决但被接受）"
    )


class FinalAdjudication(BaseModel):
    """
    最终裁决 - Final Adjudicator 的输出

    【白话解释】
    这是"最终裁决者"的判决书。
    独立判断是否放行，明确给出最终立场和风险边界。

    【关键约束 - 核心创新】
    - 写稿的不给自己放行（独立性）
    - 不能为了"形成结论"而抹平冲突（诚实性）
    - 必须明确保留的风险边界（完整性）
    """
    generated_at: datetime = Field(default_factory=datetime.utcnow)

    # 裁决状态
    approval_status: ApprovalStatus = Field(
        ...,
        description="批准状态"
    )

    # 最终立场
    final_stance: str = Field(
        ...,
        description="对 NDX 的最终立场",
        max_length=200
    )

    # 置信度
    confidence: Confidence = Field(..., description="置信度")

    # 关键支撑链
    key_support_chains: List[KeySupportChain] = Field(
        default_factory=list,
        description="采纳的关键支撑链"
    )

    # 必须保留的风险（关键字段）
    must_preserve_risks: List[str] = Field(
        ...,
        description="必须在最终报告中保留的风险警示"
    )

    # 阻塞问题（如果未批准）
    blocking_issues: List[str] = Field(
        default_factory=list,
        description="阻止批准的具体问题"
    )

    # 裁决说明
    adjudicator_notes: str = Field(
        ...,
        description="裁决者的说明",
        max_length=500
    )

    # 可追溯引用
    evidence_refs: List[str] = Field(
        default_factory=list,
        description="支撑裁决的关键证据引用"
    )

    # Token 统计
    token_usage: Optional[Dict[str, Any]] = Field(
        default=None,
        description="LLM Token 使用统计"
    )

    model_config = {"extra": "allow"}


# ============================================================================
# Analysis Packet - 分析包（输入）
# ============================================================================

class CandidateCrossLayerLink(BaseModel):
    """候选跨层关系 - Python 预生成，供 Bridge Agent 参考"""
    link_type: str = Field(..., description="关系类型，如 'L1_L4'")
    description: str = Field(..., description="关系描述")
    trigger_condition: str = Field(..., description="触发条件")
    relevant_metrics: List[str] = Field(..., description="相关指标")


class LayerFacts(BaseModel):
    """层事实 - 从 data_json 提取的结构化事实"""
    core_signals: List[Dict[str, Any]] = Field(default_factory=list)
    state: str = "unknown"
    key_metrics: List[str] = Field(default_factory=list)
    summary: str = Field("", description="该层事实摘要")


class AnalysisPacket(BaseModel):
    """
    分析包 - Agent 分析流程的输入

    【白话解释】
    这是送给 Agent 的"资料包"。
    包含：原始数据、按层整理的事实、Python 预生成的跨层候选关系。

    【设计意图】
    - 不让 Agent 自己联网拉数据（遵守约束 #2）
    - 预生成候选跨层关系，减轻 Agent 负担
    """
    meta: Dict[str, Any] = Field(
        default_factory=dict,
        description="元数据：版本、生成时间、数据日期等"
    )

    # 原始数据（来自 data_json）
    raw_data: Dict[str, Any] = Field(
        ...,
        description="原始数据，按 L1-L5 组织"
    )

    # 按层整理的事实
    facts_by_layer: Dict[str, LayerFacts] = Field(
        default_factory=dict,
        description="按层整理的事实摘要"
    )

    # 候选跨层关系（Python 预生成）
    candidate_cross_layer_links: List[CandidateCrossLayerLink] = Field(
        default_factory=list,
        description="候选跨层关系，供 Bridge Agent 参考"
    )

    # 人工覆盖
    manual_overrides: Dict[str, Any] = Field(
        default_factory=dict,
        description="来自 manual_data.py 的覆盖数据"
    )

    # 上下文信息
    context: Dict[str, Any] = Field(
        default_factory=dict,
        description="额外上下文，如分析日期、回测标记等"
    )


# ============================================================================
# Context Brief - 上下文摘要
# ============================================================================

class ContextBrief(BaseModel):
    """
    上下文摘要 - Context Loader 的输出

    【白话解释】
    这是 Context Loader 给后续 Agent 准备的"任务说明书"。
    总结分析包的核心内容，提炼关键信息。
    """
    generated_at: datetime = Field(default_factory=datetime.utcnow)

    # 数据概况
    data_summary: str = Field(..., description="数据概况", max_length=300)

    # 各层关键信号
    layer_highlights: Dict[str, List[str]] = Field(
        default_factory=dict,
        description="各层关键信号摘要"
    )

    # 明显的跨层关联线索
    apparent_cross_layer_signals: List[str] = Field(
        default_factory=list,
        description="明显的跨层关联线索"
    )

    # 分析任务说明
    task_description: str = Field(..., description="分析任务说明")

    # 特别关注点
    special_attention: List[str] = Field(
        default_factory=list,
        description="特别关注点"
    )


# ============================================================================
# 辅助函数
# ============================================================================

def create_layer_card_from_data(
    layer: Layer,
    data: Dict[str, Any],
    conclusion: str,
    hooks: Optional[List[CrossLayerHook]] = None
) -> LayerCard:
    """
    从原始数据创建 Layer Card

    【使用场景】
    在 Layer Analyst Agent 中，Agent 读取 analysis_packet 后，
    使用此函数格式化输出。
    """
    # 提取核心事实
    facts = []
    for key, value in data.items():
        if isinstance(value, dict) and "value" in value:
            facts.append(CoreFact(
                metric=key,
                value=value.get("value"),
                historical_percentile=value.get("percentile"),
                trend=value.get("trend"),
                raw_data=value
            ))

    return LayerCard(
        layer=layer,
        core_facts=facts,
        local_conclusion=conclusion,
        confidence=Confidence.MEDIUM,  # 默认中等，Agent 可调整
        cross_layer_hooks=hooks or []
    )


def merge_bridge_memos(memos: List[BridgeMemo]) -> Dict[str, Any]:
    """
    合并多个 Bridge Memo

    【使用场景】
    Thesis Builder 读取多个 Bridge Memo 时，使用此函数合并。
    """
    all_claims = []
    all_conflicts = []
    implications = []

    for memo in memos:
        all_claims.extend(memo.cross_layer_claims)
        all_conflicts.extend(memo.conflicts)
        implications.append(memo.implication_for_ndx)

    return {
        "claims": all_claims,
        "conflicts": all_conflicts,
        "implications": implications
    }


# ============================================================================
# 版本信息
# ============================================================================

VERSION = "vNext-1.0"
SCHEMA_VERSION = "1.0"

if __name__ == "__main__":
    # 简单测试
    print(f"NDX Agent vNext Contracts Module {VERSION}")
    print(f"Schema Version: {SCHEMA_VERSION}")
    print(f"\nDefined models:")
    print(f"  - LayerCard: 层级分析卡")
    print(f"  - BridgeMemo: 跨层桥接备忘录")
    print(f"  - ThesisDraft: 论点草稿")
    print(f"  - FinalAdjudication: 最终裁决")
    print(f"\nAll models use Pydantic for validation.")
