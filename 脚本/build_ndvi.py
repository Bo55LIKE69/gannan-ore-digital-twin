# -*- coding: utf-8 -*-
"""
赣南 NDVI 生产管线
数据源：Sentinel-2 L2A（AWS Earth Search STAC，公开 COG，无需认证）
流程：
  STAC 搜索 -> 按 MGRS tile 挑云量最低景 -> 读 B04(红)/B08(近红外)/SCL(场景分类) 窗口
  -> 云掩膜 -> 逐景算 NDVI -> 最大值合成(MVC) -> 重采样到 DEM 1024 网格 -> ndvi_data.js

用法：
  E:/adaconda/python.exe 脚本/build_ndvi.py [datetime_rfc3339]

注意：
  - STAC 的 datetime 必须是完整 RFC3339：2025-09-01T00:00:00Z/2026-08-31T23:59:59Z
  - GDAL/rasterio 走代理需设 GDAL_HTTP_PROXY
"""
import base64
import json
import os
import sys
import time
import warnings

import numpy as np

warnings.filterwarnings('ignore')

import requests
import rasterio
from rasterio.enums import Resampling
from rasterio.transform import from_bounds
from rasterio.warp import reproject

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_JS = os.path.join(ROOT, 'ndvi_data.js')
CACHE = os.path.join(ROOT, '.temp', 'ndvi')
os.makedirs(CACHE, exist_ok=True)

STAC = 'https://earth-search.aws.element84.com/v1/search'

# 与 dem_terrain_data.js 完全一致的输出网格
GRID = 1024
# 赣州市范围（DEM 边界）
WEST, SOUTH, EAST, NORTH = 113.908124000, 24.487615312, 116.645068466, 27.146782000

# GDAL 网络读取优化（COG 范围请求）
os.environ.setdefault('GDAL_DISABLE_READDIR_ON_OPEN', 'EMPTY_DIR')
os.environ.setdefault('GDAL_HTTP_MAX_RETRY', '5')
os.environ.setdefault('GDAL_HTTP_RETRY_DELAY', '2')
os.environ.setdefault('VSI_CACHE', 'TRUE')
os.environ.setdefault('GDAL_HTTP_MULTIPLEX', 'YES')
os.environ.setdefault('GDAL_HTTP_VERSION', '2')
os.environ.setdefault('GDAL_HTTP_TIMEOUT', '120')
os.environ.setdefault('CPL_VSIL_CURL_ALLOWED_EXTENSIONS', '.tif')

# 代理：从系统环境变量继承（GDAL 只认 http_proxy/https_proxy）
for k in ('http_proxy', 'https_proxy', 'HTTP_PROXY', 'HTTPS_PROXY'):
    v = os.environ.get(k)
    if v:
        os.environ['GDAL_HTTP_PROXY'] = v
        break

S = requests.Session()
S.headers.update({'User-Agent': 'Mozilla/5.0', 'Accept': 'application/geo+json'})


def post_json(url, payload, tries=6, timeout=120):
    last = None
    for i in range(tries):
        try:
            r = S.post(url, json=payload, timeout=timeout)
            if r.status_code == 200:
                return r.json()
            last = 'HTTP %d %s' % (r.status_code, r.text[:160])
        except Exception as e:
            last = str(e)[:160]
        time.sleep(2 + i * 2)
    raise RuntimeError('STAC 请求失败: %s' % last)


def search_scenes(dt=None, max_cloud=30, min_date='2025-01-01'):
    """搜索覆盖赣州的 Sentinel-2 L2A，按 MGRS tile 分组各取云量最低一景。

    注意：不要在 STAC 侧传大跨度 datetime —— 服务端容易超时（代理返回 502）。
    改为「按日期倒序拉最新 N 条 + 本地按 tile 分组挑云量最低」。
    """
    # limit 不能设太大：实测 limit=500 会让服务端超时（代理表现为 502），200 以内稳定
    PAGE = 200
    PAGES = 4
    feats = []
    seen = set()
    payload = {
        'collections': ['sentinel-2-c1-l2a'],
        'bbox': [WEST, SOUTH, EAST, NORTH],
        'limit': PAGE,
        'sortby': [{'field': 'properties.datetime', 'direction': 'desc'}],
    }
    if dt:
        payload['datetime'] = dt

    for pg in range(PAGES):
        print('[STAC] 第 %d/%d 页 ...' % (pg + 1, PAGES))
        d = post_json(STAC, dict(payload))
        fs = d.get('features', [])
        new = 0
        for f in fs:
            if f['id'] in seen:
                continue
            seen.add(f['id'])
            feats.append(f)
            new += 1
        print('   新增 %d 条（累计 %d）' % (new, len(feats)))
        if not fs or new == 0:
            break
        # 下一页：改用 datetime 上界收窄（earth-search v1 对深分页不稳定）
        last_date = min((f['properties'].get('datetime') or '')[:10] for f in fs)
        if not last_date:
            break
        payload['datetime'] = '2000-01-01T00:00:00Z/%sT00:00:00Z' % last_date

    print('[STAC] 共取回 %d 条' % len(feats))
    if not feats:
        return {}

    by_tile = {}
    for f in feats:
        p = f['properties']
        date = (p.get('datetime') or '')[:10]
        if min_date and date and date < min_date:
            continue
        tile = (p.get('grid:code') or f['id'].split('_')[1]).replace('MGRS-', '')
        cc = p.get('eo:cloud_cover')
        if cc is None:
            continue
        cur = by_tile.get(tile)
        if cur is None or cc < cur[0]:
            by_tile[tile] = (cc, f)

    out = {}
    print('[STAC] tile 数 %d，按云量排序：' % len(by_tile))
    for tile, (cc, f) in sorted(by_tile.items(), key=lambda kv: kv[1][0]):
        ok = cc <= max_cloud
        print('   %-8s 云 %5.1f%%  %s  %s' % (
            tile, cc, f['properties'].get('datetime', '')[:10], '选用' if ok else '跳过'))
        if ok:
            out[tile] = f
    print('[STAC] 采用 %d 景' % len(out))
    return out


