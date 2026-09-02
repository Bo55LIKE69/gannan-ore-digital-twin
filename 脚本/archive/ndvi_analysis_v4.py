# -*- coding: utf-8 -*-
"""
赣州多年 NDVI 计算 v4 —— 修复版

修复:
  1. window() 经纬度顺序: window(left, bottom, right, top)，之前 bottom/top 写反
  2. QA 波段重采样 NaN: 用 nan_to_num 安全转换
  3. 按 path 分组选景，确保全城覆盖

数据源: Microsoft Planetary Computer → Landsat C2 L2
输出: EPSG:4326, ~30m, GeoTIFF
"""

import os, sys, json, time
import numpy as np
import rasterio
from rasterio.transform import from_bounds
from rasterio.crs import CRS
from rasterio.warp import transform_bounds, reproject, Resampling
from rasterio.features import geometry_mask
from shapely.geometry import shape
from shapely.ops import unary_union
from pystac_client import Client
import planetary_computer as pc
import warnings
warnings.filterwarnings('ignore')

BASE = r"E:\Data\赣州稀土"
OUTPUT = os.path.join(BASE, "NDVI分析结果")
os.makedirs(OUTPUT, exist_ok=True)

# ============================================================
# 加载赣州边界
# ============================================================
CITY_GEOJSON = os.path.join(BASE, "赣州市_360700_批量下载", "市级", "赣州市_360700.geojson")
with open(CITY_GEOJSON, 'r', encoding='utf-8') as f:
    city_data = json.load(f)

city_polys = []
for feat in city_data['features']:
    geom = shape(feat['geometry'])
    city_polys.extend(list(geom.geoms) if geom.geom_type == 'MultiPolygon' else [geom])
city_geom = unary_union(city_polys)
cb = city_geom.bounds
print(f"赣州范围: {cb[0]:.4f}~{cb[2]:.4f}E, {cb[1]:.4f}~{cb[3]:.4f}N")

# ============================================================
# 参数
# ============================================================
PAD = 0.15
SEARCH_BBOX = [cb[0]-PAD, cb[1]-PAD, cb[2]+PAD, cb[3]+PAD]

RES = 0.0003  # ~30m at this latitude
OUT_WIDTH  = int((cb[2] - cb[0]) / RES) + 1
OUT_HEIGHT = int((cb[3] - cb[1]) / RES) + 1
OUT_TRANSFORM = from_bounds(cb[0], cb[1], cb[2], cb[3], OUT_WIDTH, OUT_HEIGHT)
NODATA = np.float32(-9999)

print(f"输出网格: {OUT_WIDTH}x{OUT_HEIGHT} ({OUT_WIDTH*OUT_HEIGHT/1e6:.1f}M px)")

# ============================================================
# MPC 连接
# ============================================================
print("连接 MPC...")
for attempt in range(5):
    try:
        catalog = Client.open(
            "https://planetarycomputer.microsoft.com/api/stac/v1",
            modifier=pc.sign_inplace
        )
        print("MPC 已连接\n")
        break
    except Exception as e:
        if attempt < 4:
            time.sleep((attempt+1)*15)
        else:
            raise

# ============================================================
# Landsat 参数
# ============================================================
YEARS = [1990, 2000, 2010, 2015, 2020, 2024]
YEAR_PLATFORMS = {
    1990: ["landsat-5"],
    2000: ["landsat-5", "landsat-7"],
    2010: ["landsat-5", "landsat-7"],
    2015: ["landsat-8"],
    2020: ["landsat-8"],
    2024: ["landsat-8", "landsat-9"],
}

SR_SCALE  = 0.0000275
SR_OFFSET = -0.2

# QA 位掩码 (Landsat C2 Level-2)
QA_FILL          = 1 << 0
QA_DILATED_CLOUD = 1 << 1
QA_CIRRUS        = 1 << 2
QA_CLOUD         = 1 << 3
QA_CLOUD_SHADOW  = 1 << 4
QA_BAD = QA_FILL | QA_DILATED_CLOUD | QA_CLOUD | QA_CLOUD_SHADOW


def safe_cloud_mask(qa_arr):
    """安全云掩膜：处理重采样可能产生的 NaN/float"""
    # 转 float32 后 NaN→1 (标记为云), 再转 uint16 做位运算
    arr = np.asarray(qa_arr, dtype=np.float32)
    arr = np.nan_to_num(arr, nan=1.0, posinf=1.0, neginf=1.0)
    arr = arr.astype(np.uint16)
    return (arr & QA_BAD) == 0


