# -*- coding: utf-8 -*-
"""
生成 LISA 聚类地图 (基于局部莫兰指数)
使用 pyshp + shapely + matplotlib (避免 geopandas numpy 2.x 冲突)
输出: 莫兰指数图表/图B_LISA聚类图.png + 图C_LISA显著性图.png
"""

import os
import numpy as np
import shapefile
from shapely.geometry import Polygon, Point, MultiPolygon
from shapely.ops import unary_union
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm

# 直接按路径加载字体 (绕过 matplotlib 字体解析的 weight 问题)
FONT_PATH = r"C:\Windows\Fonts\simhei.ttf"
FONT_CN = fm.FontProperties(fname=FONT_PATH, size=12)
FONT_CN_TITLE = fm.FontProperties(fname=FONT_PATH, size=22)
FONT_CN_SUBTITLE = fm.FontProperties(fname=FONT_PATH, size=10)
FONT_CN_SMALL = fm.FontProperties(fname=FONT_PATH, size=8)
FONT_CN_XSMALL = fm.FontProperties(fname=FONT_PATH, size=7)
FONT_CN_ITALIC = fm.FontProperties(fname=FONT_PATH, size=7, style="italic")
FONT_CN_LEGEND_TITLE = fm.FontProperties(fname=FONT_PATH, size=11)
FONT_CN_LEGEND = fm.FontProperties(fname=FONT_PATH, size=10)
matplotlib.rcParams["axes.unicode_minus"] = False
print("使用字体: SimHei (黑体)")

MONO_FONT = "DejaVu Sans Mono"
import matplotlib.patches as mpatches
from matplotlib.patheffects import withStroke
from matplotlib.collections import PolyCollection, LineCollection

BASE = r"E:\Data\赣州稀土"
LISA_SHP = os.path.join(BASE, "空间分布分析结果", "局域莫兰指数_LISA.shp")
COUNTY_SHP = os.path.join(BASE, "县级汇总结果", "county_stats.shp")
MINES_SHP = os.path.join(BASE, "空间分布分析结果", "裁剪后", "赣州矿场点_裁剪后.shp")
OUT_DIR = os.path.join(BASE, "莫兰指数图表")
os.makedirs(OUT_DIR, exist_ok=True)

# ── 颜色方案 ──────────────────────────────────────────
CLUSTER_COLORS = {
    "高-高集聚 (HH)": "#d73027",
    "高-低集聚 (HL)": "#fc8d59",
    "低-高集聚 (LH)": "#91bfdb",
    "低-低集聚 (LL)": "#4575b4",
    "不显著 (NS)":   "#e8e8e8",
}
CLUSTER_LABELS_CN = {
    "高-高集聚 (HH)": "高-高集聚 (HH) — 热点区 (高值被高值包围)",
    "高-低集聚 (HL)": "高-低集聚 (HL) — 高值被低值包围",
    "低-高集聚 (LH)": "低-高集聚 (LH) — 低值被高值包围",
    "低-低集聚 (LL)": "低-低集聚 (LL) — 冷点区 (低值被低值包围)",
    "不显著 (NS)":   "不显著 (NS)",
}
CLUSTER_ZORDER = {"不显著 (NS)": 1, "低-低集聚 (LL)": 2, "低-高集聚 (LH)": 3,
                  "高-低集聚 (HL)": 4, "高-高集聚 (HH)": 5}

SIG_COLORS = {
    "p ≤ 0.001": "#2166ac",
    "p ≤ 0.01":  "#92c5de",
    "p ≤ 0.05":  "#d1e5f0",
    "p > 0.05":  "#f0f0f0",
}

# ── 县名映射 (DBF 编码损坏，用英文名硬映射) ──────────
COUNTY_NAMES = {
    "Anyuan": "安远县", "Chongyi": "崇义县", "Dayu": "大余县",
    "Dingnan": "定南县", "Ganxian": "赣县区", "Huichang": "会昌县",
    "Longnan": "龙南市", "Nankang": "南康区", "Ningdu": "宁都县",
    "Quannan": "全南县", "Ruijin": "瑞金市", "Shangyou": "上犹县",
    "Shicheng": "石城县", "Xinfeng": "信丰县", "Xunwu": "寻乌县",
    "Xingguo": "兴国县", "Yudu": "于都县", "Zhanggong": "章贡区",
}

