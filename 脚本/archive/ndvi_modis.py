# -*- coding: utf-8 -*-
"""
赣州多年 NDVI 计算 — MODIS MOD13Q1 (2000-2024) + Landsat (1990)

MODIS MOD13Q1:
  - 250m 分辨率, 16天合成, NDVI 已预计算 (scale=0.0001)
  - 数据源: Microsoft Planetary Computer, modis-13Q1-061
  - 覆盖赣州需要 2 个 tile: h27v06, h28v06
  - 每年生长季(6-8月)约 6 期, 中值合成

1990 (MODIS 未发射):
  - Landsat 5 TM, 仅选 3-5 景最低云量场景, 0.001° 输出
"""

import os, sys, json, time
import numpy as np
import rasterio
from rasterio.transform import from_bounds
from rasterio.crs import CRS
from rasterio.warp import transform_bounds, reproject, Resampling
from rasterio.features import geometry_mask
from shapely.geometry import shape, box
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
print(f"赣州: {cb[0]:.3f}~{cb[2]:.3f}E, {cb[1]:.3f}~{cb[3]:.3f}N")

# ============================================================
# 全局参数
# ============================================================
PAD = 0.15
SEARCH_BBOX = [cb[0]-PAD, cb[1]-PAD, cb[2]+PAD, cb[3]+PAD]

# MODIS 输出: 0.0025° ≈ 250m
RES_MODIS = 0.0025
OUT_WIDTH_M  = int((cb[2] - cb[0]) / RES_MODIS) + 1
OUT_HEIGHT_M = int((cb[3] - cb[1]) / RES_MODIS) + 1
OUT_TRANSFORM_M = from_bounds(cb[0], cb[1], cb[2], cb[3], OUT_WIDTH_M, OUT_HEIGHT_M)

# Landsat 输出: 0.001° ≈ 100m
RES_LS = 0.001
OUT_WIDTH_L  = int((cb[2] - cb[0]) / RES_LS) + 1
OUT_HEIGHT_L = int((cb[3] - cb[1]) / RES_LS) + 1
OUT_TRANSFORM_L = from_bounds(cb[0], cb[1], cb[2], cb[3], OUT_WIDTH_L, OUT_HEIGHT_L)

NODATA = np.float32(-9999)

