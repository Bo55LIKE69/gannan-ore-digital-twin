# -*- coding: utf-8 -*-
"""
赣州多年 NDVI 计算 — 中位数合成版
修复场景拼接痕迹：用 per-pixel median 替代 mean
策略: 每景全分辨率存储 (float16), 处理完后 stack → nanmedian
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
from collections import Counter
import warnings
warnings.filterwarnings('ignore')

BASE = r"E:\Data\赣州稀土"
OUTPUT = os.path.join(BASE, "NDVI分析结果")
os.makedirs(OUTPUT, exist_ok=True)

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

PAD = 0.15
SEARCH_BBOX = [cb[0]-PAD, cb[1]-PAD, cb[2]+PAD, cb[3]+PAD]

RES = 0.001
OUT_WIDTH  = int((cb[2] - cb[0]) / RES) + 1
OUT_HEIGHT = int((cb[3] - cb[1]) / RES) + 1
OUT_TRANSFORM = from_bounds(cb[0], cb[1], cb[2], cb[3], OUT_WIDTH, OUT_HEIGHT)
NODATA = np.float32(-9999)
MAX_WINDOW = 800

SR_SCALE  = 0.0000275
SR_OFFSET = -0.2

print(f"输出网格: {OUT_WIDTH}x{OUT_HEIGHT} ({OUT_WIDTH*OUT_HEIGHT/1e6:.1f}M px)")

# MPC
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


def search_mpc(bbox, dt, platforms, cc_max, max_items):
    for attempt in range(3):
        try:
            s = catalog.search(
                collections=["landsat-c2-l2"],
                bbox=bbox, datetime=dt,
                query={"platform": {"in": platforms}, "eo:cloud_cover": {"lt": cc_max}},
                max_items=max_items
            )
            return list(s.items())
        except Exception:
            if attempt < 2:
                time.sleep((attempt+1)*8)
    return []


def process_scene(item):
    """单景 → NDVI → reproject → 返回 float16 数组"""
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
            return None

        if sc_crs and sc_crs != CRS.from_epsg(4326):
            ol_proj = transform_bounds(CRS.from_epsg(4326), sc_crs, ol_l, ol_b, ol_r, ol_t)
            window = nir_src.window(ol_proj[0], ol_proj[1], ol_proj[2], ol_proj[3])
        else:
            window = nir_src.window(ol_l, ol_b, ol_r, ol_t)

        ww, wh = int(window.width), int(window.height)
        scale = min(1.0, MAX_WINDOW / max(ww, wh))
        ow, oh = max(10, int(ww*scale)), max(10, int(wh*scale))

        with rasterio.open(red_url) as red_src:
            nir_arr = nir_src.read(1, window=window, out_shape=(oh, ow))
            red_arr = red_src.read(1, window=window, out_shape=(oh, ow))

        if nir_src.nodata is not None:
            nir_arr = np.where(nir_arr == nir_src.nodata, np.nan, nir_arr)
        if red_src.nodata is not None:
            red_arr = np.where(red_arr == red_src.nodata, np.nan, red_arr)

        nir_arr = np.where((nir_arr > 1000) & (nir_arr < 60000), nir_arr, np.nan)
        red_arr = np.where((red_arr > 1000) & (red_arr < 60000), red_arr, np.nan)

        nir_sr = (nir_arr.astype(np.float32)*SR_SCALE+SR_OFFSET).clip(0, 1)
        red_sr = (red_arr.astype(np.float32)*SR_SCALE+SR_OFFSET).clip(0, 1)
        ndvi_arr = ((nir_sr-red_sr)/(nir_sr+red_sr+1e-8)).clip(-1, 1)

        src_tf = nir_src.window_transform(window)
        src_tf = src_tf * src_tf.scale(ww/ow, wh/oh)

    out = np.full((OUT_HEIGHT, OUT_WIDTH), np.nan, dtype=np.float32)
    reproject(
        source=ndvi_arr, destination=out,
        src_transform=src_tf, src_crs=sc_crs,
        dst_transform=OUT_TRANSFORM, dst_crs=CRS.from_epsg(4326),
        src_nodata=np.nan, dst_nodata=np.nan,
        resampling=Resampling.bilinear
    )
    return np.where(np.isnan(out), np.nan, out.astype(np.float16))


def select_scenes(year, platforms):
    """搜索并按 path 分组选景"""
    if year == 1990:
        items = search_mpc(SEARCH_BBOX, f"{year}-04-01/{year}-10-31", platforms, 80, 500)
        if len(items) < 50:
            items2 = search_mpc(SEARCH_BBOX, f"{year}-01-01/{year}-12-31", platforms, 100, 500)
            ids = {it.id for it in items}
            for it in items2:
                if it.id not in ids:
                    items.append(it); ids.add(it.id)
    else:
        items = search_mpc(SEARCH_BBOX, f"{year}-06-01/{year}-09-30", platforms, 60, 300)
        if len(items) < 20:
            items2 = search_mpc(SEARCH_BBOX, f"{year}-04-01/{year}-10-31", platforms, 80, 300)
            ids = {it.id for it in items}
            for it in items2:
                if it.id not in ids:
                    items.append(it); ids.add(it.id)

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

    per_path = 20 if year == 1990 else 15
    total_max = 80 if year == 1990 else 60
    selected = []
    for pp, grp in path_groups.items():
        grp.sort(key=lambda x: x.properties.get('eo:cloud_cover', 100))
        selected.extend(grp[:per_path])

    seen = set()
    selected = [s for s in selected if not (s.id in seen or seen.add(s.id))]
    selected.sort(key=lambda x: x.properties.get('eo:cloud_cover', 100))
    selected = selected[:total_max]

    pcnt = Counter(s.properties.get('landsat:wrs_path', '?') for s in selected)
    clouds = [s.properties.get('eo:cloud_cover', 999) for s in selected]
    print(f"  选中 {len(selected)} 景: {dict(pcnt)}")
    if clouds:
        print(f"  云量: {min(clouds):.0f}%~{max(clouds):.0f}%, 平均{np.mean(clouds):.1f}%")
    return selected


def save_result(ndvi_median, ndvi_count, year, n_ok):
    """裁剪、mask、保存"""
    city_mask = geometry_mask(
        [city_geom], out_shape=(OUT_HEIGHT, OUT_WIDTH),
        transform=OUT_TRANSFORM, invert=True, all_touched=True
    )
    ndvi_median[~city_mask] = np.nan

    n_city_px = np.sum(city_mask)
    n_valid = np.sum(~np.isnan(ndvi_median))
    cov_pct = n_valid / n_city_px * 100 if n_city_px > 0 else 0

    mid = OUT_WIDTH // 2
    for label, sl in [("西", slice(0, mid)), ("东", slice(mid, None))]:
        rm = city_mask[:, sl]; rn = ndvi_median[:, sl]
        rt = np.sum(rm); rv = np.sum(~np.isnan(rn)) if rt > 0 else 0
        if rt > 0: print(f"    {label}半部: {rv/rt*100:.1f}%")
    print(f"  城市整体覆盖: {cov_pct:.1f}%")

    if n_valid == 0:
        return None

    rows, cols = np.where(~np.isnan(ndvi_median))
    r0, r1 = rows.min(), rows.max() + 1
    c0, c1 = cols.min(), cols.max() + 1
    ndvi_crop = ndvi_median[r0:r1, c0:c1]
    crop_tf = OUT_TRANSFORM * rasterio.Affine.translation(c0, r0)

    out_path = os.path.join(OUTPUT, f"赣州_NDVI_{year}_wgs84.tif")
    if os.path.exists(out_path):
        os.remove(out_path)

    with rasterio.open(
        out_path, 'w', driver='GTiff',
        height=ndvi_crop.shape[0], width=ndvi_crop.shape[1], count=1,
        dtype='float32', crs=CRS.from_epsg(4326), transform=crop_tf,
        compress='lzw', nodata=NODATA, tiled=True, blockxsize=256, blockysize=256
    ) as dst:
        out_data = np.where(np.isnan(ndvi_crop), NODATA, ndvi_crop).astype(np.float32)
        dst.write(out_data, 1)
        dst.update_tags(
            year=str(year), index='NDVI', method='Landsat_median_100m',
            n_scenes=str(n_ok), coverage_pct=f"{cov_pct:.1f}"
        )

    mb = os.path.getsize(out_path) / 1024 / 1024
    vals = out_data[out_data != NODATA]
    print(f"  保存: {os.path.basename(out_path)} ({mb:.1f} MB)")
    print(f"  NDVI median: mean={np.mean(vals):.4f}, range=[{np.min(vals):.4f}, {np.max(vals):.4f}]")
    return out_path


# ============================================================
# 主循环
# ============================================================
for year in [1990, 2000, 2010, 2015, 2020, 2024]:
    print(f"\n{'='*60}")
    print(f"[{year}] 中位数合成...")
    platforms = {
        1990: ["landsat-5"], 2000: ["landsat-5", "landsat-7"],
        2010: ["landsat-5", "landsat-7"], 2015: ["landsat-8"],
        2020: ["landsat-8"], 2024: ["landsat-8", "landsat-9"],
    }.get(year, ["landsat-8"])

    selected = select_scenes(year, platforms)
    if len(selected) == 0:
        print(f"  无数据\n")
        continue

    # 收集所有场景 NDVI
    scene_arrays = []
    ndvi_count = np.zeros((OUT_HEIGHT, OUT_WIDTH), dtype=np.int32)
    n_ok = 0
    t0 = time.time()

    for idx, item in enumerate(selected):
        try:
            arr = process_scene(item)
            if arr is None:
                continue
            valid = ~np.isnan(arr)
            ndvi_count[valid] += 1
            scene_arrays.append(arr)
            n_ok += 1
        except Exception as e:
            if idx < 3:
                print(f"  场景[{idx}] {item.id[:30]} 失败: {e}")
            continue

        done = idx + 1
        if done % 10 == 0 or done == len(selected):
            elapsed = time.time() - t0
            sys.stdout.write(f"\r  收集: {done}/{len(selected)}, 成功: {n_ok}, "
                           f"{elapsed/done:.1f}s/景, 总{elapsed:.0f}s")
            sys.stdout.flush()

    elapsed = time.time() - t0
    print(f"\r  收集完成: {n_ok}/{len(selected)}, "
          f"{elapsed/n_ok:.1f}s/景, 总{elapsed:.0f}s" if n_ok > 0 else f"\r  收集: 0")

    if n_ok == 0:
        print(f"  [{year}] 无有效数据\n")
        continue

    # 中位数合成
    print(f"  计算中位数 (n={n_ok})...")
    t1 = time.time()
    stack = np.stack(scene_arrays, axis=0)  # (n_scenes, H, W), float16
    ndvi_median = np.nanmedian(stack, axis=0).astype(np.float32)
    del stack, scene_arrays

    # 覆盖统计
    valid_mask = ndvi_count > 0
    mean_scenes = ndvi_count[valid_mask].mean()
    cover_1 = np.sum(ndvi_count == 1) / valid_mask.sum() * 100
    cover_5 = np.sum(ndvi_count >= 5) / valid_mask.sum() * 100
    print(f"  覆盖: 平均{mean_scenes:.1f}景, 仅1景={cover_1:.1f}%, >=5景={cover_5:.1f}%")
    print(f"  中位数计算耗时: {time.time()-t1:.0f}s")

    save_result(ndvi_median, ndvi_count, year, n_ok)

# ============================================================
# 统计汇总
# ============================================================
print(f"\n{'='*60}")
print("NDVI 统计汇总 (中位数合成)")
print("=" * 60)

csv_path = os.path.join(OUTPUT, "NDVI统计汇总_中位数.csv")
with open(csv_path, 'w', encoding='utf-8-sig') as f:
    f.write("年份,NDVI中位数均值,标准差,最小值,最大值,植被覆盖比例(%),城市覆盖率(%)\n")
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
            veg = np.sum(v > 0.3) / len(v) * 100
            cov = src.tags().get('coverage_pct', 'N/A')
            f.write(f"{year},{np.mean(v):.4f},{np.std(v):.4f},{np.min(v):.4f},{np.max(v):.4f},{veg:.1f},{cov}\n")
            print(f"  {year}: mean={np.mean(v):.4f}, sigma={np.std(v):.4f}, "
                  f"veg={veg:.1f}%, cov={cov}%")

print(f"\n统计表: {csv_path}")
print("=== 完毕 ===")
