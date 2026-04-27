# Migration Manifest

Target: `C:\ndx_vnext`
Date: 2026-04-23
Strategy: clean-room bootstrap with selective migration only

## Migrated
- Constitution docs: `docs/4.20 VNEXT_REPORT.md`, `docs/history/4.12vnext_2026-04-12.md`
- Context docs: `docs/context/CLAUDE.md`, `docs/context/纳斯达克100指挥中心[MECE].txt`
- Runtime config: `.env`, `.env.example`, `config/api_config*.json`, `config/manual_data*.json`
- Stable support modules: `src/api_config.py`, `src/config.py`, `src/data_manager.py`, `src/data_cache.py`, `src/manual_data.py`
- Data collection stack: `src/tools*.py`, `src/core/collector.py`
- Legacy report stack: `src/chart_generator.py`, `src/chart_adapter_v6.py`, `src/core/reporter.py`
- Reference cognition assets: `src/prompt_examples.py`, `src/reasoning_examples.py`
- Recycled vNext modules from feature branch: `src/agent_analysis/llm_engine.py`, `src/agent_analysis/legacy_adapter.py`, `src/agent_analysis/contracts.py`
- Lightweight tests for recycled modules: `tests/test_vnext_llm_engine.py`, `tests/test_vnext_legacy_adapter.py`

## Intentionally not migrated
- `.venv`, `.pytest_cache`, IDE folders, historical outputs, caches
- `src/core/analyzer.py` (legacy giant-prompt chain)
- `src/launcher.py`, `run_launcher.py`, GUI/API config UI
- current worktree `src/agent_analysis/orchestrator.py` and `packet_builder.py`
- feature-branch heavy/still-disputed vNext flow files beyond the clearly reusable pieces

## User action needed
- Recreate a fresh virtual environment inside `C:\ndx_vnext`
- Review copied secrets/config: `.env`, `config/api_config.local.json`, `config/manual_data.local.json`
- Install dependencies from `requirements.txt`
