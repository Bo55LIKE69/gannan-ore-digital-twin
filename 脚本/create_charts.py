# -*- coding: utf-8 -*-
"""
生成地图故事所需图表：
  图16 - NDVI变化趋势图
  图2  - 矿点核密度分析图
  图1  - 矿场空间分布图
  图4  - 矿种大类分布对比图
"""
import os, sys
import numpy as np
import shapefile
from collections import Counter

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
import matplotlib.ticker as mticker

BASE = r"E:\Data\赣州稀土"
OUTPUT = os.path.join(BASE, "空间分布分析结果", "图表输出")
os.makedirs(OUTPUT, exist_ok=True)

# ============================================
# 全局样式
# ============================================
plt.rcParams.update({
    'font.family': 'sans-serif',
    'font.sans-serif': ['Microsoft YaHei', 'SimHei', 'DejaVu Sans'],
    'axes.unicode_minus': False,
    'figure.dpi': 150,
    'savefig.dpi': 300,
    'savefig.bbox': 'tight',
    'savefig.pad_inches': 0.1,
})

BG_DARK = '#1a1410'
BG_CARD = '#231e18'
TEXT_PRIMARY = '#e8e0d5'
TEXT_SECONDARY = '#b8a99a'
ACCENT_GOLD = '#c4944a'
ACCENT_TEAL = '#5a8a7a'
ACCENT_COPPER = '#b8653a'
ACCENT_RED = '#c4544a'
ACCENT_GREEN = '#5a9a5a'
GRID_COLOR = '#2c2620'

