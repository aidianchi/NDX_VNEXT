import json, re, sys
sys.path.insert(0, "/Users/aidianchi/Desktop/ndx_mac/src")
sys.path.insert(0, "/Users/aidianchi/Desktop/ndx_mac")

from src.agent_analysis.llm_engine import LLMEngine

AUDIT = "/Users/aidianchi/Desktop/ndx_mac/output/analysis/vnext/20260715_001617_r3_replay/prompt_audit/final_adjudicator/attempt_4.prompt.txt"
OUTDIR = "/private/tmp/claude-501/-Users-aidianchi-Desktop-ndx-mac/5d2f461b-379f-40f2-bc47-8ab6f074dd39/scratchpad"

prompt = open(AUDIT, encoding="utf-8").read()

A_OLD = "再写一段 400-700 字的连贯判决正文"
A_NEW = "再写一段 450-900 字的连贯判决正文"
B_OLD = "- 只允许使用本次输入中已经出现的数字、分位和 evidence refs；不得引入任何新的数据、阈值或概率。每个关键断言"
B_NEW = (
    "- must_preserve_risks 的每一条都必须在正文中出现，但一条只需一个短语点名（例如“广度分化”四个字即算点名），"
    "不必逐条展开；一条都不许漏，也禁止弱化任何一条的严重性。\n"
    "- 只允许使用本次输入中已经出现的数字、分位和 evidence refs；不得引入任何新的数据、阈值或概率。"
    "引用数字时优先使用分位表述；输入中标记为 audit-only 或 supporting_only 的字段不得作为正文中的数值依据。"
    "三条主要理由每条必须至少带一个方括号标注的 evidence_ref（例如 [L1.get_10y_real_rate]）——这是硬要求，一个都没有等于整段作废；"
    "其余断言可以不标，但凡是标了的必须真实存在于输入中。每个关键断言"
)
C_OLD = "- 不确定的就写不确定。禁止为了行文顺滑而弱化或省略 must_preserve_risks 里的任何一条。"
C_NEW = "- 不确定的就写不确定。"
D_OLD = "<400-700 字的总分总判决正文>"
D_NEW = "<450-900 字的总分总判决正文>"

for tag, old in (("A", A_OLD), ("B", B_OLD), ("C", C_OLD), ("D", D_OLD)):
    if old not in prompt:
        raise SystemExit(f"pattern {tag} not found in audited prompt")

prompt2 = prompt.replace(A_OLD, A_NEW).replace(B_OLD, B_NEW).replace(C_OLD, C_NEW).replace(D_OLD, D_NEW)
open(f"{OUTDIR}/r3v2_prompt.txt", "w", encoding="utf-8").write(prompt2)

engine = LLMEngine(available_models=["deepseek-v4-flash", "deepseek-v4-pro"])
raw = engine.call_with_fallback(prompt2, stage_name="final_adjudicator_r3v2")
open(f"{OUTDIR}/r3v2_raw.txt", "w", encoding="utf-8").write(raw or "")
if not raw:
    raise SystemExit("EMPTY RESPONSE")

text = raw.strip()
m = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
if m:
    text = m.group(1)
start, end = text.find("{"), text.rfind("}")
data = json.loads(text[start : end + 1])

v = data.get("reasoned_verdict", "")
print("VERDICT_LEN:", len(v))
print(v)
print()
refs = re.findall(r"\[([^\[\]]+)\]", v)
missing = [r for r in refs if r not in prompt]
print("refs:", len(refs), "| 不在输入中的 ref:", missing)
risks = data.get("must_preserve_risks", [])
print("must_preserve_risks:", len(risks))
for r in risks:
    rd = r if isinstance(r, str) else (r.get("risk") or r.get("description") or json.dumps(r, ensure_ascii=False))
    print(" -", str(rd)[:70])
json.dump(data, open(f"{OUTDIR}/r3v2_final.json", "w", encoding="utf-8"), ensure_ascii=False, indent=2)
