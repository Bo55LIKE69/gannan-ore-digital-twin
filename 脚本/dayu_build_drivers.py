# -*- coding: utf-8 -*-
"""
大余县 PLUS 模型驱动因子栅格生成
依赖: rasterio, scipy, pyproj, numpy (刻意避开 geopandas, 因环境 numpy2 与 geopandas/pyarrow 编译版本冲突)
基准网格: 用 CLCD_dayu/CLCD_v01_1990_dayu.tif 的 profile(分辨率/范围/投影与 CLCD 完全一致)
输出: 数据/大余县/drivers/
  dist_mine.tif   距最近矿点距离(m)
  kde_mine.tif    矿点核密度(高斯滤波, 标准化0-1)
  mine_weight.tif 矿点规模加权密度(标准化0-1)
  dem/slope/aspect.tif  地形因子(从 ganzhou_dem/slope/aspect 重采样对齐, 处理nodata)
"""
import os, csv, io, json, warnings
import numpy as np
import rasterio
from rasterio.warp import reproject, Resampling
from scipy.ndimage import distance_transform_edt, gaussian_filter
import pyproj

warnings.filterwarnings("ignore")
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BOUND_GEO = os.path.join(BASE, "boundary", "dayu_boundary.geojson")
CSV = os.path.join(BASE, "数据", "全国矿产地分布", "原始数据", "全国矿产地分布数据.csv")
DAYU = os.path.join(BASE, "数据", "大余县", "CLCD_dayu")
DRV = os.path.join(BASE, "数据", "大余县", "drivers"); os.makedirs(DRV, exist_ok=True)
DEM_DIR = os.path.join(BASE, "数据", "DEM")

def get_base():
    base_tif = os.path.join(DAYU, "CLCD_v01_1990_dayu.tif")
    if not os.path.exists(base_tif):
        raise SystemExit(f"基准 grid 缺失: {base_tif}，请先完成 CLCD 1990 裁切")
    with rasterio.open(base_tif) as ds:
        return ds.profile, ds.transform, ds.height, ds.width, ds.crs

def build_mine_factors(transform, H, W, crs):
    rows = list(csv.DictReader(io.open(CSV, encoding="utf-8-sig", errors="replace")))
    dy = [r for r in rows if "大余" in str(r)]
    pts = [(float(r["lon"]), float(r["lat"]), r) for r in dy if r.get("lon")]
    transformer = pyproj.Transformer.from_crs("EPSG:4326", crs.to_wkt(), always_xy=True)
    xs, ys = transformer.transform([p[0] for p in pts], [p[1] for p in pts])
    cols = np.array([int(round((x - transform.c) / transform.a)) for x in xs])
    rws = np.array([int(round((y - transform.f) / transform.e)) for y in ys])
    mine = np.zeros((H, W), np.float32)
    valid = [(c, r, rec) for (c, r), rec in zip(zip(cols, rws), [p[2] for p in pts])
             if 0 <= c < W and 0 <= r < H]
    for c, r, _ in valid:
        mine[r, c] = 1.0
    print(f"  [矿点] 有效落点 {len(valid)}/{len(pts)} 个")
    # 关键修正: edt 计算每个像素到最近矿点(=0)的距离, 故背景置1、矿点置0
    dist = distance_transform_edt(1.0 - mine, sampling=[abs(transform.e), transform.a]).astype(np.float32)
    kde = gaussian_filter(mine, sigma=5).astype(np.float32)
    kde = (kde - kde.min()) / (kde.max() - kde.min() + 1e-9)
    wmap = {"大型矿床": 3.0, "中型矿床": 2.0, "小型矿床": 1.0, "矿点": 0.5}
    wgrid = np.zeros((H, W), np.float32)
    for c, r, rec in valid:
        wgrid[r, c] = wmap.get(rec.get("kcgm", ""), 0.5)
    wsum = gaussian_filter(wgrid, sigma=5).astype(np.float32)
    wsum = (wsum - wsum.min()) / (wsum.max() - wsum.min() + 1e-9)
    return {"dist_mine": dist, "kde_mine": kde, "mine_weight": wsum}

def reproject_dem(src_path, name, transform, H, W, crs):
    with rasterio.open(src_path) as src:
        src_nd = src.nodata
        if src_nd is None:
            src_nd = -32768 if src.dtypes[0] == "int16" else -9999
        dst = np.full((H, W), -9999, np.float32)
        reproject(source=rasterio.band(src, 1), destination=dst,
                  src_transform=src.transform, src_crs=src.crs, src_nodata=src_nd,
                  dst_transform=transform, dst_crs=crs, dst_nodata=-9999,
                  resampling=Resampling.bilinear)
    return {name: dst}

def main():
    profile, transform, H, W, crs = get_base()
    out_profile = profile.copy()
    out_profile.update(dtype="float32", count=1, nodata=-9999, compress="LZW")
    print(f"基准 grid: {W}x{H}, crs={crs}, 分辨率={transform.a:.1f}m")
    factors = {}
    print("构建矿点驱动因子...")
    factors.update(build_mine_factors(transform, H, W, crs))
    print("重采样地形因子...")
    for fn, nm in [("ganzhou_dem.tif", "dem"), ("ganzhou_slope.tif", "slope"), ("ganzhou_aspect.tif", "aspect")]:
        p = os.path.join(DEM_DIR, fn)
        if os.path.exists(p):
            factors.update(reproject_dem(p, nm, transform, H, W, crs))
        else:
            print("  缺少", p)
    for name, arr in factors.items():
        op = os.path.join(DRV, name + ".tif")
        with rasterio.open(op, "w", **out_profile) as d:
            d.write(arr, 1)
        print(f"  写出 {name}: {os.path.getsize(op)/1e6:.2f}MB")
    print("DRIVERS DONE ->", DRV)

if __name__ == "__main__":
    main()