print(f"MODIS 网格: {OUT_WIDTH_M}x{OUT_HEIGHT_M} ({OUT_WIDTH_M*OUT_HEIGHT_M/1e6:.1f}M px)")
print(f"Landsat 网格: {OUT_WIDTH_L}x{OUT_HEIGHT_L} ({OUT_WIDTH_L*OUT_HEIGHT_L/1e6:.1f}M px)")

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
# MODIS MOD13Q1 NDVI
# ============================================================
def process_modis_year(year):
    """MODIS MOD13Q1 生长季中值合成"""
    out_path = os.path.join(OUTPUT, f"赣州_NDVI_{year}_wgs84.tif")
    if os.path.exists(out_path) and os.path.getsize(out_path) > 500 * 1024:
        print(f"[{year}] MODIS 已存在，跳过\n")
        return

    print(f"[{year}] 搜索 MODIS MOD13Q1 (6-9月)...")

    items = []
    for attempt in range(3):
        try:
            s = catalog.search(
                collections=["modis-13Q1-061"],
                bbox=SEARCH_BBOX,
                datetime=f"{year}-06-01/{year}-09-30",
                max_items=20
            )
            items = list(s.items())
            break
        except Exception as e:
            if attempt < 2:
                time.sleep((attempt+1)*8)

    print(f"  找到 {len(items)} 期数据")

    if len(items) == 0:
        print(f"  [{year}] 无 MODIS 数据\n")
        return

    # 按日期排序 (MODIS datetime 可能为 None)
    items.sort(key=lambda x: x.properties.get('datetime') or '')

    ndvi_stack = []
    n_ok = 0

    for idx, item in enumerate(items):
        try:
            ndvi_key = '250m_16_days_NDVI'
            if ndvi_key not in item.assets:
                continue

            url = pc.sign(item.assets[ndvi_key].href)
            date_str = (item.properties.get('datetime') or 'unknown')[:10]

            with rasterio.open(url) as src:
                # MODIS Sinusoidal → WGS84
                sc_crs = src.crs
                sc_b_wgs = transform_bounds(sc_crs, CRS.from_epsg(4326), *src.bounds)

                # 检查与城市是否重叠
                ol = [max(cb[0], sc_b_wgs[0]), max(cb[1], sc_b_wgs[1]),
                      min(cb[2], sc_b_wgs[2]), min(cb[3], sc_b_wgs[3])]
                if ol[0] >= ol[2] or ol[1] >= ol[3]:
                    continue

                # 读取全图 (MODIS tile 只有 4800x4800, 很小)
                ndvi_raw = src.read(1)
                # MODIS NDVI scale factor = 0.0001, valid range -2000 to 10000
                ndvi_raw = ndvi_raw.astype(np.float32) * 0.0001
                # 无效值: -3000 (fill value)
                ndvi_raw = np.where(ndvi_raw < -0.3, np.nan, ndvi_raw)
                ndvi_raw = np.where(ndvi_raw > 1.0, np.nan, ndvi_raw)

            # Reproject 到统一 WGS84 网格
            out = np.full((OUT_HEIGHT_M, OUT_WIDTH_M), np.nan, dtype=np.float32)
            reproject(
                source=ndvi_raw, destination=out,
                src_transform=src.transform, src_crs=sc_crs,
                dst_transform=OUT_TRANSFORM_M, dst_crs=CRS.from_epsg(4326),
                src_nodata=np.nan, dst_nodata=np.nan,
                resampling=Resampling.bilinear
            )
            n_valid = np.sum(~np.isnan(out))
            if n_valid > 100:  # 至少有数据
                ndvi_stack.append(out)
                n_ok += 1

            sys.stdout.write(f"\r  处理: {idx+1}/{len(items)}, 有效: {n_ok} ({date_str}, {n_valid}px)")
            sys.stdout.flush()

        except Exception as e:
            if idx < 3:
                print(f"\n  MODIS[{idx}] 失败: {e}")
            continue

    print(f"\r  有效期数: {n_ok}/{len(items)}")

    if n_ok == 0:
        print(f"  [{year}] 无有效 MODIS 数据\n")
        return

    # 中值合成
    print(f"  中值合成 ({n_ok} 期)...")
    stack = np.stack(ndvi_stack, axis=0)
    ndvi_median = np.nanmedian(stack, axis=0)
    del stack, ndvi_stack

    # 统计合成质量
    n_pixels = np.sum(~np.isnan(ndvi_median))

    # Mask 到城市边界
    city_mask = geometry_mask(
        [city_geom], out_shape=(OUT_HEIGHT_M, OUT_WIDTH_M),
        transform=OUT_TRANSFORM_M, invert=True, all_touched=True
    )
    ndvi_median[~city_mask] = np.nan
    n_city = np.sum(city_mask)
    n_valid = np.sum(~np.isnan(ndvi_median))
    cov_pct = n_valid / n_city * 100 if n_city > 0 else 0
    print(f"  城市覆盖率: {cov_pct:.1f}%")

    # 裁剪 & 导出
    rows, cols = np.where(~np.isnan(ndvi_median))
    if len(rows) == 0:
        print(f"  [{year}] 无有效像素\n")
        return
    r0, r1 = rows.min(), rows.max() + 1
    c0, c1 = cols.min(), cols.max() + 1
    ndvi_crop = ndvi_median[r0:r1, c0:c1]
    crop_tf = OUT_TRANSFORM_M * rasterio.Affine.translation(c0, r0)

    with rasterio.open(
        out_path, 'w', driver='GTiff',
        height=ndvi_crop.shape[0], width=ndvi_crop.shape[1], count=1,
        dtype='float32', crs=CRS.from_epsg(4326), transform=crop_tf,
        compress='lzw', nodata=NODATA, tiled=True, blockxsize=256, blockysize=256
    ) as dst:
        out_data = np.where(np.isnan(ndvi_crop), NODATA, ndvi_crop).astype(np.float32)
        dst.write(out_data, 1)
        dst.update_tags(year=str(year), index='NDVI', method='MODIS_MOD13Q1_median',
                        n_periods=str(n_ok), coverage_pct=f"{cov_pct:.1f}")

    mb = os.path.getsize(out_path) / 1024 / 1024
    vals = out_data[out_data != NODATA]
    print(f"  保存: {os.path.basename(out_path)} ({mb:.1f} MB)")
    print(f"  NDVI: mean={np.mean(vals):.4f}, range=[{np.min(vals):.4f}, {np.max(vals):.4f}]\n")


