# 事件层二档研究部（dsh 底盘）。
#
# 三圈制度：议程账本（agenda.py）/ 经费卡（budget.py + hooks/budget_gate.py）/
# 对账器（reconcile.py）。底盘是 DeepSeek Harness，经官方 Python SDK 驱动；
# 卡口逻辑全部在 Python hooks（hooks/），语义镣铐在 persona.md。
# 红线：本包产出永远是第二层候选材料，流向 IA，永不进数据主链。
