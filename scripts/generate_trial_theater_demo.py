from __future__ import annotations

import html
import json
import re
from pathlib import Path
from typing import Any, Iterable, Mapping


ROOT = Path(__file__).resolve().parents[1]
EVENT_JSON = ROOT / "output/analysis/vnext/20260704_184659/event_mechanism_report.json"
CHARTBOOK_HTML = ROOT / "output/reports/vnext_brief_20260701_1319.html"
OUTPUT_HTML = ROOT / "output/reports/event_mechanism_trial_theater_demo_20260704.html"


def esc(value: Any) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def compact(value: Any, limit: int = 180) -> str:
    text = re.sub(r"\s+", " ", "" if value is None else str(value)).strip()
    if len(text) <= limit:
        return text
    for mark in "。；;，,":
        pos = text.rfind(mark, 0, limit)
        if pos > 40:
            return text[: pos + 1]
    return text[: limit - 1].rstrip() + "..."


def label_confidence(value: Any) -> str:
    labels = {"high": "高", "medium": "中", "low": "低", "very_low": "很低"}
    return labels.get(str(value), str(value or "未知"))


def take(items: Iterable[Any], n: int) -> list[Any]:
    result = []
    for item in items:
        result.append(item)
        if len(result) >= n:
            break
    return result


def load_report() -> dict[str, Any]:
    return json.loads(EVENT_JSON.read_text(encoding="utf-8"))


def extract_chart_svgs() -> tuple[str, list[str]]:
    source = CHARTBOOK_HTML.read_text(encoding="utf-8")
    line_match = re.search(r'<svg class="line-chart[\s\S]*?</svg>', source)
    sparks = re.findall(r'<svg class="spark[\s\S]*?</svg>', source)
    return (line_match.group(0) if line_match else ""), take(sparks, 8)


def render_chips(values: Iterable[Any], class_name: str = "pill") -> str:
    return "".join(f'<span class="{class_name}">{esc(value)}</span>' for value in values if value)


def render_news_buttons(card_ids: list[str], cards_by_id: Mapping[str, Mapping[str, Any]]) -> str:
    buttons = []
    for card_id in card_ids[:6]:
        card = cards_by_id.get(card_id)
        if not card:
            continue
        band = {
            "core": "核心证词",
            "supporting": "辅助证词",
            "background": "背景旁证",
        }.get(str(card.get("relevance_band")), "证词")
        buttons.append(
            f"""
            <button class="evidence-tile" type="button" data-news-id="{esc(card_id)}">
              <span>{esc(band)} / {esc(label_confidence(card.get("confidence")))}</span>
              <b>{esc(card.get("title"))}</b>
              <small>{esc(compact(card.get("one_line_summary"), 92))}</small>
            </button>
            """
        )
    return "\n".join(buttons)


def render_mainlines(report: Mapping[str, Any]) -> str:
    cards_by_id = {card["news_id"]: card for card in report.get("news_cards", [])}
    roles = [
        ("prosecution", "控方：增长叙事", "gold"),
        ("defense", "辩方：宏观约束", "red"),
        ("jury", "陪审团：指数结构", "cyan"),
        ("gallery", "旁听席：背景噪音", "dim"),
    ]
    rendered = []
    for index, mainline in enumerate(report.get("mainlines", []), start=1):
        role_key, role_label, tone = roles[index - 1] if index <= len(roles) else roles[-1]
        rendered.append(
            f"""
            <article class="case-card case-card--{esc(tone)}" id="case-{index}" data-role="{esc(role_key)}">
              <div class="case-number">ACT {index:02d}</div>
              <div class="case-body">
                <p class="micro-label">{esc(role_label)}</p>
                <h2>{esc(mainline.get("title"))}</h2>
                <p class="case-summary">{esc(mainline.get("plain_summary"))}</p>
                <div class="argument-grid">
                  <section>
                    <h3>可以陈述</h3>
                    <p>{esc(mainline.get("can_say"))}</p>
                  </section>
                  <section>
                    <h3>禁止越权</h3>
                    <p>{esc(mainline.get("cannot_say"))}</p>
                  </section>
                </div>
                <div class="evidence-grid">
                  {render_news_buttons(mainline.get("news_card_ids", []), cards_by_id)}
                </div>
              </div>
              <aside class="case-meter">
                <b>{esc(mainline.get("core_news_count", 0))}</b>
                <span>条核心材料</span>
                <i>{esc(mainline.get("missing_evidence_count", 0))} 个缺口</i>
              </aside>
            </article>
            """
        )
    return "\n".join(rendered)


