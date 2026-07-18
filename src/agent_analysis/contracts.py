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

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Literal, Optional, Union
from uuid import uuid4

try:
    from pydantic import BaseModel, Field, field_validator, model_validator
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


class InquiryMessageType(str, Enum):
    """
    反馈环里的四类受控追问。

    【白话解释】
    任何反向追问都不能私下回拨 L1-L5；必须先变成这里的一类消息，
    再由 InquiryRouter 决定是否开一张受控任务书。
    """
    OBSERVATION_INQUIRY = "observation_inquiry"
    EVENT_CHALLENGE = "event_challenge"
    ADJUDICATION_GAP = "adjudication_gap"
    EVIDENCE_UPGRADE_REQUEST = "evidence_upgrade_request"


FeedbackStage = Literal[
    "L1",
    "L2",
    "L3",
    "L4",
    "L5",
    "bridge",
    "synthesis",
    "inquiry_router",
    "investigation",
    "integrated_synthesis",
]


class AgentBudget(BaseModel):
    """Visible budget for one controlled investigation task."""
    model_config = {"extra": "allow"}

    max_tool_calls: int = Field(0, ge=0, description="最多工具调用次数；0 表示只定义任务、不执行")
    max_minutes: int = Field(0, ge=0, description="最多运行分钟数；0 表示只定义任务、不执行")
    max_source_refs: int = Field(0, ge=0, description="最多可引入的来源引用数量")


class EvidenceSourceAuthority(BaseModel):
    """
    最小证据权威字段。

    阶段 1 先不做完整 Evidence Passport，但调查报告必须说清来源是什么级别、
    能证明什么、不能证明什么，避免外部材料散落成“看起来像正式证据”的碎片。
    """
    model_config = {"extra": "allow"}

    evidence_ref: str = Field(..., description="证据引用 ID 或 artifact 路径")
    source_ref: str = Field("", description="来源名称、URL、文件或数据源引用")
    source_tier: Literal[
        "official",
        "licensed_provider",
        "licensed_manual",
        "formal_data_source",
        "trusted_sidecar",
        "candidate_external_material",
        "proxy",
        "unknown",
    ] = Field("unknown", description="来源权威等级")
    authority_note: str = Field("", description="为什么该来源有或没有发言权")
    supports: List[str] = Field(default_factory=list, description="它支持哪些 claim")
    limitations: List[str] = Field(default_factory=list, description="它不能证明什么")


class EvidencePassport(BaseModel):
    """
    阶段 4 统一证据护照。

    【白话解释】
    每一条可以被引用的材料都要有一张身份证：它从哪里来、权威等级是什么、
    能证明什么、不能证明什么、什么情况下必须降级。
    """
    model_config = {"extra": "allow"}

    evidence_id: str = Field(..., description="统一证据 ID；数据、事件、调查、假说和最终 claim 共用同一种引用空间")
    evidence_kind: Literal["data", "event", "investigation", "hypothesis", "final_claim", "unknown"] = Field(
        "unknown",
        description="证据类型",
    )
    source_ref: str = Field("", description="来源 artifact、数据函数、URL 或任务引用")
    source_tier: Literal[
        "official",
        "licensed_provider",
        "licensed_manual",
        "formal_data_source",
        "trusted_sidecar",
        "candidate_external_material",
        "proxy",
        "derived_inference",
        "unknown",
    ] = Field("unknown", description="统一来源权威等级")
    permission_type: Optional[PermissionType] = Field(None, description="数据/指标的发言权类型")
    authority_model: Dict[str, Any] = Field(
        default_factory=dict,
        description="能支持什么、不能支持什么、需要哪些确认",
    )
    downgrade_rules: List[str] = Field(default_factory=list, description="触发降级或阻断的规则")
    data_quality: Dict[str, Any] = Field(default_factory=dict, description="数据侧 data_quality 原样摘要")
    effective_date: str = Field("", description="该证据适用的数据日期或历史可见日期")
    verified: bool = Field(False, description="是否已通过本轮权限与完整性检查")
    linked_claim_ids: List[str] = Field(default_factory=list, description="引用该证据的 claim")
    limitations: List[str] = Field(default_factory=list, description="该证据不能证明什么")


class EvidenceRegistry(BaseModel):
    """统一证据注册表。"""
    model_config = {"extra": "allow"}

    schema_version: str = Field("evidence_registry_v1", description="schema 版本")
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    effective_date: str = Field("", description="本注册表适用日期")
    passports: Dict[str, EvidencePassport] = Field(default_factory=dict, description="evidence_id -> EvidencePassport")
    source_tier_policy: Dict[str, Any] = Field(default_factory=dict, description="统一 source tier / authority / downgrade 规则")
    downgrade_summary: List[Dict[str, Any]] = Field(default_factory=list, description="本轮降级或阻断摘要")
    no_backflow_rule: str = Field(
        "EvidenceRegistry is downstream audit material; it must not rewrite or be injected into L1-L5 layer cards.",
        description="证据注册表不得反向污染 L1-L5",
    )


class ClaimLedgerEntry(BaseModel):
    """
    阶段 4 最终 claim 台账条目。

    每条重要自然语言结论必须能追问：支持证据、反证、推理步骤、失效条件和是否通过检查。
    """
    model_config = {"extra": "allow"}

    claim_id: str = Field(..., description="稳定 claim ID")
    source_stage: Literal["thesis", "final", "integrated_synthesis"] = Field("final", description="claim 来源阶段")
    claim_text: str = Field(..., min_length=1, description="自然语言结论")
    claim_type: Literal[
        "market_state",
        "valuation",
        "timing",
        "risk_boundary",
        "action_translation",
        "price_reflection",
        "integrated_explanation",
        "other",
    ] = Field("other", description="claim 类型")
    evidence_refs: List[str] = Field(default_factory=list, description="支持证据 refs")
    counter_evidence_refs: List[str] = Field(default_factory=list, description="反证 refs")
    inference_steps: List[str] = Field(default_factory=list, description="从证据到 claim 的推理步骤")
    falsification_conditions: List[str] = Field(default_factory=list, description="失效条件")
    verified: bool = Field(False, description="是否有足够证据、反证和失效条件支撑可发布")
    downgrade_reason: str = Field("", description="未通过时的降级或阻断原因")
    authority_status: Literal["verified", "downgraded", "blocked"] = Field("downgraded", description="权限检查结果")