def ndvi_from_sr(nir, red):
    """地表反射率 → NDVI"""
    nir_sr = (nir.astype(np.float32) * SR_SCALE + SR_OFFSET).clip(0, 1)
    red_sr = (red.astype(np.float32) * SR_SCALE + SR_OFFSET).clip(0, 1)
    return ((nir_sr - red_sr) / (nir_sr + red_sr + 1e-8)).clip(-1, 1)


def search_mpc(bbox, dt, platforms, cc_max, max_items):
    """搜索 Landsat 场景"""
    for attempt in range(3):
        try:
            s = catalog.search(
                collections=["landsat-c2-l2"],
                bbox=bbox, datetime=dt,
                query={"platform": {"in": platforms}, "eo:cloud_cover": {"lt": cc_max}},
                max_items=max_items
            )
            return list(s.items())
        except Exception as e:
            if attempt < 2:
                time.sleep((attempt+1)*8)
            else:
                raise
    return []


def process_scene(item):
    """处理单景 Landsat → 全网格 NDVI"""
    nir_url = pc.sign(item.assets['nir08'].href)
    red_url = pc.sign(item.assets['red'].href)
    qa_url  = pc.sign(item.assets['qa_pixel'].href) if 'qa_pixel' in item.assets else None

    with rasterio.open(nir_url) as nir_src:
        sc_crs = nir_src.crs

        # 场景在 WGS84 下的范围
        if sc_crs and sc_crs != CRS.from_epsg(4326):
            sc_b_wgs = transform_bounds(sc_crs, CRS.from_epsg(4326), *nir_src.bounds)
        else:
            sc_b_wgs = nir_src.bounds

        # 与搜索区域的交集 (WGS84)
        ol_left   = max(SEARCH_BBOX[0], sc_b_wgs[0])
        ol_bottom = max(SEARCH_BBOX[1], sc_b_wgs[1])
        ol_right  = min(SEARCH_BBOX[2], sc_b_wgs[2])
        ol_top    = min(SEARCH_BBOX[3], sc_b_wgs[3])

        if ol_left >= ol_right or ol_bottom >= ol_top:
            return None

        # 计算读取窗口 (注意: window() 参数是 left, bottom, right, top)
        if sc_crs and sc_crs != CRS.from_epsg(4326):
            ol_proj = transform_bounds(CRS.from_epsg(4326), sc_crs, ol_left, ol_bottom, ol_right, ol_top)
            window = nir_src.window(ol_proj[0], ol_proj[1], ol_proj[2], ol_proj[3])
        else:
            # FIX: 正确的顺序是 left, bottom, right, top
            window = nir_src.window(ol_left, ol_bottom, ol_right, ol_top)

        ww, wh = int(window.width), int(window.height)
        max_dim = 4000
        scale = min(1.0, max_dim / max(ww, wh))
        ow, oh = max(10, int(ww * scale)), max(10, int(wh * scale))

        # 读取 NIR + Red
        with rasterio.open(red_url) as red_src:
            nir_arr = nir_src.read(1, window=window, out_shape=(oh, ow))
            red_arr = red_src.read(1, window=window, out_shape=(oh, ow))

        # nodata → NaN
        if nir_src.nodata is not None:
            nir_arr = np.where(nir_arr == nir_src.nodata, np.nan, nir_arr)
        if red_src.nodata is not None:
            red_arr = np.where(red_arr == red_src.nodata, np.nan, red_arr)

        # 云掩膜
        if qa_url:
            with rasterio.open(qa_url) as qa_src:
                qa_arr = qa_src.read(1, window=window, out_shape=(oh, ow))
            clear = safe_cloud_mask(qa_arr)
            nir_arr = np.where(clear, nir_arr, np.nan)
            red_arr = np.where(clear, red_arr, np.nan)

        # NDVI
        ndvi_arr = ndvi_from_sr(nir_arr, red_arr)

        # 源数据 transform (用于 reproject)
        src_tf = nir_src.window_transform(window)
        src_tf = src_tf * src_tf.scale(ww / ow, wh / oh)

    # Reproject 到统一 WGS84 网格
    out = np.full((OUT_HEIGHT, OUT_WIDTH), np.nan, dtype=np.float32)
    reproject(
        source=ndvi_arr, destination=out,
        src_transform=src_tf, src_crs=sc_crs,
        dst_transform=OUT_TRANSFORM, dst_crs=CRS.from_epsg(4326),
        src_nodata=np.nan, dst_nodata=np.nan,
        resampling=Resampling.bilinear
    )
    return out