def render_event_cards(report: Mapping[str, Any]) -> str:
    rendered = []
    for index, card in enumerate(report.get("event_research_cards", []), start=1):
        counter = card.get("counterevidence") or []
        rendered.append(
            f"""
            <article class="testimony">
              <div class="testimony-head">
                <span>证人 {index:02d}</span>
                <b>{esc(card.get("importance"))} / 把握 {esc(label_confidence(card.get("confidence")))}</b>
              </div>
              <h3>{esc(card.get("title"))}</h3>
              <p><strong>最小事实：</strong>{esc(compact(card.get("minimum_fact"), 230))}</p>
              <p><strong>可能影响：</strong>{esc(card.get("possible_impact"))}</p>
              <ul>{''.join(f'<li>{esc(item)}</li>' for item in counter)}</ul>
            </article>
            """
        )
    return "\n".join(rendered)


def render_questions(report: Mapping[str, Any]) -> str:
    rendered = []
    for index, question in enumerate(report.get("cross_layer_questions", []), start=1):
        checks = question.get("requested_checks") or []
        rendered.append(
            f"""
            <article class="cross-card">
              <span>追问 {index:02d}</span>
              <h3>{esc(question.get("question"))}</h3>
              <p>{esc(question.get("why_it_matters"))}</p>
              <div class="checklist">{render_chips(checks, "mini-pill")}</div>
            </article>
            """
        )
    return "\n".join(rendered)


def render_ledger(report: Mapping[str, Any]) -> str:
    rows = []
    for item in report.get("claim_permission_ledger", [])[:24]:
        rows.append(
            f"""
            <tr>
              <td>{esc(compact(item.get("claim"), 92))}</td>
              <td>{esc(item.get("nature"))}</td>
              <td>{esc(compact(item.get("can_support"), 110))}</td>
              <td>{esc(compact(item.get("cannot_support"), 120))}</td>
              <td>{esc(item.get("status"))}</td>
            </tr>
            """
        )
    return "\n".join(rows)


def render_chart_wall(line_chart: str, sparks: list[str]) -> str:
    labels = [
        ("价格趋势", "趋势只是案情背景，不等于胜诉。"),
        ("ERP 月度路径", "风险补偿是尺度，不是单独裁决。"),
        ("估值分位", "高分位提醒安全垫薄。"),
        ("收益差距", "需要和利率一起看。"),
        ("RSI / 动量", "技术读数只说明执行环境。"),
        ("成交量 / 资金", "资金动作不能绕过证据权限。"),
    ]
    cards = []
    for index, svg in enumerate(sparks[:6]):
        title, note = labels[index]
        cards.append(
            f"""
            <article class="chart-shard">
              <div><span>证据光幕 {index + 1:02d}</span><b>{esc(title)}</b></div>
              {svg}
              <p>{esc(note)}</p>
            </article>
            """
        )
    return f"""
      <section class="chart-stage">
        <div class="chart-hero">
          <div>
            <p class="micro-label">核心图册被传唤出庭</p>
            <h2>图表不是结论，是证词的照明。</h2>
            <p>这里保留 vNext 图册里的趋势图，把它们改造成审判舞台上的证据光幕。它们只帮助读者看清张力，不替新闻越权发言。</p>
          </div>
          <div class="large-chart">{line_chart}</div>
        </div>
        <div class="chart-shards">{''.join(cards)}</div>
      </section>
    """


def build_html() -> str:
    report = load_report()
    line_chart, sparks = extract_chart_svgs()
    headline = report.get("headline_judgment", {})
    delivery = report.get("delivery_to_integrated_report", {})
    metrics = {
        "核心事件": len(report.get("event_research_cards", [])),
        "待追问": len(report.get("cross_layer_questions", [])),
        "新闻材料": len(report.get("news_cards", [])),
        "可升主证据": 0,
    }
    news_json = json.dumps({card["news_id"]: card for card in report.get("news_cards", [])}, ensure_ascii=False)
    watchlist = "".join(f"<li>{esc(item)}</li>" for item in delivery.get("watchlist", [])[:10])
    risk_pills = render_chips(delivery.get("must_preserve_risks", []), "risk-pill")

    template = r"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>NDX 新闻事件研报 · 审判剧场 Demo</title>
