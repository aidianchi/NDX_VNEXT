import os
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
    assert "人工 / Wind 输入" in html
    assert "deepseek-v4-flash" in html
    assert "deepseek-v4-pro" in html
    assert "数据源健康" in html
    assert "WorldPERatio" in html
    assert "Damodaran ERPbymonth.xlsx" in html
    assert "生成运行命令" in html
    assert "打开最新报告" in html
    assert "保存人工模板" in html
    assert "vnext_research_ui_brief_20260505.html" in html
    assert "manual_data.local.json" in html
    assert "runCommandPreview" in html