# ============================================================
# 主处理循环
# ============================================================
for year in YEARS:
    out_path = os.path.join(OUTPUT, f"赣州_NDVI_{year}_wgs84.tif")
    if os.path.exists(out_path) and os.path.getsize(out_path) > 2 * 1024 * 1024:
        print(f"[{year}] 已存在，跳过\n")
        continue
    elif os.path.exists(out_path):
        os.remove(out_path)

    print(f"{'='*60}")
    print(f"[{year}] 搜索 Landsat 影像...")

    platforms = YEAR_PLATFORMS.get(year, ["landsat-8"])

    # 搜索
    items = search_mpc(SEARCH_BBOX, f"{year}-04-01/{year}-10-31", platforms, 50, 300)

    if len(items) < 20:
        print(f"  仅 {len(items)} 景，放宽云量阈值...")
        items2 = search_mpc(SEARCH_BBOX, f"{year}-03-01/{year}-11-30", platforms, 70, 300)
        ids = {it.id for it in items}
        for it in items2:
            if it.id not in ids:
                items.append(it)
                ids.add(it.id)

    print(f"  搜索到 {len(items)} 景")

    # 筛选与城市相交，按 path 分组
    path_groups = {}
    for item in items:
        try:
            item_geom = shape(item.geometry) if item.geometry else None
            if not item_geom or not item_geom.intersects(city_geom):
                continue
        except Exception:
            continue
        pp = item.properties.get('landsat:wrs_path', 'unknown')
        path_groups.setdefault(pp, []).append(item)

    n_city = sum(len(v) for v in path_groups.values())
    print(f"  城市相交: {n_city} 景, path: {sorted(path_groups.keys())}")

    if n_city == 0:
        print(f"  [{year}] 无数据\n")
        continue

    # 每 path 选云量最低的 N 景
    selected = []
    per_path = 15
    for pp, grp in path_groups.items():
        grp.sort(key=lambda x: x.properties.get('eo:cloud_cover', 100))
        selected.extend(grp[:per_path])

    # 去重
    seen = set()
    selected = [s for s in selected if not (s.id in seen or seen.add(s.id))]
    selected.sort(key=lambda x: x.properties.get('eo:cloud_cover', 100))
    selected = selected[:80]

    from collections import Counter
    pcnt = Counter(s.properties.get('landsat:wrs_path', '?') for s in selected)
    print(f"  选中 {len(selected)} 景: {dict(pcnt)}")

    # 增量均值合成
    ndvi_sum   = np.zeros((OUT_HEIGHT, OUT_WIDTH), dtype=np.float64)
    ndvi_count = np.zeros((OUT_HEIGHT, OUT_WIDTH), dtype=np.int32)
    n_ok = 0

    t0 = time.time()
    for idx, item in enumerate(selected):
        try:
            arr = process_scene(item)
            if arr is None:
                continue
            valid = ~np.isnan(arr)
            ndvi_sum[valid]   += arr[valid].astype(np.float64)
            ndvi_count[valid] += 1
            n_ok += 1
        except Exception as e:
            if idx < 5:
                print(f"  场景[{idx}] {item.id[:30]} 失败: {e}")
            continue

        if (idx + 1) % 15 == 0:
            elapsed = time.time() - t0
            sys.stdout.write(f"\r  处理: {idx+1}/{len(selected)}, 成功: {n_ok}, 耗时: {elapsed:.0f}s")
            sys.stdout.flush()

    elapsed = time.time() - t0
    print(f"\r  成功: {n_ok}/{len(selected)}, 耗时: {elapsed:.0f}s")

    if n_ok == 0:
        print(f"  [{year}] 无有效数据\n")
        continue

    # 均值合成
    valid_mask = ndvi_count > 0
    ndvi = np.full((OUT_HEIGHT, OUT_WIDTH), np.nan, dtype=np.float32)
    ndvi[valid_mask] = (ndvi_sum[valid_mask] / ndvi_count[valid_mask]).astype(np.float32)
    del ndvi_sum

    # 覆盖统计
    cover_1 = np.sum(ndvi_count == 1) / valid_mask.sum() * 100 if valid_mask.sum() > 0 else 0
    cover_3 = np.sum(ndvi_count >= 3) / valid_mask.sum() * 100 if valid_mask.sum() > 0 else 0
    print(f"  覆盖: 仅1景={cover_1:.1f}%, >=3景={cover_3:.1f}%, 平均={ndvi_count[valid_mask].mean():.1f}景")

    # Mask 到城市边界
    city_mask = geometry_mask(
        [city_geom], out_shape=(OUT_HEIGHT, OUT_WIDTH),
        transform=OUT_TRANSFORM, invert=True, all_touched=True
    )
    ndvi[~city_mask] = np.nan

    n_city_px = np.sum(city_mask)
    n_valid   = np.sum(~np.isnan(ndvi))
    cov_pct   = n_valid / n_city_px * 100 if n_city_px > 0 else 0

    # 分区覆盖
    mid = OUT_WIDTH // 2
    for label, sl in [("西半部", slice(0, mid)), ("东半部", slice(mid, None))]:
        rm = city_mask[:, sl]
        rn = ndvi[:, sl]
        rt = np.sum(rm)
        rv = np.sum(~np.isnan(rn)) if rt > 0 else 0
        print(f"    {label}: {rv/rt*100:.1f}%" if rt > 0 else f"    {label}: N/A")

    print(f"  城市整体覆盖: {cov_pct:.1f}%")

    # 裁剪到有效区域
    rows, cols = np.where(~np.isnan(ndvi))
    if len(rows) == 0:
        print(f"  [{year}] 无像素\n")
        continue

    r0, r1 = rows.min(), rows.max() + 1
    c0, c1 = cols.min(), cols.max() + 1
    ndvi_crop = ndvi[r0:r1, c0:c1]
    crop_tf   = OUT_TRANSFORM * rasterio.Affine.translation(c0, r0)

    # 导出
    with rasterio.open(
        out_path, 'w', driver='GTiff',
        height=ndvi_crop.shape[0], width=ndvi_crop.shape[1], count=1,
        dtype='float32', crs=CRS.from_epsg(4326), transform=crop_tf,
        compress='lzw', nodata=NODATA, tiled=True, blockxsize=256, blockysize=256
    ) as dst:
        out_data = np.where(np.isnan(ndvi_crop), NODATA, ndvi_crop).astype(np.float32)
        dst.write(out_data, 1)
        dst.update_tags(
            year=str(year), index='NDVI', method='mean_composite_path_balanced',
            n_scenes=str(n_ok), coverage_pct=f"{cov_pct:.1f}"
        )

    mb = os.path.getsize(out_path) / 1024 / 1024
    vals = out_data[out_data != NODATA]
    print(f"  保存: {os.path.basename(out_path)} ({mb:.1f} MB)")
    print(f"  NDVI: mean={np.mean(vals):.4f}, range=[{np.min(vals):.4f}, {np.max(vals):.4f}]\n")

