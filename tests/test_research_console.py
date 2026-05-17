import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from research_console import ResearchConsoleGenerator


def test_research_console_generates_first_screen_controls(tmp_path: Path, monkeypatch):
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir()
    (reports_dir / "vnext_research_ui_brief_20260505.html").write_text("<html></html>", encoding="utf-8")
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    latest_data = data_dir / "data_collected_v9_20260509.json"
    latest_data.write_text('{"timestamp_utc": "2026-05-09T12:30:00Z"}', encoding="utf-8")
    logs_dir = tmp_path / "logs"
    control_log_dir = logs_dir / "control_service"
    control_log_dir.mkdir(parents=True)
    (control_log_dir / "20260512_215333_001.log").write_text("run log", encoding="utf-8")

    import research_console
    monkeypatch.setattr(research_console.path_config, "data_dir", str(data_dir))
    monkeypatch.setattr(research_console.path_config, "logs_dir", str(logs_dir))
    generator = ResearchConsoleGenerator(reports_dir=reports_dir)
    output = Path(generator.run(output_path=tmp_path / "console.html"))
    html = output.read_text(encoding="utf-8")

    assert "NDX vNext 研究控制台" in html
    assert "console_logs_entry_v4" in html
    assert "运行对象与日期" in html
    assert "历史日期 / 回测" in html
    assert 'id="historicalDateMode"' in html
    assert "人工数据与数据源校准" in html
    assert "完整 vNext 默认重新采集数据" in html
    assert "使用人工数据" in html
    assert 'id="manualActive"' in html
    assert 'data-manual-field="confidence"' not in html
    assert "当前 PE" in html
    assert "Forward PE" in html
    assert "Earnings Yield" in html
    assert "Forward Earnings Yield" in html
    assert "FCF Yield" in html
    assert "当前 PCF" in html
    assert "PE 10Y 分位" in html
    assert "ERP 5Y 分位" in html
    assert "ERP 10Y 分位" in html
    assert "manual_erp_percentile_10y" in html
    assert "当前 PB" in html
    assert "PB 10Y 分位" in html
    assert "高级 JSON 预览" in html
    assert "模型与 vNext 流程" in html
    assert "完整 vNext" in html
    assert "已有数据分析" in html
    assert "只生成 brief" in html
    assert "只生成 workbench" in html
    assert "查看日志" in html
    assert 'value="logs_only"' in html
    assert "最新日志" in html
    assert "20260512_215333_001.log" in html
    assert "output/logs/control_service/*.log" in html
    assert "visual_check" not in html
    assert "deepseek-v4-flash" in html
    assert "deepseek-v4-pro" in html
    assert "自定义顺序" in html
    assert "数据源选择" in html
    assert "旧版 HTML 已退出日常入口" in html
    assert "默认只生成 vNext artifacts、native brief 和 workbench" in html
    assert "运行时生成官方事件底账与市场连接观察" in html
    assert "news_event_data_links.json" in html
    assert "最新新闻产物" in html
    assert "--enable-news" in html
    assert "Trendonify sidecar 标记为信任" in html
    assert "勾选只影响 sidecar 输出的信任标记" in html
    assert "采集 Trendonify" in html
    assert "单独采集事件底账" in html
    assert "src/news_event_ledger.py" in html
    assert "运行完整报告" in html
    assert "运行日志 / 健康 / 安全" in html
    assert "一键运行安全方案" in html
    assert "它会先保存人工数据，再串联生成报告" in html
    assert 'id="runNow"' in html
    assert "const controlOrigin" in html
    assert "fetch(`${controlOrigin}/run`" in html
    assert "fetch(`${controlOrigin}/manual-data`" in html
    assert "src/console_run_all.py" in html
    assert "data_collected_v9_20260509.json" in html
    assert "dataJsonWarning" in html
    assert "mode === 'analyze_existing'" in html
    assert "mode !== 'collect_data'" not in html
    assert "base.concat(['--collect-only']).join(' ')" in html
    assert "document.getElementById('historicalDateMode').checked && dataDate.value" in html
    assert "control service" in html
    assert "news_event_ledger.py" in html
    assert "数据源健康" in html
    assert "WorldPERatio" in html
    assert "Damodaran ERPbymonth.xlsx" in html
    assert "生成运行命令" in html
    assert "交互工作台模块" in html
    assert "价格技术" in html
    assert "波动信用" in html
    assert "利率估值" in html
    assert "广度集中度" in html
    assert "流动性" in html
    assert "--modules price_technical,volatility_credit,rates_valuation,breadth_concentration,liquidity" in html
    assert "打开最新报告" in html
    assert "data-artifact-path" in html
    assert "function artifactUrl(path)" in html
    assert "latest-product" in html
    assert "startJobAutoRefresh" in html
    assert "保存人工数据" in html
    assert "vnext_research_ui_brief_20260505.html" in html
    assert "manual_data.local.json" in html
    assert "runCommandPreview" in html
    assert "workbenchCommandPreview" in html
    assert "buildManualPayload" in html
    assert "valuation.value.ForwardPE = fields.forward_pe" in html
    assert "valuation.value.FCFYield = fields.fcf_yield" in html
    assert "valuation.value.PCF_TTM = fields.pcf" in html

    console_data = re.search(r'<script type="application/json" id="console-data">(.*?)</script>', html, re.S)
    assert console_data is not None
    assert "&quot;" not in console_data.group(1)
    parsed = json.loads(console_data.group(1))
    assert "manualTemplate" in parsed
    assert "initialManualData" in parsed
    assert "manual_data.local.json" in parsed["manualPath"]
    assert parsed["latestDataJson"].endswith("data_collected_v9_20260509.json")
    assert parsed["latestDataJsonMeta"]["data_date"] == "2026-05-09"
