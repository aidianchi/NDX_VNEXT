import os
import json
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from browser_sidecar import collect_trendonify_valuation_sidecar


def test_trendonify_browser_sidecar_parses_multi_window_percentiles():
    page_text = """
Nasdaq 100 Forward PE Ratio
Last Updated: May 08, 2026
Forward PE Ratio
23.73
Valuation Percentile Rank
57.5%
Historical P/E Comparison
Period Median PE Percentile Valuation
1 Year 24.88 33.3% Undervalued
5 Years 24.73 40% Undervalued
10 Years 22.82 57.5% Fair Value
20 Years 20.27 71.2% Overvalued
Since Jun 2002 21.24 63.5% Overvalued
"""

    def fake_runner(args, timeout):
        if args[:3] == ["bb-browser", "eval", "document.body ? document.body.innerText : ''"]:
            return subprocess.CompletedProcess(args, 0, stdout=json.dumps({"data": {"result": page_text}}), stderr="")
        return subprocess.CompletedProcess(args, 0, stdout="{}", stderr="")

    payload = collect_trendonify_valuation_sidecar(trusted=True, wait_seconds=0, runner=fake_runner)

    assert payload["schema_version"] == "browser_sidecar_v1"
    assert payload["policy"]["main_chain_rule"].startswith("The main L4 requests path")
    assert len(payload["pages"]) == 2
    assert payload["pages"][0]["requires_user_trust"] is True
    assert payload["pages"][0]["user_trusted"] is True
    forward = next(page for page in payload["pages"] if page["page_type"] == "forward_pe")
    assert forward["parsed"]["percentile_10y"] == 57.5
    assert forward["parsed"]["historical_percentiles"]["5y"]["percentile"] == 40.0