# ── 工具函数 ──────────────────────────────────────────
def read_shp_polygons(path, encoding="gbk"):
    """读取 polygon shapefile, 返回 (geoms_wgs84, records, fields)"""
    sf = shapefile.Reader(path, encoding=encoding, encodingErrors="replace")
    records = sf.records()
    fields = [f[0] for f in sf.fields[1:]]
    geoms = []
    for shp in sf.shapes():
        pts = shp.points
        parts = list(shp.parts) + [len(pts)]
        rings = []
        for i in range(len(parts) - 1):
            ring_pts = pts[parts[i]:parts[i+1]]
            if len(ring_pts) >= 3:
                rings.append(ring_pts)
        if rings:
            geoms.append(Polygon(rings[0], rings[1:]) if len(rings) > 1 else Polygon(rings[0]))
        else:
            geoms.append(Polygon())
    sf.close()
    return geoms, records, fields

def read_shp_points(path, encoding="gbk"):
    """读取 point shapefile, 返回 (x_list, y_list)"""
    sf = shapefile.Reader(path, encoding=encoding)
    xs, ys = [], []
    for shp in sf.shapes():
        xs.append(shp.points[0][0])
        ys.append(shp.points[0][1])
    sf.close()
    return xs, ys

def polygon_to_verts(poly):
    """将 shapely polygon 转为 matplotlib PolyCollection 可用的顶点列表"""
    if poly.is_empty:
        return []
    if poly.geom_type == "Polygon":
        verts = [np.array(poly.exterior.coords)]
        for interior in poly.interiors:
            verts.append(np.array(interior.coords))
        return verts
    elif poly.geom_type == "MultiPolygon":
        result = []
        for p in poly.geoms:
            result.extend(polygon_to_verts(p))
        return result
    return []

# ── 加载 LISA 数据 ────────────────────────────────────
print("加载 LISA 网格数据...")
lisa_geoms, lisa_recs, lisa_fields = read_shp_polygons(LISA_SHP, encoding="gbk")
# 字段: cell_row, cell_col, count, local_I, p_value, z_std, lag_std, cluster
field_idx = {f: i for i, f in enumerate(lisa_fields)}
cluster_idx = field_idx["cluster"]
pval_idx = field_idx["p_value"]
print(f"  LISA 网格: {len(lisa_geoms)} 个")

# 按聚类类型分组顶点
cluster_groups = {k: [] for k in CLUSTER_COLORS}
for geom, rec in zip(lisa_geoms, lisa_recs):
    cluster_label = rec[cluster_idx].strip()
    if cluster_label not in cluster_groups:
        cluster_label = [k for k in cluster_groups if k.split("(")[0].strip() in cluster_label or cluster_label in k]
        cluster_label = cluster_label[0] if cluster_label else "不显著 (NS)"
    verts = polygon_to_verts(geom)
    if verts:
        # 只取外环
        cluster_groups[cluster_label].append(np.array(geom.exterior.coords))

# 按显著性分组
pval_groups = {"p ≤ 0.001": [], "p ≤ 0.01": [], "p ≤ 0.05": [], "p > 0.05": []}
for geom, rec in zip(lisa_geoms, lisa_recs):
    pv = rec[pval_idx]
    verts = np.array(geom.exterior.coords)
    if pv <= 0.001:
        pval_groups["p ≤ 0.001"].append(verts)
    elif pv <= 0.01:
        pval_groups["p ≤ 0.01"].append(verts)
    elif pv <= 0.05:
        pval_groups["p ≤ 0.05"].append(verts)
    else:
        pval_groups["p > 0.05"].append(verts)

# ── 加载县级边界 ──────────────────────────────────────
print("加载县级边界...")
county_geoms, county_recs, county_fields = read_shp_polygons(COUNTY_SHP, encoding="utf-8")
print(f"  县域: {len(county_geoms)} 个")

# 提取边界线段
all_boundary_lines = []
county_boundary_lines = []
for geom in county_geoms:
    if geom.is_empty:
        continue
    if geom.geom_type == "Polygon":
        coords = np.array(geom.exterior.coords)
        segments = np.stack([coords[:-1], coords[1:]], axis=1)
        all_boundary_lines.extend(segments)
        county_boundary_lines.extend(segments)
    elif geom.geom_type == "MultiPolygon":
        for p in geom.geoms:
            coords = np.array(p.exterior.coords)
            segments = np.stack([coords[:-1], coords[1:]], axis=1)
            all_boundary_lines.extend(segments)
            county_boundary_lines.extend(segments)