<style>
:root{
  --void:#050504;
  --ink:#fff9e8;
  --muted:#b9a889;
  --dim:#756b5f;
  --line:rgba(255,226,154,.22);
  --gold:#f8c75a;
  --amber:#ff8f3d;
  --red:#ff4d42;
  --cyan:#5ce7ff;
  --green:#71f2a4;
  --panel:rgba(19,16,13,.74);
  --panel-strong:rgba(37,28,17,.82);
  --shadow:0 30px 90px rgba(0,0,0,.55);
}
*{box-sizing:border-box}
html{scroll-behavior:smooth}
body{
  margin:0;
  color:var(--ink);
  background:
    radial-gradient(circle at 18% 8%, rgba(255,143,61,.18), transparent 34%),
    radial-gradient(circle at 78% 12%, rgba(92,231,255,.13), transparent 28%),
    linear-gradient(180deg,#050504 0%,#120b08 42%,#040404 100%);
  font-family:"Songti SC","Noto Serif SC",Georgia,serif;
  line-height:1.65;
  overflow-x:hidden;
}
body::before{
  content:"";
  position:fixed;
  inset:0;
  z-index:-3;
  background-image:
    linear-gradient(rgba(255,255,255,.035) 1px, transparent 1px),
    linear-gradient(90deg, rgba(255,255,255,.026) 1px, transparent 1px);
  background-size:72px 72px;
  mask-image:linear-gradient(180deg,rgba(0,0,0,.8),transparent 88%);
}
body::after{
  content:"";
  position:fixed;
  inset:0;
  z-index:-1;
  pointer-events:none;
  background:
    linear-gradient(90deg, transparent 0 8%, rgba(248,199,90,.08) 12%, transparent 18% 82%, rgba(92,231,255,.07) 88%, transparent 94%),
    radial-gradient(ellipse at 50% 100%, rgba(248,199,90,.13), transparent 50%);
  mix-blend-mode:screen;
}
canvas#stageDust{position:fixed;inset:0;z-index:-2;pointer-events:none;opacity:.52}
a{color:inherit}
.page{width:min(1440px,100%);margin:0 auto}
.hero{
  min-height:100vh;
  display:grid;
  grid-template-rows:auto 1fr auto;
  padding:26px clamp(18px,4vw,64px) 42px;
  position:relative;
}
.topline,.nav{
  display:flex;
  align-items:center;
  justify-content:space-between;
  gap:14px;
  color:var(--muted);
  font:12px/1.3 Menlo,Consolas,monospace;
  letter-spacing:.08em;
  text-transform:uppercase;
}
.topline{border-bottom:1px solid var(--line);padding-bottom:14px}
.topline strong{color:var(--gold)}
.hero-grid{
  display:grid;
  grid-template-columns:minmax(0,1.05fr) minmax(320px,.72fr);
  gap:clamp(24px,4vw,58px);
  align-items:center;
  padding:8vh 0 6vh;
}
.micro-label{
  margin:0 0 12px;
  color:var(--gold);
  font:700 12px/1.2 Menlo,Consolas,monospace;
  letter-spacing:.16em;
  text-transform:uppercase;
}
h1,h2,h3,p{margin-top:0}
h1{
  font-family:"Bodoni 72","Didot","Songti SC",serif;
  font-size:clamp(54px,8vw,132px);
  line-height:.88;
  max-width:980px;
  margin-bottom:26px;
  letter-spacing:-.035em;
  text-shadow:0 0 34px rgba(248,199,90,.17);
}
h2{font-size:clamp(30px,4vw,58px);line-height:1.02;letter-spacing:-.025em}
h3{font-size:22px;line-height:1.22}
.lead{
  max-width:760px;
  color:#eadbbd;
  font-size:clamp(18px,2.1vw,28px);
  line-height:1.48;
}
.verdict{
  position:relative;
  min-height:480px;
  padding:28px;
  border:1px solid rgba(248,199,90,.36);
  background:
    linear-gradient(145deg,rgba(248,199,90,.12),rgba(255,77,66,.05) 42%,rgba(5,5,4,.72)),
    var(--panel);
  box-shadow:var(--shadow), inset 0 0 80px rgba(248,199,90,.08);
  overflow:hidden;
  border-radius:8px;
}
.verdict::before{
  content:"";
  position:absolute;
  inset:16px;
  border:1px solid rgba(248,199,90,.16);
  pointer-events:none;
}
.verdict h2{font-size:42px;margin-bottom:18px}
.verdict p{position:relative;font-size:20px;color:#f6e9ca}
.seal{
  width:180px;
  aspect-ratio:1;
  display:grid;
  place-items:center;
  margin:0 0 26px auto;
  border-radius:50%;
  color:#130d06;
  background:radial-gradient(circle,#ffe7a1 0 34%,#f8c75a 35% 55%,#7b311a 56% 57%,#f8c75a 58% 100%);
  box-shadow:0 0 50px rgba(248,199,90,.45);
  transform:rotate(-9deg);
  font:900 26px/1 Menlo,Consolas,monospace;
}
.pills{display:flex;flex-wrap:wrap;gap:9px;margin-top:20px}
.pill,.risk-pill,.mini-pill{
  display:inline-flex;
  align-items:center;
  border:1px solid rgba(248,199,90,.28);
  color:#ffe7a1;
  background:rgba(248,199,90,.08);
  padding:7px 10px;
  border-radius:999px;
  font:12px/1.2 Menlo,Consolas,monospace;
}
.risk-pill{border-color:rgba(255,77,66,.45);color:#ffc4be;background:rgba(255,77,66,.1)}
.mini-pill{font-size:11px;border-color:rgba(92,231,255,.3);color:#c8f7ff;background:rgba(92,231,255,.08)}
.metrics{
  display:grid;
  grid-template-columns:repeat(4,1fr);
  gap:1px;
  border:1px solid var(--line);
  background:var(--line);
  box-shadow:0 16px 60px rgba(0,0,0,.35);
}
.metric{padding:18px;background:rgba(9,8,7,.78)}
.metric b{display:block;font:700 40px/1 Menlo,Consolas,monospace;color:var(--gold)}
.metric span{color:var(--muted);font-size:13px}
.nav{
  position:sticky;
  top:0;
  z-index:10;
  justify-content:center;
  flex-wrap:wrap;
  padding:12px clamp(18px,4vw,64px);
  border-top:1px solid var(--line);
  border-bottom:1px solid var(--line);
  background:rgba(5,5,4,.84);
  backdrop-filter:blur(14px);
}
.nav a{
  text-decoration:none;
  color:#e9d7b8;
  border:1px solid transparent;
  padding:8px 10px;
  border-radius:999px;
}
.nav a:hover,.nav a:focus-visible{border-color:rgba(248,199,90,.45);outline:none;color:#fff}
.section{
  padding:86px clamp(18px,4vw,64px);
  border-top:1px solid rgba(248,199,90,.12);
}
.section-head{display:grid;grid-template-columns:minmax(0,.78fr) minmax(280px,.45fr);gap:30px;align-items:end;margin-bottom:34px}
.section-head p{color:#d7c6a8;font-size:18px}
.case-stack{display:grid;gap:26px}
.case-card{
  position:relative;
  display:grid;
  grid-template-columns:88px minmax(0,1fr) 180px;
  gap:22px;
  align-items:stretch;
  padding:22px;
  border:1px solid rgba(248,199,90,.24);
  background:linear-gradient(135deg,rgba(255,255,255,.04),rgba(255,255,255,.01)),var(--panel);
  border-radius:8px;
  box-shadow:0 24px 70px rgba(0,0,0,.34);
  overflow:hidden;
}
.case-card::before{content:"";position:absolute;inset:0 0 auto;height:3px;background:var(--gold)}
.case-card--red::before{background:var(--red)}
.case-card--cyan::before{background:var(--cyan)}
.case-card--dim::before{background:var(--dim)}
.case-number{
  writing-mode:vertical-rl;
  text-orientation:mixed;
  color:var(--gold);
  font:700 15px/1 Menlo,Consolas,monospace;
  letter-spacing:.14em;
  border-right:1px solid var(--line);
  padding-right:18px;
}
.case-body h2{margin-bottom:14px}
.case-summary{font-size:18px;color:#eadbbd}
.argument-grid{
  display:grid;
  grid-template-columns:1fr 1fr;
  gap:14px;
  margin:20px 0;
}
.argument-grid section{
  border-left:2px solid rgba(248,199,90,.55);
  padding:8px 0 8px 14px;
}
.argument-grid section:nth-child(2){border-left-color:rgba(255,77,66,.7)}
.argument-grid h3{margin:0 0 6px;font-size:15px;color:#ffe7a1}
.argument-grid p{color:#d7c6a8;margin:0}
.evidence-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px}
.evidence-tile{
  appearance:none;
  min-height:158px;
  text-align:left;
  color:var(--ink);
  background:rgba(255,248,225,.055);
  border:1px solid rgba(248,199,90,.22);
  border-radius:6px;
  padding:14px;
  cursor:pointer;
  font:inherit;
  transition:transform .18s ease,border-color .18s ease,background .18s ease;
}
.evidence-tile:hover,.evidence-tile:focus-visible{
  transform:translateY(-3px);
  border-color:rgba(248,199,90,.72);
  background:rgba(248,199,90,.11);
  outline:none;
}
.evidence-tile span{display:block;color:var(--gold);font:11px/1.2 Menlo,Consolas,monospace;letter-spacing:.08em;text-transform:uppercase;margin-bottom:10px}
.evidence-tile b{display:block;font-size:15px;line-height:1.34;margin-bottom:9px}
.evidence-tile small{display:block;color:#cbb99b;font-size:13px;line-height:1.45}
.case-meter{
  display:flex;
  flex-direction:column;
  justify-content:center;
  align-items:flex-start;
  border-left:1px solid var(--line);
  padding-left:22px;
}
.case-meter b{font:700 58px/1 Menlo,Consolas,monospace;color:var(--gold)}
.case-meter span{color:#eadbbd}
.case-meter i{font-style:normal;color:var(--red);font:12px/1.2 Menlo,Consolas,monospace;margin-top:12px}
.chart-stage{
  border:1px solid rgba(92,231,255,.22);
  border-radius:8px;
  padding:24px;
  background:linear-gradient(180deg,rgba(92,231,255,.08),rgba(248,199,90,.04)),rgba(5,8,9,.78);
  box-shadow:var(--shadow);
}
.chart-hero{
  display:grid;
  grid-template-columns:.55fr 1fr;
  gap:22px;
  align-items:center;
}
.chart-hero p{color:#d7c6a8}
.large-chart{
  min-height:280px;
  border:1px solid rgba(92,231,255,.22);
  border-radius:8px;
  padding:16px;
  background:radial-gradient(circle at 50% 20%,rgba(92,231,255,.12),transparent 52%),rgba(0,0,0,.32);
  overflow:hidden;
}
.chart-shards{
  display:grid;
  grid-template-columns:repeat(3,minmax(0,1fr));
  gap:14px;
  margin-top:16px;
}
.chart-shard{
  border:1px solid rgba(248,199,90,.18);
  background:rgba(255,255,255,.035);
  border-radius:8px;
  padding:14px;
  min-width:0;
}
.chart-shard div:first-child{display:flex;justify-content:space-between;gap:12px;margin-bottom:8px}
.chart-shard span{font:11px/1.2 Menlo,Consolas,monospace;color:var(--cyan)}
.chart-shard b{font-size:15px;color:#ffe7a1}
.chart-shard p{margin:8px 0 0;color:#cbb99b;font-size:13px}
.spark,.line-chart{width:100%;height:auto;display:block;overflow:visible}
.spark path,.line-chart path{fill:none;stroke:var(--gold);stroke-width:3;stroke-linecap:round;stroke-linejoin:round;filter:drop-shadow(0 0 8px rgba(248,199,90,.35))}
.spark.down path,.line-chart .series-rate{stroke:var(--red)}
.line-chart .series-erp{stroke:var(--cyan)}
.line-chart .series-return{stroke:var(--gold)}
.spark text,.line-chart text{fill:#d8c5a2;font:12px Menlo,Consolas,monospace}
.spark line,.line-chart line,.line-chart rect{stroke:rgba(255,255,255,.13);fill:transparent}
.theater-grid{
  display:grid;
  grid-template-columns:repeat(2,minmax(0,1fr));
  gap:18px;
}
.testimony,.cross-card{
  border:1px solid rgba(248,199,90,.2);
  background:rgba(19,16,13,.72);
  border-radius:8px;
  padding:18px;
}
.testimony-head{
  display:flex;
  justify-content:space-between;
  gap:12px;
  color:var(--muted);
  font:12px/1.2 Menlo,Consolas,monospace;
  margin-bottom:12px;
}
.testimony h3,.cross-card h3{color:#ffe7a1}
.testimony p,.testimony li,.cross-card p{color:#d7c6a8}
.testimony ul{padding-left:18px;margin-bottom:0}
.cross-card{
  min-height:230px;
  border-color:rgba(92,231,255,.22);
  background:rgba(7,18,20,.62);
}
.cross-card span{display:block;color:var(--cyan);font:12px/1.2 Menlo,Consolas,monospace;margin-bottom:10px}
.checklist{display:flex;flex-wrap:wrap;gap:8px;margin-top:16px}
.ledger-wrap{
  max-height:620px;
  overflow:auto;
  border:1px solid rgba(248,199,90,.2);
  border-radius:8px;
  background:rgba(8,7,6,.72);
}
table{width:100%;border-collapse:collapse;font-size:14px}
th,td{border-bottom:1px solid rgba(248,199,90,.14);padding:12px;text-align:left;vertical-align:top}
th{position:sticky;top:0;background:#15100b;color:#ffe7a1;font:12px/1.2 Menlo,Consolas,monospace;z-index:1}
td{color:#d7c6a8}
.finale{
  min-height:84vh;
  display:grid;
  grid-template-columns:minmax(0,1fr) minmax(320px,.55fr);
  gap:34px;
  align-items:center;
  padding-bottom:100px;
}
.final-verdict{
  border:1px solid rgba(248,199,90,.42);
  border-radius:8px;
  background:linear-gradient(145deg,rgba(248,199,90,.14),rgba(255,77,66,.08),rgba(7,7,6,.86));
  padding:32px;
  box-shadow:var(--shadow);
}
.final-verdict h2{font-size:clamp(40px,6vw,92px)}
.final-verdict p{font-size:22px;color:#f5e4c6}
.watchlist{
  border:1px solid rgba(92,231,255,.22);
  border-radius:8px;
  padding:24px;
  background:rgba(7,18,20,.68);
}
.watchlist li{margin-bottom:10px;color:#d7c6a8}
.modal-backdrop{
  position:fixed;
  inset:0;
  z-index:50;
  display:none;
  align-items:center;
  justify-content:center;
  padding:18px;
  background:rgba(0,0,0,.72);
  backdrop-filter:blur(12px);
}
.modal-backdrop.open{display:flex}
.modal{
  width:min(920px,100%);
  max-height:88vh;
  overflow:auto;
  border:1px solid rgba(248,199,90,.5);
  border-radius:8px;
  background:#100c08;
  box-shadow:0 40px 140px rgba(0,0,0,.75);
  padding:24px;
}
.modal-head{display:flex;justify-content:space-between;gap:18px;border-bottom:1px solid var(--line);padding-bottom:14px;margin-bottom:18px}
.modal-close{
  appearance:none;
  width:40px;
  height:40px;
  border:1px solid rgba(248,199,90,.42);
  border-radius:6px;
  background:rgba(248,199,90,.08);
  color:var(--ink);
  font-size:24px;
  cursor:pointer;
}
.detail-grid{display:grid;grid-template-columns:140px 1fr;gap:10px 16px}
.detail-grid b{color:var(--gold);font:12px/1.2 Menlo,Consolas,monospace}
.detail-grid span{color:#decdae}
@media (max-width:980px){
  .hero-grid,.section-head,.chart-hero,.finale{grid-template-columns:1fr}
  .metrics{grid-template-columns:repeat(2,1fr)}
  .case-card{grid-template-columns:1fr}
  .case-number{writing-mode:initial;border-right:0;border-bottom:1px solid var(--line);padding:0 0 12px}
  .case-meter{border-left:0;border-top:1px solid var(--line);padding:16px 0 0}
  .evidence-grid,.chart-shards,.theater-grid{grid-template-columns:1fr}
}
@media (max-width:560px){
  .hero{padding-left:16px;padding-right:16px}
  .section{padding-left:16px;padding-right:16px}
  .metrics{grid-template-columns:1fr}
  .argument-grid{grid-template-columns:1fr}
  .detail-grid{grid-template-columns:1fr}
}
</style>
</head>
<body>
<canvas id="stageDust" aria-hidden="true"></canvas>
<main class="page">
  <header class="hero" id="top">
    <div class="topline">
      <strong>NDX TRIAL THEATER</strong>
      <span>正式第二层报告 · 非主证据</span>
      <span>__GENERATED_AT__</span>
    </div>
    <section class="hero-grid">
      <div>
        <p class="micro-label">案由 / 市场叙事是否有资格发言</p>
        <h1>今天市场在交易什么故事？哪些故事站得住？</h1>
        <p class="lead">新闻不是判决。新闻只是证人。它可以提示市场正在相信什么，却不能替数据层签字画押。</p>
        <div class="pills">
          <span class="pill">Context-first</span>
          <span class="pill">反证保留</span>
          <span class="risk-pill">不能当主证据</span>
        </div>
      </div>
      <aside class="verdict">
        <div class="seal">LOW</div>
        <p class="micro-label">开庭陈述</p>
        <h2>__HEADLINE_TITLE__</h2>
        <p>__HEADLINE_TEXT__</p>
        <div class="pills">
          <span class="pill">新闻线索</span>
          <span class="risk-pill">证据权限受限</span>
          <span class="pill">把握：__CONFIDENCE__</span>
        </div>
      </aside>
    </section>
    <section class="metrics" aria-label="事件快照">
      __METRICS__
    </section>
  </header>
  <nav class="nav" aria-label="页面导航">
    <a href="#cases">四幕审判</a>
    <a href="#charts">证据光幕</a>
    <a href="#testimony">证人席</a>
    <a href="#cross">交叉询问</a>
    <a href="#ledger">主张权限</a>
    <a href="#finale">最终裁定</a>
  </nav>
  <section class="section" id="cases">
    <div class="section-head">
      <div>
        <p class="micro-label">Scene 01</p>
        <h2>四条主线进入法庭。</h2>
      </div>
      <p>每条主线都必须同时说清“可以说什么”和“不能说什么”。这就是 vNext 的漂亮之处：它不把冲突磨平，而是把冲突摆上台面。</p>
    </div>
    <div class="case-stack">
      __MAINLINES__
    </div>
  </section>
  <section class="section" id="charts">
    __CHART_WALL__
  </section>
  <section class="section" id="testimony">
    <div class="section-head">
      <div>
        <p class="micro-label">Scene 03</p>
        <h2>证人席：事件卡逐条作证。</h2>
      </div>
      <p>事件卡不是为了凑材料，而是把“最小事实、可能影响、反证”放在同一个视野里，让读者看到它到底能走多远。</p>
    </div>
    <div class="theater-grid">
      __EVENT_CARDS__
    </div>
  </section>
  <section class="section" id="cross">
    <div class="section-head">
      <div>
        <p class="micro-label">Scene 04</p>
        <h2>交叉询问：新闻必须把问题交给数据。</h2>
      </div>
      <p>这些问题才是新闻层真正的交付：不是“新闻证明了什么”，而是“哪些数据必须回答它”。</p>
    </div>
    <div class="theater-grid">
      __QUESTIONS__
    </div>
  </section>
  <section class="section" id="ledger">
    <div class="section-head">
      <div>
        <p class="micro-label">Scene 05</p>
        <h2>主张权限台账：每句话都要过安检。</h2>
      </div>
      <p>这里保留“能支持什么、不能支持什么”。它不华丽，但它是这场剧的法条。</p>
    </div>
    <div class="ledger-wrap">
      <table>
        <thead><tr><th>主张</th><th>性质</th><th>能支持什么</th><th>不能支持什么</th><th>状态</th></tr></thead>
        <tbody>__LEDGER__</tbody>
      </table>
    </div>
  </section>
  <section class="section finale" id="finale">
    <article class="final-verdict">
      <p class="micro-label">Final Verdict</p>
      <h2>新闻退庭，数据接管。</h2>
      <p>__DELIVERY__</p>
      <div class="pills">__RISKS__</div>
    </article>
    <aside class="watchlist">
      <p class="micro-label">下一步必须追踪</p>
      <ul>__WATCHLIST__</ul>
    </aside>
  </section>
</main>
<div class="modal-backdrop" id="newsModal" aria-hidden="true">
  <section class="modal" role="dialog" aria-modal="true" aria-labelledby="modalTitle">
    <div class="modal-head">
      <div>
        <p class="micro-label" id="modalSource">新闻详情</p>
        <h2 id="modalTitle">标题</h2>
      </div>
      <button class="modal-close" type="button" aria-label="关闭">×</button>
    </div>
    <div class="detail-grid">
      <b>日期</b><span id="modalDate"></span>
      <b>来源</b><span id="modalProvider"></span>
      <b>材料等级</b><span id="modalQuality"></span>
      <b>材料缺口</b><span id="modalMissing"></span>
      <b>摘要</b><span id="modalSummary"></span>
      <b>AI 分析</b><span id="modalAnalysis"></span>
      <b>可以说</b><span id="modalCan"></span>
      <b>不能说</b><span id="modalCannot"></span>
      <b>还要确认</b><span id="modalNeed"></span>
    </div>
  </section>
</div>
<script>
const newsDetails = __NEWS_JSON__;
const modal = document.getElementById("newsModal");
const fields = {
  source: document.getElementById("modalSource"),
  title: document.getElementById("modalTitle"),
  date: document.getElementById("modalDate"),
  provider: document.getElementById("modalProvider"),
  quality: document.getElementById("modalQuality"),
  missing: document.getElementById("modalMissing"),
  summary: document.getElementById("modalSummary"),
  analysis: document.getElementById("modalAnalysis"),
  can: document.getElementById("modalCan"),
  cannot: document.getElementById("modalCannot"),
  need: document.getElementById("modalNeed")
};
function bandLabel(value){
  return {core:"核心证词",supporting:"辅助证词",background:"背景旁证"}[value] || "证词";
}
function openNews(id){
  const item = newsDetails[id];
  if(!item) return;
  fields.source.textContent = bandLabel(item.relevance_band) + " / 把握：" + (item.confidence === "medium" ? "中" : "低");
  fields.title.textContent = item.title || "";
  fields.date.textContent = item.published_at || "";
  fields.provider.textContent = item.source_name || "";
  fields.quality.textContent = item.source_quality || "";
  fields.missing.textContent = (item.missing_evidence || []).join("；") || "暂无明显缺口";
  fields.summary.textContent = item.one_line_summary || "";
  fields.analysis.textContent = item.ai_analysis || "";
  fields.can.textContent = item.can_support || "";
  fields.cannot.textContent = item.cannot_support || "";
  fields.need.textContent = (item.needs_data_confirmation || []).join("；") || "暂无";
  modal.classList.add("open");
  modal.setAttribute("aria-hidden","false");
  document.querySelector(".modal-close").focus();
}
function closeModal(){
  modal.classList.remove("open");
  modal.setAttribute("aria-hidden","true");
}
document.querySelectorAll("[data-news-id]").forEach((button) => {
  button.addEventListener("click", () => openNews(button.dataset.newsId));
});
document.querySelector(".modal-close").addEventListener("click", closeModal);
modal.addEventListener("click", (event) => { if(event.target === modal) closeModal(); });
document.addEventListener("keydown", (event) => { if(event.key === "Escape") closeModal(); });

const canvas = document.getElementById("stageDust");
const ctx = canvas.getContext("2d");
let particles = [];
function resizeDust(){
  const ratio = window.devicePixelRatio || 1;
  canvas.width = Math.floor(window.innerWidth * ratio);
  canvas.height = Math.floor(window.innerHeight * ratio);
  canvas.style.width = window.innerWidth + "px";
  canvas.style.height = window.innerHeight + "px";
  ctx.setTransform(ratio,0,0,ratio,0,0);
  particles = Array.from({length: Math.min(130, Math.floor(window.innerWidth / 8))}, () => ({
    x: Math.random() * window.innerWidth,
    y: Math.random() * window.innerHeight,
    r: Math.random() * 1.8 + .4,
    v: Math.random() * .35 + .08,
    a: Math.random() * .55 + .12
  }));
}
function drawDust(){
  ctx.clearRect(0,0,window.innerWidth,window.innerHeight);
  const beam = ctx.createLinearGradient(0,0,window.innerWidth,window.innerHeight);
  beam.addColorStop(0,"rgba(248,199,90,.05)");
  beam.addColorStop(.5,"rgba(92,231,255,.03)");
  beam.addColorStop(1,"rgba(255,77,66,.04)");
  ctx.fillStyle = beam;
  ctx.fillRect(0,0,window.innerWidth,window.innerHeight);
  particles.forEach((p) => {
    p.y -= p.v;
    p.x += Math.sin((p.y + p.r) * .01) * .18;
    if(p.y < -10){ p.y = window.innerHeight + 10; p.x = Math.random() * window.innerWidth; }
    ctx.beginPath();
    ctx.fillStyle = `rgba(248,199,90,${p.a})`;
    ctx.arc(p.x,p.y,p.r,0,Math.PI*2);
    ctx.fill();
  });
  requestAnimationFrame(drawDust);
}
resizeDust();
drawDust();
window.addEventListener("resize", resizeDust);
</script>
</body>
</html>
"""
    metrics_html = "".join(
        f'<div class="metric"><b>{esc(value)}</b><span>{esc(label)}</span></div>'
        for label, value in metrics.items()
    )
    return (
        template.replace("__GENERATED_AT__", esc(report.get("generated_at_utc")))
        .replace("__HEADLINE_TITLE__", esc(headline.get("title")))
        .replace("__HEADLINE_TEXT__", esc(headline.get("plain_text")))
        .replace("__CONFIDENCE__", esc(label_confidence(headline.get("confidence"))))
        .replace("__METRICS__", metrics_html)
        .replace("__MAINLINES__", render_mainlines(report))
        .replace("__CHART_WALL__", render_chart_wall(line_chart, sparks))
        .replace("__EVENT_CARDS__", render_event_cards(report))
        .replace("__QUESTIONS__", render_questions(report))
        .replace("__LEDGER__", render_ledger(report))
        .replace("__DELIVERY__", esc(delivery.get("one_sentence")))
        .replace("__RISKS__", risk_pills)
        .replace("__WATCHLIST__", watchlist)
        .replace("__NEWS_JSON__", news_json)
    )


def main() -> None:
    OUTPUT_HTML.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_HTML.write_text(build_html(), encoding="utf-8")
    print(OUTPUT_HTML)


if __name__ == "__main__":
    main()
