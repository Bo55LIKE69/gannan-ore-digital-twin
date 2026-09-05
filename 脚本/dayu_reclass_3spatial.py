# -*- coding: utf-8 -*-
"""
大余县 CLCD -> 三生空间 重分类 + 时空演化分析
输入: 数据/大余县/CLCD_dayu/CLCD_v01_YYYY_dayu.tif (CLCD 1-9 类)
输出:
  数据/大余县/3spatial/CLCD_v01_YYYY_3spatial.tif  (1=生产 2=生活 3=生态 0=背景)
  数据/大余县/stats/area_by_year.csv               各期三生面积(km2)
  数据/大余县/stats/transition_YYYY_YYYY.csv       相邻/指定年份转移矩阵
映射(参考焦庚英等 自然资源学报2021, 可据论文定义微调):
  生产空间(1): 耕地(1)
  生活空间(2): 人工表面(9)
  生态空间(3): 森林(2)灌木(3)草地(4)水体(5)冰雪(6)裸地(7)湿地(8)
"""
import os, glob, csv, numpy as np
import rasterio

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DAYU = os.path.join(BASE, "数据", "大余县", "CLCD_dayu")
OUT = os.path.join(BASE, "数据", "大余县", "3spatial"); os.makedirs(OUT, exist_ok=True)
STAT = os.path.join(BASE, "数据", "大余县", "stats"); os.makedirs(STAT, exist_ok=True)

REMAP = {1: 1, 9: 2, 2: 3, 3: 3, 4: 3, 5: 3, 6: 3, 7: 3, 8: 3}
LABELS = {1: "生产空间", 2: "生活空间", 3: "生态空间"}
PX_KM2 = 900.0 / 1e6  # 30m 分辨率单像素面积 km2

def load_years():
    files = sorted(glob.glob(os.path.join(DAYU, "CLCD_v01_*_dayu.tif")))
    yrs = []
    for f in files:
        y = int(os.path.basename(f).split("_")[2])
        yrs.append((y, f))
    return sorted(yrs)

def reclass_all():
    arrs = {}
    print("=== 重分类 + 面积统计 ===")
    area_rows = [("year", "生产空间_km2", "生活空间_km2", "生态空间_km2", "有效像素")]
    for y, f in load_years():
        with rasterio.open(f) as ds:
            a = ds.read(1)
            meta = ds.meta.copy()
        out = np.zeros(a.shape, np.uint8)
        for k, v in REMAP.items():
            out[a == k] = v
        arrs[y] = out
        op = os.path.join(OUT, f"CLCD_v01_{y}_3spatial.tif")
        m = meta.copy(); m.update(dtype="uint8", compress="LZW", nodata=0)
        with rasterio.open(op, "w", **m) as d:
            d.write(out, 1)
        n = {v: int((out == v).sum()) for v in (1, 2, 3)}
        tot = int((out > 0).sum())
        print(f"  {y}: 生产{n[1]*PX_KM2:.1f}  生活{n[2]*PX_KM2:.1f}  生态{n[3]*PX_KM2:.1f}  km2 (有效 {tot}px)")
        area_rows.append((y, round(n[1]*PX_KM2, 2), round(n[2]*PX_KM2, 2), round(n[3]*PX_KM2, 2), tot))
    with open(os.path.join(STAT, "area_by_year.csv"), "w", newline="", encoding="utf-8") as fp:
        csv.writer(fp).writerows(area_rows)
    return arrs

def transition(y1, y2, arrs):
    a = arrs[y1].ravel(); b = arrs[y2].ravel()
    valid = (a > 0) & (b > 0)
    a, b = a[valid], b[valid]
    M = np.zeros((3, 3), dtype=np.int64)
    for x, yv in zip(a, b):
        M[x - 1, yv - 1] += 1
    rows = [["from\\to"] + [LABELS[i] for i in (1, 2, 3)]]
    for i in (1, 2, 3):
        rows.append([LABELS[i]] + [int(M[i-1, j-1]) for j in (1, 2, 3)])
    # 行比例(%)
    rows.append([])
    rows.append(["行比例%"] + [""] * 3)
    for i in (1, 2, 3):
        tot = M[i-1].sum()
        rows.append([LABELS[i]] + [round(100*M[i-1, j-1]/tot, 2) if tot else 0 for j in (1, 2, 3)])
    fn = os.path.join(STAT, f"transition_{y1}_{y2}.csv")
    with open(fn, "w", newline="", encoding="utf-8") as fp:
        csv.writer(fp).writerows(rows)
    print(f"  转移矩阵 {y1}->{y2} 已写 {fn}")
    return M

def main():
    arrs = reclass_all()
    yrs = sorted(arrs.keys())
    print("\n=== 转移矩阵 ===")
    for i in range(len(yrs) - 1):
        transition(yrs[i], yrs[i+1], arrs)
    # 首末总转移
    transition(yrs[0], yrs[-1], arrs)
    print("\nDONE ->", OUT, STAT)

if __name__ == "__main__":
    main()
