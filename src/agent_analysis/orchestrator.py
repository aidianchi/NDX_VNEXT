from __future__ import annotations

import copy
import json
import logging
import os
import re
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple, Type

try:
    from .contracts import (
        AgentBudget,
        AnalysisPacket,
        AnalysisRevised,
        BridgeMemo,
        AdjudicationChangeRecord,
        AdjudicationHistory,
        ClaimLedger,
        ClaimLedgerEntry,
        CompetingHypothesis,
        ContextBrief,
        Critique,
        EvidencePassport,
        EvidenceRegistry,
        CounterThesisDraft,
        Confidence,
        EvidenceSourceAuthority,
        EventInterpretationCard,
        EventInterpretationPassport,
        EventSectionSummary,
        FinalAdjudication,
        GoldenPitChecklist,
        GoldenPitChecklistItem,
        GovernanceInputPacket,
        HypothesisCompetition,
        InquiryMessage,
        InquiryMessageType,
        InquiryRouterOutput,
        InvestigationReport,
        LayerCard,
        ObjectiveFirewallSummary,
        OutcomeReviewReport,
        PermissionType,
        QualityGate,
        SynthesisPacket,
        LayerSynthesisItem,
        BridgeSynthesisItem,
        RiskBoundaryReport,
        RunReviewReport,
        SchemaGuardReport,
        ThesisDraft,
        UserDecisionCondition,
        UserDecisionProfile,
    )
    from .deep_research_canon import L3_STRUCTURAL_PRIORITY_FUNCTIONS, build_layer_canon_prompt, get_indicator_canon
    from .few_shot import build_layer_few_shot_prompt
    from .inquiry_router import InquiryRouter
    from .llm_engine import (
        LLMEngine,
        normalize_none_list_fields_for_strict_schema_validation,
        sanitize_json_schema_for_strict_tool_calling,
    )
    from .packet_builder import indicator_payload_unavailable_reason
    from .run_review import build_run_review_report
    from .outcome_review import build_outcome_review_report
except ImportError:
    from contracts import (
        AgentBudget,
        AnalysisPacket,
        AnalysisRevised,
        BridgeMemo,
        AdjudicationChangeRecord,
        AdjudicationHistory,
        ClaimLedger,
        ClaimLedgerEntry,
        CompetingHypothesis,
        ContextBrief,
        Critique,
        EvidencePassport,
        EvidenceRegistry,
        CounterThesisDraft,
        Confidence,
        EvidenceSourceAuthority,
        EventInterpretationCard,
        EventInterpretationPassport,
        EventSectionSummary,
        FinalAdjudication,
        GoldenPitChecklist,
        GoldenPitChecklistItem,
        GovernanceInputPacket,
        HypothesisCompetition,
        InquiryMessage,
        InquiryMessageType,
        InquiryRouterOutput,
        InvestigationReport,
        LayerCard,
        ObjectiveFirewallSummary,
        OutcomeReviewReport,
        PermissionType,
        QualityGate,
        SynthesisPacket,
        LayerSynthesisItem,
        BridgeSynthesisItem,
        RiskBoundaryReport,
        RunReviewReport,
        SchemaGuardReport,
        ThesisDraft,
        UserDecisionCondition,
        UserDecisionProfile,
    )
    from deep_research_canon import L3_STRUCTURAL_PRIORITY_FUNCTIONS, build_layer_canon_prompt, get_indicator_canon
    from few_shot import build_layer_few_shot_prompt
    from inquiry_router import InquiryRouter
    from llm_engine import (
        LLMEngine,
        normalize_none_list_fields_for_strict_schema_validation,
        sanitize_json_schema_for_strict_tool_calling,
    )
    from packet_builder import indicator_payload_unavailable_reason
    from run_review import build_run_review_report
    from outcome_review import build_outcome_review_report

try:
    from ..data_availability import has_meaningful_observation_value
except ImportError:
    from data_availability import has_meaningful_observation_value

try:
    from ..data_evidence import data_evidence_issues, normalize_source_tier_for_evidence_passport
except ImportError:
    from data_evidence import data_evidence_issues, normalize_source_tier_for_evidence_passport

try:
    from ..state_ledger import STATE_VARIABLE_SPEC_BY_KEY, extract_state_variables
except ImportError:
    from state_ledger import STATE_VARIABLE_SPEC_BY_KEY, extract_state_variables

logger = logging.getLogger(__name__)

PROMPT_FILES = {
    "l1_analyst": "l1_analyst.md",
    "l2_analyst": "l2_analyst.md",
    "l3_analyst": "l3_analyst.md",
    "l4_analyst": "l4_analyst.md",
    "l5_analyst": "l5_analyst.md",
    "bridge": "cross_layer_bridge.md",
    "thesis": "thesis_builder.md",
    "counter_thesis": "counter_thesis.md",
    "critic": "critic.md",
    "risk": "risk_sentinel.md",
    "reviser": "reviser.md",
    "final": "final_adjudicator.md",
    "controlled_investigation": "controlled_investigator.md",
    "event_card_interpreter": "event_card_interpreter.md",
    "event_section_summary": "event_section_summary.md",
}

# 合约—说明书一致性登记表：stage_key -> 该 stage 的 prompt 文件里必须逐字出现的关键词。
#
# 存在理由（真实事故 run 20260724_223804）：合约写在本文件的 validator 里，说明书写在
# prompts/*.md 里，两者没有任何东西保证说的是同一件事。每加一条治理要求，改 validator
# 是必做的、改 prompt 是"顺手做一下"——不做也没人报错，直到一次正式跑崩在那儿。
# reviser 当时同时挂着 _validate_stage_evidence_refs 和 _validate_thesis_hypothesis_responses
# 两条合约，而它的 prompt 一条都没写，于是两条各崩过一次真实运行。
#
# 新增/修改 stage validator 时，必须同步在这里登记它会点名的字段或规则关键词；
# tests/test_governance_input.py 会强制两边对齐。
STAGE_CONTRACT_PROMPT_REQUIREMENTS: Dict[str, tuple] = {
    # _validate_thesis_hypothesis_responses + evidence_index 合法性
    # 2026-07-27 T28：触发集合从"仅 candidate"扩大为"非 downgraded"（含 leading /
    # kept_unresolved），说明书必须逐字点名这两个新状态词，否则又是"合约写在代码里、
    # 模型看不见"的 T19 型漂移。
    # 2026-07-29 追加 conflict_id：审计闸门按编号认亲，而正方会把上游冲突的类型名
    # 改写成自己的措辞（run 20260728_222759：bridge `rate_vs_valuation` → thesis
    # `real_rate_vs_valuation`），于是闸门谎报"高严重度冲突被抹平"——冲突其实一条没丢。
    "thesis": ("hypothesis_responses", "evidence_index", "kept_unresolved", "downgraded", "conflict_id"),
    # reviser 同时受上述两条合约约束，是合约面最宽的治理 stage
    "reviser": ("hypothesis_responses", "evidence_index", "kept_unresolved", "downgraded", "conflict_id"),
    # _validate_stage_evidence_refs + _validate_reasoned_verdict_refs（三条理由各带引用）
    # 2026-08-17 T54 批 6：claim_ledger 从模型答卷撤下——台账整本由代码装配
    # （_build_final_claim_ledger），模型输出在归一化阶段摘除、不进校验，登记词同步摘下。
    # 2026-08-16 T42②/③追加两个关键词：数字存在性比对（判决正文里的百分数/小数
    # 必须逐字来自输入）与 conflict_refs（终审必须用编号覆盖保留的高严重度冲突）。
    "final": ("evidence_index", "三条主要理由", "数字", "conflict_refs"),
    # _validate_counter_thesis_draft + CompetingHypothesis 必填字段（真实事故 run
    # 20260724_223804：counter_thesis.md 从未逐字写过 hypothesis_text /
    # falsification_conditions，模型两次尝试各猜错一个字段名，约 28 万 prompt token
    # 被烧光后退回确定性兜底稿）
    "counter_thesis": (
        "hypothesis_text",
        "falsification_conditions",
        "support_evidence_refs",
        "diagnostic_evidence_refs",
        "evidence_index",
    ),
    # Critique.revision_direction 是 pydantic max_length 硬约束（不是自定义 validator，
    # 但同样是"模型没被告知就会被拒"的合约面）。真实事故复现于 20260725_232410：
    # critic.md 当时未提及 200 字符上限，模型认真写长了被打回重试一次。这里的登记与
    # 来源不限于自定义 validator——凡是会让结构校验/合约校验判失败、却可能没被写进
    # 说明书的约束，都值得登记，不局限于 lambda validator。
    #
    # 2026-07-26 数字规则重构：overall_assessment 的 200 字符上限已确认无下游依据、
    # 纯属人为限制并已移除，故从此登记撤下；revision_direction 上限放宽至 500，
    # 登记同步更新为新数字。
    "critic": ("500",),
    # 2026-07-28「丙」反射闸门上线后立刻查出的三个漏登记 stage。前两个的说明书本来就
    # 写过对应规则，只是从没登记；bridge 是真缺口——`_validate_bridge_memo_v2` 硬性要求
    # resonance_chains 的 confirming_indicators / falsifiers 非空，而 cross_layer_bridge.md
    # 里这两个词各出现 0 次，真实 run 20260728_110702 的 bridge 就为此重试了一次
    # （`resonance_chains[resonance_chain].confirming_indicators must not be empty`）。
    "bridge": ("confirming_indicators", "falsifiers", "path_id"),
    # _event_card_validation_errors：机制假设前缀 + 不得断言市场必然方向
    # 2026-07-30：删除 attribution_quote 与"该事件可能通过"前缀两条登记——对应闸门已按
    # 用户裁决删除（措辞由代码渲染保证，见 _event_card_validation_errors 的说明）。
    # 仅保留方向越权这条禁止型规则。
    "event_card_interpreter": ("必须涨或必须跌",),
    # _event_section_summary_validation_errors：卡片引用格式与 2-5 张的引用数量区间。
    # T36（2026-07-31）：cited_event_ids 已改为代码从正文 [card:...] 标记里提取，
    # 不再要求模型自报这份清单，故从登记里摘下——它不再是"模型必须被告知的字段名"。
    "event_section_summary": ("[card:", "至少引用两张"),
}

# 「丙」的豁免名单：`_run_stage` 的 stage_key 在这些调用点是运行时拼出来的，静态扫描
# 无法解析，只能显式登记豁免并写清理由——豁免必须看得见，不能靠扫描器沉默跳过。
DYNAMIC_STAGE_KEY_CALL_SITES: Dict[str, str] = {
    "layer_analyst": (
        "L1-L5 分析站的 stage_key 由 f-string 按层拼出（如 l1_analyst）；它们共用一份"
        "按层渲染的说明书模板，合约面由 _validate_layer_card_v2 统一约束，不适用"
        "单文件关键词登记。"
    ),
    "generic_stage_helper": (
        "内部通用 _run_stage 包装，stage_key 由调用方传入变量；真正的合约登记落在"
        "各自的具体 stage 上。"
    ),
}

# 证据权限等级：**唯一**词汇表（2026-07-28 单一事实源审计发现并根治）。
#
# 此前这份事实分两处各存一份：`_field_authority_from_payload` 里的 `usage_rank` 既当
# 排序表又当白名单，而 36 行之后的 `_field_authority_usages` 另写了一份 `allowed` 集合。
# 两份已经漂移——`usage_rank` 漏收 `validation_only`（"经第三方交叉校验的值"），于是
# `tools_L4.py` 真实产出的 `usage="validation_only"` 一进合并逻辑就被静默改写成
# `audit_only`，报告里解释"这条证据为什么被降级"的审计文案因此与工具本意对不上。
# 当时没有翻转 verified/downgraded 判定，纯属两者恰好同档的侥幸，不是设计保证。
#
# rank 用于两个来源声明冲突时取更保守的一档；`validation_only` 与 `audit_only` 同档，
# 与既有弱证据集合（`_downgrade_reason_for_claim` 里的判断）口径一致，因此这次修复
# 只恢复了标签的真实性，不改变任何既有的强弱判定。
METRIC_AUTHORITY_USAGE_RANK: Dict[str, int] = {
    "rejected": 0,
    "audit_only": 1,
    "validation_only": 1,
    "supporting_only": 2,
    "core_allowed": 3,
}

PROMPT_AUDIT_BOOKKEEPING_FIELDS = {
    "source_switches",
    "StaleReferences",
    "HistoryOfMarket",
    "raw_wind_payload_compact",
    "recompute_input",
    "recompute_inputs",
    "source_snapshot",
}

# Thesis / Counter-Thesis prompt 瘦身阈值（investigation_reports/20260725_thesis_
# counter_thesis_slimming/PROPOSAL.md）：evidence_index 里超过这个条数、且序列化
# 后超过这个字符数的嵌套列表（全成分逐票明细、raw_series 历史序列等）判定为
# "审计专用明细"——两站的合法 evidence_ref 只到 parent#field_name 一层，模型没有
# 任何合法引用路径能指到某一票或某一天，压缩前后模型"能合法引用什么"完全不变。
# ref key 本身和聚合字段（value/coverage/windows/...）不受影响；完整明细继续留在
# synthesis_packet.json / evidence_registry.json 供审计与独立重算。
EVIDENCE_FIELD_LIST_PROMPT_COUNT_THRESHOLD = 8
EVIDENCE_FIELD_LIST_PROMPT_CHAR_THRESHOLD = 800

# thesis_builder.md「## 输入」重点字段清单和「对竞争假说的强制回应」一节、
# counter_thesis.md「## 输入边界」清单，均未把这些字段列为必读；
# evidence_registry_summary 明确是 _build_governance_input_packet 转发给 Critic/
# Risk/Reviser/Final 四个治理站用的阶段 4 摘要，不是这两站的输入面。只在喂给
# LLM 的 prompt 层丢弃——_run_thesis / _counter_thesis_prompt_payload 构造出的
# 完整 payload 仍保留它们，供 checkpoint 续跑比对和 prompt_input_audit 使用完整
# 上游输入。
# 叙事阶段 prompt 中可以安全丢弃的记账类字段。
#
# 【2026-07-27 收缩：`hypothesis_competition_summary` 与 `adjudication_history` 撤出丢弃清单】
# 首版把这两个字段一并丢弃，重复采样实验证明这是错的（脚本见 WORK_LOG 同日条目）：
#   现状丢弃：thesis.invalidation_conditions = [2, 2, 2]（含原跑 232410 共 4/4 恒为 2）
#   仅保留 hypothesis_competition_summary：= [4, 5, 3]
#   未瘦身历史基线（20260725_145833）：4
# 两组区间零重叠。机制清楚：`hypothesis_competition_summary.retained_disputes` 装的是
# 11 条"未解决的争议"，而"改判条件"本就是从"我哪里还不确定"推导出来的——把不确定
# 清单从 thesis 眼前拿走，它就写不出独立的失效通道，只能退化成"多个条件同时成立才
# 算失效"的复合 AND 条件，实际永远不会触发（等于把确认偏误制度化）。
# 代价对比更说明问题：丢弃这四个字段合计只省 0.40%，而证据索引明细压缩省 72.71%。
# 为 0.4% 的 token 牺牲"冲突是资产"的核心载体，不成比例。
# `adjudication_history` 同批保留：403 字符，记录 candidate → kept_unresolved 的降级
# 原因，是假说降级审计链，thesis 需要看见"这条假说为什么被降级"。
# 余下两项属纯记账元数据（输入边界声明、证据护照计数），维持丢弃。
NARRATIVE_STAGE_PROMPT_DROP_FIELDS: Dict[str, tuple] = {
    "thesis": (
        "counter_thesis_boundary",
        "evidence_registry_summary",
    ),
    "counter_thesis": ("evidence_registry_summary",),
}
EVENT_INTERPRETATION_CARD_LIMIT = 10
EVENT_FINANCIAL_LINKS = [
    "earnings_path",
    "valuation_multiple",
    "discount_rate",
    "risk_premium",
    "liquidity_condition",
    "credit_condition",
    "index_structure",
    "market_breadth",
    "technical_flow",
]

INLINE_PROMPTS = {
    "bridge": "你负责显式识别跨层支撑关系、冲突关系与关键不确定性。只返回合法 JSON。",
    "thesis": "你负责把 synthesis_packet 整合成状态、价格、赔率、动作和失效条件，并保留未解决冲突。只返回合法 JSON。",
    "counter_thesis": "你负责在 Thesis 之前提出独立反方假说，只读取允许输入并返回合法 JSON。",
    "critic": "你负责攻击 ThesisDraft 的逻辑弱点、证据跳跃和过度谨慎导致的错过赔率风险。只返回合法 JSON。",
    "risk": "你负责保留下行风险、踏空风险、确认成本、失效条件与必须保留的风险提示。只返回合法 JSON。",
    "reviser": "你负责吸收 critique/risk/schema 反馈后修订 thesis，保留决策语义和冲突，不能自动改得更保守。只返回合法 JSON。",
    "final": "你负责分离内部 quality_gate 与 reader_final，给出状态、价格、赔率、动作和失效条件。只返回合法 JSON。",
}


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _model_dump(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if hasattr(value, "dict"):
        return value.dict()
    return value


def _dump_governance_input(packet: Any, consumer: str) -> Dict[str, Any]:
    """序列化 GovernanceInputPacket 进治理站 payload。

    consumer="risk" 时做论证盲形式收尾（配餐单/C3）：thesis_* 键（含 thesis 派生的
    retained_conflict_types）从序列化结果里整个移除，而不是以空值残留——空键出现在
    risk 包与提示词里同样构成分料泄漏。契约字段保持原样不动，排除只发生在序列化
    这一步；critic/reviser/final 默认路径不受影响。
    """
    dumped = _model_dump(packet)
    if consumer == "risk" and isinstance(dumped, dict):
        for key in [k for k in dumped if k.startswith("thesis_") or k == "retained_conflict_types"]:
            dumped.pop(key, None)
    return dumped


def _inject_evidence_fields(card_dict: Dict[str, Any], event: Dict[str, Any]) -> None:
    """T49 第二件：把源材料的正文摘录与可用标志逐字注入卡 dict（纯代码搬运，非模型输出）。

    空正文纪律：raw_text_available=false 时 evidence_excerpt 必须为空字符串。
    契约零改动：只作用于落盘副本；内存/模型对象不含这些字段
    （EventInterpretationCard 为 extra="forbid"，模型契约一个字不改）。
    """
    available = bool(event.get("raw_text_available"))
    card_dict["evidence_excerpt"] = event.get("raw_text_excerpt") or "" if available else ""
    card_dict["raw_text_available"] = available


def _with_evidence_injected_artifact(
    artifact: Dict[str, Any],
    events_by_id: Dict[str, Dict[str, Any]],
) -> Dict[str, Any]:
    """返回 artifact 的深拷贝副本，其中每张卡按 event_id 对回源材料注入证据字段。"""
    injected = copy.deepcopy(artifact)
    for card in injected.get("cards") or []:
        if isinstance(card, dict):
            _inject_evidence_fields(card, events_by_id.get(str(card.get("event_id") or ""), {}))
    return injected


def _enum_value(value: Any) -> Any:
    return getattr(value, "value", value)


def _as_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


_SEVERITY_HIGH_MEDIUM = frozenset({"high", "medium"})
# T54 批 3：原 _PERMISSION_TYPE_VALUES（08-16 过渡安全带"非枚举才回正"的配套表）
# 已随无条件法典装配下线——不再有"枚举内合法值保留"的判定需求。
_EVIDENCE_REF_PATTERN = re.compile(r"L[1-5]\.[A-Za-z_][A-Za-z0-9_]*(?:#[A-Za-z_][A-Za-z0-9_]*)?")
_AUTHORITY_OVERREACH_RULES: Dict[str, List[tuple[str, str]]] = {
    "technical": [
        (r"(估值便宜|估值低估|undervalued|cheap valuation)", "technical_indicator_claims_valuation"),
        (r"(技术|均线|RSI|MACD|ADX|ATR|价格|趋势|超买|超卖).{0,20}(证明|说明|表明).{0,12}(估值便宜|估值低估|基本面改善|盈利改善)", "technical_indicator_overclaims_valuation_or_fundamentals"),
        (r"(基本面已经改善|盈利已经改善|fundamentals? (have )?improved)", "technical_indicator_claims_fundamentals"),
        (r"(大买|强烈买入|all[- ]?in)", "technical_indicator_outputs_strong_action"),
    ],
    "proxy": [
        (r"(官方事实|官方真理|official fact|official truth)", "proxy_marked_as_official_fact"),
        (r"(代理|proxy).{0,20}(证明|proves?).{0,20}(真实|actual|official)", "proxy_overclaims_actual_or_official_state"),
    ],
    "composite": [
        (r"(单一原因|唯一原因|sole cause|single cause)", "composite_overclaims_single_cause"),
        (r"(官方事实|official fact)", "composite_marked_as_official_fact"),
    ],
    "structural": [
        (r"(证明|说明|表明).{0,12}(短线买点|短线卖点|立刻买入|立刻卖出)", "structural_indicator_claims_tactical_timing"),
    ],
}

# 键必须与 contracts.PRICE_REFLECTION_CATEGORY_KEYS 完全一致（唯一名单），
# 由模块末尾的断言在导入时强制；这里额外承载每类的 target / label / hint 文案。
PRICE_REFLECTION_CATEGORIES: Dict[str, Dict[str, str]] = {
    "credit": {
        "target": "credit_stress",
        "label": "信用",
        "hint": "信用利差、融资压力或信用风险是否已被价格反映",
    },
    "rates": {
        "target": "rates_discount_rate",
        "label": "利率",
        "hint": "名义/真实利率和贴现率压力是否已被价格反映",
    },
    "valuation": {
        "target": "valuation_risk_premium",
        "label": "估值",
        "hint": "估值压缩、ERP 或盈利风险补偿是否已被价格反映",
    },
    "technical_panic": {
        "target": "technical_panic_positioning",
        "label": "技术恐慌",
        "hint": "恐慌、波动、趋势破坏或反抽是否已被价格反映",
    },
    "liquidity": {
        "target": "liquidity_conditions",
        "label": "流动性",
        "hint": "政策/市场流动性冲击与修复是否已被价格反映",
    },
}


def _severity_is_high_or_medium(conflict: Any) -> bool:
    return str(_enum_value(conflict.severity)) in _SEVERITY_HIGH_MEDIUM


def _layer_has_usable_raw_data(layer_payload: Any) -> bool:
    if not isinstance(layer_payload, dict):
        return False
    for indicator_payload in layer_payload.values():
        if not isinstance(indicator_payload, dict):
            continue
        if indicator_payload.get("error"):
            continue
        if _indicator_payload_unavailable_for_object_firewall(indicator_payload):
            continue
        if "value" in indicator_payload:
            if has_meaningful_observation_value(indicator_payload.get("value")):
                return True
            continue
        if has_meaningful_observation_value(indicator_payload):
            return True
    return False


def _indicator_payload_unavailable_for_object_firewall(payload: Dict[str, Any]) -> bool:
    return indicator_payload_unavailable_reason(payload) is not None


class VNextOrchestrator:
    """Lightweight real-LLM orchestrator for the vNext chain."""

    def __init__(
        self,
        *,
        available_models: List[str],
        output_dir: str,
        prompts_dir: Optional[str] = None,
        llm_engine: Optional[Any] = None,
        max_node_retries: int = 2,
        schema_guard_retry: bool = True,
        resume_from_existing: bool = False,
        model_mode: str = "",
    ) -> None:
        if not llm_engine and not available_models:
            raise ValueError("At least one available model is required.")
        self.available_models = available_models
        self.model_mode = (model_mode or "").strip() or os.environ.get("NDX_MODEL_MODE", "").strip()
        self.output_dir = Path(output_dir).resolve()
        self.prompts_dir = Path(prompts_dir) if prompts_dir else Path(__file__).with_name("prompts")
        self.llm_engine = llm_engine or LLMEngine(available_models=available_models)
        self.max_node_retries = max_node_retries
        self.schema_guard_retry = schema_guard_retry
        self.resume_from_existing = resume_from_existing
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.layer_cards_dir = self.output_dir / "layer_cards"
        self.layer_context_dir = self.output_dir / "layer_context_briefs"
        self.bridge_dir = self.output_dir / "bridge_memos"
        self.investigation_reports_dir = self.output_dir / "investigation_reports"
        self.prompt_audit_dir = self.output_dir / "prompt_audit"
        self.layer_cards_dir.mkdir(exist_ok=True)
        self.layer_context_dir.mkdir(exist_ok=True)
        self.bridge_dir.mkdir(exist_ok=True)
        self.investigation_reports_dir.mkdir(exist_ok=True)
        self.prompt_audit_dir.mkdir(exist_ok=True)
        self.stage_diagnostics: Dict[str, Any] = {"schema_version": "vnext_llm_stage_diagnostics_v1", "stages": {}}
        self.stage_manifest_path = self.output_dir / "stage_manifest.json"
        self.stage_manifest = self._load_stage_manifest()
        self.stage_model_routing = self._load_stage_model_routing()

    def run(self, packet: AnalysisPacket | Dict[str, Any]) -> Dict[str, Any]:
        packet_model = packet if isinstance(packet, AnalysisPacket) else AnalysisPacket.model_validate(packet)
        self._save_json("analysis_packet.json", packet_model)
        self._save_json("runtime_boundary_manifest.json", self._build_runtime_boundary_manifest())
        self._save_json("feedback_contract_manifest.json", self._build_feedback_contract_manifest())

        context_brief = self._build_context_brief(packet_model)
        self._save_json("context_brief.json", context_brief)

        layer_cards = self._run_layer_cards(packet_model, context_brief)
        bridge_v1 = self._run_bridge(packet_model, context_brief, layer_cards)
        feedback_messages = self._build_feedback_inquiry_messages(packet_model, layer_cards, bridge_v1)
        inquiry_router_output = self._route_feedback_inquiries(feedback_messages)
        investigation_reports = self._run_controlled_investigations(inquiry_router_output)
        bridge_v2 = self._build_bridge_v2(
            packet_model=packet_model,
            layer_cards=layer_cards,
            bridge_v1=bridge_v1,
            router_output=inquiry_router_output,
            investigation_reports=investigation_reports,
        )
        bridge_memos = [bridge_v1, bridge_v2]
        synthesis_packet = self._build_synthesis_packet(packet_model, context_brief, layer_cards, bridge_memos)
        hypothesis_competition = self._build_hypothesis_competition(
            synthesis_packet=synthesis_packet,
            bridge_v2=bridge_v2,
            investigation_reports=investigation_reports,
            effective_date=self._effective_date(packet_model),
        )
        synthesis_packet.competing_hypotheses = hypothesis_competition.hypotheses
        synthesis_packet.hypothesis_competition_summary = self._hypothesis_competition_summary(hypothesis_competition)
        synthesis_packet.adjudication_history = list(hypothesis_competition.downgrade_or_split_events)
        synthesis_packet.counter_thesis_boundary = {
            "input_refs": list(hypothesis_competition.input_refs),
            "forbidden_context_refs": list(hypothesis_competition.forbidden_context_refs),
            "independence_verified": "thesis_draft.json" in set(hypothesis_competition.forbidden_context_refs),
        }
        event_interpretation_cards = self._build_event_interpretation_cards(
            effective_date=self._effective_date(packet_model),
            feedback_messages=feedback_messages,
            hypothesis_competition=hypothesis_competition,
        )
        evidence_registry = self._build_evidence_registry(
            packet_model=packet_model,
            synthesis_packet=synthesis_packet,
            investigation_reports=investigation_reports,
            hypothesis_competition=hypothesis_competition,
        )
        synthesis_packet.evidence_registry_summary = self._evidence_registry_summary(evidence_registry)
        self._save_json("synthesis_packet.json", synthesis_packet)
        self._save_json("evidence_registry.json", evidence_registry)
        thesis = self._run_thesis(synthesis_packet)

        gov_input_critic = self._build_governance_input_packet(
            synthesis_packet=synthesis_packet,
            thesis=thesis,
            layer_cards=layer_cards,
        )
        critique = self._run_and_save(
            stage_key="critic",
            stage_name="critic",
            model_cls=Critique,
            payload={"governance_input": _model_dump(gov_input_critic)},
            filename="critique.json",
            strict_tool_schema=self._strict_tool_schema_for_stage("critic", Critique),
            strict_tool_name="emit_critique",
        )

        gov_input_risk = self._build_governance_input_packet(
            synthesis_packet=synthesis_packet,
            thesis=thesis,
            layer_cards=layer_cards,
            consumer="risk",
        )
        risk_report = self._run_and_save(
            stage_key="risk",
            stage_name="risk",
            model_cls=RiskBoundaryReport,
            payload={"governance_input": _dump_governance_input(gov_input_risk, "risk")},
            filename="risk_boundary_report.json",
        )

        schema_report = self._run_schema_guard(packet_model, layer_cards, bridge_memos, thesis, critique, risk_report)
        self._save_json("schema_guard_report.json", schema_report)

        # Schema Guard retry: if enabled and structural issues found, re-run thesis/critic/risk once
        # with the schema issues injected into governance input, then re-check.
        if self.schema_guard_retry and not schema_report.passed and (schema_report.structural_issues or schema_report.missing_fields):
            logger.warning(
                "Schema Guard detected structural issues; retrying thesis/critic/risk with "
                "schema feedback injected into governance input."
            )
            gov_input_critic_retry = self._build_governance_input_packet(
                synthesis_packet=synthesis_packet,
                thesis=thesis,
                layer_cards=layer_cards,
                schema_report=schema_report,
            )
            critique = self._run_and_save(
                stage_key="critic",
                stage_name="critic_retry",
                model_cls=Critique,
                payload={"governance_input": _model_dump(gov_input_critic_retry)},
                filename="critique.json",
                strict_tool_schema=self._strict_tool_schema_for_stage("critic", Critique),
                strict_tool_name="emit_critique",
            )
            gov_input_risk_retry = self._build_governance_input_packet(
                synthesis_packet=synthesis_packet,
                thesis=thesis,
                layer_cards=layer_cards,
                schema_report=schema_report,
                consumer="risk",
            )
            risk_report = self._run_and_save(
                stage_key="risk",
                stage_name="risk_retry",
                model_cls=RiskBoundaryReport,
                payload={"governance_input": _dump_governance_input(gov_input_risk_retry, "risk")},
                filename="risk_boundary_report.json",
            )
            schema_report = self._run_schema_guard(
                packet_model, layer_cards, bridge_memos, thesis, critique, risk_report
            )
            self._save_json("schema_guard_report.json", schema_report)
            if not schema_report.passed:
                logger.warning(
                    "Schema Guard still failing after retry; continuing with residual issues. "
                    "Structural: %s; Consistency: %s",
                    schema_report.structural_issues,
                    schema_report.consistency_issues,
                )

        gov_input_reviser = self._build_governance_input_packet(
            synthesis_packet=synthesis_packet,
            thesis=thesis,
            critique=critique,
            risk_report=risk_report,
            schema_report=schema_report,
            layer_cards=layer_cards,
            consumer="reviser",
        )
        reviser_payload = {"governance_input": _model_dump(gov_input_reviser)}
        conflict_id_candidates = self._collect_thesis_conflict_id_candidates(synthesis_packet)
        analysis_revised = self._load_reviser_checkpoint(reviser_payload)
        if analysis_revised is None:
            try:
                analysis_revised = self._run_stage(
                    stage_key="reviser",
                    stage_name="reviser",
                    model_cls=AnalysisRevised,
                    payload=reviser_payload,
                    # T42④：reviser 重新产出同结构的 retained_conflicts[].conflict_id，
                    # 必须与 thesis 站同款 enum 选单，防止模型抄写时自行改写编号前缀。
                    strict_tool_schema=self._strict_tool_schema_for_stage(
                        "reviser",
                        AnalysisRevised,
                        schema_postprocess=lambda schema: self._constrain_reviser_conflict_id_enum(
                            schema, conflict_id_candidates
                        ),
                    ),
                    strict_tool_name="emit_analysis_revised",
                    # 两道 pre-validate 降级，顺序不可颠倒：
                    # 1) 遗漏继承——reviser 整个漏掉的 revised_thesis 字段从 thesis 原稿原样
                    #    搬回并留痕（键存在则一律不碰，见 _carry_forward_reviser_thesis_fields）；
                    # 2) 引用净化——幻觉出的非法 parent#field 可退回的退回、混合权威父级或
                    #    无法解析的丢弃。继承先行，使搬回的原稿引用也过同一张净化网。
                    # 两者都不放松下方 validator 的合法性判定：残留问题仍会被拦下并重试。
                    # 3) T54 批 2 追加最外层：revision_claimed_fields 由代码 diff 装配
                    #    （必须在继承与净化之后计算，才与最终落盘实物一致）。
                    pre_validate_transform=lambda parsed: self._inject_revision_claimed_fields(
                        self._sanitize_reviser_evidence_refs(
                            self._carry_forward_reviser_thesis_fields(parsed, thesis),
                            synthesis_packet.evidence_index,
                        ),
                        thesis,
                    ),
                    validator=lambda candidate: (
                        self._validate_stage_evidence_refs(
                            candidate,
                            set(synthesis_packet.evidence_index.keys()),
                            "reviser",
                        )
                        + self._validate_thesis_hypothesis_responses(
                            candidate.revised_thesis,
                            synthesis_packet,
                        )
                    ),
                )
            except RuntimeError as exc:
                # 软着陆：reviser 是编辑岗，它失败不该让上游约 25 分钟的采集、五层分析、
                # 桥接、论点、批评、风险全部归零（对照 counter_thesis 的既有兜底成例）。
                # 退回未修订的 thesis 原稿——该原稿已通过同一组合约校验，所以兜底产物
                # 不放松任何合约；但必须带 degraded_fallback 显式声明"本轮判断书未经修订"。
                logger.warning("reviser 阶段全部尝试均未通过合约校验，退回未修订原稿：%s", exc)
                analysis_revised = self._build_degraded_analysis_revised(thesis, str(exc))
            self._save_json("analysis_revised.json", analysis_revised)
            self._record_stage_artifact(
                self.output_dir / "analysis_revised.json",
                stage_key="reviser",
                stage_name="reviser",
                payload=reviser_payload,
            )

        gov_input_final = self._build_governance_input_packet(
            synthesis_packet=synthesis_packet,
            thesis=analysis_revised.revised_thesis,
            critique=critique,
            risk_report=risk_report,
            schema_report=schema_report,
            analysis_revised=analysis_revised,
            layer_cards=layer_cards,
            consumer="final",
        )
        final_payload = {
            "governance_input": _model_dump(gov_input_final),
        }
        final_source_text = json.dumps(final_payload, ensure_ascii=False, default=str)
        final_adjudication = self._load_stage_checkpoint(
            "final_adjudication.json",
            FinalAdjudication,
            stage_key="final",
            stage_name="final_adjudicator",
            expected_payload=final_payload,
        )
        if final_adjudication is None:
            final_adjudication = self._run_stage(
                stage_key="final",
                stage_name="final_adjudicator",
                model_cls=FinalAdjudication,
                payload=final_payload,
                strict_tool_schema=self._strict_tool_schema_for_stage("final", FinalAdjudication),
                strict_tool_name="emit_final_adjudication",
                validator=lambda candidate: (
                    self._validate_stage_evidence_refs(
                        candidate,
                        set(synthesis_packet.evidence_index.keys()),
                        "final",
                    )
                    + self._validate_reasoned_verdict_refs(
                        candidate,
                        set(synthesis_packet.evidence_index.keys()),
                        source_text=final_source_text,
                    )
                    + self._validate_final_conflict_responses(
                        candidate,
                        analysis_revised.revised_thesis,
                    )
                ),
            )
            token_report = self.llm_engine.get_token_report() if hasattr(self.llm_engine, "get_token_report") else {}
            final_adjudication.token_usage = token_report
            self._save_json("final_adjudication.json", final_adjudication)
            self._record_stage_artifact(
                self.output_dir / "final_adjudication.json",
                stage_key="final",
                stage_name="final_adjudicator",
                payload=final_payload,
            )
        self._annotate_reasoned_verdict_refs(
            final_adjudication,
            set(synthesis_packet.evidence_index.keys()),
        )
        # 修订阶段降级必须进入质量闸门，由发布闸门决定这样一份"未经修订"的判断书能不能发，
        # 而不是让它悄悄长成一份正常报告。
        if getattr(analysis_revised, "degraded_fallback", None):
            self._append_final_quality_note(final_adjudication, "reviser_degraded_unrevised_thesis")
        # 反方降级同理：counter_thesis 两次尝试失败退回确定性兜底稿时，此前只留痕在
        # counter_thesis.json 自己的 prompt_input_audit 里，终审判决书看不出这次反方
        # 论证其实是模板凑数。对齐 reviser 的可见度处理，让发布闸门也能看到这条信号。
        if "counter_thesis_deterministic_fallback" in list(hypothesis_competition.fallback_warnings or []):
            self._append_final_quality_note(final_adjudication, "counter_thesis_degraded_deterministic_fallback")
        # 同理：event_section_summary 走了 T36 的解析失败兜底时把降级信号带进终审
        # 质量闸门，不新造一套发布闸门。
        self._annotate_event_section_summary_degradation(final_adjudication, event_interpretation_cards)
        final_claim_ledger = self._build_final_claim_ledger(
            synthesis_packet=synthesis_packet,
            thesis=analysis_revised.revised_thesis,
            final_adjudication=final_adjudication,
            evidence_registry=evidence_registry,
            effective_date=self._effective_date(packet_model),
            risk_report=risk_report,
        )
        final_adjudication.claim_ledger = final_claim_ledger
        evidence_registry = self._attach_claims_to_evidence_registry(evidence_registry, final_claim_ledger)
        # Persist the enriched final artifact as well as the standalone ledger.
        # Otherwise the in-memory final has a claim gate that the saved final omits.
        self._save_json("final_adjudication.json", final_adjudication)
        self._record_stage_artifact(
            self.output_dir / "final_adjudication.json",
            stage_key="final",
            stage_name="final_adjudicator",
            payload=final_payload,
        )
        self._save_json("final_claim_ledger.json", final_claim_ledger)
        self._save_json("evidence_registry.json", evidence_registry)
        user_decision_profile = self._load_user_decision_profile()
        golden_pit_checklist = self._build_golden_pit_checklist(
            final_claim_ledger=final_claim_ledger,
            decision_profile=user_decision_profile,
            final_adjudication=final_adjudication,
            effective_date=self._effective_date(packet_model),
            state_variables=extract_state_variables(_model_dump(packet_model))[0],
            evidence_registry=evidence_registry,
        )
        self._save_json("user_decision_profile.json", user_decision_profile)
        self._save_json("golden_pit_checklist.json", golden_pit_checklist)
        run_review_report = self._build_run_review_report(
            packet_model=packet_model,
            bridge_memos=bridge_memos,
            synthesis_packet=synthesis_packet,
            thesis=thesis,
            risk_report=risk_report,
            schema_report=schema_report,
            final_adjudication=final_adjudication,
            hypothesis_competition=hypothesis_competition,
        )
        self._save_json("run_review_report.json", run_review_report)
        outcome_review_report = self._build_outcome_review_report(
            packet_model=packet_model,
            final_adjudication=final_adjudication,
        )
        self._save_json("outcome_review_report.json", outcome_review_report)
        reflection_library = self._build_post_run_reflection_library(
            run_review_report=run_review_report,
            outcome_review_report=outcome_review_report,
            schema_report=schema_report,
        )
        self._save_json("post_run_reflection_library.json", reflection_library)
        self._run_persistent_checks()

        return {
            "context_brief": context_brief,
            "layer_cards": layer_cards,
            "bridge_memos": bridge_memos,
            "synthesis_packet": synthesis_packet,
            "hypothesis_competition": hypothesis_competition,
            "event_interpretation_cards": event_interpretation_cards,
            "evidence_registry": evidence_registry,
            "thesis_draft": thesis,
            "critique": critique,
            "risk_boundary_report": risk_report,
            "schema_guard_report": schema_report,
            "analysis_revised": analysis_revised,
            "final_adjudication": final_adjudication,
            "final_claim_ledger": final_claim_ledger,
            "user_decision_profile": user_decision_profile,
            "golden_pit_checklist": golden_pit_checklist,
            "run_review_report": run_review_report,
            "outcome_review_report": outcome_review_report,
            "post_run_reflection_library": reflection_library,
            "output_dir": str(self.output_dir),
        }

    def _build_run_review_report(
        self,
        *,
        packet_model: AnalysisPacket,
        bridge_memos: List[BridgeMemo],
        synthesis_packet: SynthesisPacket,
        thesis: ThesisDraft,
        risk_report: RiskBoundaryReport,
        schema_report: SchemaGuardReport,
        final_adjudication: FinalAdjudication,
        hypothesis_competition: Optional[HypothesisCompetition] = None,
    ) -> RunReviewReport:
        data_integrity = {}
        data_integrity_path = self.output_dir / "data_integrity_report.json"
        if data_integrity_path.exists():
            try:
                data_integrity = json.loads(data_integrity_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                data_integrity = {}
        inquiry_router_output = {}
        inquiry_router_path = self.output_dir / "inquiry_router_output.json"
        if inquiry_router_path.exists():
            try:
                inquiry_router_output = json.loads(inquiry_router_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                inquiry_router_output = {}
        investigation_reports = []
        for report_path in sorted(self.investigation_reports_dir.glob("*.json")):
            try:
                investigation_reports.append(json.loads(report_path.read_text(encoding="utf-8")))
            except json.JSONDecodeError:
                continue
        return build_run_review_report(
            run_dir=str(self.output_dir),
            analysis_packet=_model_dump(packet_model),
            bridges=[_model_dump(memo) for memo in bridge_memos],
            synthesis_packet=_model_dump(synthesis_packet),
            thesis_draft=_model_dump(thesis),
            risk_boundary_report=_model_dump(risk_report),
            schema_guard_report=_model_dump(schema_report),
            final_adjudication=_model_dump(final_adjudication),
            data_integrity_report=data_integrity,
            inquiry_router_output=inquiry_router_output,
            investigation_reports=investigation_reports,
            hypothesis_competition=_model_dump(hypothesis_competition) if hypothesis_competition is not None else self._load_local_json(self.output_dir / "hypothesis_competition.json", {}),
            adjudication_history=self._load_local_json(self.output_dir / "adjudication_history.json", {}),
            evidence_registry=self._load_local_json(self.output_dir / "evidence_registry.json", {}),
            final_claim_ledger=self._load_local_json(self.output_dir / "final_claim_ledger.json", {}),
            golden_pit_checklist=self._load_local_json(self.output_dir / "golden_pit_checklist.json", {}),
        )

    def _build_outcome_review_report(
        self,
        *,
        packet_model: AnalysisPacket,
        final_adjudication: FinalAdjudication,
    ) -> OutcomeReviewReport:
        meta = packet_model.meta if isinstance(packet_model.meta, dict) else {}
        backtest_date = meta.get("backtest_date")
        if not backtest_date:
            return OutcomeReviewReport(
                run_dir=str(self.output_dir),
                backtest_date=meta.get("data_date"),
                source="not_run_for_live_or_non_backtest_context",
                market_outcome_label="not_applicable",
                caution_review="非历史回测语境，不接入后验 QQQ 表现。",
                aggression_review="非历史回测语境，不接入后验 QQQ 表现。",
                prompt_leakage_checks=["Outcome Review skipped because packet has no backtest_date."],
            )
        return build_outcome_review_report(
            run_dir=str(self.output_dir),
            backtest_date=backtest_date,
            final_adjudication=_model_dump(final_adjudication),
        )

    def _build_post_run_reflection_library(
        self,
        *,
        run_review_report: RunReviewReport,
        outcome_review_report: OutcomeReviewReport,
        schema_report: SchemaGuardReport,
    ) -> Dict[str, Any]:
        run_updates = list(getattr(run_review_report, "learning_updates", []) or [])
        outcome_updates = list(getattr(outcome_review_report, "learning_updates", []) or [])
        next_checks = list(getattr(run_review_report, "next_run_checks", []) or [])
        items: List[Dict[str, Any]] = []
        for index, text in enumerate(dict.fromkeys(run_updates + outcome_updates), start=1):
            if not str(text).strip():
                continue
            items.append(
                {
                    "id": f"reflection_{index}",
                    "source": "run_review_or_outcome_review",
                    "lesson": str(text),
                    "allowed_use": "manual_rule_update_or_test_design_for_future_runs",
                    "runtime_prompt_use": "forbidden_for_current_run",
                }
            )
        return {
            "schema_version": "post_run_reflection_library_v1",
            "generated_at": _utc_now().isoformat(),
            "run_dir": str(self.output_dir),
            "boundary": (
                "This artifact is generated after Final. It must not be injected into L1-L5, "
                "Bridge, Thesis, Risk, Reviser, or Final prompts for the current run."
            ),
            "schema_guard_quality_status": getattr(schema_report, "quality_status", ""),
            "items": items,
            "next_run_checks": next_checks,
            "eligible_destinations": ["tests", "documentation", "future prompt/manual rule revisions"],
        }

    def _run_layer_cards(self, packet: AnalysisPacket, context_brief: ContextBrief) -> List[LayerCard]:
        cards: List[LayerCard] = []
        for layer in ["L1", "L2", "L3", "L4", "L5"]:
            layer_payload = self._build_layer_stage_payload(packet, context_brief, layer)
            self._save_json(self.layer_context_dir / f"{layer}.json", layer_payload["context_brief"])
            checkpoint = self._load_stage_checkpoint(
                self.layer_cards_dir / f"{layer}.json",
                LayerCard,
                stage_key=f"{layer.lower()}_analyst",
                stage_name=layer.lower(),
                expected_payload=layer_payload,
            )
            if checkpoint is not None:
                cards.append(checkpoint)
                continue
            card = self._run_stage(
                stage_key=f"{layer.lower()}_analyst",
                stage_name=layer.lower(),
                model_cls=LayerCard,
                payload=layer_payload,
                validator=lambda card, layer=layer: self._validate_layer_card_v2(
                    card,
                    layer,
                    self._analysis_required_indicator_map(packet, layer),
                ),
            )
            if str(card.layer) != layer and getattr(card.layer, "value", None) != layer:
                raise ValueError(f"{layer} analyst returned mismatched layer: {card.layer}")
            cards.append(card)
            # B7：落盘层卡片同样补 percentile_scale 声明（PC-13 扫 payload 与卡片两处）。
            self._save_json(
                self.layer_cards_dir / f"{layer}.json",
                self._annotate_percentile_scales(_model_dump(card)),
            )
            self._record_stage_artifact(
                self.layer_cards_dir / f"{layer}.json",
                stage_key=f"{layer.lower()}_analyst",
                stage_name=layer.lower(),
                payload=layer_payload,
            )
        return cards

    def _build_layer_stage_payload(
        self,
        packet: AnalysisPacket,
        context_brief: ContextBrief,
        layer: str,
    ) -> Dict[str, Any]:
        layer = layer.upper()
        layer_context_brief = self._build_layer_context_brief(packet, context_brief, layer)
        raw_for_prompt = packet.raw_data.get(layer, {})
        if isinstance(raw_for_prompt, dict):
            raw_for_prompt = self._align_metric_names_to_canon(layer, raw_for_prompt)
        return {
            "context_brief": _model_dump(layer_context_brief),
            "layer": layer,
            "layer_facts": self._annotate_percentile_scales(
                self._purify_layer_facts_for_prompt(_model_dump(packet.facts_by_layer.get(layer)))
            ),
            "layer_raw_data": self._annotate_percentile_scales(raw_for_prompt) if isinstance(raw_for_prompt, dict) else raw_for_prompt,
            "manual_overrides": self._build_layer_manual_overrides(packet, layer),
            "runtime_boundary_policy_id": "layer_runtime_input_policy_v1",
        }

    @staticmethod
    def _align_metric_names_to_canon(layer: str, layer_raw_data: Dict[str, Any]) -> Dict[str, Any]:
        """C12 修复：发给模型的 metric_name 与 IndicatorCanon 注册名强制一致。

        以 canon 表为唯一名单，逐 function_id 对齐；canon 表没有的保持原样。
        只改发给模型的副本，不回写 analysis_packet 原始材料。
        """
        aligned: Dict[str, Any] = {}
        for key, item in layer_raw_data.items():
            if not isinstance(item, dict):
                aligned[key] = item
                continue
            function_id = str(item.get("function_id") or key)
            try:
                canon_name = str(get_indicator_canon(function_id).metric_name or "")
            except KeyError:
                canon_name = ""
            if canon_name and str(item.get("metric_name") or "") != canon_name:
                new_item = dict(item)
                new_item["metric_name"] = canon_name
                aligned[key] = new_item
            else:
                aligned[key] = item
        return aligned

    @staticmethod
    def _annotate_percentile_scales(value: Any) -> Any:
        """B7 修复：给 percentile 类数值叶补 `percentile_scale` 声明（0-1 / 0-100）。

        同一 dict 内数值全部 ≤1 → 0-1；全部 >1 → 0-100；两者并存 → mixed。
        只作用于发给模型的副本与落盘层卡片，不回写 analysis_packet 原始材料。
        """
        if isinstance(value, dict):
            annotated = {
                key: VNextOrchestrator._annotate_percentile_scales(item)
                for key, item in value.items()
            }
            scales = set()
            for key, item in annotated.items():
                if (
                    re.search(r"percentile", key, re.IGNORECASE)
                    and isinstance(item, (int, float))
                    and not isinstance(item, bool)
                ):
                    numeric = float(item)
                    scales.add("0-1" if 0.0 <= numeric <= 1.0 else "0-100")
            if scales:
                annotated["percentile_scale"] = next(iter(scales)) if len(scales) == 1 else "mixed"
            return annotated
        if isinstance(value, list):
            return [VNextOrchestrator._annotate_percentile_scales(item) for item in value]
        return value

    def _purify_layer_facts_for_prompt(self, facts: Any) -> Any:
        """拍板⑤：发给 L1-L5 的 layer_facts 用净化副本，落盘 analysis_packet 不动。

        去掉预置 state 与 summary 开头的“<层>状态: <值>。”段，只保留“关键事实: …”与
        “缺口=…”部分；层的状态判断必须由层分析师自己从数据得出。
        """
        if not isinstance(facts, dict):
            return facts
        cleaned = dict(facts)
        cleaned.pop("state", None)
        summary = cleaned.get("summary")
        if isinstance(summary, str):
            # 只剥“关键事实”之前的前导段（状态句）；没有“关键事实”时才按状态句正则剥，
            # 避免 summary 后段出现“状态: X。”时把关键事实一并误删。
            if "关键事实" in summary:
                cleaned["summary"] = summary[summary.index("关键事实"):]
            else:
                cleaned["summary"] = re.sub(r"^.*?状态: [^。]*。", "", summary, count=1)
        return cleaned

    def _build_layer_input_policy(self, layer: str) -> Dict[str, Any]:
        layer = layer.upper()
        return {
            "schema_version": "layer_runtime_input_policy_v1",
            "layer": layer,
            "allowed_runtime_inputs": [
                f"context_brief.layer_highlights.{layer}",
                f"facts_by_layer.{layer}",
                f"raw_data.{layer}",
                f"manual_overrides.metrics filtered to raw_data.{layer} function_id values",
                "ObjectCanon and same-layer IndicatorCanon as static rules only",
            ],
            "forbidden_runtime_inputs": [
                "facts_by_layer.other_layers",
                "raw_data.other_layers",
                "candidate_cross_layer_links",
                "context_brief.apparent_cross_layer_signals",
                "event_refs",
                "news_layer_analysis",
                "event_narrative_ledger",
                "event_mechanism_report",
                "integrated_synthesis_report",
                "bridge_memos",
                "synthesis_packet",
                "thesis_draft",
                "critique",
                "risk_boundary_report",
                "analysis_revised",
                "final_adjudication",
                "investigation_reports",
                "post_run_reflection_library",
            ],
            "no_backflow_rule": (
                "InvestigationReport, integrated reports, Bridge, Thesis, Risk, Reviser, "
                "and Final artifacts must not rewrite or be injected into L1-L5 layer cards."
            ),
            "event_evidence_rule": (
                "Events, news, browser output, and sidecars are event/background material only "
                "unless upgraded by a formal data-source path; they must not become L1-L5 evidence_ref."
            ),
        }

    def _build_runtime_boundary_manifest(self) -> Dict[str, Any]:
        return {
            "schema_version": "runtime_boundary_manifest_v1",
            "purpose": "Stage 0 audit artifact; not injected into L1-L5 prompts.",
            "fixed_chain": [
                "L1-L5 layer analysts",
                "Bridge",
                "SynthesisPacket",
                "Thesis",
                "Critic",
                "Risk",
                "SchemaGuard",
                "Reviser",
                "Final",
                "ReaderExit(UserDecisionProfile + GoldenPitChecklist)",
            ],
            "layer_input_policies": {
                layer: self._build_layer_input_policy(layer)
                for layer in ["L1", "L2", "L3", "L4", "L5"]
            },
            "no_backflow_rule": (
                "Integrated reports, event reports, future InvestigationReport artifacts, "
                "Bridge, Thesis, Risk, Reviser, Final, UserDecisionProfile, GoldenPitChecklist, "
                "and post-run reflection artifacts "
                "must not rewrite or be injected into L1-L5 layer cards."
            ),
            "reader_exit_boundary": (
                "UserDecisionProfile and golden_pit_checklist.json are reader-exit translation artifacts only. "
                "They are generated after Final/ClaimLedger and must not enter L1-L5, Bridge, Thesis, Critic, "
                "Risk, Reviser, Final, or hypothesis competition prompts."
            ),
            "evidence_boundary": (
                "event_refs, news, browser output, sidecars, and future investigation outputs "
                "are not L1-L5 evidence_ref unless promoted through a formal data-source path."
            ),
            "prompt_noise_boundary": (
                "This manifest is stored as an artifact for audit; L1-L5 prompts receive only "
                "their layer-local context, facts, raw data, and filtered manual overrides."
            ),
        }

    def _build_feedback_contract_manifest(self) -> Dict[str, Any]:
        runtime_budget = AgentBudget(max_tool_calls=1, max_minutes=1, max_source_refs=3)
        router = InquiryRouter(max_agent_specs=3, default_budget=runtime_budget)
        return {
            "schema_version": "feedback_contract_manifest_v1",
            "purpose": "Stage 1 audit artifact; defines controlled inquiry messages, task sheets, and investigation reports.",
            "message_contract": {
                "contract": "InquiryMessage",
                "message_types": [
                    "observation_inquiry",
                    "event_challenge",
                    "adjudication_gap",
                    "evidence_upgrade_request",
                ],
                "required_fields": [
                    "message_id",
                    "message_type",
                    "sender_stage",
                    "target_stage",
                    "trigger",
                    "question",
                    "allowed_context_refs",
                    "forbidden_context_refs",
                    "effective_date",
                ],
            },
            "agent_spec_contract": {
                "contract": "AgentSpec",
                "required_fields": [
                    "agent_id",
                    "originating_message_id",
                    "research_question",
                    "allowed_context_refs",
                    "forbidden_context_refs",
                    "allowed_tools",
                    "budget",
                    "stop_conditions",
                    "success_criteria",
                    "required_output",
                ],
                "budget_visible": True,
                "stop_conditions_required": True,
            },
            "investigation_report_contract": {
                "contract": "InvestigationReport",
                "required_fields": router.policy_manifest()["required_investigation_output_fields"],
                "minimal_evidence_fields": [
                    "evidence_refs",
                    "counter_evidence_refs",
                    "claims_supported",
                    "claims_challenged",
                    "cannot_establish",
                    "source_authority",
                ],
            },
            "router_policy": router.policy_manifest(),
            "runtime_budget": runtime_budget.model_dump(mode="json"),
            "no_backflow_rule": (
                "InquiryMessage, AgentSpec, and InvestigationReport are feedback artifacts. "
                "They may be audited or consumed by later Bridge/integrated synthesis stages, "
                "but must not rewrite or be injected into L1-L5 layer cards."
            ),
        }

    def _build_initial_inquiry_router_output(self) -> Dict[str, Any]:
        return InquiryRouter(max_agent_specs=3).route([]).model_dump(mode="json")

    def _effective_date(self, packet: AnalysisPacket) -> str:
        meta = packet.meta if isinstance(packet.meta, dict) else {}
        return str(meta.get("data_date") or meta.get("backtest_date") or meta.get("timestamp_utc") or _utc_now().date().isoformat())

    def _load_stage_model_routing(self) -> Dict[str, Any]:
        path = Path(__file__).resolve().parents[2] / "config" / "stage_model_routing.json"
        payload: Optional[Dict[str, Any]] = None
        if path.exists():
            try:
                loaded = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    payload = loaded
            except Exception as exc:
                logger.warning("Failed to load stage model routing from %s: %s", path, exc)
        if payload is None:
            payload = {
                "schema_version": "stage_model_routing_v2_default",
                "modes": {
                    "default": {
                        "stage_preferences": {
                            "counter_thesis": ["deepseek-v4-pro", "deepseek-v4-flash"],
                            "thesis": ["deepseek-v4-pro", "deepseek-v4-flash"],
                            "reviser": ["deepseek-v4-pro", "deepseek-v4-flash"],
                            "final": ["deepseek-v4-pro", "deepseek-v4-flash"],
                            "event_card_interpreter": ["deepseek-v4-flash", "deepseek-v4-pro"],
                            "event_section_summary": ["deepseek-v4-flash", "deepseek-v4-pro"],
                        }
                    },
                    "all_flash": {
                        "stage_preferences": {
                            "counter_thesis": ["deepseek-v4-flash", "deepseek-v4-pro"],
                            "thesis": ["deepseek-v4-flash", "deepseek-v4-pro"],
                            "reviser": ["deepseek-v4-flash", "deepseek-v4-pro"],
                            "final": ["deepseek-v4-flash", "deepseek-v4-pro"],
                            "event_card_interpreter": ["deepseek-v4-flash", "deepseek-v4-pro"],
                            "event_section_summary": ["deepseek-v4-flash", "deepseek-v4-pro"],
                        }
                    },
                },
            }
        # 多模式解析：优先取 modes.<mode>.stage_preferences；旧版单层
        # stage_preferences 结构（mode 不存在或未配置）时保持向后兼容。
        modes = payload.get("modes") if isinstance(payload.get("modes"), dict) else {}
        mode = self.model_mode or str(payload.get("mode") or "default")
        mode_entry = modes.get(mode) if isinstance(modes.get(mode), dict) else None
        if mode_entry and isinstance(mode_entry.get("stage_preferences"), dict):
            resolved = dict(payload)
            resolved["stage_preferences"] = mode_entry["stage_preferences"]
        else:
            resolved = dict(payload)
        resolved["active_mode"] = mode if mode in modes else "default"
        resolved["schema_version"] = str(resolved.get("schema_version") or "stage_model_routing_v2")
        return resolved

    def _preferred_models_for_stage(self, stage_key: str) -> List[str]:
        preferences = self.stage_model_routing.get("stage_preferences", {})
        raw = preferences.get(stage_key, []) if isinstance(preferences, dict) else []
        ordered: List[str] = []
        for model_key in raw:
            if model_key in self.available_models and model_key not in ordered:
                ordered.append(model_key)
        return ordered

    def _stable_inquiry_id(self, message_type: InquiryMessageType, parts: List[Any]) -> str:
        seed = "|".join(str(part or "") for part in [message_type.value] + parts)
        return f"inq_{hashlib.sha1(seed.encode('utf-8')).hexdigest()[:12]}"

    def _feedback_forbidden_refs(self) -> List[str]:
        return [
            "layer_cards.other_layers_runtime_data",
            "thesis_draft.json",
            "critique.json",
            "risk_boundary_report.json",
            "analysis_revised.json",
            "final_adjudication.json",
            "post_run_reflection_library.json",
        ]

    def _build_feedback_inquiry_messages(
        self,
        packet: AnalysisPacket,
        layer_cards: List[LayerCard],
        bridge_v1: BridgeMemo,
    ) -> List[InquiryMessage]:
        effective_date = self._effective_date(packet)
        forbidden_refs = self._feedback_forbidden_refs()
        messages: List[InquiryMessage] = []

        for question in list(dict.fromkeys(getattr(bridge_v1, "unresolved_questions", []) or []))[:2]:
            messages.append(
                InquiryMessage(
                    message_id=self._stable_inquiry_id(InquiryMessageType.ADJUDICATION_GAP, ["bridge_unresolved", question]),
                    message_type=InquiryMessageType.ADJUDICATION_GAP,
                    sender_stage="bridge",
                    target_stage="inquiry_router",
                    trigger="Bridge V1 unresolved_questions 暴露仍需二次核查的问题。",
                    question=str(question),
                    allowed_context_refs=["bridge_memos/bridge_0.json", "synthesis_packet.pending"],
                    forbidden_context_refs=forbidden_refs,
                    effective_date=effective_date,
                )
            )

        principal = getattr(bridge_v1, "principal_contradiction", None)
        principal_dict = _model_dump(principal) if principal is not None else {}
        principal_needs_review = (
            not principal_dict
            or not principal_dict.get("evidence_refs")
            or str(principal_dict.get("price_reflection") or "").lower() in {"", "unclear", "unknown"}
            or "principal_contradiction_derived_by_code" in (getattr(bridge_v1, "normalization_notes", []) or [])
        )
        if principal_needs_review:
            messages.append(
                InquiryMessage(
                    message_id=self._stable_inquiry_id(InquiryMessageType.ADJUDICATION_GAP, ["principal_gap", principal_dict.get("contradiction_id")]),
                    message_type=InquiryMessageType.ADJUDICATION_GAP,
                    sender_stage="bridge",
                    target_stage="inquiry_router",
                    trigger="Bridge V1 的主要矛盾、证据或价格反映仍有缺口。",
                    question="主要矛盾是否有足够证据支撑？价格反映判断是否需要保留为未解决？",
                    allowed_context_refs=["bridge_memos/bridge_0.json"],
                    forbidden_context_refs=forbidden_refs,
                    effective_date=effective_date,
                )
            )

        messages.extend(self._build_event_challenge_messages(effective_date, forbidden_refs))
        messages.extend(self._build_observation_inquiry_messages(packet, layer_cards, effective_date, forbidden_refs))

        deduped: List[InquiryMessage] = []
        seen = set()
        for message in messages:
            if message.message_id in seen:
                continue
            seen.add(message.message_id)
            deduped.append(message)
        self._save_json(
            "inquiry_messages.json",
            {"schema_version": "inquiry_messages_v1", "messages": [_model_dump(message) for message in deduped]},
        )
        return deduped

    def _build_event_challenge_messages(
        self,
        effective_date: str,
        forbidden_refs: List[str],
    ) -> List[InquiryMessage]:
        questions_path = self.output_dir / "cross_layer_questions.json"
        summary_path = self.output_dir / "event_layer_summary.json"
        questions_payload = self._load_local_json(questions_path, {})
        raw_questions = _as_list(questions_payload.get("questions")) if isinstance(questions_payload, dict) else []
        messages: List[InquiryMessage] = []
        for question in raw_questions:
            if not isinstance(question, dict):
                continue
            if question.get("direction") != "event_to_data":
                continue
            if str(question.get("status") or "open") not in {"open", "insufficient_data"}:
                continue
            question_text = str(question.get("question") or "").strip()
            if not question_text:
                continue
            messages.append(
                InquiryMessage(
                    message_id=self._stable_inquiry_id(InquiryMessageType.EVENT_CHALLENGE, [question.get("question_id"), question_text]),
                    message_type=InquiryMessageType.EVENT_CHALLENGE,
                    sender_stage="L2",
                    target_stage="integrated_synthesis",
                    trigger=str(question.get("why_it_matters") or "L2 事件账本提出需要数据层压力测试的开放问题。"),
                    question=question_text,
                    allowed_context_refs=[
                        "cross_layer_questions.json",
                        "event_layer_summary.json",
                        "event_mechanism_report.json",
                        "bridge_memos/bridge_0.json",
                    ],
                    forbidden_context_refs=forbidden_refs,
                    effective_date=effective_date,
                    event_refs=_as_list(question.get("event_refs")),
                )
            )
        if messages or not summary_path.exists():
            return messages[:2]

        rejection = {
            "schema_version": "event_challenge_rejections_v1",
            "generated_at": _utc_now().isoformat(),
            "status": "rejected",
            "reason": "event_layer_present_but_no_open_event_to_data_questions",
            "trigger": "L2 事件层存在，但没有可转成 event_challenge 的开放问题。",
            "source_refs": ["event_layer_summary.json", "cross_layer_questions.json"],
        }
        self._save_json("event_challenge_rejections.json", rejection)
        return []

    def _build_observation_inquiry_messages(
        self,
        packet: AnalysisPacket,
        layer_cards: List[LayerCard],
        effective_date: str,
        forbidden_refs: List[str],
    ) -> List[InquiryMessage]:
        messages: List[InquiryMessage] = []
        for card in layer_cards:
            layer_label = str(_enum_value(card.layer))
            quality = getattr(card, "quality_self_check", None)
            missing = list(getattr(quality, "missing_or_weak_indicators", []) or []) if quality else []
            flags = list(getattr(card, "risk_flags", []) or [])
            combined = [str(item) for item in missing + flags if str(item).strip()]
            anomaly_text = next(
                (
                    item
                    for item in combined
                    if any(token in item.lower() for token in ["missing", "weak", "缺", "不足", "data", "异常", "breadth", "广度"])
                ),
                "",
            )
            if not anomaly_text:
                continue
            messages.append(
                InquiryMessage(
                    message_id=self._stable_inquiry_id(InquiryMessageType.OBSERVATION_INQUIRY, [layer_label, anomaly_text]),
                    message_type=InquiryMessageType.OBSERVATION_INQUIRY,
                    sender_stage=layer_label,
                    target_stage="L2",
                    trigger=f"{layer_label} 发现数据缺口或异常：{anomaly_text}",
                    question=f"{layer_label} 的数据缺口或异常是否有可见语境、历史相似背景或反证需要保留？",
                    allowed_context_refs=[f"layer_cards/{layer_label}.json", "bridge_memos/bridge_0.json"],
                    forbidden_context_refs=forbidden_refs,
                    effective_date=effective_date,
                )
            )
            break
        return messages[:1]

    @staticmethod
    def _event_ref_token(value: Any) -> str:
        text = str(value or "").strip()
        return text.split(":", 1)[-1] if text else ""

    def _select_event_card_candidates(
        self,
        *,
        effective_date: str,
        feedback_messages: List[InquiryMessage],
    ) -> List[Dict[str, Any]]:
        ledger = self._load_local_json(self.output_dir / "news_event_ledger.json", {})
        mechanism = self._load_local_json(self.output_dir / "event_mechanism_report.json", {})
        events = [item for item in _as_list(ledger.get("events")) if isinstance(item, dict)]

        mainline_tokens: set[str] = set()
        for mainline in _as_list(mechanism.get("mainlines")):
            if not isinstance(mainline, dict) or str(mainline.get("mainline_id")) == "other_watchlist":
                continue
            mainline_tokens.update(
                self._event_ref_token(ref)
                for ref in _as_list(mainline.get("news_card_ids"))
                if self._event_ref_token(ref)
            )

        inquiry_tokens: set[str] = set()
        for message in feedback_messages:
            if _enum_value(getattr(message, "message_type", "")) not in {
                InquiryMessageType.EVENT_CHALLENGE.value,
                InquiryMessageType.OBSERVATION_INQUIRY.value,
            }:
                continue
            inquiry_tokens.update(
                self._event_ref_token(ref)
                for ref in _as_list(getattr(message, "event_refs", []))
                if self._event_ref_token(ref)
            )

        selected: List[Dict[str, Any]] = []
        for event in events:
            event_token = self._event_ref_token(event.get("event_id") or event.get("dedupe_id"))
            dedupe_token = self._event_ref_token(event.get("dedupe_id"))
            tokens = {token for token in (event_token, dedupe_token) if token}
            reasons: List[str] = []
            if tokens & mainline_tokens:
                reasons.append("mainline")
            if tokens & inquiry_tokens:
                reasons.append("inquiry_reference")
            if (
                str(event.get("event_type") or "") == "official_calendar"
                and str(event.get("event_date") or "") == str(effective_date)[:10]
            ):
                reasons.append("official_calendar_landing")
            if reasons:
                selected.append({**event, "trigger_reasons": reasons})

        priority = {"mainline": 0, "inquiry_reference": 1, "official_calendar_landing": 2}
        return sorted(
            selected,
            key=lambda event: min(priority[reason] for reason in event["trigger_reasons"]),
        )

    def _event_card_validation_errors(
        self,
        card: EventInterpretationCard,
        *,
        event: Dict[str, Any],
        allowed_hypothesis_ids: set[str],
    ) -> List[str]:
        errors: List[str] = []
        invalid_hypotheses = (
            set(card.supports_hypotheses) | set(card.refutes_hypotheses)
        ) - allowed_hypothesis_ids
        if invalid_hypotheses:
            errors.append(f"unknown hypothesis_id: {', '.join(sorted(invalid_hypotheses))}")

        hypothesis_text = card.mechanism_hypothesis.hypothesis.strip()

        # 2026-07-30 用户裁决：删除三条"必须怎么说"的闸门——机制假设必须以"该事件可能通过"
        # 开头、非官方来源必须含"据报道/该媒体称"、仅标题材料必须在 limitations 写
        # "未读全文，降级阅读"。
        #
        # 依据是实测：最近四次真实 run 的 28 条重试/失败报错里，这三条占 14 条（50%），
        # 且全部集中在本 stage。它们判的是措辞，措辞判不完——模型写"据投资预测报道"比
        # 词表里的"据报道"更具体，仍被判失败，属误伤合格产出。
        #
        # 更根本的是它们**多余**：这三条想保护的是"读者别把只有标题的弱来源当确凿事实"，
        # 而报告本来就由代码渲染这一行（`vnext_reporter.py` 的 event_row）：
        #     「Yahoo Finance M7 Headlines · 可靠媒体转述 · 仅标题与片段 · 降级阅读」
        # 它从 source_tier 与 raw_text_excerpt 算出，与模型措辞无关，且一条不漏——
        # 比"靠模型记得写某个词"更强。删规则不降低保证，反而去掉了误伤。
        #
        # 保留下面的方向越权检查：它是**禁止型**规则，代码无法替代（渲染标不出
        # "这句话有没有断言必涨必跌"），且在那 28 条里一次都没触发过，成本为零。
        directional_overreach = ("必然上涨", "必然下跌", "必须上涨", "必须下跌", "一定上涨", "一定下跌")
        if any(token in f"{card.interpretation} {hypothesis_text}" for token in directional_overreach):
            errors.append("event card must not claim mandatory market direction")

        material_text = f"{event.get('title') or ''} {event.get('raw_text_excerpt') or ''}"
        material_declares_alternative = bool(re.search(r"(?:\bor\b|或)", material_text, flags=re.IGNORECASE))
        fact_adds_alternative = bool(re.search(r"[（(]\s*或", card.fact_summary))
        if fact_adds_alternative and not material_declares_alternative:
            errors.append("fact_summary contains alternative classification absent from material")

        def signed_numbers(text: str) -> Dict[str, str]:
            values: Dict[str, str] = {}
            for match in re.finditer(r"(?<!\d)([+-])\s*(\d+(?:[.,]\d+)*)\s*[%％]?", text):
                magnitude = re.sub(r"[^0-9]", "", match.group(2)).lstrip("0") or "0"
                values[magnitude] = match.group(1)
            return values

        material_signed = signed_numbers(
            f"{event.get('title') or ''} {event.get('raw_text_excerpt') or ''}"
        )
        fact_signed = signed_numbers(card.fact_summary)
        reversed_magnitudes = sorted(
            magnitude
            for magnitude, sign in fact_signed.items()
            if magnitude in material_signed and material_signed[magnitude] != sign
        )
        if reversed_magnitudes:
            errors.append(
                "fact_summary reverses signed number direction: " + ", ".join(reversed_magnitudes)
            )

        return errors

    def _build_event_interpretation_cards(
        self,
        *,
        effective_date: str,
        feedback_messages: List[InquiryMessage],
        hypothesis_competition: HypothesisCompetition,
    ) -> Dict[str, Any]:
        candidates = self._select_event_card_candidates(
            effective_date=effective_date,
            feedback_messages=feedback_messages,
        )
        selected = candidates[:EVENT_INTERPRETATION_CARD_LIMIT]
        hypotheses = [
            {
                "hypothesis_id": hypothesis.hypothesis_id,
                "hypothesis_text": hypothesis.hypothesis_text,
                "status": hypothesis.status,
            }
            for hypothesis in list(hypothesis_competition.hypotheses or [])
        ]
        allowed_hypothesis_ids = {str(item["hypothesis_id"]) for item in hypotheses}
        cards: List[EventInterpretationCard] = []
        failures: List[Dict[str, Any]] = []
        for event in selected:
            event_id = str(event.get("event_id") or "")
            stage_token = re.sub(r"[^A-Za-z0-9_.-]+", "_", event_id).strip("_") or "event"
            payload = {
                "event_material": {
                    "event_id": event_id,
                    "title": event.get("title"),
                    "source": event.get("source_name"),
                    "tier": event.get("source_tier"),
                    "published_at": event.get("published_at"),
                    "event_date": event.get("event_date"),
                    "effective_date": effective_date,
                    "event_type": event.get("event_type"),
                    "entities": _as_list(event.get("symbols")),
                    "raw_text_available": bool(event.get("raw_text_available")),
                    "raw_text_excerpt": event.get("raw_text_excerpt") or "",
                    "trigger_reasons": _as_list(event.get("trigger_reasons")),
                },
                "allowed_financial_links": EVENT_FINANCIAL_LINKS,
                "competing_hypotheses": hypotheses,
                "boundary": {
                    "event_ref_only": True,
                    "must_not_become_l1_l5_evidence_ref": True,
                    "must_not_feed_back": True,
                },
            }
            try:
                card = self._run_stage(
                    stage_key="event_card_interpreter",
                    stage_name=f"event_card_interpreter.{stage_token}",
                    model_cls=EventInterpretationCard,
                    payload=payload,
                    strict_tool_schema=self._strict_tool_schema_for_stage(
                        "event_card_interpreter", EventInterpretationCard
                    ),
                    strict_tool_name="emit_event_interpretation_card",
                    validator=lambda candidate, event=event: self._event_card_validation_errors(
                        candidate,
                        event=event,
                        allowed_hypothesis_ids=allowed_hypothesis_ids,
                    ),
                )
            except Exception as exc:
                failures.append({"event_id": event_id, "error": f"{type(exc).__name__}: {str(exc)[:600]}"})
                logger.warning("Event interpretation card failed for %s: %s", event_id, exc)
                continue
            passport = EventInterpretationPassport(
                source=str(event.get("source_name") or "unknown source"),
                tier=str(event.get("source_tier") or "unknown"),
                published_at=str(event.get("published_at") or ""),
                event_date=str(event.get("event_date") or ""),
                effective_date=effective_date,
            )
            finalized_card = card.model_copy(
                update={
                    "event_id": event_id,
                    # T54 批 2（机械字段不出答卷）：event_type / entities 是采集底账字段
                    # （采集标签，配餐单 08-17 口径），由代码按底账装配——模型填错或编造
                    # 一律覆盖，模型原文留在 prompt_audit raw response 可逐字审计。
                    "event_type": str(event.get("event_type") or "uncollected"),
                    "entities": [str(symbol) for symbol in _as_list(event.get("symbols"))],
                    "passport": passport,
                }
            )
            cards.append(finalized_card)
            # T49 第二件：落盘副本带上源材料的正文摘录（逐字注入，非模型输出）；
            # 内存/模型对象保持契约纯净（EventInterpretationCard extra="forbid"）。
            card_dict = _model_dump(finalized_card)
            _inject_evidence_fields(card_dict, event)
            self._save_json(
                self.output_dir / "event_interpretation_cards" / f"{stage_token}.json",
                card_dict,
            )

        events_by_id = {str(event.get("event_id") or ""): event for event in selected}
        section_summary, summary_failure = self._build_event_section_summary(
            cards, events_by_id=events_by_id, effective_date=effective_date
        )
        artifact = {
            "schema_version": "event_interpretation_cards_v1",
            "generated_at": _utc_now().isoformat(),
            "effective_date": effective_date,
            "per_run_limit": EVENT_INTERPRETATION_CARD_LIMIT,
            "candidate_count_before_limit": len(candidates),
            "selected_count": len(selected),
            "cards": [_model_dump(card) for card in cards],
            "failures": failures,
            "section_summary": section_summary,
            "section_summary_failure": summary_failure,
            "no_backflow_rule": (
                "EventInterpretationCard is layer-2/layer-3 material only; it must not rewrite or be "
                "injected into L1-L5, Bridge, Thesis, Risk, Reviser, or Final, and must not become evidence_ref."
            ),
        }
        # 写盘副本注入证据字段（IA 从文件读卡即可见正文）；内存 artifact 保持契约纯净。
        self._save_json("event_interpretation_cards.json", _with_evidence_injected_artifact(artifact, events_by_id))
        return artifact

    def _build_event_section_summary(
        self,
        cards: List["EventInterpretationCard"],
        *,
        events_by_id: Dict[str, Dict[str, Any]],
        effective_date: str,
    ) -> Tuple[Optional[Dict[str, Any]], str]:
        """Q3：外部世界章节的 governed 总结。失败宁缺毋滥，绝不回退到模板句。

        codex 审查（2026-07-20）指出：总结模型此前只拿到 fact_summary/interpretation，
        看不到 raw_text_available/limitations/发布时间，既无法履行"如实说明材料质量限制"
        的提示词要求，也没有代码兜底防止把标题材料写实、把事后信息写进历史报告。
        本版从 selected 事件底账（而非只信任模型自报的 limitations）代码级富化 payload，
        并新增两条硬校验：材料质量豁免句、日期泄漏。
        """
        if len(cards) < 2:
            return None, "insufficient_cards" if cards else "no_cards"
        compact_cards = []
        title_only_count = 0
        downgrade_required_ids: set[str] = set()
        official_source_tiers = {"official", "official_macro", "official_filing", "company_disclosure"}
        for card in cards:
            event = events_by_id.get(str(card.event_id), {})
            raw_text_available = bool(event.get("raw_text_available"))
            source_tier = str(event.get("source_tier") or (card.passport.tier if card.passport else "unknown"))
            if not raw_text_available:
                title_only_count += 1
            if not raw_text_available or source_tier not in official_source_tiers:
                downgrade_required_ids.add(str(card.event_id))
            compact_cards.append({
                "event_id": card.event_id,
                # 现成的引用串，供模型原样抄进正文——不要让它从 `[card:<event_id>]`
                # 这个占位模式自己拼，拼的时候它会把 event: 前缀当成重复而删掉。
                "citation": f"[card:{card.event_id}]",
                "fact_summary": card.fact_summary,
                "interpretation": card.interpretation,
                "financial_link": card.mechanism_hypothesis.financial_link,
                "source": card.passport.source if card.passport else "unknown source",
                "tier": source_tier,
                "published_at": event.get("published_at") or (card.passport.published_at if card.passport else ""),
                "event_date": event.get("event_date") or (card.passport.event_date if card.passport else ""),
                "raw_text_available": raw_text_available,
                "limitations": list(card.limitations)[:3],
                "needs_data_confirmation": list(card.needs_data_confirmation)[:3],
            })
        allowed_ids = {str(card.event_id) for card in cards}
        title_only_majority = title_only_count > len(cards) / 2
        payload = {
            "effective_date": effective_date,
            "event_cards": compact_cards,
            "card_count": len(compact_cards),
            "title_only_card_count": title_only_count,
            "boundary": {
                "event_material_only": True,
                "must_not_reference_l1_l5": True,
                "must_not_exceed_effective_date": effective_date,
                "must_end_with": "以上事件材料不构成主证据，判断以数据层为准。",
                "citation_rule": (
                    "引用一律原样抄 event_cards[].citation 字段的值，不要自行拼接、不要删改 id；"
                    "代码会从正文里的 [card:...] 标记自动提取，不需要另外列出引用清单。"
                ),
                "note": (
                    f"本轮 {len(compact_cards)} 张卡中有 {title_only_count} 张 raw_text_available=false"
                    "（仅标题，未读全文），引用这些卡时用'据报道/该媒体称/仅标题'等限定语说清分寸。"
                ),
            },
        }

        def _inject_cited_event_ids(parsed: Dict[str, Any]) -> Dict[str, Any]:
            # T36：cited_event_ids 不再要求模型自报——那是纯重复劳动，且正是这份
            # 重复逼出过真实的 JSON 外壳解析失败（模型正文已经内联写了
            # [card:event:xxx]，还要求它在清单里把同样的编号再抄一遍）。这里不做
            # allowed_ids 过滤：保持与正文里方括号标记逐字一致，让下面
            # `_event_section_summary_validation_errors` 的"引用越界"判据照常生效
            # ——身份合法性判定不因为改成代码导出而放松，只是不再靠模型自己数数。
            parsed["cited_event_ids"] = self._extract_cited_event_ids_from_text(
                str(parsed.get("summary_text") or "")
            )
            return parsed

        def _raw_text_fallback(raw_text: str, error_kind: str) -> Optional["EventSectionSummary"]:
            # 只接 parse_error：JSON 外壳本身没解析出来，不是"结构清楚但内容越权/
            # 不合法"（那些仍必须让原有重试与失败路径生效，不能被这道兜底悄悄放行——
            # 见 _event_section_summary_validation_errors 的 unknown ids 判据）。
            if error_kind != "parse_error":
                return None
            text = str(raw_text or "").strip()
            if not text:
                return None
            # 先把正文从坏掉的 JSON 外壳里捞出来，否则报告那一节会把花括号和字段名
            # 渲染给用户看——那是"收下了但没读懂"，不是"不拒收"（ARCHITECTURE.md 3.1c）。
            # 捞不出来时该方法原样返回，兜底仍然成立，绝不因此变成新的拒收点。
            prose = self._salvage_text_field_from_broken_json(text, "summary_text")
            # 索引仍必须过身份合法性：只收本轮真实存在的卡号，未知编号不索引、
            # 不放行——即使原始正文里写了，也不让它冒充一条可追溯引用。
            verified_ids = self._extract_cited_event_ids_from_text(prose, allowed_ids=allowed_ids)
            return EventSectionSummary(summary_text=prose, cited_event_ids=verified_ids)

        try:
            summary = self._run_stage(
                stage_key="event_section_summary",
                stage_name="event_section_summary",
                model_cls=EventSectionSummary,
                payload=payload,
                strict_tool_schema=self._strict_tool_schema_for_stage(
                    "event_section_summary", EventSectionSummary
                ),
                strict_tool_name="emit_event_section_summary",
                pre_validate_transform=_inject_cited_event_ids,
                validator=lambda candidate: self._event_section_summary_validation_errors(
                    candidate,
                    allowed_ids=allowed_ids,
                    effective_date=effective_date,
                    title_only_majority=title_only_majority,
                    downgrade_required_ids=downgrade_required_ids,
                ),
                raw_text_fallback=_raw_text_fallback,
            )
        except Exception as exc:
            logger.warning("Event section summary failed: %s", exc)
            return None, f"{type(exc).__name__}: {str(exc)[:300]}"
        summary_dict = _model_dump(summary)
        stage_record = self.stage_diagnostics.get("stages", {}).get("event_section_summary", {})
        degraded_kind = (
            stage_record.get("degraded_fallback_kind")
            if stage_record.get("status") == "degraded_fallback"
            else None
        )
        if degraded_kind:
            # 牙齿：走了降级路径必须留痕，且不得被当作可发布依据。留痕字段接在这份
            # artifact 自己身上（供渲染/复核识别"这节是兜底文本，未经索引校验的正常
            # 治理链"）；能不能发布则交给 run() 里已有的终审质量闸门
            # （_append_final_quality_note，同一机制此前已用于 reviser_degraded_
            # unrevised_thesis / counter_thesis_degraded_deterministic_fallback），
            # 不新造一套发布闸门。
            summary_dict["index_degraded"] = degraded_kind
            return summary_dict, f"degraded_fallback:{degraded_kind}"
        return summary_dict, ""

    _EVENT_CARD_CITATION_ID_PATTERN = re.compile(r"\[card:([^\[\]]+)\]")

    @staticmethod
    def _salvage_text_field_from_broken_json(raw_text: str, field_name: str) -> str:
        """从"解析不了的 JSON"里把某个文本字段的正文捞出来，只做形状处理不判语义。

        为什么需要它：降级兜底若把整段原始响应原样当正文收下，报告那一节会渲染出
        `{ "summary_text": "…", "cited_event_ids": [ … ] }` 这一堆花括号和字段名给用户看。
        那是"收下了但没读懂"——满足了"不许因形式拒收内容"的字面，却没满足它的目的
        （`ARCHITECTURE.md` 3.1c）。真实事故 run `20260731_002156`：外壳其实完好，
        只是正文里有未转义的半角双引号（`这为"AI投资…"这一竞争假说`）把 JSON 从第 2 行截断。

        做法与 `_extract_cited_event_ids_from_text` 同源：正则找形状（键名、引号、下一个
        键的起点），不理解内容。捞不出来就原样返回入参——**任何情况下都不抛错、不返回空**，
        否则这道兜底自己就变成了新的拒收点。
        """
        text = str(raw_text or "")
        opening = re.search(r'"%s"\s*:\s*"' % re.escape(field_name), text)
        if not opening:
            return text
        body = text[opening.end():]
        # 正文结束于"下一个顶层键的起点"；没有下一个键时结束于对象收尾的 `"}`。
        next_key = re.search(r'"\s*,\s*"[A-Za-z_][A-Za-z0-9_]*"\s*:', body)
        if next_key:
            body = body[: next_key.start()]
        else:
            body = re.sub(r'"\s*\}\s*$', "", body)
        if not body.strip():
            return text
        # 还原标准 JSON 转义（顺序要紧：先换行后引号，最后反斜杠，避免二次转义）
        for escaped, plain in (("\\n", "\n"), ("\\t", "\t"), ('\\"', '"'), ("\\\\", "\\")):
            body = body.replace(escaped, plain)
        return body.strip()

    @classmethod
    def _extract_cited_event_ids_from_text(
        cls,
        text: str,
        allowed_ids: Optional[set] = None,
    ) -> List[str]:
        """从正文里的 `[card:<event_id>]` 内联标记代码导出引用清单，去重、保序。

        风格对齐 `_reasoned_verdict_bracket_groups` / `_annotate_reasoned_verdict_refs`
        （见下方两个方法）：只做形状识别（正则找方括号标记），不猜语义。

        `allowed_ids=None`（默认）：不过滤，原样返回正文里出现的每个编号——
        提供给 `_run_stage` 的 `pre_validate_transform` 用，让下游
        `_event_section_summary_validation_errors` 的"引用越界"判据仍能看到未过滤
        的清单、照常拒绝非法编号并触发重试；这是"身份比对不因为改成代码导出而
        放松"的关键点，不能在这一步偷偷把非法编号滤掉。

        `allowed_ids` 给定时：只保留确实在本轮事件卡范围内的编号——供降级兜底路径
        （JSON 解析失败、绕过了上面那条重试链）使用，防止兜底文本里出现的编号
        未经身份校验就被当成合法索引收下。
        """
        seen: List[str] = []
        for raw_id in cls._EVENT_CARD_CITATION_ID_PATTERN.findall(text or ""):
            candidate_id = raw_id.strip()
            if not candidate_id or candidate_id in seen:
                continue
            if allowed_ids is not None and candidate_id not in allowed_ids:
                continue
            seen.append(candidate_id)
        return seen

    _HINDSIGHT_OR_CAUSAL_PATTERNS = (
        r"(?:后来|随后|最终|事后|此后).{0,16}(?:结果|进展|显示|表明|证实|确认|证明|兑现)",
        r"(?:后来|随后|最终|事后|此后).{0,16}(?:上涨|下跌|走强|走弱|反弹|回落|上行|下行)",
        r"后续(?:结果|进展).{0,8}(?:显示|表明|证实|确认|证明|兑现)",
        r"(?:结果|进展).{0,8}(?:显示|表明|证实|确认|证明)",
        r"已经充分解释",
        r"(?:必然|确定|确实|直接|已经|已).{0,8}(?:推动|导致|造成|引发|改变|改善|恶化|压低|抬升|兑现)",
        r"(?:因为|由于).{1,40}(?:所以|因此|导致)",
    )

    @staticmethod
    def _event_section_summary_validation_errors(
        candidate: "EventSectionSummary",
        *,
        allowed_ids: set,
        effective_date: str,
        title_only_majority: bool,
        downgrade_required_ids: Optional[set] = None,
    ) -> List[str]:
        errors: List[str] = []
        text = str(candidate.summary_text or "")
        cited_in_text = set(re.findall(r"\[card:([^\[\]]+)\]", text))
        declared = {str(item).strip() for item in (candidate.cited_event_ids or []) if str(item).strip()}
        # event_id 自带 `event:` 前缀，而引用写法是 `[card:<event_id>]`——拼起来是
        # `[card:event:xxx]`，看着像重复前缀，模型会本能地去掉一层。两条规则于是互相
        # 卡死：去掉前缀则正文与清单不一致，改成两边都去前缀又落到 allowed_ids 之外
        # （真实事故：event_section_summary 连续四次 run 全灭，见 WORK_LOG）。
        # 修法不是放宽比对，而是让报错自带可执行的修法示例。
        example_id = sorted(allowed_ids)[0] if allowed_ids else "event:<id>"
        if cited_in_text != declared:
            errors.append(
                "cited_event_ids must exactly match the [card:...] citations in summary_text"
                f"；正文有而清单无: {sorted(cited_in_text - declared)[:5]}"
                f"；清单有而正文无: {sorted(declared - cited_in_text)[:5]}"
                f"；两边都必须写完整 id（含 event: 前缀），正文里写作 [card:{example_id}]"
            )
        unknown = sorted(declared - allowed_ids)
        if unknown:
            errors.append(
                f"cited_event_ids contain ids outside this run's cards: {unknown[:5]}"
                f"；本轮合法 id 形如 {example_id}，不得删去 event: 前缀"
            )
        if len(declared) < 2:
            errors.append("summary must cite at least 2 event cards")
        if len(declared) > 5:
            errors.append("summary must cite at most 5 event cards")
        if not text.rstrip().endswith("以上事件材料不构成主证据，判断以数据层为准。"):
            errors.append("summary_text must end with the fixed boundary sentence")
        if re.search(r"L[1-5]\.get_", text):
            errors.append("summary_text must not reference L1-L5 data refs")
        # 下限 100 予以保留：短于此难以对多张事件卡（含各自降级措辞）给出实质总结，
        # 是在强制内容而非任意数字。上限从 600 放宽到 1500（2026-07-26 数字规则
        # 重构）：渲染进 `<div class="prose event-summary"><p>` 普通段落，不是固定
        # 宽度展示位，原上限无下游依据；尤其是最多可引用 5 张卡、每张仅标题/非官方
        # 来源卡都要求带各自的降级措辞时，600 字经常装不下诚实的表达。
        plain = re.sub(r"\[card:[^\[\]]+\]", "", text)
        if not 100 <= len(plain) <= 1500:
            errors.append(f"summary_text length {len(plain)} outside tolerant band 100-1500")
        # 2026-07-30 用户裁决：删除"被引弱来源卡必须在同句带降级措辞"这条闸门。
        #
        # 它先后有过两个实现，都在真实 run 上误伤了合格产出：扫写死的词表（0729 误伤
        # "据投资预测报道"）、改成模型自报原文再逐字比对（0730 误伤"另一标题显示"，
        # 该站两次尝试用尽而 failed）。两次危害相同——拦住了本该通过的输出。
        #
        # 根本原因是它多余：报告里每条事件本来就由代码渲染
        #     「Yahoo Finance M7 Headlines · 可靠媒体转述 · 仅标题与片段 · 降级阅读」
        # （`vnext_reporter.py` 的 event_row，取自 source_tier 与 raw_text_excerpt），
        # 与模型措辞无关且一条不漏。读者要的保护已经在了，不需要再逼模型写某个词。
        #
        # `downgrade_required_ids` 参数予以保留：调用方仍在计算它，且它是"哪些卡属于弱
        # 来源"的唯一真源，将来若要做离线抽样复核仍需它。
        # 无日期的“后来已证实”和确定性因果同样属于事后信息/新闻越权，不能靠避开 ISO 日期绕过。
        semantic_text = re.sub(r"\s+", " ", text)
        for pattern in VNextOrchestrator._HINDSIGHT_OR_CAUSAL_PATTERNS:
            if re.search(pattern, semantic_text):
                errors.append("summary_text contains hindsight or deterministic causal language")
                break
        # codex P1：禁止把 effective_date 之后的日期写进历史总结（防止事后信息回流）。
        if effective_date:
            try:
                effective_day = datetime.strptime(str(effective_date)[:10], "%Y-%m-%d").date()
            except ValueError:
                errors.append(f"effective_date is not a valid ISO date: {effective_date}")
            else:
                date_pattern = re.compile(
                    r"(20\d{2})\s*(?:[-/.]|年)\s*(\d{1,2})\s*(?:[-/.]|月)\s*(\d{1,2})\s*日?"
                )
                for year, month, day in date_pattern.findall(text):
                    try:
                        mentioned_day = datetime(int(year), int(month), int(day)).date()
                    except ValueError:
                        errors.append(f"summary_text contains an invalid date: {year}-{month}-{day}")
                        break
                    if mentioned_day > effective_day:
                        errors.append(
                            f"summary_text contains a date ({mentioned_day.isoformat()}) "
                            f"beyond effective_date ({effective_day.isoformat()})"
                        )
                        break
        return errors

    def _route_feedback_inquiries(self, messages: List[InquiryMessage]) -> InquiryRouterOutput:
        router = InquiryRouter(
            max_agent_specs=3,
            default_budget=AgentBudget(max_tool_calls=1, max_minutes=1, max_source_refs=3),
        )
        router_output = router.route(messages)
        self._save_json("inquiry_router_output.json", router_output)
        self._save_json(
            "feedback_loop_manifest.json",
            {
                "schema_version": "feedback_loop_manifest_v1",
                "generated_at": _utc_now().isoformat(),
                "phase": "stage_2_minimal_feedback_loop",
                "max_agent_specs": 3,
                "message_count": len(messages),
                "accepted_agent_specs": len(router_output.agent_specs),
                "rejected_messages": len(router_output.rejected_messages),
                "budget_enforced": all(spec.budget.max_tool_calls <= 1 for spec in router_output.agent_specs),
                "no_backflow_rule": "InvestigationReport and Bridge V2 are downstream artifacts; they must not rewrite L1-L5 layer cards.",
            },
        )
        return router_output

    def _run_controlled_investigations(self, router_output: InquiryRouterOutput) -> List[InvestigationReport]:
        message_by_id = {message.message_id: message for message in router_output.input_messages}
        reports: List[InvestigationReport] = []
        for spec in router_output.agent_specs:
            message = message_by_id.get(spec.originating_message_id)
            if message is None:
                continue
            report = self._build_investigation_report(spec, message)
            reports.append(report)
            report_path = self.investigation_reports_dir / f"{report.investigation_id}.json"
            self._save_json(report_path, report)
        return reports

    def _build_investigation_report(self, spec: Any, message: InquiryMessage) -> InvestigationReport:
        investigation_id = f"inv_{hashlib.sha1(spec.agent_id.encode('utf-8')).hexdigest()[:12]}"
        forbidden_refs = set(spec.forbidden_context_refs) | set(message.forbidden_context_refs)
        forbidden_paths = {(self.output_dir / ref).resolve() for ref in forbidden_refs}
        requested_forbidden = [
            ref
            for ref in spec.allowed_context_refs
            if ref in forbidden_refs or (self.output_dir / ref).resolve() in forbidden_paths
        ]
        if requested_forbidden:
            raise ValueError(f"forbidden_context_ref: {', '.join(requested_forbidden)}")

        llm_enabled = os.getenv("CONTROLLED_INVESTIGATION_LLM_ENABLED", "1").strip().lower() not in {
            "0",
            "false",
            "no",
            "off",
        }
        assembled_refs: List[str] = []
        context_notes = self._read_allowed_context_notes(
            spec.allowed_context_refs,
            spec.budget.max_source_refs,
            question=message.question,
            assembled_refs=assembled_refs,
            include_status_notes=not llm_enabled,
        )
        if not llm_enabled:
            return self._build_stub_investigation_report(
                spec,
                message,
                investigation_id=investigation_id,
                context_notes=context_notes,
            )

        base_prompt = self._load_prompt("controlled_investigation")
        materials_text = "\n\n".join(context_notes) if context_notes else "（无可读材料）"
        required_fields = {
            "finding",
            "claims_supported",
            "claims_challenged",
            "counter_evidence_refs",
            "cannot_establish",
            "confidence",
            "limits",
        }
        list_fields = required_fields - {"finding", "confidence"}
        last_error = ""
        allowed_refs = list(assembled_refs)
        for attempt in range(1, 3):
            retry_instruction = (
                "\n\n上一次输出未通过 JSON/合约校验。请重新输出完整 JSON，不要省略任何字段。"
                f"校验错误：{last_error[:600]}"
                if attempt == 2
                else ""
            )
            prompt = (
                f"{base_prompt}\n\n调查问题：\n{message.question}"
                f"\n\n允许材料（只能依据以下内容）：\n{materials_text}"
                "\n\n材料编号纪律（合约会逐项校验）：finding、claims_supported、claims_challenged、"
                "cannot_establish 和 counter_evidence_refs 的每一项都必须原样写出至少一个可用的"
                " [M#] 编号；counter_evidence_refs 如需同时保留材料内的证据 ID，写成“[M#] 证据ID”。"
                f"{retry_instruction}"
            )
            audit_prefix = f"{investigation_id}.attempt_{attempt}"
            self._save_prompt_audit_text(
                "controlled_investigation",
                f"{audit_prefix}.prompt.txt",
                prompt,
            )
            try:
                response = self.llm_engine.call_with_fallback(
                    prompt,
                    stage_name="controlled_investigation",
                )
                self._save_prompt_audit_text(
                    "controlled_investigation",
                    f"{audit_prefix}.response.txt",
                    str(response),
                )
                payload = self.llm_engine.extract_json(response, "controlled_investigation")
                if not isinstance(payload, dict):
                    raise ValueError("controlled investigation output must be a JSON object")
                missing = sorted(required_fields - set(payload))
                if missing:
                    raise ValueError(f"missing required fields: {', '.join(missing)}")
                for field in list_fields:
                    if isinstance(payload.get(field), str):
                        payload[field] = [payload[field]]
                for field in ("claims_supported", "claims_challenged"):
                    normalized_claims: List[Any] = []
                    for item in payload.get(field, []):
                        if isinstance(item, dict) and isinstance(item.get("claim"), str):
                            material_ref = item.get("material_ref") or item.get("ref")
                            if isinstance(material_ref, str) and material_ref.strip():
                                normalized_claims.append(f"{item['claim']} {material_ref}".strip())
                            else:
                                normalized_claims.append(item["claim"])
                        else:
                            normalized_claims.append(item)
                    payload[field] = normalized_claims
                invalid_lists = sorted(field for field in list_fields if not isinstance(payload.get(field), list))
                if invalid_lists:
                    raise ValueError(f"fields must be lists: {', '.join(invalid_lists)}")
                citation_normalizations = self._normalize_single_material_citations(
                    payload,
                    len(context_notes),
                )
                citation_normalizations.extend(
                    self._normalize_finding_from_explicit_citations(payload)
                )
                citation_normalizations.extend(
                    self._normalize_cannot_establish_absence_scope(
                        payload,
                        len(context_notes),
                    )
                )
                cited_material_indexes = self._validate_investigation_material_citations(
                    payload,
                    len(context_notes),
                )
                self._validate_investigation_limits_against_materials(payload, materials_text)
                cited_refs = [allowed_refs[index - 1] for index in cited_material_indexes]
                report_payload = {
                    **payload,
                    "investigation_id": investigation_id,
                    "originating_agent_id": spec.agent_id,
                    "is_deterministic_stub": False,
                    "evidence_refs": cited_refs,
                    "limits": list(payload["limits"])
                    + ["zero_external_tools", "no_backflow_to_l1_l5"],
                    "source_authority": self._investigation_source_authority(
                        cited_refs,
                        message.question,
                    ),
                    "effective_date": message.effective_date,
                }
                if citation_normalizations:
                    report_payload["normalization_notes"] = citation_normalizations
                return InvestigationReport.model_validate(report_payload)
            except Exception as exc:
                last_error = f"{type(exc).__name__}: {exc}"
                self._save_prompt_audit_json(
                    "controlled_investigation",
                    f"{audit_prefix}.error.json",
                    {"attempt": attempt, "error": last_error},
                )
                logger.warning(
                    "Controlled investigation %s attempt %s failed: %s",
                    investigation_id,
                    attempt,
                    last_error,
                )

        stub = self._build_stub_investigation_report(
            spec,
            message,
            investigation_id=investigation_id,
            context_notes=context_notes,
        )
        return stub.model_copy(
            update={
                "limits": list(stub.limits)
                + ["llm_investigation_failed_fell_back_to_stub"],
                "llm_failure": last_error,
            }
        )

    def _build_stub_investigation_report(
        self,
        spec: Any,
        message: InquiryMessage,
        *,
        investigation_id: str,
        context_notes: List[str],
    ) -> InvestigationReport:
        message_type = message.message_type
        if message_type == InquiryMessageType.EVENT_CHALLENGE:
            finding = "本轮未执行真实调查，仅登记事件挑战缺口；事件材料仍不能升级为 L1-L5 主证据。"
            claims_challenged: List[str] = []
            cannot_establish = ["事件是否已经因果性改变 NDX 走势", "事件材料是否可直接成为 L1-L5 evidence_ref"]
            confidence = Confidence.LOW
        elif message_type == InquiryMessageType.OBSERVATION_INQUIRY:
            finding = "本轮未执行真实调查，仅登记数据异常或缺口；二次综合只能把它作为待核查限制。"
            claims_challenged = []
            cannot_establish = ["缺口背后的外部原因", "历史相似样本的胜率或收益"]
            confidence = Confidence.LOW
        else:
            finding = "本轮未执行真实调查，仅登记 Bridge 裁决缺口；现有 allowed artifacts 不能自动强化或反驳主结论。"
            claims_challenged = []
            cannot_establish = ["主要矛盾已经完全解决", "价格反映程度已经高置信确定"]
            confidence = Confidence.LOW

        allowed_refs = list(
            spec.allowed_context_refs[: spec.budget.max_source_refs or len(spec.allowed_context_refs)]
        )
        source_authority = self._investigation_source_authority(allowed_refs, message.question)
        return InvestigationReport(
            investigation_id=investigation_id,
            originating_agent_id=spec.agent_id,
            is_deterministic_stub=True,
            finding=finding,
            evidence_refs=allowed_refs,
            counter_evidence_refs=[],
            claims_supported=[],
            claims_challenged=claims_challenged,
            cannot_establish=cannot_establish,
            confidence=confidence,
            limits=[
                "stage_2_minimal_deterministic_investigation_only",
                "no_external_research_performed",
                "no_real_investigation_performed",
                "no_backflow_to_l1_l5",
                f"allowed_context_notes={len(context_notes)}",
            ],
            source_authority=source_authority,
            effective_date=message.effective_date,
        )

    def _investigation_source_authority(
        self,
        refs: List[str],
        question: str,
    ) -> List[EvidenceSourceAuthority]:
        return [
            EvidenceSourceAuthority(
                evidence_ref=ref,
                source_ref=ref,
                source_tier=self._source_tier_for_allowed_ref(ref),
                authority_note="受控调查只读取 AgentSpec.allowed_context_refs；该引用不自动升级为 L1-L5 evidence_ref。",
                supports=[question],
                limitations=["不能回写 L1-L5 layer card", "不能替代正式数据源升级流程"],
            )
            for ref in refs
        ]

    def _read_allowed_context_notes(
        self,
        refs: List[str],
        max_refs: int,
        *,
        question: str = "",
        assembled_refs: Optional[List[str]] = None,
        include_status_notes: bool = True,
    ) -> List[str]:
        notes: List[str] = []
        total_chars = 0
        for ref in refs[: max_refs or len(refs)]:
            path = (self.output_dir / ref).resolve()
            try:
                path.relative_to(self.output_dir)
            except ValueError:
                if not include_status_notes:
                    continue
                excerpt = "rejected_outside_run_dir"
                material_index = len(notes) + 1
                material = f"[M{material_index}] artifact={ref}\n{excerpt}\n[/M{material_index}]"
                notes.append(material[: min(4000, 12000 - total_chars)])
                total_chars += len(notes[-1])
                continue
            if not path.exists() or not path.is_file():
                if not include_status_notes:
                    continue
                excerpt = "artifact_not_found_or_symbolic_ref"
                material_index = len(notes) + 1
                material = f"[M{material_index}] artifact={ref}\n{excerpt}\n[/M{material_index}]"
                notes.append(material[: min(4000, 12000 - total_chars)])
                total_chars += len(notes[-1])
                continue
            try:
                raw_text = path.read_text(encoding="utf-8")
                payload = json.loads(raw_text)
            except Exception:
                if not include_status_notes:
                    continue
                excerpt = "unreadable_json"
                material_index = len(notes) + 1
                material = f"[M{material_index}] artifact={ref}\n{excerpt}\n[/M{material_index}]"
                notes.append(material[: min(4000, 12000 - total_chars)])
                total_chars += len(notes[-1])
                continue
            excerpt = raw_text
            stripped_keys: List[str] = []
            if isinstance(payload, dict):
                # 配餐单余站条目第 4 类：序列化前递归删除立场字段，调查员只看事实面。
                # 用 JSON 字段标“已剥离”而不是在 JSON 外贴注记，保证材料块始终是
                # 可解析的完整 JSON（PC-06 机器检查要求）。
                stripped_payload, stripped_keys = self._strip_material_stance_fields(payload)
                if stripped_keys:
                    stripped_payload["_stance_fields_stripped"] = True
                    stripped_payload["_stance_fields_stripped_count"] = len(stripped_keys)
                if question:
                    keywords = self._investigation_question_keywords(question)
                    ranked_blocks: List[tuple[int, int, str, Any]] = []
                    for index, (key, value) in enumerate(stripped_payload.items()):
                        searchable = f"{key} {json.dumps(value, ensure_ascii=False, default=str)}".lower()
                        score = sum(1 for keyword in keywords if keyword in searchable)
                        if score:
                            ranked_blocks.append((score, -index, str(key), value))
                    if ranked_blocks:
                        ranked_blocks.sort(reverse=True)
                        selected = {key: value for _, _, key, value in ranked_blocks}
                        if stripped_keys:
                            selected["_stance_fields_stripped"] = True
                            selected["_stance_fields_stripped_count"] = len(stripped_keys)
                        excerpt = json.dumps(selected, ensure_ascii=False, indent=2, default=str)
                    else:
                        excerpt = json.dumps(stripped_payload, ensure_ascii=False, indent=2, default=str)
                else:
                    excerpt = json.dumps(stripped_payload, ensure_ascii=False, indent=2, default=str)

            remaining = 12000 - total_chars
            if remaining <= 0:
                break
            material_index = len(notes) + 1
            prefix = f"[M{material_index}] artifact={ref}\n"
            suffix = f"\n[/M{material_index}]"
            max_excerpt_len = max(0, 4000 - len(prefix) - len(suffix))
            if len(excerpt) > max_excerpt_len:
                # 截断时发“合法的截断信封”，不发半截 JSON：preview 是字符串，
                # 信封本身可解析，模型被明确禁止据此补全未显示内容。
                # 先算信封固定开销，再定 preview 预算，使整块材料仍恰好贴住 4000 上限。
                envelope = {
                    "_material_truncated": True,
                    "artifact": ref,
                    "note": "材料 JSON 超过调查预算，已截断；完整内容在磁盘 artifact，禁止据此补全未显示内容。",
                    "preview": "",
                }
                if stripped_keys:
                    envelope["_stance_fields_stripped"] = True
                    envelope["_stance_fields_stripped_count"] = len(stripped_keys)
                overhead = len(json.dumps(envelope, ensure_ascii=False, indent=2, default=str))
                preview_budget = max(0, max_excerpt_len - overhead)
                # preview 里的引号/反斜杠会被 JSON 转义、实际长度膨胀，迭代收缩到
                # 信封序列化后确定 ≤ max_excerpt_len，绝不用切片切断 JSON。
                for _ in range(6):
                    envelope["preview"] = excerpt[:preview_budget]
                    serialized = json.dumps(envelope, ensure_ascii=False, indent=2, default=str)
                    if len(serialized) <= max_excerpt_len:
                        break
                    preview_budget = max(0, preview_budget - (len(serialized) - max_excerpt_len) - 10)
                # 用无转义安全字符把信封补齐到上限，保持每块材料恰好 4000、总额恰好 12000。
                while len(serialized) < max_excerpt_len:
                    padded = json.dumps(
                        {**envelope, "preview": envelope["preview"] + "甲"},
                        ensure_ascii=False, indent=2, default=str,
                    )
                    if len(padded) > max_excerpt_len:
                        break
                    envelope["preview"] += "甲"
                    serialized = padded
                excerpt_trimmed = serialized
            else:
                excerpt_trimmed = excerpt
            material = prefix + excerpt_trimmed + suffix
            material = material[:remaining]
            notes.append(material)
            total_chars += len(material)
            if assembled_refs is not None:
                assembled_refs.append(ref)
        return notes

    def _strip_material_stance_fields(self, value: Any) -> Tuple[Any, List[str]]:
        """递归删除材料 dict 里的立场字段，返回 (净化副本, 被剥离的键列表)。

        删除规则：仅按立场键名白名单剥离 `dominant_side` / `action_implication` /
        `action_constraint`，不按字符串内容猜测，避免误删材料里合法的仓位事实字段。
        调用方只写通用说明“已剥离立场字段”（不列键名，避免常设检查把说明本身
        误判为立场字段泄漏）。
        """
        stripped_keys: List[str] = []

        def _strip(node: Any) -> Any:
            if isinstance(node, dict):
                cleaned: Dict[str, Any] = {}
                for key, item in node.items():
                    if key in {"dominant_side", "action_implication", "action_constraint"}:
                        stripped_keys.append(key)
                        continue
                    cleaned[key] = _strip(item)
                return cleaned
            if isinstance(node, list):
                return [_strip(item) for item in node]
            return node

        return _strip(value), list(dict.fromkeys(stripped_keys))

    def _validate_investigation_material_citations(
        self,
        payload: Dict[str, Any],
        material_count: int,
    ) -> List[int]:
        valid_citations = {f"M{index}" for index in range(1, material_count + 1)}
        cited_materials: set[str] = set()

        def validate_text(label: str, text: Any) -> None:
            if not isinstance(text, str):
                raise ValueError(f"{label} must contain strings")
            citations = set(re.findall(r"\[(M\d+)\]", text))
            if not citations:
                raise ValueError(f"{label} missing [M#] material citation")
            invalid = sorted(citations - valid_citations)
            if invalid:
                raise ValueError(f"{label} cites unavailable materials: {', '.join(invalid)}")
            cited_materials.update(citations)

        validate_text("finding", payload.get("finding"))
        for field in ("claims_supported", "claims_challenged", "cannot_establish", "counter_evidence_refs"):
            for index, item in enumerate(payload.get(field, [])):
                validate_text(f"{field}[{index}]", item)
        return sorted(int(citation.removeprefix("M")) for citation in cited_materials)

    def _normalize_single_material_citations(
        self,
        payload: Dict[str, Any],
        material_count: int,
    ) -> List[str]:
        if material_count != 1:
            return []
        normalized_fields: List[str] = []

        finding = payload.get("finding")
        if isinstance(finding, str) and not re.search(r"\[M\d+\]", finding):
            payload["finding"] = f"{finding.rstrip()} [M1]"
            normalized_fields.append("finding")

        for field in ("claims_supported", "claims_challenged", "cannot_establish", "counter_evidence_refs"):
            values = payload.get(field, [])
            if not isinstance(values, list):
                continue
            for index, item in enumerate(values):
                if isinstance(item, str) and not re.search(r"\[M\d+\]", item):
                    values[index] = f"{item.rstrip()} [M1]"
                    normalized_fields.append(f"{field}[{index}]")
        if not normalized_fields:
            return []
        return [
            "single_material_citation_normalized_to_M1:" + ",".join(normalized_fields)
        ]

    def _normalize_cannot_establish_absence_scope(
        self,
        payload: Dict[str, Any],
        material_count: int,
    ) -> List[str]:
        if material_count <= 1:
            return []
        values = payload.get("cannot_establish", [])
        if not isinstance(values, list):
            return []
        scope = "".join(f"[M{index}]" for index in range(1, material_count + 1))
        normalized_indexes: List[str] = []
        for index, item in enumerate(values):
            if isinstance(item, str) and not re.search(r"\[M\d+\]", item):
                values[index] = f"{item.rstrip()} {scope}"
                normalized_indexes.append(str(index))
        if not normalized_indexes:
            return []
        return [
            "cannot_establish_absence_scope_normalized_to_all_materials:"
            + ",".join(normalized_indexes)
        ]

    def _normalize_finding_from_explicit_citations(
        self,
        payload: Dict[str, Any],
    ) -> List[str]:
        finding = payload.get("finding")
        if not isinstance(finding, str) or re.search(r"\[M\d+\]", finding):
            return []
        citations: set[str] = set()
        for field in ("claims_supported", "claims_challenged", "cannot_establish", "counter_evidence_refs"):
            for item in payload.get(field, []):
                if isinstance(item, str):
                    citations.update(re.findall(r"\[(M\d+)\]", item))
        if not citations:
            return []
        ordered = sorted(citations, key=lambda value: int(value.removeprefix("M")))
        payload["finding"] = f"{finding.rstrip()} " + "".join(f"[{citation}]" for citation in ordered)
        return [
            "finding_citations_normalized_from_explicit_output_refs:" + ",".join(ordered)
        ]

    def _validate_investigation_limits_against_materials(
        self,
        payload: Dict[str, Any],
        materials_text: str,
    ) -> None:
        has_reported_number = bool(
            re.search(
                r"\d+(?:\.\d+)?\s*(?:%|％|倍|点|分位|亿美元|万亿美元)",
                materials_text,
            )
        )
        if not has_reported_number:
            return
        limits_text = " ".join(str(item) for item in payload.get("limits", []))
        denies_reported_numbers = bool(
            re.search(
                r"(?:无|没有|未包含任何).{0,10}(?:定量|量化|数值|数字).{0,6}(?:数据|指标)",
                limits_text,
            )
            or re.search(r"(?:未分析|没有分析).{0,12}(?:具体)?(?:数字|数值)", limits_text)
            or re.search(r"(?:不包含|不含|没有|无).{0,8}实际市场数据", limits_text)
            or (
                re.search(r"(?:不包含|不含|没有|无).{0,12}(?:价格|行情|交易).{0,12}(?:数据|硬数据)", limits_text)
                and not re.search(r"(?:时间序列|结构化|连续序列)", limits_text)
            )
        )
        if denies_reported_numbers:
            raise ValueError(
                "limits overstates material absence: materials contain reported numbers; "
                "state the missing structured series or confirmation data instead"
            )

    def _investigation_question_keywords(self, question: str) -> List[str]:
        keywords = {item.lower() for item in re.findall(r"[A-Za-z0-9_]{2,}", question)}
        stopwords = {
            "材料",
            "确认",
            "什么",
            "挑战",
            "问题",
            "回答",
            "哪些",
            "是否",
            "能否",
            "无法",
        }
        for chunk in re.findall(r"[\u4e00-\u9fff]+", question):
            if len(chunk) <= 6:
                keywords.add(chunk)
            for width in range(2, min(6, len(chunk)) + 1):
                keywords.update(chunk[index : index + width] for index in range(len(chunk) - width + 1))
        return sorted((keyword for keyword in keywords if keyword not in stopwords), key=len, reverse=True)

    def _source_tier_for_allowed_ref(self, ref: str) -> str:
        if ref.startswith("event_") or ref.startswith("cross_layer_questions"):
            return "candidate_external_material"
        if ref.startswith("layer_cards/"):
            return "formal_data_source"
        return "unknown"

    def _build_bridge_v2(
        self,
        *,
        packet_model: AnalysisPacket,
        layer_cards: List[LayerCard],
        bridge_v1: BridgeMemo,
        router_output: InquiryRouterOutput,
        investigation_reports: List[InvestigationReport],
    ) -> BridgeMemo:
        effects: List[Dict[str, Any]] = []
        for report in investigation_reports:
            changed = bool(
                not getattr(report, "is_deterministic_stub", False)
                and report.claims_challenged
                and "strong_single_path_adjudication" not in report.claims_challenged
            )
            effects.append(
                {
                    "investigation_id": report.investigation_id,
                    "originating_agent_id": report.originating_agent_id,
                    "is_deterministic_stub": bool(getattr(report, "is_deterministic_stub", False)),
                    "effect_on_judgment": "downgraded_or_kept_unresolved" if changed else "stub_gap_recorded_no_judgment_change",
                    "finding": report.finding,
                    "confidence": _enum_value(report.confidence),
                    "evidence_refs": list(report.evidence_refs),
                    "cannot_establish": list(report.cannot_establish),
                }
            )

        accepted_ids = {spec.originating_message_id for spec in router_output.agent_specs}
        rejected_questions = [
            {
                "message_id": decision.message_id,
                "message_type": _enum_value(decision.message_type),
                "rejection_reason": decision.rejection_reason,
                "trigger": decision.trigger,
            }
            for decision in router_output.rejected_messages
        ]
        report_refs = [f"investigation_reports/{report.investigation_id}.json" for report in investigation_reports]
        old_principal = _model_dump(getattr(bridge_v1, "principal_contradiction", None))
        if not isinstance(old_principal, dict):
            old_principal = {}
        unresolved_questions = list(dict.fromkeys(
            list(getattr(bridge_v1, "unresolved_questions", []) or [])
            + [
                item
                for report in investigation_reports
                for item in list(report.cannot_establish)
            ]
        ))
        if old_principal:
            old_principal.setdefault("unresolved_questions", [])
            old_principal["unresolved_questions"] = list(dict.fromkeys(
                list(old_principal.get("unresolved_questions") or []) + unresolved_questions[:4]
            ))
        layers_connected = list(getattr(bridge_v1, "layers_connected", []) or [])
        if len(layers_connected) < 2:
            layers_connected = [card.layer for card in layer_cards[:2]]

        bridge_v2_payload = {
            "bridge_type": "feedback_bridge_v2",
            "layers_connected": layers_connected[:5],
            "cross_layer_claims": [],
            "conflicts": [_model_dump(item) for item in getattr(bridge_v1, "conflicts", []) or []],
            "typed_conflicts": [_model_dump(item) for item in getattr(bridge_v1, "typed_conflicts", []) or []],
            "resonance_chains": [_model_dump(item) for item in getattr(bridge_v1, "resonance_chains", []) or []],
            "transmission_paths": [_model_dump(item) for item in getattr(bridge_v1, "transmission_paths", []) or []],
            "principal_contradiction": old_principal or None,
            "secondary_contradictions": [_model_dump(item) for item in getattr(bridge_v1, "secondary_contradictions", []) or []],
            "price_reflection_map": [_model_dump(item) for item in getattr(bridge_v1, "price_reflection_map", []) or []],
            "contradiction_transformation_signals": [_model_dump(item) for item in getattr(bridge_v1, "contradiction_transformation_signals", []) or []],
            "unresolved_questions": unresolved_questions[:12],
            "implication_for_ndx": (
                "Bridge V2 已读取受控 InvestigationReport。"
                "若调查未能建立新证据，二次综合必须保留原有张力并降低强裁决倾向。"
            ),
            "key_uncertainties": list(dict.fromkeys(
                list(getattr(bridge_v1, "key_uncertainties", []) or [])
                + [item for report in investigation_reports for item in list(report.cannot_establish)]
            ))[:12],
            "event_refs": list(dict.fromkeys(getattr(bridge_v1, "event_refs", []) or [])),
            "normalization_notes": list(dict.fromkeys(
                list(getattr(bridge_v1, "normalization_notes", []) or [])
                + ["bridge_v2_deterministic_feedback_loop"]
            )),
            "investigation_effects": effects,
            "feedback_loop_summary": {
                "schema_version": "bridge_v2_feedback_summary_v1",
                "input_bridge": "bridge_memos/bridge_0.json",
                "input_messages": len(router_output.input_messages),
                "accepted_messages": sorted(accepted_ids),
                "rejected_messages": rejected_questions,
                "investigation_report_refs": report_refs,
                "changed_judgment_count": sum(1 for item in effects if item["effect_on_judgment"] == "downgraded_or_kept_unresolved"),
                "unchanged_or_unresolved_count": sum(1 for item in effects if item["effect_on_judgment"] != "downgraded_or_kept_unresolved"),
                "no_backflow_asserted": True,
            },
        }
        bridge_v2 = BridgeMemo.model_validate(bridge_v2_payload)
        self._save_json(self.bridge_dir / "bridge_v2.json", bridge_v2)
        return bridge_v2

    def _build_hypothesis_competition(
        self,
        *,
        synthesis_packet: SynthesisPacket,
        bridge_v2: BridgeMemo,
        investigation_reports: List[InvestigationReport],
        effective_date: str,
    ) -> HypothesisCompetition:
        counter_thesis = self._build_counter_thesis(
            synthesis_packet=synthesis_packet,
            bridge_v2=bridge_v2,
            investigation_reports=investigation_reports,
        )
        base_hypothesis = self._build_base_hypothesis_from_bridge(
            bridge_v2=bridge_v2,
            investigation_reports=investigation_reports,
        )
        hypotheses = [base_hypothesis] + list(counter_thesis.hypotheses)
        hypotheses = self._dedupe_hypotheses(hypotheses)

        fallback_warnings = self._competition_fallback_warnings(bridge_v2)
        # 反方(counter_thesis)降级可见度对齐 reviser：reviser 失败退回原稿时会显式打上
        # degraded_fallback 并传导进终审质量闸门（见 _append_final_quality_note 调用点），
        # 但 counter_thesis 失败退回 _build_deterministic_counter_thesis 时，此前只把
        # fallback_reason 记进 counter_thesis.json 自己的 prompt_input_audit 里，终审判决书
        # 完全看不出这次反方论证其实是模板凑数，不像 reviser 那样留下可见标记。这里把它
        # 也计入 fallback_warnings，交给下游在终审阶段同样显式标注。
        if counter_thesis.prompt_input_audit.get("fallback_reason"):
            fallback_warnings = list(dict.fromkeys(fallback_warnings + ["counter_thesis_deterministic_fallback"]))
        downgrade_records = self._build_adjudication_change_records(
            base_hypothesis=base_hypothesis,
            counter_hypotheses=counter_thesis.hypotheses,
            investigation_reports=investigation_reports,
            fallback_warnings=fallback_warnings,
            effective_date=effective_date,
        )
        leading_id = "" if downgrade_records else base_hypothesis.hypothesis_id
        retained_disputes = list(dict.fromkeys(
            list(getattr(bridge_v2, "unresolved_questions", []) or [])
            + [item for report in investigation_reports for item in list(report.cannot_establish)]
            + [record.reason for record in downgrade_records if record.reason]
        ))[:12]
        if leading_id:
            hypotheses = [
                hypothesis.model_copy(update={"status": "leading", "adjudication_reason": "当前证据未触发改判，暂列主导解释。"})
                if hypothesis.hypothesis_id == leading_id else hypothesis
                for hypothesis in hypotheses
            ]
        elif hypotheses:
            hypotheses = [
                hypothesis.model_copy(update={"status": "kept_unresolved", "adjudication_reason": "存在调查反证、证据缺口或兜底痕迹，不能形成单一路径裁决。"})
                for hypothesis in hypotheses
            ]

        competition = HypothesisCompetition(
            input_refs=["synthesis_packet.json", "bridge_memos/bridge_v2.json", "investigation_reports/*.json"],
            forbidden_context_refs=["thesis_draft.json", "analysis_revised.json", "final_adjudication.json"],
            hypotheses=hypotheses,
            leading_hypothesis_id=leading_id,
            retained_disputes=retained_disputes,
            downgrade_or_split_events=downgrade_records,
            insufficient_evidence_reason="" if len(hypotheses) >= 2 else "少于两个可竞争解释；只能保留证据不足状态。",
            fallback_warnings=fallback_warnings,
            principal_contradiction_quality=self._principal_contradiction_quality(bridge_v2),
            price_reflection_quality=self._price_reflection_quality(bridge_v2),
            adjudication_notes=[
                "Counter-Thesis 首次生成发生在 Thesis 之前，且禁止读取 thesis_draft.json。",
                "InvestigationReport 只影响假说状态、争议保留和重判记录，不回写 L1-L5。",
                "principal_contradiction / price_reflection 如有兜底痕迹，必须在裁决中降级或显式标记。",
            ],
        )
        history = AdjudicationHistory(
            effective_date=effective_date,
            records=downgrade_records
            or [
                AdjudicationChangeRecord(
                    version_id="adj_initial_v1",
                    previous_hypothesis_id="",
                    new_hypothesis_id=leading_id,
                    trigger_evidence_refs=[],
                    change_type="initial",
                    old_status="none",
                    new_status="leading" if leading_id else "insufficient_evidence",
                    reason="建立阶段 3 初始竞争裁决记录。",
                    effective_date=effective_date,
                )
            ],
            current_hypothesis_ids=[hypothesis.hypothesis_id for hypothesis in hypotheses],
        )
        self._save_json("counter_thesis.json", counter_thesis)
        counter_payload = getattr(self, "_last_counter_thesis_payload", None)
        if counter_payload is not None:
            self._record_stage_artifact(
                self.output_dir / "counter_thesis.json",
                stage_key="counter_thesis",
                stage_name="counter_thesis",
                payload=counter_payload,
                # 走了确定性兜底的反方稿是降级产物，不是"已验证"结果——续跑必须重试，
                # 不能把模板凑数稿当检查点一路带下去。
                checkpoint_reusable=not getattr(self, "_last_counter_thesis_fallback", False),
            )
        self._save_json("hypothesis_competition.json", competition)
        self._save_json("adjudication_history.json", history)
        self._save_json(
            "competition_adjudication_manifest.json",
            {
                "schema_version": "competition_adjudication_manifest_v1",
                "phase": "stage_3_minimal_competition",
                "counter_thesis_independent": "thesis_draft.json" in set(counter_thesis.forbidden_context_refs),
                "hypothesis_count": len(hypotheses),
                "leading_hypothesis_id": leading_id,
                "downgrade_or_split_count": len(downgrade_records),
                "no_backflow_rule": "Competition artifacts may be read by Thesis and governance stages, but must not rewrite L1-L5 layer cards.",
            },
        )
        return competition

    def _build_counter_thesis(
        self,
        *,
        synthesis_packet: SynthesisPacket,
        bridge_v2: BridgeMemo,
        investigation_reports: List[InvestigationReport],
    ) -> CounterThesisDraft:
        payload = self._counter_thesis_prompt_payload(
            synthesis_packet=synthesis_packet,
            bridge_v2=bridge_v2,
            investigation_reports=investigation_reports,
        )
        allowed_refs = set(synthesis_packet.evidence_index.keys())
        fallback_reason = ""
        # 断点续跑：counter_thesis 此前是唯一没有接进检查点机制的叙事站——它用
        # `_save_json` 直接落盘，manifest 里 stage_key / payload_sha256 都是 None，
        # 也没有对应的 `_load_stage_checkpoint`。后果是一条缺失引发整条级联：续跑必然
        # 重跑反方 → 竞争假说变了 → thesis 的 expected_payload 指纹对不上 → thesis
        # 检查点作废 → reviser / final 跟着全部重跑，并**静默覆盖**已经产出的产物。
        # 真实事故 run 20260728_110702：首跑那批 3 条假说的验收样本就是这样消失的，
        # 而 `--resume-run-dir` 的帮助文字写的是"verified stage checkpoints are reused"。
        # 修行为而不是修文档——帮助文字描述的才是设计意图，这里只是从没接上。
        checkpoint = self._load_stage_checkpoint(
            "counter_thesis.json",
            CounterThesisDraft,
            stage_key="counter_thesis",
            stage_name="counter_thesis",
            expected_payload=payload,
        )
        if checkpoint is not None:
            return checkpoint
        try:
            draft = self._run_stage(
                stage_key="counter_thesis",
                stage_name="counter_thesis",
                model_cls=CounterThesisDraft,
                payload=payload,
                validator=lambda candidate: self._validate_counter_thesis_draft(candidate, allowed_refs),
            )
            draft = self._normalize_counter_thesis_draft(draft, allowed_refs)
        except Exception as exc:
            logger.warning("counter_thesis LLM stage failed; using deterministic fallback: %s", exc)
            fallback_reason = str(exc)
            draft = self._build_deterministic_counter_thesis(
                synthesis_packet=synthesis_packet,
                bridge_v2=bridge_v2,
                investigation_reports=investigation_reports,
                fallback_reason=fallback_reason,
            )

        audit = self._counter_thesis_prompt_input_audit(payload)
        if fallback_reason:
            audit["fallback_reason"] = fallback_reason[:500]
        # 交给 `_run_hypothesis_competition` 在落盘后登记检查点指纹；不重算一遍 payload，
        # 避免两处构造逻辑日后各走各路（这正是本次会话反复治理的那类重复）。
        self._last_counter_thesis_payload = payload
        self._last_counter_thesis_fallback = bool(fallback_reason)
        return draft.model_copy(
            update={
                # T54 批 1（机械字段不出答卷）：schema_version / independence_boundary 是
                # 固定字面量，与 input_refs/forbidden_context_refs/prompt_input_audit 一样
                # 由代码装配——模型填错一律覆盖，模型原文留在 prompt_audit raw response。
                "schema_version": CounterThesisDraft.model_fields["schema_version"].default,
                "independence_boundary": CounterThesisDraft.model_fields["independence_boundary"].default,
                # T54 批 4（编号规范 02）：hypothesis_id 由代码发放——沿用既有
                # `_stable_hypothesis_id` 内容哈希机制（LLM 稿与确定性兜底稿同构、幂等，
                # 同文同 id，跨 run 可审计），source 恒为 counter_thesis；模型自填 id 不保留，
                # 原文留在 prompt_audit raw response。
                "hypotheses": [
                    hypothesis.model_copy(
                        update={
                            "hypothesis_id": self._stable_hypothesis_id(
                                "counter", str(hypothesis.hypothesis_text or "")
                            ),
                            "source": "counter_thesis",
                        }
                    )
                    for hypothesis in draft.hypotheses
                ],
                "input_refs": ["synthesis_packet.json", "bridge_memos/bridge_0.json", "investigation_reports/*.json"],
                "forbidden_context_refs": ["thesis_draft.json", "analysis_revised.json", "final_adjudication.json"],
                "prompt_input_audit": audit,
            }
        )

    def _counter_thesis_prompt_payload(
        self,
        *,
        synthesis_packet: SynthesisPacket,
        bridge_v2: BridgeMemo,
        investigation_reports: List[InvestigationReport],
    ) -> Dict[str, Any]:
        synthesis_payload = _model_dump(synthesis_packet)
        for key in (
            "competing_hypotheses",
            "hypothesis_competition_summary",
            "adjudication_history",
            "counter_thesis_boundary",
        ):
            synthesis_payload.pop(key, None)
        bridge_v1_summaries = [
            item
            for item in _as_list(synthesis_payload.get("bridge_summaries"))
            if isinstance(item, dict) and str(item.get("bridge_type") or "") != "feedback_bridge_v2"
        ]
        non_stub_reports = [
            _model_dump(report)
            for report in investigation_reports
            if not getattr(report, "is_deterministic_stub", False)
        ]
        return {
            "synthesis_packet_without_self_reference": synthesis_payload,
            "bridge_v1_structure": bridge_v1_summaries[:1],
            "bridge_v2_feedback_summary": _model_dump(getattr(bridge_v2, "feedback_loop_summary", {})),
            "non_stub_investigation_reports": non_stub_reports,
            "allowed_evidence_refs": sorted(synthesis_packet.evidence_index.keys()),
            "forbidden_context_refs": ["thesis_draft.json", "analysis_revised.json", "final_adjudication.json"],
            "output_contract": "CounterThesisDraft",
        }

    def _validate_counter_thesis_draft(self, draft: CounterThesisDraft, allowed_refs: set[str]) -> List[str]:
        errors: List[str] = []
        if not draft.hypotheses:
            errors.append("CounterThesisDraft.hypotheses must contain at least one hypothesis.")
        for index, hypothesis in enumerate(draft.hypotheses):
            for field_name in ("support_evidence_refs", "counter_evidence_refs", "diagnostic_evidence_refs"):
                refs = [str(ref) for ref in getattr(hypothesis, field_name, []) or []]
                invalid = [ref for ref in refs if ref not in allowed_refs]
                if invalid:
                    errors.append(f"hypotheses[{index}].{field_name} contains refs outside evidence_index: {invalid[:5]}")
            if not hypothesis.support_evidence_refs:
                errors.append(f"hypotheses[{index}].support_evidence_refs must not be empty.")
            if not hypothesis.diagnostic_evidence_refs:
                errors.append(f"hypotheses[{index}].diagnostic_evidence_refs must not be empty.")
            if not hypothesis.falsification_conditions:
                errors.append(f"hypotheses[{index}].falsification_conditions must not be empty.")
        return errors

    def _normalize_counter_thesis_draft(self, draft: CounterThesisDraft, allowed_refs: set[str]) -> CounterThesisDraft:
        hypotheses: List[CompetingHypothesis] = []
        for hypothesis in draft.hypotheses[:2]:
            support_refs = [ref for ref in hypothesis.support_evidence_refs if ref in allowed_refs]
            counter_refs = [ref for ref in hypothesis.counter_evidence_refs if ref in allowed_refs]
            diagnostic_refs = [ref for ref in hypothesis.diagnostic_evidence_refs if ref in allowed_refs]
            text = " ".join(str(hypothesis.hypothesis_text or "").split())
            if not text or not support_refs or not diagnostic_refs:
                continue
            hypotheses.append(
                hypothesis.model_copy(
                    update={
                        "hypothesis_id": hypothesis.hypothesis_id or self._stable_hypothesis_id("counter", text),
                        "hypothesis_text": text,
                        "source": "counter_thesis",
                        "support_evidence_refs": support_refs[:10],
                        "counter_evidence_refs": counter_refs[:10],
                        "diagnostic_evidence_refs": diagnostic_refs[:10],
                        "source_refs": ["synthesis_packet.json", "bridge_memos/bridge_0.json", "investigation_reports/*.json"],
                    }
                )
            )
        return draft.model_copy(
            update={
                "hypotheses": hypotheses,
                "principal_counterargument": draft.principal_counterargument or (hypotheses[0].hypothesis_text if hypotheses else ""),
            }
        )

    def _counter_thesis_prompt_input_audit(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        forbidden_refs = {"thesis_draft.json", "analysis_revised.json", "final_adjudication.json"}
        hits: List[str] = []

        def walk(value: Any, path: str = "") -> None:
            if isinstance(value, dict):
                for key, child in value.items():
                    if key in {"forbidden_context_refs", "forbidden_artifacts"}:
                        continue
                    walk(child, f"{path}.{key}" if path else str(key))
                return
            if isinstance(value, list):
                for index, child in enumerate(value):
                    walk(child, f"{path}[{index}]")
                return
            text = str(value)
            for ref in forbidden_refs:
                if ref in text:
                    hits.append(f"{path}:{ref}")

        walk(payload)
        prompt_files = sorted(str(path.relative_to(self.output_dir)) for path in self._prompt_audit_stage_dir("counter_thesis").glob("attempt_*.prompt.txt"))
        return {
            "measurement": "payload_tree_scan_excluding_forbidden_context_declarations",
            "thesis_exists_at_generation": (self.output_dir / "thesis_draft.json").exists(),
            "thesis_read": any("thesis_draft.json" in hit for hit in hits),
            "allowed_inputs_only": not hits,
            "forbidden_payload_refs": hits,
            "prompt_audit_files": prompt_files,
            "forbidden_context_refs": sorted(forbidden_refs),
        }

    def _build_deterministic_counter_thesis(
        self,
        *,
        synthesis_packet: SynthesisPacket,
        bridge_v2: BridgeMemo,
        investigation_reports: List[InvestigationReport],
        fallback_reason: str = "",
    ) -> CounterThesisDraft:
        principal = _model_dump(getattr(bridge_v2, "principal_contradiction", None))
        if not isinstance(principal, dict):
            principal = {}
        investigation_evidence = list(dict.fromkeys(
            ref
            for report in investigation_reports
            if not getattr(report, "is_deterministic_stub", False)
            for ref in list(report.evidence_refs)
            if ref in synthesis_packet.evidence_index
        ))
        unresolved = list(dict.fromkeys(
            list(getattr(bridge_v2, "unresolved_questions", []) or [])
            + [item for report in investigation_reports for item in list(report.cannot_establish)]
        ))
        base_refs = list(dict.fromkeys(
            list(principal.get("evidence_refs") or [])
            + [ref for conflict in synthesis_packet.high_severity_typed_conflicts for ref in list(conflict.evidence_refs)]
        ))
        counter_text = (
            "反方解释：现有证据更像是未解决张力和证据缺口，"
            "不足以支持把补查结果吸收到单一主线。"
        )
        if unresolved:
            counter_text += f" 关键缺口：{unresolved[0]}"
        counter_hypothesis = CompetingHypothesis(
            hypothesis_id=self._stable_hypothesis_id("counter", counter_text),
            hypothesis_text=counter_text,
            source="deterministic_fallback",
            support_evidence_refs=investigation_evidence or base_refs[:3],
            counter_evidence_refs=base_refs[:6],
            diagnostic_evidence_refs=list(dict.fromkeys(investigation_evidence + base_refs))[:8],
            cannot_explain=["如果后续正式数据源补齐并确认主要矛盾已解决，反方只能保留为历史争议。"],
            falsification_conditions=list(dict.fromkeys(
                [item for report in investigation_reports for item in list(report.cannot_establish)]
                + ["Bridge V2 原生给出充分 price_reflection_map 且关键反证被正式证据排除。"]
            ))[:8],
            confidence=Confidence.LOW if not investigation_evidence else Confidence.MEDIUM,
            status="candidate",
            adjudication_reason="反方只读取 SynthesisPacket / Bridge V2 / InvestigationReport，用于挑战单一路径吸收。",
            source_refs=["synthesis_packet.json", "bridge_memos/bridge_v2.json", "investigation_reports/*.json"],
        )
        return CounterThesisDraft(
            input_refs=["synthesis_packet.json", "bridge_memos/bridge_v2.json", "investigation_reports/*.json"],
            forbidden_context_refs=["thesis_draft.json", "analysis_revised.json", "final_adjudication.json"],
            hypotheses=[counter_hypothesis],
            principal_counterargument=counter_text,
            cannot_establish=unresolved[:10] or ["反方不能证明主线错误，只能证明证据不足或争议仍需保留。"],
            prompt_input_audit={
                "thesis_exists_at_generation": (self.output_dir / "thesis_draft.json").exists(),
                "thesis_read": False,
                "allowed_inputs_only": True,
                "fallback_reason": fallback_reason[:500],
                "forbidden_context_refs": ["thesis_draft.json", "analysis_revised.json", "final_adjudication.json"],
            },
        )

    def _build_base_hypothesis_from_bridge(
        self,
        *,
        bridge_v2: BridgeMemo,
        investigation_reports: List[InvestigationReport],
    ) -> CompetingHypothesis:
        principal = _model_dump(getattr(bridge_v2, "principal_contradiction", None))
        if not isinstance(principal, dict):
            principal = {}
        support_refs = list(dict.fromkeys(principal.get("evidence_refs") or []))
        typed_refs = [
            ref
            for conflict in getattr(bridge_v2, "typed_conflicts", []) or []
            for ref in list(getattr(conflict, "evidence_refs", []) or [])
        ]
        if not support_refs:
            support_refs = list(dict.fromkeys(typed_refs))[:8]
        counter_refs = list(dict.fromkeys(
            ref
            for report in investigation_reports
            if report.claims_challenged
            for ref in list(report.evidence_refs)
        ))
        transformation_signals = _as_list(principal.get("transformation_signals"))
        falsifiers = []
        for item in transformation_signals:
            signal = item.get("signal") if isinstance(item, dict) else item
            if str(signal or "").strip():
                falsifiers.append(str(signal))
        for conflict in getattr(bridge_v2, "typed_conflicts", []) or []:
            falsifiers.extend(str(item) for item in list(getattr(conflict, "falsifiers", []) or []))
        text = principal.get("summary") or "主线解释：Bridge V2 的主要矛盾仍是当前综合判断的基础。"
        return CompetingHypothesis(
            hypothesis_id=self._stable_hypothesis_id("base", text),
            hypothesis_text="主线解释：" + str(text).removeprefix("主线解释："),
            source="bridge_v2",
            support_evidence_refs=support_refs[:10],
            counter_evidence_refs=counter_refs[:8],
            diagnostic_evidence_refs=list(dict.fromkeys(support_refs + typed_refs + counter_refs))[:10],
            cannot_explain=list(dict.fromkeys(
                list(getattr(bridge_v2, "unresolved_questions", []) or [])
                + [item for report in investigation_reports for item in list(report.cannot_establish)]
            ))[:10],
            falsification_conditions=list(dict.fromkeys(falsifiers))[:10] or ["关键价格反映或主要矛盾证据被正式证据反驳。"],
            confidence=Confidence.MEDIUM if support_refs else Confidence.LOW,
            status="candidate",
            adjudication_reason="来自 Bridge V2 的主要矛盾候选，等待与反方假说比较。",
            source_refs=["bridge_memos/bridge_v2.json"],
        )

    def _build_adjudication_change_records(
        self,
        *,
        base_hypothesis: CompetingHypothesis,
        counter_hypotheses: List[CompetingHypothesis],
        investigation_reports: List[InvestigationReport],
        fallback_warnings: List[str],
        effective_date: str,
    ) -> List[AdjudicationChangeRecord]:
        records: List[AdjudicationChangeRecord] = []
        trigger_refs = list(dict.fromkeys(
            ref
            for report in investigation_reports
            if not getattr(report, "is_deterministic_stub", False)
            and (report.claims_challenged or report.counter_evidence_refs)
            for ref in list(report.evidence_refs)
        ))
        if trigger_refs or fallback_warnings:
            records.append(
                AdjudicationChangeRecord(
                    version_id="adj_stage3_downgrade_v1",
                    previous_hypothesis_id=base_hypothesis.hypothesis_id,
                    new_hypothesis_id=counter_hypotheses[0].hypothesis_id if counter_hypotheses else "",
                    trigger_evidence_refs=trigger_refs,
                    change_type="kept_unresolved" if trigger_refs else "downgrade",
                    old_status="candidate",
                    new_status="kept_unresolved",
                    reason=(
                        "受控调查挑战了强单一路径裁决，或 principal_contradiction / price_reflection 存在兜底痕迹；"
                        "本轮保留旧主线但降级为争议状态。"
                    ),
                    effective_date=effective_date,
                )
            )
        return records

    def _hypothesis_competition_summary(self, competition: HypothesisCompetition) -> Dict[str, Any]:
        return {
            "schema_version": competition.schema_version,
            "hypothesis_count": len(competition.hypotheses),
            "leading_hypothesis_id": competition.leading_hypothesis_id,
            "retained_disputes": list(competition.retained_disputes),
            "downgrade_or_split_count": len(competition.downgrade_or_split_events),
            "fallback_warnings": list(competition.fallback_warnings),
            "principal_contradiction_quality": competition.principal_contradiction_quality,
            "price_reflection_quality": competition.price_reflection_quality,
        }

    def _dedupe_hypotheses(self, hypotheses: List[CompetingHypothesis]) -> List[CompetingHypothesis]:
        deduped: List[CompetingHypothesis] = []
        seen = set()
        for hypothesis in hypotheses:
            if hypothesis.hypothesis_id in seen:
                continue
            seen.add(hypothesis.hypothesis_id)
            deduped.append(hypothesis)
        return deduped

    def _stable_hypothesis_id(self, prefix: str, text: str) -> str:
        return f"hyp_{prefix}_{hashlib.sha1(str(text).encode('utf-8')).hexdigest()[:10]}"

    def _competition_fallback_warnings(self, bridge: BridgeMemo) -> List[str]:
        notes = list(getattr(bridge, "normalization_notes", []) or [])
        warnings = []
        for note in notes:
            note_text = str(note)
            if "principal_contradiction" in note_text or "price_reflection" in note_text:
                warnings.append(note_text)
        if getattr(bridge, "principal_contradiction", None) is None:
            warnings.append("principal_contradiction_missing")
        if not list(getattr(bridge, "price_reflection_map", []) or []):
            warnings.append("price_reflection_map_missing")
        return list(dict.fromkeys(warnings))

    def _principal_contradiction_quality(self, bridge: BridgeMemo) -> str:
        if getattr(bridge, "principal_contradiction", None) is None:
            return "missing"
        notes = " ".join(str(item) for item in getattr(bridge, "normalization_notes", []) or [])
        return "fallback" if "principal_contradiction" in notes else "native"

    def _price_reflection_quality(self, bridge: BridgeMemo) -> str:
        if not list(getattr(bridge, "price_reflection_map", []) or []):
            return "missing"
        notes = " ".join(str(item) for item in getattr(bridge, "normalization_notes", []) or [])
        return "fallback" if "price_reflection" in notes else "native"

    def _build_evidence_registry(
        self,
        *,
        packet_model: AnalysisPacket,
        synthesis_packet: SynthesisPacket,
        investigation_reports: List[InvestigationReport],
        hypothesis_competition: HypothesisCompetition,
    ) -> EvidenceRegistry:
        effective_date = self._effective_date(packet_model)
        passports: Dict[str, EvidencePassport] = {}

        for evidence_id, item in list(synthesis_packet.evidence_index.items()):
            if "#" in evidence_id:
                continue
            raw_payload = self._raw_payload_for_evidence_ref(packet_model, evidence_id)
            quality = raw_payload.get("data_quality") if isinstance(raw_payload.get("data_quality"), dict) else {}
            permission = item.get("permission_type") if isinstance(item, dict) else ""
            issues = data_evidence_issues(raw_payload, function_id=evidence_id.split(".", 1)[-1], backtest_date=packet_model.meta.get("backtest_date") if isinstance(packet_model.meta, dict) else None) if raw_payload else {"hard_block": [], "degraded": [], "audit_warn": []}
            downgrade_rules = [issue["code"] for issue in issues.get("hard_block", []) + issues.get("degraded", []) if isinstance(issue, dict)]
            downgrade_rules.extend(
                str(rule)
                for rule in quality.get("downgrade_rules", [])
                if str(rule).strip()
            )
            item_source_tier = item.get("source_tier") if isinstance(item, dict) else ""
            source_tier = self._normalize_source_tier(
                quality.get("source_tier") or item_source_tier or raw_payload.get("source_tier")
            )
            field_authority = self._field_authority_from_payload(raw_payload)
            field_usages = self._field_authority_usages(field_authority)
            availability = str(quality.get("availability") or "").strip().lower()
            evidence_available = availability not in {"unavailable", "missing", "failed", "error"}
            observed_value = raw_payload.get("value") if "value" in raw_payload else raw_payload
            evidence_has_value = has_meaningful_observation_value(observed_value)
            mixed_field_authority = len(field_usages) > 1
            parent_usage = next(iter(field_usages), "") if len(field_usages) == 1 else ""
            parent_downgrade_rules = list(downgrade_rules)
            if not evidence_available:
                parent_downgrade_rules.append("evidence_unavailable")
            if not evidence_has_value:
                parent_downgrade_rules.append("evidence_value_missing")
            if mixed_field_authority:
                parent_downgrade_rules.append("mixed_field_authority")
            elif parent_usage and parent_usage != "core_allowed":
                parent_downgrade_rules.append(f"field_authority_{parent_usage}")
            # T35 修复（方案 A）：合法性（身份）与权限分级（MetricAuthority）是两件事，
            # 见 `_run_schema_guard` 里 valid_evidence_refs 的并集扩展。这里把父级
            # passport 的真实字段名单一并记下（不是新建字段级 passport，不触碰②的红线），
            # 供 `_verify_claim_entry` 里"合法但未登记 MetricAuthority 的字段引用"回落到
            # 父级权限时做身份比对，而不是被判成查无此证据。
            real_value_fields = sorted(
                (raw_payload.get("value") if isinstance(raw_payload.get("value"), dict) else {}).keys()
            )
            passports[evidence_id] = EvidencePassport(
                evidence_id=evidence_id,
                evidence_kind="data",
                source_ref=str(quality.get("source_name") or quality.get("provider") or evidence_id),
                source_tier=source_tier,
                permission_type=permission or None,
                authority_model={
                    "can_support": item.get("canonical_question") if isinstance(item, dict) else "",
                    "cannot_support": list(item.get("misread_guards") or []) if isinstance(item, dict) else [],
                    "requires_confirmation": list(item.get("cross_validation_targets") or []) if isinstance(item, dict) else [],
                    "field_authority": field_authority,
                    "real_value_fields": real_value_fields,
                    "field_usages": sorted(field_usages),
                    "field_usage": parent_usage,
                    "mixed_field_authority": mixed_field_authority,
                },
                downgrade_rules=list(dict.fromkeys(parent_downgrade_rules)),
                data_quality=quality,
                effective_date=str(quality.get("effective_date") or effective_date),
                verified=(
                    source_tier not in {"unknown"}
                    and not issues.get("hard_block")
                    and evidence_available
                    and evidence_has_value
                    and not mixed_field_authority
                    and parent_usage != "rejected"
                ),
                limitations=list(item.get("misread_guards") or []) if isinstance(item, dict) else [],
            )
            for field, field_rule in field_authority.items():
                if not isinstance(field_rule, dict):
                    continue
                field_ref = f"{evidence_id}#{field}"
                usage = str(field_rule.get("usage") or "").strip().lower()
                field_rules = list(downgrade_rules)
                value_payload = raw_payload.get("value") if isinstance(raw_payload.get("value"), dict) else {}
                field_has_value = has_meaningful_observation_value(value_payload.get(field))
                if not evidence_available:
                    field_rules.append("evidence_unavailable")
                if not field_has_value:
                    field_rules.append("evidence_value_missing")
                if usage and usage != "core_allowed":
                    field_rules.append(f"field_authority_{usage}")
                passports[field_ref] = EvidencePassport(
                    evidence_id=field_ref,
                    evidence_kind="data",
                    source_ref=str(quality.get("source_name") or quality.get("provider") or evidence_id),
                    source_tier=source_tier,
                    permission_type=permission or None,
                    authority_model={
                        "parent_evidence_ref": evidence_id,
                        "field_name": field,
                        "field_usage": usage,
                        "field_authority": field_rule,
                        "can_support": item.get("canonical_question") if isinstance(item, dict) else "",
                        "cannot_support": list(item.get("misread_guards") or []) if isinstance(item, dict) else [],
                    },
                    downgrade_rules=list(dict.fromkeys(field_rules)),
                    data_quality=quality,
                    effective_date=str(quality.get("effective_date") or effective_date),
                    verified=(
                        source_tier not in {"unknown"}
                        and not issues.get("hard_block")
                        and evidence_available
                        and field_has_value
                        and usage != "rejected"
                    ),
                    limitations=list(item.get("misread_guards") or []) if isinstance(item, dict) else [],
                )

            # Reader-exit predicates use exact state-variable paths. Register
            # those paths explicitly so a checklist never points at an ID that
            # the evidence registry cannot resolve. This remains downstream of
            # L1-L5 and does not alter the layer payload or prompt.
            value_payload = raw_payload.get("value") if isinstance(raw_payload.get("value"), dict) else {}
            for state_spec in STATE_VARIABLE_SPEC_BY_KEY.values():
                for state_ref in _as_list(state_spec.get("evidence_refs") or state_spec.get("evidence_ref")):
                    state_ref = str(state_ref)
                    if "#" not in state_ref or state_ref.split("#", 1)[0] != evidence_id or state_ref in passports:
                        continue
                    field_path = [part for part in state_ref.split("#", 1)[1].split(".") if part]
                    field_value: Any = value_payload
                    for part in field_path:
                        field_value = field_value.get(part) if isinstance(field_value, dict) else None
                    top_rule = field_authority.get(field_path[0], {}) if field_path else {}
                    top_rule = top_rule if isinstance(top_rule, dict) else {}
                    usage = str(top_rule.get("usage") or parent_usage or "unknown").strip().lower()
                    state_rules = list(downgrade_rules)
                    field_has_value = has_meaningful_observation_value(field_value)
                    if not evidence_available:
                        state_rules.append("evidence_unavailable")
                    if not field_has_value:
                        state_rules.append("evidence_value_missing")
                    if usage and usage != "core_allowed":
                        state_rules.append(f"field_authority_{usage}")
                    passports[state_ref] = EvidencePassport(
                        evidence_id=state_ref,
                        evidence_kind="data",
                        source_ref=str(quality.get("source_name") or quality.get("provider") or evidence_id),
                        source_tier=source_tier,
                        permission_type=permission or None,
                        authority_model={
                            "parent_evidence_ref": evidence_id,
                            "field_name": ".".join(field_path),
                            "field_usage": usage,
                            "field_authority": top_rule,
                            "state_variable_key": state_spec.get("key"),
                            "can_support": "reader_exit_state_predicate_only",
                            "cannot_support": ["must_not_backflow_to_l1_l5_bridge_or_thesis"],
                        },
                        downgrade_rules=list(dict.fromkeys(state_rules)),
                        data_quality=quality,
                        effective_date=str(quality.get("effective_date") or effective_date),
                        verified=(
                            source_tier not in {"unknown"}
                            and not issues.get("hard_block")
                            and evidence_available
                            and field_has_value
                            and usage != "rejected"
                        ),
                        limitations=["reader_exit_only", "no_backflow_to_l1_l5"],
                    )

        for event_passport in self._event_passports(effective_date):
            passports[event_passport.evidence_id] = event_passport

        for report in investigation_reports:
            evidence_id = f"investigation_reports/{report.investigation_id}.json"
            tiers = [self._normalize_source_tier(item.source_tier) for item in report.source_authority]
            source_tier = "formal_data_source" if "formal_data_source" in tiers else (tiers[0] if tiers else "unknown")
            report_downgrade_rules = ["investigation_is_downstream_no_l1_l5_backflow", *list(report.limits)]
            if getattr(report, "is_deterministic_stub", False):
                report_downgrade_rules.append("deterministic_stub_not_real_investigation")
            passports[evidence_id] = EvidencePassport(
                evidence_id=evidence_id,
                evidence_kind="investigation",
                source_ref=report.originating_agent_id,
                source_tier=source_tier,
                authority_model={
                    "can_support": list(report.claims_supported),
                    "cannot_support": list(report.cannot_establish),
                    "counter_evidence_refs": list(report.counter_evidence_refs),
                },
                downgrade_rules=report_downgrade_rules,
                effective_date=report.effective_date,
                verified=bool(
                    not getattr(report, "is_deterministic_stub", False)
                    and report.finding
                    and report.evidence_refs
                    and report.cannot_establish
                ),
                limitations=list(report.cannot_establish),
            )

        for hypothesis in hypothesis_competition.hypotheses:
            passports[hypothesis.hypothesis_id] = EvidencePassport(
                evidence_id=hypothesis.hypothesis_id,
                evidence_kind="hypothesis",
                source_ref="hypothesis_competition.json",
                source_tier="derived_inference",
                authority_model={
                    "support_evidence_refs": list(hypothesis.support_evidence_refs),
                    "counter_evidence_refs": list(hypothesis.counter_evidence_refs),
                    "diagnostic_evidence_refs": list(hypothesis.diagnostic_evidence_refs),
                    "cannot_explain": list(hypothesis.cannot_explain),
                },
                downgrade_rules=["derived_inference_cannot_replace_underlying_evidence"],
                effective_date=effective_date,
                verified=bool(hypothesis.support_evidence_refs and hypothesis.counter_evidence_refs and hypothesis.falsification_conditions),
                limitations=list(hypothesis.cannot_explain),
            )

        downgrade_summary = [
            {
                "evidence_id": passport.evidence_id,
                "reason": list(passport.downgrade_rules),
                "source_tier": passport.source_tier,
            }
            for passport in passports.values()
            if passport.downgrade_rules or not passport.verified
        ][:80]
        return EvidenceRegistry(
            effective_date=effective_date,
            passports=passports,
            source_tier_policy=self._source_tier_policy(),
            downgrade_summary=downgrade_summary,
        )

    def _raw_payload_for_evidence_ref(self, packet: AnalysisPacket, evidence_ref: str) -> Dict[str, Any]:
        if "." not in evidence_ref:
            return {}
        layer, function_id = evidence_ref.split(".", 1)
        function_id = function_id.split("#", 1)[0]
        layer_data = packet.raw_data.get(layer, {}) if isinstance(packet.raw_data, dict) else {}
        payload = layer_data.get(function_id) if isinstance(layer_data, dict) else {}
        return payload if isinstance(payload, dict) else {}

    @staticmethod
    def _field_authority_from_payload(raw_payload: Dict[str, Any]) -> Dict[str, Any]:
        value = raw_payload.get("value") if isinstance(raw_payload.get("value"), dict) else {}
        value_field_authority = value.get("MetricAuthority") if isinstance(value.get("MetricAuthority"), dict) else {}
        quality = raw_payload.get("data_quality") if isinstance(raw_payload.get("data_quality"), dict) else {}
        quality_field_authority = quality.get("metric_authority") if isinstance(quality.get("metric_authority"), dict) else {}
        usage_rank = METRIC_AUTHORITY_USAGE_RANK

        def normalized_rule(value: Any) -> Any:
            if not isinstance(value, dict):
                return value
            rule = dict(value)
            usage = str(rule.get("usage") or "audit_only").strip().lower()
            rule["usage"] = usage if usage in usage_rank else "audit_only"
            return rule

        merged: Dict[str, Any] = {}
        for field in set(value_field_authority) | set(quality_field_authority):
            value_rule = normalized_rule(value_field_authority.get(field))
            quality_rule = normalized_rule(quality_field_authority.get(field))
            if not isinstance(value_rule, dict):
                merged[field] = quality_rule
                continue
            if not isinstance(quality_rule, dict):
                merged[field] = value_rule
                continue
            rule = {**value_rule, **quality_rule}
            value_usage = str(value_rule.get("usage") or "audit_only").strip().lower()
            quality_usage = str(quality_rule.get("usage") or "audit_only").strip().lower()
            rule["usage"] = min(
                (value_usage, quality_usage),
                key=lambda usage: usage_rank.get(usage, usage_rank["audit_only"]),
            )
            rule["requires_confirmation"] = list(dict.fromkeys(
                _as_list(value_rule.get("requires_confirmation"))
                + _as_list(quality_rule.get("requires_confirmation"))
            ))
            merged[field] = rule
        return merged

    @staticmethod
    def _field_authority_usages(field_authority: Dict[str, Any]) -> set[str]:
        allowed = set(METRIC_AUTHORITY_USAGE_RANK)
        usages = set()
        for rule in field_authority.values():
            if not isinstance(rule, dict):
                continue
            usage = str(rule.get("usage") or "").strip().lower() or "unknown"
            usages.add(usage if usage in allowed else "audit_only")
        return usages

    def _normalize_source_tier(self, value: Any) -> str:
        return normalize_source_tier_for_evidence_passport(value)

    def _event_passports(self, effective_date: str) -> List[EvidencePassport]:
        payload = self._load_local_json(self.output_dir / "event_narrative_ledger.json", {})
        claims = [
            claim
            for event in _as_list(payload.get("events")) if isinstance(event, dict)
            for claim in _as_list(event.get("claims")) if isinstance(claim, dict)
        ]
        passports: List[EvidencePassport] = []
        for claim in claims:
            claim_id = str(claim.get("claim_id") or "").strip()
            if not claim_id:
                continue
            claim_type = str(claim.get("claim_type") or "")
            verified = claim_type in {"official_fact", "company_disclosure", "data_release_claim"} and bool(claim.get("source_url") or claim.get("source_name"))
            source_tier = "candidate_external_material"
            if claim_type in {"official_fact", "company_disclosure", "data_release_claim"}:
                source_tier = "official"
            passports.append(
                EvidencePassport(
                    evidence_id=claim_id,
                    evidence_kind="event",
                    source_ref=str(claim.get("source_url") or claim.get("source_name") or claim.get("source_event_id") or claim_id),
                    source_tier=source_tier,
                    authority_model={
                        "claim_type": claim_type,
                        "can_support": claim.get("what_it_can_support", ""),
                        "cannot_support": claim.get("what_it_cannot_support", ""),
                        "needs_data_confirmation": claim.get("needs_data_confirmation", True),
                    },
                    downgrade_rules=self._event_downgrade_rules(claim),
                    effective_date=effective_date,
                    verified=verified and not claim.get("needs_data_confirmation"),
                    limitations=_as_list(claim.get("counterevidence_or_limits")) + [str(claim.get("what_it_cannot_support") or "")],
                )
            )
        return passports

    def _event_downgrade_rules(self, claim: Dict[str, Any]) -> List[str]:
        rules = ["event_material_cannot_be_l1_l5_primary_evidence"]
        if claim.get("needs_data_confirmation"):
            rules.append("event_claim_requires_data_confirmation")
        if not claim.get("source_url"):
            rules.append("event_claim_missing_source_url")
        if claim.get("raw_text_available") is False:
            rules.append("event_claim_title_only_or_unread_full_text")
        if str(claim.get("claim_type") or "") in {"narrative_claim", "rumor_claim", "interpretation_claim", "view_claim"}:
            rules.append("non_official_event_claim_cannot_support_strong_market_conclusion")
        return list(dict.fromkeys(rules))

    def _source_tier_policy(self) -> Dict[str, Any]:
        return {
            "schema_version": "source_tier_policy_v1",
            "can_support_strong_data_claim": ["official", "licensed_provider", "licensed_manual", "formal_data_source"],
            "must_not_support_strong_data_claim": ["candidate_external_material", "proxy", "derived_inference", "unknown"],
            "downgrade_rules": [
                "headline/news/social/event materials stay candidate until upgraded through a formal data-source path.",
                "proxy indicators cannot be described as official fact.",
                "technical indicators cannot prove valuation cheapness or fundamental improvement.",
                "derived hypotheses and final claims cannot replace their underlying evidence_refs.",
                "missing counter evidence or falsification conditions downgrades final claims.",
            ],
        }

    def _evidence_registry_summary(self, registry: EvidenceRegistry) -> Dict[str, Any]:
        by_kind: Dict[str, int] = {}
        by_tier: Dict[str, int] = {}
        for passport in registry.passports.values():
            by_kind[passport.evidence_kind] = by_kind.get(passport.evidence_kind, 0) + 1
            by_tier[passport.source_tier] = by_tier.get(passport.source_tier, 0) + 1
        return {
            "schema_version": registry.schema_version,
            "passport_count": len(registry.passports),
            "by_kind": by_kind,
            "by_source_tier": by_tier,
            "downgrade_count": len(registry.downgrade_summary),
            "source_tier_policy_ref": "evidence_registry.json:source_tier_policy",
        }

    def _build_final_claim_ledger(
        self,
        *,
        synthesis_packet: SynthesisPacket,
        thesis: ThesisDraft,
        final_adjudication: FinalAdjudication,
        evidence_registry: EvidenceRegistry,
        effective_date: str,
        risk_report: Optional[RiskBoundaryReport] = None,
    ) -> ClaimLedger:
        entries: List[ClaimLedgerEntry] = []
        common_refs = self._compact_string_refs(
            [ref for chain in getattr(final_adjudication, "key_support_chains", []) or [] for ref in chain.evidence_refs]
            + list(getattr(final_adjudication, "evidence_refs", []) or [])
            + [ref for chain in getattr(thesis, "key_support_chains", []) or [] for ref in chain.evidence_refs]
        )

        def add(source_stage: str, claim_type: str, claim_text: str, evidence_refs: List[str], inference_steps: List[str], falsifiers: List[str]) -> None:
            text = " ".join(str(claim_text or "").split())
            if not text:
                return
            claim_id = f"claim:{source_stage}:{hashlib.sha1((claim_type + '|' + text).encode('utf-8')).hexdigest()[:12]}"
            raw_refs = self._compact_string_refs(evidence_refs or common_refs)
            # valuation 放宽到 {L1, L3, L4}：deep_research_canon.get_ndx_pe_and_earnings_yield 的
            # cross_validation_targets 显式包含 get_10y_real_rate（L1）与 get_ndx_ndxe_ratio（L3），
            # 二者是估值判断的合法交叉验证证据；仍排除 L2/L5，"技术指标/情绪不能证明估值便宜"的红线不变。
            # risk_boundary 不设层级白名单：风险表述的合法来源覆盖全部层，限制无意义。
            layer_scope = {
                "valuation": {"L1", "L3", "L4"},
                "timing": {"L2", "L3", "L5"},
                "price_reflection": {"L5"},
            }.get(claim_type)
            if layer_scope:
                raw_refs = [ref for ref in raw_refs if str(ref).split(".", 1)[0] in layer_scope]
            # LLM 有时把 "known_data_gaps" 一类说明性 token 混进 evidence refs；
            # 只保留形如 L#.func 或注册表内的真实引用，其余记录为被剔除 token，不让它冒充缺失证据去阻断发布。
            entry_refs = [
                ref
                for ref in raw_refs
                if ref in evidence_registry.passports or _EVIDENCE_REF_PATTERN.fullmatch(ref)
            ]
            dropped_tokens = [ref for ref in raw_refs if ref not in entry_refs]
            counter_refs, counter_method = self._claim_specific_counter_refs(
                claim_type=claim_type,
                synthesis_packet=synthesis_packet,
                thesis=thesis,
                final_adjudication=final_adjudication,
            )
            falsification_conditions, falsifier_method = self._claim_specific_falsifiers(
                claim_type=claim_type,
                provided_falsifiers=falsifiers,
                synthesis_packet=synthesis_packet,
                thesis=thesis,
                final_adjudication=final_adjudication,
                risk_report=risk_report,
            )
            entry = ClaimLedgerEntry(
                claim_id=claim_id,
                source_stage=source_stage,  # type: ignore[arg-type]
                claim_text=text,
                claim_type=claim_type,  # type: ignore[arg-type]
                evidence_refs=entry_refs,
                counter_evidence_refs=counter_refs,
                inference_steps=self._compact_strings(inference_steps),
                falsification_conditions=falsification_conditions,
                counter_evidence_method=counter_method,
                falsifier_method=falsifier_method,
                dropped_non_evidence_tokens=dropped_tokens,
            )
            entries.append(self._verify_claim_entry(entry, evidence_registry))

        add(
            "thesis",
            "market_state",
            thesis.main_thesis,
            common_refs,
            [thesis.environment_assessment, thesis.valuation_assessment, thesis.timing_assessment],
            list(getattr(thesis, "invalidation_conditions", []) or []),
        )
        add("thesis", "valuation", thesis.valuation_assessment, common_refs, [thesis.valuation_assessment], list(getattr(thesis, "invalidation_conditions", []) or []))
        add("thesis", "timing", thesis.timing_assessment, common_refs, [thesis.timing_assessment], list(getattr(thesis, "invalidation_conditions", []) or []))
        add("thesis", "price_reflection", getattr(thesis, "priced_narrative", ""), common_refs, [getattr(thesis, "payoff_assessment", "")], list(getattr(thesis, "invalidation_conditions", []) or []))
        add("final", "market_state", final_adjudication.final_stance, common_refs, [final_adjudication.adjudicator_notes], list(final_adjudication.invalidation_conditions or []))
        add("final", "market_state", getattr(final_adjudication.reader_final, "one_liner", ""), list(getattr(final_adjudication.reader_final, "evidence_refs", []) or []) + common_refs, list(getattr(final_adjudication.reader_final, "three_reasons", []) or []), list(getattr(final_adjudication.reader_final, "invalidation_summary", []) or []))
        add("final", "risk_boundary", "；".join(str(item) for item in list(final_adjudication.must_preserve_risks or [])[:6]), common_refs, ["Final 必须保留 Risk Sentinel 和主要矛盾中的风险边界。"], list(final_adjudication.invalidation_conditions or []))
        add("final", "action_translation", "；".join(str(getattr(action, "action", "")) for action in list(getattr(final_adjudication, "portfolio_actions", []) or [])[:4]), common_refs, [str(getattr(action, "rationale", "")) for action in list(getattr(final_adjudication, "portfolio_actions", []) or [])[:4]], list(final_adjudication.invalidation_conditions or []))

        publish_gate = self._claim_ledger_publish_gate(entries)
        return ClaimLedger(
            effective_date=effective_date,
            entries=entries,
            publish_gate=publish_gate,
        )

    @staticmethod
    def _normalize_evidence_ref_key(ref: str) -> str:
        """把 LLM 可能写出的 ref 变体（首尾/内部空白、"# " / " #" 间距）规整成紧凑形式，
        供大小写不敏感匹配用。不改变 entry.evidence_refs 本身的原始文本（审计留痕）。"""
        compact = " ".join(str(ref or "").split())
        return compact.replace(" #", "#").replace("# ", "#")

    def _resolve_claim_evidence_ref(self, ref: str, passports: Dict[str, Any], lower_key_map: Dict[str, str]) -> Optional[str]:
        """把一条 claim 引用的 ref 字符串解析成 registry.passports 里的规范 key。
        优先精确匹配；找不到时按规整+大小写不敏感兜底，兜底命中才算已注册引用，
        未命中仍然计入 missing_refs（笔误/幻觉引用名不能被规范化"洗白"）。"""
        if ref in passports:
            return ref
        normalized = self._normalize_evidence_ref_key(ref)
        if normalized in passports:
            return normalized
        return lower_key_map.get(normalized.lower())

    def _resolve_claim_evidence_ref_with_parent_fallback(
        self,
        ref: str,
        registry: EvidenceRegistry,
        lower_key_map: Dict[str, str],
    ) -> Optional[str]:
        """T35 修复（方案 A）第③步：`_build_evidence_registry` 只对 MetricAuthority
        登记过的字段建字段级 passport（未登记字段不批量建 passport，避免凭空引入
        `audit_only` 而把已登记的 7 个函数集体判成 mixed_field_authority）。这意味着
        schema_guard 放行的"真实但未登记"字段引用在这里查不到自己的 passport——如果
        直接判"查无此证据"，等于绕了一圈又把身份合法的引用打成幻觉。这里做的是身份
        比对而非放宽权限：只有当字段名真实出现在父级 payload 的 `value` 里
        （记在 authority_model["real_value_fields"]，见 `_build_evidence_registry`）才
        回落到父级 passport 的权限；编造的字段名仍然解析失败、计入 missing_refs。"""
        resolved = self._resolve_claim_evidence_ref(ref, registry.passports, lower_key_map)
        if resolved is not None or "#" not in ref:
            return resolved
        parent_ref, field_name = self._normalize_evidence_ref_key(ref).split("#", 1)
        parent_resolved = self._resolve_claim_evidence_ref(parent_ref, registry.passports, lower_key_map)
        if parent_resolved is None:
            return None
        parent_authority = registry.passports[parent_resolved].authority_model
        parent_authority = parent_authority if isinstance(parent_authority, dict) else {}
        real_fields = set(parent_authority.get("real_value_fields") or [])
        if field_name.strip() in real_fields:
            return parent_resolved
        return None

    def _verify_claim_entry(self, entry: ClaimLedgerEntry, registry: EvidenceRegistry) -> ClaimLedgerEntry:
        strong_tiers = {"official", "licensed_provider", "licensed_manual", "formal_data_source"}
        lower_key_map = {key.lower(): key for key in registry.passports}
        resolved_refs = [
            (ref, self._resolve_claim_evidence_ref_with_parent_fallback(ref, registry, lower_key_map))
            for ref in entry.evidence_refs
        ]
        missing_refs = [ref for ref, resolved in resolved_refs if resolved is None]
        registered_refs = [resolved for _, resolved in resolved_refs if resolved is not None]
        weak_refs = [
            ref
            for ref in registered_refs
            if registry.passports[ref].source_tier in {"candidate_external_material", "proxy", "derived_inference", "unknown"}
        ]
        evidence_field_refs = [ref for ref in registered_refs if "#" in ref]

        # 第一遍：只分类权限状态，不下结论、不追加 reason。裸引用（无 #field）指向"混合容器"时，
        # 如果容器内混了 rejected 字段——无法排除引用其实是在借道引用被正式拒绝的口径，这种歧义是
        # 真违规，判定与是否有其他强证据无关，无条件追加（hard_mixed_parent_refs）。如果容器内所有
        # 字段都只是弱-但-合法（supporting_only/validation_only/audit_only/unknown，没有 rejected 也
        # 没有 core_allowed 可"蹭"），裸引用不可能是在冒充强结论，等价于弱字段引用，纳入比例判断
        # （soft_mixed_parent_refs，并入 weak_parent_refs 一起走比例原则）。
        field_authority_records: List[tuple[str, str, str, str, bool]] = []
        hard_mixed_parent_refs: List[str] = []
        parent_usage_by_ref: Dict[str, str] = {}
        for ref in registered_refs:
            passport = registry.passports[ref]
            authority_model = passport.authority_model if isinstance(passport.authority_model, dict) else {}
            if "#" in ref:
                field = str(authority_model.get("field_name") or ref.rsplit("#", 1)[-1])
                field_rule = authority_model.get("field_authority") if isinstance(authority_model.get("field_authority"), dict) else {}
                usage = str(authority_model.get("field_usage") or field_rule.get("usage") or "unknown").strip().lower()
                field_authority_records.append((ref, field, usage, passport.source_tier, passport.verified))
            elif authority_model.get("mixed_field_authority"):
                field_usages = authority_model.get("field_usages") if isinstance(authority_model.get("field_usages"), list) else []
                if "rejected" in field_usages:
                    hard_mixed_parent_refs.append(ref)
                else:
                    parent_usage_by_ref[ref] = "mixed_weak_fields"
            else:
                parent_usage = str(authority_model.get("field_usage") or "").strip().lower()
                if parent_usage:
                    parent_usage_by_ref[ref] = parent_usage

        supporting_field_refs = [
            field_ref
            for field_ref, _, usage, _, _ in field_authority_records
            if usage in {"supporting_only", "validation_only", "audit_only", "unknown", ""}
        ]
        rejected_field_refs = [field_ref for field_ref, _, usage, _, _ in field_authority_records if usage == "rejected"]
        weak_parent_refs = [ref for ref, usage in parent_usage_by_ref.items() if usage in {"supporting_only", "validation_only", "audit_only", "unknown", "mixed_weak_fields"}]
        rejected_parent_refs = [ref for ref, usage in parent_usage_by_ref.items() if usage == "rejected"]

        # 比例原则（工单#13 claim gate 稳定化）：判断这条 claim 除了权限受限/歧义引用之外，
        # 是否还有独立的强证据（official/licensed_provider/licensed_manual/formal_data_source）支撑
        # ——独立指该强证据本身不是被限权的字段/裸引用（Wind 这类强 provider 下也可能挂着
        # supporting_only/validation_only 的子字段，子字段不能借用父级 provider 的强 tier 洗白自己）。
        # 若存在独立强证据，"顺带多引用一条 validation_only/audit_only 交叉校验字段"只是同一份结论的
        # 措辞/引用清单差异，不应单独把整条 claim 从 verified 拖到 downgraded——这正是同输入 verified 率
        # 在 7/8 与 1/8 间跳动的机械来源。若没有独立强证据（孤证/纯弱证据），仍然照常降级。
        restricted_refs = set(supporting_field_refs) | set(rejected_field_refs) | set(hard_mixed_parent_refs) | set(weak_parent_refs) | set(rejected_parent_refs)
        has_strong_support = any(
            ref not in restricted_refs and registry.passports[ref].source_tier in strong_tiers
            for ref in registered_refs
        )

        reasons: List[str] = []
        block = False
        for ref in hard_mixed_parent_refs:
            reasons.append(f"mixed_field_authority_parent_ref:{ref}")
        for ref in rejected_parent_refs:
            reasons.append(f"field_authority_rejected_parent_ref:{ref}")
            block = True
        if not has_strong_support:
            for ref in weak_parent_refs:
                usage = parent_usage_by_ref[ref]
                label = "mixed_field_authority_parent_ref" if usage == "mixed_weak_fields" else f"field_authority_{usage}_parent_ref"
                reasons.append(f"{label}:{ref}")
        if not entry.evidence_refs:
            reasons.append("missing_evidence_refs")
            block = True
        if missing_refs:
            # 比例原则：个别引用无法核验（多为模型笔误/幻觉引用名）时点名降级；
            # 只有当没有任何可核验引用时，才等同于证据缺失而阻断。
            reasons.append("unverifiable_evidence_refs:" + ",".join(missing_refs[:5]))
            if not registered_refs:
                block = True
        if not entry.counter_evidence_refs:
            reasons.append("missing_counter_evidence_refs")
        if not entry.falsification_conditions:
            reasons.append("missing_falsification_conditions")
        if getattr(entry, "counter_evidence_method", "") == "not_claim_specific":
            reasons.append("counter_evidence_not_claim_specific")
        if getattr(entry, "falsifier_method", "") == "not_claim_specific":
            reasons.append("falsification_conditions_not_claim_specific")
        if weak_refs and not has_strong_support:
            reasons.append("only_weak_or_derived_evidence_refs")
        if supporting_field_refs and not has_strong_support:
            usages = sorted({usage or "unknown" for ref, _, usage, _, _ in field_authority_records if ref in supporting_field_refs})
            reasons.append("field_authority_" + "_or_".join(usages) + ":" + ",".join(supporting_field_refs))
        if rejected_field_refs:
            reasons.append("field_authority_rejected:" + ",".join(rejected_field_refs))
            rejected_fields = {field for _, field, usage, _, _ in field_authority_records if usage == "rejected"}
            rescued_fields = {
                field
                for _, field, usage, source_tier, passport_verified in field_authority_records
                if usage == "core_allowed" and source_tier in strong_tiers and passport_verified
            }
            if not rejected_fields.issubset(rescued_fields):
                block = True
        verified = not reasons
        return entry.model_copy(
            update={
                "verified": verified,
                "authority_status": "verified" if verified else ("blocked" if block else "downgraded"),
                "downgrade_reason": "；".join(reasons),
                "evidence_field_refs": list(dict.fromkeys(evidence_field_refs)),
            }
        )

    def _claim_ledger_publish_gate(self, entries: List[ClaimLedgerEntry]) -> Dict[str, Any]:
        blocked = [entry.claim_id for entry in entries if entry.authority_status == "blocked"]
        downgraded = [entry.claim_id for entry in entries if entry.authority_status == "downgraded"]
        status = "pass" if entries and not blocked and not downgraded else ("blocked" if blocked else "downgraded")
        return {
            "status": status,
            "entry_count": len(entries),
            "verified_count": sum(1 for entry in entries if entry.verified),
            "blocked_claim_ids": blocked,
            "downgraded_claim_ids": downgraded,
            "rule": "重要 final/thesis claim 必须同时有 evidence_refs、counter_evidence_refs、inference_steps、falsification_conditions，且证据权限不能越权。",
        }

    def _attach_claims_to_evidence_registry(self, registry: EvidenceRegistry, ledger: ClaimLedger) -> EvidenceRegistry:
        passports = dict(registry.passports)
        for entry in ledger.entries:
            passports[entry.claim_id] = EvidencePassport(
                evidence_id=entry.claim_id,
                evidence_kind="final_claim",
                source_ref=f"final_claim_ledger.json:{entry.claim_id}",
                source_tier="derived_inference",
                authority_model={
                    "claim_type": entry.claim_type,
                    "evidence_refs": list(entry.evidence_refs),
                    "counter_evidence_refs": list(entry.counter_evidence_refs),
                },
                downgrade_rules=[entry.downgrade_reason] if entry.downgrade_reason else ["derived_final_claim_requires_underlying_evidence"],
                effective_date=ledger.effective_date,
                verified=entry.verified,
                limitations=["Final claim is not primary evidence; inspect underlying evidence_refs."],
            )
            for ref in entry.evidence_refs + entry.counter_evidence_refs:
                passport = passports.get(ref)
                if passport is None:
                    continue
                linked = list(passport.linked_claim_ids)
                if entry.claim_id not in linked:
                    linked.append(entry.claim_id)
                passports[ref] = passport.model_copy(update={"linked_claim_ids": linked})
        return registry.model_copy(update={"passports": passports, "downgrade_summary": self._registry_downgrade_summary(passports)})

    def _registry_downgrade_summary(self, passports: Dict[str, EvidencePassport]) -> List[Dict[str, Any]]:
        return [
            {
                "evidence_id": passport.evidence_id,
                "reason": list(passport.downgrade_rules),
                "source_tier": passport.source_tier,
            }
            for passport in passports.values()
            if passport.downgrade_rules or not passport.verified
        ][:120]

    def _claim_counter_refs(self, synthesis_packet: SynthesisPacket, thesis: ThesisDraft, final_adjudication: FinalAdjudication) -> List[str]:
        refs: List[str] = []
        for conflict in list(synthesis_packet.high_severity_typed_conflicts or []):
            refs.extend(list(getattr(conflict, "evidence_refs", []) or []))
        for hypothesis in list(synthesis_packet.competing_hypotheses or []):
            refs.extend(list(getattr(hypothesis, "counter_evidence_refs", []) or []))
        for item in list(getattr(thesis, "price_reflection_map", []) or []) + list(getattr(final_adjudication, "price_reflection_map", []) or []):
            refs.extend(list(getattr(item, "counterevidence_refs", []) or []))
        return self._compact_string_refs(refs)

    def _claim_falsifiers(self, thesis: ThesisDraft, final_adjudication: FinalAdjudication, synthesis_packet: SynthesisPacket) -> List[str]:
        items: List[str] = []
        items.extend(str(item) for item in list(getattr(thesis, "invalidation_conditions", []) or []))
        items.extend(str(item) for item in list(getattr(final_adjudication, "invalidation_conditions", []) or []))
        reader = getattr(final_adjudication, "reader_final", None)
        if reader is not None:
            items.extend(str(item) for item in list(getattr(reader, "invalidation_summary", []) or []))
        for hypothesis in list(synthesis_packet.competing_hypotheses or []):
            items.extend(str(item) for item in list(getattr(hypothesis, "falsification_conditions", []) or []))
        return self._compact_strings(items)

    def _claim_specific_counter_refs(
        self,
        *,
        claim_type: str,
        synthesis_packet: SynthesisPacket,
        thesis: ThesisDraft,
        final_adjudication: FinalAdjudication,
    ) -> tuple[List[str], str]:
        competing_support_refs = [
            ref
            for hypothesis in list(synthesis_packet.competing_hypotheses or [])
            if str(getattr(hypothesis, "source", "")) in {"counter_thesis", "deterministic_fallback", "investigation"}
            for ref in list(getattr(hypothesis, "support_evidence_refs", []) or [])
        ]
        typed_conflict_refs = [
            ref
            for conflict in list(synthesis_packet.high_severity_typed_conflicts or [])
            for ref in list(getattr(conflict, "evidence_refs", []) or [])
        ]
        price_counter_refs = [
            ref
            for item in list(getattr(thesis, "price_reflection_map", []) or []) + list(getattr(final_adjudication, "price_reflection_map", []) or [])
            for ref in list(getattr(item, "counterevidence_refs", []) or [])
        ]
        invalidation_related_refs = [
            ref
            for view in list(getattr(final_adjudication, "time_horizon_views", []) or []) + list(getattr(thesis, "time_horizon_views", []) or [])
            for ref in list(getattr(view, "evidence_refs", []) or [])
        ]

        if claim_type == "market_state":
            refs = self._compact_string_refs(competing_support_refs + typed_conflict_refs)
            return refs, "opposing_hypothesis_support_plus_typed_conflicts" if refs else "not_claim_specific"
        if claim_type == "price_reflection":
            refs = self._compact_string_refs(price_counter_refs + competing_support_refs)
            return refs, "price_reflection_counterevidence" if refs else "not_claim_specific"
        if claim_type == "risk_boundary":
            refs = self._compact_string_refs(typed_conflict_refs + price_counter_refs)
            return refs, "risk_conflicts_and_price_counterevidence" if refs else "not_claim_specific"
        if claim_type == "valuation":
            refs = self._compact_string_refs(typed_conflict_refs + price_counter_refs + competing_support_refs)
            return refs, "valuation_conflicts_and_opposing_support" if refs else "not_claim_specific"
        if claim_type == "timing":
            refs = self._compact_string_refs(invalidation_related_refs + competing_support_refs)
            return refs, "timing_invalidation_and_opposing_support" if refs else "not_claim_specific"
        if claim_type == "action_translation":
            refs = self._compact_string_refs(invalidation_related_refs + competing_support_refs + price_counter_refs)
            return refs, "action_invalidation_related_refs" if refs else "not_claim_specific"
        refs = self._compact_string_refs(price_counter_refs + typed_conflict_refs)
        return refs, "typed_conflicts_or_price_counterevidence" if refs else "not_claim_specific"

    def _claim_specific_falsifiers(
        self,
        *,
        claim_type: str,
        provided_falsifiers: List[str],
        synthesis_packet: SynthesisPacket,
        thesis: ThesisDraft,
        final_adjudication: FinalAdjudication,
        risk_report: Optional[RiskBoundaryReport],
    ) -> tuple[List[str], str]:
        provided = self._compact_strings(provided_falsifiers)
        if claim_type in {"market_state", "price_reflection"}:
            hypothesis_falsifiers = [
                item
                for hypothesis in list(synthesis_packet.competing_hypotheses or [])
                for item in list(getattr(hypothesis, "falsification_conditions", []) or [])
            ]
            result = self._compact_strings(provided + hypothesis_falsifiers)
            return result, "claim_invalidation_plus_hypothesis_falsifiers" if result else "not_claim_specific"
        if claim_type == "risk_boundary":
            risk_items: List[str] = []
            if risk_report is not None:
                risk_items.extend(str(item) for item in list(getattr(risk_report, "must_preserve_risks", []) or []))
                risk_items.extend(str(item.get("condition") or item.get("risk") or item) for item in list(getattr(risk_report, "failure_conditions", []) or []) if isinstance(item, dict))
                risk_items.extend(str(item) for item in list(getattr(risk_report, "false_safety_risks", []) or []))
            result = self._compact_strings(risk_items + provided)
            return result, "risk_sentinel_failure_conditions" if result else "not_claim_specific"
        if claim_type == "action_translation":
            action_conditions = [
                condition
                for action in list(getattr(final_adjudication, "portfolio_actions", []) or []) + list(getattr(thesis, "portfolio_actions", []) or [])
                for condition in list(getattr(action, "conditions", []) or [])
            ]
            result = self._compact_strings(provided + action_conditions)
            return result, "action_conditions_and_invalidation" if result else "not_claim_specific"
        if claim_type in {"valuation", "timing"}:
            hypothesis_falsifiers = [
                item
                for hypothesis in list(synthesis_packet.competing_hypotheses or [])
                for item in list(getattr(hypothesis, "falsification_conditions", []) or [])
            ]
            result = self._compact_strings(provided + hypothesis_falsifiers)
            return result, f"{claim_type}_claim_invalidation_plus_hypothesis_falsifiers" if result else "not_claim_specific"
        result = self._compact_strings(provided)
        return result, "provided_claim_falsifiers" if result else "not_claim_specific"

    def _load_user_decision_profile(self) -> UserDecisionProfile:
        config_dir = Path(__file__).resolve().parents[2] / "config"

        def read_json(path: Path) -> Dict[str, Any]:
            if not path.exists():
                return {}
            try:
                value = json.loads(path.read_text(encoding="utf-8"))
                return value if isinstance(value, dict) else {}
            except Exception as exc:
                logger.warning("Failed to load user decision profile from %s: %s", path, exc)
                return {}

        return self._decision_profile_from_config_documents(
            read_json(config_dir / "user_decision_profile.json"),
            read_json(config_dir / "user_decision_profile.local.json"),
        )

    def _decision_profile_from_config_documents(
        self,
        tracked_document: Dict[str, Any],
        local_document: Optional[Dict[str, Any]] = None,
    ) -> UserDecisionProfile:
        """Build the reader-exit profile from an explicit, privacy-bounded subtree.

        The IPS document may contain amounts and holdings.  Only ``reader_exit``
        fields are selected, so those private values cannot enter an artifact by
        accident.  Missing or malformed disciplines fail closed instead of
        silently activating generic defaults.
        """
        allowed = {
            "schema_version", "profile_id", "version", "holding_status", "objective",
            "risk_tolerance", "decision_frequency", "buy_disciplines", "sell_disciplines",
            "configuration_status", "configuration_issues",
        }

        def reader_exit(document: Dict[str, Any]) -> Dict[str, Any]:
            candidate = document.get("reader_exit") if isinstance(document.get("reader_exit"), dict) else {}
            if document.get("schema_version") == "user_decision_profile_v1":
                candidate = document
            return {key: value for key, value in candidate.items() if key in allowed}

        selected = reader_exit(tracked_document)
        selected.update(reader_exit(local_document or {}))
        selected.setdefault("configuration_status", "unconfigured")
        selected.setdefault("configuration_issues", [])
        try:
            profile = UserDecisionProfile.model_validate(selected)
        except Exception as exc:
            return UserDecisionProfile(
                configuration_status="invalid",
                configuration_issues=[f"reader_exit_profile_validation_failed:{type(exc).__name__}"],
            )
        condition_count = len(profile.buy_disciplines) + len(profile.sell_disciplines)
        if condition_count == 0:
            issues = list(profile.configuration_issues)
            if "no_confirmed_buy_or_sell_disciplines" not in issues:
                issues.append("no_confirmed_buy_or_sell_disciplines")
            return profile.model_copy(update={"configuration_status": "unconfigured", "configuration_issues": issues})
        return profile

    def _build_golden_pit_checklist(
        self,
        *,
        final_claim_ledger: ClaimLedger,
        decision_profile: UserDecisionProfile,
        final_adjudication: FinalAdjudication,
        effective_date: str,
        state_variables: Optional[Dict[str, Any]] = None,
        evidence_registry: Optional[EvidenceRegistry] = None,
    ) -> GoldenPitChecklist:
        selected = [
            entry
            for entry in list(final_claim_ledger.entries or [])
            if entry.claim_type in {"valuation", "timing", "risk_boundary"}
        ]
        entries: List[GoldenPitChecklistItem] = []
        for entry in selected:
            status = self._checklist_status_from_claim(entry)
            item = GoldenPitChecklistItem(
                condition_id=f"claim:{entry.claim_id}",
                condition=entry.claim_text,
                discipline_side="claim",
                source_claim_ids=[entry.claim_id],
                evidence_refs=list(entry.evidence_refs),
                current_status=status,
                falsification_conditions=list(entry.falsification_conditions),
                status_method="claim_authority_status",
                status_evidence={"authority_status": entry.authority_status, "verified": entry.verified},
            )
            entries.append(item.model_copy(update={"changed_since_last_run": self._deferred_cross_run_change(item)}))

        profile_conditions = list(decision_profile.buy_disciplines or []) + list(decision_profile.sell_disciplines or [])
        if not profile_conditions:
            item = GoldenPitChecklistItem(
                condition_id="profile_disciplines_unconfigured",
                condition="个人买卖阈值尚未由用户确认；本轮只展示研究结论，不生成个性化买卖触发。",
                discipline_side="hold",
                current_status="insufficient_evidence",
                status_method="profile_configuration_gate",
                status_evidence={
                    "configuration_status": decision_profile.configuration_status,
                    "configuration_issues": list(decision_profile.configuration_issues),
                },
                falsification_conditions=["用户明确确认阈值、单位与适用条件后，才可解除本闸门。"],
            )
            entries.append(item.model_copy(update={"changed_since_last_run": self._deferred_cross_run_change(item)}))
        for condition in profile_conditions:
            matched = [entry for entry in selected if entry.claim_type in set(condition.required_claim_types)]
            predicate_refs, predicate_falsifiers = self._predicate_refs_and_falsifiers(condition)
            unregistered_predicate_refs: List[str] = []
            unverified_predicate_refs: List[str] = []
            if evidence_registry is not None:
                registered = set(evidence_registry.passports)
                unregistered_predicate_refs = [ref for ref in predicate_refs if ref not in registered]
                predicate_refs = [ref for ref in predicate_refs if ref in registered]
                unverified_predicate_refs = [
                    ref for ref in predicate_refs
                    if not bool(evidence_registry.passports[ref].verified)
                ]
            evidence_refs = predicate_refs or self._compact_string_refs([ref for entry in matched for ref in entry.evidence_refs], limit=24)
            falsifiers = predicate_falsifiers or self._compact_strings([item for entry in matched for item in entry.falsification_conditions], limit=12)
            if unregistered_predicate_refs or unverified_predicate_refs:
                status, status_method, status_evidence = (
                    "insufficient_evidence",
                    "evidence_registry_gate",
                    {
                        "unregistered_predicate_refs": unregistered_predicate_refs,
                        "unverified_predicate_refs": unverified_predicate_refs,
                    },
                )
                evidence_refs = predicate_refs
            elif decision_profile.configuration_status != "configured":
                status, status_method, status_evidence = (
                    "insufficient_evidence",
                    "profile_configuration_gate",
                    {
                        "configuration_status": decision_profile.configuration_status,
                        "configuration_issues": list(decision_profile.configuration_issues),
                    },
                )
            else:
                status, status_method, status_evidence = self._profile_condition_status(condition, matched, state_variables or {})
            item = GoldenPitChecklistItem(
                condition_id=condition.condition_id,
                condition=f"{condition.label}：{condition.discipline}",
                discipline_side=condition.side,
                source_claim_ids=[entry.claim_id for entry in matched],
                evidence_refs=evidence_refs,
                current_status=status,  # type: ignore[arg-type]
                falsification_conditions=falsifiers,
                status_method=status_method,
                status_evidence=status_evidence,
            )
            entries.append(item.model_copy(update={"changed_since_last_run": self._deferred_cross_run_change(item)}))

        changed_summary = [
            "跨 run 变化对比暂缓启用：需等待 claim schema、数据源覆盖和 Run Review 通过历史稳定后再前置。"
        ]
        return GoldenPitChecklist(
            effective_date=effective_date,
            previous_checklist_ref="",
            current_state=getattr(final_adjudication, "state_diagnosis", "") or getattr(final_adjudication.reader_final, "one_liner", "") or final_adjudication.final_stance,
            changed_since_last_run_summary=changed_summary,
            entries=entries,
        )

    def _predicate_refs_and_falsifiers(self, condition: UserDecisionCondition) -> tuple[List[str], List[str]]:
        expression = condition.metric_predicates if isinstance(condition.metric_predicates, dict) else {}
        predicates = expression.get("predicates") if isinstance(expression.get("predicates"), list) else []
        refs: List[str] = []
        falsifiers: List[str] = []
        for predicate in predicates:
            if not isinstance(predicate, dict):
                continue
            variable = str(predicate.get("var") or "")
            spec = STATE_VARIABLE_SPEC_BY_KEY.get(variable, {})
            refs.extend(str(ref) for ref in _as_list(spec.get("evidence_refs") or spec.get("evidence_ref")) if str(ref))
            op = str(predicate.get("op") or "")
            expected = predicate.get("value")
            unit = str(predicate.get("unit") or spec.get("unit") or "").strip()
            if variable and op and expected is not None:
                falsifiers.append(f"若 {variable} 不再满足 {op} {expected} {unit}，则该条件失效。".replace("  ", " "))
        return self._compact_string_refs(refs, limit=24), self._compact_strings(falsifiers, limit=12)

    def _checklist_status_from_claim(self, entry: ClaimLedgerEntry) -> str:
        if entry.verified:
            return "met"
        if entry.authority_status == "blocked":
            return "insufficient_evidence"
        return "not_met"

    def _profile_condition_status(
        self,
        condition: UserDecisionCondition,
        matched: List[ClaimLedgerEntry],
        state_variables: Dict[str, Any],
    ) -> tuple[str, str, Dict[str, Any]]:
        metric_predicates = getattr(condition, "metric_predicates", {}) or {}
        if isinstance(metric_predicates, dict) and metric_predicates:
            status, details = self._evaluate_metric_predicates(metric_predicates, state_variables)
            return status, "metric_predicates", details

        fallback_evidence = {
            "reason": "condition_has_no_metric_predicates",
            "matched_claim_ids": [entry.claim_id for entry in matched],
        }
        if not matched:
            return "insufficient_evidence", "claim_text_fallback", fallback_evidence
        if any(entry.authority_status == "blocked" for entry in matched):
            fallback_evidence["blocked_claim_ids"] = [entry.claim_id for entry in matched if entry.authority_status == "blocked"]
            return "insufficient_evidence", "claim_text_fallback", fallback_evidence
        required_types = set(condition.required_claim_types)
        present_types = {entry.claim_type for entry in matched}
        if required_types and not required_types.issubset(present_types):
            fallback_evidence["missing_claim_types"] = sorted(required_types - present_types)
            return "insufficient_evidence", "claim_text_fallback", fallback_evidence
        if any(not entry.verified for entry in matched):
            fallback_evidence["unverified_claim_ids"] = [entry.claim_id for entry in matched if not entry.verified]
            return "not_met", "claim_text_fallback", fallback_evidence

        by_type: Dict[str, List[ClaimLedgerEntry]] = {}
        for entry in matched:
            by_type.setdefault(str(entry.claim_type), []).append(entry)

        if condition.side == "buy":
            checks = []
            if "valuation" in required_types:
                checks.append(any(self._claim_text_supports_buy("valuation", entry.claim_text) for entry in by_type.get("valuation", [])))
            if "timing" in required_types:
                checks.append(any(self._claim_text_supports_buy("timing", entry.claim_text) for entry in by_type.get("timing", [])))
            if "risk_boundary" in required_types:
                checks.append(any(self._claim_text_supports_buy("risk_boundary", entry.claim_text) for entry in by_type.get("risk_boundary", [])))
            fallback_evidence["claim_text_checks"] = checks
            return ("met" if checks and all(checks) else "not_met"), "claim_text_fallback", fallback_evidence
        if condition.side == "sell":
            checks = [self._claim_text_supports_sell(entry.claim_type, entry.claim_text) for entry in matched]
            fallback_evidence["claim_text_checks"] = checks
            return ("met" if any(checks) else "not_met"), "claim_text_fallback", fallback_evidence
        return ("met" if all(entry.verified for entry in matched) else "not_met"), "claim_text_fallback", fallback_evidence

    def _evaluate_metric_predicates(self, expression: Dict[str, Any], state_variables: Dict[str, Any]) -> tuple[str, Dict[str, Any]]:
        logic = str(expression.get("logic") or "all_of")
        raw_predicates = expression.get("predicates") if isinstance(expression.get("predicates"), list) else []
        results = []
        missing = False
        for predicate in raw_predicates:
            if not isinstance(predicate, dict):
                results.append({"status": "invalid_predicate", "predicate": predicate})
                missing = True
                continue
            variable = str(predicate.get("var") or "")
            op = str(predicate.get("op") or "")
            expected = predicate.get("value")
            threshold_status = str(predicate.get("threshold_status") or "")
            declared_unit = str(predicate.get("unit") or "")
            spec = STATE_VARIABLE_SPEC_BY_KEY.get(variable)
            if threshold_status != "confirmed":
                results.append({"var": variable, "op": op, "expected": expected, "actual": None, "met": None, "status": "threshold_unconfirmed", "threshold_status": threshold_status})
                missing = True
                continue
            if not spec:
                results.append({"var": variable, "op": op, "expected": expected, "actual": None, "met": None, "status": "unknown_state_variable", "threshold_status": threshold_status})
                missing = True
                continue
            if declared_unit != str(spec.get("unit") or ""):
                results.append({"var": variable, "op": op, "expected": expected, "actual": None, "met": None, "status": "unit_mismatch", "declared_unit": declared_unit, "expected_unit": spec.get("unit"), "threshold_status": threshold_status})
                missing = True
                continue
            if op not in list(spec.get("allowed_operators") or []):
                results.append({"var": variable, "op": op, "expected": expected, "actual": None, "met": None, "status": "operator_not_allowed", "threshold_status": threshold_status})
                missing = True
                continue
            if expected is None:
                results.append({"var": variable, "op": op, "expected": None, "actual": None, "met": None, "status": "threshold_missing", "threshold_status": threshold_status})
                missing = True
                continue
            actual = state_variables.get(variable)
            if actual is None:
                results.append(
                    {
                        "var": variable,
                        "op": op,
                        "expected": expected,
                        "actual": None,
                        "met": None,
                        "status": "missing_variable",
                        "threshold_status": predicate.get("threshold_status", ""),
                    }
                )
                missing = True
                continue
            met = self._evaluate_single_metric_predicate(actual, op, expected)
            results.append(
                {
                    "var": variable,
                    "op": op,
                    "expected": expected,
                    "actual": actual,
                    "met": met,
                    "status": "evaluated",
                    "threshold_status": predicate.get("threshold_status", ""),
                }
            )
        evaluated = [item for item in results if item.get("met") is not None]
        if not raw_predicates or missing or len(evaluated) != len(raw_predicates):
            status = "insufficient_evidence"
        elif logic == "any_of":
            status = "met" if any(bool(item.get("met")) for item in evaluated) else "not_met"
        else:
            status = "met" if all(bool(item.get("met")) for item in evaluated) else "not_met"
        return status, {
            "logic": logic,
            "predicate_count": len(raw_predicates),
            "results": results,
            "state_variable_source": "state_ledger.extract_state_variables",
        }

    def _evaluate_single_metric_predicate(self, actual: Any, op: str, expected: Any) -> bool:
        if op in {"==", "!="}:
            result = str(actual) == str(expected)
            return result if op == "==" else not result
        try:
            actual_number = float(actual)
            expected_number = float(expected)
        except (TypeError, ValueError):
            return False
        if op == "<":
            return actual_number < expected_number
        if op == "<=":
            return actual_number <= expected_number
        if op == ">":
            return actual_number > expected_number
        if op == ">=":
            return actual_number >= expected_number
        return False

    def _claim_text_supports_buy(self, claim_type: str, text: str) -> bool:
        raw = str(text or "")
        negative = re.search(r"不足|不便宜|偏贵|昂贵|未到|不支持|压力|恶化|破坏|脆弱|风险仍|风险边界仍需保留", raw)
        if negative:
            return False
        if claim_type == "valuation":
            return bool(re.search(r"便宜|低估|折价|安全垫|回落|改善|赔率改善|风险溢价改善", raw))
        if claim_type == "timing":
            return bool(re.search(r"趋势未破坏|趋势确认|企稳|转强|时机改善", raw))
        if claim_type == "risk_boundary":
            return bool(re.search(r"风险可承受|风险缓和|未触发|边界安全|压力缓和", raw))
        return False

    def _claim_text_supports_sell(self, claim_type: str, text: str) -> bool:
        raw = str(text or "")
        if claim_type == "timing":
            return bool(re.search(r"趋势破坏|跌破|转弱|失守|下行确认", raw))
        if claim_type == "risk_boundary":
            return bool(re.search(r"风险触发|边界突破|风险恶化|压力升级|信用恶化|流动性冲击", raw))
        return False

    def _deferred_cross_run_change(self, item: GoldenPitChecklistItem) -> Dict[str, Any]:
        return {
            "changed": False,
            "status": "deferred_until_run_quality_stable",
            "previous_status": "",
            "current_status": item.current_status,
            "summary": "跨 run 变化对比暂缓；当前只展示本轮状态与条件证据差距。",
        }

    def _compact_string_refs(self, values: List[Any], limit: int = 20) -> List[str]:
        return self._compact_strings([value for value in values if isinstance(value, str) and value], limit=limit)

    def _compact_strings(self, values: List[Any], limit: int = 20) -> List[str]:
        items: List[str] = []
        for value in values:
            text = " ".join(str(value or "").split())
            if text and text not in items:
                items.append(text)
            if len(items) >= limit:
                break
        return items

    def _load_local_json(self, path: Path, default: Any) -> Any:
        if not path.exists():
            return default
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return default

    # DeepSeek Strict Function Calling（Beta）试点范围：只有这里列出的 stage_key 才
    # 可能被启用，默认整个集合为空（不读环境变量也不改变行为）。试点范围收窄到
    # bridge 一处，是因为 docs/2026-05-10_BRIDGE_JSON_RESILIENCE_AI_AUDIT.md 当时
    # 已经把 bridge 的事故诊断透了、且切到 /beta 端点的前置工作已经做完，属于"捡起
    # 被搁置的阶段 C"而不是从零开始；其余 stage 一律走原有 json_object 路径。
    # 2026-07-29 扩围：bridge 在 run 20260729_175306 上 attempts=1 零报错，且产出质量
    # 相对 5 次非严格跑的基线带全面上移（字符 9097-13079→19837、共振链 1-2→3、传导路径
    # 2-3→4，内容核验非凑数）。T29 离线体检确认另外三个站的严格 schema 同样零问题，
    # 故一并纳入白名单。仍需环境变量逐个点名才会真正启用。
    # 2026-08-16 扩围（T42④/T44①）：reviser 纳入白名单以便给
    # `revised_thesis.retained_conflicts[].conflict_id` 注入与 thesis 同款的 enum 选单；
    # final / critic 纳入白名单——T44 核实 FinalAdjudication 的 3 处自由形态 object
    # 全部是代码事后填、模型从不需要填，Critique 则 0 处自由形态 object。
    _STRICT_TOOL_CALLING_ELIGIBLE_STAGES = {
        "bridge", "thesis", "event_card_interpreter", "event_section_summary",
        "reviser", "final", "critic",
    }

    def _strict_tool_schema_for_stage(
        self,
        stage_key: str,
        model_cls: Type[Any],
        *,
        schema_postprocess: Optional[Callable[[Dict[str, Any]], Dict[str, Any]]] = None,
    ) -> Optional[Dict[str, Any]]:
        """按 `NDX_STRICT_TOOL_CALLING_STAGES` 环境变量（逗号分隔 stage_key）决定
        是否为这次调用启用 DeepSeek strict function calling。未设置该环境变量、
        或 stage_key 不在试点白名单内时返回 None——调用方据此完全跳过 strict 路径，
        与试点之前的行为逐字节相同。这是刻意选择的显式 opt-in 开关，不是配置文件，
        方便用户在一次真实 run 前后随时打开/关闭做对比，不需要改代码。

        `schema_postprocess`（T34①新增）：可选的按本轮 run 动态改写 schema 的钩子，
        例如 thesis 站把 `retained_conflicts[].conflict_id` 收紧成本轮 bridge 实际
        给出的编号 enum（见 `_constrain_thesis_retained_conflict_id_enum`）。只有在
        真正启用严格模式（上面两道判断都通过）时才会被调用一次；未启用时钩子完全
        不执行，不影响"未启用=逐字节相同"这条保证。"""
        if stage_key not in self._STRICT_TOOL_CALLING_ELIGIBLE_STAGES:
            return None
        enabled_stages = {
            item.strip()
            for item in os.environ.get("NDX_STRICT_TOOL_CALLING_STAGES", "").split(",")
            if item.strip()
        }
        if stage_key not in enabled_stages:
            return None
        schema = sanitize_json_schema_for_strict_tool_calling(model_cls.model_json_schema())
        if schema_postprocess is not None:
            schema = schema_postprocess(schema)
        return schema

    def _run_bridge(
        self,
        packet: AnalysisPacket,
        context_brief: ContextBrief,
        layer_cards: List[LayerCard],
    ) -> BridgeMemo:
        bridge_payload = {
            "context_brief": _model_dump(self._purify_bridge_context_brief(context_brief)),
            "candidate_cross_layer_links": [_model_dump(link) for link in packet.candidate_cross_layer_links],
            "layer_cards": [_model_dump(card) for card in layer_cards],
        }
        checkpoint = self._load_stage_checkpoint(
            self.bridge_dir / "bridge_0.json",
            BridgeMemo,
            stage_key="bridge",
            stage_name="bridge",
            expected_payload=bridge_payload,
        )
        if checkpoint is not None:
            return checkpoint
        bridge = self._run_stage(
            stage_key="bridge",
            stage_name="bridge",
            model_cls=BridgeMemo,
            payload=bridge_payload,
            validator=self._validate_bridge_memo_v2,
            strict_tool_schema=self._strict_tool_schema_for_stage("bridge", BridgeMemo),
            strict_tool_name="emit_bridge_memo",
        )
        self._save_json(self.bridge_dir / "bridge_0.json", bridge)
        self._record_stage_artifact(
            self.bridge_dir / "bridge_0.json",
            stage_key="bridge",
            stage_name="bridge",
            payload=bridge_payload,
        )
        return bridge

    def _run_thesis(self, synthesis_packet: SynthesisPacket) -> ThesisDraft:
        thesis_payload = {
            "synthesis_packet": _model_dump(synthesis_packet),
        }
        checkpoint = self._load_stage_checkpoint(
            "thesis_draft.json",
            ThesisDraft,
            stage_key="thesis",
            stage_name="thesis",
            expected_payload=thesis_payload,
        )
        if checkpoint is not None and not self._validate_thesis_hypothesis_responses(
            checkpoint,
            synthesis_packet,
        ):
            return checkpoint
        conflict_id_candidates = self._collect_thesis_conflict_id_candidates(synthesis_packet)
        thesis = self._run_stage(
            stage_key="thesis",
            stage_name="thesis",
            model_cls=ThesisDraft,
            payload=thesis_payload,
            strict_tool_schema=self._strict_tool_schema_for_stage(
                "thesis",
                ThesisDraft,
                schema_postprocess=lambda schema: self._constrain_thesis_retained_conflict_id_enum(
                    schema, conflict_id_candidates
                ),
            ),
            strict_tool_name="emit_thesis_draft",
            validator=lambda candidate: self._validate_thesis_hypothesis_responses(
                candidate,
                synthesis_packet,
            ),
        )
        self._save_json("thesis_draft.json", thesis)
        self._record_stage_artifact(
            self.output_dir / "thesis_draft.json",
            stage_key="thesis",
            stage_name="thesis",
            payload=thesis_payload,
        )
        return thesis

    @staticmethod
    def _collect_thesis_conflict_id_candidates(synthesis_packet: SynthesisPacket) -> List[str]:
        """收集本轮 thesis 输入（`synthesis_packet`）里模型实际看得见的全部
        conflict_id，作为严格 schema enum 的候选集合（T34①）。只取模型这一轮
        真的看得见的编号——它看不见的编号不该允许它填：

        - `high_severity_typed_conflicts[].conflict_id`（TypedConflict，Bridge v2）
        - `high_severity_conflicts[].conflict_id`（Conflict，legacy 同名字段，可能非空）
        - `bridge_summaries[].typed_conflicts[].conflict_id`（dict，Bridge v2 原始输出，
          覆盖面比 high_severity_* 更全——后者只是"必须保留"的子集）

        按上述顺序去重保序返回；不在这里追加 `None`，"允许留空表示本站新发现的
        冲突"这条语义由调用方（`_constrain_thesis_retained_conflict_id_enum`）负责。
        """
        candidates: List[str] = []
        seen: set = set()

        def _add(conflict_id: Any) -> None:
            if isinstance(conflict_id, str) and conflict_id and conflict_id not in seen:
                seen.add(conflict_id)
                candidates.append(conflict_id)

        for typed_conflict in synthesis_packet.high_severity_typed_conflicts:
            _add(typed_conflict.conflict_id)
        for conflict in synthesis_packet.high_severity_conflicts:
            _add(conflict.conflict_id)
        for bridge_summary in synthesis_packet.bridge_summaries:
            for typed_conflict_dict in bridge_summary.typed_conflicts:
                if isinstance(typed_conflict_dict, dict):
                    _add(typed_conflict_dict.get("conflict_id"))
        return candidates

    def _find_strict_schema_array_items_node(self, container_schema: Any) -> Optional[Dict[str, Any]]:
        """在严格 schema 的数组字段节点里定位 `items` 子 schema，路径无关地兼容
        两种形态（T34①注入必须两种都命中，理由见类定义处的白名单注释和相关
        测试）：

        - 必填数组：`{"type": "array", "items": {...}}`
        - 可空数组（T34②"非必填容器字段改写为可空 anyOf"落地后）：
          `{"anyOf": [{"type": "array", "items": {...}}, {"type": "null"}]}`

        不能硬编码 `properties.X.items` 这一条路径——sanitize 逻辑在与本改动
        并行演进，形态会漂移；这里改为递归查找，两种形态、以及未来可能出现的
        嵌套变体都能命中。
        """
        if not isinstance(container_schema, dict):
            return None
        items = container_schema.get("items")
        if isinstance(items, dict):
            return items
        branches = container_schema.get("anyOf")
        if isinstance(branches, list):
            for branch in branches:
                found = self._find_strict_schema_array_items_node(branch)
                if found is not None:
                    return found
        return None

    @staticmethod
    def _resolve_strict_schema_object_node(node: Any, schema: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """把 `items` 节点解析成真正携带 `properties` 的 object schema。

        `sanitize_json_schema_for_strict_tool_calling` 的 `fix_anyof` 只内联展开
        anyOf 分支内的 `$ref`；顶层（非 anyOf 分支）的 `$ref`——比如必填数组字段的
        `items: {"$ref": "#/$defs/Conflict"}`——原样保留，要去 `$defs` 里查。已经
        是内联 object（anyOf 分支内展开过的情形）时直接用。
        """
        if not isinstance(node, dict):
            return None
        ref = node.get("$ref")
        if isinstance(ref, str):
            ref_name = ref.rsplit("/", 1)[-1]
            defs = schema.get("$defs", {})
            resolved = defs.get(ref_name)
            return resolved if isinstance(resolved, dict) else None
        if isinstance(node.get("properties"), dict):
            return node
        return None

    def _constrain_conflict_id_enum_for_paths(
        self,
        schema: Dict[str, Any],
        candidate_conflict_ids: List[str],
        paths: tuple,
    ) -> Dict[str, Any]:
        """按给定路径给 `Conflict.conflict_id` 注入 enum 选单的通用实现。

        `paths` 是 schema 内指向 `List[Conflict]` 数组字段的属性路径元组，例如
        `(("retained_conflicts",),)` 或 `(("revised_thesis", "retained_conflicts"),
        ("remaining_conflicts",))`。路径上的 `$ref` 节点会先解析成真正的 object
        schema，再继续向下走；兼容 sanitize 后两种数组形态（直接 items / anyOf
        包裹）。所有路径最终都指向同一个 `$defs.Conflict` 时，enum 只会在同一处
        节点上设置一次，重复设置无副作用。
        """
        if not candidate_conflict_ids:
            return schema
        dedup: List[str] = []
        seen: set = set()
        for conflict_id in candidate_conflict_ids:
            if conflict_id and conflict_id not in seen:
                seen.add(conflict_id)
                dedup.append(conflict_id)
        if not dedup:
            return schema
        enum_values: List[Optional[str]] = [*dedup, None]

        for path in paths:
            node: Any = schema
            for part in path:
                node = self._resolve_strict_schema_object_node(node, schema)
                if not isinstance(node, dict):
                    node = None
                    break
                node = node.get("properties", {}).get(part)
            if not isinstance(node, dict):
                continue
            items_node = self._find_strict_schema_array_items_node(node)
            conflict_object_schema = self._resolve_strict_schema_object_node(items_node, schema)
            if conflict_object_schema is None:
                continue
            conflict_id_node = conflict_object_schema.get("properties", {}).get("conflict_id")
            if isinstance(conflict_id_node, dict):
                conflict_id_node["enum"] = enum_values
        return schema

    def _constrain_thesis_retained_conflict_id_enum(
        self,
        schema: Dict[str, Any],
        candidate_conflict_ids: List[str],
    ) -> Dict[str, Any]:
        """T34①：把 `ThesisDraft.retained_conflicts[].conflict_id` 的取值域收紧为
        「本轮 bridge 实际给出的 conflict_id」∪ null 的 enum。

        真实事故（run 20260730_114704，本改动接替的 T31 假设的证伪证据）：旧判据
        是"要求模型把 bridge 的 conflict_id 原样抄进这个字段"，结果模型把
        `TC1_restrictive_macro_vs_moderate_valuation` 写成了
        `C1_restrictive_macro_vs_moderate_valuation`——后缀一字不差，前缀自行
        改写。这不是模型能力差，是机制选错了：靠"抄"字符串没有物理约束。改成
        enum 后模型只能从清单里选，物理上打不出清单外的值。

        `candidate_conflict_ids` 为空（本轮 bridge 一条 conflict_id 都没给）时，
        原样返回 schema，不注入任何 enum——`Conflict.conflict_id` 留空是"本站新
        发现的冲突"的合法表达（见 contracts.py 字段描述），注入空 enum 或
        `enum: [null]` 等于物理上禁止模型填任何编号，语义上说不通；部分 provider
        对空 enum 还会直接拒绝请求。
        """
        return self._constrain_conflict_id_enum_for_paths(
            schema,
            candidate_conflict_ids,
            (("retained_conflicts",),),
        )

    def _constrain_reviser_conflict_id_enum(
        self,
        schema: Dict[str, Any],
        candidate_conflict_ids: List[str],
    ) -> Dict[str, Any]:
        """T42④：reviser 输出的 `AnalysisRevised.revised_thesis` 与 `remaining_conflicts`
        都是 `Conflict` 结构，要重新产出同结构的 `conflict_id`。把 thesis 站已验证的
        enum 选单机制原样接到 reviser 站：模型只能从本轮 bridge 实际给出的编号里选，
        不能在抄写时自行改写前缀（T34 事故 `TC1_…` → `C1_…` 的重演路径就此物理关闭）。
        """
        return self._constrain_conflict_id_enum_for_paths(
            schema,
            candidate_conflict_ids,
            (
                ("revised_thesis", "retained_conflicts"),
                ("remaining_conflicts",),
            ),
        )

    def _validate_thesis_hypothesis_responses(
        self,
        thesis: ThesisDraft,
        synthesis_packet: SynthesisPacket,
    ) -> List[str]:
        """Require an auditable response for every non-downgraded competing hypothesis.

        触发集合（2026-07-27 T28）：从曾经的"仅 status == candidate"扩大为
        "status 不是 downgraded"，即 candidate / leading / split / kept_unresolved
        都要求逐一回应。动机：`_run_hypothesis_competition` 只要触发降级（受控调查
        提出挑战，或存在 fallback_warnings），就会把全部假说（含反方、含 base）
        统一改判为 kept_unresolved——旧触发集合下 candidate 集合因此归零，合约
        整体空转（四次真实 run 三次 candidate 数为 0），导致"越有争议的假说越
        不会被要求回应"。`downgraded` 是唯一表示"已被正式裁决出局"的状态，是这里
        唯一被豁免的状态；`kept_unresolved` 的语义是"没有胜出、张力未解决"，不等于
        "不需要被回应"——合格回应允许 `absorb_partially`（承认张力未解决），
        不强求 `accept_and_revise` 或 `reject`，否则"冲突是资产"会退化成逼模型
        对每条争议硬下结论。`reject` 无论对方状态是什么，仍必须带合法 evidence_ref。
        """
        errors: List[str] = []
        required_hypotheses = {
            hypothesis.hypothesis_id: hypothesis.status
            for hypothesis in synthesis_packet.competing_hypotheses
            if hypothesis.status != "downgraded"
        }
        responses_by_id: Dict[str, List[Any]] = {}
        for response in thesis.hypothesis_responses:
            responses_by_id.setdefault(response.hypothesis_id, []).append(response)

        for hypothesis_id in sorted(required_hypotheses):
            status = required_hypotheses[hypothesis_id]
            responses = responses_by_id.get(hypothesis_id, [])
            if not responses:
                errors.append(
                    f"competing hypothesis {hypothesis_id} (status={status}) is missing from hypothesis_responses."
                )
                continue
            if len(responses) > 1:
                errors.append(
                    f"competing hypothesis {hypothesis_id} (status={status}) has duplicate hypothesis_responses."
                )
                continue
            response = responses[0]
            if response.verdict != "reject":
                continue
            refs = [str(ref) for ref in response.evidence_refs]
            if not refs:
                errors.append(
                    f"hypothesis_responses[{hypothesis_id}] reject requires at least one evidence_ref."
                )
                continue
            invalid_refs = [ref for ref in refs if ref not in synthesis_packet.evidence_index]
            if invalid_refs:
                errors.append(
                    f"hypothesis_responses[{hypothesis_id}] reject contains refs outside evidence_index: "
                    f"{invalid_refs[:5]}"
                )
        return errors

    def _build_synthesis_packet(
        self,
        packet: AnalysisPacket,
        context_brief: ContextBrief,
        layer_cards: List[LayerCard],
        bridge_memos: List[BridgeMemo],
    ) -> SynthesisPacket:
        layer_summaries: List[LayerSynthesisItem] = []
        bridge_summaries: List[BridgeSynthesisItem] = []
        high_conflicts = []
        high_typed_conflicts = []
        principal_contradictions = []
        evidence_index: Dict[str, Dict[str, Any]] = {}

        for card in layer_cards:
            layer_label = getattr(card.layer, "value", str(card.layer))
            indicator_refs: List[str] = []
            key_evidence: List[str] = []
            for analysis in card.indicator_analyses:
                ref = f"{layer_label}.{analysis.function_id}"
                indicator_refs.append(ref)
                raw_payload = self._raw_payload_for_evidence_ref(packet, ref)
                field_authority = self._field_authority_from_payload(raw_payload)
                field_usages = self._field_authority_usages(field_authority)
                raw_quality = raw_payload.get("data_quality") if isinstance(raw_payload.get("data_quality"), dict) else {}
                evidence_item = {
                    "layer": layer_label,
                    "function_id": analysis.function_id,
                    "metric": analysis.metric,
                    "current_reading": analysis.current_reading,
                    "normalized_state": analysis.normalized_state,
                    "narrative": analysis.narrative,
                    "reasoning_process": analysis.reasoning_process,
                    "first_principles_chain": analysis.first_principles_chain,
                    "cross_layer_implications": analysis.cross_layer_implications,
                    "risk_flags": analysis.risk_flags,
                    "permission_type": _enum_value(analysis.permission_type),
                    "canonical_question": analysis.canonical_question,
                    "misread_guards": analysis.misread_guards,
                    "cross_validation_targets": analysis.cross_validation_targets,
                    "falsifiers": analysis.falsifiers,
                    "core_vs_tactical_boundary": analysis.core_vs_tactical_boundary,
                    "confidence": _enum_value(analysis.confidence),
                    "source_tier": raw_payload.get("source_tier") or raw_quality.get("source_tier"),
                    "mixed_field_authority": len(field_usages) > 1,
                }
                evidence_index[ref] = evidence_item
                value = raw_payload.get("value") if isinstance(raw_payload.get("value"), dict) else {}
                for field, field_rule in field_authority.items():
                    if not isinstance(field_rule, dict):
                        continue
                    evidence_index[f"{ref}#{field}"] = {
                        "layer": layer_label,
                        "function_id": analysis.function_id,
                        "metric": analysis.metric,
                        "parent_evidence_ref": ref,
                        "field_name": field,
                        "field_value": value.get(field),
                        "field_authority": field_rule,
                        "permission_type": _enum_value(analysis.permission_type),
                        "canonical_question": analysis.canonical_question,
                        "misread_guards": analysis.misread_guards,
                        "source_tier": evidence_item.get("source_tier"),
                    }
                if analysis.current_reading:
                    key_evidence.append(f"{analysis.metric}: {analysis.current_reading}")
                else:
                    key_evidence.append(f"{analysis.metric}: {analysis.narrative[:160]}")

            if not key_evidence:
                for fact in card.core_facts[:4]:
                    ref = f"{layer_label}.{fact.metric}"
                    indicator_refs.append(ref)
                    evidence_index[ref] = {
                        "layer": layer_label,
                        "metric": fact.metric,
                        "value": fact.value,
                        "historical_percentile": fact.historical_percentile,
                        "trend": _enum_value(fact.trend),
                        "magnitude": _enum_value(fact.magnitude),
                    }
                    key_evidence.append(f"{fact.metric}: {fact.value}")

            layer_summaries.append(
                LayerSynthesisItem(
                    layer=card.layer,
                    local_conclusion=card.local_conclusion,
                    layer_synthesis=card.layer_synthesis or card.notes,
                    indicator_refs=indicator_refs[:12],
                    key_evidence=key_evidence[:8],
                    risk_flags=card.risk_flags,
                    internal_conflict_analysis=card.internal_conflict_analysis,
                    cross_layer_hooks=[
                        f"{_enum_value(hook.target_layer)}: {hook.question}"
                        for hook in card.cross_layer_hooks
                    ],
                    confidence=card.confidence,
                )
            )

        for memo in bridge_memos:
            is_feedback_bridge = str(getattr(memo, "bridge_type", "")) == "feedback_bridge_v2"
            # H3: Include both high and medium severity conflicts so Thesis is aware
            # of all meaningful cross-layer tensions, not just the highest severity ones.
            if not is_feedback_bridge:
                high_conflicts.extend(
                    conflict for conflict in memo.conflicts if _severity_is_high_or_medium(conflict)
                )
                high_typed_conflicts.extend(
                    conflict for conflict in memo.typed_conflicts if _severity_is_high_or_medium(conflict)
                )
            if not is_feedback_bridge and getattr(memo, "principal_contradiction", None) is not None:
                principal_contradictions.append(memo.principal_contradiction)
            bridge_summaries.append(
                BridgeSynthesisItem(
                    bridge_type=memo.bridge_type,
                    layers_connected=memo.layers_connected,
                    key_claims=[] if is_feedback_bridge else [claim.claim for claim in memo.cross_layer_claims],
                    key_conflicts=[
                        f"{conflict.conflict_type}: {conflict.description}"
                        for conflict in memo.conflicts
                    ] if not is_feedback_bridge else [],
                    typed_conflicts=[] if is_feedback_bridge else [_model_dump(conflict) for conflict in memo.typed_conflicts],
                    resonance_chains=[] if is_feedback_bridge else [_model_dump(chain) for chain in memo.resonance_chains],
                    transmission_paths=[] if is_feedback_bridge else [_model_dump(path) for path in memo.transmission_paths],
                    principal_contradiction=(
                        None
                        if is_feedback_bridge
                        else _model_dump(memo.principal_contradiction) if getattr(memo, "principal_contradiction", None) is not None else None
                    ),
                    secondary_contradictions=[] if is_feedback_bridge else [_model_dump(item) for item in memo.secondary_contradictions],
                    price_reflection_map=[] if is_feedback_bridge else [_model_dump(item) for item in memo.price_reflection_map],
                    contradiction_transformation_signals=[] if is_feedback_bridge else [_model_dump(item) for item in memo.contradiction_transformation_signals],
                    unresolved_questions=memo.unresolved_questions,
                    event_refs=list(dict.fromkeys(getattr(memo, "event_refs", []) or [])),
                    implication_for_ndx=memo.implication_for_ndx,
                    key_uncertainties=memo.key_uncertainties,
                )
            )

        objective_firewall = self._build_objective_firewall_summary(packet, layer_cards, bridge_memos)

        return SynthesisPacket(
            packet_meta=packet.meta,
            context_summary=(
                f"{context_brief.data_summary} "
                f"{context_brief.task_description}"
            ).strip(),
            layer_summaries=layer_summaries,
            bridge_summaries=bridge_summaries,
            high_severity_conflicts=high_conflicts,
            high_severity_typed_conflicts=high_typed_conflicts,
            principal_contradictions=principal_contradictions,
            objective_firewall_summary=objective_firewall,
            evidence_index=evidence_index,
            event_index=packet.event_refs,
            synthesis_guidance=[
                "必须消费 objective_firewall_summary：若 object_clear、authority_clear、cross_layer_verified 任一为 false，主结论必须降置信度并保留警示。",
                "Thesis 只能整合 synthesis_packet，不得重新分析原始指标。",
                "必须保留 high_severity_conflicts，不能为了叙事流畅而抹平张力。",
                "必须显式消费 principal_contradictions / Bridge principal_contradiction：先判断当前主要矛盾，再判断价格是否已经反映风险，最后才给动作。",
                "必须显式消费 competing_hypotheses / hypothesis_competition_summary：正式综合前至少比较主线解释和反方解释；若证据不足，必须降级或保留争议。",
                "必须尊重 evidence_registry_summary：数据、事件、调查、假说和最终 claim 使用同一种 evidence id；弱权限证据不能越权支撑强结论。",
                "mixed_field_authority=true 的函数级父 evidence ref 只能表示混合容器；具体字段结论必须使用 evidence_index 中的 #FieldName 子 ref。",
                "Thesis / Final 的重要自然语言结论会进入 final_claim_ledger；缺证据、缺反证、缺失效条件或证据权限不足时必须降级。",
                "所有 key_support_chains 的 evidence_refs 必须来自 evidence_index 或 bridge_summaries。",
                "event_refs 与 evidence_refs 分离：事件只能写成解释/触发/观察背景，不能用来证明估值、广度、利率或趋势结论。",
            ],
        )

    def _build_objective_firewall_summary(
        self,
        packet: AnalysisPacket,
        layer_cards: List[LayerCard],
        bridge_memos: List[BridgeMemo],
    ) -> ObjectiveFirewallSummary:
        warnings: List[str] = []
        unresolved_tensions: List[str] = []
        falsifiers: List[str] = []

        # F3: Check investment object clarity — verify raw_data has expected L1-L5 layers
        # with actual content. If the packet is empty or has no layer data, object is unclear.
        # Note: raw_data keys are already uppercase "L1"-"L5" (set by packet_builder LAYER_NAMES).
        expected_layers = {"L1", "L2", "L3", "L4", "L5"}
        raw_data_layers = {
            layer
            for layer in expected_layers
            if _layer_has_usable_raw_data(packet.raw_data.get(layer))
        }
        # object_clear requires at least 3 of 5 layers to have data (partial data is acceptable
        # but complete absence suggests the investment object is not properly defined)
        object_clear = len(raw_data_layers) >= 3
        if not object_clear:
            present = sorted(raw_data_layers) if raw_data_layers else ["none"]
            warnings.append(
                f"Investment object unclear: only {len(raw_data_layers)}/5 layers "
                f"have data ({', '.join(present)}). Expected L1-L5 coverage."
            )

        known_items = []
        for card in layer_cards:
            for item in card.indicator_analyses:
                try:
                    get_indicator_canon(item.function_id)
                except KeyError:
                    continue
                known_items.append(item)

        authority_clear = all(
            item.permission_type
            and item.canonical_question
            and item.misread_guards
            and item.cross_validation_targets
            and item.falsifiers
            for item in known_items
        )
        if known_items and not authority_clear:
            warnings.append("Some known indicators are missing permission or falsifier fields.")
        authority_overreach = self._find_indicator_authority_overreach(known_items)
        if authority_overreach:
            authority_clear = False
            for issue in authority_overreach:
                warnings.append(
                    "Indicator authority overreach: "
                    f"{issue['function_id']} ({issue['permission_type']}) -> {issue['rule_id']}"
                )
        for item in known_items:
            falsifiers.extend(item.falsifiers)

        structural_bridge_memos = [
            memo
            for memo in bridge_memos
            if str(getattr(memo, "bridge_type", "")) != "feedback_bridge_v2"
        ]
        typed_conflicts = [
            conflict
            for memo in structural_bridge_memos
            for conflict in memo.typed_conflicts
        ]
        legacy_conflicts = [
            conflict
            for memo in structural_bridge_memos
            for conflict in memo.conflicts
        ]
        # F4: cross_layer_verified means "bridge has verified cross-layer logic",
        # i.e. bridge memos exist and contain meaningful cross-layer analysis.
        # Previously this was inverted: conflicts present → True, no conflicts → False.
        cross_layer_verified = bool(bridge_memos)
        if not cross_layer_verified:
            warnings.append("No bridge memos produced; cross-layer logic cannot be verified.")

        for conflict in typed_conflicts:
            if str(_enum_value(conflict.severity)) == "high" or conflict.status == "unresolved":
                unresolved_tensions.append(f"{conflict.conflict_id}: {conflict.description}")
            falsifiers.extend(conflict.falsifiers)
        for conflict in legacy_conflicts:
            if str(_enum_value(conflict.severity)) == "high":
                unresolved_tensions.append(f"{conflict.conflict_type}: {conflict.description}")

        data_date = packet.meta.get("data_date") or packet.meta.get("timestamp_utc")
        timing_clear = bool(data_date) or not packet.meta
        if not timing_clear:
            warnings.append("Packet has no data_date or timestamp_utc; timing alignment cannot be verified.")

        return ObjectiveFirewallSummary(
            object_clear=object_clear,
            authority_clear=authority_clear if known_items else False,
            timing_clear=timing_clear,
            cross_layer_verified=cross_layer_verified,
            strongest_falsifier=falsifiers[0] if falsifiers else "",
            unresolved_tensions=unresolved_tensions,
            warnings=warnings,
        )

    def _find_indicator_authority_overreach(self, items: List[Any]) -> List[Dict[str, str]]:
        issues: List[Dict[str, str]] = []
        for item in items:
            permission_type = str(_enum_value(getattr(item, "permission_type", "")) or "").strip().lower()
            rules = _AUTHORITY_OVERREACH_RULES.get(permission_type, [])
            if not rules:
                continue
            text = self._indicator_authority_text(item)
            for pattern, rule_id in rules:
                if re.search(pattern, text, flags=re.IGNORECASE):
                    issues.append(
                        {
                            "function_id": str(getattr(item, "function_id", "unknown")),
                            "permission_type": permission_type,
                            "rule_id": rule_id,
                        }
                    )
                    break
        return issues

    def _indicator_authority_text(self, item: Any) -> str:
        fields = [
            getattr(item, "current_reading", ""),
            getattr(item, "normalized_state", ""),
            getattr(item, "narrative", ""),
            getattr(item, "reasoning_process", ""),
        ]
        for list_field in ("first_principles_chain", "cross_layer_implications", "risk_flags"):
            value = getattr(item, list_field, [])
            if isinstance(value, list):
                fields.extend(str(part) for part in value)
            else:
                fields.append(str(value))
        return "\n".join(str(field) for field in fields if field)

    def _build_governance_input_packet(
        self,
        synthesis_packet: SynthesisPacket,
        thesis: ThesisDraft,
        critique: Optional[Critique] = None,
        risk_report: Optional[RiskBoundaryReport] = None,
        schema_report: Optional[SchemaGuardReport] = None,
        analysis_revised: Optional[AnalysisRevised] = None,
        layer_cards: Optional[List[LayerCard]] = None,
        consumer: str = "critic",
    ) -> GovernanceInputPacket:
        """Build a compressed governance input packet for Critic / Risk / Reviser / Final.

        Reduces token bloat by only including what governance stages need:
        - Thesis essentials (not full artifact)
        - High severity typed conflicts (must not be lost)
        - Objective firewall summary
        - Schema guard essentials
        - Must-preserve risks
        - Thesis support chains and their evidence refs
        - Key evidence refs (subset related to high-severity conflicts and thesis support chains)
        - Known data gaps (especially L3 breadth)

        consumer="critic" 保持既有行为不变。
        consumer="reviser"/"final" = 基础同 critic（含 counter 原文与反证引用），
        但去噪音：synthesis_guidance/pricing_expectation_ledger/
        evidence_registry_summary 清空，key_evidence_refs 的 field_value 超长明细
        递归压成 _prompt_summary。
        终审口径（2026-08-16 老板重裁）：final 只收修订稿 + revision_summary；
        原稿不进终审输入，只落盘供审计——thesis_original 已从本包移除。
        consumer="risk" = 论证盲分料版：thesis_* 字段在构造时清空，并在序列化进
        payload 时（_dump_governance_input）整个移除这些键——空键残留同样算分料泄漏；
        事实面由 layer_summaries + 冲突面 + Bridge 主要矛盾候选提供，key_evidence_refs
        只从冲突 evidence_refs 与 layer_summaries.indicator_refs 重建，不从 thesis
        支撑链/假说回应/仓位/时间尺度/读者结论里收集；counter_thesis_hypotheses 恒空。
        """
        # ── Thesis summary ──
        thesis_confidence = getattr(thesis.overall_confidence, "value", str(thesis.overall_confidence)) if thesis.overall_confidence else "medium"
        retained_conflict_types = [
            getattr(conflict, "conflict_type", str(conflict))
            for conflict in thesis.retained_conflicts
        ]

        # ── Key evidence refs: high-severity conflicts plus Thesis support chains ──
        all_evidence_refs: set = set()
        all_event_refs: set = set()
        for conflict in synthesis_packet.high_severity_typed_conflicts:
            refs = getattr(conflict, "evidence_refs", []) if hasattr(conflict, "evidence_refs") else conflict.get("evidence_refs", [])
            all_evidence_refs.update(refs)
            event_refs = getattr(conflict, "event_refs", []) if hasattr(conflict, "event_refs") else conflict.get("event_refs", [])
            all_event_refs.update(event_refs)

        # Also collect event_refs from bridge summaries (Bridge may have marked
        # events at the memo level that don't appear in typed conflicts).
        for bridge_summary in synthesis_packet.bridge_summaries:
            all_event_refs.update(bridge_summary.get("event_refs", []) if isinstance(bridge_summary, dict) else getattr(bridge_summary, "event_refs", []) or [])

        # ── Counter thesis 原文与反证引用（拍板③ + T46）：critic/reviser/final
        #    把来源为 counter_thesis 的假说原文带上，并把三类 evidence_refs 并入
        #    all_evidence_refs；risk 论证盲不并（它只从 risk_evidence_refs 取）。 ──
        counter_thesis_hypotheses: List[Dict[str, Any]] = []
        counter_thesis_evidence_refs: set = set()
        for hypothesis in getattr(synthesis_packet, "competing_hypotheses", []) or []:
            if isinstance(hypothesis, dict):
                hypothesis_dict = dict(hypothesis)
            else:
                hypothesis_dict = _model_dump(hypothesis) or {}
            if hypothesis_dict.get("source") != "counter_thesis":
                continue
            support_refs = list(hypothesis_dict.get("support_evidence_refs") or [])
            counter_refs = list(hypothesis_dict.get("counter_evidence_refs") or [])
            diagnostic_refs = list(hypothesis_dict.get("diagnostic_evidence_refs") or [])
            counter_thesis_hypotheses.append({
                "hypothesis_id": hypothesis_dict.get("hypothesis_id"),
                "hypothesis_text": hypothesis_dict.get("hypothesis_text"),
                "status": hypothesis_dict.get("status"),
                "support_evidence_refs": support_refs,
                "counter_evidence_refs": counter_refs,
                "diagnostic_evidence_refs": diagnostic_refs,
            })
            counter_thesis_evidence_refs.update(support_refs)
            counter_thesis_evidence_refs.update(counter_refs)
            counter_thesis_evidence_refs.update(diagnostic_refs)
        all_evidence_refs.update(counter_thesis_evidence_refs)

        # ── Risk = 论证盲：key_evidence_refs 只从冲突面 + Bridge 主要矛盾候选 + 各层
        #    摘要的 indicator_refs 重建，绝不从 thesis 支撑链、假说回应、仓位、时间尺度、
        #    读者结论里收集（配餐单 v0 第四节第 1 条）。 ──
        risk_evidence_refs: set = set()
        for conflict in synthesis_packet.high_severity_typed_conflicts:
            refs = (
                getattr(conflict, "evidence_refs", [])
                if hasattr(conflict, "evidence_refs")
                else conflict.get("evidence_refs", [])
            )
            risk_evidence_refs.update(refs or [])
        for conflict in synthesis_packet.high_severity_conflicts:
            # 普通 Conflict 契约没有 evidence_refs，getattr 兜底空列表；保留遍历是为了
            # 将来契约补字段时这里自动生效，且与任务书"typed 与普通 conflict"口径一致。
            risk_evidence_refs.update(getattr(conflict, "evidence_refs", []) or [])
        for contradiction in getattr(synthesis_packet, "principal_contradictions", []) or []:
            refs = (
                getattr(contradiction, "evidence_refs", [])
                if hasattr(contradiction, "evidence_refs")
                else contradiction.get("evidence_refs", [])
            )
            risk_evidence_refs.update(refs or [])
        for summary in getattr(synthesis_packet, "layer_summaries", []) or []:
            indicator_refs = getattr(summary, "indicator_refs", []) or []
            risk_evidence_refs.update(indicator_refs[:12])  # 最多 12 个/层

        thesis_key_support_chains = [_model_dump(chain) for chain in thesis.key_support_chains]
        thesis_hypothesis_responses = list(getattr(thesis, "hypothesis_responses", []) or [])
        for chain in thesis.key_support_chains:
            all_evidence_refs.update(chain.evidence_refs)
            all_event_refs.update(getattr(chain, "event_refs", []) or [])
        for response in thesis_hypothesis_responses:
            all_evidence_refs.update(response.evidence_refs)
        for action in getattr(thesis, "portfolio_actions", []) or []:
            all_evidence_refs.update(getattr(action, "evidence_refs", []) or [])
        for view in getattr(thesis, "time_horizon_views", []) or []:
            all_evidence_refs.update(getattr(view, "evidence_refs", []) or [])
        reader_conclusion = _model_dump(getattr(thesis, "reader_conclusion", {}) or {})
        if isinstance(reader_conclusion, dict):
            all_evidence_refs.update(reader_conclusion.get("evidence_refs", []) or [])
        thesis_principal_contradiction = _model_dump(getattr(thesis, "principal_contradiction", None))
        if not isinstance(thesis_principal_contradiction, dict):
            thesis_principal_contradiction = None
        thesis_secondary_contradictions = [
            _model_dump(item) for item in getattr(thesis, "secondary_contradictions", []) or []
        ]
        thesis_price_reflection_map = [
            _model_dump(item) for item in getattr(thesis, "price_reflection_map", []) or []
        ]
        for item in [thesis_principal_contradiction] + thesis_secondary_contradictions + thesis_price_reflection_map:
            if isinstance(item, dict):
                all_evidence_refs.update(item.get("evidence_refs", []) or [])
                all_evidence_refs.update(item.get("counterevidence_refs", []) or [])

        evidence_refs_for_packet = risk_evidence_refs if consumer == "risk" else all_evidence_refs
        key_evidence_refs: Dict[str, Dict[str, Any]] = {}
        for ref in sorted(evidence_refs_for_packet):
            if ref in synthesis_packet.evidence_index:
                key_evidence_refs[ref] = synthesis_packet.evidence_index[ref]

        key_event_refs: Dict[str, Dict[str, Any]] = {}
        if consumer != "risk":
            for ref in sorted(all_event_refs):
                if ref in synthesis_packet.event_index:
                    key_event_refs[ref] = synthesis_packet.event_index[ref]

        # ── Known data gaps: collect from layer cards, schema, and bridge ──
        known_data_gaps: List[str] = []
        if layer_cards:
            for card in layer_cards:
                if card.quality_self_check:
                    missing = getattr(card.quality_self_check, "missing_or_weak_indicators", [])
                    known_data_gaps.extend(missing)

        if schema_report is not None:
            if schema_report.structural_issues:
                known_data_gaps.extend(f"[schema] {issue}" for issue in schema_report.structural_issues)
            if schema_report.missing_fields:
                known_data_gaps.extend(f"[schema] {field}" for field in schema_report.missing_fields)

        # L3 广度缺失（特别重要）
        if layer_cards:
            for card in layer_cards:
                layer_label = getattr(card.layer, "value", str(card.layer))
                if layer_label == "L3":
                    l3_warnings = [f"[L3] {flag}" for flag in card.risk_flags if "breadth" in flag.lower() or "结构" in flag]
                    if l3_warnings:
                        known_data_gaps.extend(l3_warnings)

        # Bridge 未解决问题
        unresolved_questions: List[str] = []
        for bridge_summary in synthesis_packet.bridge_summaries:
            unresolved = bridge_summary.unresolved_questions if bridge_summary.unresolved_questions else []
            unresolved_questions.extend(unresolved)

        # ── Schema guard summary ──
        schema_passed = schema_report.passed if schema_report is not None else True
        schema_structural = schema_report.structural_issues if schema_report is not None else []
        schema_consistency = schema_report.consistency_issues if schema_report is not None else []
        schema_missing = schema_report.missing_fields if schema_report is not None else []

        # ── Must-preserve risks (from Risk Sentinel, if available) ──
        must_preserve_risks = list(risk_report.must_preserve_risks) if risk_report is not None else []
        opportunity_costs = [_model_dump(item) for item in getattr(risk_report, "opportunity_costs", [])] if risk_report is not None else []
        confirmation_costs = [_model_dump(item) for item in getattr(risk_report, "confirmation_costs", [])] if risk_report is not None else []
        false_safety_risks = list(getattr(risk_report, "false_safety_risks", []) or []) if risk_report is not None else []

        # ── Critique summary (for reviser / final) ──
        critique_overall = critique.overall_assessment if critique is not None else None
        critique_cross_layer = critique.cross_layer_issues if critique is not None else []

        # ── Revision summary (for final) ──
        revision_summary = analysis_revised.revision_summary if analysis_revised is not None else None

        # ── Objective firewall ──
        obj_firewall = _model_dump(synthesis_packet.objective_firewall_summary) if synthesis_packet.objective_firewall_summary is not None else None

        # ── Typed conflicts as dicts ──
        high_severity_typed = [_model_dump(conflict) for conflict in synthesis_packet.high_severity_typed_conflicts]
        principal_contradictions = [
            _model_dump(item) for item in getattr(synthesis_packet, "principal_contradictions", []) or []
        ]

        # 配餐单 v0（所有者过目定稿）：pricing_expectation_ledger 自标
        # supporting_only / forbidden_as_core_ref，critic/risk/reviser/final
        # 四个治理站提示词都不把它列为输入，一律不给；台账留磁盘审计。
        pricing_expectation_ledger: Dict[str, Any] = {}

        if consumer == "risk":
            # ── risk = 论证盲：只给事实面与冲突面。thesis 字段这里仍按契约填空值，
            #    序列化进 payload 时由 _dump_governance_input 把这些键整个移除。 ──
            return GovernanceInputPacket(
                thesis_main="",
                thesis_environment="",
                thesis_valuation="",
                thesis_timing="",
                thesis_confidence="",
                thesis_dependencies=[],
                thesis_key_support_chains=[],
                thesis_hypothesis_responses=[],
                retained_conflict_types=[],
                thesis_state_diagnosis="",
                thesis_priced_narrative="",
                thesis_payoff_assessment="",
                thesis_time_horizon_views=[],
                thesis_portfolio_actions=[],
                thesis_confirmation_cost="",
                thesis_invalidation_conditions=[],
                thesis_reader_conclusion={},
                thesis_principal_contradiction=None,
                thesis_secondary_contradictions=[],
                thesis_price_reflection_map=[],
                layer_summaries=[_model_dump(item) for item in getattr(synthesis_packet, "layer_summaries", []) or []],
                high_severity_typed_conflicts=high_severity_typed,
                principal_contradictions=principal_contradictions,
                objective_firewall_summary=obj_firewall,
                schema_passed=schema_passed,
                schema_structural_issues=list(schema_structural),
                schema_consistency_issues=list(schema_consistency),
                schema_missing_fields=list(schema_missing),
                must_preserve_risks=must_preserve_risks,
                opportunity_costs=opportunity_costs,
                confirmation_costs=confirmation_costs,
                false_safety_risks=false_safety_risks,
                key_evidence_refs=key_evidence_refs,
                key_event_refs={},
                evidence_registry_summary={},
                pricing_expectation_ledger=pricing_expectation_ledger,
                known_data_gaps=list(dict.fromkeys(known_data_gaps)),  # 去重
                unresolved_questions=list(dict.fromkeys(unresolved_questions)),  # 去重
                synthesis_guidance=[],
                critique_overall=critique_overall,
                critique_cross_layer_issues=list(critique_cross_layer),
                revision_summary=revision_summary,
                counter_thesis_hypotheses=[],
            )

        if consumer in {"reviser", "final"}:
            # 08-15 已批：reviser/final 去噪音字段 + 证据索引瘦身。ref key 集合不动，
            # 只压 field_value 里 >8 条且 >800 字符的超长明细列表。
            evidence_registry_summary_packet: Dict[str, Any] = {}
            synthesis_guidance_packet: List[str] = []
            key_evidence_refs = self._slim_governance_key_evidence_refs(key_evidence_refs)
        else:
            evidence_registry_summary_packet = dict(getattr(synthesis_packet, "evidence_registry_summary", {}) or {})
            synthesis_guidance_packet = list(synthesis_packet.synthesis_guidance) if synthesis_packet.synthesis_guidance else []

        return GovernanceInputPacket(
            thesis_main=thesis.main_thesis or "",
            thesis_environment=thesis.environment_assessment or "",
            thesis_valuation=thesis.valuation_assessment or "",
            thesis_timing=thesis.timing_assessment or "",
            thesis_confidence=thesis_confidence,
            thesis_dependencies=list(thesis.dependencies) if thesis.dependencies else [],
            thesis_key_support_chains=thesis_key_support_chains,
            thesis_hypothesis_responses=thesis_hypothesis_responses,
            retained_conflict_types=retained_conflict_types,
            thesis_state_diagnosis=getattr(thesis, "state_diagnosis", "") or "",
            thesis_priced_narrative=getattr(thesis, "priced_narrative", "") or "",
            thesis_payoff_assessment=getattr(thesis, "payoff_assessment", "") or "",
            thesis_time_horizon_views=[_model_dump(item) for item in getattr(thesis, "time_horizon_views", []) or []],
            thesis_portfolio_actions=[_model_dump(item) for item in getattr(thesis, "portfolio_actions", []) or []],
            thesis_confirmation_cost=getattr(thesis, "confirmation_cost", "") or "",
            thesis_invalidation_conditions=list(getattr(thesis, "invalidation_conditions", []) or []),
            thesis_reader_conclusion=reader_conclusion if isinstance(reader_conclusion, dict) else {},
            thesis_principal_contradiction=thesis_principal_contradiction,
            thesis_secondary_contradictions=thesis_secondary_contradictions,
            thesis_price_reflection_map=thesis_price_reflection_map,
            high_severity_typed_conflicts=high_severity_typed,
            principal_contradictions=principal_contradictions,
            objective_firewall_summary=obj_firewall,
            schema_passed=schema_passed,
            schema_structural_issues=list(schema_structural),
            schema_consistency_issues=list(schema_consistency),
            schema_missing_fields=list(schema_missing),
            must_preserve_risks=must_preserve_risks,
            opportunity_costs=opportunity_costs,
            confirmation_costs=confirmation_costs,
            false_safety_risks=false_safety_risks,
            key_evidence_refs=key_evidence_refs,
            key_event_refs=key_event_refs,
            evidence_registry_summary=evidence_registry_summary_packet,
            pricing_expectation_ledger=pricing_expectation_ledger,
            known_data_gaps=list(dict.fromkeys(known_data_gaps)),  # 去重
            unresolved_questions=list(dict.fromkeys(unresolved_questions)),  # 去重
            synthesis_guidance=synthesis_guidance_packet,
            critique_overall=critique_overall,
            critique_cross_layer_issues=list(critique_cross_layer),
            revision_summary=revision_summary,
            counter_thesis_hypotheses=counter_thesis_hypotheses,
        )

    def _pricing_expectation_ledger_summary(self, synthesis_packet: SynthesisPacket) -> Dict[str, Any]:
        """Expose a compact PIT-matched supporting ledger only to governance stages."""
        ledger = self._load_local_json(self.output_dir / "expectation_vs_realized.json", {})
        if not isinstance(ledger, dict) or not ledger:
            return {}
        authority = str(ledger.get("metric_authority") or "")
        effective_date = str(ledger.get("effective_date") or "")[:10]
        packet_date = str(
            synthesis_packet.packet_meta.get("data_date")
            or synthesis_packet.packet_meta.get("backtest_date")
            or synthesis_packet.packet_meta.get("effective_date")
            or ""
        )[:10]
        boundary = {
            "artifact_ref": "expectation_vs_realized.json",
            "metric_authority": authority or "missing",
            "effective_date": effective_date or None,
            "packet_effective_date": packet_date or None,
            "downgrade_rules": list(ledger.get("downgrade_rules") or []),
            "usage_rule": "pricing_narrative_support_only; forbidden_as_core_ref",
        }
        try:
            ledger_day = datetime.strptime(effective_date, "%Y-%m-%d").date()
        except ValueError:
            return {**boundary, "status": "audit_only_invalid_effective_date"}
        if authority != "supporting_only":
            return {**boundary, "status": "rejected_authority_mismatch"}
        if packet_date and effective_date != packet_date:
            return {**boundary, "status": "audit_only_effective_date_mismatch"}

        earnings = ledger.get("earnings_expectations") if isinstance(ledger.get("earnings_expectations"), dict) else {}
        earnings_windows = []
        for window in _as_list(earnings.get("windows")):
            if not isinstance(window, dict):
                continue
            earnings_windows.append({
                key: window.get(key)
                for key in (
                    "window_days",
                    "status",
                    "target_date",
                    "prior_snapshot_date",
                    "actual_elapsed_days",
                    "intersection_ticker_count",
                    "average_change_pct",
                    "note",
                )
            })
        rate = ledger.get("rate_path") if isinstance(ledger.get("rate_path"), dict) else {}
        current_path = rate.get("current_path") if isinstance(rate.get("current_path"), dict) else None
        current_path_date = str((current_path or {}).get("effective_date") or "")[:10]
        if current_path:
            try:
                current_path_day = datetime.strptime(current_path_date, "%Y-%m-%d").date()
            except ValueError:
                current_path_day = None
            if current_path_day is None or current_path_day > ledger_day:
                return {
                    **boundary,
                    "status": "audit_only_nested_rate_path_date_mismatch",
                    "rate_path_effective_date": current_path_date or None,
                }
        volatility = ledger.get("volatility_premium") if isinstance(ledger.get("volatility_premium"), dict) else {}
        return {
            **boundary,
            "status": str(ledger.get("status") or "available_for_supporting_use"),
            "earnings_expectations": {
                "status": earnings.get("status"),
                "current_snapshot_date": earnings.get("current_snapshot_date"),
                "current_ticker_count": earnings.get("current_ticker_count"),
                "windows": earnings_windows,
            },
            "rate_path": {
                "status": rate.get("status"),
                "current_path": current_path,
                "current_path_status": rate.get("current_path_status"),
                "historical_path_count_eligible": rate.get("historical_path_count_eligible"),
                "comparisons": _as_list(rate.get("comparisons"))[-12:],
                "note": rate.get("note"),
            },
            "volatility_premium": {
                "status": volatility.get("status"),
                "window_trading_days": volatility.get("window_trading_days"),
                "sample_count": volatility.get("sample_count"),
                "recent_premium_pct_points": volatility.get("recent_premium_pct_points"),
                "recent_percentile": volatility.get("recent_percentile"),
                "note": volatility.get("note"),
            },
        }

    def _build_context_brief(self, packet: AnalysisPacket) -> ContextBrief:
        layer_highlights: Dict[str, List[str]] = {}
        special_attention: List[str] = []
        for layer in ["L1", "L2", "L3", "L4", "L5"]:
            facts = packet.facts_by_layer.get(layer)
            summaries = []
            if facts:
                summaries = [item.get("summary", "") for item in facts.core_signals[:3] if item.get("summary")]
                if not summaries and facts.summary:
                    summaries = [facts.summary]
            layer_highlights[layer] = summaries
        for link in packet.candidate_cross_layer_links[:4]:
            special_attention.append(link.description)
        return ContextBrief(
            data_summary=(
                f"运行时点 {packet.meta.get('data_date')}，"
                f"共 {packet.meta.get('indicator_successful', 0)}/{packet.meta.get('indicator_total', 0)} 个指标成功。"
                "各指标实际数据日期以各自 data_quality.data_date / effective_date 为准："
                "早于运行时点属正常时点纪律，不要求与运行时点同一天。"
            ),
            layer_highlights=layer_highlights,
            apparent_cross_layer_signals=[link.description for link in packet.candidate_cross_layer_links[:4]],
            task_description="基于五层框架完成 Layer -> Bridge -> Thesis -> Governance -> Final 的完整分析链路。",
            special_attention=special_attention or ["检查高严重度冲突是否被完整保留。"],
        )

    def _build_layer_context_brief(self, packet: AnalysisPacket, context_brief: ContextBrief, layer: str) -> ContextBrief:
        """Build a layer-local brief for L1-L5 analysts.

        Layer analysts should not see other layers' current readings or Python-generated
        cross-layer state claims before they form their own local interpretation.
        Bridge and later stages still receive the global context brief.
        """
        layer = layer.upper()
        layer_highlights = {
            layer: list(context_brief.layer_highlights.get(layer, []))
        }
        return ContextBrief(
            data_summary=self._build_layer_data_summary(packet, layer),
            layer_highlights=layer_highlights,
            apparent_cross_layer_signals=[],
            task_description=(
                f"只完成 {layer} 的本层分析：先基于本层数据生成指标级推理，"
                "再输出本层综合、层内冲突和需要 Bridge 后续验证的问题。"
            ),
            special_attention=[
                "可以使用静态五层职责边界来路由验证问题，但不要读取或推断其他层当前状态。",
                "不得因为最终报告需要完整结论而提前吸收其他层叙事。",
            ],
        )

    def _build_layer_data_summary(self, packet: AnalysisPacket, layer: str) -> str:
        """Return a data summary scoped to the current layer only."""
        layer_data = packet.raw_data.get(layer, {})
        if not isinstance(layer_data, dict):
            total = 0
            successful = 0
        else:
            total = sum(1 for item in layer_data.values() if isinstance(item, dict))
            successful = sum(
                1
                for item in layer_data.values()
                if isinstance(item, dict) and not item.get("error")
            )
        return (
            f"运行时点 {packet.meta.get('data_date')}，"
            f"{layer} 本层 {successful}/{total} 个指标成功。"
            "各指标实际数据日期以各自 data_quality.data_date / effective_date 为准："
            "早于运行时点属正常时点纪律（月度指标滞后发布等），不要求与运行时点同一天。"
        )

    def _build_layer_manual_overrides(self, packet: AnalysisPacket, layer: str) -> Dict[str, Any]:
        """Filter manual overrides so layer analysts only see metrics in their own layer."""
        overrides = packet.manual_overrides if isinstance(packet.manual_overrides, dict) else {}
        if not overrides.get("active"):
            return {
                "active": False,
                "date": overrides.get("date", ""),
                "metrics": {},
            }
        layer_data = packet.raw_data.get(layer, {})
        layer_function_ids = set(layer_data.keys()) if isinstance(layer_data, dict) else set()
        metrics = overrides.get("metrics", {}) if isinstance(overrides.get("metrics"), dict) else {}
        return {
            "active": bool(overrides.get("active")),
            "date": overrides.get("date", ""),
            "metrics": {
                function_id: metric
                for function_id, metric in metrics.items()
                if function_id in layer_function_ids
            },
        }

    def _purify_bridge_context_brief(self, context_brief: ContextBrief) -> ContextBrief:
        """拍板⑤：bridge payload 的 context_brief 换净化副本。

        去掉 Python 预生成的跨层信号与各层摘要，Bridge 只能从五张层卡自己找跨层
        关系；全局 context_brief.json 落盘不动。
        """
        return ContextBrief(
            data_summary=context_brief.data_summary,
            layer_highlights={},
            apparent_cross_layer_signals=[],
            task_description=context_brief.task_description,
            special_attention=["检查高严重度冲突是否被完整保留。"],
            generated_at=getattr(context_brief, "generated_at", None),
        )

    def _run_stage(
        self,
        *,
        stage_key: str,
        stage_name: str,
        model_cls: Type[Any],
        payload: Dict[str, Any],
        validator: Optional[Callable[[Any], List[str]]] = None,
        pre_validate_transform: Optional[Callable[[Dict[str, Any]], Dict[str, Any]]] = None,
        strict_tool_schema: Optional[Dict[str, Any]] = None,
        strict_tool_name: Optional[str] = None,
        raw_text_fallback: Optional[Callable[[str, str], Optional[Any]]] = None,
    ) -> Any:
        """`raw_text_fallback`（T36 新增，默认 None，其余调用点不传，行为逐字节不变）：
        全部尝试耗尽、即将抛 RuntimeError 前的最后一道兜底，只对"结构本身就没能
        解析"的失败开放——不放松任何一条内容合法性判据。签名是
        `(last_raw_response_text, last_error_kind) -> Optional[model_cls 实例]`：
        返回非 None 就当作本次调用的正常结果收下（写审计、标记 degraded_fallback，
        不再抛异常）；返回 None 就维持原样抛出 RuntimeError。调用方必须自己判断
        `last_error_kind`（如只接受 "parse_error"），不能替它兜底——`_run_stage`
        本身不改变判定 parse_error / schema_validation_error / contract_validation_error
        的既有逻辑，只是把"耗尽后怎么办"这一步交还给调用方。"""
        prompt = self._compose_prompt(stage_key, model_cls, payload)
        preferred_models = self._preferred_models_for_stage(stage_key)
        last_error = ""
        last_raw_response = ""
        stage_record: Dict[str, Any] = {
            "stage_key": stage_key,
            "stage_name": stage_name,
            "attempts": 0,
            "errors": [],
            "prompt_chars": len(prompt),
            "status": "running",
            # T44④：留痕该站本次实际是否启用了 DeepSeek strict tool schema——
            # 反映调用方这次真传没传 strict_tool_schema，不是猜测的全局值。
            "strict_tool_schema_enabled": strict_tool_schema is not None,
            "model_routing": {
                "schema_version": self.stage_model_routing.get("schema_version", ""),
                "active_mode": self.stage_model_routing.get("active_mode", "default"),
                "preferred_models": preferred_models,
                "fallback_chain": [model for model in self.available_models if model not in preferred_models],
            },
            "prompt_audit": {
                "stage_dir": self._prompt_audit_relpath(stage_name),
                "attempts": [],
            },
        }
        self.stage_diagnostics["stages"][stage_name] = stage_record
        self._save_stage_diagnostics()
        for attempt in range(1, self.max_node_retries + 1):
            stage_record["attempts"] = attempt
            active_prompt = prompt
            if last_error:
                active_prompt = (
                    f"{prompt}\n\n上一次返回未通过结构校验，错误如下：\n{last_error}\n"
                    "请仅输出修正后的 JSON 对象，不要附加任何解释。"
                )
            attempt_record = self._capture_prompt_attempt(
                stage_key=stage_key,
                stage_name=stage_name,
                attempt=attempt,
                active_prompt=active_prompt,
                payload=payload,
                retry_feedback=last_error,
            )
            stage_record["prompt_chars"] = len(active_prompt)
            stage_record["prompt_audit"]["attempts"].append(attempt_record)
            stage_record["prompt_audit"]["latest_prompt_file"] = attempt_record["prompt_file"]
            self._save_stage_diagnostics()
            # strict_tool_schema 只在明确传入时才加进调用参数——绝大多数 stage 从不
            # 传它，这条路径与改动前逐字节相同，不影响任何既有 stage 或测试用的
            # 简化版 fake engine（它们的 call_with_fallback 大多不接受这个新参数）。
            call_kwargs: Dict[str, Any] = {
                "stage_name": stage_name,
                "preferred_models": preferred_models or None,
            }
            if strict_tool_schema is not None:
                call_kwargs["strict_tool_schema"] = strict_tool_schema
                call_kwargs["strict_tool_name"] = strict_tool_name or f"emit_{stage_key}_output"
            try:
                raw = self.llm_engine.call_with_fallback(active_prompt, **call_kwargs)
            except TypeError:
                raw = self.llm_engine.call_with_fallback(active_prompt, stage_name=stage_name)
            last_raw_response = str(raw or "")
            self._save_prompt_audit_text(stage_name, f"attempt_{attempt}.response.raw.txt", str(raw or ""))
            attempt_record["raw_response_file"] = self._prompt_audit_relpath(
                stage_name,
                f"attempt_{attempt}.response.raw.txt",
            )
            self._write_prompt_stage_meta(stage_name, stage_record)
            if not raw:
                last_error = f"{stage_name} received empty response"
                stage_record["errors"].append({"attempt": attempt, "kind": "empty_response", "message": last_error})
                self._write_prompt_stage_meta(stage_name, stage_record)
                self._save_stage_diagnostics()
                continue
            parsed = self.llm_engine.extract_json(raw, stage_name)
            if not isinstance(parsed, dict):
                raw_text = str(raw or "")
                tail = raw_text[-400:]
                # T47：先尝试定位真实解析错误——旧反馈无条件把嫌疑指向"末尾未闭合"，
                # 但真实事故（run 20260731_002156）里错误在第 3 行的未转义双引号、
                # 末尾语法完好，那句指引把模型指去了没有错的地方。拿到真实定位时
                # 以它为主、末尾片段降为次要参考；拿不到时（测试用简化 engine 没有
                # diagnose_json_error 方法，或块本身是合法 JSON 但不是对象、拿不到
                # JSONDecodeError）回退到原有末尾片段行为。
                diagnosis = None
                diagnose = getattr(self.llm_engine, "diagnose_json_error", None)
                if callable(diagnose):
                    try:
                        diagnosis = diagnose(raw_text)
                    except Exception:
                        diagnosis = None
                if diagnosis:
                    last_error = (
                        f"{stage_name} did not return a parseable JSON object."
                        f" 原始响应字符数: {len(raw_text)}."
                        f" {diagnosis}"
                        f" 响应末尾片段（次要参考——真实错误位置以上面定位为准，未必在末尾）：\n{tail}"
                    )
                else:
                    last_error = (
                        f"{stage_name} did not return a parseable JSON object."
                        f" 原始响应字符数: {len(raw_text)}."
                        f" 响应末尾片段（用于定位 JSON 语法错误，请检查最后未闭合的数组、对象或字符串）：\n{tail}"
                    )
                stage_record["errors"].append(
                    {
                        "attempt": attempt,
                        "kind": "parse_error",
                        "message": last_error[:1500],
                        "raw_excerpt": raw_text[:500],
                    }
                )
                self._write_prompt_stage_meta(stage_name, stage_record)
                self._save_stage_diagnostics()
                continue
            parsed = self._normalize_payload(stage_key, parsed)
            # T54 批 2（机械字段不出答卷）：代码能确定性定的字段在契约校验前装配。
            parsed = self._assemble_stage_mechanical_fields(stage_key, parsed, payload)
            if pre_validate_transform is not None:
                try:
                    parsed = pre_validate_transform(parsed)
                except Exception as exc:
                    logger.warning(
                        "%s pre_validate_transform raised, continuing with unsanitized payload: %s",
                        stage_name,
                        exc,
                    )
            self._save_prompt_audit_json(stage_name, f"attempt_{attempt}.parsed.normalized.json", parsed)
            attempt_record["parsed_response_file"] = self._prompt_audit_relpath(
                stage_name,
                f"attempt_{attempt}.parsed.normalized.json",
            )
            # 强制覆盖 generated_at：防止 LLM 日期幻觉
            # LLM 经常在 JSON 输出中编造 generated_at 值，覆盖掉 pydantic 的 default_factory
            # 这里用代码实际运行时间强制覆盖，确保审计可追溯性
            if hasattr(model_cls, "model_fields") and "generated_at" in model_cls.model_fields:
                parsed["generated_at"] = datetime.now(timezone.utc)
            # 无条件把非必填 list 字段收到的显式 null 收回成 []（与
            # sanitize_json_schema_for_strict_tool_calling 放开的字段集合精确对齐，
            # 见 llm_engine.py 里两个函数互相指名的 docstring）。不加"仅严格模式"
            # 开关：非严格模式下模型本来也偶尔返回 null 表示"没有内容"，是同一种
            # 合法表达，两条路径统一走这一层归一化才不会分叉。
            parsed = normalize_none_list_fields_for_strict_schema_validation(model_cls, parsed)
            try:
                validated = model_cls.model_validate(parsed)
            except Exception as exc:
                last_error = str(exc)
                stage_record["errors"].append(
                    {
                        "attempt": attempt,
                        "kind": "schema_validation_error",
                        "message": last_error[:1000],
                    }
                )
                self._write_prompt_stage_meta(stage_name, stage_record)
                self._save_stage_diagnostics()
                logger.warning("%s validation failed on attempt %s: %s", stage_name, attempt, exc)
                continue
            if validator:
                validation_errors = validator(validated)
                if validation_errors:
                    last_error = "\n".join(validation_errors)
                    stage_record["errors"].append(
                        {
                            "attempt": attempt,
                            "kind": "contract_validation_error",
                            "message": last_error[:1000],
                        }
                    )
                    self._write_prompt_stage_meta(stage_name, stage_record)
                    self._save_stage_diagnostics()
                    logger.warning(
                        "%s contract validation failed on attempt %s: %s",
                        stage_name,
                        attempt,
                        last_error,
                    )
                    continue
            stage_record["status"] = "ok"
            stage_record["model"] = getattr(self.llm_engine, "successful_model", None)
            self._save_prompt_audit_json(stage_name, "output.validated.json", _model_dump(validated))
            stage_record["prompt_audit"]["validated_output_file"] = self._prompt_audit_relpath(
                stage_name,
                "output.validated.json",
            )
            self._write_prompt_stage_meta(stage_name, stage_record)
            self._save_stage_diagnostics()
            return validated
        if raw_text_fallback is not None:
            last_error_kind = stage_record["errors"][-1]["kind"] if stage_record["errors"] else "unknown"
            fallback_result = raw_text_fallback(last_raw_response, last_error_kind)
            if fallback_result is not None:
                stage_record["status"] = "degraded_fallback"
                stage_record["degraded_fallback_kind"] = last_error_kind
                self._save_prompt_audit_json(stage_name, "output.validated.json", _model_dump(fallback_result))
                stage_record["prompt_audit"]["validated_output_file"] = self._prompt_audit_relpath(
                    stage_name,
                    "output.validated.json",
                )
                self._write_prompt_stage_meta(stage_name, stage_record)
                self._save_stage_diagnostics()
                return fallback_result
        stage_record["status"] = "failed"
        self._write_prompt_stage_meta(stage_name, stage_record)
        self._save_stage_diagnostics()
        raise RuntimeError(f"{stage_name} failed after {self.max_node_retries} attempts: {last_error}")

    def _prompt_audit_stage_dir(self, stage_name: str) -> Path:
        return self.prompt_audit_dir / self._prompt_audit_stage_label(stage_name)

    def _prompt_audit_stage_label(self, stage_name: str) -> str:
        normalized = str(stage_name or "stage").strip()
        layer_match = re.fullmatch(r"l([1-5])", normalized.lower())
        if layer_match:
            return f"L{layer_match.group(1)}"
        return re.sub(r"[^A-Za-z0-9_.-]+", "_", normalized).strip("_") or "stage"

    def _prompt_audit_relpath(self, stage_name: str, filename: Optional[str] = None) -> str:
        path = Path("prompt_audit") / self._prompt_audit_stage_label(stage_name)
        if filename:
            path = path / filename
        return path.as_posix()

    def _actual_prompt_text(self, user_prompt: str) -> str:
        system_constraints = ""
        if hasattr(self.llm_engine, "_load_system_constraints"):
            try:
                system_constraints = self.llm_engine._load_system_constraints()
            except Exception:
                system_constraints = ""
        return (
            "## System Message\n"
            f"{system_constraints}\n\n"
            "## User Message\n"
            f"{user_prompt}"
        )

    def _capture_prompt_attempt(
        self,
        *,
        stage_key: str,
        stage_name: str,
        attempt: int,
        active_prompt: str,
        payload: Dict[str, Any],
        retry_feedback: str,
    ) -> Dict[str, Any]:
        actual_prompt = self._actual_prompt_text(active_prompt)
        prompt_hash = hashlib.sha256(actual_prompt.encode("utf-8")).hexdigest()
        prompt_filename = f"attempt_{attempt}.prompt.txt"
        payload_filename = f"attempt_{attempt}.payload.json"
        self._save_prompt_audit_text(stage_name, prompt_filename, actual_prompt)
        self._save_prompt_audit_json(
            stage_name,
            payload_filename,
            {
                "stage_key": stage_key,
                "stage_name": stage_name,
                "attempt": attempt,
                "payload": self._sanitize_prompt_payload(stage_key, payload),
                "retry_feedback": retry_feedback or "",
            },
        )
        return {
            "attempt": attempt,
            "prompt_file": self._prompt_audit_relpath(stage_name, prompt_filename),
            "payload_file": self._prompt_audit_relpath(stage_name, payload_filename),
            "prompt_sha256": prompt_hash,
            "prompt_chars": len(actual_prompt),
            "retry_feedback": bool(retry_feedback),
        }

    def _save_prompt_audit_text(self, stage_name: str, filename: str, text: str) -> None:
        stage_dir = self._prompt_audit_stage_dir(stage_name)
        stage_dir.mkdir(parents=True, exist_ok=True)
        (stage_dir / filename).write_text(text, encoding="utf-8")

    def _save_prompt_audit_json(self, stage_name: str, filename: str, payload: Any) -> None:
        stage_dir = self._prompt_audit_stage_dir(stage_name)
        stage_dir.mkdir(parents=True, exist_ok=True)
        (stage_dir / filename).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )

    def _write_prompt_stage_meta(self, stage_name: str, stage_record: Dict[str, Any]) -> None:
        prompt_audit = stage_record.get("prompt_audit", {}) if isinstance(stage_record, dict) else {}
        attempts = prompt_audit.get("attempts", []) if isinstance(prompt_audit, dict) else []
        latest_attempt = attempts[-1] if attempts else {}
        meta = {
            "stage": self._prompt_audit_stage_label(stage_name),
            "stage_name": stage_name,
            "stage_key": stage_record.get("stage_key"),
            "attempt": latest_attempt.get("attempt"),
            "attempts": stage_record.get("attempts", 0),
            "model": stage_record.get("model") or getattr(self.llm_engine, "successful_model", None),
            "status": stage_record.get("status"),
            "prompt_chars": latest_attempt.get("prompt_chars") or stage_record.get("prompt_chars"),
            "prompt_tokens_estimate": None,
            "prompt_sha256": latest_attempt.get("prompt_sha256"),
            "prompt_file": latest_attempt.get("prompt_file"),
            "effective_date": self._infer_effective_date_from_prompt_audit(stage_name),
            "mode": self._infer_run_mode_from_prompt_audit(stage_name),
            "input_artifacts": self._infer_input_artifacts(stage_name),
            "output_artifact": self._infer_output_artifact(stage_name),
            "validation_errors": [
                item for item in stage_record.get("errors", [])
                if isinstance(item, dict) and item.get("kind") in {"schema_validation_error", "contract_validation_error"}
            ],
            "errors": stage_record.get("errors", []),
            "attempt_files": attempts,
            "data_boundary": self._infer_data_boundary_from_prompt_audit(stage_name),
        }
        self._save_prompt_audit_json(stage_name, "meta.json", meta)

    def _infer_effective_date_from_prompt_audit(self, stage_name: str) -> Optional[str]:
        analysis_path = self.output_dir / "analysis_packet.json"
        packet = {}
        if analysis_path.exists():
            try:
                packet = json.loads(analysis_path.read_text(encoding="utf-8"))
            except Exception:
                packet = {}
        meta = packet.get("meta", {}) if isinstance(packet, dict) else {}
        return meta.get("backtest_date") or meta.get("data_date") or meta.get("timestamp_utc")

    def _infer_run_mode_from_prompt_audit(self, stage_name: str) -> str:
        analysis_path = self.output_dir / "analysis_packet.json"
        if analysis_path.exists():
            try:
                packet = json.loads(analysis_path.read_text(encoding="utf-8"))
            except Exception:
                packet = {}
            meta = packet.get("meta", {}) if isinstance(packet, dict) else {}
            if meta.get("backtest_date"):
                return "backtest"
            if meta.get("snapshot_id") or meta.get("snapshot_mode"):
                return "snapshot"
        return "latest"

    def _infer_data_boundary_from_prompt_audit(self, stage_name: str) -> Dict[str, Any]:
        effective_date = self._infer_effective_date_from_prompt_audit(stage_name)
        return {
            "effective_date": effective_date,
            "max_input_date": None,
            "backtest_cutoff_respected": None,
        }

    def _infer_input_artifacts(self, stage_name: str) -> List[str]:
        layer_match = re.fullmatch(r"l([1-5])", str(stage_name).lower())
        if layer_match:
            layer = f"L{layer_match.group(1)}"
            return [
                f"layer_context_briefs/{layer}.json",
                f"analysis_packet.raw_data.{layer}",
            ]
        return {
            "bridge": ["context_brief.json", "layer_cards/L1-L5.json"],
            "thesis": ["synthesis_packet.json"],
            "critic": ["governance_input(thesis + synthesis + layer cards)"],
            "critic_retry": ["governance_input(thesis + synthesis + schema feedback + layer cards)"],
            "risk": ["governance_input(thesis + synthesis + layer cards)"],
            "risk_retry": ["governance_input(thesis + synthesis + schema feedback + layer cards)"],
            "reviser": ["governance_input(thesis + critique + risk + schema + layer cards)"],
            "final_adjudicator": ["governance_input(revised thesis + critique + risk + schema + layer cards)"],
        }.get(stage_name, [])

    def _infer_output_artifact(self, stage_name: str) -> str:
        layer_match = re.fullmatch(r"l([1-5])", str(stage_name).lower())
        if layer_match:
            return f"layer_cards/L{layer_match.group(1)}.json"
        return {
            "bridge": "bridge_memos/bridge_0.json",
            "thesis": "thesis_draft.json",
            "critic": "critique.json",
            "critic_retry": "critique.json",
            "risk": "risk_boundary_report.json",
            "risk_retry": "risk_boundary_report.json",
            "reviser": "analysis_revised.json",
            "final_adjudicator": "final_adjudication.json",
        }.get(stage_name, "")

    def _save_stage_diagnostics(self) -> None:
        path = self.output_dir / "llm_stage_diagnostics.json"
        path.write_text(json.dumps(self.stage_diagnostics, ensure_ascii=False, indent=2), encoding="utf-8")
        self._record_stage_artifact(path)

    # Field keys that carry evidence_ref-style citations inside reviser JSON output;
    # kept in sync with the key set _validate_stage_evidence_refs walks below.
    _REVISER_REF_LIST_KEYS = ("evidence_refs", "counterevidence_refs", "counter_evidence_refs")

    def _sanitize_reviser_ref_list(
        self,
        raw_refs: Any,
        evidence_index: Dict[str, Any],
        owner_desc: str,
        warnings: List[str],
    ) -> List[str]:
        """净化单个 evidence_refs 列表（reviser 专用降级，不改变全局合法性判定）。

        规则：
        - ref 本身在 evidence_index 中 → 原样保留。
        - ref 形如 parent#field 且不在 evidence_index，但 parent 在 evidence_index 且
          parent 非 mixed_field_authority → 退回为 parent（coerce），记 warning。
        - parent 是 mixed_field_authority，或 parent 本身也不在 evidence_index，或 ref
          不含 '#' 且不在 evidence_index → 丢弃该 ref，记 warning。
        """
        sanitized: List[str] = []
        seen: set[str] = set()
        for ref in self._coerce_string_list(raw_refs):
            if ref in evidence_index:
                if ref not in seen:
                    sanitized.append(ref)
                    seen.add(ref)
                continue
            parent = ref.split("#", 1)[0] if "#" in ref else ""
            parent_entry = evidence_index.get(parent) if parent else None
            if (
                parent
                and isinstance(parent_entry, dict)
                and not parent_entry.get("mixed_field_authority")
            ):
                warnings.append(
                    f"{owner_desc}: coerced illegal ref '{ref}' -> parent '{parent}' "
                    "(parent in evidence_index, not mixed_field_authority)"
                )
                if parent not in seen:
                    sanitized.append(parent)
                    seen.add(parent)
                continue
            if parent and isinstance(parent_entry, dict) and parent_entry.get("mixed_field_authority"):
                warnings.append(
                    f"{owner_desc}: dropped illegal ref '{ref}' "
                    f"(parent '{parent}' is mixed_field_authority; refusing to coerce to parent)"
                )
                continue
            warnings.append(f"{owner_desc}: dropped illegal ref '{ref}' (not resolvable in evidence_index)")
        return sanitized

    def _sanitize_reviser_evidence_refs(
        self,
        parsed: Dict[str, Any],
        evidence_index: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Reviser 产出证据引用的优雅降级净化，只在 reviser 阶段的 pre_validate_transform
        中调用。在 pydantic 校验之前，把可退回/需丢弃的非法 ref 处理掉，避免一次真实
        run 仅因幻觉 ref 而 RuntimeError 整体中止；不放松 `_validate_stage_evidence_refs`
        本身的合法性判定——净化失败的残留非法 ref 仍会被该函数拦下并触发既有重试路径。

        若某个结构性元素（support_chain / time_horizon_view / portfolio_action 等，位于
        某个 list 内的 dict 项）净化后所有 evidence_ref 类字段都清空，且清空是净化动作
        造成的（净化前非空），则整条元素从其所在 list 中剔除，视为"无证据支撑降级"。
        单例字段（如 reader_conclusion 本身）无法整体剔除，只保留净化后的空列表。
        """
        warnings: List[str] = []

        def process(node: Any, path: str) -> bool:
            """原地净化 node；返回 True 表示调用方应把该 dict 从其所在 list 中剔除。"""
            if isinstance(node, dict):
                had_refs_before = False
                has_refs_after = False
                touched = False
                for key in self._REVISER_REF_LIST_KEYS:
                    if key not in node or not isinstance(node[key], list):
                        continue
                    raw = node[key]
                    if raw:
                        had_refs_before = True
                    sanitized = self._sanitize_reviser_ref_list(
                        raw, evidence_index, f"{path}.{key}", warnings
                    )
                    if sanitized != self._coerce_string_list(raw):
                        touched = True
                    node[key] = sanitized
                    if sanitized:
                        has_refs_after = True
                for key, value in list(node.items()):
                    if key in self._REVISER_REF_LIST_KEYS:
                        continue
                    process(value, f"{path}.{key}")
                return touched and had_refs_before and not has_refs_after
            if isinstance(node, list):
                survivors: List[Any] = []
                for index, item in enumerate(node):
                    if isinstance(item, dict):
                        if process(item, f"{path}[{index}]"):
                            warnings.append(
                                f"{path}[{index}]: dropped entire element — all evidence_refs "
                                "were sanitized away, no legal ref remains"
                            )
                            continue
                        survivors.append(item)
                    else:
                        process(item, f"{path}[{index}]")
                        survivors.append(item)
                node[:] = survivors
                return False
            return False

        process(parsed, "reviser")
        if warnings:
            logger.warning(
                "reviser evidence_ref sanitization applied (%d action(s)): %s",
                len(warnings),
                "; ".join(warnings[:20]) + (" ..." if len(warnings) > 20 else ""),
            )
            self.stage_diagnostics.setdefault("reviser_evidence_ref_sanitization", [])
            self.stage_diagnostics["reviser_evidence_ref_sanitization"].extend(warnings)
            self._save_stage_diagnostics()
        return parsed

    # `revised_thesis` 中允许 reviser 原样不动的字段。Reviser 的岗位定义是"编辑，不是
    # 重写者"，所以某个键**完全缺席**语义上等于"本段未修订"，代码可以确定性地把原稿
    # 搬过来；而键存在（哪怕是空列表）是 reviser 自己的作答，永不覆盖——否则继承就成了
    # 绕过"冲突是资产"的后门。
    _REVISER_CARRY_FORWARD_FIELDS = ("hypothesis_responses",)

    def _carry_forward_reviser_thesis_fields(
        self,
        parsed: Dict[str, Any],
        thesis: Optional[Any],
    ) -> Dict[str, Any]:
        """把 reviser 整个遗漏的 revised_thesis 字段从 thesis 原稿继承过来并留痕。

        动机（真实事故 run 20260724_223804）：reviser 的合约要求每个 candidate 假说恰有
        一条回应，但"别把交给你的东西弄丢"是**确定性义务**；交给一次约 9.5K token 的自由
        生成去保证，等于抽奖，且失败时整条流水线硬崩。代码继承把它变回确定的。

        严格边界（任何一条被放松都会让它变成合约后门）：
        - 只在键**完全缺席**时介入；键存在（含空列表）一律不碰，交给既有 validator 硬拦。
        - 只搬运 thesis 已在案、且已通过同一组合约校验的原文；代码**永不生成**回应内容。
        - 每条继承项打 `carried_forward_from_thesis` 标记并写 stage_diagnostics 留痕，
          使"本轮未修订"对下游、审计区和人工复核可见，不伪装成 reviser 自己的判断。
        """
        if thesis is None:
            return parsed
        revised = parsed.get("revised_thesis")
        if not isinstance(revised, dict):
            return parsed

        notes: List[str] = []
        for field in self._REVISER_CARRY_FORWARD_FIELDS:
            if field in revised:
                continue
            source_items = getattr(thesis, field, None)
            if not source_items:
                continue
            carried: List[Any] = []
            for item in source_items:
                dumped = _model_dump(item)
                if not isinstance(dumped, dict):
                    continue
                dumped["carried_forward_from_thesis"] = True
                carried.append(dumped)
            if not carried:
                continue
            revised[field] = carried
            notes.append(
                f"reviser.revised_thesis.{field}: omitted by reviser, carried forward "
                f"verbatim from thesis_draft ({len(carried)} item(s)); marked "
                "carried_forward_from_thesis=true — 本轮未修订"
            )

        if notes:
            logger.warning(
                "reviser thesis field carry-forward applied (%d field(s)): %s",
                len(notes),
                "; ".join(notes),
            )
            self.stage_diagnostics.setdefault("reviser_thesis_field_carry_forward", [])
            self.stage_diagnostics["reviser_thesis_field_carry_forward"].extend(notes)
            self._save_stage_diagnostics()
        return parsed

    def _load_reviser_checkpoint(self, expected_payload: Dict[str, Any]) -> Optional[AnalysisRevised]:
        """载入 reviser 检查点，但拒绝复用降级兜底产物。

        降级产物代表"本轮放弃了修订"，不是一次成功的 reviser 结果。续跑必须重新尝试
        修订，否则一次失败会把"未经修订"永久固化进后续所有续跑。
        """
        checkpoint = self._load_stage_checkpoint(
            "analysis_revised.json",
            AnalysisRevised,
            stage_key="reviser",
            stage_name="reviser",
            expected_payload=expected_payload,
        )
        if checkpoint is not None and getattr(checkpoint, "degraded_fallback", None):
            logger.warning("analysis_revised.json 是降级兜底产物，忽略该检查点并重跑 reviser。")
            return None
        return checkpoint

    def _build_degraded_analysis_revised(self, thesis: ThesisDraft, reason: str) -> AnalysisRevised:
        """Reviser 全部尝试失败时的兜底：原样退回未修订的 thesis，并显式声明降级。

        不放松任何合约——thesis 已通过 reviser 所受的同一组校验（证据引用合法性、
        每个 candidate 假说恰一条回应），所以兜底产物天然合规。但它**不是**一份修订稿，
        必须让下游、质量闸门、报告审计区和人工复核一眼看见"本轮未经修订"，
        绝不能长得像正常产物。
        """
        note = (
            f"[degraded] reviser 阶段 {self.max_node_retries} 次尝试均未通过合约校验，"
            "本轮判断书未经修订，直接沿用 thesis 原稿。批评与风险意见本轮未被吸收。"
        )
        self.stage_diagnostics.setdefault("reviser_degraded_fallback", [])
        self.stage_diagnostics["reviser_degraded_fallback"].append(
            {"reason": reason[:1000], "attempts": self.max_node_retries}
        )
        self._save_stage_diagnostics()
        return AnalysisRevised(
            revision_summary=note[:500],
            accepted_critiques=[],
            rejected_critiques=[],
            revised_thesis=thesis,
            # 冲突是资产：兜底不得顺手抹平原稿已保留的冲突。
            remaining_conflicts=list(thesis.retained_conflicts),
            degraded_fallback={
                "stage": "reviser",
                "reason": reason[:1000],
                "attempts": self.max_node_retries,
                "effect": "revised_thesis 为未修订的 thesis 原稿；critique/risk 反馈本轮未吸收",
            },
        )

    def _validate_stage_evidence_refs(self, candidate: Any, allowed_refs: set[str], stage_key: str) -> List[str]:
        payload = _model_dump(candidate)
        refs_by_path: List[tuple[str, str]] = []

        def walk(value: Any, path: str = "") -> None:
            if isinstance(value, dict):
                for key, child in value.items():
                    next_path = f"{path}.{key}" if path else str(key)
                    if key in {"evidence_refs", "counterevidence_refs", "counter_evidence_refs"}:
                        for ref in self._coerce_string_list(child):
                            refs_by_path.append((next_path, ref))
                    else:
                        walk(child, next_path)
                return
            if isinstance(value, list):
                for index, child in enumerate(value):
                    walk(child, f"{path}[{index}]")

        walk(payload)
        invalid = [
            (path, ref)
            for path, ref in refs_by_path
            if ref and ref not in allowed_refs
        ]
        if not invalid:
            return []
        examples = "; ".join(f"{path} -> {ref}" for path, ref in invalid[:8])
        return [
            (
                f"evidence_ref_source_validation failed for {stage_key}: "
                f"refs must come from synthesis_packet.evidence_index. Invalid refs: {examples}"
            )
        ]

    def _append_final_quality_note(self, final: FinalAdjudication, note: str) -> None:
        if final.quality_gate is None:
            final.quality_gate = QualityGate(
                approval_status=final.approval_status,
                blocking_issues=list(final.blocking_issues),
                notes=note,
            )
            return
        notes = [item for item in str(final.quality_gate.notes or "").split("；") if item]
        if note not in notes:
            notes.append(note)
            final.quality_gate.notes = "；".join(notes)

    def _annotate_event_section_summary_degradation(
        self,
        final: FinalAdjudication,
        event_interpretation_cards: Dict[str, Any],
    ) -> None:
        """T36 的牙齿：`_build_event_section_summary` 走解析失败兜底时已经在
        `event_interpretation_cards.section_summary.index_degraded` 里留痕，但那份
        artifact 不会被读者当成"能不能发布"的裁决——收下 ≠ 认可。这里把同一个信号
        接到 reviser_degraded_unrevised_thesis / counter_thesis_degraded_deterministic_
        fallback 用的同一份终审质量闸门（`final.quality_gate.notes`）上，风格与行为
        对齐这两条既有先例，不新造一套发布闸门。"""
        section_summary_meta = (
            event_interpretation_cards.get("section_summary")
            if isinstance(event_interpretation_cards, dict)
            else None
        )
        if isinstance(section_summary_meta, dict) and section_summary_meta.get("index_degraded"):
            self._append_final_quality_note(
                final,
                f"event_section_summary_index_degraded:{section_summary_meta['index_degraded']}",
            )

    def _validate_reasoned_verdict_refs(
        self,
        candidate: Any,
        allowed_refs: set[str],
        source_text: Optional[str] = None,
    ) -> List[str]:
        """final_adjudicator.md 白纸黑字："三条主要理由每条必须至少带一个方括号标注
        的 evidence_ref……这是硬要求，一个都没有等于整段作废。"但此前这条规则只在
        生成之后由 `_annotate_reasoned_verdict_refs` 做软性标注（写进
        quality_gate.notes），从不触发重试——真实事故（run 20260725_232410）：
        终审一次通过，`reasoned_verdict` 514 字、内容连贯、数字详实，却**零处**方括号
        引用，读者拿到手的主判决文字完全没有可追溯证据，质量闸门只留了一条
        `reasoned_verdict_missing_refs` 备注，报告照常发布。

        这里补成真正的合约校验，接进 `_run_stage` 的 validator 链：说明书已经给了
        模型示例格式（`[L1.get_10y_real_rate]`），这不是"模型不知道规则"（reviser/
        counter_thesis 那两次事故的根因），而是"规则没有被强制"，补一道校验、让重试
        机制把报错原样喂回去即可，不需要改说明书。`reasoned_verdict` 长度已经是硬性
        pydantic 校验（`test_final_stage_retries_after_overlong_reasoned_verdict`
        锁定的既有行为），这里只是把"必须带引用"这条也提到同一严重度，不额外放大
        终审阶段本来就有的爆炸半径。

        `source_text`（T42②）是终审这一站实际收到的 payload 文本。传了就额外做
        "数字存在性比对"：判决正文里出现的百分数 / 小数值必须逐字出现在本次输入
        中——"报告里写的 2.3%，原始 payload 里找不找得到 2.3%"是身份比对，不是
        语义判断，符合「闸门不判意思」。
        """
        verdict = str(getattr(candidate, "reasoned_verdict", "") or "").strip()
        if not verdict:
            return []
        bracket_groups = self._reasoned_verdict_bracket_groups(verdict)
        cited_refs = [ref for group in bracket_groups for ref in group]
        if not cited_refs:
            return [
                "reasoned_verdict must cite at least one evidence_ref in [brackets] "
                "(e.g. [L1.get_10y_real_rate]); found zero citations."
            ]
        # final_adjudicator.md:243-245 要求"总-分-总"结构，中间按最有分量的**三条理由**
        # 展开，且"三条主要理由每条必须至少带一个方括号标注的 evidence_ref"。只校验
        # "至少一条引用"会放过真实事故形态：run 20260725_232410 的 514 字判决书把状态、
        # 矛盾、风险、定价、赔率、仓位、失效条件全部压进单段连续文字，没有三条理由的
        # 层级，读者拿不到"哪条证据支撑哪条理由"。三条理由各至少一条引用 ⇒ 至少三条
        # 不同引用，这不是新拍的数字，是把说明书里已经写死的结构提到同一强制等级。
        # 真实事故 run 20260728_110702：模型把两条合法 ref 逗号合并进同一个方括号
        # （`[L1.get_10y_real_rate, L4.get_equity_risk_premium#level]`），旧解析把整段
        # 当成一个 ref，两条都合法却被判"引用不在索引内"，终审两次尝试后整跑硬崩。
        # 这是 2026-07-27 把"至少一条引用"收紧为"至少三条不同引用"之后的第一次真实 run，
        # 收紧恰好把模型推向了这种写法——所以修法是让解析容忍逗号合并（每一段仍须逐字
        # 合法，不放松任何一条 ref 的合法性），而不是把计数要求退回去。
        #
        # 但只按"不同 ref 条数"计数会重新打开 2026-07-27 要堵的洞：一段连续文字里塞一个
        # 装三条 ref 的方括号也能凑够 3 条。所以这里同时要求**方括号组数 ≥ 3**——这才是
        # `final_adjudicator.md:244` 写死的原文（"三条主要理由每条必须至少带一个方括号
        # 标注的 evidence_ref"），比"3 条不同引用"更贴近说明书，不是新拍的数字。
        if len(bracket_groups) < 3 or len(set(cited_refs)) < 3:
            return [
                "reasoned_verdict must follow the documented 总-分-总 structure: the three "
                "main reasons each need at least one [bracketed] evidence_ref, i.e. at least "
                "3 separate [bracket] groups and at least 3 distinct citations. Found "
                f"{len(bracket_groups)} bracket group(s) and {len(set(cited_refs))} distinct "
                f"citation(s): {sorted(set(cited_refs))}. Put one evidence_ref per bracket and "
                "do not merge the three reasons into one continuous paragraph."
            ]
        lower_key_map = {key.lower(): key for key in allowed_refs}
        passports = {key: None for key in allowed_refs}
        unresolved = [
            ref
            for ref in cited_refs
            if self._resolve_claim_evidence_ref(ref, passports, lower_key_map) is None
        ]
        if unresolved:
            return [
                f"reasoned_verdict cites refs outside evidence_index: {unresolved[:5]}"
            ]
        if source_text is not None:
            missing_numbers = [
                token
                for token in self._reasoned_verdict_numeric_tokens(verdict)
                if token not in source_text
            ]
            if missing_numbers:
                return [
                    "reasoned_verdict contains numbers that are not present in the stage "
                    "payload (identity check, not semantic): "
                    f"{missing_numbers[:5]}. Only use numbers that appear verbatim in the input."
                ]
        return []

    @staticmethod
    def _reasoned_verdict_bracket_groups(verdict: str) -> List[List[str]]:
        """把 `reasoned_verdict` 里的方括号标注解析成"每个方括号一组 ref"。

        模型会把多条 ref 逗号合并进同一个方括号（真实事故 run 20260728_110702），
        所以每组内部再按中英文逗号/顿号/分号拆开。只做形状纠正：拆出来的每一段仍要
        逐字通过 `_resolve_claim_evidence_ref`，不放松任何 ref 的合法性要求。
        """
        groups: List[List[str]] = []
        for raw in re.findall(r"\[([^\[\]]+)\]", verdict):
            refs = [part.strip() for part in re.split(r"[,，、;；]", raw) if part.strip()]
            if refs:
                groups.append(refs)
        return groups

    @staticmethod
    def _reasoned_verdict_numeric_tokens(verdict: str) -> List[str]:
        """提取判决正文里"像数据"的数字 token：百分数（含整数百分数）和小数。
        只做身份比对用——这些 token 必须逐字出现在终审实际收到的 payload 里。
        不提取纯整数（如"三条理由""纳斯达克100"里的 3/100），避免把行文数字
        误判成编造数据；也不提取 evidence_ref 里的编号（如 L1）。"""
        tokens: List[str] = []
        for match in re.finditer(r"\d+(?:\.\d+)?\s*%|\d+\.\d+", verdict):
            token = re.sub(r"\s+", "", match.group(0))
            if token not in tokens:
                tokens.append(token)
        return tokens

    def _annotate_reasoned_verdict_refs(
        self,
        final: FinalAdjudication,
        allowed_refs: set[str],
    ) -> None:
        verdict = str(final.reasoned_verdict or "").strip()
        if not verdict:
            return
        cited_refs = [ref for group in self._reasoned_verdict_bracket_groups(verdict) for ref in group]
        if not cited_refs:
            self._append_final_quality_note(final, "reasoned_verdict_missing_refs")
            return
        lower_key_map = {key.lower(): key for key in allowed_refs}
        passports = {key: None for key in allowed_refs}
        unresolved = [
            ref
            for ref in cited_refs
            if self._resolve_claim_evidence_ref(ref, passports, lower_key_map) is None
        ]
        if unresolved:
            self._append_final_quality_note(
                final,
                "reasoned_verdict_unresolved_refs:" + ",".join(dict.fromkeys(unresolved)),
            )

    def _validate_final_conflict_responses(
        self,
        candidate: Any,
        thesis: ThesisDraft,
    ) -> List[str]:
        """T42③：Thesis→Final 段补"保留冲突是否被回应"的编号级校验。

        Bridge→Thesis 段已查得扎实（`_run_schema_guard` 里的 retained_conflicts
        认亲），Thesis→Final 段此前无对等检查——终审只被要求"带够 3 条引用"，
        不被要求"覆盖住仍然保留的冲突"。后果：冲突条目仍在结构字段里（"没抹平"
        形式成立），但终审叙事可完全绕开。**冲突没被删掉，只是没被回答。**

        这里只做身份比对：thesis 保留的、带 `conflict_id` 的高严重度冲突，其编号
        必须逐字出现在终审输出的 `principal_contradiction.conflict_refs`、
        `reasoned_verdict` 或 `adjudicator_notes` 里。不判意思——不回应对措辞、
        不看回应质量；编号没出现就是没覆盖，把缺失编号原样喂回重试。
        """
        retained_high_conflict_ids = [
            str(getattr(conflict, "conflict_id", "") or "").strip()
            for conflict in (getattr(thesis, "retained_conflicts", []) or [])
            if str(getattr(getattr(conflict, "severity", ""), "value", getattr(conflict, "severity", ""))).lower() == "high"
            and str(getattr(conflict, "conflict_id", "") or "").strip()
        ]
        if not retained_high_conflict_ids:
            return []

        haystack_parts: List[str] = [
            str(getattr(candidate, "reasoned_verdict", "") or ""),
            str(getattr(candidate, "adjudicator_notes", "") or ""),
            str(getattr(candidate, "final_stance", "") or ""),
        ]
        principal = getattr(candidate, "principal_contradiction", None)
        if principal is not None:
            haystack_parts.append(" ".join(getattr(principal, "conflict_refs", []) or []))
            haystack_parts.append(str(getattr(principal, "contradiction_id", "") or ""))
        for secondary in getattr(candidate, "secondary_contradictions", []) or []:
            haystack_parts.append(str(getattr(secondary, "contradiction_id", "") or ""))
        haystack = "\n".join(haystack_parts)

        missing = [conflict_id for conflict_id in dict.fromkeys(retained_high_conflict_ids) if conflict_id not in haystack]
        if missing:
            return [
                "final must respond to or preserve retained high-severity conflicts; "
                "missing conflict ids in final principal_contradiction.conflict_refs / "
                f"reasoned_verdict / adjudicator_notes: {missing[:5]}"
            ]
        return []

    def _validate_layer_card_v2(
        self,
        card: LayerCard,
        layer_label: str,
        expected_indicators: Dict[str, str],
    ) -> List[str]:
        """Reject thin legacy-style LayerCards before Bridge consumes them."""
        errors: List[str] = []
        expected_function_ids = set(expected_indicators)

        if not str(card.layer_synthesis or "").strip():
            errors.append(f"{layer_label}.layer_synthesis is required for LayerCard v2.")
        if not str(card.internal_conflict_analysis or "").strip():
            errors.append(f"{layer_label}.internal_conflict_analysis is required for LayerCard v2.")
        if card.quality_self_check is None:
            errors.append(f"{layer_label}.quality_self_check is required for LayerCard v2.")

        analyses_by_function: Dict[str, Any] = {}
        for analysis in card.indicator_analyses:
            if analysis.function_id:
                analyses_by_function[analysis.function_id] = analysis
            if not analysis.narrative.strip():
                errors.append(f"{layer_label}.{analysis.function_id}.narrative is required.")
            if not analysis.reasoning_process.strip():
                errors.append(f"{layer_label}.{analysis.function_id}.reasoning_process is required.")
            if not analysis.evidence_refs:
                errors.append(f"{layer_label}.{analysis.function_id}.evidence_refs must not be empty.")

        missing_analyses = sorted(expected_function_ids - set(analyses_by_function))
        for function_id in missing_analyses:
            errors.append(f"{layer_label}.indicator_analyses[{function_id}] is required.")

        # T54 批 5（收紧）：幻觉出来的 function_id（不在输入键集里）此前静默通过、
        # 只靠"漏分析"间接报错——现在显式拒收重试。批 5 装配层已把唯一高相似近邻的
        # 拼写错误回正，走到这里的都是配不上的，必须打回而不是放行。
        unknown_analyses = sorted(set(analyses_by_function) - expected_function_ids)
        for function_id in unknown_analyses:
            errors.append(f"{layer_label}.indicator_analyses[{function_id}] is not an input function_id.")

        for function_id, metric_name in expected_indicators.items():
            analysis = analyses_by_function.get(function_id)
            if analysis and metric_name and analysis.metric != metric_name:
                errors.append(
                    f"{layer_label}.{function_id}.metric must equal input metric_name '{metric_name}'."
                )

        if card.quality_self_check is not None:
            covered = set(card.quality_self_check.covered_function_ids)
            covered_from_analyses = expected_function_ids & set(analyses_by_function)
            effective_covered = covered | covered_from_analyses
            missing_from_self_check = sorted(expected_function_ids - effective_covered)
            if covered_from_analyses - covered:
                card.quality_self_check.covered_function_ids = sorted(effective_covered)
            if expected_function_ids and not missing_analyses and not card.quality_self_check.coverage_complete:
                card.quality_self_check.coverage_complete = True
            if missing_from_self_check:
                errors.append(
                    f"{layer_label}.quality_self_check.covered_function_ids missing: "
                    + ", ".join(missing_from_self_check)
                )

        return errors

    def _validate_bridge_memo_v2(self, bridge: BridgeMemo) -> List[str]:
        """Reject soft Bridge resonance chains that lack evidence, mechanism, or falsifiers."""
        errors: List[str] = []
        notes = set(getattr(bridge, "normalization_notes", []) or [])
        typed_conflicts_derived = "typed_conflicts_derived_from_legacy_conflicts" in notes
        for conflict in bridge.typed_conflicts:
            conflict_id = str(conflict.conflict_id or "typed_conflict")
            if not conflict.evidence_refs:
                errors.append(f"bridge.typed_conflicts[{conflict_id}].evidence_refs must not be empty.")
            if not typed_conflicts_derived and not str(conflict.mechanism or "").strip():
                errors.append(f"bridge.typed_conflicts[{conflict_id}].mechanism is required.")
            if not str(conflict.implication or "").strip():
                errors.append(f"bridge.typed_conflicts[{conflict_id}].implication is required.")
        for chain in bridge.resonance_chains:
            chain_id = str(chain.chain_id or "resonance_chain")
            if not chain.evidence_refs:
                errors.append(f"bridge.resonance_chains[{chain_id}].evidence_refs must not be empty.")
            if not chain.confirming_indicators:
                errors.append(f"bridge.resonance_chains[{chain_id}].confirming_indicators must not be empty.")
            if not str(chain.mechanism or "").strip():
                errors.append(f"bridge.resonance_chains[{chain_id}].mechanism is required.")
            if not str(chain.implication or "").strip():
                errors.append(f"bridge.resonance_chains[{chain_id}].implication is required.")
            if not chain.falsifiers:
                errors.append(f"bridge.resonance_chains[{chain_id}].falsifiers must not be empty.")
        seen_path_ids: set[str] = set()
        for path in bridge.transmission_paths:
            path_id = str(path.path_id or "transmission_path")
            if path_id in seen_path_ids:
                errors.append(f"bridge.transmission_paths[{path_id}] duplicate path_id.")
            seen_path_ids.add(path_id)
            if not path.evidence_refs:
                errors.append(f"bridge.transmission_paths[{path_id}].evidence_refs must not be empty.")
            if not str(path.implication or "").strip():
                errors.append(f"bridge.transmission_paths[{path_id}].implication is required.")
        # 4.7 口径：事件永不进第一层，bridge 的 evidence_refs 不得含 event: 前缀。
        for container_name, container in (
            ("typed_conflicts", bridge.typed_conflicts),
            ("resonance_chains", bridge.resonance_chains),
            ("transmission_paths", bridge.transmission_paths),
        ):
            for item in container:
                if container_name == "typed_conflicts":
                    item_id = str(getattr(item, "conflict_id", None) or "typed_conflict")
                elif container_name == "resonance_chains":
                    item_id = str(getattr(item, "chain_id", None) or "resonance_chain")
                else:
                    item_id = str(getattr(item, "path_id", None) or "transmission_path")
                for ref in getattr(item, "evidence_refs", []) or []:
                    if str(ref).startswith("event:"):
                        errors.append(
                            f"bridge.{container_name}[{item_id}].evidence_refs "
                            f"事件不得作为 evidence_ref：{ref}"
                        )
        # 顶层 event_refs 同样恒空（三明治口径）：输出非空即污染事故。
        if getattr(bridge, "event_refs", None):
            errors.append("bridge.event_refs must stay empty: 事件永不进第一层（含治理链）。")
        return errors

    def _run_schema_guard(
        self,
        packet: AnalysisPacket,
        layer_cards: List[LayerCard],
        bridge_memos: List[BridgeMemo],
        thesis: ThesisDraft,
        critique: Critique,
        risk_report: RiskBoundaryReport,
    ) -> SchemaGuardReport:
        structural_issues: List[str] = []
        consistency_issues: List[str] = []
        missing_fields: List[str] = []
        suggested_fixes: List[str] = []
        soft_canon_warnings: List[str] = []
        l3_structural_warnings: List[str] = []
        semantic_warnings: List[str] = []
        valid_evidence_refs: set[str] = set()
        for layer, metrics in packet.raw_data.items():
            if not isinstance(metrics, dict):
                continue
            for function_id, raw_payload in metrics.items():
                parent_ref = f"{layer}.{function_id}"
                valid_evidence_refs.add(parent_ref)
                if isinstance(raw_payload, dict):
                    # T35 修复（方案 A）：合法性只判身份（这个字段这一轮真实存在吗），
                    # 不判权限（够不够格支撑强结论）。此前只读 MetricAuthority 人工登记表
                    # ——L4 17 个 get_* 函数里 10 个从未登记过，字段真实存在、取数成功、
                    # 来源官方，也会被判"引用不在索引内"（真实事故：run 20260730_114704，
                    # L4.get_damodaran_us_implied_erp#erp_t12m_adjusted_payout）。这里改成
                    # MetricAuthority 键与 raw value 真实顶层键的并集，不减少任何现有合法 ref。
                    value_payload = raw_payload.get("value") if isinstance(raw_payload.get("value"), dict) else {}
                    field_names = set(self._field_authority_from_payload(raw_payload)) | set(value_payload)
                    for field in field_names:
                        valid_evidence_refs.add(f"{parent_ref}#{field}")

        def _bad_refs(refs: List[str]) -> List[str]:
            bad: List[str] = []
            for ref in refs or []:
                ref_text = str(ref)
                if not _EVIDENCE_REF_PATTERN.fullmatch(ref_text) or ref_text not in valid_evidence_refs:
                    bad.append(ref_text)
            return bad

        def _composite_submetric_issue(conflict: Any) -> Optional[str]:
            severity = str(getattr(getattr(conflict, "severity", ""), "value", getattr(conflict, "severity", ""))).lower()
            refs = [str(ref) for ref in getattr(conflict, "evidence_refs", []) or []]
            if severity != "high" or "L2.get_cnn_fear_greed_index" not in refs:
                return None
            text = " ".join(
                str(getattr(conflict, field, "") or "")
                for field in ("conflict_id", "conflict_type", "description", "mechanism", "implication")
            ).lower()
            submetric_tokens = (
                "market momentum",
                "put/call",
                "safe haven",
                "junk bond",
                "stock price strength",
                "stock price breadth",
                "market volatility",
                "子项",
                "分项",
            )
            aggregate_tokens = (
                "total score",
                "overall",
                "aggregate",
                "headline",
                "总分",
                "综合",
                "整体",
                "总指标",
            )
            if any(token in text for token in submetric_tokens) and not any(token in text for token in aggregate_tokens):
                return (
                    "high severity conflict uses CNN Fear & Greed sub-metric without aggregate-score semantics; "
                    "treat sub-metric divergence as internal tension unless independently supported."
                )
            return None

        def _normalize_conflict_text(text: Any) -> str:
            return " ".join(str(text or "").split())

        def _high_severity_conflict_candidates(memo: BridgeMemo) -> List[Dict[str, Any]]:
            source: List[Any] = list(memo.typed_conflicts) if memo.typed_conflicts else list(memo.conflicts)
            candidates: List[Dict[str, Any]] = []
            for conflict in source:
                severity = str(getattr(getattr(conflict, "severity", ""), "value", getattr(conflict, "severity", ""))).lower()
                if severity != "high":
                    continue
                conflict_type = str(getattr(conflict, "conflict_type", "") or "")
                conflict_id = str(getattr(conflict, "conflict_id", "") or "")
                ids = {value for value in (conflict_type, conflict_id) if value}
                label = conflict_id or conflict_type or "unknown_conflict"
                candidates.append(
                    {
                        "ids": ids,
                        "label": label,
                        "severity": severity,
                        "description": str(getattr(conflict, "description", "") or ""),
                    }
                )
            return candidates

        if len(layer_cards) != 5:
            structural_issues.append(f"Expected 5 layer cards, got {len(layer_cards)}.")

        for card in layer_cards:
            if not card.core_facts:
                structural_issues.append(f"{card.layer} has no core_facts.")
            if not card.local_conclusion:
                missing_fields.append(f"{card.layer}.local_conclusion")
            layer_label = getattr(card.layer, "value", str(card.layer))
            expected_function_ids = self._analysis_required_function_ids(packet, layer_label)
            if layer_label == "L3":
                present_priority = sorted(set(expected_function_ids) & L3_STRUCTURAL_PRIORITY_FUNCTIONS)
                missing_priority = sorted(L3_STRUCTURAL_PRIORITY_FUNCTIONS - set(expected_function_ids))
                if present_priority and missing_priority:
                    l3_structural_warnings.append(
                        "L3 structural priority coverage is partial; missing "
                        + ", ".join(missing_priority)
                    )
            covered_function_ids = {
                item.function_id
                for item in card.indicator_analyses
                if item.function_id
            }
            for function_id in expected_function_ids:
                if function_id not in covered_function_ids:
                    missing_fields.append(f"{layer_label}.indicator_analyses[{function_id}]")
            for item in card.indicator_analyses:
                if not item.narrative.strip():
                    missing_fields.append(f"{layer_label}.{item.function_id}.narrative")
                if not item.reasoning_process.strip():
                    missing_fields.append(f"{layer_label}.{item.function_id}.reasoning_process")
                try:
                    get_indicator_canon(item.function_id)
                except KeyError:
                    continue
                missing_soft_fields = [
                    field_name
                    for field_name in (
                        "permission_type",
                        "canonical_question",
                        "misread_guards",
                        "cross_validation_targets",
                        "falsifiers",
                        "core_vs_tactical_boundary",
                    )
                    if not getattr(item, field_name)
                ]
                if missing_soft_fields:
                    soft_canon_warnings.append(
                        f"{layer_label}.{item.function_id} missing soft canon fields: "
                        + ", ".join(missing_soft_fields)
                    )
            authority_overreach = self._find_indicator_authority_overreach(card.indicator_analyses)
            for issue in authority_overreach:
                semantic_warnings.append(
                    "Indicator authority overreach: "
                    f"{layer_label}.{issue['function_id']} ({issue['permission_type']}) -> {issue['rule_id']}"
                )

        if not bridge_memos:
            structural_issues.append("No bridge memo generated.")
        else:
            structural_bridge_memos = [
                memo
                for memo in bridge_memos
                if str(getattr(memo, "bridge_type", "")) != "feedback_bridge_v2"
            ]
            total_conflicts = sum(len(memo.conflicts) for memo in structural_bridge_memos)
            if total_conflicts == 0:
                consistency_issues.append("Bridge stage produced zero conflicts; this usually means tension was flattened.")
            for memo_index, memo in enumerate(structural_bridge_memos):
                seen_path_ids: set[str] = set()
                for claim_index, claim in enumerate(memo.cross_layer_claims):
                    bad_refs = _bad_refs(claim.supporting_facts)
                    if bad_refs:
                        consistency_issues.append(
                            f"BridgeMemo[{memo_index}].cross_layer_claims[{claim_index}].supporting_facts invalid: "
                            + ", ".join(bad_refs[:5])
                        )
                for conflict in memo.typed_conflicts:
                    conflict_id = str(conflict.conflict_id or "typed_conflict")
                    if not conflict.evidence_refs:
                        consistency_issues.append(f"BridgeMemo[{memo_index}].typed_conflicts[{conflict_id}].evidence_refs must not be empty.")
                    bad_refs = _bad_refs(conflict.evidence_refs)
                    if bad_refs:
                        consistency_issues.append(
                            f"BridgeMemo[{memo_index}].typed_conflicts[{conflict_id}].evidence_refs invalid: "
                            + ", ".join(bad_refs[:5])
                        )
                    composite_issue = _composite_submetric_issue(conflict)
                    if composite_issue:
                        consistency_issues.append(
                            f"BridgeMemo[{memo_index}].typed_conflicts[{conflict_id}] composite sub-metric over-promotion: "
                            + composite_issue
                        )
                for chain in memo.resonance_chains:
                    chain_id = str(chain.chain_id or "resonance_chain")
                    bad_refs = _bad_refs(chain.evidence_refs)
                    if bad_refs:
                        consistency_issues.append(
                            f"BridgeMemo[{memo_index}].resonance_chains[{chain_id}].evidence_refs invalid: "
                            + ", ".join(bad_refs[:5])
                        )
                for path in memo.transmission_paths:
                    path_id = str(path.path_id or "transmission_path")
                    if path_id in seen_path_ids:
                        consistency_issues.append(f"BridgeMemo[{memo_index}].transmission_paths[{path_id}] duplicate path_id.")
                    seen_path_ids.add(path_id)
                    if not path.evidence_refs:
                        consistency_issues.append(f"BridgeMemo[{memo_index}].transmission_paths[{path_id}].evidence_refs must not be empty.")
                    if not str(path.implication or "").strip():
                        consistency_issues.append(f"BridgeMemo[{memo_index}].transmission_paths[{path_id}].implication is required.")
                    bad_refs = _bad_refs(path.evidence_refs)
                    if bad_refs:
                        consistency_issues.append(
                            f"BridgeMemo[{memo_index}].transmission_paths[{path_id}].evidence_refs invalid: "
                            + ", ".join(bad_refs[:5])
                        )

        if not thesis.main_thesis:
            missing_fields.append("thesis.main_thesis")
        if not critique.revision_direction:
            missing_fields.append("critique.revision_direction")
        if not risk_report.must_preserve_risks:
            consistency_issues.append("RiskBoundaryReport.must_preserve_risks is empty.")

        # 与 bridge 侧对称：两边都用 {conflict_id, conflict_type} 的并集来认亲。
        # 此前 thesis 侧只取 conflict_type，而正方会把类型名改写成自己的措辞
        # （bridge `rate_vs_valuation` → thesis `real_rate_vs_valuation`），
        # 于是闸门谎报"高严重度冲突被抹平"——冲突其实一条没丢（run 20260728_222759）。
        retained_conflict_ids = {
            value
            for conflict in thesis.retained_conflicts
            for value in (
                str(conflict.conflict_type or ""),
                str(getattr(conflict, "conflict_id", "") or ""),
            )
            if value
        }
        retained_conflict_semantic = {
            (
                str(getattr(getattr(conflict, "severity", ""), "value", conflict.severity)).lower(),
                _normalize_conflict_text(conflict.description),
            )
            for conflict in thesis.retained_conflicts
        }
        dropped_high_conflicts: List[str] = []
        for memo in bridge_memos:
            for candidate in _high_severity_conflict_candidates(memo):
                if candidate["ids"] & retained_conflict_ids:
                    continue
                if (candidate["severity"], _normalize_conflict_text(candidate["description"])) in retained_conflict_semantic:
                    continue
                dropped_high_conflicts.append(candidate["label"])
        if dropped_high_conflicts:
            message = (
                "High severity conflicts missing from ThesisDraft.retained_conflicts: "
                + ", ".join(sorted(set(dropped_high_conflicts)))
            )
            # "编号没传下来"和"冲突真被抹平"后果天差地别：后者踩到"冲突是资产"这条
            # 常驻边界，前者只是通道断了。不加区分地报后者，会让人去修一个不存在的病。
            if thesis.retained_conflicts and not any(
                str(getattr(conflict, "conflict_id", "") or "").strip()
                for conflict in thesis.retained_conflicts
            ):
                message += (
                    "；注意：retained_conflicts 共 "
                    f"{len(thesis.retained_conflicts)} 条但无一条填写 conflict_id，"
                    "本条告警可能是编号未沿用而非冲突真被抹平，请先核对描述内容再下结论"
                )
            consistency_issues.append(message)

        if structural_issues:
            suggested_fixes.append("Re-run the failed stage and verify JSON output matches the contract.")
        if consistency_issues:
            suggested_fixes.append("Force the reviser/final stages to preserve bridge conflicts and risk boundaries explicitly.")
        if missing_fields:
            suggested_fixes.append("Patch prompts so required fields are always returned, even when the model is uncertain.")
        if soft_canon_warnings:
            suggested_fixes.append(
                "Add soft canon fields to indicator_analyses where available: "
                + "; ".join(soft_canon_warnings[:8])
            )
        if l3_structural_warnings:
            suggested_fixes.append(
                "L3 structural priority should be treated cautiously, not as a hard blocker: "
                + "; ".join(l3_structural_warnings)
            )
        if semantic_warnings:
            suggested_fixes.append(
                "Review indicator authority before publishing: "
                + "; ".join(semantic_warnings[:8])
            )

        passed = not structural_issues and not consistency_issues and not missing_fields
        quality_status = "review_required" if semantic_warnings or not passed else "passed"
        return SchemaGuardReport(
            passed=passed,
            structural_issues=structural_issues,
            consistency_issues=consistency_issues,
            missing_fields=missing_fields,
            suggested_fixes=suggested_fixes,
            quality_status=quality_status,
        )

    def _analysis_required_function_ids(self, packet: AnalysisPacket, layer: str) -> List[str]:
        layer_data = packet.raw_data.get(layer, {})
        if not isinstance(layer_data, dict):
            return []
        required = []
        for function_id, payload in layer_data.items():
            if not isinstance(payload, dict):
                continue
            if self._indicator_unavailable_for_analysis(payload):
                continue
            required.append(str(payload.get("function_id") or function_id))
        return required

    def _analysis_required_indicator_map(self, packet: AnalysisPacket, layer: str) -> Dict[str, str]:
        layer_data = packet.raw_data.get(layer, {})
        if not isinstance(layer_data, dict):
            return {}
        required: Dict[str, str] = {}
        for function_id, payload in layer_data.items():
            if not isinstance(payload, dict):
                continue
            if self._indicator_unavailable_for_analysis(payload):
                continue
            resolved_function_id = str(payload.get("function_id") or function_id)
            required[resolved_function_id] = str(
                payload.get("metric_name")
                or payload.get("name")
                or resolved_function_id
            )
        return required

    def _indicator_unavailable_for_analysis(self, payload: Dict[str, Any]) -> bool:
        return indicator_payload_unavailable_reason(payload) is not None

    def _compose_prompt(self, stage_key: str, model_cls: Type[Any], payload: Dict[str, Any]) -> str:
        prompt_payload = self._sanitize_prompt_payload(stage_key, payload)
        prompt_body = self._load_prompt(stage_key)
        if stage_key.startswith("l") and stage_key.endswith("_analyst"):
            prompt_body = self._compose_layer_prompt(stage_key, prompt_body, prompt_payload)
        elif stage_key == "bridge":
            prompt_body = self._compose_bridge_prompt(prompt_body, prompt_payload)
        elif stage_key == "thesis":
            prompt_body = self._compose_thesis_prompt(prompt_body, prompt_payload)
        fields = list(getattr(model_cls, "model_fields", {}).keys())
        schema_hint = ", ".join(fields) if fields else model_cls.__name__
        field_spec = self._render_contract_field_spec(model_cls)
        return (
            f"{prompt_body}\n\n"
            "## Runtime Input\n"
            f"{json.dumps(prompt_payload, ensure_ascii=False, indent=2, default=str)}\n\n"
            f"{field_spec}"
            "## Response Rules\n"
            "- 只返回一个 JSON 对象。\n"
            "- 不要使用 markdown code fence。\n"
            f"- JSON 顶层字段必须匹配: {schema_hint}。\n"
            "- 字段的**形状**（对象 / 数组 / 标量、是否可为 null）以上面「输出字段规格」为准；"
            "正文里的示例只解释语义，形状冲突时以规格为准。\n"
            "- 不要编造新的外部数据源，只能使用输入中的信息。\n"
        )

    # 一层嵌套里最多列几个**自由形状**子字段名，超出用省略号——够模型判断"这是对象不是数组"，
    # 又不至于把整棵 schema 树铺进 prompt。受限子字段（Literal / dict）不受该上限约束：
    # 它们猜错就是硬失败，必须每一个都带类型出现（见 _render_contract_nested_hint）。
    _CONTRACT_SPEC_NESTED_FIELD_LIMIT = 8
    _CONTRACT_SPEC_DESCRIPTION_LIMIT = 70

    # 受限子字段最多往下钻几层。深处只报"猜错就硬失败"的字段，不报自由文本字段——
    # 既堵住 ClaimLedgerEntry 这类藏在第二层的枚举，又不至于把整棵 schema 铺进 prompt。
    _CONTRACT_SPEC_MAX_NESTED_DEPTH = 2

    @classmethod
    def _render_contract_nested_hint(cls, annotation: Any, *, depth: int = 0) -> str:
        """嵌套子字段里"猜错就硬失败"的那部分类型，渲染成一小段紧凑提示。

        覆盖 Literal（取值必须落在枚举里）、dict（必须是对象）与 list（必须是数组），
        因为这三类是 pydantic 会当场硬拒的形状；字符串 / 数字 不标注，字段名本身够用，
        全量铺开会把规格撑成第二份 schema。

        真实事故 run 20260728_222759：`CoreFact.magnitude`(Literal) 与 `raw_data`(dict)
        在规格里只有名字，模型分别填成 -4.9 和一句描述文本，L1 两次尝试全废、整跑终止。
        同一跑的终审又证伪了"复数字段名足以暗示数组"这个判断：`uncertainty_notes`
        (List[str]) 被写成一整句话，终审首次尝试即被拒——数组必须和枚举、对象一样明说。
        """
        import typing

        origin = typing.get_origin(annotation)
        args = typing.get_args(annotation)
        if origin is typing.Union or (
            origin is not None and getattr(origin, "__name__", "") == "UnionType"
        ):
            for arg in args:
                if arg is type(None):  # noqa: E721
                    continue
                hint = cls._render_contract_nested_hint(arg, depth=depth)
                if hint:
                    return hint
            return ""
        if origin is typing.Literal:
            return ":" + "|".join(json.dumps(arg, ensure_ascii=False) for arg in args)
        if origin is dict:
            return ":对象"
        if origin in (list, set, tuple):
            inner = (
                cls._render_contract_nested_hint(args[0], depth=depth) if args else ""
            )
            # 元素形状不受限时也要留下空方括号——"是不是数组"本身就是硬失败点。
            return f":[{inner.lstrip(':')}]"
        if depth < cls._CONTRACT_SPEC_MAX_NESTED_DEPTH and isinstance(annotation, type):
            sub_fields = getattr(annotation, "model_fields", None)
            if sub_fields is not None:
                parts = [
                    f"{name}{hint}"
                    for name, field in sub_fields.items()
                    if (
                        hint := cls._render_contract_nested_hint(
                            getattr(field, "annotation", None), depth=depth + 1
                        )
                    )
                ]
                if parts:
                    # 只列了受限字段，用省略号如实交代"还有别的字段没写在这里"。
                    return f":对象 {annotation.__name__}{{{', '.join(parts)}, …}}"
        return ""

    @classmethod
    def _render_contract_type(cls, annotation: Any, *, depth: int = 0) -> str:
        """把 pydantic 字段注解渲染成一句人能读、模型也能照做的形状说明。"""
        import enum
        import typing

        origin = typing.get_origin(annotation)
        args = [arg for arg in typing.get_args(annotation)]
        if origin is typing.Union or str(origin) == "typing.Union" or (
            origin is not None and getattr(origin, "__name__", "") == "UnionType"
        ):
            non_none = [arg for arg in args if arg is not type(None)]  # noqa: E721
            rendered = " 或 ".join(cls._render_contract_type(arg, depth=depth) for arg in non_none)
            return f"{rendered} 或 null" if len(non_none) < len(args) else rendered
        if origin is typing.Literal or str(origin) == "typing.Literal":
            return "取值之一：" + " / ".join(json.dumps(arg, ensure_ascii=False) for arg in args)
        if origin in (list, set, tuple):
            inner = cls._render_contract_type(args[0], depth=depth) if args else "任意值"
            return f"数组，元素为 {inner}"
        if origin is dict:
            return "对象（键自由）"
        if isinstance(annotation, type):
            if issubclass(annotation, enum.Enum):
                return "取值之一：" + " / ".join(
                    json.dumps(getattr(member, "value", member.name), ensure_ascii=False)
                    for member in annotation
                )
            if annotation is bool:
                return "布尔"
            if annotation in (int, float):
                return "数字"
            if annotation is str:
                return "字符串"
            if annotation is datetime:
                return "ISO8601 时间字符串"
            sub_fields = getattr(annotation, "model_fields", None)
            if sub_fields is not None:
                if depth >= 1:
                    return f"对象 {annotation.__name__}"
                shown: List[str] = []
                budget = cls._CONTRACT_SPEC_NESTED_FIELD_LIMIT
                for sub_name, sub_field in sub_fields.items():
                    hint = cls._render_contract_nested_hint(
                        getattr(sub_field, "annotation", None)
                    )
                    if hint:
                        # 受限子字段不占名额：漏掉一个就等于让模型猜一个硬失败点。
                        shown.append(f"{sub_name}{hint}")
                    elif budget > 0:
                        shown.append(sub_name)
                        budget -= 1
                suffix = ", …" if len(shown) < len(sub_fields) else ""
                return f"对象 {annotation.__name__}{{{', '.join(shown)}{suffix}}}"
        return "任意值"

    def _render_contract_field_spec(self, model_cls: Type[Any]) -> str:
        """由契约本身生成输出字段规格，取代"靠人记得把字段写进说明书"。

        2026-07-28 用户裁决：合约写在代码里、说明书写在 prompt 里、再拿一张关键词
        登记表对账——这套"三件套"并没有消除重复，而是把两份变成三份，而且只查关键词
        在不在、不查解释对不对。**形状漂移**这一类可以从结构上根除：契约里每个字段本来
        就带 `description`，直接由 `model_fields` 生成规格即可，模型永远不可能收到一份
        漏掉某个字段的说明书。

        它只覆盖形状与字段存在性（真实事故：`claim_ledger` 在 final_adjudicator.md 里
        零覆盖、模型猜成裸数组；counter_thesis 猜错字段名烧掉 28 万 token）；行为规则
        （例如"必须逐一回应非 downgraded 假说"）仍由手写说明书承担，那部分由
        `STAGE_CONTRACT_PROMPT_REQUIREMENTS` 登记闸门守。
        """
        model_fields = getattr(model_cls, "model_fields", None)
        if not model_fields:
            return ""
        lines: List[str] = []
        for name, field in model_fields.items():
            shape = self._render_contract_type(getattr(field, "annotation", None))
            necessity = "必填" if field.is_required() else "可选"
            description = str(getattr(field, "description", "") or "").strip()
            if len(description) > self._CONTRACT_SPEC_DESCRIPTION_LIMIT:
                description = description[: self._CONTRACT_SPEC_DESCRIPTION_LIMIT] + "…"
            tail = f" —— {description}" if description else ""
            lines.append(f"- `{name}`（{necessity}）：{shape}{tail}")
        return (
            f"## 输出字段规格（由 {model_cls.__name__} 契约自动生成，形状以此为准）\n"
            + "\n".join(lines)
            + "\n\n"
        )

    def _sanitize_prompt_payload(self, stage_key: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Return the exact payload that may be serialized into an LLM prompt."""
        if stage_key == "bridge":
            return self._strip_empty_event_prompt_fields(payload)
        if stage_key == "thesis":
            slimmed = self._slim_object_run_gate_for_prompt(payload)
            slimmed = self._drop_low_value_synthesis_fields_for_prompt(
                slimmed, "synthesis_packet", NARRATIVE_STAGE_PROMPT_DROP_FIELDS["thesis"]
            )
            slimmed = self._slim_evidence_index_for_prompt(slimmed, "synthesis_packet")
            return self._strip_empty_event_prompt_fields(slimmed)
        if stage_key == "counter_thesis":
            slimmed = self._drop_low_value_synthesis_fields_for_prompt(
                payload,
                "synthesis_packet_without_self_reference",
                NARRATIVE_STAGE_PROMPT_DROP_FIELDS["counter_thesis"],
            )
            slimmed = self._slim_evidence_index_for_prompt(slimmed, "synthesis_packet_without_self_reference")
            return self._strip_empty_event_prompt_fields(slimmed)
        if not (stage_key.startswith("l") and stage_key.endswith("_analyst")):
            return payload
        sanitized = dict(payload)
        layer = str(sanitized.get("layer") or stage_key[:2].upper())
        raw_data = self._filter_layer_raw_data_for_prompt(
            layer,
            sanitized.get("layer_raw_data", {}),
        )
        if layer.upper() == "L4":
            raw_data = self._summarize_l4_raw_data_for_prompt(raw_data)
        sanitized["layer_raw_data"] = raw_data
        sanitized.pop("runtime_boundary_policy_id", None)
        return sanitized

    def _slim_object_run_gate_for_prompt(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Keep full object gate in artifacts, but send only the decision-relevant kernel to prompts."""
        sanitized = dict(payload)
        synthesis = sanitized.get("synthesis_packet")
        if not isinstance(synthesis, dict):
            return sanitized
        packet_meta = synthesis.get("packet_meta")
        if not isinstance(packet_meta, dict):
            return sanitized
        object_gate = packet_meta.get("object_run_gate")
        if not isinstance(object_gate, dict):
            return sanitized
        slim_meta = dict(packet_meta)
        slim_meta["object_run_gate"] = {
            "schema_version": object_gate.get("schema_version", "object_run_gate_v1"),
            "primary_object": object_gate.get("primary_object", "NDX"),
            "tradable_proxy": object_gate.get("tradable_proxy", "QQQ"),
            "equal_weight_references": object_gate.get("equal_weight_references", []),
            "date_boundary": object_gate.get("date_boundary"),
            "prompt_note": "Full object boundary is stored in analysis_packet meta; use this only as object scope.",
        }
        slim_synthesis = dict(synthesis)
        slim_synthesis["packet_meta"] = slim_meta
        sanitized["synthesis_packet"] = slim_synthesis
        return sanitized

    def _drop_low_value_synthesis_fields_for_prompt(
        self,
        payload: Dict[str, Any],
        synthesis_key: str,
        drop_fields: tuple,
    ) -> Dict[str, Any]:
        """Drop SynthesisPacket top-level fields that neither thesis_builder.md nor
        counter_thesis.md ever asks the model to read (see investigation_reports/
        20260725_thesis_counter_thesis_slimming/PROPOSAL.md). Only affects the text
        actually serialized into the prompt; the full payload passed into
        _run_thesis / _counter_thesis_prompt_payload (used for checkpoint diffing
        and prompt_input_audit) is untouched.
        """
        sanitized = dict(payload)
        synthesis = sanitized.get(synthesis_key)
        if not isinstance(synthesis, dict):
            return sanitized
        sanitized[synthesis_key] = {
            key: value for key, value in synthesis.items() if key not in drop_fields
        }
        return sanitized

    def _slim_evidence_index_for_prompt(self, payload: Dict[str, Any], synthesis_key: str) -> Dict[str, Any]:
        """Compress audit-only nested detail out of evidence_index before it reaches
        the Thesis / Counter-Thesis prompt text.

        不删除、不重命名任何 evidence_ref key —— 两站的引用合法性校验完全依赖
        key 是否存在，与 value 内容无关。只压缩每条记录 field_value 里超长的
        逐票/逐日审计明细（如全成分明细、raw_series 历史序列），聚合字段
        （value/coverage/windows/...）原样保留。完整明细继续留在持久化的
        synthesis_packet.json / evidence_registry.json 中。
        """
        sanitized = dict(payload)
        synthesis = sanitized.get(synthesis_key)
        if not isinstance(synthesis, dict):
            return sanitized
        evidence_index = synthesis.get("evidence_index")
        if not isinstance(evidence_index, dict):
            return sanitized
        slim_index: Dict[str, Any] = {}
        for ref, entry in evidence_index.items():
            if not isinstance(entry, dict) or "field_value" not in entry:
                slim_index[ref] = entry
                continue
            entry_copy = dict(entry)
            entry_copy["field_value"] = self._slim_long_list_for_prompt(entry_copy["field_value"])
            slim_index[ref] = entry_copy
        slim_synthesis = dict(synthesis)
        slim_synthesis["evidence_index"] = slim_index
        sanitized[synthesis_key] = slim_synthesis
        return sanitized

    @classmethod
    def _slim_long_list_for_prompt(cls, value: Any) -> Any:
        """Recursively replace oversized nested lists with a count+sample summary.

        阈值见 EVIDENCE_FIELD_LIST_PROMPT_COUNT_THRESHOLD /
        EVIDENCE_FIELD_LIST_PROMPT_CHAR_THRESHOLD：条数和序列化字符数都超过阈值
        才判定为审计明细，避免误伤本来就短的合法列表（如季度趋势这类只有几条、
        但本身就是叙事所需信号的列表）。
        """
        if isinstance(value, list):
            if len(value) > EVIDENCE_FIELD_LIST_PROMPT_COUNT_THRESHOLD:
                serialized_len = len(json.dumps(value, ensure_ascii=False, default=str))
                if serialized_len > EVIDENCE_FIELD_LIST_PROMPT_CHAR_THRESHOLD:
                    sample_items = value[:2] + (value[-1:] if len(value) > 3 else [])
                    return {
                        "_prompt_summary": True,
                        "count": len(value),
                        "sample": [cls._slim_long_list_for_prompt(item) for item in sample_items],
                        "note": (
                            "完整明细保留在 synthesis_packet.json / evidence_registry.json 供审计与"
                            "独立重算；聚合统计见同级 value/coverage/windows 等字段。"
                        ),
                    }
            return [cls._slim_long_list_for_prompt(item) for item in value]
        if isinstance(value, dict):
            return {key: cls._slim_long_list_for_prompt(item) for key, item in value.items()}
        return value

    def _slim_governance_key_evidence_refs(
        self,
        key_evidence_refs: Dict[str, Dict[str, Any]],
    ) -> Dict[str, Dict[str, Any]]:
        """A 档证据索引瘦身：只压 field_value，ref key 集合不动、聚合字段逐字节不变。

        供 reviser/final 的 governance_input.key_evidence_refs 使用；critic 默认行为
        不回退（仍拿完整 evidence_index 子集）。完整明细继续留在落盘的
        synthesis_packet.json / evidence_registry.json 中。
        """
        slimmed: Dict[str, Dict[str, Any]] = {}
        for ref, entry in key_evidence_refs.items():
            if not isinstance(entry, dict) or "field_value" not in entry:
                slimmed[ref] = entry
                continue
            entry_copy = dict(entry)
            entry_copy["field_value"] = self._slim_long_list_for_prompt(entry_copy["field_value"])
            slimmed[ref] = entry_copy
        return slimmed

    def _strip_empty_event_prompt_fields(self, payload: Any) -> Any:
        if isinstance(payload, dict):
            stripped: Dict[str, Any] = {}
            for key, value in payload.items():
                cleaned = self._strip_empty_event_prompt_fields(value)
                if key in {"event_refs", "event_index", "key_event_refs"} and cleaned in ({}, [], None):
                    continue
                stripped[key] = cleaned
            return stripped
        if isinstance(payload, list):
            return [self._strip_empty_event_prompt_fields(item) for item in payload]
        return payload

    def _compose_layer_prompt(self, stage_key: str, prompt_body: str, payload: Dict[str, Any]) -> str:
        layer = str(payload.get("layer") or stage_key[:2].upper())
        layer_raw_data = payload.get("layer_raw_data", {})
        layer_raw_data = self._filter_layer_raw_data_for_prompt(layer, layer_raw_data)
        expected_indicators = self._layer_indicator_manifest(layer_raw_data)
        # B4 修复：结构示例必须用本层真实存在的指标，不得把 L1 的 get_10y_real_rate
        # 当通用示例塞给所有层。用清单第一项动态渲染；本层无指标时示例留空。
        first_indicator = expected_indicators[0] if expected_indicators else {}
        example_function_id = str(first_indicator.get("function_id") or "").strip()
        example_metric = str(first_indicator.get("metric_name") or example_function_id)
        example_ref = f"{layer}.{example_function_id}" if example_function_id else ""
        canon_prompt = build_layer_canon_prompt(layer=layer, layer_raw_data=layer_raw_data)
        few_shot = build_layer_few_shot_prompt(layer=layer, layer_raw_data=layer_raw_data)
        v2_contract = (
            "## vNext v2 Context-Bounded Professional Layer Contract\n"
            "你在一个隔离的本层上下文中工作：角色是专业认知镜头，context boundary 是信息隔离边界。"
            "先用本层专家视角完成指标级研究，再把结果压缩为可审计、可展示、可被 Bridge 消费的结构化产物。\n\n"
            "### 静态五层本体（只用于路由，不代表当前状态）\n"
            "- L1: 宏观流动性、利率、实际利率、期限结构、货币供应、净流动性和增长预期代理。\n"
            "- L2: 风险偏好、信用利差、波动率、情绪、仓位和拥挤度。\n"
            "- L3: 指数内部结构、广度、集中度、等权/市值权重差异和领导力质量。\n"
            "- L4: 估值、盈利收益率、简式收益差距、Damodaran 美国 implied ERP 参考锚、安全边际和估值压缩风险。\n"
            "- L5: 价格趋势、动量、波动、成交量、支撑阻力和趋势失效触发。\n"
            "- Bridge: 读取各层结构化产物，验证跨层共振、冲突和传导机制。\n"
            "以上只是职责边界和接口协议，不是其他层的当前数据、状态或结论。"
            "你可以据此决定把验证问题路由给哪一层，但不得据此推断其他层现在是 bullish、bearish、expensive、healthy 或 uptrend。\n\n"
            "### 必须新增并认真填写的字段\n"
            "- local_conclusion: 必填字段，最多500字符，本层最核心的一句结论（例如"
            "\"估值处于历史高位但盈利韧性提供部分支撑\"）；缺失会被结构校验直接拒绝，"
            "不允许省略或留空。\n"
            "- indicator_analyses: 对每一个 analysis_required=true 的指标输出一条原生分析。\n"
            "- indicator_analyses[].function_id 必须等于输入 function_id。\n"
            "- indicator_analyses[].metric 必须优先等于输入 metric_name。\n"
            "- indicator_analyses[].evidence_refs 必须是字符串数组，例如 [\"L2.get_vix\"]，不得输出对象/dict。\n"
            "- 若一个 payload 的 MetricAuthority 含不同 usage，它是 mixed-field payload；引用其中任何字段时必须写成 L4.function_id#FieldName。父级 L4.function_id 只能表示混合容器，不能支撑强字段结论。\n"
            "- indicator_analyses[].narrative 是可进入最终报告的典范化解读。\n"
            "- indicator_analyses[].reasoning_process 必须展示从当前读数、分位/趋势到局部判断的因果推理。\n"
            "- indicator_analyses[].first_principles_chain 用列表写出机制链，例如 利率上升 -> 折现率上升 -> 成长股估值受压。\n"
            "- layer_synthesis 必须由 indicator_analyses 归纳，不能只重复 local_conclusion，并应适合该层独立 UI 展示。\n"
            "- internal_conflict_analysis 必须讨论本层内部指标之间的共振、背离、降噪和优先级，也应适合展开阅读。\n"
            "- quality_self_check 必须开放说明覆盖情况、弱推理点和置信度边界。\n\n"
            "### 隔离纪律\n"
            "- 允许知道其他层负责什么；禁止假设其他层当前看到了什么、判断了什么。\n"
            "- 跨层内容只能写成待 Bridge 验证的问题，不能写成已经成立的跨层结论。\n"
            "- 不得为了形成完整市场故事而提前综合其他层。\n"
            "- 不得给出最终买卖建议。\n\n"
            "### 数值单位纪律\n"
            "- 引用金额/规模数值时必须带上 payload 中的 unit 单位；payload 无单位标注时不得猜测单位，只能写明“单位未标注”。\n\n"
            "### 当前层指标清单\n"
            f"{json.dumps(expected_indicators, ensure_ascii=False, indent=2, default=str)}\n\n"
            "### 结构示例\n"
            "{\n"
            '  "indicator_analyses": [\n'
            "    {\n"
            f'      "function_id": {json.dumps(example_function_id)},\n'
            f'      "metric": {json.dumps(example_metric)},\n'
            '      "current_reading": "该指标当前读数（引用 payload 实际数值）",\n'
            '      "normalized_state": "neutral",\n'
            '      "narrative": "把读数、趋势与分位压缩成一句本层判断。",\n'
            '      "reasoning_process": "先看水平，再看趋势和分位，最后落到本层职责内的判断。",\n'
            '      "first_principles_chain": ["读数事实", "本层机制", "本层判断"],\n'
            f'      "evidence_refs": {json.dumps([example_ref] if example_ref else [])},\n'
            '      "cross_layer_implications": ["只写待 Bridge 验证的问题，不写跨层结论"],\n'
            '      "risk_flags": ["本层风险标签"],\n'
            '      "confidence": "medium"\n'
            "    }\n"
            "  ],\n"
            '  "quality_self_check": {\n'
            '    "coverage_complete": true,\n'
            f'    "covered_function_ids": {json.dumps([example_function_id] if example_function_id else [])},\n'
            '    "missing_or_weak_indicators": [],\n'
            '    "weak_reasoning_points": [],\n'
            '    "unresolved_internal_tensions": [],\n'
            '    "confidence_limitations": ["具体限制以本层指标清单与 payload 为准"]\n'
            "  }\n"
            "}\n"
        )
        parts = [part for part in [canon_prompt, few_shot, v2_contract, prompt_body] if part]
        return "\n\n".join(parts)

    def _compose_bridge_prompt(self, prompt_body: str, payload: Optional[Dict[str, Any]] = None) -> str:
        bridge_contract = (
            "## vNext v2 Bridge Contract\n"
            "Bridge 的职责不是重新解释单个指标，而是读取各 LayerCard 的 indicator_analyses、layer_synthesis、"
            "internal_conflict_analysis 和 cross_layer_hooks，识别跨层共振、冲突、传导机制与不确定性。\n\n"
            "必须优先使用 indicator_analyses[].reasoning_process 中已经完成的专业推理；"
            "如果要提出冲突，必须指出冲突来自哪些层、哪些指标或哪些机制。\n"
            "输出仍保持 BridgeMemo 结构，但 conflicts 和 cross_layer_claims 需要引用具体 function_id。\n"
            "cross_layer_claims[].supporting_facts 只能填写 evidence ref 字符串，格式如 "
            "\"L4.get_ndx_pe_and_earnings_yield\"；不要写中文事实句、数值解释或自然语言，"
            "这些解释应放在 claim 或 mechanism。若 LayerCard 标出 mixed-field payload，必须沿用其显式 "
            "#FieldName 子引用；不得退回函数级父 ref。"
        )
        bridge_contract += (
            "\nBridge v2 新增字段必须尽量原生填写：\n"
            "- typed_conflicts: 结构化冲突地图，包含 conflict_id、conflict_type、severity、confidence、description、mechanism、implication、involved_layers、evidence_refs、falsifiers。\n"
            "- resonance_chains: 跨层共振链，必须包含 involved_layers、evidence_refs、mechanism、confirming_indicators、falsifiers、implication；没有证据或确认指标时降低 confidence。\n"
            "- transmission_paths: 跨层传导路径，说明压力或支撑如何从 source_layer 传到 target_layer。\n"
            "- principal_contradiction: 主要矛盾地图，必须说明 contradiction_id、summary、why_principal、dominant_side、secondary_side、price_reflection、action_implication、conflict_refs、evidence_refs、transformation_signals。\n"
            "- secondary_contradictions: 次要矛盾列表，说明为什么当前不是主导项，以及它如何约束行动力度、节奏或置信度。\n"
            "- price_reflection_map: 判断关键风险/叙事是否已经进入价格，可用 not_reflected / partially_reflected / largely_reflected / over_reflected / unclear。\n"
            "- contradiction_transformation_signals: 会让主次矛盾或矛盾主导方面发生转化的可观察信号。\n"
            "- unresolved_questions: 仍需 Thesis/Critic/Risk 保留的问题。\n"
            "旧字段 conflicts 仍要填写，用于兼容；typed_conflicts 是更高优先级的 Bridge v2 产物。\n"
        )
        bridge_contract += (
            "\n## 事件纪律（三明治口径，恒空）\n"
            "- 本轮输入不包含任何事件材料；BridgeMemo.event_refs 必须保持为空列表 []。\n"
            "- 不得自行引入事件 ID、不得把事件写成 evidence_ref；evidence_refs 中出现 event: 前缀会被校验器打回。\n"
        )
        return f"{bridge_contract}\n\n{prompt_body}"

    def _compose_thesis_prompt(self, prompt_body: str, payload: Optional[Dict[str, Any]] = None) -> str:
        synthesis_payload = payload.get("synthesis_packet") if isinstance(payload, dict) else {}
        has_event_input = bool(isinstance(synthesis_payload, dict) and synthesis_payload.get("event_index"))
        thesis_contract = (
            "## vNext v2 Decision Thesis Contract\n"
            "你现在只消费 synthesis_packet。不要重新分析原始数据，不要替 L1-L5 补写单指标推理。"
            "你的职责是把 layer_summaries、bridge_summaries、high_severity_conflicts 与 evidence_index "
            "整合成主论点、支撑链、保留冲突、依赖前提，以及定价与赔率判断面。\n\n"
            "key_support_chains[].evidence_refs 应引用 synthesis_packet.evidence_index 的键或 Bridge 摘要。"
            "若 evidence_index 条目标记 mixed_field_authority=true，函数级父 ref 不能支持强结论；必须改用同一索引内显式的 #FieldName 子 ref。"
            "retained_conflicts 必须包含 synthesis_packet.high_severity_conflicts 中的所有高严重度冲突。"
        )
        thesis_contract += (
            "\n必须读取 synthesis_packet.objective_firewall_summary，检查投资对象、指标发言权、跨层验证和最强反证。"
            "如果 objective_firewall_summary 的 object_clear、authority_clear 或 cross_layer_verified 为 false，"
            "不得给出强结论，必须降低 confidence 并在 dependencies/retained_conflicts 中保留相应边界。"
        )
        if has_event_input:
            thesis_contract += (
                "如果使用 synthesis_packet.event_index，只能把 event_refs 写成催化剂、背景或观察事项；"
                "不得让 event_refs 替代 key_support_chains[].evidence_refs。"
            )
        thesis_contract += (
            "\n\nDecision Semantics 必填语义："
            "state_diagnosis 说明当前市场状态；priced_narrative 说明价格正在定价什么、哪些坏消息已/未反映；"
            "payoff_assessment 必须区分高风险高赔率、高风险低赔率、低风险低赔率等；"
            "time_horizon_views 至少覆盖数日、1-3个月、6-12个月；"
            "portfolio_actions 至少覆盖 core_position、tactical_position、waiting_cash；"
            "confirmation_cost 必须说明等待确认降低什么风险、可能错过什么；"
            "invalidation_conditions 必须是可观察条件；reader_conclusion 面向普通读者，不能写内部审批话术。"
            "principal_contradiction 必须来自 synthesis_packet.principal_contradictions 或 bridge_summaries[].principal_contradiction，并说明 why_principal、price_reflection、action_implication；"
            "secondary_contradictions 和 price_reflection_map 必须保留关键次要矛盾和定价判断。"
            "不要把“风险存在”自动等同于“赔率不利”，也不要把“估值改善”自动等同于可以买。"
        )
        return f"{thesis_contract}\n\n{prompt_body}"

    def _filter_layer_raw_data_for_prompt(self, layer: str, layer_raw_data: Any) -> Any:
        """Drop cross-layer indicators and prompt-only audit bookkeeping."""
        if not isinstance(layer_raw_data, dict):
            return layer_raw_data

        layer_value = str(layer).upper()
        filtered: Dict[str, Any] = {}
        for key, payload in layer_raw_data.items():
            function_id = str(payload.get("function_id") or key) if isinstance(payload, dict) else str(key)
            try:
                canon = get_indicator_canon(function_id)
            except KeyError:
                filtered[key] = self._strip_prompt_audit_bookkeeping_fields(payload)
                continue
            if canon.layer.value == layer_value:
                filtered[key] = self._strip_prompt_audit_bookkeeping_fields(payload)
        return filtered

    @classmethod
    def _strip_prompt_audit_bookkeeping_fields(cls, value: Any) -> Any:
        if isinstance(value, dict):
            return {
                key: cls._strip_prompt_audit_bookkeeping_fields(item)
                for key, item in value.items()
                if key not in PROMPT_AUDIT_BOOKKEEPING_FIELDS
            }
        if isinstance(value, list):
            return [cls._strip_prompt_audit_bookkeeping_fields(item) for item in value]
        return value

    def _summarize_l4_raw_data_for_prompt(self, layer_raw_data: Dict[str, Any]) -> Dict[str, Any]:
        """压缩 L4 prompt 中的长序列数据。

        长序列（如 Damodaran monthly 120 条）留在 artifact，prompt 只保留
        latest/start/end/count/percentile/关键拐点，显著降低 token 成本。
        """
        summarized: Dict[str, Any] = {}
        for key, payload in layer_raw_data.items():
            if not isinstance(payload, dict):
                summarized[key] = payload
                continue
            value = payload.get("value")
            if not isinstance(value, dict):
                summarized[key] = payload
                continue
            new_value = dict(value)
            for field_name, field_value in list(value.items()):
                if isinstance(field_value, list) and len(field_value) > 10:
                    new_value[field_name] = self._summarize_long_series(field_value)
            summarized[key] = {**payload, "value": new_value}
        return summarized

    @staticmethod
    def _summarize_long_series(series: List[Dict[str, Any]], keep_recent: int = 5) -> Dict[str, Any]:
        """对长序列列表计算统计摘要，同时保留最近 N 条精简记录和趋势方向。

        recent_records 只保留 data_date 和数值字段的最新值，避免完整 dict 塞入 prompt。
        """
        if not series:
            return {"count": 0, "summary": "empty"}
        count = len(series)
        first = series[0]
        last = series[-1]

        # Single-pass: collect numeric values per column
        col_values: Dict[str, List[float]] = {}
        if isinstance(first, dict):
            for item in series:
                if not isinstance(item, dict):
                    continue
                for col, v in item.items():
                    if isinstance(v, (int, float)) and v is not None:
                        col_values.setdefault(col, []).append(v)

        numeric_stats: Dict[str, Dict[str, Any]] = {}
        numeric_cols: List[str] = []
        for col, values in col_values.items():
            numeric_cols.append(col)
            mid = len(values) // 2
            first_half_mean = sum(values[:mid]) / mid if mid > 0 else values[0]
            second_half_mean = sum(values[mid:]) / len(values[mid:]) if values[mid:] else values[-1]
            if second_half_mean > first_half_mean * 1.02:
                trend = "rising"
            elif second_half_mean < first_half_mean * 0.98:
                trend = "falling"
            else:
                trend = "stable"
            numeric_stats[col] = {
                "min": round(min(values), 6),
                "max": round(max(values), 6),
                "mean": round(sum(values) / len(values), 6),
                "latest": round(values[-1], 6),
                "trend": trend,
            }

        raw_recent = series[-keep_recent:] if count > keep_recent else series
        recent_items = []
        for item in raw_recent:
            if not isinstance(item, dict):
                continue
            compact = {}
            if "data_date" in item:
                compact["data_date"] = item["data_date"]
            for col in numeric_cols:
                if col in item and item[col] is not None:
                    compact[col] = item[col]
            recent_items.append(compact)
        return {
            "count": count,
            "period_start": first.get("data_date") if isinstance(first, dict) else None,
            "period_end": last.get("data_date") if isinstance(last, dict) else None,
            "latest_record": last if isinstance(last, dict) else None,
            "numeric_summary": numeric_stats,
            "recent_records": recent_items,
            "note": f"显示最近 {len(recent_items)}/{count} 条记录（仅 data_date + 数值）。完整序列在 chart_time_series.json artifact 中可用。",
        }

    def _layer_indicator_manifest(self, layer_raw_data: Any) -> List[Dict[str, Any]]:
        if not isinstance(layer_raw_data, dict):
            return []
        manifest: List[Dict[str, Any]] = []
        for function_id, payload in layer_raw_data.items():
            if not isinstance(payload, dict):
                continue
            manifest.append(
                {
                    "function_id": payload.get("function_id") or function_id,
                    "metric_name": payload.get("metric_name") or payload.get("name") or function_id,
                    "analysis_required": not self._indicator_unavailable_for_analysis(payload),
                    "error": payload.get("error"),
                    "source_tier": payload.get("source_tier") or (payload.get("data_quality") or {}).get("source_tier"),
                    "source_name": payload.get("source_name"),
                    "date": payload.get("date"),
                    "notes": payload.get("notes"),
                    "manual_override_used": payload.get("manual_override_used", False),
                }
            )
        return manifest

    def _run_and_save(
        self,
        *,
        stage_key: str,
        stage_name: str,
        model_cls: type,
        payload: dict,
        filename: str,
        validator: Optional[Callable[[Any], List[str]]] = None,
        pre_validate_transform: Optional[Callable[[Dict[str, Any]], Dict[str, Any]]] = None,
        strict_tool_schema: Optional[Dict[str, Any]] = None,
        strict_tool_name: Optional[str] = None,
    ) -> Any:
        checkpoint = self._load_stage_checkpoint(
            filename,
            model_cls,
            stage_key=stage_key,
            stage_name=stage_name,
            expected_payload=payload,
        )
        if checkpoint is not None:
            return checkpoint
        result = self._run_stage(
            stage_key=stage_key,
            stage_name=stage_name,
            model_cls=model_cls,
            payload=payload,
            validator=validator,
            pre_validate_transform=pre_validate_transform,
            strict_tool_schema=strict_tool_schema,
            strict_tool_name=strict_tool_name,
        )
        self._save_json(filename, result)
        path = Path(filename)
        if not path.is_absolute():
            path = self.output_dir / path
        self._record_stage_artifact(path, stage_key=stage_key, stage_name=stage_name, payload=payload)
        return result

    def _load_prompt(self, stage_key: str) -> str:
        prompt_name = PROMPT_FILES.get(stage_key)
        if prompt_name:
            prompt_path = self.prompts_dir / prompt_name
            if prompt_path.exists():
                return prompt_path.read_text(encoding="utf-8")
        else:
            prompt_path = self.prompts_dir / f"{stage_key}.md"
        if stage_key in INLINE_PROMPTS:
            return INLINE_PROMPTS[stage_key]
        raise RuntimeError(
            f"未找到 stage `{stage_key}` 的 prompt 文件（期望路径：{prompt_path}），"
            "且 INLINE_PROMPTS 没有对应兜底条目。绝不静默返回通用占位 prompt。"
        )

    def _normalize_historical_percentile(self, value: Any) -> tuple[Optional[float], Optional[str]]:
        if value is None or isinstance(value, bool):
            return None, None
        if isinstance(value, (int, float)):
            number = float(value)
            return (number, None) if 0 <= number <= 100 else (None, str(value))
        if isinstance(value, str):
            text = value.strip()
            match = re.fullmatch(r"([0-9]+(?:\.[0-9]+)?)\s*%?", text)
            if match:
                number = float(match.group(1))
                return (number, None) if 0 <= number <= 100 else (None, text)
            if text:
                return None, text
        return None, str(value)

    def _save_json(self, filename: str | Path, payload: Any) -> None:
        path = Path(filename)
        if not path.is_absolute():
            path = self.output_dir / path
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as handle:
            json.dump(_model_dump(payload), handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        self._record_stage_artifact(path)

    def _run_persistent_checks(self) -> Dict[str, Any]:
        """常设检查接线：懒导入 A/B 两包，以本 run 的 output_dir 为 run_dir 执行。

        两条结果合并写 `persistent_checks_report.json`；任何异常只写 failed 汇总，
        绝不让主链崩溃。检查包未交付时写 status="modules_missing"。
        """
        report_path = "persistent_checks_report.json"
        try:
            from agent_analysis.persistent_checks_a import run_checks_a
            from agent_analysis.persistent_checks_b import run_checks_b
        except ImportError:
            report = {
                "schema_version": "vnext_persistent_checks_v1",
                "status": "modules_missing",
                "passed_count": 0,
                "failed_count": 0,
                "checks": [],
            }
            self._save_json(report_path, report)
            return report
        try:
            checks_a = run_checks_a(self.output_dir)
            checks_b = run_checks_b(self.output_dir)
            checks = [*checks_a, *checks_b]
            passed_count = sum(1 for check in checks if check.get("passed"))
            report = {
                "schema_version": "vnext_persistent_checks_v1",
                "status": "ok",
                "passed_count": passed_count,
                "failed_count": len(checks) - passed_count,
                "checks": checks,
            }
        except Exception as exc:  # noqa: BLE001 —— 常设检查绝不拖垮主链
            report = {
                "schema_version": "vnext_persistent_checks_v1",
                "status": "failed",
                "passed_count": 0,
                "failed_count": 0,
                "checks": [],
                "error": str(exc),
            }
        self._save_json(report_path, report)
        return report

    def _load_stage_manifest(self) -> Dict[str, Any]:
        if self.stage_manifest_path.exists():
            try:
                payload = json.loads(self.stage_manifest_path.read_text(encoding="utf-8"))
                if isinstance(payload, dict):
                    payload.setdefault("artifacts", {})
                    return payload
            except Exception:
                pass
        return {
            "schema_version": "vnext_stage_manifest_v1",
            "run_id": self.output_dir.name,
            "output_dir": str(self.output_dir),
            "resume_scope": "same output_dir and same input packet/effective_date only",
            "created_at": _utc_now().isoformat(),
            "updated_at": _utc_now().isoformat(),
            "artifacts": {},
        }

    def _artifact_relpath(self, path: Path) -> str:
        try:
            return path.resolve().relative_to(self.output_dir).as_posix()
        except ValueError:
            return path.resolve().as_posix()

    def _sha256_file(self, path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def _strip_volatile_hash_fields(self, value: Any) -> Any:
        if isinstance(value, dict):
            return {
                key: self._strip_volatile_hash_fields(item)
                for key, item in value.items()
                if key not in {"generated_at"}
            }
        if isinstance(value, list):
            return [self._strip_volatile_hash_fields(item) for item in value]
        return value

    def _stable_json_file_sha256(self, path: Path) -> str:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return self._sha256_file(path)
        normalized = json.dumps(
            self._strip_volatile_hash_fields(payload),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        )
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()

    def _stable_stage_payload_sha256(self, stage_key: str, payload: Dict[str, Any]) -> str:
        normalized = json.dumps(
            self._strip_volatile_hash_fields(self._sanitize_prompt_payload(stage_key, payload)),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        )
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()

    def _current_input_sha256(self) -> Optional[str]:
        analysis_packet_path = self.output_dir / "analysis_packet.json"
        if not analysis_packet_path.exists():
            return None
        return self._stable_json_file_sha256(analysis_packet_path)

    def _manifest_stage_for_path(self, relpath: str) -> str:
        if relpath == "analysis_packet.json":
            return "input"
        if relpath == "context_brief.json" or relpath.startswith("layer_context_briefs/"):
            return "context"
        layer_match = re.fullmatch(r"layer_cards/(L[1-5])\.json", relpath)
        if layer_match:
            return layer_match.group(1).lower()
        if relpath.startswith("bridge_memos/"):
            return "bridge"
        if relpath.startswith("investigation_reports/"):
            return "investigation"
        return {
            "synthesis_packet.json": "synthesis",
            "feedback_contract_manifest.json": "feedback_contract",
            "inquiry_router_output.json": "inquiry_router",
            "thesis_draft.json": "thesis",
            "critique.json": "critic",
            "risk_boundary_report.json": "risk",
            "schema_guard_report.json": "schema_guard",
            "analysis_revised.json": "reviser",
            "final_adjudication.json": "final_adjudicator",
            "run_review_report.json": "run_review",
            "outcome_review_report.json": "outcome_review",
            "post_run_reflection_library.json": "post_run_reflection",
            "llm_stage_diagnostics.json": "diagnostics",
        }.get(relpath, "artifact")

    def _write_stage_manifest(self) -> None:
        self.stage_manifest["updated_at"] = _utc_now().isoformat()
        self.stage_manifest_path.write_text(
            json.dumps(self.stage_manifest, ensure_ascii=False, indent=2, default=str) + "\n",
            encoding="utf-8",
        )

    def _record_stage_artifact(
        self,
        path: Path,
        *,
        stage_key: Optional[str] = None,
        stage_name: Optional[str] = None,
        payload: Optional[Dict[str, Any]] = None,
        checkpoint_reusable: Optional[bool] = None,
    ) -> None:
        """登记产物指纹。`checkpoint_reusable=False` 用于显式拒绝复用降级产物。"""
        if path.resolve() == self.stage_manifest_path.resolve() or not path.exists():
            return
        relpath = self._artifact_relpath(path)
        previous = self.stage_manifest.get("artifacts", {}).get(relpath, {})
        input_sha256 = self._current_input_sha256()
        item = {
            "stage": self._manifest_stage_for_path(relpath),
            "path": relpath,
            "sha256": self._sha256_file(path),
            "input_sha256": input_sha256,
            "bytes": path.stat().st_size,
            "status": "complete",
            "checkpoint_reusable": relpath.endswith(".json")
            and not relpath.startswith("prompt_audit/")
            and relpath != "run_review_report.json"
            and relpath != "outcome_review_report.json"
            and relpath != "post_run_reflection_library.json",
            "updated_at": _utc_now().isoformat(),
            "effective_date": self._infer_effective_date_from_prompt_audit(""),
        }
        if stage_key:
            item["stage_key"] = stage_key
        if stage_name:
            item["stage_name"] = stage_name
        if checkpoint_reusable is not None:
            item["checkpoint_reusable"] = bool(checkpoint_reusable)
        if stage_key and payload is not None:
            item["payload_sha256"] = self._stable_stage_payload_sha256(stage_key, payload)
        # 续跑静默覆盖已验证产物是本项目踩过的真实坑（run 20260728_110702：首跑那批
        # 竞争假说样本被续跑覆盖后无迹可寻）。这里不改变覆盖行为——重跑就该写新结果——
        # 但必须留痕，让"我读到的那份还在不在"可被事后追查。
        if self.resume_from_existing and previous.get("sha256"):
            if previous["sha256"] != item["sha256"]:
                item["overwritten_in_resume"] = {
                    "previous_sha256": previous["sha256"],
                    "previous_updated_at": previous.get("updated_at", ""),
                }
            elif previous.get("overwritten_in_resume"):
                # 同一份产物常被登记两次：`_save_json` 先无 stage_key 记一次，调用方再带
                # stage_key/payload 补记一次。第二次的 sha 与第一次相同，若不继承就会把
                # 第一次留下的覆盖痕迹擦掉——留痕机制自己被覆盖，是最讽刺的失败方式。
                item["overwritten_in_resume"] = previous["overwritten_in_resume"]
        self.stage_manifest.setdefault("artifacts", {})[relpath] = item
        self._write_stage_manifest()

    def _load_stage_checkpoint(
        self,
        filename: str | Path,
        model_cls: type,
        *,
        stage_key: str,
        stage_name: str,
        expected_payload: Optional[Dict[str, Any]] = None,
    ) -> Any:
        if not self.resume_from_existing:
            return None
        path = Path(filename)
        if not path.is_absolute():
            path = self.output_dir / path
        if not path.exists():
            return None
        relpath = self._artifact_relpath(path)
        manifest_item = self.stage_manifest.get("artifacts", {}).get(relpath, {})
        if not manifest_item or manifest_item.get("checkpoint_reusable") is False:
            return None
        if manifest_item.get("sha256") and manifest_item.get("sha256") != self._sha256_file(path):
            return None
        if manifest_item.get("stage_key") and manifest_item.get("stage_key") != stage_key:
            return None
        if manifest_item.get("stage_name") and manifest_item.get("stage_name") != stage_name:
            return None
        if expected_payload is not None:
            expected_payload_sha = self._stable_stage_payload_sha256(stage_key, expected_payload)
            if manifest_item.get("payload_sha256") != expected_payload_sha:
                return None
        current_input_sha256 = self._current_input_sha256()
        if manifest_item.get("input_sha256") and current_input_sha256:
            if manifest_item.get("input_sha256") != current_input_sha256:
                return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            # 同一条归一化，无条件应用（见 _run_stage 里的调用点注释）：checkpoint
            # 文件正常情况下来自已校验过的模型 dump，不该再有裸 null，但覆盖这条
            # 解析入口是本次改动明确要求的——不给旧跑或手改文件留漏网之鱼。
            payload = normalize_none_list_fields_for_strict_schema_validation(model_cls, payload)
            validated = model_cls.model_validate(payload)
        except Exception:
            return None
        self.stage_diagnostics["stages"][stage_name] = {
            "stage_key": stage_key,
            "stage_name": stage_name,
            "attempts": 0,
            "errors": [],
            "status": "resumed",
            "checkpoint": {
                "artifact": relpath,
                "sha256": manifest_item.get("sha256"),
                "resume_scope": self.stage_manifest.get("resume_scope"),
            },
            "prompt_audit": {
                "stage_dir": self._prompt_audit_relpath(stage_name),
                "attempts": [],
            },
        }
        self._save_stage_diagnostics()
        return validated

    @staticmethod
    def _match_input_function_id(fid: str, input_ids: Dict[str, str]) -> Optional[str]:
        """T54 批 5（抄回配对）：仅当模型自报的 function_id 有唯一高相似输入近邻时
        返回回正目标；两个候选相似度拉不开或都不够像时返回 None——交给校验器拒收
        重试。绝不按列表位置硬配（那会把模型的张冠李戴变成系统的张冠李戴）。"""
        import difflib

        scored = sorted(
            (
                (difflib.SequenceMatcher(None, fid, candidate).ratio(), candidate)
                for candidate in input_ids
            ),
            reverse=True,
        )
        if not scored or scored[0][0] < 0.9:
            return None
        if len(scored) > 1 and scored[0][0] - scored[1][0] < 0.05:
            return None
        return scored[0][1]

    def _assemble_stage_mechanical_fields(
        self, stage_key: str, parsed: Dict[str, Any], input_payload: Dict[str, Any]
    ) -> Dict[str, Any]:
        """T54 批 2/批 5（机械字段不出答卷）：代码能确定性定的字段在归一化后、契约校验前装配。

        l*_analyst 三族：
        - ``layer`` 由 stage_key 派生（l1_analyst -> L1），模型填错一律覆盖；
        - ``indicator_analyses[].function_id``/``metric`` 抄回配对（批 5）：function_id
          模型自报、代码对输入键集校验——拼写错误有唯一高相似近邻时回正（evidence_refs
          自引用同步改写），配不上则原样留给 `_validate_layer_card_v2` 拒收重试；
          metric 在 function_id 落定后强制为输入 metric_name；
        - ``quality_self_check.covered_function_ids`` / ``coverage_complete`` 由
          indicator_analyses ∩ 输入 analysis_required 指标集派生。

        自检的判断类字段（weak_reasoning_points 等）不碰；quality_self_check 整个缺失时
        不代造——那是校验器 `_validate_layer_card_v2` 该拦的形状病，闸门不因此放松。
        """
        if not isinstance(parsed, dict):
            return parsed
        if not (stage_key.startswith("l") and stage_key.endswith("_analyst")):
            return parsed
        parsed["layer"] = stage_key[:2].upper()
        raw_data = input_payload.get("layer_raw_data") if isinstance(input_payload, dict) else None
        if not isinstance(raw_data, dict):
            return parsed
        input_metric_names: Dict[str, str] = {}
        for function_id, indicator in raw_data.items():
            if isinstance(indicator, dict):
                canonical = str(indicator.get("function_id") or function_id)
                input_metric_names[canonical] = str(
                    indicator.get("metric_name") or indicator.get("name") or canonical
                )
        analyses = parsed.get("indicator_analyses")
        if isinstance(analyses, list):
            layer_label = parsed["layer"]
            for item in analyses:
                if not isinstance(item, dict):
                    continue
                fid = str(item.get("function_id") or "")
                if fid and fid != "unknown" and fid not in input_metric_names:
                    corrected = self._match_input_function_id(fid, input_metric_names)
                    if corrected:
                        self_ref = f"{layer_label}.{fid}"
                        refs = item.get("evidence_refs")
                        if isinstance(refs, list):
                            item["evidence_refs"] = [
                                f"{layer_label}.{corrected}" if str(ref) == self_ref else ref
                                for ref in refs
                            ]
                        logger.warning(
                            "indicator function_id 拼写回正：%r -> %r（唯一高相似近邻，%s）",
                            fid,
                            corrected,
                            stage_key,
                        )
                        item["function_id"] = corrected
                settled = str(item.get("function_id") or "")
                if settled in input_metric_names:
                    # metric 是输入里就有的机械事实（metric_name），代码强制装配；
                    # 校验器里的 metric 一致性检查保留作兜底。
                    item["metric"] = input_metric_names[settled]
        expected = {
            str(indicator.get("function_id") or function_id)
            for function_id, indicator in raw_data.items()
            if isinstance(indicator, dict) and not self._indicator_unavailable_for_analysis(indicator)
        }
        covered = sorted(
            expected & {
                str(item.get("function_id"))
                for item in parsed.get("indicator_analyses") or []
                if isinstance(item, dict) and item.get("function_id")
            }
        )
        self_check = parsed.get("quality_self_check")
        if isinstance(self_check, dict):
            self_check["covered_function_ids"] = covered
            self_check["coverage_complete"] = expected <= set(covered)
        return parsed

    def _inject_revision_claimed_fields(self, parsed: Dict[str, Any], thesis: ThesisDraft) -> Dict[str, Any]:
        """T54 批 2：revision_claimed_fields 由代码 diff 装配（thesis 原稿 vs 修订稿
        顶层字段，canonical JSON 比对），模型自报一律覆盖——"修订说明声称改了什么"
        是机器事实，不是模型表达。generated_at 是时间戳，不参与 diff。
        PC-03 按同一口径重算比对（thesis_draft.json vs analysis_revised.json）。"""
        if not isinstance(parsed, dict):
            return parsed
        revised = parsed.get("revised_thesis")
        if not isinstance(revised, dict):
            return parsed
        original = _model_dump(thesis)
        if not isinstance(original, dict):
            return parsed
        changed = []
        for key in set(original) | set(revised):
            if key == "generated_at":
                continue
            if key not in original or key not in revised:
                changed.append(key)
                continue
            left = json.dumps(original[key], ensure_ascii=False, sort_keys=True, default=str)
            right = json.dumps(revised[key], ensure_ascii=False, sort_keys=True, default=str)
            if left != right:
                changed.append(key)
        parsed["revision_claimed_fields"] = sorted(changed)
        return parsed

    def _normalize_payload(self, stage_key: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        normalized = json.loads(json.dumps(payload, ensure_ascii=False, default=str))
        if stage_key.startswith("l") and stage_key.endswith("_analyst"):
            layer_label = str(normalized.get("layer") or stage_key[:2].upper()).upper()
            normalized["confidence"] = self._normalize_confidence(normalized.get("confidence"))
            for text_key in ("local_conclusion", "layer_synthesis", "internal_conflict_analysis", "notes"):
                if normalized.get(text_key) is not None and not isinstance(normalized.get(text_key), str):
                    normalized[text_key] = json.dumps(normalized[text_key], ensure_ascii=False, default=str)
            if "local_conclusion" in normalized:
                normalized["local_conclusion"] = self._truncate_text(normalized.get("local_conclusion"), 500)
            raw_core_facts = normalized.get("core_facts", []) or []
            if isinstance(raw_core_facts, (str, bytes, dict)) or not isinstance(raw_core_facts, list):
                raw_core_facts = [raw_core_facts]

            normalized_core_facts = []
            for fact in raw_core_facts:
                if not isinstance(fact, dict):
                    text = str(fact)
                    normalized_core_facts.append({"metric": text[:80] or "core_fact", "value": text})
                    continue
                fact["trend"] = self._normalize_trend(fact.get("trend"))
                fact["magnitude"] = self._normalize_magnitude(fact.get("magnitude"))
                if "historical_percentile" in fact:
                    percentile, percentile_note = self._normalize_historical_percentile(fact.get("historical_percentile"))
                    fact["historical_percentile"] = percentile
                    if percentile_note:
                        raw_data = fact.get("raw_data") if isinstance(fact.get("raw_data"), dict) else {}
                        raw_data["historical_percentile_note"] = percentile_note
                        fact["raw_data"] = raw_data
                if isinstance(fact.get("value"), dict):
                    fact["value"] = json.dumps(fact["value"], ensure_ascii=False)
                normalized_core_facts.append(fact)
            normalized["core_facts"] = normalized_core_facts
            if isinstance(normalized.get("indicator_analyses"), list):
                normalized["indicator_analyses"] = [
                    self._normalize_indicator_analysis(item, layer_label=layer_label)
                    for item in normalized["indicator_analyses"]
                    if isinstance(item, dict)
                ]
            if isinstance(normalized.get("quality_self_check"), dict):
                normalized["quality_self_check"].setdefault("covered_function_ids", [])
                normalized["quality_self_check"].setdefault("missing_or_weak_indicators", [])
                normalized["quality_self_check"].setdefault("weak_reasoning_points", [])
                normalized["quality_self_check"].setdefault("unresolved_internal_tensions", [])
                normalized["quality_self_check"].setdefault("confidence_limitations", [])
            if isinstance(normalized.get("cross_layer_hooks"), list):
                normalized["cross_layer_hooks"] = [
                    self._normalize_cross_layer_hook(item)
                    for item in normalized["cross_layer_hooks"]
                ]
        if stage_key in {"bridge", "thesis", "reviser"}:
            for key in ("conflicts", "retained_conflicts", "remaining_conflicts"):
                if isinstance(normalized.get(key), list):
                    normalized[key] = [
                        conflict
                        for conflict in (self._normalize_conflict(item) for item in normalized[key])
                        if conflict
                    ]
            if stage_key == "bridge":
                normalization_notes = self._coerce_string_list(normalized.get("normalization_notes"))
                if "implication_for_ndx" in normalized:
                    normalized["implication_for_ndx"] = self._truncate_text(normalized.get("implication_for_ndx"), 500)
                if isinstance(normalized.get("typed_conflicts"), list):
                    normalized["typed_conflicts"] = [
                        self._normalize_typed_conflict(item)
                        for item in normalized["typed_conflicts"]
                        if isinstance(item, dict)
                    ]
                else:
                    normalized["typed_conflicts"] = self._derive_typed_conflicts(normalized.get("conflicts", []))
                    if normalized["typed_conflicts"]:
                        normalization_notes.append("typed_conflicts_derived_from_legacy_conflicts")
                # T54 批 4（编号规范 02）：typed_conflicts 是权威容器。id 由代码按序
                # 重发（TC_01…），legacy conflicts 由 typed 反向重建——双容器同源，
                # PC-23 恒一致。模型原 id 记入 normalization_notes，不静默丢弃；
                # 同一 payload 内对旧 id 的精确匹配引用按 old→new 重接，对不上的
                # 原样保留交给既有闸门。本规范取代 08-17 的逐对对齐止血逻辑。
                typed_conflicts = normalized.get("typed_conflicts")
                if isinstance(typed_conflicts, list) and typed_conflicts:
                    id_map: Dict[str, str] = {}
                    for index, typed in enumerate(typed_conflicts):
                        if not isinstance(typed, dict):
                            continue
                        new_id = f"TC_{index + 1:02d}"
                        old_id = str(typed.get("conflict_id") or "")
                        if old_id and old_id != new_id:
                            id_map[old_id] = new_id
                        typed["conflict_id"] = new_id
                        derived_layers = sorted(
                            {
                                str(ref).split(".", 1)[0]
                                for ref in typed.get("evidence_refs") or []
                                if re.fullmatch(r"L[1-5]\..+", str(ref))
                            }
                        )
                        if derived_layers:
                            typed["involved_layers"] = derived_layers
                    typed_conflicts = [c for c in typed_conflicts if isinstance(c, dict)]
                    normalized["typed_conflicts"] = typed_conflicts
                    normalized["conflicts"] = [
                        {
                            "conflict_id": typed["conflict_id"],
                            "conflict_type": typed.get("conflict_type", ""),
                            "severity": typed.get("severity", "medium"),
                            "description": typed.get("description", ""),
                            "implication": typed.get("implication", ""),
                            "involved_layers": list(typed.get("involved_layers") or []),
                        }
                        for typed in typed_conflicts
                    ]
                    normalization_notes.append("legacy_conflicts_rebuilt_from_typed_conflicts")
                    if id_map:
                        normalization_notes.append(
                            "conflict_ids_reassigned_by_code:"
                            + ",".join(f"{new}<={old}" for old, new in sorted(id_map.items()))
                        )

                        def _rewire(value: Any) -> Any:
                            return id_map.get(value, value) if isinstance(value, str) else value

                        principal = normalized.get("principal_contradiction")
                        if isinstance(principal, dict):
                            if principal.get("contradiction_id"):
                                principal["contradiction_id"] = _rewire(principal["contradiction_id"])
                            if isinstance(principal.get("conflict_refs"), list):
                                principal["conflict_refs"] = [_rewire(ref) for ref in principal["conflict_refs"]]
                        for secondary in normalized.get("secondary_contradictions") or []:
                            if isinstance(secondary, dict) and secondary.get("contradiction_id"):
                                secondary["contradiction_id"] = _rewire(secondary["contradiction_id"])
                        for assessment in normalized.get("price_reflection_map") or []:
                            if isinstance(assessment, dict) and assessment.get("target"):
                                assessment["target"] = _rewire(assessment["target"])
                bridge_fallback_refs = self._bridge_fallback_evidence_refs(normalized)
                if isinstance(normalized.get("cross_layer_claims"), list):
                    claims = []
                    claim_refs_normalized = False
                    for item in normalized["cross_layer_claims"]:
                        if not isinstance(item, dict):
                            continue
                        claim = self._normalize_cross_layer_claim(item, bridge_fallback_refs)
                        claims.append(claim)
                        if claim.get("_supporting_facts_normalized"):
                            claim_refs_normalized = True
                            claim.pop("_supporting_facts_normalized", None)
                    normalized["cross_layer_claims"] = claims
                    if claim_refs_normalized:
                        normalization_notes.append("cross_layer_claim_supporting_facts_normalized_to_evidence_refs")
                if isinstance(normalized.get("resonance_chains"), list):
                    resonance_chains = [
                        self._normalize_resonance_chain(item)
                        for item in normalized["resonance_chains"]
                        if isinstance(item, dict)
                    ]
                    # T54 批 4：chain_id 由代码按序重发（RC_01…）。
                    for index, chain in enumerate(resonance_chains):
                        chain["chain_id"] = f"RC_{index + 1:02d}"
                    normalized["resonance_chains"] = resonance_chains
                if isinstance(normalized.get("transmission_paths"), list):
                    transmission_paths = [
                        self._normalize_transmission_path(item)
                        for item in normalized["transmission_paths"]
                        if isinstance(item, dict)
                    ]
                    normalized["transmission_paths"] = self._dedupe_bridge_transmission_paths(transmission_paths)
                    # T54 批 4：path_id 由代码按序重发（TP_01…），重复 id 由构造消除。
                    for index, path in enumerate(normalized["transmission_paths"]):
                        path["path_id"] = f"TP_{index + 1:02d}"
                if isinstance(normalized.get("principal_contradiction"), dict):
                    normalized["principal_contradiction"] = self._normalize_principal_contradiction(
                        normalized["principal_contradiction"],
                        typed_conflicts=normalized.get("typed_conflicts", []),
                    )
                else:
                    normalized["principal_contradiction"] = self._derive_principal_contradiction(
                        normalized.get("typed_conflicts", []),
                        normalized.get("conflicts", []),
                    )
                    if normalized.get("principal_contradiction"):
                        normalization_notes.append("principal_contradiction_derived_by_code")
                if isinstance(normalized.get("secondary_contradictions"), list):
                    normalized["secondary_contradictions"] = [
                        self._normalize_secondary_contradiction(item)
                        for item in normalized["secondary_contradictions"]
                        if isinstance(item, dict)
                    ]
                else:
                    normalized["secondary_contradictions"] = self._derive_secondary_contradictions(
                        normalized.get("typed_conflicts", []),
                        normalized.get("principal_contradiction"),
                    )
                    if normalized["secondary_contradictions"]:
                        normalization_notes.append("secondary_contradictions_derived_by_code")
                if isinstance(normalized.get("price_reflection_map"), list):
                    normalized["price_reflection_map"] = [
                        self._normalize_price_reflection_assessment(item)
                        for item in normalized["price_reflection_map"]
                        if isinstance(item, dict)
                    ]
                else:
                    normalized["price_reflection_map"] = self._derive_price_reflection_map(
                        normalized.get("principal_contradiction"),
                    )
                    if normalized["price_reflection_map"]:
                        normalization_notes.append("price_reflection_map_derived_by_code")
                categories_before_completion = {
                    item.get("category")
                    for item in normalized.get("price_reflection_map", [])
                    if isinstance(item, dict)
                }
                normalized["price_reflection_map"] = self._ensure_price_reflection_categories(
                    normalized.get("price_reflection_map", []),
                    fallback_evidence_refs=(normalized.get("principal_contradiction") or {}).get("evidence_refs", []),
                    stage_key=stage_key,
                )
                categories_after_completion = {
                    item.get("category")
                    for item in normalized.get("price_reflection_map", [])
                    if isinstance(item, dict)
                }
                added_categories = sorted(categories_after_completion - categories_before_completion)
                if added_categories:
                    normalization_notes.append(
                        "price_reflection_categories_added_by_code:" + ",".join(added_categories)
                    )
                if isinstance(normalized.get("contradiction_transformation_signals"), list):
                    normalized["contradiction_transformation_signals"] = [
                        self._normalize_contradiction_transformation_signal(item)
                        for item in normalized["contradiction_transformation_signals"]
                        if isinstance(item, dict)
                    ]
                else:
                    principal = normalized.get("principal_contradiction") or {}
                    normalized["contradiction_transformation_signals"] = list(principal.get("transformation_signals", []) or [])
                if not isinstance(normalized.get("unresolved_questions"), list):
                    normalized["unresolved_questions"] = []
                normalized["event_refs"] = self._coerce_event_refs_list(normalized.get("event_refs"))
                normalized["normalization_notes"] = list(dict.fromkeys(normalization_notes))
            if stage_key in {"thesis", "reviser"}:
                thesis_payload = normalized.get("revised_thesis") if stage_key == "reviser" else normalized
                if isinstance(thesis_payload, dict):
                    if isinstance(thesis_payload.get("principal_contradiction"), dict):
                        thesis_payload["principal_contradiction"] = self._normalize_principal_contradiction(
                            thesis_payload["principal_contradiction"],
                            typed_conflicts=[],
                        )
                    if isinstance(thesis_payload.get("secondary_contradictions"), list):
                        thesis_payload["secondary_contradictions"] = [
                            self._normalize_secondary_contradiction(item)
                            for item in thesis_payload["secondary_contradictions"]
                            if isinstance(item, dict)
                        ]
                    if isinstance(thesis_payload.get("price_reflection_map"), list):
                        thesis_payload["price_reflection_map"] = [
                            self._normalize_price_reflection_assessment(item)
                            for item in thesis_payload["price_reflection_map"]
                            if isinstance(item, dict)
                        ]
                    else:
                        thesis_payload["price_reflection_map"] = []
                    thesis_payload["price_reflection_map"] = self._ensure_price_reflection_categories(
                        thesis_payload["price_reflection_map"],
                        fallback_evidence_refs=(thesis_payload.get("principal_contradiction") or {}).get("evidence_refs", []),
                        stage_key=stage_key,
                    )
                    for key in ("time_horizon_views", "portfolio_actions"):
                        if not isinstance(thesis_payload.get(key), list):
                            thesis_payload[key] = []
                    thesis_payload["time_horizon_views"] = [
                        self._normalize_time_horizon_view(item, index=index)
                        for index, item in enumerate(thesis_payload.get("time_horizon_views", []))
                    ]
                    thesis_payload["portfolio_actions"] = [
                        self._normalize_portfolio_action(item, index=index)
                        for index, item in enumerate(thesis_payload.get("portfolio_actions", []))
                    ]
                    if isinstance(thesis_payload.get("reader_conclusion"), dict):
                        thesis_payload["reader_conclusion"] = self._normalize_reader_final(thesis_payload["reader_conclusion"])
            if stage_key == "reviser":
                revised_thesis = normalized.get("revised_thesis")
                if isinstance(revised_thesis, dict) and isinstance(revised_thesis.get("retained_conflicts"), list):
                    revised_thesis["retained_conflicts"] = [
                        conflict
                        for conflict in (
                            self._normalize_conflict(item)
                            for item in revised_thesis["retained_conflicts"]
                        )
                        if conflict
                    ]
        if stage_key == "final":
            # T54 批 6（机械字段不出答卷）：claim_ledger 整本由代码在终审后重建
            # （_build_final_claim_ledger），模型答卷里的任何 claim_ledger 一律在
            # 归一化阶段摘除——不进契约校验，20260728 那类"模型猜错形状烧重试"的
            # 事故面从结构上消除；契约侧的裸列表宽容校验同步下线。
            if "claim_ledger" in normalized:
                normalized.pop("claim_ledger", None)
                logger.warning("final 答卷中的 claim_ledger 已摘除（台账由代码整本装配）")
            if not isinstance(normalized.get("token_usage"), dict):
                normalized["token_usage"] = None
            if isinstance(normalized.get("principal_contradiction"), dict):
                normalized["principal_contradiction"] = self._normalize_principal_contradiction(
                    normalized["principal_contradiction"],
                    typed_conflicts=[],
                )
            if isinstance(normalized.get("secondary_contradictions"), list):
                normalized["secondary_contradictions"] = [
                    self._normalize_secondary_contradiction(item)
                    for item in normalized["secondary_contradictions"]
                    if isinstance(item, dict)
                ]
            if isinstance(normalized.get("price_reflection_map"), list):
                normalized["price_reflection_map"] = [
                    self._normalize_price_reflection_assessment(item)
                    for item in normalized["price_reflection_map"]
                    if isinstance(item, dict)
                ]
            else:
                normalized["price_reflection_map"] = []
            normalized["price_reflection_map"] = self._ensure_price_reflection_categories(
                normalized["price_reflection_map"],
                fallback_evidence_refs=(normalized.get("principal_contradiction") or {}).get("evidence_refs", []),
                stage_key=stage_key,
            )
            for key in ("time_horizon_views", "portfolio_actions"):
                if not isinstance(normalized.get(key), list):
                    normalized[key] = []
            normalized["time_horizon_views"] = [
                self._normalize_time_horizon_view(item, index=index)
                for index, item in enumerate(normalized.get("time_horizon_views", []))
            ]
            normalized["portfolio_actions"] = [
                self._normalize_portfolio_action(item, index=index)
                for index, item in enumerate(normalized.get("portfolio_actions", []))
            ]
            if isinstance(normalized.get("reader_final"), dict):
                normalized["reader_final"] = self._normalize_reader_final(normalized["reader_final"])
        return normalized

    def _normalize_indicator_analysis(self, item: Dict[str, Any], *, layer_label: Optional[str] = None) -> Dict[str, Any]:
        normalized = dict(item)
        normalized["function_id"] = str(
            normalized.get("function_id")
            or normalized.get("metric_id")
            or normalized.get("metric")
            or "unknown"
        )
        normalized["metric"] = str(
            normalized.get("metric")
            or normalized.get("metric_name")
            or normalized["function_id"]
        )
        normalized["narrative"] = str(
            normalized.get("narrative")
            or normalized.get("output_narrative")
            or normalized.get("interpretation")
            or normalized.get("current_reading")
            or ""
        )
        normalized["reasoning_process"] = str(
            normalized.get("reasoning_process")
            or normalized.get("reasoning")
            or normalized.get("rationale")
            or normalized["narrative"]
        )
        if normalized.get("current_reading") is not None and not isinstance(normalized.get("current_reading"), str):
            normalized["current_reading"] = json.dumps(normalized["current_reading"], ensure_ascii=False, default=str)
        for key in (
            "first_principles_chain",
            "evidence_refs",
            "cross_layer_implications",
            "risk_flags",
            "misread_guards",
            "cross_validation_targets",
            "falsifiers",
        ):
            value = normalized.get(key)
            normalized[key] = self._coerce_string_list(value)
        if not normalized["evidence_refs"] and layer_label and normalized["function_id"] != "unknown":
            normalized["evidence_refs"] = [f"{layer_label}.{normalized['function_id']}"]
        normalized["confidence"] = self._normalize_confidence(normalized.get("confidence"))
        self._backfill_indicator_canon_fields(normalized)
        return normalized

    def _backfill_indicator_canon_fields(self, normalized: Dict[str, Any]) -> None:
        """T54 批 3（机械字段不出答卷）：canon 六字段无条件按法典装配——08-16 的
        "缺省回填 + 非枚举回正"只是过渡安全带，法典对每个指标的这些字段是唯一权威。

        模型填了不同值不静默丢弃（"形式不得拒收内容"）：原文逐项改写进 canon_dispute
        异议通道，进审计区、可逐字审计；装配值不变。装配值错了改 canon，不改提示词。
        法典不认识的指标（KeyError）原样放行，由 schema 校验拦。"""
        try:
            canon = get_indicator_canon(str(normalized.get("function_id") or ""))
        except KeyError:
            return

        disputes: List[str] = []

        def _assemble_scalar(field_name: str, canon_value: Any) -> None:
            canon_text = str(_enum_value(canon_value) or "").strip()
            model_text = str(_enum_value(normalized.get(field_name)) or "").strip()
            if model_text and model_text != canon_text:
                disputes.append(
                    f"{field_name}: 模型填 {model_text[:80]!r}，法典装配 {canon_text[:80]!r}"
                )
            normalized[field_name] = canon_text

        def _assemble_list(field_name: str, canon_items: List[str]) -> None:
            canon_list = [str(item) for item in canon_items]
            model_items = [
                str(item) for item in _as_list(normalized.get(field_name)) if str(item).strip()
            ]
            extras = [item for item in model_items if item not in canon_list]
            if extras:
                disputes.append(
                    f"{field_name}: 模型补充未进装配值：{'；'.join(item[:80] for item in extras[:3])}"
                )
            normalized[field_name] = canon_list

        _assemble_scalar("permission_type", canon.permission_type)
        _assemble_scalar("canonical_question", canon.canonical_question)
        _assemble_scalar("core_vs_tactical_boundary", canon.core_vs_tactical_boundary)
        for field_name in ("misread_guards", "cross_validation_targets", "falsifiers"):
            _assemble_list(field_name, list(getattr(canon, field_name)))
        if disputes:
            normalized["canon_dispute"] = disputes
            logger.warning(
                "canon 六字段按法典装配，模型分歧已进 canon_dispute（function_id=%s）：%s",
                normalized.get("function_id"),
                "；".join(disputes)[:300],
            )

    def _normalize_cross_layer_hook(self, item: Any) -> Dict[str, Any]:
        if not isinstance(item, dict):
            text = str(item)
            target = self._infer_layer_from_text(text, default="L4")
            return {
                "target_layer": target,
                "question": text,
                "priority": "medium",
            }

        normalized = dict(item)
        target = normalized.get("target_layer") or normalized.get("layer") or normalized.get("target")
        if not target:
            target = self._infer_layer_from_text(json.dumps(normalized, ensure_ascii=False, default=str), default="L4")
        normalized["target_layer"] = self._normalize_layer_label(target)

        question = (
            normalized.get("question")
            or normalized.get("issue")
            or normalized.get("description")
            or normalized.get("rationale")
            or normalized.get("mechanism")
            or normalized.get("prompt")
        )
        if not question:
            question = json.dumps(normalized, ensure_ascii=False, default=str)
        normalized["question"] = str(question)

        priority = str(normalized.get("priority") or "medium").strip().lower()
        normalized["priority"] = priority if priority in {"high", "medium", "low"} else "medium"
        return normalized

    def _normalize_layer_label(self, value: Any) -> str:
        text = str(_enum_value(value) or "").strip().upper()
        match = re.search(r"L([1-5])", text)
        if match:
            return f"L{match.group(1)}"
        if text in {"1", "2", "3", "4", "5"}:
            return f"L{text}"
        return "L4"

    def _infer_layer_from_text(self, text: str, *, default: str) -> str:
        match = re.search(r"L\s*([1-5])", text, re.IGNORECASE)
        if match:
            return f"L{match.group(1)}"
        return default

    def _normalize_conflict(self, conflict: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(conflict, dict):
            return {}
        normalized = dict(conflict)
        if not any(str(value or "").strip() for value in normalized.values()):
            return {}
        normalized["conflict_type"] = str(
            normalized.get("conflict_type")
            or normalized.get("conflict_id")
            or normalized.get("type")
            or "normalized_conflict"
        )
        severity = str(normalized.get("severity") or "medium").lower()
        normalized["severity"] = severity if severity in {"high", "medium", "low"} else "medium"
        normalized["description"] = str(
            normalized.get("description")
            or normalized.get("summary")
            or normalized.get("claim")
            or normalized.get("conflict_type")
            or "模型输出的冲突项缺少描述，已降级为结构占位。"
        )
        normalized["implication"] = str(
            normalized.get("implication")
            or normalized.get("action_implication")
            or normalized.get("description")
            or "需继续跟踪其对最终立场的影响。"
        )
        if not normalized.get("involved_layers"):
            layers = re.findall(r"L[1-5]", normalized.get("conflict_type", "") + " " + normalized.get("description", ""))
            normalized["involved_layers"] = sorted(set(layers)) or ["L1", "L4"]
        return normalized

    def _derive_typed_conflicts(self, conflicts: Any) -> List[Dict[str, Any]]:
        if not isinstance(conflicts, list):
            return []
        return [
            self._normalize_typed_conflict(
                {
                    "conflict_id": conflict.get("conflict_type") or f"conflict_{index}",
                    "conflict_type": conflict.get("conflict_type") or "legacy_conflict",
                    "severity": conflict.get("severity", "medium"),
                    "confidence": conflict.get("confidence", "medium"),
                    "description": conflict.get("description", ""),
                    "mechanism": conflict.get("mechanism", ""),
                    "implication": conflict.get("implication", ""),
                    "involved_layers": conflict.get("involved_layers", []),
                    "evidence_refs": conflict.get("evidence_refs", []),
                    "falsifiers": conflict.get("falsifiers", []),
                }
            )
            for index, conflict in enumerate(conflicts)
            if isinstance(conflict, dict)
        ]

    def _normalize_typed_conflict(self, item: Dict[str, Any]) -> Dict[str, Any]:
        normalized = dict(item)
        normalized["conflict_id"] = str(
            normalized.get("conflict_id")
            or normalized.get("id")
            or normalized.get("conflict_type")
            or "typed_conflict"
        )
        normalized["conflict_type"] = str(normalized.get("conflict_type") or normalized["conflict_id"])
        normalized["severity"] = str(normalized.get("severity") or "medium").lower()
        normalized["confidence"] = self._normalize_confidence(normalized.get("confidence"))
        normalized["description"] = str(normalized.get("description") or "")
        normalized["mechanism"] = str(normalized.get("mechanism") or "")
        normalized["implication"] = str(normalized.get("implication") or normalized["description"])
        for key in ("involved_layers", "evidence_refs", "falsifiers"):
            value = normalized.get(key)
            normalized[key] = self._coerce_string_list(value)
        normalized["event_refs"] = self._coerce_event_refs_list(normalized.get("event_refs"))
        status = str(normalized.get("status") or "unresolved").lower()
        normalized["status"] = status if status in {"unresolved", "confirmed", "weakened"} else "unresolved"
        return normalized

    def _bridge_fallback_evidence_refs(self, bridge: Dict[str, Any]) -> List[str]:
        refs: List[str] = []

        def add(raw_refs: Any) -> None:
            for ref in self._coerce_string_list(raw_refs):
                if _EVIDENCE_REF_PATTERN.fullmatch(ref) and ref not in refs:
                    refs.append(ref)

        for key in (
            "typed_conflicts",
            "resonance_chains",
            "transmission_paths",
            "secondary_contradictions",
            "price_reflection_map",
        ):
            for item in bridge.get(key) or []:
                if isinstance(item, dict):
                    add(item.get("evidence_refs"))
                    add(item.get("counterevidence_refs"))
        principal = bridge.get("principal_contradiction")
        if isinstance(principal, dict):
            add(principal.get("evidence_refs"))
            for signal in principal.get("transformation_signals") or []:
                if isinstance(signal, dict):
                    add(signal.get("evidence_refs"))
        return refs

    def _normalize_cross_layer_claim(self, item: Dict[str, Any], fallback_refs: List[str]) -> Dict[str, Any]:
        normalized = dict(item)
        raw_supporting_facts = self._coerce_string_list(normalized.get("supporting_facts"))
        valid_refs = [
            ref for ref in raw_supporting_facts
            if _EVIDENCE_REF_PATTERN.fullmatch(ref)
        ]
        invalid_notes = [ref for ref in raw_supporting_facts if ref not in valid_refs]
        if invalid_notes:
            existing_notes = self._coerce_string_list(normalized.get("supporting_fact_notes"))
            normalized["supporting_fact_notes"] = list(dict.fromkeys(existing_notes + invalid_notes))
        if not valid_refs and fallback_refs:
            text = " ".join(
                [
                    str(normalized.get("claim") or ""),
                    str(normalized.get("mechanism") or ""),
                    " ".join(invalid_notes),
                ]
            )
            layers = {
                f"L{match}"
                for match in re.findall(r"L\s*([1-5])", text, flags=re.IGNORECASE)
            }
            if layers:
                valid_refs = [ref for ref in fallback_refs if ref.split(".", 1)[0] in layers]
            if not valid_refs:
                valid_refs = list(fallback_refs)
        normalized["supporting_facts"] = list(dict.fromkeys(valid_refs))
        if invalid_notes or normalized["supporting_facts"] != raw_supporting_facts:
            normalized["_supporting_facts_normalized"] = True
        return normalized

    def _normalize_resonance_chain(self, item: Dict[str, Any]) -> Dict[str, Any]:
        normalized = dict(item)
        normalized["chain_id"] = str(normalized.get("chain_id") or normalized.get("id") or "resonance_chain")
        normalized["description"] = str(normalized.get("description") or normalized.get("claim") or "")
        normalized["mechanism"] = str(normalized.get("mechanism") or "")
        normalized["implication"] = str(normalized.get("implication") or "")
        normalized["confidence"] = self._normalize_confidence(normalized.get("confidence"))
        if not normalized.get("involved_layers") and normalized.get("layers"):
            normalized["involved_layers"] = normalized.get("layers")
        for key in ("involved_layers", "evidence_refs", "confirming_indicators", "falsifiers"):
            value = normalized.get(key)
            normalized[key] = self._coerce_string_list(value)
        normalized["event_refs"] = self._coerce_event_refs_list(normalized.get("event_refs"))
        return normalized

    def _normalize_transmission_path(self, item: Dict[str, Any]) -> Dict[str, Any]:
        normalized = dict(item)
        normalized["path_id"] = str(normalized.get("path_id") or normalized.get("id") or "transmission_path")
        normalized["source_layer"] = self._normalize_layer_label(normalized.get("source_layer") or normalized.get("source") or "L1")
        normalized["target_layer"] = self._normalize_layer_label(normalized.get("target_layer") or normalized.get("target") or "L4")
        normalized["mechanism"] = str(normalized.get("mechanism") or normalized.get("description") or "")
        normalized["implication"] = str(
            normalized.get("implication")
            or normalized.get("action_implication")
            or normalized.get("portfolio_implication")
            or normalized.get("description")
            or normalized.get("mechanism")
            or ""
        )
        normalized["confidence"] = self._normalize_confidence(normalized.get("confidence"))
        value = normalized.get("evidence_refs")
        normalized["evidence_refs"] = self._coerce_string_list(value)
        value = normalized.get("event_refs")
        normalized["event_refs"] = self._coerce_event_refs_list(value)
        return normalized

    def _dedupe_bridge_transmission_paths(self, paths: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        normalized_paths: List[Dict[str, Any]] = []
        seen: set[str] = set()
        for index, path in enumerate(paths):
            if not isinstance(path, dict):
                continue
            normalized = dict(path)
            raw_id = str(normalized.get("path_id") or "").strip()
            source = self._normalize_layer_label(normalized.get("source_layer") or "L1")
            target = self._normalize_layer_label(normalized.get("target_layer") or "L4")
            base_id = raw_id
            if not base_id or base_id == "transmission_path" or base_id in seen:
                base_id = f"{str(source).lower()}_to_{str(target).lower()}_{index + 1}"
            path_id = base_id
            suffix = 2
            while path_id in seen:
                path_id = f"{base_id}_{suffix}"
                suffix += 1
            seen.add(path_id)
            normalized["path_id"] = path_id
            normalized["source_layer"] = source
            normalized["target_layer"] = target
            if not str(normalized.get("implication") or "").strip():
                normalized["implication"] = str(normalized.get("mechanism") or normalized.get("description") or "")
            normalized_paths.append(normalized)
        return normalized_paths

    def _normalize_contradiction_transformation_signal(self, item: Dict[str, Any]) -> Dict[str, Any]:
        normalized = dict(item)
        normalized["signal"] = str(normalized.get("signal") or normalized.get("condition") or normalized.get("trigger") or "")
        normalized["direction"] = str(normalized.get("direction") or normalized.get("turns_toward") or "")
        normalized["implication"] = str(normalized.get("implication") or normalized.get("action_implication") or "")
        normalized["evidence_refs"] = self._coerce_string_list(normalized.get("evidence_refs"))
        normalized["event_refs"] = self._coerce_event_refs_list(normalized.get("event_refs"))
        return normalized

    def _normalize_price_reflection_assessment(self, item: Dict[str, Any]) -> Dict[str, Any]:
        normalized = dict(item)
        normalized["category"] = self._normalize_price_reflection_category(
            normalized.get("category")
            or normalized.get("type")
            or normalized.get("dimension")
            or normalized.get("target")
            or normalized.get("risk")
            or normalized.get("narrative")
        )
        normalized["target"] = str(
            normalized.get("target")
            or normalized.get("conflict_id")
            or normalized.get("risk")
            or normalized.get("narrative")
            or PRICE_REFLECTION_CATEGORIES.get(normalized["category"], {}).get("target")
            or "price_reflection"
        )
        reflected = str(
            normalized.get("reflected_state")
            or normalized.get("reflection_state")
            or normalized.get("price_reflection")
            or "unclear"
        ).strip().lower()
        allowed = {"not_reflected", "partially_reflected", "largely_reflected", "over_reflected", "unclear"}
        normalized["reflected_state"] = reflected if reflected in allowed else "unclear"
        normalized["rationale"] = str(normalized.get("rationale") or normalized.get("reasoning") or "")
        normalized["evidence_refs"] = self._coerce_string_list(normalized.get("evidence_refs"))
        normalized["counterevidence"] = self._coerce_string_list(
            normalized.get("counterevidence")
            or normalized.get("counter_evidence")
            or normalized.get("falsifiers")
            or normalized.get("contrary_evidence")
        )
        normalized["counterevidence_refs"] = self._coerce_string_list(
            normalized.get("counterevidence_refs")
            or normalized.get("counter_evidence_refs")
            or normalized.get("contrary_evidence_refs")
        )
        normalized["action_implication"] = str(
            normalized.get("action_implication")
            or normalized.get("portfolio_implication")
            or normalized.get("implication")
            or ""
        )
        normalized["missing_evidence"] = self._coerce_string_list(normalized.get("missing_evidence"))
        return normalized

    def _normalize_price_reflection_category(self, value: Any) -> str:
        text = str(value or "").strip().lower()
        text = text.replace("-", "_").replace(" ", "_")
        aliases = {
            "credit": ("credit", "spread", "oas", "hyg", "信用", "利差"),
            "rates": ("rates", "rate", "yield", "real_rate", "treasury", "discount", "利率", "真实利率", "贴现"),
            "valuation": ("valuation", "erp", "earnings", "pe", "multiple", "估值", "盈利", "风险补偿"),
            "technical_panic": ("technical", "panic", "trend", "volatility", "vix", "vxn", "ta", "恐慌", "技术", "波动", "趋势"),
            "liquidity": ("liquidity", "m2", "fed", "policy", "流动性", "政策", "美联储"),
        }
        for category, tokens in aliases.items():
            if any(token in text for token in tokens):
                return category
        return text if text in PRICE_REFLECTION_CATEGORIES else "other"

    def _ensure_price_reflection_categories(
        self,
        items: List[Dict[str, Any]],
        *,
        fallback_evidence_refs: Any = None,
        stage_key: str = "",
    ) -> List[Dict[str, Any]]:
        normalized_items = [self._normalize_price_reflection_assessment(item) for item in items if isinstance(item, dict)]
        seen = {item.get("category") for item in normalized_items}
        fallback_refs = self._coerce_string_list(fallback_evidence_refs)
        for category, meta in PRICE_REFLECTION_CATEGORIES.items():
            if category in seen:
                continue
            normalized_items.append(
                self._normalize_price_reflection_assessment(
                    {
                        "category": category,
                        "target": meta["target"],
                        "reflected_state": "unclear",
                        "rationale": f"{meta['label']}价格反映未被 {stage_key or 'stage'} 原生拆出；保留为待复核项，不能当作已分析充分。",
                        "evidence_refs": fallback_refs[:2],
                        "counterevidence": ["缺少该类别的结构化反证分析"],
                        "counterevidence_refs": [],
                        "action_implication": "降低该类别对动作升级/降级的确定性；等待下游或人工复盘补足。",
                        "missing_evidence": [meta["hint"]],
                    }
                )
            )
        return normalized_items

    def _normalize_time_horizon_view(self, item: Any, *, index: int = 0) -> Dict[str, Any]:
        horizons = ["same_day_or_days", "one_to_three_months", "six_to_twelve_months"]
        if not isinstance(item, dict):
            text = str(item)
            return {
                "horizon": horizons[index] if index < len(horizons) else f"horizon_{index + 1}",
                "view": text,
                "action_implication": "模型以字符串输出；归一化层仅保留语义，证据引用仍需结构化补足。",
                "evidence_refs": [],
                "invalidation_conditions": [],
            }
        normalized = dict(item)
        default_horizon = horizons[index] if index < len(horizons) else f"horizon_{index + 1}"
        horizon_value = str(normalized.get("horizon") or default_horizon)
        if horizon_value not in horizons:
            # T54 批 4：horizon 是固定三档的机械拼写——出界按位置兜底值回正，不发明别名。
            logger.warning("time_horizon_view.horizon 非枚举值 %r，按位置回正为 %r", horizon_value, default_horizon)
            horizon_value = default_horizon
        normalized["horizon"] = horizon_value
        normalized["view"] = str(normalized.get("view") or normalized.get("summary") or normalized.get("thesis") or "")
        normalized["action_implication"] = str(normalized.get("action_implication") or normalized.get("action") or "")
        normalized["evidence_refs"] = self._coerce_string_list(normalized.get("evidence_refs"))
        normalized["invalidation_conditions"] = self._coerce_string_list(normalized.get("invalidation_conditions"))
        return normalized

    def _normalize_portfolio_action(self, item: Any, *, index: int = 0) -> Dict[str, Any]:
        buckets = ["core_position", "tactical_position", "waiting_cash"]
        if not isinstance(item, dict):
            text = str(item)
            return {
                "bucket": buckets[index] if index < len(buckets) else f"bucket_{index + 1}",
                "action": text,
                "rationale": "模型以字符串输出；归一化层仅保留语义，证据引用仍需结构化补足。",
                "conditions": [],
                "evidence_refs": [],
            }
        normalized = dict(item)
        default_bucket = buckets[index] if index < len(buckets) else f"bucket_{index + 1}"
        bucket_value = str(normalized.get("bucket") or normalized.get("position_bucket") or default_bucket)
        if bucket_value not in buckets:
            # T54 批 4：bucket 是固定三档的机械拼写——出界按位置兜底值回正，不发明别名。
            logger.warning("portfolio_action.bucket 非枚举值 %r，按位置回正为 %r", bucket_value, default_bucket)
            bucket_value = default_bucket
        normalized["bucket"] = bucket_value
        normalized["action"] = str(normalized.get("action") or normalized.get("recommendation") or normalized.get("view") or "")
        normalized["rationale"] = str(normalized.get("rationale") or normalized.get("reasoning") or "")
        normalized["conditions"] = self._coerce_string_list(normalized.get("conditions"))
        normalized["evidence_refs"] = self._coerce_string_list(normalized.get("evidence_refs"))
        return normalized

    def _normalize_reader_final(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        normalized = dict(payload)
        normalized["three_reasons"] = self._coerce_string_list(normalized.get("three_reasons"))
        normalized["invalidation_summary"] = self._coerce_string_list(normalized.get("invalidation_summary"))
        normalized["evidence_refs"] = self._coerce_string_list(normalized.get("evidence_refs"))
        normalized["time_horizon_summary"] = [
            self._normalize_time_horizon_view(item, index=index)
            for index, item in enumerate(self._as_list_for_normalization(normalized.get("time_horizon_summary")))
        ]
        normalized["action_summary"] = [
            self._normalize_portfolio_action(item, index=index)
            for index, item in enumerate(self._as_list_for_normalization(normalized.get("action_summary")))
        ]
        return normalized

    def _as_list_for_normalization(self, value: Any) -> List[Any]:
        if value is None:
            return []
        return value if isinstance(value, list) else [value]

    def _normalize_principal_contradiction(
        self,
        item: Dict[str, Any],
        *,
        typed_conflicts: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        normalized = dict(item)
        normalized["contradiction_id"] = str(
            normalized.get("contradiction_id")
            or normalized.get("conflict_id")
            or normalized.get("id")
            or "principal_contradiction"
        )
        normalized["summary"] = str(normalized.get("summary") or normalized.get("description") or "")
        normalized["why_principal"] = str(normalized.get("why_principal") or normalized.get("rationale") or "")
        normalized["dominant_side"] = str(normalized.get("dominant_side") or normalized.get("main_side") or "")
        normalized["secondary_side"] = str(normalized.get("secondary_side") or normalized.get("other_side") or "")
        normalized["price_reflection"] = str(
            normalized.get("price_reflection")
            or normalized.get("price_reflection_assessment")
            or normalized.get("pricing")
            or ""
        )
        normalized["action_implication"] = str(normalized.get("action_implication") or normalized.get("implication") or "")
        normalized["conflict_refs"] = self._coerce_string_list(normalized.get("conflict_refs"))
        if not normalized["conflict_refs"]:
            conflict_id = normalized["contradiction_id"]
            normalized["conflict_refs"] = [conflict_id] if conflict_id else []
        normalized["evidence_refs"] = self._coerce_string_list(normalized.get("evidence_refs"))
        if not normalized["evidence_refs"] and typed_conflicts:
            for conflict in typed_conflicts:
                if conflict.get("conflict_id") in normalized["conflict_refs"]:
                    normalized["evidence_refs"] = self._coerce_string_list(conflict.get("evidence_refs"))
                    break
        signals = normalized.get("transformation_signals")
        if isinstance(signals, list):
            normalized["transformation_signals"] = [
                self._normalize_contradiction_transformation_signal(signal)
                for signal in signals
                if isinstance(signal, dict)
            ]
        else:
            normalized["transformation_signals"] = []
        normalized["unresolved_questions"] = self._coerce_string_list(normalized.get("unresolved_questions"))
        return normalized

    def _normalize_secondary_contradiction(self, item: Dict[str, Any]) -> Dict[str, Any]:
        normalized = dict(item)
        normalized["contradiction_id"] = str(
            normalized.get("contradiction_id")
            or normalized.get("conflict_id")
            or normalized.get("id")
            or "secondary_contradiction"
        )
        normalized["summary"] = str(normalized.get("summary") or normalized.get("description") or "")
        normalized["why_secondary"] = str(normalized.get("why_secondary") or normalized.get("rationale") or "")
        normalized["action_constraint"] = str(normalized.get("action_constraint") or normalized.get("implication") or "")
        normalized["evidence_refs"] = self._coerce_string_list(normalized.get("evidence_refs"))
        return normalized

    def _derive_principal_contradiction(
        self,
        typed_conflicts: List[Dict[str, Any]],
        legacy_conflicts: List[Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        candidates = typed_conflicts if typed_conflicts else [
            self._normalize_typed_conflict(
                {
                    "conflict_id": conflict.get("conflict_type") or f"legacy_conflict_{index}",
                    "conflict_type": conflict.get("conflict_type") or "legacy_conflict",
                    "severity": conflict.get("severity", "medium"),
                    "confidence": conflict.get("confidence", "medium"),
                    "description": conflict.get("description", ""),
                    "mechanism": conflict.get("mechanism", ""),
                    "implication": conflict.get("implication", ""),
                    "involved_layers": conflict.get("involved_layers", []),
                    "evidence_refs": conflict.get("evidence_refs", []),
                    "falsifiers": conflict.get("falsifiers", []),
                }
            )
            for index, conflict in enumerate(legacy_conflicts or [])
            if isinstance(conflict, dict)
        ]
        if not candidates:
            return None

        severity_rank = {"high": 3, "medium": 2, "low": 1}
        principal = sorted(
            candidates,
            key=lambda item: severity_rank.get(str(item.get("severity", "medium")).lower(), 2),
            reverse=True,
        )[0]
        conflict_id = str(principal.get("conflict_id") or principal.get("conflict_type") or "principal_contradiction")
        return self._normalize_principal_contradiction(
            {
                "contradiction_id": conflict_id,
                "summary": principal.get("description", ""),
                "why_principal": "由当前最高严重度跨层冲突兜底推导；Thesis 必须进一步判断其是否真正主导收益风险。",
                "dominant_side": "unclear_until_thesis",
                "secondary_side": "",
                "price_reflection": "unclear",
                "action_implication": principal.get("implication", ""),
                "conflict_refs": [conflict_id],
                "evidence_refs": principal.get("evidence_refs", []),
                "transformation_signals": [
                    {"signal": falsifier, "direction": "weaken_principal_contradiction"}
                    for falsifier in self._coerce_string_list(principal.get("falsifiers"))[:3]
                ],
                "unresolved_questions": [],
            },
            typed_conflicts=candidates,
        )

    def _derive_secondary_contradictions(
        self,
        typed_conflicts: List[Dict[str, Any]],
        principal: Optional[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        principal_refs = set((principal or {}).get("conflict_refs", []) or [])
        secondary = []
        for conflict in typed_conflicts or []:
            conflict_id = str(conflict.get("conflict_id") or conflict.get("conflict_type") or "")
            if conflict_id and conflict_id in principal_refs:
                continue
            secondary.append(
                self._normalize_secondary_contradiction(
                    {
                        "contradiction_id": conflict_id,
                        "summary": conflict.get("description", ""),
                        "why_secondary": "未被 Bridge 标为当前主要矛盾，但仍约束行动力度或置信度。",
                        "action_constraint": conflict.get("implication", ""),
                        "evidence_refs": conflict.get("evidence_refs", []),
                    }
                )
            )
        return secondary[:4]

    def _derive_price_reflection_map(self, principal: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if not principal:
            return []
        return [
            self._normalize_price_reflection_assessment(
                {
                    "target": principal.get("contradiction_id") or "principal_contradiction",
                    "reflected_state": principal.get("price_reflection") or "unclear",
                    "rationale": "Bridge 未原生提供 price_reflection_map；从主要矛盾价格反映字段兜底生成。",
                    "evidence_refs": principal.get("evidence_refs", []),
                    "missing_evidence": [] if principal.get("price_reflection") else ["Bridge 未说明价格反映程度"],
                }
            )
        ]

    def _coerce_event_refs_list(self, value: Any) -> List[str]:
        """BridgeMemo.event_refs must be List[str]; defend against AI mirroring the
        dict-shaped AnalysisPacket.event_refs from the prompt input."""
        if value is None:
            return []
        if isinstance(value, list):
            coerced: List[str] = []
            for item in value:
                if isinstance(item, str):
                    coerced.append(item)
                elif isinstance(item, dict):
                    ref = (
                        item.get("event_id")
                        or item.get("id")
                        or item.get("event_ref")
                        or item.get("ref")
                    )
                    if ref:
                        coerced.append(str(ref))
                elif item is not None:
                    coerced.append(str(item))
            return coerced
        if isinstance(value, dict):
            return [str(key) for key in value.keys()]
        return [str(value)]

    def _coerce_string_list(self, value: Any) -> List[str]:
        if value is None:
            return []
        items = value if isinstance(value, list) else [value]
        coerced: List[str] = []
        for item in items:
            if item is None:
                continue
            if isinstance(item, str):
                text = item.strip()
            elif isinstance(item, dict):
                layer = str(item.get("layer") or "").strip().upper()
                function_id = str(item.get("function_id") or item.get("metric_id") or "").strip()
                if layer and function_id:
                    text = f"{layer}.{function_id}"
                else:
                    text = str(
                        item.get("ref")
                        or item.get("evidence_ref")
                        or item.get("function_id")
                        or item.get("id")
                        or item.get("metric")
                        or ""
                    ).strip()
            else:
                text = str(item).strip()
            if text:
                coerced.append(text)
        return coerced

    def _truncate_text(self, value: Any, max_length: int) -> str:
        text = str(value or "")
        if len(text) <= max_length:
            return text
        if max_length <= 3:
            return text[:max_length]
        return text[: max_length - 3].rstrip() + "..."

    def _normalize_confidence(self, confidence: Any) -> str:
        if not isinstance(confidence, str):
            return "medium"
        lowered = confidence.strip().lower()
        mapping = {
            "高": "high",
            "高置信度": "high",
            "中": "medium",
            "中等": "medium",
            "中等置信度": "medium",
            "低": "low",
            "低置信度": "low",
        }
        if lowered in {"high", "medium", "low"}:
            return lowered
        return mapping.get(confidence.strip(), "medium")

    def _normalize_trend(self, trend: Any) -> Any:
        if not isinstance(trend, str):
            return trend
        mapping = {
            "flat": "stable",
            "neutral": "stable",
            "normal": "stable",
            "sideways": "stable",
            "below": "falling",
            "below_ma": "falling",
            "near_lower": "falling",
            "bearish": "falling",
            "fear": "falling",
            "above": "rising",
            "above_ma": "rising",
            "near_upper": "rising",
            "bullish": "rising",
            "greed": "rising",
            "accumulation": "rising",
            "distribution": "falling",
        }
        lowered = trend.strip().lower()
        return mapping.get(lowered, trend if lowered in {"rising", "falling", "stable", "volatile"} else None)

    def _normalize_magnitude(self, magnitude: Any) -> Any:
        if not isinstance(magnitude, str):
            return magnitude
        lowered = magnitude.strip().lower()
        mapping = {
            "moderate": "elevated",
            "medium": "elevated",
            "unknown": None,
            "na": None,
        }
        if lowered in {"extreme", "high", "elevated", "normal", "low"}:
            return lowered
        return mapping.get(lowered)


def run_vnext_analysis(
    packet: AnalysisPacket | Dict[str, Any],
    *,
    available_models: List[str],
    output_dir: str,
    resume_from_existing: bool = False,
    model_mode: str = "",
) -> Dict[str, Any]:
    orchestrator = VNextOrchestrator(
        available_models=available_models,
        output_dir=output_dir,
        resume_from_existing=resume_from_existing,
        model_mode=model_mode,
    )
    return orchestrator.run(packet)
