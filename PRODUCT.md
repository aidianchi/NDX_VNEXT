# NDX vNext Product Context

register: product

## Product Purpose

NDX vNext is a research operating system for judging Nasdaq-100 market conditions through an auditable reasoning chain. Its job is not to produce a prettier one-page market note. Its job is to help a serious reader move from raw market data, through isolated L1-L5 analysis, into explicit conflicts, resonances, risks, and a final thesis that preserves unresolved tension.

The product should answer five questions every time:

1. What object are we judging: NDX, QQQ exposure, or an equal-weight reference?
2. What does each indicator have permission to say?
3. Which facts confirm each other?
4. Which facts disagree?
5. What new evidence would change the conclusion?

## Users

The primary user is a research-oriented individual investor or analyst who is comfortable with market concepts but does not want a black-box report. They need to inspect the chain of reasoning, challenge the evidence, and rerun the system with controlled inputs.

Secondary users include future code agents and maintainers who need clear artifacts, stable contracts, and explicit boundaries between data collection, layer analysis, bridge synthesis, governance review, UI rendering, and interactive workbench exploration.

## Product Principles

- Context-first, role-second. Agents exist to isolate context and cognitive transformation boundaries, not to imitate human job titles.
- Conflicts are assets. The product must preserve high-severity tension instead of smoothing it away.
- Native vNext artifacts are the source of truth. Legacy HTML is compatibility output, not the main product.
- Data humility beats fluent certainty. Missing, stale, weak, or proxy data must lower confidence visibly.
- UI serves audit and repeated use. The interface should feel like a professional research console, not a marketing page and not a temporary form.
- Sidecar information stays sidecar until proven safe. News and event context can explain catalysts, but it must not overwrite numeric indicators or leak into L1-L5 runtime context.

## Scope

The product currently includes:

- Market data collection and standardization.
- L1-L5 isolated analysis.
- Bridge conflict, resonance, and transmission mapping.
- Thesis, critic, risk, reviser, and final adjudication stages.
- Native brief report.
- Interactive chart workbench.
- Research console for configuration, manual data, model strategy, artifacts, and controlled run entry.
- Optional sidecar event ledger for official macro and issuer events.

The product does not yet include:

- A formal multi-user web app.
- Persistent authenticated backend workflows.
- A general-purpose news sentiment engine.
- A full OpenBB integration.
- Automatic trading, portfolio execution, or investment advice.

## Tone

The product should sound calm, precise, and unseduced by its own conclusions. It can be direct, but it should not sound like a trading signal service. Chinese is the default explanation language for user-facing reports and documentation. English terms are acceptable when they name standard market concepts, but first-use explanations should be clear.

## Anti-References

Avoid:

- SaaS landing-page aesthetics.
- Hero metrics and decorative dashboards.
- Dark terminal visuals used only because finance software often looks dark.
- Overconfident market calls.
- Hiding data gaps behind smooth prose.
- Treating all data sources as equally authoritative.
- Turning news into narrative confirmation before numeric evidence is checked.

## Success Criteria

The product is successful when a reader can:

- Understand the final stance without reading code.
- Trace every major claim back to evidence refs or event refs.
- See which conflicts remain unresolved.
- Use the console to configure a run without editing command lines.
- Open the latest brief and workbench naturally.
- Distinguish official facts, proxies, composites, structural signals, and technical indicators.
- Rerun or review the system without breaking context isolation.