# ── 加载矿点 ──────────────────────────────────────────
print("加载矿点...")
mine_xs, mine_ys = read_shp_points(MINES_SHP, encoding="gbk")
print(f"  矿点: {len(mine_xs)} 个")

# ── 统计 ──────────────────────────────────────────────
cluster_counts = {}
for rec in lisa_recs:
    lbl = rec[cluster_idx].strip()
    cluster_counts[lbl] = cluster_counts.get(lbl, 0) + 1

# ═══════════════════════════════════════════════════════
# 图1: LISA 聚类地图
# ═══════════════════════════════════════════════════════
print("绘制 LISA 聚类地图...")

fig, ax = plt.subplots(1, 1, figsize=(19, 21), dpi=200)

# 县级边界 (底图虚线)
if all_boundary_lines:
    lc = LineCollection(all_boundary_lines, colors="#b0a090", linewidths=0.4,
                        linestyles="dashed", zorder=0)
    ax.add_collection(lc)

# LISA 聚类网格 (按 zorder 从下到上)
for label in ["不显著 (NS)", "低-低集聚 (LL)", "低-高集聚 (LH)", "高-低集聚 (HL)", "高-高集聚 (HH)"]:
    verts_list = cluster_groups.get(label, [])
    if verts_list:
        pc = PolyCollection(verts_list, facecolors=CLUSTER_COLORS[label],
                           edgecolors="none", linewidths=0,
                           zorder=CLUSTER_ZORDER[label])
        ax.add_collection(pc)

# 县级边界 (顶层实线)
if county_boundary_lines:
    lc_top = LineCollection(county_boundary_lines, colors="#4a3520", linewidths=1.0, zorder=6)
    ax.add_collection(lc_top)

# 矿点散点
ax.scatter(mine_xs, mine_ys, c="#1a1a1a", s=4, edgecolors="white",
           linewidths=0.15, zorder=7, alpha=0.8, marker="o")

# 县域标注
eng_name_idx = None
for i, f in enumerate(county_fields):
    if f == "eng_name":
        eng_name_idx = i
        break

for geom, rec in zip(county_geoms, county_recs):
    if geom.is_empty:
        continue
    eng = str(rec[eng_name_idx]) if eng_name_idx is not None else ""
    name = COUNTY_NAMES.get(eng, eng)
    c = geom.centroid
    ax.annotate(name, xy=(c.x, c.y), fontproperties=FONT_CN_XSMALL,
                color="#2a1f10", ha="center", va="center",
                path_effects=[withStroke(linewidth=2.0, foreground="white")],
                zorder=8)

# ── 图面设置 ──────────────────────────────────────────
ax.set_xlim(113.7, 116.9)
ax.set_ylim(24.3, 27.4)
ax.set_aspect(1.0)
ax.axis("off")

fig.text(0.5, 0.965, "赣州市矿山 LISA 聚类地图",
         fontproperties=FONT_CN_TITLE, ha="center", va="top")
fig.text(0.5, 0.945, "Local Moran's I · 3km 渔网格网 · KNN (k=8) 空间权重 · 999 permutations",
         fontproperties=FONT_CN_SUBTITLE, color="#6b5f50", ha="center", va="top")

# 图例
legend_items = [mpatches.Patch(color=CLUSTER_COLORS[k], label=CLUSTER_LABELS_CN[k])
                for k in ["高-高集聚 (HH)", "高-低集聚 (HL)", "低-高集聚 (LH)",
                          "低-低集聚 (LL)", "不显著 (NS)"]]
legend = ax.legend(handles=legend_items, loc="lower left", prop=FONT_CN_LEGEND,
                   framealpha=0.93,
                   edgecolor="#c0b8a8", facecolor="white", ncol=1,
                   title="LISA 聚类类型")
legend.get_title().set_fontproperties(FONT_CN_LEGEND_TITLE)