def asset_href(f, keys):
    a = f['assets']
    for k in keys:
        if k in a:
            return a[k]['href']
    return None


def read_window(href, bounds, out_size, resampling=Resampling.average):
    """只读 COG 与 bounds 相交的窗口并直接重投影到目标网格（避免整景下载）"""
    w, s, e, n = bounds
    dst = np.zeros((out_size, out_size), dtype=np.float32)
    dst_mask = np.zeros((out_size, out_size), dtype=np.uint8)
    with rasterio.open(href) as src:
        # 影像多为 UTM 投影，必须先把 WGS84 经纬度 bounds 转到源 CRS 再算像素窗口，
        # 否则会把 113.9 当成米来算，窗口落到影像外（Intersection is empty）
        from rasterio.warp import transform_bounds
        sw, ss, se, sn = transform_bounds('EPSG:4326', src.crs, w, s, e, n)
        win = src.window(sw, ss, se, sn)
        win = win.intersection(rasterio.windows.Window(0, 0, src.width, src.height))
        if win.width < 2 or win.height < 2:
            return None, None
        win = win.round_offsets().round_lengths()
        wh, ww = int(win.height), int(win.width)
        if wh < 2 or ww < 2:
            return None, None
        arr = src.read(1, window=win, boundless=False,
                       out_shape=(wh, ww), resampling=Resampling.nearest)
        win_transform = src.window_transform(win)
        reproject(
            source=arr.astype(np.float32),
            destination=dst,
            src_transform=win_transform,
            src_crs=src.crs,
            dst_transform=from_bounds(w, s, e, n, out_size, out_size),
            dst_crs='EPSG:4326',
            src_nodata=src.nodata if src.nodata is not None else 0,
            dst_nodata=0,
            resampling=resampling,
        )
        reproject(
            source=((arr != (src.nodata if src.nodata is not None else 0)) &
                    (arr > 0)).astype(np.uint8),
            destination=dst_mask,
            src_transform=win_transform,
            src_crs=src.crs,
            dst_transform=from_bounds(w, s, e, n, out_size, out_size),
            dst_crs='EPSG:4326',
            dst_nodata=0,
            resampling=Resampling.average,
        )
    return dst, dst_mask


# SCL 场景分类：需要剔除的值
SCL_BAD = {0: '无数据', 1: '饱和/缺陷', 3: '云阴影',
           8: '云(中概率)', 9: '云(高概率)', 10: '薄卷云'}


def process_scene(tile, f, work_size=1024):
    """返回 (ndvi, valid) 两幅 work_size 网格。

    f 可以是 STAC feature（含 assets）或缓存 dict（含 red/nir/scl 直接 href）。
    """
    if 'assets' in f:
        red_h = asset_href(f, ['red', 'B04', 'b04'])
        nir_h = asset_href(f, ['nir', 'nir08', 'B08', 'b08'])
        scl_h = asset_href(f, ['scl', 'SCL'])
    else:
        red_h, nir_h, scl_h = f.get('red'), f.get('nir'), f.get('scl')
    if not red_h or not nir_h:
        print('   %s 缺波段，跳过' % tile)
        return None

    print('   %s 读红/近红外 ...' % tile)
    red, rmask = read_window(red_h, (WEST, SOUTH, EAST, NORTH), work_size)
    nir, nmask = read_window(nir_h, (WEST, SOUTH, EAST, NORTH), work_size)
    if red is None or nir is None:
        print('   %s 窗口为空，跳过' % tile)
        return None

    with np.errstate(invalid='ignore', divide='ignore'):
        nd = (nir.astype(np.float32) - red.astype(np.float32)) / \
             (nir.astype(np.float32) + red.astype(np.float32))
    ok = (rmask > 0.3) & (nmask > 0.3) & np.isfinite(nd) & (nd > -1) & (nd < 1)

    if scl_h:
        print('   %s 读云掩膜 ...' % tile)
        try:
            scl, smask = read_window(scl_h, (WEST, SOUTH, EAST, NORTH), work_size,
                                     resampling=Resampling.nearest)
            if scl is not None:
                bad = np.zeros_like(scl, dtype=bool)
                for v in SCL_BAD:
                    bad |= (scl.round().astype(np.int16) == v)
                # 云掩膜只在读到数据的区域生效
                ok &= (~bad) | (smask < 0.3)
                print('   %s 云掩膜剔除 %.1f%%' % (tile, bad.mean() * 100))
        except Exception as e:
            print('   %s 云掩膜失败(%s)，忽略' % (tile, str(e)[:80]))

    nd = np.where(ok, nd, np.nan)
    cov = ok.mean() * 100
    print('   %s 有效覆盖 %.1f%%' % (tile, cov))
    return nd, ok