# ============================================================
# 统计汇总
# ============================================================
print("=" * 60)
print("NDVI 统计汇总")
print("=" * 60)

csv_path = os.path.join(OUTPUT, "NDVI统计汇总.csv")
with open(csv_path, 'w', encoding='utf-8-sig') as f:
    f.write("年份,NDVI均值,标准差,最小值,最大值,植被覆盖比例(%),城市覆盖率(%)\n")
    for year in YEARS:
        fp = os.path.join(OUTPUT, f"赣州_NDVI_{year}_wgs84.tif")
        if not os.path.exists(fp):
            print(f"  {year}: 文件缺失")
            continue
        with rasterio.open(fp) as src:
            data = src.read(1)
            v = data[data != NODATA]
            if len(v) == 0:
                print(f"  {year}: 无有效数据")
                continue
            veg_pct = np.sum(v > 0.3) / len(v) * 100
            cov_tag = src.tags().get('coverage_pct', 'N/A')
            f.write(f"{year},{np.mean(v):.4f},{np.std(v):.4f},{np.min(v):.4f},{np.max(v):.4f},{veg_pct:.1f},{cov_tag}\n")
            print(f"  {year}: mean={np.mean(v):.4f}, sigma={np.std(v):.4f}, veg={veg_pct:.1f}%, city_cov={cov_tag}%")

print(f"\n统计表: {csv_path}")
print("\n=== 完毕 ===")