# ============================================================
# Landsat 1990 (MODIS 未发射, 用少量关键场景)
# ============================================================
def process_landsat_1990():
    """1990 年 Landsat 5: 仅选每个 path 最低云量 2 景, 共约 6 景"""
    year = 1990
    out_path = os.path.join(OUTPUT, f"赣州_NDVI_{year}_wgs84.tif")
    if os.path.exists(out_path) and os.path.getsize(out_path) > 500 * 1024:
        print(f"[{year}] Landsat 已存在，跳过\n")
        return

    print(f"[{year}] 搜索 Landsat-5 (MODIS 尚未发射)...")

    items = []
    for attempt in range(3):
        try:
            s = catalog.search(
                collections=["landsat-c2-l2"],
                bbox=SEARCH_BBOX,
                datetime=f"{year}-06-01/{year}-09-30",
                query={"platform": {"in": ["landsat-5"]}, "eo:cloud_cover": {"lt": 30}},
                max_items=50
            )
            items = list(s.items())
            break
        except Exception as e:
            if attempt < 2:
                time.sleep((attempt+1)*8)

    print(f"  搜索到 {len(items)} 景")

    # 按 path 分组, 每 path 选最低云量 2 景
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

    selected = []
    for pp, grp in path_groups.items():
        grp.sort(key=lambda x: x.properties.get('eo:cloud_cover', 100))
        selected.extend(grp[:2])

    seen = set()
    selected = [s for s in selected if not (s.id in seen or seen.add(s.id))]
    selected.sort(key=lambda x: x.properties.get('eo:cloud_cover', 100))

    from collections import Counter
    pcnt = Counter(s.properties.get('landsat:wrs_path', '?') for s in selected)
    print(f"  选中 {len(selected)} 景: {dict(pcnt)}")

    SR_SCALE = 0.0000275
    SR_OFFSET = -0.2

    ndvi_sum   = np.zeros((OUT_HEIGHT_L, OUT_WIDTH_L), dtype=np.float64)
    ndvi_count = np.zeros((OUT_HEIGHT_L, OUT_WIDTH_L), dtype=np.int32)
    n_ok = 0
    t0 = time.time()

    for idx, item in enumerate(selected):
        try:
            nir_url = pc.sign(item.assets['nir08'].href)
            red_url = pc.sign(item.assets['red'].href)

            with rasterio.open(nir_url) as nir_src:
                sc_crs = nir_src.crs
                if sc_crs and sc_crs != CRS.from_epsg(4326):
                    sc_b_wgs = transform_bounds(sc_crs, CRS.from_epsg(4326), *nir_src.bounds)
                else:
                    sc_b_wgs = nir_src.bounds

                ol_l = max(SEARCH_BBOX[0], sc_b_wgs[0])
                ol_b = max(SEARCH_BBOX[1], sc_b_wgs[1])
                ol_r = min(SEARCH_BBOX[2], sc_b_wgs[2])
                ol_t = min(SEARCH_BBOX[3], sc_b_wgs[3])
                if ol_l >= ol_r or ol_b >= ol_t:
                    continue

                if sc_crs and sc_crs != CRS.from_epsg(4326):
                    ol_proj = transform_bounds(CRS.from_epsg(4326), sc_crs, ol_l, ol_b, ol_r, ol_t)
                    window = nir_src.window(ol_proj[0], ol_proj[1], ol_proj[2], ol_proj[3])
                else:
                    window = nir_src.window(ol_l, ol_b, ol_r, ol_t)

                ww, wh = int(window.width), int(window.height)
                # 低分辨率: max 1500px
                scale = min(1.0, 1500 / max(ww, wh))
                ow, oh = max(10, int(ww*scale)), max(10, int(wh*scale))

                with rasterio.open(red_url) as red_src:
                    nir_arr = nir_src.read(1, window=window, out_shape=(oh, ow))
                    red_arr = red_src.read(1, window=window, out_shape=(oh, ow))

                if nir_src.nodata is not None:
                    nir_arr = np.where(nir_arr == nir_src.nodata, np.nan, nir_arr)
                if red_src.nodata is not None:
                    red_arr = np.where(red_arr == red_src.nodata, np.nan, red_arr)

                nir_arr = np.where(nir_arr > 0, nir_arr, np.nan)
                red_arr = np.where(red_arr > 0, red_arr, np.nan)

                nir_sr = (nir_arr.astype(np.float32)*SR_SCALE+SR_OFFSET).clip(0, 1)
                red_sr = (red_arr.astype(np.float32)*SR_SCALE+SR_OFFSET).clip(0, 1)
                ndvi_arr = ((nir_sr-red_sr)/(nir_sr+red_sr+1e-8)).clip(-1, 1)

                src_tf = nir_src.window_transform(window)
                src_tf = src_tf * src_tf.scale(ww/ow, wh/oh)

            out = np.full((OUT_HEIGHT_L, OUT_WIDTH_L), np.nan, dtype=np.float32)
            reproject(
                source=ndvi_arr, destination=out,
                src_transform=src_tf, src_crs=sc_crs,
                dst_transform=OUT_TRANSFORM_L, dst_crs=CRS.from_epsg(4326),
                src_nodata=np.nan, dst_nodata=np.nan, resampling=Resampling.bilinear
            )
            valid = ~np.isnan(out)
            ndvi_sum[valid]   += out[valid].astype(np.float64)
            ndvi_count[valid] += 1
            n_ok += 1

        except Exception as e:
            if idx < 3:
                print(f"  场景[{idx}] {item.id[:30]} 失败: {e}")
            continue

        elapsed = time.time() - t0
        sys.stdout.write(f"\r  处理: {idx+1}/{len(selected)}, 成功: {n_ok}, 耗时: {elapsed:.0f}s")
        sys.stdout.flush()

    elapsed = time.time() - t0
    print(f"\r  成功: {n_ok}/{len(selected)}, 耗时: {elapsed:.0f}s")

    if n_ok == 0:
        print(f"  [{year}] 无有效数据\n")
        return

    valid_mask = ndvi_count > 0
    ndvi = np.full((OUT_HEIGHT_L, OUT_WIDTH_L), np.nan, dtype=np.float32)
    ndvi[valid_mask] = (ndvi_sum[valid_mask] / ndvi_count[valid_mask]).astype(np.float32)
    del ndvi_sum

    city_mask = geometry_mask(
        [city_geom], out_shape=(OUT_HEIGHT_L, OUT_WIDTH_L),
        transform=OUT_TRANSFORM_L, invert=True, all_touched=True
    )
    ndvi[~city_mask] = np.nan
    n_city = np.sum(city_mask)
    n_valid = np.sum(~np.isnan(ndvi))
    cov_pct = n_valid / n_city * 100 if n_city > 0 else 0
    print(f"  城市覆盖率: {cov_pct:.1f}%")

    rows, cols = np.where(~np.isnan(ndvi))
    if len(rows) == 0:
        print(f"  [{year}] 无有效像素\n")
        return
    r0, r1 = rows.min(), rows.max() + 1
    c0, c1 = cols.min(), cols.max() + 1
    ndvi_crop = ndvi[r0:r1, c0:c1]
    crop_tf = OUT_TRANSFORM_L * rasterio.Affine.translation(c0, r0)

    with rasterio.open(
        out_path, 'w', driver='GTiff',
        height=ndvi_crop.shape[0], width=ndvi_crop.shape[1], count=1,
        dtype='float32', crs=CRS.from_epsg(4326), transform=crop_tf,
        compress='lzw', nodata=NODATA, tiled=True, blockxsize=256, blockysize=256
    ) as dst:
        out_data = np.where(np.isnan(ndvi_crop), NODATA, ndvi_crop).astype(np.float32)
        dst.write(out_data, 1)
        dst.update_tags(year='1990', index='NDVI', method='Landsat5_mean_lowres',
                        n_scenes=str(n_ok), coverage_pct=f"{cov_pct:.1f}")

    mb = os.path.getsize(out_path) / 1024 / 1024
    vals = out_data[out_data != NODATA]
    print(f"  保存: {os.path.basename(out_path)} ({mb:.1f} MB)")
    print(f"  NDVI: mean={np.mean(vals):.4f}, range=[{np.min(vals):.4f}, {np.max(vals):.4f}]\n")


