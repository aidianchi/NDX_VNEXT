# -*- coding: utf-8 -*-
"""Recycled vNext building blocks for ndx_vnext."""

from .llm_engine import LLMEngine
from .legacy_adapter import adapt_vnext_to_legacy
from .orchestrator import VNextOrchestrator, run_vnext_analysis
from .packet_builder import AnalysisPacketBuilder, build_analysis_packet
from .vnext_reporter import VNextReportGenerator
from .contracts import (
    Layer,
    PermissionType,
    ObjectCanon,
    IndicatorCanon,
    RegimeScenarioCanon,
    ObjectiveFirewallSummary,
    LayerCard,
    IndicatorAnalysis,
    QualitySelfCheck,
    TypedConflict,
    ResonanceChain,
    TransmissionPath,
    BridgeMemo,
    SynthesisPacket,
    ThesisDraft,
    Critique,
    RiskBoundaryReport,
    SchemaGuardReport,
    AnalysisRevised,
    FinalAdjudication,
    AnalysisPacket,
)

__all__ = [
    "LLMEngine",
    "adapt_vnext_to_legacy",
    "AnalysisPacketBuilder",
    "build_analysis_packet",
    "VNextReportGenerator",
    "VNextOrchestrator",
    "run_vnext_analysis",
    "Layer",
    "PermissionType",
    "ObjectCanon",
    "IndicatorCanon",
    "RegimeScenarioCanon",
    "ObjectiveFirewallSummary",
    "LayerCard",
    "IndicatorAnalysis",
    "QualitySelfCheck",
    "TypedConflict",
    "ResonanceChain",
    "TransmissionPath",
    "BridgeMemo",
    "SynthesisPacket",
    "ThesisDraft",
    "Critique",
    "RiskBoundaryReport",
    "SchemaGuardReport",
    "AnalysisRevised",
    "FinalAdjudication",
    "AnalysisPacket",
]