# 统计表
label_order = ["高-高集聚 (HH)", "高-低集聚 (HL)", "低-高集聚 (LH)", "低-低集聚 (LL)", "不显著 (NS)"]
stats_lines = ["LISA 聚类统计", "─" * 26]
for lbl in label_order:
    cnt = cluster_counts.get(lbl, 0)
    short = lbl.split("(")[0].strip()
    stats_lines.append(f"{short:8s}  {cnt:5d}  ({cnt/len(lisa_geoms)*100:4.1f}%)")
stats_lines += ["─" * 26, "Moran's I = 0.1424  p = 0.001"]

ax.text(0.985, 0.992, "\n".join(stats_lines), transform=ax.transAxes,
        fontproperties=FONT_CN_XSMALL, verticalalignment="top",
        horizontalalignment="right",
        bbox=dict(boxstyle="round,pad=0.5", facecolor="white",
                  edgecolor="#c0b8a8", alpha=0.93), zorder=10)

# 底部信息
fig.text(0.5, 0.012, "数据来源: 全国矿产地分布数据 (2025) · 分析工具: PySAL/esda · Python",
         fontproperties=FONT_CN_SMALL, color="#988b7a", ha="center")

# 比例尺 (约30km)
from matplotlib.lines import Line2D
scale_km = 30
# 在纬度25.2°处，1° ≈ 111km * cos(25.2°) ≈ 100.5km
deg_per_km = 1.0 / (111.0 * np.cos(np.radians(25.2)))
scale_deg = scale_km * deg_per_km
scale_x = 113.85
scale_y = 24.45
ax.add_line(Line2D([scale_x, scale_x + scale_deg], [scale_y, scale_y],
                   color="#2a1f10", linewidth=2.5, zorder=9))
ax.text(scale_x + scale_deg / 2, scale_y + 0.03, f"{scale_km} km",
        fontproperties=FONT_CN_SMALL, ha="center", color="#2a1f10", zorder=9)

# 指北针
north_x, north_y = 116.65, 27.15
ax.annotate("N", xy=(north_x, north_y),
            fontproperties=FONT_CN_TITLE, color="#2a1f10", ha="center", va="center", zorder=9)
ax.plot([north_x, north_x], [north_y - 0.15, north_y + 0.12], color="#2a1f10",
        linewidth=1.5, zorder=9)

# 保存
out_svg = os.path.join(OUT_DIR, "图B_LISA聚类图.svg")
out_png = os.path.join(OUT_DIR, "图B_LISA聚类图.png")
out_pdf = os.path.join(OUT_DIR, "图B_LISA聚类图.pdf")
fig.savefig(out_svg, bbox_inches="tight", pad_inches=0.3, facecolor="white")
fig.savefig(out_png, bbox_inches="tight", pad_inches=0.3, facecolor="white")
fig.savefig(out_pdf, bbox_inches="tight", pad_inches=0.3, facecolor="white")
plt.close(fig)
print(f"  -> {out_svg}")
print(f"  -> {out_png}")

# ═══════════════════════════════════════════════════════
# 图2: LISA 显著性地图
# ═══════════════════════════════════════════════════════
print("绘制 LISA 显著性地图...")

fig2, ax2 = plt.subplots(1, 1, figsize=(19, 21), dpi=200)

if all_boundary_lines:
    lc2 = LineCollection(all_boundary_lines, colors="#b0a090", linewidths=0.4,
                         linestyles="dashed", zorder=0)
    ax2.add_collection(lc2)

sig_zorder = {"p > 0.05": 1, "p ≤ 0.05": 2, "p ≤ 0.01": 3, "p ≤ 0.001": 4}
for label in ["p > 0.05", "p ≤ 0.05", "p ≤ 0.01", "p ≤ 0.001"]:
    verts_list = pval_groups.get(label, [])
    if verts_list:
        pc2 = PolyCollection(verts_list, facecolors=SIG_COLORS[label],
                            edgecolors="none", linewidths=0, zorder=sig_zorder[label])
        ax2.add_collection(pc2)

if county_boundary_lines:
    lc_top2 = LineCollection(county_boundary_lines, colors="#4a3520", linewidths=1.0, zorder=6)
    ax2.add_collection(lc_top2)

ax2.scatter(mine_xs, mine_ys, c="#1a1a1a", s=4, edgecolors="white",
            linewidths=0.15, zorder=7, alpha=0.8, marker="o")