class ClaimLedger(BaseModel):
    """Thesis / Final 自然语言结论台账。"""
    model_config = {"extra": "allow"}

    schema_version: str = Field("claim_ledger_v1", description="schema 版本")
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    effective_date: str = Field("", description="本台账适用日期")
    entries: List[ClaimLedgerEntry] = Field(default_factory=list, description="重要 claim 条目")
    publish_gate: Dict[str, Any] = Field(default_factory=dict, description="基于 claim 完整性和证据权限的发布检查")
    evidence_registry_ref: str = Field("evidence_registry.json", description="对应统一证据注册表")
    no_backflow_rule: str = Field(
        "ClaimLedger is generated after Thesis/Final and must not feed back into L1-L5.",
        description="claim 台账不得反向污染 L1-L5",
    )


class UserDecisionCondition(BaseModel):
    """One condition from the reader's personal decision discipline."""
    model_config = {"extra": "allow"}

    condition_id: str = Field(..., description="稳定条件 ID")
    side: Literal["buy", "sell", "hold", "risk"] = Field(..., description="买入、卖出、持有或风险纪律")
    label: str = Field(..., min_length=1, description="读者可见条件名称")
    discipline: str = Field(..., min_length=1, description="纪律描述")
    required_claim_types: List[Literal["valuation", "timing", "risk_boundary"]] = Field(
        default_factory=list,
        description="该纪律需要哪些 final_claim_ledger claim 类型确认",
    )
    metric_predicates: Dict[str, Any] = Field(
        default_factory=dict,
        description="基于 state_ledger 稳定状态变量的确定性谓词；缺失时才允许回退到 claim 文本启发式。",
    )


class UserDecisionProfile(BaseModel):
    """
    阶段 5：个人决策翻译档案。

    该档案只允许读者出口消费，不能进入 L1-L5、Bridge、Thesis、Critic、Risk、
    Reviser、Final 的分析 prompt。
    """
    model_config = {"extra": "allow"}

    schema_version: str = Field("user_decision_profile_v1", description="schema 版本")
    profile_id: str = Field("default_value_buy_trend_sell", description="档案 ID")
    version: str = Field("v1", description="档案版本")
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    holding_status: str = Field("unknown", description="当前持仓状态；未知时不得假装知道")
    objective: str = Field("NDX as long-term compounding base", description="长期目标")
    risk_tolerance: str = Field("unknown", description="风险承受能力；未知时只能条件式翻译")
    decision_frequency: str = Field("2-5 decisions per year", description="真实决策频率")
    buy_disciplines: List[UserDecisionCondition] = Field(default_factory=list, description="买入纪律")
    sell_disciplines: List[UserDecisionCondition] = Field(default_factory=list, description="卖出纪律")
    configuration_status: Literal["configured", "unconfigured", "invalid"] = Field(
        "unconfigured", description="读者出口纪律是否已由用户明确确认"
    )
    configuration_issues: List[str] = Field(default_factory=list, description="未配置或无效原因；不得静默吞掉")
    no_backflow_rule: str = Field(
        "UserDecisionProfile is reader-exit translation material only; it must not be injected into L1-L5, Bridge, Thesis, Critic, Risk, Reviser, Final, or hypothesis competition prompts.",
        description="个人决策档案不得反向污染上游分析",
    )


class GoldenPitChecklistItem(BaseModel):
    """阶段 5 黄金坑清单条目。"""
    model_config = {"extra": "allow"}

    condition_id: str = Field(..., description="稳定条件 ID")
    condition: str = Field(..., min_length=1, description="要检查的买入/卖出/风险条件")
    discipline_side: Literal["buy", "sell", "hold", "risk", "claim"] = Field("claim", description="条件归属")
    source_claim_ids: List[str] = Field(default_factory=list, description="来自 final_claim_ledger 的 claim IDs")
    evidence_refs: List[str] = Field(default_factory=list, description="支撑该条件判断的证据 refs")
    current_status: Literal["met", "not_met", "insufficient_evidence"] = Field(
        "insufficient_evidence",
        description="当前是否满足该条件",
    )
    falsification_conditions: List[str] = Field(default_factory=list, description="会让该条件失效的证据")
    status_method: str = Field("", description="状态判定方法，如 metric_predicates 或 claim_text_fallback")
    status_evidence: Dict[str, Any] = Field(default_factory=dict, description="状态判定所用变量、谓词或 fallback 说明")
    changed_since_last_run: Dict[str, Any] = Field(default_factory=dict, description="跨 run 变化预留字段；当前可标记为暂缓启用")


class GoldenPitChecklist(BaseModel):
    """
    阶段 5：黄金坑清单。

    这是读者出口层的跨 run 产物，只能读取 final_claim_ledger 与 UserDecisionProfile；
    不得回流 L1-L5 或任何上游推理阶段。
    """
    model_config = {"extra": "allow"}

    schema_version: str = Field("golden_pit_checklist_v1", description="schema 版本")
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    effective_date: str = Field("", description="本清单适用日期")
    decision_profile_ref: str = Field("user_decision_profile.json", description="所用个人决策档案")
    previous_checklist_ref: str = Field("", description="上一 run 的 golden_pit_checklist.json；当前跨 run 对比暂缓时为空")
    current_state: str = Field("", description="30 秒读者出口：当前状态是什么")
    changed_since_last_run_summary: List[str] = Field(default_factory=list, description="跨 run 变化预留摘要；当前暂缓启用时写明原因")
    entries: List[GoldenPitChecklistItem] = Field(default_factory=list, description="条件清单")
    no_backflow_rule: str = Field(
        "GoldenPitChecklist is generated after Final/ClaimLedger for reader-exit use only; it must not feed back into L1-L5, Bridge, Thesis, Critic, Risk, Reviser, Final, or hypothesis competition.",
        description="黄金坑清单不得反向污染主链",
    )


class InquiryMessage(BaseModel):
    """
    受控追问消息。

    它只说明“谁因为什么问题想问什么”，不携带禁止上下文里的运行时结论。
    """
    model_config = {"extra": "allow"}

    message_id: str = Field(default_factory=lambda: f"inq_{uuid4().hex[:12]}", description="消息 ID")
    message_type: InquiryMessageType = Field(..., description="四类受控消息之一")
    sender_stage: FeedbackStage = Field(..., description="发起阶段")
    target_stage: FeedbackStage = Field(..., description="目标阶段")
    trigger: str = Field(..., min_length=1, description="触发追问的观察或缺口")
    question: str = Field(..., min_length=1, description="需要回答的具体问题")
    allowed_context_refs: List[str] = Field(default_factory=list, description="允许读取的上下文或 artifact 引用")
    forbidden_context_refs: List[str] = Field(default_factory=list, description="明确禁止读取的上下文或 artifact 引用")
    effective_date: str = Field(..., min_length=1, description="该追问适用的数据日期或历史可见日期")