def main():
    # 默认不给 STAC 传 datetime（大跨度查询会超时），改为本地按 min_date 过滤
    dt = sys.argv[1] if len(sys.argv) > 1 else None
    cache_file = os.path.join(CACHE, 'scenes.json')

    if os.path.exists(cache_file) and '--fresh' not in sys.argv:
        scenes = json.load(open(cache_file, encoding='utf-8'))
        print('[缓存] 复用 %d 景' % len(scenes))
    else:
        sc = search_scenes(dt)
        scenes = {k: {'id': v['id'],
                      'cloud': v['properties'].get('eo:cloud_cover'),
                      'datetime': v['properties'].get('datetime'),
                      'red': asset_href(v, ['red', 'B04', 'b04']),
                      'nir': asset_href(v, ['nir', 'nir08', 'B08', 'b08']),
                      'scl': asset_href(v, ['scl', 'SCL'])}
                  for k, v in sc.items()}
        json.dump(scenes, open(cache_file, 'w', encoding='utf-8'),
                  ensure_ascii=False, indent=1)

    if not scenes:
        print('没有可用影像，终止')
        return

    stack = []
    metas = []
    for tile, m in scenes.items():
        print('[处理] %s (云 %.1f%%)' % (tile, m.get('cloud') or 0))
        try:
            r = process_scene(tile, m)
        except Exception as e:
            print('   %s 失败: %s' % (tile, str(e)[:200]))
            continue
        if r is None:
            continue
        nd, ok = r
        np.save(os.path.join(CACHE, 'nd_%s.npy' % tile), nd)
        stack.append(nd)
        metas.append({'tile': tile, 'date': (m.get('datetime') or '')[:10],
                      'cloud': m.get('cloud')})
        print('   %s 完成' % tile)

    if not stack:
        print('没有任何景成功，终止')
        return

    # 最大值合成 MVC（NDVI 标准做法：抑制云残留与物候差异）
    print('[合成] %d 景最大值合成 ...' % len(stack))
    A = np.stack(stack, axis=0)
    ndvi = np.nanmax(A, axis=0)
    valid = np.isfinite(ndvi)

    # 用 DEM 掩膜对齐（可选）：此处保留数据自身有效性
    print('[合成] 有效像元 %.1f%%' % (valid.mean() * 100))
    if valid.sum():
        v = ndvi[valid]
        print('[统计] NDVI min %.3f / p5 %.3f / 中位 %.3f / p95 %.3f / max %.3f'
              % (v.min(), np.percentile(v, 5), np.median(v),
                 np.percentile(v, 95), v.max()))

    # 编码：uint8，0 = 无数据，1..255 映射 -1..1
    enc = np.zeros((GRID, GRID), dtype=np.uint8)
    if np.isfinite(ndvi).any():
        vals = np.clip(np.nan_to_num(ndvi, nan=-1.0), -1.0, 1.0)
        enc = np.round((vals + 1.0) / 2.0 * 254.0 + 1.0).astype(np.uint8)
    enc[~np.isfinite(ndvi)] = 0

    b64 = base64.b64encode(enc.tobytes()).decode('ascii')
    print('[输出] base64 %.2f MB' % (len(b64) / 1048576.0))

    lines = [
        '// 自动生成，请勿手改 —— 源脚本：脚本/build_ndvi.py',
        '// 数据源：Sentinel-2 L2A (AWS Earth Search STAC)，最大值合成 MVC，云掩膜 SCL',
        'window.NDVI_DATA = {',
        '  west: %.9f, south: %.9f, east: %.9f, north: %.9f,' % (WEST, SOUTH, EAST, NORTH),
        '  width: %d, height: %d,' % (GRID, GRID),
        '  // 编码: 0=无数据, 1..255 线性映射 NDVI -1..1',
        '  scenes: %s,' % json.dumps(metas, ensure_ascii=False),
        '  data: "%s"' % b64,
        '};',
    ]
    with open(OUT_JS, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))
    print('已写出:', OUT_JS, '(%.2f MB)' % (os.path.getsize(OUT_JS) / 1048576.0))


if __name__ == '__main__':
    main()
