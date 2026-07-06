import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from research_console import ResearchConsoleGenerator


def test_research_console_generates_simple_launcher(tmp_path: Path, monkeypatch):
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir()
    (reports_dir / "vnext_research_ui_brief_20260505.html").write_text("<html></html>", encoding="utf-8")
    (reports_dir / "vnext_workbench_20260505.html").write_text("<html></html>", encoding="utf-8")
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
    assert "console_simple_launcher_v1" in html
    assert "运行模式" in html
    assert "纯数据报告" in html
    assert "事件新闻报告" in html
    assert "综合报告" in html
    assert "开始综合报告" in html
    assert 'id="runStatus" class="run-status is-idle" role="button" tabindex="0"' in html
    assert "点击刷新任务状态" in html
    assert "function refreshStatusFromBox()" in html
    assert "runStatus.addEventListener('click'" in html
    assert "已刷新" in html
    assert "是否回测" in html
    assert 'id="backtestMode"' in html
    assert 'id="backtestDate"' in html
    assert "综合报告会同时生成纯数据报告和事件新闻报告" in html
    assert "事件材料不进入 L1-L5 主证据" in html
    assert "末次数据" in html
    assert "data_collected_v9_20260509.json" in html
    assert "打开最新报告" in html
    assert "打开最新 workbench" in html
    assert "打开最新日志" in html
    assert "高级设置" in html
    assert "Wind L4 主锚" in html
    assert "NDX_DISABLE_WIND_L4" in html
    assert "人工覆盖：未启用" in html
    assert 'id="manualActive"' in html
    assert "开发者命令" in html
    assert "src/console_run_all.py" in html
    assert "src/main.py" in html
    assert "--event-only" in html
    assert "--data-json" in html
    assert "--enable-news" in html
    assert "fetch(`${controlOrigin}/run`" in html
    assert "env_overrides: envOverrides()" in html
    assert "latest-product" in html
    assert "function artifactUrl(path)" in html

    assert "只生成 brief" not in html
    assert "只生成 workbench" not in html
    assert "查看日志" not in html
    assert "采集 Trendonify" not in html
    assert "Trendonify sidecar 标记为信任" not in html
    assert "单独采集事件底账" not in html
    assert "高级 JSON 预览" not in html
    assert "数据源健康" not in html

    console_data = re.search(r'<script type="application/json" id="console-data">(.*?)</script>', html, re.S)
    assert console_data is not None
    assert "&quot;" not in console_data.group(1)
    parsed = json.loads(console_data.group(1))
    assert "manualTemplate" in parsed
    assert "initialManualData" in parsed
    assert "manual_data.local.json" in parsed["manualPath"]
    assert parsed["latestDataJson"].endswith("data_collected_v9_20260509.json")
    assert parsed["latestDataJsonMeta"]["name"] == "data_collected_v9_20260509.json"
    assert parsed["latestDataJsonMeta"]["data_date"] == "2026-05-09"
    assert parsed["latestDataJsonMeta"]["is_backtest"] is False
