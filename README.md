# ndx_vnext

A clean vNext rebuild workspace extracted from `C:\ndx_agent`.

Current bootstrap scope:
- vNext constitution and context docs
- API/config/manual override files
- stable data collection and legacy reporting layers
- selected recyclable vNext modules (`llm_engine`, `legacy_adapter`, `contracts`)
- no legacy GUI, no legacy giant-prompt analyzer, no historical output garbage

Immediate goal:
- build the main cognitive chain in this repository
- keep a legacy report compatibility bridge during the transition

Important:
- `docs/4.20 VNEXT_REPORT.md` is the primary architecture constitution
- old repo files are reference material, not binding architecture