# ============================================
# 图16: NDVI 变化趋势图
# ============================================
def create_ndvi_trend():
    print("[图16] NDVI变化趋势图...")

    # 从 CSV 动态读取最新 NDVI 数据
    import csv
    csv_path = os.path.join(BASE, "NDVI分析结果", "NDVI统计汇总.csv")
    years, ndvi_mean, ndvi_std, veg_cover = [], [], [], []
    with open(csv_path, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        for row in reader:
            years.append(int(row['年份']))
            ndvi_mean.append(float(row['NDVI均值']))
            ndvi_std.append(float(row['标准差']))
            veg_cover.append(float(row['植被覆盖比例(%)']))

    fig, ax1 = plt.subplots(figsize=(12, 6))
    fig.patch.set_facecolor(BG_DARK)
    ax1.set_facecolor(BG_CARD)

    # NDVI line
    ax1.plot(years, ndvi_mean, color=ACCENT_GOLD, linewidth=2.5, marker='o',
             markersize=10, markerfacecolor=ACCENT_GOLD, markeredgecolor='white',
             markeredgewidth=1.5, zorder=5, label='NDVI均值')
    ax1.fill_between(years,
                     [m - s for m, s in zip(ndvi_mean, ndvi_std)],
                     [m + s for m, s in zip(ndvi_mean, ndvi_std)],
                     color=ACCENT_GOLD, alpha=0.12)
    ax1.set_ylabel('NDVI', color=ACCENT_GOLD, fontsize=13, fontweight='bold')
    ax1.tick_params(axis='y', labelcolor=ACCENT_GOLD, colors=ACCENT_GOLD)
    ax1.set_ylim(0.45, 0.85)

    # Vegetation cover on secondary axis
    ax2 = ax1.twinx()
    ax2.plot(years, veg_cover, color=ACCENT_GREEN, linewidth=2, marker='s',
             markersize=8, markerfacecolor=ACCENT_GREEN, markeredgecolor='white',
             markeredgewidth=1, linestyle='--', zorder=4, label='植被覆盖比例')
    ax2.set_ylabel('植被覆盖比例 (%)', color=ACCENT_GREEN, fontsize=13, fontweight='bold')
    ax2.tick_params(axis='y', labelcolor=ACCENT_GREEN, colors=ACCENT_GREEN)
    ax2.set_ylim(80, 105)

    # Annotate each point
    for i, (y, v, c) in enumerate(zip(years, ndvi_mean, veg_cover)):
        offset = 0.018 if i != 4 else -0.025
        ax1.annotate(f'{v:.3f}', (y, v), textcoords="offset points",
                     xytext=(0, 12 if offset > 0 else -16), ha='center',
                     fontsize=9, color=TEXT_PRIMARY, fontweight='bold')

    # Policy annotations
    annotations = [
        (2007, 0.78, '稀土整合\n政策出台', ACCENT_COPPER),
        (2019, 0.78, '绿色矿山\n建设规范', ACCENT_TEAL),
    ]
    for x, y, text, color in annotations:
        ax1.axvline(x=x, color=color, linestyle=':', alpha=0.4, linewidth=1)
        ax1.annotate(text, (x, y), fontsize=8, color=color, ha='center',
                     bbox=dict(boxstyle='round,pad=0.3', facecolor=BG_DARK,
                               edgecolor=color, alpha=0.8))

    # Highlight 2020 dip (if 2020 is the minimum)
    min_idx = np.argmin(ndvi_mean)
    if years[min_idx] == 2020:
        ax1.annotate(f'{years[min_idx]}年NDVI最低\n植被覆盖仅{veg_cover[min_idx]:.0f}%',
                     xy=(years[min_idx], ndvi_mean[min_idx]),
                     xytext=(years[min_idx]-2.5, ndvi_mean[min_idx]-0.10),
                     arrowprops=dict(arrowstyle='->', color=ACCENT_RED, lw=1.5),
                     fontsize=9, color=ACCENT_RED, fontweight='bold')

    # Highlight 2024 recovery (if 2024 is the maximum)
    max_idx = np.argmax(ndvi_mean)
    if years[max_idx] == 2024:
        ax1.annotate(f'{years[max_idx]}年最高值',
                     xy=(years[max_idx], ndvi_mean[max_idx]),
                     xytext=(years[max_idx]-2, ndvi_mean[max_idx]+0.04),
                     arrowprops=dict(arrowstyle='->', color=ACCENT_GREEN, lw=1.5),
                     fontsize=9, color=ACCENT_GREEN, fontweight='bold')

    ax1.set_xticks(years)
    ax1.set_xlabel('年份', color=TEXT_PRIMARY, fontsize=13, fontweight='bold')
    ax1.tick_params(axis='x', colors=TEXT_SECONDARY)

    # Grid
    ax1.grid(True, alpha=0.15, color='white')
    ax1.set_xlim(1987, 2027)

    # Title
    ax1.set_title('赣州市矿山区域 NDVI 时序变化 (1990–2024)',
                  color=TEXT_PRIMARY, fontsize=16, fontweight='bold', pad=16)
    ax1.text(0.5, -0.12, '数据来源: Landsat 5 TM / Landsat 8 OLI  |  30m分辨率  |  NDVI = (NIR-Red)/(NIR+Red)',
             transform=ax1.transAxes, ha='center', fontsize=8, color=TEXT_SECONDARY)

    # Legend
    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    legend = ax1.legend(lines1 + lines2, labels1 + labels2, loc='lower left',
                        frameon=True, facecolor=BG_CARD, edgecolor=ACCENT_GOLD,
                        labelcolor=TEXT_SECONDARY, fontsize=10)
    legend.get_frame().set_alpha(0.9)

    fig.tight_layout()
    out = os.path.join(OUTPUT, '图16_NDVI变化趋势图.png')
    fig.savefig(out, facecolor=BG_DARK, edgecolor='none')
    plt.close(fig)
    print(f"  已保存: {out}")


# ============================================
# 图2: 矿山核密度分析图
# ============================================
def create_kernel_density():
    print("[图2] 矿点核密度分析图...")
    from scipy.stats import gaussian_kde
    from shapely.geometry import Point as ShpPoint

    # Load mining points
    sf_pts = shapefile.Reader(os.path.join(BASE, "空间分布分析结果", "裁剪后",
                                           "赣州矿场点_裁剪后.shp"), encoding='gbk')

    lons, lats = [], []
    for i in range(len(sf_pts.records())):
        pt = sf_pts.shape(i).points[0]
        lons.append(pt[0])
        lats.append(pt[1])
    lons = np.array(lons)
    lats = np.array(lats)

    # Load county boundary for context
    sf_county = shapefile.Reader(os.path.join(BASE, r"赣州市_360700_批量下载\县级",
                                              "县级边界_360700.shp"), encoding='gbk')

    fig, ax = plt.subplots(figsize=(12, 10))
    fig.patch.set_facecolor(BG_DARK)
    ax.set_facecolor(BG_CARD)

    # Plot county boundaries
    for i in range(len(sf_county.records())):
        shp = sf_county.shape(i)
        pts = shp.points
        parts = list(shp.parts) + [len(pts)]
        for pi in range(len(parts)-1):
            ring = np.array(pts[parts[pi]:parts[pi+1]])
            ax.plot(ring[:, 0], ring[:, 1], color='white', linewidth=0.5, alpha=0.25)

    # Kernel density estimation
    xy = np.vstack([lons, lats])
    kde = gaussian_kde(xy, bw_method='scott')

    # Create grid
    xi = np.linspace(lons.min()-0.1, lons.max()+0.1, 300)
    yi = np.linspace(lats.min()-0.1, lats.max()+0.1, 300)
    xi_grid, yi_grid = np.meshgrid(xi, yi)
    zi = kde(np.vstack([xi_grid.ravel(), yi_grid.ravel()])).reshape(xi_grid.shape)

    # Plot density
    from matplotlib.colors import LinearSegmentedColormap
    colors = ['#1a1410', '#2c1a0a', '#5c3a1a', '#8a5a2a', '#c4944a', '#e8c87a', '#ffe8a0']
    cmap = LinearSegmentedColormap.from_list('mineral_density', colors, N=256)

    im = ax.pcolormesh(xi_grid, yi_grid, zi, cmap=cmap, shading='auto',
                       alpha=0.85, rasterized=True)

    # County boundaries on top
    for i in range(len(sf_county.records())):
        shp = sf_county.shape(i)
        pts = shp.points
        parts = list(shp.parts) + [len(pts)]
        for pi in range(len(parts)-1):
            ring = np.array(pts[parts[pi]:parts[pi+1]])
            ax.plot(ring[:, 0], ring[:, 1], color='white', linewidth=0.6, alpha=0.35)

    # Key mining towns
    key_towns = {
        '崇义县': (114.30, 25.68),
        '大余县': (114.36, 25.40),
        '上犹县': (114.55, 25.79),
        '于都县': (115.41, 25.95),
        '龙南市': (114.79, 24.91),
        '章贡区': (114.93, 25.83),
    }
    from shapely.geometry import Point, Polygon
    county_centers = {}
    for i in range(len(sf_county.records())):
        name = sf_county.record(i)[2]
        shp = sf_county.shape(i)
        pts = np.array(shp.points)
        cx, cy = np.mean(pts[:, 0]), np.mean(pts[:, 1])
        county_centers[name] = (cx, cy)

    for name, (cx, cy) in county_centers.items():
        ax.annotate(name, (cx, cy), fontsize=7, color='white', ha='center', va='center',
                    alpha=0.7, fontweight='bold')

    # Colorbar
    cbar = fig.colorbar(im, ax=ax, shrink=0.82, pad=0.02)
    cbar.set_label('核密度', color=TEXT_PRIMARY, fontsize=11, fontweight='bold')
    cbar.ax.tick_params(colors=TEXT_SECONDARY)
    cbar.outline.set_edgecolor(TEXT_SECONDARY)

    ax.set_xlabel('经度 (°E)', color=TEXT_PRIMARY, fontsize=12)
    ax.set_ylabel('纬度 (°N)', color=TEXT_PRIMARY, fontsize=12)
    ax.tick_params(colors=TEXT_SECONDARY, labelsize=8)

    ax.set_title('赣州市矿场点核密度分析', color=TEXT_PRIMARY, fontsize=16,
                 fontweight='bold', pad=14)
    ax.text(0.5, -0.06, f'共{len(lons)}个矿点  |  带宽: Scott自适应  |  WGS84坐标系',
            transform=ax.transAxes, ha='center', fontsize=8, color=TEXT_SECONDARY)

    ax.set_aspect('equal')
    fig.tight_layout()
    out = os.path.join(OUTPUT, '图2_矿点核密度分析图.png')
    fig.savefig(out, facecolor=BG_DARK, edgecolor='none')
    plt.close(fig)
    print(f"  已保存: {out}")


# ============================================
# 图1: 矿场空间分布图
# ============================================
def create_mineral_distribution():
    print("[图1] 矿场空间分布图...")

    sf_pts = shapefile.Reader(os.path.join(BASE, "空间分布分析结果", "裁剪后",
                                           "赣州矿场点_裁剪后.shp"), encoding='gbk')
    sf_county = shapefile.Reader(os.path.join(BASE, r"赣州市_360700_批量下载\县级",
                                              "县级边界_360700.shp"), encoding='gbk')

    # Collect points by mineral category
    MINERAL_CATEGORY_MAP = {
        '铁矿': '黑色金属', '锰矿': '黑色金属', '钛矿': '黑色金属',
        '铜矿': '有色金属', '铅矿': '有色金属', '锌矿': '有色金属',
        '钨矿': '有色金属', '锡矿': '有色金属', '钼矿': '有色金属',
        '铋矿': '有色金属', '钴矿': '有色金属',
        '金矿': '贵金属', '砂金': '贵金属', '银矿': '贵金属',
        '钽矿': '稀有金属', '铌矿': '稀有金属', '铍矿': '稀有金属',
        '锆矿': '稀有金属', '铪矿': '稀有金属',
        '稀土矿': '稀土金属', '磷钇矿': '稀土金属', '钇矿': '稀土金属',
    }

    flds = [f[0] for f in sf_pts.fields[1:]]
    kz_idx = flds.index('kz')

    cat_colors = {
        '黑色金属': '#6a8a9a',
        '有色金属': '#c4944a',
        '贵金属': '#e8c84a',
        '稀有金属': '#c4544a',
        '稀土金属': '#5a9a7a',
        '非金属': '#8a7c6e',
    }
    cat_points = {k: ([], []) for k in cat_colors}
    cat_counts = Counter()

    for i in range(len(sf_pts.records())):
        rec = sf_pts.record(i)
        kz = rec[kz_idx]
        cat = MINERAL_CATEGORY_MAP.get(kz, '非金属')
        pt = sf_pts.shape(i).points[0]
        cat_points[cat][0].append(pt[0])
        cat_points[cat][1].append(pt[1])
        cat_counts[cat] += 1

    fig, ax = plt.subplots(figsize=(14, 12))
    fig.patch.set_facecolor(BG_DARK)
    ax.set_facecolor(BG_CARD)

    # County boundaries
    for i in range(len(sf_county.records())):
        shp = sf_county.shape(i)
        pts = shp.points
        parts = list(shp.parts) + [len(pts)]
        for pi in range(len(parts)-1):
            ring = np.array(pts[parts[pi]:parts[pi+1]])
            ax.fill(ring[:, 0], ring[:, 1], color='white', alpha=0.03,
                    edgecolor='white', linewidth=0.5)

    # Plot points by category
    legend_handles = []
    zorder_map = {'有色金属': 5, '黑色金属': 4, '稀有金属': 3, '稀土金属': 2, '贵金属': 2, '非金属': 1}
    for cat in sorted(cat_points.keys(), key=lambda c: zorder_map.get(c, 0)):
        lons, lats = cat_points[cat]
        if len(lons) > 0:
            ax.scatter(lons, lats, s=18, c=cat_colors[cat], alpha=0.85,
                       edgecolors='white', linewidth=0.2, zorder=zorder_map.get(cat, 1),
                       label=f'{cat} ({cat_counts[cat]}个)')

    # County labels
    for i in range(len(sf_county.records())):
        name = sf_county.record(i)[2]
        shp = sf_county.shape(i)
        pts = np.array(shp.points)
        cx, cy = np.mean(pts[:, 0]), np.mean(pts[:, 1])
        ax.annotate(name, (cx, cy), fontsize=8, color='white', ha='center',
                    va='center', alpha=0.55, fontweight='bold',
                    bbox=dict(boxstyle='round,pad=0.2', facecolor=BG_DARK,
                              edgecolor='none', alpha=0.4))

    ax.set_xlabel('经度 (°E)', color=TEXT_PRIMARY, fontsize=12)
    ax.set_ylabel('纬度 (°N)', color=TEXT_PRIMARY, fontsize=12)
    ax.tick_params(colors=TEXT_SECONDARY, labelsize=8)
    ax.set_title('赣州市矿场空间分布图', color=TEXT_PRIMARY, fontsize=18,
                 fontweight='bold', pad=14)
    ax.text(0.5, -0.04, f'共474个矿场点  |  数据来源: 全国矿产地分布数据(2025)  |  WGS84',
            transform=ax.transAxes, ha='center', fontsize=8, color=TEXT_SECONDARY)

    legend = ax.legend(frameon=True, facecolor=BG_CARD, edgecolor=ACCENT_GOLD,
                       labelcolor=TEXT_PRIMARY, fontsize=10, loc='lower right',
                       title='矿种大类', title_fontsize=11)
    legend.get_frame().set_alpha(0.9)
    legend.get_title().set_color(TEXT_PRIMARY)

    ax.set_aspect('equal')
    fig.tight_layout()
    out = os.path.join(OUTPUT, '图1_矿场空间分布图.png')
    fig.savefig(out, facecolor=BG_DARK, edgecolor='none')
    plt.close(fig)
    print(f"  已保存: {out}")


# ============================================
# 图4: 矿种大类分布对比图 (分面地图)
# ============================================
def create_mineral_facet_map():
    print("[图4] 矿种大类分面对比图...")

    sf_pts = shapefile.Reader(os.path.join(BASE, "空间分布分析结果", "裁剪后",
                                           "赣州矿场点_裁剪后.shp"), encoding='gbk')
    sf_county = shapefile.Reader(os.path.join(BASE, r"赣州市_360700_批量下载\县级",
                                              "县级边界_360700.shp"), encoding='gbk')

    MINERAL_CATEGORY_MAP = {
        '铁矿': '黑色金属', '锰矿': '黑色金属', '钛矿': '黑色金属',
        '铜矿': '有色金属', '铅矿': '有色金属', '锌矿': '有色金属',
        '钨矿': '有色金属', '锡矿': '有色金属', '钼矿': '有色金属',
        '铋矿': '有色金属', '钴矿': '有色金属',
        '金矿': '贵金属', '砂金': '贵金属', '银矿': '贵金属',
        '钽矿': '稀有金属', '铌矿': '稀有金属', '铍矿': '稀有金属',
        '锆矿': '稀有金属', '铪矿': '稀有金属',
        '稀土矿': '稀土金属', '磷钇矿': '稀土金属', '钇矿': '稀土金属',
    }

    flds = [f[0] for f in sf_pts.fields[1:]]
    kz_idx = flds.index('kz')

    categories = ['有色金属', '黑色金属', '稀有金属', '稀土金属', '贵金属', '非金属']
    cat_colors_map = {
        '有色金属': '#c4944a',
        '黑色金属': '#6a8a9a',
        '稀有金属': '#c4544a',
        '稀土金属': '#5a9a7a',
        '贵金属': '#e8c84a',
        '非金属': '#8a7c6e',
    }

    # Collect points
    cat_points_data = {c: ([], []) for c in categories}
    cat_counts_data = Counter()
    for i in range(len(sf_pts.records())):
        kz = sf_pts.record(i)[kz_idx]
        cat = MINERAL_CATEGORY_MAP.get(kz, '非金属')
        pt = sf_pts.shape(i).points[0]
        cat_points_data[cat][0].append(pt[0])
        cat_points_data[cat][1].append(pt[1])
        cat_counts_data[cat] += 1

    # Pre-extract county boundary rings
    county_rings = []
    for i in range(len(sf_county.records())):
        shp = sf_county.shape(i)
        pts = shp.points
        parts = list(shp.parts) + [len(pts)]
        for pi in range(len(parts)-1):
            county_rings.append(pts[parts[pi]:parts[pi+1]])

    fig, axes = plt.subplots(2, 3, figsize=(18, 14))
    fig.patch.set_facecolor(BG_DARK)

    for ax, cat in zip(axes.flat, categories):
        ax.set_facecolor(BG_CARD)

        # County boundaries
        for ring in county_rings:
            ring_arr = np.array(ring)
            ax.fill(ring_arr[:, 0], ring_arr[:, 1], color='white', alpha=0.03,
                    edgecolor='white', linewidth=0.3)

        # Points
        lons, lats = cat_points_data[cat]
        if len(lons) > 0:
            ax.scatter(lons, lats, s=20, c=cat_colors_map[cat], alpha=0.8,
                       edgecolors='white', linewidth=0.3, zorder=5)

        ax.set_title(f'{cat}\n({cat_counts_data[cat]}个矿点)', color=cat_colors_map[cat],
                     fontsize=13, fontweight='bold', pad=8)
        ax.tick_params(colors=TEXT_SECONDARY, labelsize=6)
        ax.set_aspect('equal')

    # Main title
    fig.suptitle('赣州市不同矿种大类空间分布对比', color=TEXT_PRIMARY,
                 fontsize=18, fontweight='bold', y=0.98)

    # Remove empty subplot if odd number
    # (2x3 = 6 categories, perfect)

    fig.tight_layout(rect=[0, 0, 1, 0.95])
    out = os.path.join(OUTPUT, '图4_矿种大类分面对比图.png')
    fig.savefig(out, facecolor=BG_DARK, edgecolor='none')
    plt.close(fig)
    print(f"  已保存: {out}")


# ============================================
# 附加: 矿种数量统计条形图
# ============================================
def create_mineral_bar_chart():
    print("[附加] 矿种数量统计图...")

    sf_pts = shapefile.Reader(os.path.join(BASE, "空间分布分析结果", "裁剪后",
                                           "赣州矿场点_裁剪后.shp"), encoding='gbk')
    flds = [f[0] for f in sf_pts.fields[1:]]
    kz_idx = flds.index('kz')

    kz_counts = Counter()
    for i in range(len(sf_pts.records())):
        kz = sf_pts.record(i)[kz_idx]
        kz_counts[kz] += 1

    # Top 15 minerals
    top15 = kz_counts.most_common(15)
    names = [n for n, _ in reversed(top15)]
    counts = [c for _, c in reversed(top15)]

    fig, ax = plt.subplots(figsize=(10, 7))
    fig.patch.set_facecolor(BG_DARK)
    ax.set_facecolor(BG_CARD)

    # Color gradient based on count
    max_c = max(counts)
    bar_colors = []
    for n, c in zip(names, counts):
        if '钨' in n:
            bar_colors.append('#c4944a')
        elif '铁' in n:
            bar_colors.append('#6a8a9a')
        elif any(w in n for w in ['稀土', '磷钇']):
            bar_colors.append('#5a9a7a')
        elif any(w in n for w in ['铅', '锌', '铜', '锡']):
            bar_colors.append('#b8653a')
        elif any(w in n for w in ['金', '银']):
            bar_colors.append('#e8c84a')
        elif '钽' in n:
            bar_colors.append('#c4544a')
        else:
            bar_colors.append('#8a7c6e')

    bars = ax.barh(names, counts, color=bar_colors, height=0.7, edgecolor='white',
                   linewidth=0.3, alpha=0.9)

    # Value labels
    for bar, c in zip(bars, reversed(counts)):
        ax.text(bar.get_width() + 1, bar.get_y() + bar.get_height()/2,
                str(c), va='center', fontsize=9, color=TEXT_PRIMARY, fontweight='bold')

    ax.set_xlabel('矿点数量', color=TEXT_PRIMARY, fontsize=12)
    ax.tick_params(colors=TEXT_SECONDARY, labelsize=10)
    ax.set_title('赣州市主要矿种数量统计 (Top 15)', color=TEXT_PRIMARY,
                 fontsize=15, fontweight='bold', pad=14)
    ax.set_xlim(0, max_c * 1.15)
    ax.grid(axis='x', alpha=0.1, color='white')

    fig.tight_layout()
    out = os.path.join(OUTPUT, '附加_矿种数量统计图.png')
    fig.savefig(out, facecolor=BG_DARK, edgecolor='none')
    plt.close(fig)
    print(f"  已保存: {out}")


# ============================================
# Main
# ============================================
if __name__ == '__main__':
    print("=" * 50)
    print("生成地图故事图表")
    print("=" * 50)
    try:
        create_ndvi_trend()
    except Exception as e:
        print(f"  图16失败: {e}")
        import traceback; traceback.print_exc()

    try:
        create_kernel_density()
    except Exception as e:
        print(f"  图2失败: {e}")
        import traceback; traceback.print_exc()

    try:
        create_mineral_distribution()
    except Exception as e:
        print(f"  图1失败: {e}")
        import traceback; traceback.print_exc()

    try:
        create_mineral_facet_map()
    except Exception as e:
        print(f"  图4失败: {e}")
        import traceback; traceback.print_exc()

    try:
        create_mineral_bar_chart()
    except Exception as e:
        print(f"  附加图失败: {e}")
        import traceback; traceback.print_exc()

    print(f"\n所有图表已保存到: {OUTPUT}")
    for f in sorted(os.listdir(OUTPUT)):
        size = os.path.getsize(os.path.join(OUTPUT, f))
        print(f"  {f} ({size:,} bytes)")
