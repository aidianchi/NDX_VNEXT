from __future__ import annotations

import argparse
import html
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from .config import path_config
except ImportError:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from config import path_config


def _escape(value: Any) -> str:
    return html.escape(str(value or ""), quote=True)


def _load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _safe_number(value: Any) -> Optional[float]:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value).replace(",", "").strip())
    except ValueError:
        return None


def _fmt_number(value: Any, digits: int = 2) -> str:
    number = _safe_number(value)
    return "N/A" if number is None else f"{number:.{digits}f}"


def _json_for_script(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")


class InteractiveChartWorkbenchGenerator:
    """Generate an experimental TradingView-style chart workbench.

    This is intentionally separate from the native brief report. The brief
    remains a reading surface; this workbench is for interactive market
    exploration when a chart needs crosshair, zoom and overlay behavior.
    """

    def __init__(self, reports_dir: Optional[str] = None, bundle_js: Optional[str] = None) -> None:
        self.reports_dir = Path(reports_dir or path_config.reports_dir)
        self.reports_dir.mkdir(parents=True, exist_ok=True)
        self.bundle_js = bundle_js

    def run(
        self,
        run_dir: str | Path,
        output_path: str | Path | None = None,
        *,
        price_rows: Optional[List[Dict[str, Any]]] = None,
        lookback_days: int = 420,
        modules: Optional[List[str]] = None,
    ) -> str:
        run_path = Path(run_dir)
        artifacts = self._load_artifacts(run_path)
        raw_rows = price_rows
        source_label = "artifact + QQQ OHLCV"
        if raw_rows is None:
            raw_rows = self._artifact_price_rows(artifacts)
            if raw_rows:
                source_label = self._artifact_price_source(artifacts)
            else:
                raw_rows = self._fetch_price_rows(lookback_days)
                source_label = "generated at report time: QQQ OHLCV"
        artifacts["_price_source_label"] = source_label
        rows = self._prepare_price_rows(raw_rows)
        html_text = self._render(run_path, artifacts, rows, selected_modules=modules)
        destination = Path(output_path) if output_path else self._default_output_path(run_path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(html_text, encoding="utf-8")
        return str(destination)

    def _default_output_path(self, run_path: Path) -> Path:
        suffix = run_path.name.split("_", 1)[0] if run_path.name else datetime.now().strftime("%Y%m%d")
        return self.reports_dir / f"vnext_interactive_charts_{suffix}.html"

    def _load_artifacts(self, run_path: Path) -> Dict[str, Any]:
        return {
            "analysis_packet": _load_json(run_path / "analysis_packet.json", {}),
            "l5": _load_json(run_path / "layer_cards" / "L5.json", {}),
            "final": _load_json(run_path / "final_adjudication.json", {}),
            "chart_time_series": _load_json(run_path / "chart_time_series.json", {}),
        }

    def _artifact_price_rows(self, artifacts: Dict[str, Any]) -> List[Dict[str, Any]]:
        chart_artifact = artifacts.get("chart_time_series", {})
        if not isinstance(chart_artifact, dict):
            return []
        series = chart_artifact.get("series", {})
        if not isinstance(series, dict):
            return []
        qqq = series.get("QQQ_OHLCV", {})
        rows = qqq.get("rows", []) if isinstance(qqq, dict) else []
        return rows if isinstance(rows, list) else []

    def _artifact_price_source(self, artifacts: Dict[str, Any]) -> str:
        chart_artifact = artifacts.get("chart_time_series", {})
        series = chart_artifact.get("series", {}) if isinstance(chart_artifact, dict) else {}
        qqq = series.get("QQQ_OHLCV", {}) if isinstance(series, dict) else {}
        source_file = qqq.get("source_file") if isinstance(qqq, dict) else None
        provider = qqq.get("provider") if isinstance(qqq, dict) else None
        if source_file and provider:
            return f"{source_file} · {provider}"
        return str(source_file or "chart_time_series.json")

    def _fetch_price_rows(self, lookback_days: int) -> List[Dict[str, Any]]:
        try:
            from chart_adapter_v6 import get_qqq_price_data
        except ImportError:
            from .chart_adapter_v6 import get_qqq_price_data

        df = get_qqq_price_data(lookback_days=lookback_days)
        if df is None or df.empty:
            return []
        for window in [5, 20, 60, 200]:
            df[f"ma{window}"] = df["close"].rolling(window=window, min_periods=1).mean()
        rows = []
        for _, row in df.iterrows():
            rows.append(
                {
                    "time": row["date"].strftime("%Y-%m-%d"),
                    "open": float(row["open"]),
                    "high": float(row["high"]),
                    "low": float(row["low"]),
                    "close": float(row["close"]),
                    "volume": float(row["volume"]),
                    "ma5": float(row["ma5"]),
                    "ma20": float(row["ma20"]),
                    "ma60": float(row["ma60"]),
                    "ma200": float(row["ma200"]),
                }
            )
        return rows

    def _prepare_price_rows(self, rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        prepared = []
        closes: List[float] = []
        for row in rows:
            close = _safe_number(row.get("close"))
            if close is None:
                continue
            closes.append(close)
            prepared_row = {
                "time": str(row.get("time")),
                "open": _safe_number(row.get("open")) or close,
                "high": _safe_number(row.get("high")) or close,
                "low": _safe_number(row.get("low")) or close,
                "close": close,
                "volume": _safe_number(row.get("volume")) or 0,
            }
            for window in [5, 20, 60, 200]:
                explicit = _safe_number(row.get(f"ma{window}"))
                if explicit is not None:
                    prepared_row[f"ma{window}"] = explicit
                else:
                    tail = closes[-window:]
                    prepared_row[f"ma{window}"] = sum(tail) / len(tail)
            for key in [
                "bb_upper",
                "bb_middle",
                "bb_lower",
                "donchian_upper",
                "donchian_middle",
                "donchian_lower",
                "vwap20",
                "obv",
                "macd",
                "macd_signal",
                "macd_histogram",
                "rsi14",
                "atr14",
                "mfi14",
                "cmf20",
            ]:
                value = _safe_number(row.get(key))
                if value is not None:
                    prepared_row[key] = value
            prepared.append(prepared_row)
        return prepared

    def _chart_payload(
        self,
        artifacts: Dict[str, Any],
        price_rows: List[Dict[str, Any]],
        selected_modules: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        raw_l5 = artifacts.get("analysis_packet", {}).get("raw_data", {}).get("L5", {})
        ma_raw = raw_l5.get("get_multi_scale_ma_position", {}).get("value", {}) if isinstance(raw_l5, dict) else {}
        tech_raw = raw_l5.get("get_qqq_technical_indicators", {}).get("value", {}) if isinstance(raw_l5, dict) else {}
        l5_card = artifacts.get("l5", {})
        chart_artifact = artifacts.get("chart_time_series", {}) if isinstance(artifacts.get("chart_time_series"), dict) else {}
        all_modules = chart_artifact.get("workbench_modules", {}) if isinstance(chart_artifact.get("workbench_modules"), dict) else {}
        if not all_modules:
            all_modules = {
                "price_technical": {
                    "title": "价格技术",
                    "series": ["QQQ_OHLCV"],
                    "layer_tags": ["L5"],
                    "function_ids": ["get_qqq_technical_indicators"],
                }
            }
        selected = selected_modules or list(all_modules)
        modules = {key: value for key, value in all_modules.items() if key in selected}
        series = chart_artifact.get("series", {}) if isinstance(chart_artifact.get("series"), dict) else {}
        return {
            "source": artifacts.get("_price_source_label") or "artifact + QQQ OHLCV",
            "modules": modules,
            "supplementalSeries": self._supplemental_payload(series),
            "candles": [
                {
                    "time": row["time"],
                    "open": row["open"],
                    "high": row["high"],
                    "low": row["low"],
                    "close": row["close"],
                }
                for row in price_rows
            ],
            "volume": [
                {
                    "time": row["time"],
                    "value": row["volume"],
                    "color": "rgba(21, 128, 61, 0.38)" if row["close"] >= row["open"] else "rgba(185, 28, 28, 0.36)",
                }
                for row in price_rows
            ],
            "ma": {
                f"ma{window}": [{"time": row["time"], "value": row[f"ma{window}"]} for row in price_rows]
                for window in [5, 20, 60, 200]
            },
            "bands": {
                "bb_upper": self._line_points(price_rows, "bb_upper"),
                "bb_lower": self._line_points(price_rows, "bb_lower"),
                "donchian_upper": self._line_points(price_rows, "donchian_upper"),
                "donchian_lower": self._line_points(price_rows, "donchian_lower"),
                "vwap20": self._line_points(price_rows, "vwap20"),
            },
            "subpanels": {
                "obv": self._line_points(price_rows, "obv"),
                "macd": self._line_points(price_rows, "macd"),
                "macd_signal": self._line_points(price_rows, "macd_signal"),
                "macd_histogram": self._hist_points(price_rows, "macd_histogram"),
                "rsi14": self._line_points(price_rows, "rsi14"),
                "atr14": self._line_points(price_rows, "atr14"),
                "mfi14": self._line_points(price_rows, "mfi14"),
                "cmf20": self._line_points(price_rows, "cmf20"),
            },
            "summary": {
                "final_stance": artifacts.get("final", {}).get("final_stance"),
                "l5_conclusion": l5_card.get("local_conclusion"),
                "current_price": ma_raw.get("current_price") or tech_raw.get("current_price"),
                "rsi": tech_raw.get("rsi_14"),
                "donchian_position": tech_raw.get("donchian_position_pct"),
                "macd_histogram": tech_raw.get("macd_histogram"),
                "ma_order": ma_raw.get("ma_order"),
            },
        }

    def _line_points(self, rows: List[Dict[str, Any]], key: str) -> List[Dict[str, Any]]:
        return [{"time": row["time"], "value": _safe_number(row.get(key))} for row in rows if _safe_number(row.get(key)) is not None]

    def _hist_points(self, rows: List[Dict[str, Any]], key: str) -> List[Dict[str, Any]]:
        points = []
        for row in rows:
            value = _safe_number(row.get(key))
            if value is None:
                continue
            points.append(
                {
                    "time": row["time"],
                    "value": value,
                    "color": "rgba(21, 128, 61, 0.42)" if value >= 0 else "rgba(185, 28, 28, 0.42)",
                }
            )
        return points

    def _supplemental_payload(self, series: Dict[str, Any]) -> Dict[str, Any]:
        default_labels = {
            "VIX": "VIX",
            "VXN": "VXN",
            "HY_OAS": "HY OAS",
            "IG_OAS": "IG OAS",
            "US10Y": "10Y Treasury",
            "DAMODARAN_ERP_MONTHLY": "Damodaran ERP",
            "QQQ_QQEW_RATIO": "QQQ/QQEW",
            "NET_LIQUIDITY": "Net Liquidity",
            "WALCL": "WALCL",
            "TGA": "TGA",
            "RRP": "RRP",
            "M2_YOY": "M2 YoY",
        }
        payload: Dict[str, Any] = {}
        for key, item in series.items():
            if key == "QQQ_OHLCV" or not isinstance(item, dict):
                continue
            rows = item.get("rows", [])
            if not isinstance(rows, list):
                rows = []
            payload[key] = {
                "label": item.get("label") or default_labels.get(key) or key,
                "layer": item.get("layer"),
                "function_id": item.get("function_id"),
                "provider": item.get("provider"),
                "frequency": item.get("frequency"),
                "rows": [
                    {"time": str(row.get("time")), "value": _safe_number(row.get("value"))}
                    for row in rows
                    if isinstance(row, dict) and _safe_number(row.get("value")) is not None
                ],
            }
        return payload

    def _bundle(self) -> str:
        if self.bundle_js is not None:
            return self.bundle_js
        bundle_path = Path(__file__).resolve().parents[1] / "node_modules" / "lightweight-charts" / "dist" / "lightweight-charts.standalone.production.js"
        if bundle_path.exists():
            return bundle_path.read_text(encoding="utf-8")
        return ""

    def _render(
        self,
        run_path: Path,
        artifacts: Dict[str, Any],
        price_rows: List[Dict[str, Any]],
        *,
        selected_modules: Optional[List[str]] = None,
    ) -> str:
        payload = self._chart_payload(artifacts, price_rows, selected_modules=selected_modules)
        bundle = self._bundle()
        data_json = _json_for_script(payload)
        summary = payload["summary"]
        last = price_rows[-1] if price_rows else {}
        module_tabs = self._module_tabs(payload["modules"])
        module_sections = self._module_sections(payload["modules"])
        chart_script = (
            f"<script>{bundle}</script>"
            if bundle
            else '<script src="https://unpkg.com/lightweight-charts@5.2.0/dist/lightweight-charts.standalone.production.js"></script>'
        )
        return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>vNext Interactive Chart Workbench</title>
  <style>{self._css()}</style>
</head>
<body>
  <main class="shell">
    <header class="topbar">
      <div>
        <p>NDX vNext</p>
        <h1>vNext Interactive Chart Workbench</h1>
      </div>
      <a href="./vnext_research_ui_brief_20260502.html#layers">返回 brief 底稿</a>
    </header>
    <section class="summary-grid">
      <article><span>Final</span><b>{_escape(summary.get('final_stance'))}</b></article>
      <article><span>L5</span><b>{_escape(summary.get('l5_conclusion'))}</b></article>
      <article><span>Last Close</span><b>{_fmt_number(last.get('close'))}</b></article>
      <article><span>RSI / Donchian</span><b>{_fmt_number(summary.get('rsi'))} / {_fmt_number(summary.get('donchian_position'))}%</b></article>
    </section>
    <section class="chart-shell">
      <div class="chart-head">
        <div>
          <h2>QQQ Price Action</h2>
          <p>TradingView Lightweight Charts prototype. 数据源：{_escape(payload.get('source'))}；用于验证交互图形态，不替代最终审计链。</p>
        </div>
        <div class="range-buttons">
          <button data-range="90">3M</button>
          <button data-range="180">6M</button>
          <button data-range="365">1Y</button>
          <button data-range="all">ALL</button>
        </div>
      </div>
      <nav class="module-tabs" aria-label="Workbench modules">
        {module_tabs}
      </nav>
      <div class="chart-grid">
        <div>
          <section class="module-section is-active" data-module="price_technical">
            <div class="price-chart" data-chart-root="qqq-price-action"></div>
            <div class="subpanel-grid" aria-label="L5 technical subpanels">
              <article><h3>Volume</h3><div data-panel-root="volume"></div></article>
              <article><h3>OBV</h3><div data-panel-root="obv"></div></article>
              <article><h3>MACD</h3><div data-panel-root="macd"></div></article>
              <article><h3>RSI / ATR</h3><div data-panel-root="rsi-atr"></div></article>
              <article><h3>MFI / CMF</h3><div data-panel-root="money-flow"></div></article>
            </div>
          </section>
          {module_sections}
        </div>
        <aside class="readout" id="readout">
          <h3>Crosshair</h3>
          <p>把鼠标移到图上查看 OHLC、成交量和均线读数。</p>
        </aside>
      </div>
      <div class="legend">
        <span class="candle">Candles</span>
        <span class="ma5">MA5</span>
        <span class="ma20">MA20</span>
        <span class="ma60">MA60</span>
        <span class="ma200">MA200</span>
        <span class="bollinger">Bollinger</span>
        <span class="donchian">Donchian</span>
        <span class="vwap">VWAP</span>
        <span class="volume">Volume</span>
      </div>
    </section>
  </main>
  <script id="chart-data" type="application/json">{data_json}</script>
  {chart_script}
  <script>{self._js()}</script>
</body>
</html>
"""

    def _module_tabs(self, modules: Dict[str, Any]) -> str:
        labels = []
        for key, module in modules.items():
            title = _escape(module.get("title") if isinstance(module, dict) else key)
            active = " is-active" if key == "price_technical" else ""
            labels.append(f'<button type="button" class="module-tab{active}" data-module-tab="{_escape(key)}">{title}</button>')
        return "".join(labels)

    def _module_sections(self, modules: Dict[str, Any]) -> str:
        titles = {
            "volatility_credit": "波动信用",
            "rates_valuation": "利率估值",
            "breadth_concentration": "广度集中度",
            "liquidity": "流动性",
        }
        hints = {
            "volatility_credit": "VIX、VXN、HY/IG OAS 与 QQQ 放在同一工作台，观察“价格强但保险费/信用先警告”。",
            "rates_valuation": "10Y、真实利率、breakeven 与 Damodaran ERP 同屏，观察估值折现压力。",
            "breadth_concentration": "QQQ/QQEW 与价格同屏，观察上涨是否集中在头部权重。",
            "liquidity": "净流动性、WALCL、TGA、RRP 与风险资产同屏，观察资金面传导。",
        }
        sections = []
        for key, title in titles.items():
            if key not in modules:
                continue
            sections.append(
                f"""
          <section class="module-section" data-module="{_escape(key)}">
            <div class="module-copy">
              <h2>{_escape(title)}</h2>
              <p>{_escape(hints[key])}</p>
            </div>
            <div class="module-chart" data-module-chart="{_escape(key)}"></div>
          </section>
"""
            )
        return "".join(sections)

    def _css(self) -> str:
        return """
:root {
  --paper: #f3f3f1;
  --panel: #fbfbf8;
  --ink: #171717;
  --muted: #6b6b66;
  --rule: #d7d4cb;
  --accent: #be4d25;
  --good: #18845b;
  --bad: #b93632;
  --blue: #2563eb;
  --amber: #b7791f;
  --violet: #6d5bd0;
  --shadow: 0 18px 50px rgba(23, 23, 23, .08);
}
* { box-sizing: border-box; }
body {
  margin: 0;
  background: var(--paper);
  color: var(--ink);
  font-family: ui-sans-serif, -apple-system, BlinkMacSystemFont, "PingFang SC", "Microsoft YaHei", sans-serif;
}
.shell {
  width: min(1280px, calc(100vw - 32px));
  margin: 0 auto;
  padding: 28px 0 48px;
}
.topbar {
  display: flex;
  justify-content: space-between;
  gap: 24px;
  align-items: end;
  border-bottom: 1px solid var(--rule);
  padding-bottom: 18px;
}
.topbar p {
  margin: 0 0 6px;
  color: var(--accent);
  font-size: 12px;
  font-weight: 700;
  letter-spacing: .12em;
  text-transform: uppercase;
}
.topbar h1 {
  margin: 0;
  font-size: 30px;
  line-height: 1.1;
  letter-spacing: 0;
}
.topbar a {
  color: var(--ink);
  border: 1px solid var(--rule);
  padding: 8px 10px;
  text-decoration: none;
  font-size: 13px;
  background: var(--panel);
}
.summary-grid {
  display: grid;
  grid-template-columns: 1fr 1.4fr .6fr .8fr;
  gap: 10px;
  margin: 18px 0;
}
.summary-grid article,
.chart-shell {
  border: 1px solid var(--rule);
  background: var(--panel);
  box-shadow: var(--shadow);
}
.summary-grid article {
  padding: 12px;
  min-width: 0;
}
.summary-grid span {
  display: block;
  color: var(--muted);
  font-size: 11px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: .08em;
}
.summary-grid b {
  display: block;
  margin-top: 5px;
  font-size: 13px;
  line-height: 1.45;
  overflow-wrap: anywhere;
}
.chart-shell { padding: 18px; }
.chart-head,
.chart-grid,
.legend {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 230px;
  gap: 16px;
}
.chart-head { align-items: end; margin-bottom: 12px; }
.chart-head h2 { margin: 0 0 4px; font-size: 22px; }
.chart-head p { margin: 0; color: var(--muted); line-height: 1.55; font-size: 13px; }
.range-buttons {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 6px;
}
.range-buttons button {
  border: 1px solid var(--rule);
  background: #fff;
  color: var(--ink);
  font-weight: 700;
  padding: 7px 0;
  cursor: pointer;
}
.range-buttons button:hover { border-color: var(--ink); }
.module-tabs {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin: 12px 0;
  border-top: 1px solid var(--rule);
  padding-top: 12px;
}
.module-tab {
  border: 1px solid var(--rule);
  background: #fff;
  color: var(--ink);
  padding: 7px 10px;
  font-weight: 700;
  cursor: pointer;
}
.module-tab.is-active {
  background: var(--ink);
  border-color: var(--ink);
  color: #fff;
}
.module-section { display: none; }
.module-section.is-active { display: block; }
.price-chart {
  height: 640px;
  min-width: 0;
  border: 1px solid var(--rule);
  background: #fff;
}
.subpanel-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
  margin-top: 8px;
}
.subpanel-grid article {
  border: 1px solid var(--rule);
  background: #fff;
  min-width: 0;
  padding: 8px;
}
.subpanel-grid article:first-child { grid-column: 1 / -1; }
.subpanel-grid h3 {
  margin: 0 0 6px;
  color: var(--muted);
  font-size: 11px;
  letter-spacing: .08em;
  text-transform: uppercase;
}
[data-panel-root] { height: 150px; min-width: 0; }
.module-copy {
  border: 1px solid var(--rule);
  border-bottom: 0;
  background: #fff;
  padding: 14px;
}
.module-copy h2 { margin: 0 0 4px; font-size: 18px; }
.module-copy p { margin: 0; color: var(--muted); font-size: 13px; line-height: 1.55; }
.module-chart {
  height: 460px;
  border: 1px solid var(--rule);
  background: #fff;
}
.readout {
  border: 1px solid var(--rule);
  background: #fff;
  padding: 14px;
  min-height: 180px;
}
.readout h3 {
  margin: 0 0 10px;
  font-size: 13px;
  text-transform: uppercase;
  letter-spacing: .08em;
}
.readout p,
.readout dl {
  margin: 0;
  color: var(--muted);
  font-size: 12px;
  line-height: 1.7;
}
.readout dl {
  display: grid;
  grid-template-columns: 70px 1fr;
  gap: 5px 8px;
}
.readout dt { color: var(--muted); }
.readout dd { margin: 0; color: var(--ink); font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }
.legend {
  margin-top: 10px;
  grid-template-columns: repeat(9, max-content);
  color: var(--muted);
  font-size: 12px;
}
.legend span::before {
  content: "";
  display: inline-block;
  width: 18px;
  height: 3px;
  margin-right: 6px;
  vertical-align: middle;
  background: currentColor;
}
.ma5 { color: var(--accent); }
.ma20 { color: var(--blue); }
.ma60 { color: var(--amber); }
.ma200 { color: var(--violet); }
.bollinger { color: #64748b; }
.donchian { color: #0f766e; }
.vwap { color: #7c3aed; }
.volume { color: var(--muted); }
@media (max-width: 900px) {
  .summary-grid,
  .chart-head,
  .chart-grid { grid-template-columns: 1fr; }
  .price-chart { height: 520px; }
  .subpanel-grid { grid-template-columns: 1fr; }
  .module-chart { height: 360px; }
}
"""

    def _js(self) -> str:
        return """
const payload = JSON.parse(document.getElementById('chart-data').textContent);
const root = document.querySelector('[data-chart-root="qqq-price-action"]');
const readout = document.getElementById('readout');
const syncedCharts = [];

function fmt(value, digits = 2) {
  return Number.isFinite(value) ? value.toFixed(digits) : 'N/A';
}

function lineData(name) {
  return (payload.ma[name] || []).filter(point => Number.isFinite(point.value));
}

function points(rows) {
  return (rows || []).filter(point => Number.isFinite(point.value));
}

function createBaseChart(target, height) {
  const chart = LightweightCharts.createChart(target, {
    autoSize: true,
    height,
    layout: { background: { color: '#ffffff' }, textColor: '#2b2b2a', attributionLogo: false },
    grid: { vertLines: { color: '#eeeeea' }, horzLines: { color: '#eeeeea' } },
    rightPriceScale: { borderColor: '#d7d4cb' },
    timeScale: { borderColor: '#d7d4cb', timeVisible: false },
  });
  syncedCharts.push(chart);
  return chart;
}

const chart = createBaseChart(root, 640);
chart.applyOptions({
  grid: { vertLines: { color: '#eeeeea' }, horzLines: { color: '#eeeeea' } },
  crosshair: { mode: LightweightCharts.CrosshairMode.Normal },
  rightPriceScale: { borderColor: '#d7d4cb', scaleMargins: { top: 0.08, bottom: 0.24 } },
  timeScale: { borderColor: '#d7d4cb', timeVisible: false },
});

const candleSeries = chart.addSeries(LightweightCharts.CandlestickSeries, {
  upColor: '#18845b',
  downColor: '#b93632',
  borderVisible: false,
  wickUpColor: '#18845b',
  wickDownColor: '#b93632',
});
candleSeries.setData(payload.candles);

const volumeSeries = chart.addSeries(LightweightCharts.HistogramSeries, {
  priceFormat: { type: 'volume' },
  priceScaleId: 'volume',
});
volumeSeries.priceScale().applyOptions({ scaleMargins: { top: 0.82, bottom: 0 } });
volumeSeries.setData(payload.volume);

[
  ['ma5', '#be4d25', 2],
  ['ma20', '#2563eb', 2],
  ['ma60', '#b7791f', 1],
  ['ma200', '#6d5bd0', 1],
].forEach(([name, color, width]) => {
  const series = chart.addSeries(LightweightCharts.LineSeries, { color, lineWidth: width, priceLineVisible: false });
  series.setData(lineData(name));
});
[
  ['bb_upper', '#64748b', 1],
  ['bb_lower', '#64748b', 1],
  ['donchian_upper', '#0f766e', 1],
  ['donchian_lower', '#0f766e', 1],
  ['vwap20', '#7c3aed', 2],
].forEach(([name, color, width]) => {
  const series = chart.addSeries(LightweightCharts.LineSeries, { color, lineWidth: width, priceLineVisible: false });
  series.setData(points(payload.bands[name]));
});

function renderPanel(rootSelector, config) {
  const target = document.querySelector(rootSelector);
  if (!target) return;
  const panel = createBaseChart(target, 150);
  config.forEach(item => {
    const kind = item.kind || 'line';
    const series = panel.addSeries(kind === 'histogram' ? LightweightCharts.HistogramSeries : LightweightCharts.LineSeries, {
      color: item.color,
      lineWidth: item.width || 1,
      priceLineVisible: false,
      priceFormat: item.priceFormat || { type: 'price', precision: 2, minMove: 0.01 },
    });
    series.setData(points(item.data));
  });
  panel.timeScale().fitContent();
}

renderPanel('[data-panel-root="volume"]', [{ kind: 'histogram', data: payload.volume, color: 'rgba(75, 85, 99, .45)', priceFormat: { type: 'volume' } }]);
renderPanel('[data-panel-root="obv"]', [{ data: payload.subpanels.obv, color: '#7c3aed' }]);
renderPanel('[data-panel-root="macd"]', [
  { kind: 'histogram', data: payload.subpanels.macd_histogram, color: '#94a3b8' },
  { data: payload.subpanels.macd, color: '#2563eb' },
  { data: payload.subpanels.macd_signal, color: '#be4d25' },
]);
renderPanel('[data-panel-root="rsi-atr"]', [
  { data: payload.subpanels.rsi14, color: '#b7791f' },
  { data: payload.subpanels.atr14, color: '#0f766e' },
]);
renderPanel('[data-panel-root="money-flow"]', [
  { data: payload.subpanels.mfi14, color: '#2563eb' },
  { data: payload.subpanels.cmf20, color: '#18845b' },
]);

function renderModuleChart(moduleKey, colors) {
  const target = document.querySelector(`[data-module-chart="${moduleKey}"]`);
  const module = payload.modules[moduleKey];
  if (!target || !module) return;
  const moduleChart = createBaseChart(target, 460);
  (module.series || []).forEach((seriesKey, index) => {
    if (seriesKey === 'QQQ_OHLCV') {
      const closeSeries = moduleChart.addSeries(LightweightCharts.LineSeries, { color: colors[index % colors.length], lineWidth: 2, priceLineVisible: false });
      closeSeries.setData(payload.candles.map(item => ({ time: item.time, value: item.close })));
      return;
    }
    const item = payload.supplementalSeries[seriesKey];
    if (!item || !item.rows || !item.rows.length) return;
    const line = moduleChart.addSeries(LightweightCharts.LineSeries, { color: colors[index % colors.length], lineWidth: 2, priceLineVisible: false, title: item.label });
    line.setData(points(item.rows));
  });
  moduleChart.timeScale().fitContent();
}

renderModuleChart('volatility_credit', ['#be4d25', '#7c3aed', '#b7791f', '#2563eb', '#18845b']);
renderModuleChart('rates_valuation', ['#2563eb', '#be4d25', '#0f766e', '#64748b', '#7c3aed']);
renderModuleChart('breadth_concentration', ['#7c3aed', '#2563eb']);
renderModuleChart('liquidity', ['#18845b', '#2563eb', '#be4d25', '#64748b', '#b7791f']);

syncedCharts.forEach(item => item.timeScale().fitContent());

function updateRange(days) {
  if (days === 'all' || payload.candles.length <= days) {
    syncedCharts.forEach(item => item.timeScale().fitContent());
    return;
  }
  const to = payload.candles.length - 1;
  syncedCharts.forEach(item => item.timeScale().setVisibleLogicalRange({ from: Math.max(0, to - Number(days)), to }));
}

document.querySelectorAll('[data-range]').forEach(button => {
  button.addEventListener('click', () => updateRange(button.dataset.range));
});

document.querySelectorAll('[data-module-tab]').forEach(button => {
  button.addEventListener('click', () => {
    const key = button.dataset.moduleTab;
    document.querySelectorAll('[data-module-tab]').forEach(item => item.classList.toggle('is-active', item === button));
    document.querySelectorAll('[data-module]').forEach(item => item.classList.toggle('is-active', item.dataset.module === key));
  });
});

chart.subscribeCrosshairMove(param => {
  if (!param || !param.time || !param.seriesData) {
    readout.innerHTML = '<h3>Crosshair</h3><p>把鼠标移到图上查看 OHLC、成交量和均线读数。</p>';
    return;
  }
  const candle = param.seriesData.get(candleSeries);
  if (!candle) return;
  const row = payload.candles.find(item => item.time === param.time) || {};
  readout.innerHTML = `
    <h3>${param.time}</h3>
    <dl>
      <dt>Open</dt><dd>${fmt(candle.open)}</dd>
      <dt>High</dt><dd>${fmt(candle.high)}</dd>
      <dt>Low</dt><dd>${fmt(candle.low)}</dd>
      <dt>Close</dt><dd>${fmt(candle.close)}</dd>
      <dt>Volume</dt><dd>${fmt((payload.volume.find(item => item.time === param.time) || {}).value, 0)}</dd>
      <dt>RSI</dt><dd>${fmt((payload.subpanels.rsi14.find(item => item.time === param.time) || {}).value)}</dd>
      <dt>MACD</dt><dd>${fmt((payload.subpanels.macd_histogram.find(item => item.time === param.time) || {}).value)}</dd>
      <dt>MFI</dt><dd>${fmt((payload.subpanels.mfi14.find(item => item.time === param.time) || {}).value)}</dd>
      <dt>CMF</dt><dd>${fmt((payload.subpanels.cmf20.find(item => item.time === param.time) || {}).value, 4)}</dd>
    </dl>
  `;
});
"""


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate vNext interactive chart workbench.")
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--output")
    parser.add_argument("--lookback-days", type=int, default=420)
    parser.add_argument(
        "--modules",
        default="price_technical,volatility_credit,rates_valuation,breadth_concentration,liquidity",
        help="Comma-separated workbench modules to render.",
    )
    args = parser.parse_args()
    generator = InteractiveChartWorkbenchGenerator()
    modules = [item.strip() for item in args.modules.split(",") if item.strip()]
    print(generator.run(args.run_dir, args.output, lookback_days=args.lookback_days, modules=modules))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