# ============================================================
# 主流程
# ============================================================
# 1990: Landsat 5 (MODIS 尚未发射)
process_landsat_1990()

# 2000-2024: MODIS MOD13Q1
for year in [2000, 2010, 2015, 2020, 2024]:
    process_modis_year(year)

# ============================================================
# 统计汇总
# ============================================================
print("=" * 60)
print("NDVI 统计汇总")
print("=" * 60)

csv_path = os.path.join(OUTPUT, "NDVI统计汇总.csv")
with open(csv_path, 'w', encoding='utf-8-sig') as f:
    f.write("年份,NDVI均值,标准差,最小值,最大值,植被覆盖比例(%),城市覆盖率(%),数据源\n")
    for year in [1990, 2000, 2010, 2015, 2020, 2024]:
        fp = os.path.join(OUTPUT, f"赣州_NDVI_{year}_wgs84.tif")
        if not os.path.exists(fp):
            print(f"  {year}: 文件缺失")
            continue
        with rasterio.open(fp) as src:
            data = src.read(1)
            v = data[data != NODATA]
            if len(v) == 0:
                continue
            veg_pct = np.sum(v > 0.3) / len(v) * 100
            cov_tag = src.tags().get('coverage_pct', 'N/A')
            method = src.tags().get('method', 'N/A')
            f.write(f"{year},{np.mean(v):.4f},{np.std(v):.4f},{np.min(v):.4f},{np.max(v):.4f},{veg_pct:.1f},{cov_tag},{method}\n")
            print(f"  {year}: mean={np.mean(v):.4f}, sigma={np.std(v):.4f}, "
                  f"veg={veg_pct:.1f}%, cov={cov_tag}%, src={method}")

print(f"\n统计表: {csv_path}")
print("=== 完毕 ===")