class AgentSpec(BaseModel):
    """
    受控调查任务书。

    它不是自由 Agent 的许可，而是一张边界清楚的任务单：能看什么、不能看什么、
    能用什么工具、预算多少、什么时候停、什么算成功。
    """
    model_config = {"extra": "allow"}

    agent_id: str = Field(default_factory=lambda: f"agent_{uuid4().hex[:12]}", description="任务 ID")
    originating_message_id: str = Field(..., description="来源 InquiryMessage ID")
    research_question: str = Field(..., min_length=1, description="本任务要回答的问题")
    allowed_context_refs: List[str] = Field(..., min_length=1, description="允许读取的上下文")
    forbidden_context_refs: List[str] = Field(..., min_length=1, description="禁止读取的上下文")
    allowed_tools: List[str] = Field(default_factory=list, description="允许工具；空列表表示阶段 1 不执行")
    budget: AgentBudget = Field(default_factory=AgentBudget, description="预算")
    stop_conditions: List[str] = Field(..., min_length=1, description="停止条件")
    success_criteria: List[str] = Field(..., min_length=1, description="成功标准")
    required_output: Dict[str, Any] = Field(..., description="必须产出的字段说明")


class InvestigationReport(BaseModel):
    """
    受控调查结果单。

    它可以被 Bridge V2 或后续综合层读取，但不能回写 L1-L5 layer card。
    """
    model_config = {"extra": "allow"}

    investigation_id: str = Field(default_factory=lambda: f"inv_{uuid4().hex[:12]}", description="调查报告 ID")
    originating_agent_id: str = Field(..., description="来源 AgentSpec ID")
    is_deterministic_stub: bool = Field(
        False,
        description="是否只是确定性占位调查；true 时不得被当作真实反证或裁决降级触发器",
    )
    finding: str = Field(..., min_length=1, description="调查发现")
    evidence_refs: List[str] = Field(default_factory=list, description="支持证据")
    counter_evidence_refs: List[str] = Field(default_factory=list, description="反证")
    claims_supported: List[str] = Field(default_factory=list, description="被支持的 claim")
    claims_challenged: List[str] = Field(default_factory=list, description="被挑战的 claim")
    cannot_establish: List[str] = Field(default_factory=list, description="仍不能证明的事项")
    confidence: Confidence = Field(Confidence.LOW, description="调查结论置信度")
    limits: List[str] = Field(default_factory=list, description="限制和口径边界")
    source_authority: List[EvidenceSourceAuthority] = Field(
        default_factory=list,
        description="最小来源权威字段；阶段 4 可升级为 Evidence Passport",
    )
    effective_date: str = Field(..., min_length=1, description="调查适用的数据日期或历史可见日期")


class InquiryRouterDecision(BaseModel):
    """InquiryRouter 对单条消息的接单或拒单记录。"""
    model_config = {"extra": "allow"}

    message_id: str = Field(..., description="被处理的消息 ID")
    message_type: InquiryMessageType = Field(..., description="消息类型")
    status: Literal["accepted", "rejected"] = Field(..., description="接单或拒单")
    agent_spec: Optional[AgentSpec] = Field(None, description="接单时生成的任务书")
    rejection_reason: str = Field("", description="拒单原因；拒单时必填")
    trigger: str = Field("", description="原始触发来源，便于审计")


