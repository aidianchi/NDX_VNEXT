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
        html_text = self._render(run_path, artifacts, rows)
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
            prepared.append(prepared_row)
        return prepared

    def _chart_payload(self, artifacts: Dict[str, Any], price_rows: List[Dict[str, Any]]) -> Dict[str, Any]:
        raw_l5 = artifacts.get("analysis_packet", {}).get("raw_data", {}).get("L5", {})
        ma_raw = raw_l5.get("get_multi_scale_ma_position", {}).get("value", {}) if isinstance(raw_l5, dict) else {}
        tech_raw = raw_l5.get("get_qqq_technical_indicators", {}).get("value", {}) if isinstance(raw_l5, dict) else {}
        l5_card = artifacts.get("l5", {})
        return {
            "source": artifacts.get("_price_source_label") or "artifact + QQQ OHLCV",
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

    def _bundle(self) -> str:
        if self.bundle_js is not None:
            return self.bundle_js
        bundle_path = Path(__file__).resolve().parents[1] / "node_modules" / "lightweight-charts" / "dist" / "lightweight-charts.standalone.production.js"
        if bundle_path.exists():
            return bundle_path.read_text(encoding="utf-8")
        return ""

    def _render(self, run_path: Path, artifacts: Dict[str, Any], price_rows: List[Dict[str, Any]]) -> str:
        payload = self._chart_payload(artifacts, price_rows)
        bundle = self._bundle()
        data_json = _json_for_script(payload)
        summary = payload["summary"]
        last = price_rows[-1] if price_rows else {}
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
      <div class="chart-grid">
        <div class="price-chart" data-chart-root="qqq-price-action"></div>
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
.price-chart {
  height: 640px;
  min-width: 0;
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
  grid-template-columns: repeat(6, max-content);
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
.volume { color: var(--muted); }
@media (max-width: 900px) {
  .summary-grid,
  .chart-head,
  .chart-grid { grid-template-columns: 1fr; }
  .price-chart { height: 520px; }
}
"""

    def _js(self) -> str:
        return """
const payload = JSON.parse(document.getElementById('chart-data').textContent);
const root = document.querySelector('[data-chart-root="qqq-price-action"]');
const readout = document.getElementById('readout');

function fmt(value, digits = 2) {
  return Number.isFinite(value) ? value.toFixed(digits) : 'N/A';
}

function lineData(name) {
  return (payload.ma[name] || []).filter(point => Number.isFinite(point.value));
}

const chart = LightweightCharts.createChart(root, {
  autoSize: true,
  layout: { background: { color: '#ffffff' }, textColor: '#2b2b2a', attributionLogo: false },
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

chart.timeScale().fitContent();

function updateRange(days) {
  if (days === 'all' || payload.candles.length <= days) {
    chart.timeScale().fitContent();
    return;
  }
  const to = payload.candles.length - 1;
  chart.timeScale().setVisibleLogicalRange({ from: Math.max(0, to - Number(days)), to });
}

document.querySelectorAll('[data-range]').forEach(button => {
  button.addEventListener('click', () => updateRange(button.dataset.range));
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
    </dl>
  `;
});
"""


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate vNext interactive chart workbench.")
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--output")
    parser.add_argument("--lookback-days", type=int, default=420)
    args = parser.parse_args()
    generator = InteractiveChartWorkbenchGenerator()
    print(generator.run(args.run_dir, args.output, lookback_days=args.lookback_days))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