# 县域标注
for geom, rec in zip(county_geoms, county_recs):
    if geom.is_empty:
        continue
    eng = str(rec[eng_name_idx]) if eng_name_idx is not None else ""
    name = COUNTY_NAMES.get(eng, eng)
    c = geom.centroid
    ax2.annotate(name, xy=(c.x, c.y), fontproperties=FONT_CN_XSMALL,
                 color="#2a1f10", ha="center", va="center",
                 path_effects=[withStroke(linewidth=2.0, foreground="white")], zorder=8)

ax2.set_xlim(113.7, 116.9)
ax2.set_ylim(24.3, 27.4)
ax2.set_aspect(1.0)
ax2.axis("off")

fig2.text(0.5, 0.965, "赣州市矿山 LISA 显著性地图",
          fontproperties=FONT_CN_TITLE, ha="center", va="top")
fig2.text(0.5, 0.945, "Local Moran's I Significance · 999 permutations · p-value 分级",
          fontproperties=FONT_CN_SUBTITLE, color="#6b5f50", ha="center", va="top")

# 图例
sig_legend_items = [
    mpatches.Patch(color=SIG_COLORS["p ≤ 0.001"], label="p ≤ 0.001 (极显著)"),
    mpatches.Patch(color=SIG_COLORS["p ≤ 0.01"],  label="p ≤ 0.01 (高度显著)"),
    mpatches.Patch(color=SIG_COLORS["p ≤ 0.05"],  label="p ≤ 0.05 (显著)"),
    mpatches.Patch(color=SIG_COLORS["p > 0.05"],  label="p > 0.05 (不显著)"),
]
legend2 = ax2.legend(handles=sig_legend_items, loc="lower left", prop=FONT_CN_LEGEND,
                     framealpha=0.93,
                     edgecolor="#c0b8a8", facecolor="white", ncol=1,
                     title="显著性水平")
legend2.get_title().set_fontproperties(FONT_CN_LEGEND_TITLE)

# 显著性统计
pval_counts = {}
for rec in lisa_recs:
    pv = rec[pval_idx]
    if pv <= 0.001:
        pval_counts["p ≤ 0.001"] = pval_counts.get("p ≤ 0.001", 0) + 1
    elif pv <= 0.01:
        pval_counts["p ≤ 0.01"] = pval_counts.get("p ≤ 0.01", 0) + 1
    elif pv <= 0.05:
        pval_counts["p ≤ 0.05"] = pval_counts.get("p ≤ 0.05", 0) + 1
    else:
        pval_counts["p > 0.05"] = pval_counts.get("p > 0.05", 0) + 1

sig_stats_lines = ["显著性统计", "─" * 22]
for lbl in ["p ≤ 0.001", "p ≤ 0.01", "p ≤ 0.05", "p > 0.05"]:
    cnt = pval_counts.get(lbl, 0)
    sig_stats_lines.append(f"{lbl:12s} {cnt:5d}  ({cnt/len(lisa_geoms)*100:4.1f}%)")

ax2.text(0.985, 0.992, "\n".join(sig_stats_lines), transform=ax2.transAxes,
         fontproperties=FONT_CN_SMALL, verticalalignment="top",
         horizontalalignment="right",
         bbox=dict(boxstyle="round,pad=0.5", facecolor="white",
                   edgecolor="#c0b8a8", alpha=0.93), zorder=10)

fig2.text(0.5, 0.012, "数据来源: 全国矿产地分布数据 (2025) · 分析工具: PySAL/esda · Python",
          fontproperties=FONT_CN_SMALL, color="#988b7a", ha="center")

fig2.text(0.02, 0.012, "* 显著性基于 999 次随机排列检验 (Randomization)",
          fontproperties=FONT_CN_ITALIC, color="#988b7a", ha="left")

out_png2 = os.path.join(OUT_DIR, "图C_LISA显著性图.png")
out_pdf2 = os.path.join(OUT_DIR, "图C_LISA显著性图.pdf")
fig2.savefig(out_png2, bbox_inches="tight", pad_inches=0.3, facecolor="white")
fig2.savefig(out_pdf2, bbox_inches="tight", pad_inches=0.3, facecolor="white")
plt.close(fig2)
print(f"  -> {out_png2}")

print("\n全部完成!")