class InquiryRouterOutput(BaseModel):
    """InquiryRouter 的批量输出。"""
    model_config = {"extra": "allow"}

    schema_version: str = Field("inquiry_router_output_v1", description="schema 版本")
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    input_messages: List[InquiryMessage] = Field(default_factory=list, description="路由器收到的原始消息")
    decisions: List[InquiryRouterDecision] = Field(default_factory=list, description="逐条消息处理结果")
    agent_specs: List[AgentSpec] = Field(default_factory=list, description="生成的任务书")
    rejected_messages: List[InquiryRouterDecision] = Field(default_factory=list, description="被拒绝但可审计的消息")
    router_policy: Dict[str, Any] = Field(default_factory=dict, description="路由规则摘要")


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
        default_factory=lambda: datetime.now(timezone.utc),
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
    event_refs: List[str] = Field(
        default_factory=list,
        description="可选事件引用；只能作为催化剂、背景或观察，不能替代 evidence_refs"
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
    event_refs: List[str] = Field(default_factory=list, description="可选事件 refs，仅作解释/触发/观察背景")
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
    event_refs: List[str] = Field(default_factory=list, description="可选事件 refs，仅作解释/触发/观察背景")
    confirming_indicators: List[str] = Field(default_factory=list, description="确认该共振链的指标或观察点")
    mechanism: str = Field("", description="共振成立的机制")
    implication: str = Field("", description="对 NDX 的含义")
    falsifiers: List[str] = Field(default_factory=list, description="会削弱或推翻该共振链的反证条件")
    confidence: Confidence = Field(Confidence.MEDIUM, description="置信度")


class TransmissionPath(BaseModel):
    """Bridge v2 transmission path - 跨层传导路径。"""
    model_config = {"extra": "allow"}

    path_id: str = Field(..., description="稳定传导路径 ID")
    source_layer: Layer = Field(..., description="传导起点层级")
    target_layer: Layer = Field(..., description="传导终点层级")
    mechanism: str = Field(..., description="传导机制")
    evidence_refs: List[str] = Field(default_factory=list, description="证据引用")
    event_refs: List[str] = Field(default_factory=list, description="可选事件 refs，仅作解释/触发/观察背景")
    implication: str = Field("", description="对 NDX 的含义")
    confidence: Confidence = Field(Confidence.MEDIUM, description="置信度")
    lag_hint: Optional[str] = Field(None, description="传导可能的时间滞后")


class ContradictionTransformationSignal(BaseModel):
    """A concrete signal that can change the contradiction map."""
    model_config = {"extra": "allow"}

    signal: str = Field(..., description="可观察的矛盾转化信号")
    direction: str = Field("", description="该信号会让矛盾向哪个方向转化")
    implication: str = Field("", description="对 NDX 判断或行动的含义")
    evidence_refs: List[str] = Field(default_factory=list, description="支撑或观察该信号的证据")
    event_refs: List[str] = Field(default_factory=list, description="可选事件 refs，仅作触发/背景")


class PriceReflectionAssessment(BaseModel):
    """Bridge assessment of whether a conflict is already reflected in price."""
    model_config = {"extra": "allow"}

    category: str = Field(
        "other",
        description="价格反映类别：credit / rates / valuation / technical_panic / liquidity / other",
    )
    target: str = Field(..., description="被评估的风险、冲突或叙事")
    reflected_state: str = Field(
        ...,
        description="价格反映程度，如 not_reflected / partially_reflected / largely_reflected / over_reflected / unclear",
    )
    rationale: str = Field("", description="为什么这样判断")
    evidence_refs: List[str] = Field(default_factory=list, description="支撑该定价判断的证据")
    counterevidence: List[str] = Field(default_factory=list, description="反证或削弱该定价判断的观察")
    counterevidence_refs: List[str] = Field(default_factory=list, description="反证引用")
    action_implication: str = Field("", description="对核心仓、战术仓或等待者动作的影响")
    missing_evidence: List[str] = Field(default_factory=list, description="仍缺少的证据")


def _coerce_llm_string_to_list(value: Any) -> Any:
    """LLM 常把单条列表字段写成裸字符串；这里只做形状纠正，不改变语义。"""
    if isinstance(value, str):
        text = value.strip()
        return [text] if text else []
    return value


class CompetingHypothesis(BaseModel):
    """
    最小竞争假说。

    一个假说只有在同时写清支持、反证、诊断力证据、解释不了什么和失效条件后，
    才能进入 Thesis 前的裁决比较。
    """
    model_config = {"extra": "allow"}

    hypothesis_id: str = Field(default_factory=lambda: f"hyp_{uuid4().hex[:12]}", description="稳定假说 ID")
    hypothesis_text: str = Field(..., min_length=1, description="假说文本")
    source: Literal["bridge_v2", "counter_thesis", "investigation", "deterministic_fallback"] = Field(
        "deterministic_fallback",
        description="假说来源",
    )
    support_evidence_refs: List[str] = Field(default_factory=list, description="支持证据")
    counter_evidence_refs: List[str] = Field(default_factory=list, description="反证")
    diagnostic_evidence_refs: List[str] = Field(default_factory=list, description="最能区分本假说和对立假说的证据")
    cannot_explain: List[str] = Field(default_factory=list, description="该假说解释不了或解释力弱的现象")
    falsification_conditions: List[str] = Field(default_factory=list, description="会让该假说失效的条件")
    confidence: Confidence = Field(Confidence.LOW, description="当前置信度")
    status: Literal["candidate", "leading", "downgraded", "split", "kept_unresolved"] = Field(
        "candidate",
        description="裁决状态",
    )
    adjudication_reason: str = Field("", description="为什么是当前状态")
    source_refs: List[str] = Field(default_factory=list, description="来源 artifact 或字段引用")

    @model_validator(mode="before")
    @classmethod
    def _tolerate_llm_field_variants(cls, data: Any) -> Any:
        """吸收已观测到的 LLM 字段变体，避免高质量反方内容因字段名被整体丢弃。"""
        if not isinstance(data, dict):
            return data
        aliases = {
            "what_it_cannot_explain": "cannot_explain",
            "explains_poorly": "cannot_explain",
            "failure_conditions": "falsification_conditions",
            "falsifiers": "falsification_conditions",
        }
        for alias, canonical in aliases.items():
            if alias in data and not data.get(canonical):
                data[canonical] = data.pop(alias)
        return data

    @field_validator(
        "support_evidence_refs",
        "counter_evidence_refs",
        "diagnostic_evidence_refs",
        "cannot_explain",
        "falsification_conditions",
        "source_refs",
        mode="before",
    )
    @classmethod
    def _coerce_single_string_fields(cls, value: Any) -> Any:
        return _coerce_llm_string_to_list(value)


class HypothesisResponse(BaseModel):
    """Thesis 对一个候选竞争假说的显式裁决。"""
    model_config = {"extra": "allow"}

    hypothesis_id: str = Field(..., min_length=1, description="被回应的竞争假说 ID")
    verdict: Literal["accept_and_revise", "absorb_partially", "reject"] = Field(
        ...,
        description="接受并修正、部分吸收或驳回",
    )
    reasoning: str = Field(..., min_length=1, description="回应理由")
    evidence_refs: List[str] = Field(default_factory=list, description="回应所引用的正式证据")

    @field_validator("evidence_refs", mode="before")
    @classmethod
    def _coerce_single_string_evidence_ref(cls, value: Any) -> Any:
        return _coerce_llm_string_to_list(value)


class CounterThesisDraft(BaseModel):
    """第一次反方构建产物；不得读取 Thesis。"""
    model_config = {"extra": "allow"}

    schema_version: str = Field("counter_thesis_v1", description="schema 版本")
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    independence_boundary: str = Field(
        "Counter-Thesis is generated before Thesis and may read only SynthesisPacket / Bridge V2, not Thesis.",
        description="反方独立性边界",
    )
    input_refs: List[str] = Field(default_factory=list, description="允许输入")
    forbidden_context_refs: List[str] = Field(default_factory=list, description="禁止输入")
    hypotheses: List[CompetingHypothesis] = Field(default_factory=list, description="反方假说")
    principal_counterargument: str = Field("", description="最强反方论点")
    cannot_establish: List[str] = Field(default_factory=list, description="反方仍不能证明的事项")
    prompt_input_audit: Dict[str, Any] = Field(default_factory=dict, description="输入审计")

    @field_validator("input_refs", "forbidden_context_refs", "cannot_establish", mode="before")
    @classmethod
    def _coerce_single_string_fields(cls, value: Any) -> Any:
        return _coerce_llm_string_to_list(value)

    @field_validator("principal_counterargument", mode="before")
    @classmethod
    def _coerce_dict_counterargument(cls, value: Any) -> Any:
        """LLM 偶尔把最强反方论点写成 {'summary': ...} 结构；取其文本，不丢内容。"""
        if isinstance(value, dict):
            summary = value.get("summary")
            if isinstance(summary, str) and summary.strip():
                return summary
            parts = [part for part in value.values() if isinstance(part, str) and part.strip()]
            return " ".join(parts)
        return value


class AdjudicationChangeRecord(BaseModel):
    """非单调重判记录：新证据改变、分叉或降级判断时必须保留旧版本。"""
    model_config = {"extra": "allow"}

    version_id: str = Field(..., description="版本记录 ID")
    previous_hypothesis_id: str = Field("", description="旧主导或候选假说")
    new_hypothesis_id: str = Field("", description="新主导、分叉或被保留假说")
    trigger_evidence_refs: List[str] = Field(default_factory=list, description="触发改判/降级/分叉的证据")
    change_type: Literal["initial", "no_change", "downgrade", "split", "reversal", "kept_unresolved"] = Field(
        "initial",
        description="变化类型",
    )
    old_status: str = Field("", description="旧状态")
    new_status: str = Field("", description="新状态")
    reason: str = Field("", description="改判、降级或保留争议的原因")
    effective_date: str = Field("", description="适用日期")


class HypothesisCompetition(BaseModel):
    """Thesis 前的最小竞争裁决卷宗。"""
    model_config = {"extra": "allow"}

    schema_version: str = Field("hypothesis_competition_v1", description="schema 版本")
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    input_refs: List[str] = Field(default_factory=list, description="允许输入")
    forbidden_context_refs: List[str] = Field(default_factory=list, description="禁止输入")
    hypotheses: List[CompetingHypothesis] = Field(default_factory=list, description="竞争假说")
    leading_hypothesis_id: str = Field("", description="当前领先假说；不足以裁决时为空")
    retained_disputes: List[str] = Field(default_factory=list, description="必须保留的争议")
    downgrade_or_split_events: List[AdjudicationChangeRecord] = Field(
        default_factory=list,
        description="由强反证触发的降级、分叉或争议保留记录",
    )
    insufficient_evidence_reason: str = Field("", description="不足以形成两个假说或无法裁决时说明原因")
    fallback_warnings: List[str] = Field(default_factory=list, description="principal_contradiction / price_reflection 兜底痕迹")
    principal_contradiction_quality: str = Field("", description="native / fallback / missing")
    price_reflection_quality: str = Field("", description="native / fallback / missing")
    adjudication_notes: List[str] = Field(default_factory=list, description="裁决说明")


class AdjudicationHistory(BaseModel):
    """本轮竞争裁决版本历史。"""
    model_config = {"extra": "allow"}

    schema_version: str = Field("adjudication_history_v1", description="schema 版本")
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    effective_date: str = Field("", description="适用日期")
    records: List[AdjudicationChangeRecord] = Field(default_factory=list, description="版本记录")
    current_hypothesis_ids: List[str] = Field(default_factory=list, description="当前仍有效的假说 ID")


class PrincipalContradiction(BaseModel):
    """The main contradiction that should dominate synthesis."""
    model_config = {"extra": "allow"}

    contradiction_id: str = Field("", description="稳定 ID；优先引用 typed_conflicts[].conflict_id")
    summary: str = Field("", description="主要矛盾的白话摘要")
    why_principal: str = Field("", description="为什么它是当前主导矛盾")
    dominant_side: str = Field("", description="当前占支配地位的一面")
    secondary_side: str = Field("", description="被压制但不能忽略的一面")
    price_reflection: str = Field("", description="风险/叙事是否已被价格反映")
    action_implication: str = Field("", description="对核心仓、战术仓或等待者的行动含义")
    conflict_refs: List[str] = Field(default_factory=list, description="关联 typed_conflicts/conflicts ID")
    evidence_refs: List[str] = Field(default_factory=list, description="支撑主要矛盾判断的证据")
    transformation_signals: List[ContradictionTransformationSignal] = Field(
        default_factory=list,
        description="会让主要矛盾或其主导方面转化的信号",
    )
    unresolved_questions: List[str] = Field(default_factory=list, description="必须留给 Thesis/Risk/Final 的未解问题")


class SecondaryContradiction(BaseModel):
    """A non-principal contradiction that still constrains the final action."""
    model_config = {"extra": "allow"}

    contradiction_id: str = Field("", description="稳定 ID")
    summary: str = Field("", description="次要矛盾摘要")
    why_secondary: str = Field("", description="为什么当前不是主要矛盾")
    action_constraint: str = Field("", description="它对行动力度、节奏或置信度的约束")
    evidence_refs: List[str] = Field(default_factory=list, description="支撑该次要矛盾的证据")


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
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

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

    principal_contradiction: Optional[PrincipalContradiction] = Field(
        None,
        description="Bridge v3 矛盾地图：当前主导 NDX 收益/风险判断的主要矛盾",
    )

    secondary_contradictions: List[SecondaryContradiction] = Field(
        default_factory=list,
        description="Bridge v3 矛盾地图：必须保留但不是当前主导项的次要矛盾",
    )

    price_reflection_map: List[PriceReflectionAssessment] = Field(
        default_factory=list,
        description="Bridge v3：风险、冲突或叙事是否已经进入价格",
    )

    contradiction_transformation_signals: List[ContradictionTransformationSignal] = Field(
        default_factory=list,
        description="Bridge v3：会改变主要/次要矛盾关系的可观察信号",
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

    event_refs: List[str] = Field(
        default_factory=list,
        description="Bridge 选择保留的事件引用；与 evidence_refs 分离，只能作为背景或催化剂"
    )

    normalization_notes: List[str] = Field(
        default_factory=list,
        description="代码归一化或兜底补全记录；用于区分模型原生判断和兼容层补齐字段"
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
    principal_contradiction: Optional[Dict[str, Any]] = Field(None, description="Bridge v3 principal contradiction")
    secondary_contradictions: List[Dict[str, Any]] = Field(default_factory=list, description="Bridge v3 secondary contradictions")
    price_reflection_map: List[Dict[str, Any]] = Field(default_factory=list, description="Bridge v3 price reflection map")
    contradiction_transformation_signals: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Bridge v3 contradiction transformation signals",
    )
    unresolved_questions: List[str] = Field(default_factory=list, description="Bridge v2 unresolved questions")
    event_refs: List[str] = Field(default_factory=list, description="Bridge 使用的事件引用")
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

    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    packet_meta: Dict[str, Any] = Field(default_factory=dict, description="输入包元数据")
    context_summary: str = Field("", description="任务与数据摘要")
    layer_summaries: List[LayerSynthesisItem] = Field(default_factory=list, description="五层压缩摘要")
    bridge_summaries: List[BridgeSynthesisItem] = Field(default_factory=list, description="Bridge 压缩摘要")
    high_severity_conflicts: List[Conflict] = Field(default_factory=list, description="必须保留的高严重度冲突")
    high_severity_typed_conflicts: List[TypedConflict] = Field(
        default_factory=list,
        description="Bridge v2 必须保留的高严重度 typed conflicts"
    )
    principal_contradictions: List[PrincipalContradiction] = Field(
        default_factory=list,
        description="Bridge v3 主要矛盾候选；Thesis 必须显式消费并选择/解释主导项",
    )
    competing_hypotheses: List[CompetingHypothesis] = Field(
        default_factory=list,
        description="阶段 3：Thesis 前必须看到的竞争假说，至少包含主线与反方候选",
    )
    hypothesis_competition_summary: Dict[str, Any] = Field(
        default_factory=dict,
        description="阶段 3：竞争裁决摘要，完整卷宗另存 hypothesis_competition.json",
    )
    adjudication_history: List[AdjudicationChangeRecord] = Field(
        default_factory=list,
        description="阶段 3：非单调重判记录摘要",
    )
    counter_thesis_boundary: Dict[str, Any] = Field(
        default_factory=dict,
        description="阶段 3：Counter-Thesis 独立性边界和输入审计摘要",
    )
    objective_firewall_summary: Optional[ObjectiveFirewallSummary] = Field(
        None,
        description="强结论前的客观性防火墙摘要"
    )
    evidence_index: Dict[str, Dict[str, Any]] = Field(
        default_factory=dict,
        description="可追溯证据索引，键形如 L1.get_10y_real_rate"
    )
    event_index: Dict[str, Dict[str, Any]] = Field(
        default_factory=dict,
        description="可选事件索引，键形如 event:<dedupe_id>；不得作为数值证据"
    )
    evidence_registry_summary: Dict[str, Any] = Field(
        default_factory=dict,
        description="阶段 4：统一 Evidence Passport 注册表摘要，完整产物另存 evidence_registry.json",
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
    event_refs: List[str] = Field(
        default_factory=list,
        description="可选事件引用；只能说明催化剂/背景/观察，不能替代 evidence_refs"
    )
    weight: float = Field(
        ...,
        ge=0.0, le=1.0,
        description="权重 (0-1)"
    )


class TimeHorizonView(BaseModel):
    """Decision Semantics: one conclusion per investment horizon."""
    model_config = {"extra": "allow"}

    horizon: str = Field(..., description="时间尺度，如 same_day_or_days / one_to_three_months / six_to_twelve_months")
    view: str = Field(..., description="该时间尺度下的判断")
    action_implication: str = Field("", description="该时间尺度对应的行动含义")
    evidence_refs: List[str] = Field(default_factory=list, description="支撑该时间尺度判断的证据")
    invalidation_conditions: List[str] = Field(default_factory=list, description="会推翻该时间尺度判断的条件")


class PortfolioAction(BaseModel):
    """Decision Semantics: action split by investor bucket, not a single stance."""
    model_config = {"extra": "allow"}

    bucket: str = Field(..., description="动作桶，如 core_position / tactical_position / waiting_cash")
    action: str = Field(..., description="建议动作或等待方式")
    rationale: str = Field("", description="为什么这样行动")
    conditions: List[str] = Field(default_factory=list, description="执行或升级/降级条件")
    evidence_refs: List[str] = Field(default_factory=list, description="支撑该动作的证据")


class ReaderFinal(BaseModel):
    """Reader-facing final answer, separated from internal quality gate notes."""
    model_config = {"extra": "allow"}

    one_liner: str = Field("", description="给普通读者的一句话结论")
    three_reasons: List[str] = Field(default_factory=list, description="三条最重要理由")
    time_horizon_summary: List[TimeHorizonView] = Field(default_factory=list, description="分时间尺度判断")
    action_summary: List[PortfolioAction] = Field(default_factory=list, description="核心仓/战术仓/等待者动作")
    invalidation_summary: List[str] = Field(default_factory=list, description="最重要失效条件")
    evidence_refs: List[str] = Field(default_factory=list, description="读者结论引用的关键证据")


class QualityGate(BaseModel):
    """Internal publishing gate. This is audit material, not reader copy."""
    model_config = {"extra": "allow"}

    approval_status: ApprovalStatus = Field(..., description="内部质量闸门状态")
    blocking_issues: List[str] = Field(default_factory=list, description="阻塞发布的问题")
    evidence_ref_issues: List[str] = Field(default_factory=list, description="证据引用问题")
    preserved_risks_check: str = Field("", description="必须保留风险是否完整")
    notes: str = Field("", description="内部裁决说明，不应进入 brief 首屏")


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

    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

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

    hypothesis_responses: List[HypothesisResponse] = Field(
        default_factory=list,
        description="对每个 candidate 竞争假说的逐一回应",
    )

    # 依赖前提
    dependencies: List[str] = Field(
        default_factory=list,
        description="该论点依赖哪些前提条件"
    )

    # Decision Semantics v1：定价与赔率判断面
    state_diagnosis: str = Field(
        "",
        description="当前市场状态诊断，不等同于最终买卖立场",
        max_length=600,
    )
    priced_narrative: str = Field(
        "",
        description="当前价格正在定价什么、哪些坏消息可能已反映、哪些仍未反映",
        max_length=800,
    )
    payoff_assessment: str = Field(
        "",
        description="风险补偿/赔率判断，如高风险高赔率、高风险低赔率等",
        max_length=600,
    )
    time_horizon_views: List[TimeHorizonView] = Field(
        default_factory=list,
        description="短期、中期、长期分时间尺度判断"
    )
    portfolio_actions: List[PortfolioAction] = Field(
        default_factory=list,
        description="核心仓、战术仓、等待者的动作含义"
    )
    confirmation_cost: str = Field(
        "",
        description="等待更多确认降低什么风险、付出什么机会成本",
        max_length=600,
    )
    invalidation_conditions: List[str] = Field(
        default_factory=list,
        description="哪些可观察证据会推翻当前定价/赔率判断"
    )
    reader_conclusion: ReaderFinal = Field(
        default_factory=ReaderFinal,
        description="面向读者的一句话结论、理由、动作和失效条件"
    )

    # Mao thought main-chain semantics: contradiction map consumed from Bridge.
    principal_contradiction: Optional[PrincipalContradiction] = Field(
        None,
        description="当前主导投资判断的主要矛盾；必须说明价格反映和行动含义",
    )
    secondary_contradictions: List[SecondaryContradiction] = Field(
        default_factory=list,
        description="仍需保留的次要矛盾及其行动约束",
    )
    price_reflection_map: List[PriceReflectionAssessment] = Field(
        default_factory=list,
        description="风险、冲突或叙事进入价格的程度",
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
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

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
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

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

    # Decision Semantics v1：双向风险与确认成本
    opportunity_costs: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="过度谨慎、踏空或错过高赔率窗口的风险"
    )
    confirmation_costs: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="等待更多确认降低的风险与付出的机会成本"
    )
    false_safety_risks: List[str] = Field(
        default_factory=list,
        description="风险看似下降但赔率也已变薄的假安全风险"
    )


class SchemaGuardReport(BaseModel):
    """
    结构校验报告 - Schema Guard 的输出

    【白话解释】
    这是"数据质检员"的报告。
    检查 JSON 结构是否正确、字段是否完整、数值引用是否一致。
    """
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
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

    quality_status: str = Field(
        "passed",
        description="passed / review_required；供 run_summary 和 Run Review 标记非数据类发布质量"
    )


# ============================================================================
# Governance Input Packet - 治理阶段窄输入
# ============================================================================

class GovernanceInputPacket(BaseModel):
    """
    治理阶段窄输入 — 压缩 Critic / Risk / Reviser / Final 的输入，降低 token 膨胀。

    只包含治理阶段需要的关键信号：高严重度冲突、客观性防火墙、必须保留的风险、
    Schema Guard 摘要、关键证据引用和已知数据缺口。

    不会包含完整 layer_cards 或 bridge_memos。
    """
    model_config = {"extra": "allow"}

    # ── Thesis 核心 ──
    thesis_main: str = Field("", description="主论点")
    thesis_environment: str = Field("", description="环境评估")
    thesis_valuation: str = Field("", description="估值评估")
    thesis_timing: str = Field("", description="时机评估")
    thesis_confidence: str = Field("medium", description="整体置信度")
    thesis_dependencies: List[str] = Field(default_factory=list, description="依赖前提")
    thesis_key_support_chains: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Thesis 主论点的关键支撑链，保留 evidence_refs 以供治理阶段核验"
    )
    thesis_hypothesis_responses: List[HypothesisResponse] = Field(
        default_factory=list,
        description="Thesis 对 candidate 竞争假说的逐一回应，治理阶段不得静默丢失",
    )
    retained_conflict_types: List[str] = Field(default_factory=list, description="已保留的冲突类型名")
    thesis_state_diagnosis: str = Field("", description="Decision Thesis 状态诊断")
    thesis_priced_narrative: str = Field("", description="Decision Thesis 价格隐含叙事")
    thesis_payoff_assessment: str = Field("", description="Decision Thesis 赔率判断")
    thesis_time_horizon_views: List[Dict[str, Any]] = Field(default_factory=list, description="分时间尺度判断")
    thesis_portfolio_actions: List[Dict[str, Any]] = Field(default_factory=list, description="核心/战术/等待动作")
    thesis_confirmation_cost: str = Field("", description="等待确认的成本")
    thesis_invalidation_conditions: List[str] = Field(default_factory=list, description="失效条件")
    thesis_reader_conclusion: Dict[str, Any] = Field(default_factory=dict, description="读者结论草稿")
    thesis_principal_contradiction: Optional[Dict[str, Any]] = Field(
        None,
        description="Thesis 选定的主要矛盾",
    )
    thesis_secondary_contradictions: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Thesis 保留的次要矛盾",
    )
    thesis_price_reflection_map: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Thesis 消费/修正后的价格反映地图",
    )

    # ── 必须不丢失的高严重度冲突 ──
    high_severity_typed_conflicts: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Bridge v2 高严重度 typed conflicts（必须保留）"
    )
    principal_contradictions: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Bridge v3 主要矛盾候选，治理阶段必须检查是否被保留",
    )

    # ── 客观性防火墙 ──
    objective_firewall_summary: Optional[Dict[str, Any]] = Field(
        None, description="客观性防火墙摘要"
    )

    # ── Schema Guard 摘要 ──
    schema_passed: bool = Field(True, description="Schema Guard 是否通过")
    schema_structural_issues: List[str] = Field(default_factory=list, description="结构问题")
    schema_consistency_issues: List[str] = Field(default_factory=list, description="一致性问题")
    schema_missing_fields: List[str] = Field(default_factory=list, description="缺失字段")

    # ── Risk Sentinel 必须保留的风险（reviser / final） ──
    must_preserve_risks: List[str] = Field(default_factory=list, description="必须保留的风险警示")
    opportunity_costs: List[Dict[str, Any]] = Field(default_factory=list, description="Risk Sentinel 识别的踏空/机会成本")
    confirmation_costs: List[Dict[str, Any]] = Field(default_factory=list, description="Risk Sentinel 识别的确认成本")
    false_safety_risks: List[str] = Field(default_factory=list, description="Risk Sentinel 识别的假安全风险")

    # ── 关键证据引用 ──
    key_evidence_refs: Dict[str, Dict[str, Any]] = Field(
        default_factory=dict,
        description="与高严重度冲突和 Thesis 支撑链相关的 evidence_index 子集"
    )

    key_event_refs: Dict[str, Dict[str, Any]] = Field(
        default_factory=dict,
        description="与高严重度冲突和 Thesis 支撑链相关的 event_index 子集；不能作为数值证据"
    )

    evidence_registry_summary: Dict[str, Any] = Field(
        default_factory=dict,
        description="阶段 4：统一证据注册摘要，用于治理阶段检查证据权限和降级规则",
    )

    # ── 已知数据缺口（尤其是 L3 广度缺失） ──
    known_data_gaps: List[str] = Field(default_factory=list, description="已知数据缺口")

    # ── Bridge 未解决问题 ──
    unresolved_questions: List[str] = Field(default_factory=list, description="Bridge v2 未解决问题")

    # ── Synthesis 指导 ──
    synthesis_guidance: List[str] = Field(default_factory=list, description="给下游的约束指令")

    # ── Critique 摘要（reviser / final） ──
    critique_overall: Optional[str] = Field(None, description="Critic 整体评估")
    critique_cross_layer_issues: List[str] = Field(default_factory=list, description="Critic 跨层逻辑问题")

    # ── 修订摘要（final） ──
    revision_summary: Optional[str] = Field(None, description="Reviser 修订说明")


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
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

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
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

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

    reasoned_verdict: str = Field(
        "",
        description="给读者看的总分总判决正文",
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

    # Decision Semantics v1：内部质量闸门与读者结论分离
    quality_gate: Optional[QualityGate] = Field(
        default=None,
        description="内部质量闸门；供审计区展示，不进入 brief 首屏"
    )
    reader_final: ReaderFinal = Field(
        default_factory=ReaderFinal,
        description="读者可见最终结论；brief 首屏优先消费"
    )
    state_diagnosis: str = Field("", description="最终状态诊断")
    priced_narrative: str = Field("", description="最终价格隐含叙事")
    payoff_assessment: str = Field("", description="最终赔率判断")
    time_horizon_views: List[TimeHorizonView] = Field(default_factory=list, description="最终分时间尺度判断")
    portfolio_actions: List[PortfolioAction] = Field(default_factory=list, description="最终组合动作含义")
    confirmation_cost: str = Field("", description="最终确认成本")
    invalidation_conditions: List[str] = Field(default_factory=list, description="最终失效条件")
    principal_contradiction: Optional[PrincipalContradiction] = Field(
        None,
        description="最终保留给读者的主要矛盾；用于说明当前真正决定收益风险的关键张力",
    )
    secondary_contradictions: List[SecondaryContradiction] = Field(
        default_factory=list,
        description="最终保留的次要矛盾",
    )
    price_reflection_map: List[PriceReflectionAssessment] = Field(
        default_factory=list,
        description="最终价格反映判断地图",
    )
    claim_ledger: Optional[ClaimLedger] = Field(
        default=None,
        description="阶段 4：最终自然语言结论的 claim-level 台账；完整产物另存 final_claim_ledger.json",
    )

    @field_validator("reasoned_verdict")
    @classmethod
    def _validate_reasoned_verdict_length(cls, value: str) -> str:
        text = str(value or "").strip()
        if text and not 300 <= len(text) <= 1300:
            raise ValueError("reasoned_verdict must be empty or contain 300-1300 characters")
        return text

    @model_validator(mode="after")
    def _note_missing_reasoned_verdict(self) -> "FinalAdjudication":
        if self.reasoned_verdict:
            return self
        if self.quality_gate is None:
            self.quality_gate = QualityGate(
                approval_status=self.approval_status,
                blocking_issues=list(self.blocking_issues),
                notes="判决正文缺失",
            )
        elif "判决正文缺失" not in self.quality_gate.notes:
            self.quality_gate.notes = "；".join(
                item for item in (self.quality_gate.notes.strip(), "判决正文缺失") if item
            )
        return self

    model_config = {"extra": "allow"}


# ============================================================================
# Run Review - 实践复盘闭环
# ============================================================================

class RunReviewFinding(BaseModel):
    """One post-run finding attributed to the stage that should learn from it."""
    model_config = {"extra": "allow"}

    category: Literal["data", "feedback", "competition", "evidence", "bridge", "thesis", "risk", "final", "expression"] = Field(
        ...,
        description="问题归因层：数据、反馈环、竞争裁决、Bridge、Thesis、Risk、Final 或表达层",
    )
    severity: Literal["pass", "observe", "fail"] = Field(..., description="复盘结论")
    finding: str = Field(..., description="具体发现")
    artifact_refs: List[str] = Field(default_factory=list, description="相关 artifact 路径或字段")
    evidence_refs: List[str] = Field(default_factory=list, description="相关 evidence refs")
    recommended_rule_update: str = Field("", description="下一轮应沉淀的规则或检查")


class RunReviewReport(BaseModel):
    """Post-run learning artifact. It does not change the current conclusion."""
    model_config = {"extra": "allow"}

    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    review_mode: str = Field("artifact_self_review", description="复盘模式")
    run_dir: str = Field("", description="被复盘的 run 目录")
    backtest_date: Optional[str] = Field(None, description="回测日")
    final_stance: str = Field("", description="最终立场")
    approval_status: str = Field("", description="审批状态")
    publish_status: str = Field("", description="DataIntegrity 发布状态")
    attribution_findings: List[RunReviewFinding] = Field(default_factory=list, description="按责任层归因的发现")
    learning_updates: List[str] = Field(default_factory=list, description="可沉淀到架构/提示词/测试的学习点")
    next_run_checks: List[str] = Field(default_factory=list, description="下一轮真实 run 必查项")


class OutcomeWindowPerformance(BaseModel):
    """Post-hoc QQQ performance for one review window."""
    model_config = {"extra": "allow"}

    window: str = Field(..., description="复盘窗口，如 +1w / +1m / +3m / +6m / +12m")
    target_trading_days: int = Field(..., description="目标交易日间隔")
    start_date: str = Field("", description="回测日或其后的实际交易日")
    end_date: str = Field("", description="窗口对应的实际交易日")
    start_close: Optional[float] = Field(None, description="QQQ 起点收盘价")
    end_close: Optional[float] = Field(None, description="QQQ 终点收盘价")
    return_pct: Optional[float] = Field(None, description="窗口收益率百分比")
    max_drawdown_pct: Optional[float] = Field(None, description="窗口内相对起点最大下探百分比")
    data_status: str = Field("missing", description="available / missing / incomplete")


class OutcomeReviewReport(BaseModel):
    """Post-hoc market outcome review. It must not feed historical-day prompts."""
    model_config = {"extra": "allow"}

    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    review_mode: str = Field("post_hoc_outcome_review", description="复盘模式")
    run_dir: str = Field("", description="被复盘的 run 目录")
    backtest_date: Optional[str] = Field(None, description="历史判断日")
    tradable_proxy: str = Field("QQQ", description="后验表现代理")
    source: str = Field("", description="后验价格数据来源")
    leakage_boundary: str = Field(
        "Outcome Review is generated only after Final; these post-hoc returns are not included in L1-L5, Bridge, Thesis, Risk, Reviser, or Final prompts.",
        description="后验隔离说明",
    )
    windows: List[OutcomeWindowPerformance] = Field(default_factory=list, description="后续表现窗口")
    market_outcome_label: str = Field("", description="后续市场大涨/下跌/震荡等标签")
    caution_review: str = Field("", description="后续大涨时，原判断是否过度谨慎")
    aggression_review: str = Field("", description="后续下跌时，原判断是否过度冒进")
    attribution_findings: List[RunReviewFinding] = Field(default_factory=list, description="Outcome 角度归因")
    learning_updates: List[str] = Field(default_factory=list, description="可沉淀的学习点")
    claim_outcome_scores: List[Dict[str, Any]] = Field(default_factory=list, description="逐条 final claim 的 T+20/60/120 复盘打分")
    claim_outcome_score_summary: Dict[str, Any] = Field(default_factory=dict, description="claim outcome scores 按 claim_type/source_tier 的汇总")
    claim_outcome_score_ref: str = Field("", description="独立 claim_outcome_scores.json 产物路径")
    prompt_leakage_checks: List[str] = Field(default_factory=list, description="确认后验未入当日 prompt 的检查")


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

    event_refs: Dict[str, Dict[str, Any]] = Field(
        default_factory=dict,
        description="独立事件底账索引；Bridge/Thesis 可选使用，L1-L5 不接收"
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
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

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
