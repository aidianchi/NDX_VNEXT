import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from research_console import ResearchConsoleGenerator


def test_research_console_generates_first_screen_controls(tmp_path: Path):
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir()
    (reports_dir / "vnext_research_ui_brief_20260505.html").write_text("<html></html>", encoding="utf-8")

    generator = ResearchConsoleGenerator(reports_dir=reports_dir)
    output = Path(generator.run(output_path=tmp_path / "console.html"))
    html = output.read_text(encoding="utf-8")

    assert "NDX vNext 研究控制台" in html
    assert "运行对象与日期" in html
    assert "人工 / Wind 数据" in html
    assert "当前 PE" in html
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
    assert "视觉回归" in html
    assert "deepseek-v4-flash" in html
    assert "deepseek-v4-pro" in html
    assert "自定义顺序" in html
    assert "数据源 / 功能开关" in html
    assert "旧版 HTML 仅保留兼容入口" in html
    assert "不生成旧版 HTML" in html
    assert "旧版 HTML 是过渡期兼容产物" in html
    assert "生成官方事件底账" in html
    assert "--enable-news" in html
    assert "Trendonify 暂缓" in html
    assert "L5 默认预设" in html
    assert "输出与工作台" in html
    assert "运行日志 / 健康 / 安全" in html
    assert "一键运行安全方案" in html
    assert "运行按钮会调用本机 127.0.0.1 的 vNext control service" in html
    assert 'id="runNow"' in html
    assert "fetch('http://127.0.0.1:8765/run'" in html
    assert "control service" in html
    assert "news_event_ledger" not in html
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
    assert "保存人工模板" in html
    assert "vnext_research_ui_brief_20260505.html" in html
    assert "manual_data.local.json" in html
    assert "runCommandPreview" in html
    assert "workbenchCommandPreview" in html
    assert "buildManualPayload" in html

    console_data = re.search(r'<script type="application/json" id="console-data">(.*?)</script>', html, re.S)
    assert console_data is not None
    assert "&quot;" not in console_data.group(1)
    parsed = json.loads(console_data.group(1))
    assert "manualTemplate" in parsed
    assert "manual_data.local.json" in parsed["manualPath"]
