# -*- coding: utf-8 -*-
"""ndx_vnext 系统架构总图：三层骨架 + 双向出题回路。手绘 matplotlib，输出 PNG + SVG。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(sys.executable).parent.parent.parent))
from daimon_runtime import setup_plot

setup_plot()

import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch

OUT_DIR = Path(__file__).resolve().parent

# ---------- 配色（蓝 / 绿 / 红 / 黄 / 深藏青 五主色 + 橙色出题箭头） ----------
INK = "#2E3A48"          # 深色字
SUBINK = "#5B6570"       # 次要字
GRAY_ARROW = "#7A8492"   # 普通箭头
SRC_FC, SRC_EC = "#EFF2F5", "#98A2AD"                 # 数据来源：浅灰
DATA_FC, DATA_EC, DATA_TX = "#E7F0FA", "#3B6EA5", "#1F4E79"   # 数据层：蓝
BRIDGE_FC = "#D6E4F5"
BULL_FC, BULL_EC, BULL_TX = "#E2F2E4", "#2E7D32", "#1B5E20"   # 正方：绿
BEAR_FC, BEAR_EC, BEAR_TX = "#FBE3DE", "#C0392B", "#922B21"   # 反方：红
IA_FC = "#2F3B52"                                     # 裁决桌：深藏青
EVENT_FC, EVENT_EC, EVENT_TX = "#FDF3D8", "#C8963E", "#7A5A12"  # 事件层：暖黄
ORANGE = "#D35400"                                    # 出题回路：橙
BOOK_EC, BOOK_TX = "#3949AB", "#1A237E"
BOSS_FC = "#37474F"

fig, ax = plt.subplots(figsize=(20, 12.5), dpi=150)
fig.patch.set_facecolor("white")
ax.set_xlim(0, 160)
ax.set_ylim(0, 100)
ax.set_aspect("equal")
ax.axis("off")


def box(x0, y0, x1, y1, fc, ec, lw=1.6, rs=1.4, z=2):
    p = FancyBboxPatch(
        (x0, y0), x1 - x0, y1 - y0,
        boxstyle=f"round,pad=0,rounding_size={rs}",
        fc=fc, ec=ec, lw=lw, mutation_scale=1, zorder=z,
    )
    ax.add_patch(p)


def text(x, y, s, size, color=INK, weight="normal", z=5, ha="center", va="center", **kw):
    ax.text(x, y, s, ha=ha, va=va, fontsize=size,
            color=color, weight=weight, zorder=z, linespacing=1.5, **kw)


def arrow(p0, p1, color=GRAY_ARROW, lw=1.8, ms=18, rad=0.0, z=3):
    ax.annotate(
        "", xy=p1, xytext=p0,
        arrowprops=dict(
            arrowstyle="-|>", color=color, lw=lw, mutation_scale=ms,
            shrinkA=1, shrinkB=1,
            connectionstyle=f"arc3,rad={rad}",
        ),
        zorder=z,
    )


# ---------- 标题 ----------
text(80, 97, "ndx_vnext 系统架构总览", 27, weight="bold")
text(80, 92.6, "AI 驱动的纳斯达克 100 研究流水线 —— 三层骨架看得全，双向出题看得远", 14.5, SUBINK)

# ---------- 1. 最左：四个数据来源 ----------
SRC = [
    ("官方经济数据", 76, 88),
    ("市场行情数据", 60, 72),
    ("新闻与外部事件", 42, 54),
    ("老板指令", 24, 36),
]
for name, y0, y1 in SRC:
    box(2, y0, 18, y1, SRC_FC, SRC_EC)
    text(10, (y0 + y1) / 2, name, 15, INK)
text(10, 91.5, "数据来源", 13.5, SUBINK, weight="bold")

# ---------- 2. 数据层：五层隔离 ----------
box(24, 44, 68, 89, DATA_FC, DATA_EC, lw=2.0, rs=2.0)
text(46, 85.2, "数据层 · 五层隔离判断", 17, DATA_TX, weight="bold")
LAYERS = [("L1", "利率宏观"), ("L2", "风险偏好"), ("L3", "内部健康"),
          ("L4", "盈利估值"), ("L5", "价格趋势")]
BW, GAP, X0, Y0, Y1 = 8.16, 0.7, 24.2, 52, 78
for i, (code, name) in enumerate(LAYERS):
    x0 = X0 + i * (BW + GAP)
    box(x0, Y0, x0 + BW, Y1, "white", DATA_EC, lw=1.5)
    text(x0 + BW / 2, 70.5, code, 15, DATA_TX, weight="bold")
    text(x0 + BW / 2, 59.5, name, 13, DATA_TX, weight="bold")
    if i < 4:  # 隔离虚线：互相看不见
        xsep = x0 + BW + GAP / 2
        ax.plot([xsep, xsep], [Y0 + 1, Y1 - 1], ls=(0, (4, 3)), lw=1.4,
                color="#7A93B5", zorder=4)
text(46, 48, "五层互不见面 · 各自只读本层事实", 12, "#5B7089")

# ---------- 3. 桥接 → 正反两方 ----------
box(70, 60, 88, 76, BRIDGE_FC, DATA_EC)
text(79, 71, "跨层桥接", 14.5, DATA_TX, weight="bold")
text(79, 65, "只读五张层卡结论", 12, DATA_TX)

box(92, 70, 106, 84, BULL_FC, BULL_EC, lw=1.8)
text(99, 77, "正方论点", 16.5, BULL_TX, weight="bold")
box(92, 52, 106, 66, BEAR_FC, BEAR_EC, lw=1.8)
text(99, 59, "反方假说", 16.5, BEAR_TX, weight="bold")
text(99, 68, "同台对质 · 同一份证据菜单", 10, SUBINK)

# ---------- 4. 综合裁决桌 ----------
box(110, 50, 132, 86, IA_FC, IA_FC, lw=2.2, rs=1.8)
text(121, 74, "综合裁决桌", 19.5, "white", weight="bold")
text(121, 62, "全系统唯一碰头处\n冲突留痕 · 裁不动上交", 12.5, "#C9D3E0")

# ---------- 5. 三层楼研报 ----------
box(136, 54, 158, 96, "#F4F5FB", BOOK_EC, lw=1.8, rs=1.6)
text(147, 92.2, "三层楼研报", 15.5, BOOK_TX, weight="bold")
book_rows = [
    ("塔尖 · 1 分钟", 78, 88, "#C5CAE9"),
    ("塔身 · 10 分钟", 67, 77, "#DDE1F4"),
    ("塔基 · 30 分钟", 56, 66, "#EBEDF9"),
]
for name, y0, y1, fc in book_rows:
    box(138.5, y0, 155.5, y1, fc, BOOK_EC, lw=1.4, rs=1.0)
    text(147, (y0 + y1) / 2, name, 13.5, BOOK_TX, weight="bold")

# ---------- 6. 老板 ----------
box(136, 34, 158, 48, BOSS_FC, BOSS_FC, lw=2.0)
text(147, 43.2, "老板", 18, "white", weight="bold")
text(147, 37.6, "验收与拍板", 12.5, "#D5DBE1")

# ---------- 7. 事件层 ----------
box(72, 6, 132, 32, EVENT_FC, EVENT_EC, lw=2.0, rs=1.8)
text(102, 28.2, "事件层 · 联网调研员", 17, EVENT_TX, weight="bold")
box(78, 10, 126, 24, "white", EVENT_EC, lw=1.5)
text(102, 19.4, "戴镣铐的调研员：自主上网搜索、抓取、写材料卡", 13.5, EVENT_TX)
text(102, 13.6, "经费卡限额 · 域名白名单 · 候选材料永不进数据主链", 11.5, "#9A7B2D")

# ---------- 普通箭头（材料 / 产物流向） ----------
arrow((18, 82), (24, 82))                       # 官方经济数据 → 数据层
arrow((18, 66), (24, 66))                       # 市场行情数据 → 数据层
arrow((18, 47), (71, 18))                       # 新闻与外部事件 → 事件层
arrow((18, 30), (71, 12))                       # 老板指令 → 事件层
arrow((68, 68), (70, 68))                       # 数据层 → 桥接
arrow((88, 71.5), (92, 76))                     # 桥接 → 正方
arrow((88, 64.5), (92, 60))                     # 桥接 → 反方
arrow((106, 77), (110, 75))                     # 正方 → 裁决桌
arrow((106, 59), (110, 61))                     # 反方 → 裁决桌
arrow((121, 32), (121, 50))                     # 事件层 → 裁决桌（候选材料）
text(118.5, 41, "候选材料", 12, SUBINK, ha="right")
arrow((132, 68), (136, 70))                     # 裁决桌 → 三层楼
arrow((147, 54), (147, 48))                     # 三层楼 → 老板
arrow((130, 50), (137, 46.5))                   # 裁决桌 → 老板（裁不动上交）
text(127, 43, "裁不动 · 上交", 11, SUBINK)

# ---------- 出题回路（两条反向醒目粗箭头） ----------
arrow((54, 43.2), (84, 32.8), color=ORANGE, lw=4.2, ms=30, rad=0.12, z=4)
arrow((97, 32.8), (67, 43.2), color=ORANGE, lw=4.2, ms=30, rad=0.12, z=4)
text(49, 34.5, "出题①：家里答不了的", 13.5, ORANGE, weight="bold", ha="center")
text(101, 42.5, "出题②：这事数据该回答", 13.5, ORANGE, weight="bold", ha="center")

# ---------- 图例 ----------
box(2, 3, 44, 16, "white", "#C9D1D9", lw=1.2, rs=1.2)
text(6, 12.6, "图例", 12.5, INK, weight="bold")
arrow((5, 8.8), (11, 8.8), color=GRAY_ARROW, lw=1.8, ms=16)
text(12, 8.8, "材料 / 产物流向", 12, SUBINK, ha="left")
arrow((5, 5.2), (11, 5.2), color=ORANGE, lw=4.2, ms=26)
text(12, 5.2, "出题回路（双向提问）", 12, SUBINK, ha="left")

png = OUT_DIR / "architecture_overview.png"
svg = OUT_DIR / "architecture_overview.svg"
fig.savefig(png, bbox_inches="tight", facecolor="white")
fig.savefig(svg, bbox_inches="tight", facecolor="white")
print(f"saved: {png}")
print(f"saved: {svg}")
