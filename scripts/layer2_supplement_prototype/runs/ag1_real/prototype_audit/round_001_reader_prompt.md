你是第二层补采原型的 reader。任务议程：
- agenda_id: ag1_real
- question: 补采一件“已发生的事”的候选解释：从 SEC EDGAR 确认苹果公司（Apple, CIK 0000320193）最新提交的 8-K 或同等级文件内容（可先读 https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=0000320193&type=8-K&dateb=&owner=include&count=10 ，再抓其中一条的索引页；材料卡只写事实与解读候选，不下结论）。
本轮（第 1 轮）工具返回如下（全部来自白名单只读工具）：
[
  {
    "tool": "fetch_official_url",
    "ok": false,
    "error_code": "network_error",
    "error": "网络失败如实返回：HTTPError: HTTP Error 403: Forbidden",
    "url": "https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=0000320193&type=8-K&dateb=&owner=include&count=10",
    "fetched_at_utc": "2026-08-15T15:57:10.351825+00:00"
  }
]

请把本轮工具材料收成 0-2 张候选材料卡（没有合格材料就输出空数组）。每张卡你只填这些字段：fact_summary, interpretation, source_tier, source_url, needs_data_confirmation, limitations。
机器会自动补 card_id / agenda_id / collected_at_utc / governance_note。

四条镣铐（机器会逐字段校验，不满足会被打回）：
1. fact_summary 与 interpretation 都必须非空且内容分离：fact_summary 只写材料原文里的事实，不得含 ['可能', '也许', '预计', '暗示', '或将', '有望', '估计', '猜测', '大概', '或许'] 或 ['may', 'might', 'could', 'likely', 'expected', 'expects', 'possibly', 'perhaps', 'maybe', 'probably', 'would', 'should'] 类措辞；interpretation 是假设性解读，必须含假设标记（如 ['可能', '假设', '推测', '猜想', '若', '也许', '或许', '不排除', '待确认'] 之一）。
2. source_tier 必须是 ['official', 'primary_news', 'aggregator_news', 'weak_social', 'unverified'] 之一。
3. collected_at_utc 由机器填，必须是 ISO 时间且不晚于现在+5分钟。
4. needs_data_confirmation 必须是非空数组：写"需要第一层哪些数据确认"。

纪律：本材料是第二层候选材料，判断以第一层数据为准；不许下结论。
输出严格 JSON，格式：{"cards":[{"fact_summary":"...","interpretation":"...","source_tier":"official","source_url":"...","needs_data_confirmation":["..."],"limitations":["..."]}]}