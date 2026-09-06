"""T71 第二批（体检 #3 网页噪音 + #4 黑话治理）行为锁定测试。

对象 run：t70_glm_check_20260902 与 20260905_171025 的实测病灶——
  #3 事件卡摘录 24-62% 是导航/广告/行情挂件，两张卡躺着两个互相矛盾的比特币报价；
     根源=清洗器跳过名单缺 <aside>、摘录取整页头部 8000 字符恰好落在商业站噪音区；
  #4 黑话传染：prompt 高频无解释内部词直出进输出（「法典」L2 输出直出 7 次、
     「三明治口径」被原样回抄、「底账」「门脸徽章」进终稿）。
修法边界（老板硬约束）：只动模型可见的叫法与清洗行为；宪法字段、检查名、机制一根不动。
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from news_event_ledger import _extract_readable_text

PROMPT_DIR = Path(__file__).resolve().parents[1] / "src" / "agent_analysis" / "prompts"
SRC_DIR = Path(__file__).resolve().parents[1] / "src"


# ── #3 清洗器：aside 行情挂件跳过 + 正文容器优先 ──


def test_parser_skips_aside_market_widgets():
    html = (
        "<html><body>"
        "<nav>首页 财经 股票 导航栏目</nav>"
        '<aside class="market-widget">比特币 77,132.93 63,925.97 行情挂件报价</aside>'
        "<article><p>英伟达财报超预期，数据中心收入创纪录，管理层上调全年指引。"
        "公司同时宣布新的股票回购计划，并强调资本开支纪律与供给约束下的定价权。"
        "数据中心与汽车业务双双增长，自由现金流创同期新高，云厂商的算力订单能见度延伸到明年。"
        "分析人士认为，供给瓶颈缓解与订单积压共同支撑了这份指引的可信度，后续关注毛利率走向与库存周转。</p></article>"
        "<footer>© 2026 版权所有 免责声明</footer>"
        "</body></html>"
    )
    out = _extract_readable_text(html)
    assert "77,132.93" not in out, "aside 行情挂件必须整体跳过（体检实锤两个矛盾报价进摘录）"
    assert "导航栏目" not in out
    assert "免责声明" not in out
    assert "英伟达财报超预期" in out


def test_excerpt_prefers_article_body_over_page_head_noise():
    noise = "导航推荐登录订阅广告" * 60
    body = "真正的正文内容，管理层上调全年指引并给出资本开支纪律。" * 40
    html = f"<html><body><div class='chrome'>{noise}</div><article><p>{body}</p></article></body></html>"
    out = _extract_readable_text(html)
    assert out.startswith("真正的正文内容"), "页面有足量 <article> 正文时，摘录必须从正文开始，不再被页头噪音占满"
    assert "导航推荐" not in out[:200]


def test_excerpt_falls_back_when_article_too_thin():
    noise = "页头噪音内容" * 40
    html = f"<html><body><div>{noise}</div><article><p>只有一句话的薄正文。</p></article></body></html>"
    out = _extract_readable_text(html)
    assert "只有一句话的薄正文" in out, "article 内容太薄时回退整页，正文不得丢失"
    assert "页头噪音内容" in out, "回退路径下保留原有整页行为"


# ── #4 黑话治理：模型可见面不出现已治理黑话 ──


def test_prompts_do_not_use_retired_jargon():
    offenders = []
    for path in PROMPT_DIR.rglob("*.md"):
        text = path.read_text(encoding="utf-8")
        for term in ("底账", "门脸徽章"):
            if term in text:
                offenders.append(f"{path.name}:{term}")
    assert offenders == [], f"提示词里不得再出现已治理黑话：{offenders}"


def test_canon_model_hints_do_not_say_fadian():
    canon_src = (SRC_DIR / "agent_analysis" / "deep_research_canon.py").read_text(encoding="utf-8")
    assert "法典值" not in canon_src, "canon 装配提示是 L1-L5 的直出传染源（L2 输出直出 7 次），改叫判读标准"
    assert "判读标准" in canon_src, "替换词必须落位"


def test_bridge_event_discipline_header_is_plain():
    orch_src = (SRC_DIR / "agent_analysis" / "orchestrator.py").read_text(encoding="utf-8")
    assert "事件纪律（三明治口径" not in orch_src, "段标题黑话「三明治口径」被模型原样回抄，改为直述宪法隔离"
    assert "事件纪律（新闻事件按宪法不进数据分析层" in orch_src, "替换标题必须落位"
