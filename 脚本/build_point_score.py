# -*- coding: utf-8 -*-
"""
矿产地重要性评分 —— 后端计算，输出 point_score.js

输入:
  dash_data.js    points = [lon, lat, cat, county]
  hotspot_data.js Getis-Ord Gi* 冷热点网格（由 build_hotspot.py 生成）

评分模型（三项可解释加权）:
  1. 主导矿种战略权重 W_CAT      —— 赣南以钨、离子吸附型稀土为战略支柱
  2. 共伴生加成  COEF_CO         —— 同一坐标多种矿产，综合利用价值更高
  3. 空间集聚加成 HOT_BONUS      —— 落在 Gi* 热点格的矿点，处于矿脉密集带

输出分级:
  lv2 重点矿产地 / lv1 次级 / lv0 一般

用法:  python 脚本/build_point_score.py
"""
import io
import os
import re
import json
from collections import Counter, OrderedDict

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ---------------- 评分参数（改这里调权重） ----------------
W_CAT = {
    'tungsten':   3.0,   # 钨 —— 赣南「世界钨都」支柱矿种
    'rare_earth': 3.0,   # 稀土 —— 离子吸附型，战略资源
    'rare':       2.4,   # 稀有金属
    'nonferrous': 1.8,   # 有色金属
    'precious':   1.6,   # 贵金属
    'ferrous':    1.2,   # 黑色金属
    'nonmetal':   0.8,   # 非金属
    'other':      0.6,   # 其他
}
COEF_CO = 0.45           # 每多一种共伴生矿种的加分
# 空间集聚项：Gi* z 值连续映射到 [0, HOT_MAX]，避免「热点=常数」把大片钨矿全抬成重点
HOT_MAX = 1.8
GI_CAP = 6.0             # Gi* z 值饱和上限（超过按上限计）
# 分级：按 score 排名分位（保证重点稀缺），并设分数下限兜底
Q_LV2 = 0.06             # 前 6% 为重点矿产地
Q_LV1 = 0.35             # 前 35% 为次级矿产地（含重点之外的部分）
MIN_LV2 = 4.0            # 重点的绝对分数下限
MIN_LV1 = 2.4            # 次级的绝对分数下限

# 矿种中文名
CAT_CN = {
    'tungsten': '钨', 'rare_earth': '稀土', 'rare': '稀有金属',
    'nonferrous': '有色金属', 'precious': '贵金属', 'ferrous': '黑色金属',
    'nonmetal': '非金属', 'other': '其他',
}
# 等级中文名
LV_CN = {2: '重点矿产地', 1: '次级矿产地', 0: '一般矿产地'}


def load_points(path):
    src = io.open(path, encoding='utf-8', errors='replace').read()
    m = re.search(r'points:\s*\[', src)
    if not m:
        raise SystemExit('dash_data.js 中未找到 points 数组')
    seg = src[m.end():]
    rows = re.findall(
        r'\[\s*([-\d.]+)\s*,\s*([-\d.]+)\s*,\s*"([^"]*)"\s*,\s*"([^"]*)"\s*\]', seg)
    return [(float(a), float(b), c, d) for a, b, c, d in rows]


def load_hotspot(path):
    if not os.path.exists(path):
        return None
    src = io.open(path, encoding='utf-8', errors='replace').read()
    m = re.search(r'window\.HOTSPOT_DATA\s*=\s*(\{.*\})', src, re.S)
    if not m:
        return None
    return json.loads(m.group(1))


def main():
    pts = load_points(os.path.join(BASE, 'dash_data.js'))
    hd = load_hotspot(os.path.join(BASE, 'hotspot_data.js'))
    print('原始矿点记录: %d 条' % len(pts))

    # ---- 1. 按坐标聚合（同址多矿种合并为一个矿产地）----
    agg = OrderedDict()
    for lon, lat, cat, county in pts:
        key = (round(lon, 5), round(lat, 5))
        if key not in agg:
            agg[key] = {'lon': lon, 'lat': lat, 'cats': [], 'county': county}
        if cat not in agg[key]['cats']:
            agg[key]['cats'].append(cat)

    # ---- 2. Gi* 网格查找表 ----
    grid = {}
    if hd:
        cw, ch = hd['cell'], hd['cellLat']
        w0, s0 = hd['west'], hd['south']
        cols, rows_n = hd['cols'], hd['rows']
        for c in hd['cells']:
            ci = int((c[0] - w0) / cw)
            rj = int((c[1] - s0) / ch)
            if 0 <= ci < cols and 0 <= rj < rows_n:
                grid[(ci, rj)] = (c[6], float(c[5]))
        print('冷热点网格: %d 格 (band=%.0f km)' % (len(grid), hd.get('bandKm', 0)))
    else:
        print('警告: 未找到 hotspot_data.js，空间集聚项按 0 计')

    def hotspot_at(lon, lat):
        if not hd:
            return '不显著', 0.0
        ci = int((lon - w0) / cw)
        rj = int((lat - s0) / ch)
        if ci < 0 or rj < 0 or ci >= cols or rj >= rows_n:
            return '不显著', 0.0
        return grid.get((ci, rj), ('不显著', 0.0))

    # ---- 3. 打分 ----
    out = []
    for key, a in agg.items():
        cats = a['cats']
        dom = max(cats, key=lambda c: W_CAT.get(c, 0.6))
        base = W_CAT.get(dom, 0.6)
        co = COEF_CO * (len(cats) - 1)
        hs_cls, gi = hotspot_at(a['lon'], a['lat'])
        hs = round(max(0.0, min(gi, GI_CAP)) / GI_CAP * HOT_MAX, 3)
        score = round(base + co + hs, 3)
        out.append({
            'lon': a['lon'], 'lat': a['lat'],
            'cats': cats, 'dom': dom, 'county': a['county'],
            'score': score, 'lv': 0, 'hs': hs_cls, 'gi': round(gi, 3),
        })

    # ---- 4. 按分位分级（重点稀缺化）----
    out.sort(key=lambda x: -x['score'])
    n = len(out)
    i_lv2 = max(1, int(round(n * Q_LV2)))
    i_lv1 = max(i_lv2 + 1, int(round(n * Q_LV1)))
    for i, o in enumerate(out):
        if i < i_lv2 and o['score'] >= MIN_LV2:
            o['lv'] = 2
        elif i < i_lv1 and o['score'] >= MIN_LV1:
            o['lv'] = 1
        else:
            o['lv'] = 0

    # ---- 4. 统计 ----
    lv_cnt = Counter(o['lv'] for o in out)
    print('聚合后矿产地: %d 处 (合并同址 %d 处)' % (len(out), len(pts) - len(out)))
    for lv in (2, 1, 0):
        print('  lv%d %s: %d 处' % (lv, LV_CN[lv], lv_cnt.get(lv, 0)))
    print('score 范围: %.2f ~ %.2f' % (min(o['score'] for o in out),
                                       max(o['score'] for o in out)))
    hist = Counter(round(o['score'], 1) for o in out)
    print('score 分布: ' + ', '.join(
        '%.1f:%d' % (k, hist[k]) for k in sorted(hist, reverse=True)))
    print('主导矿种分布: ' + str(dict(Counter(o['dom'] for o in out))))
    hs_dist = Counter(o['hs'] for o in out)
    print('所在网格类型: ' + str(dict(hs_dist)))
    print('多矿种点位数: %d' % sum(1 for o in out if len(o['cats']) > 1))

    # ---- 5. 输出 ----
    payload = {
        'meta': {
            'total': len(out), 'raw': len(pts),
            'qLv2': Q_LV2, 'qLv1': Q_LV1, 'minLv2': MIN_LV2, 'minLv1': MIN_LV1,
            'hotMax': HOT_MAX, 'giCap': GI_CAP,
            'wCat': W_CAT, 'coefCo': COEF_CO,
            'catCn': CAT_CN, 'lvCn': LV_CN,
            'lvCount': {str(k): lv_cnt.get(k, 0) for k in (0, 1, 2)},
        },
        'pts': out,
    }
    dst = os.path.join(BASE, 'point_score.js')
    with io.open(dst, 'w', encoding='utf-8') as f:
        f.write('window.POINT_SCORE = ')
        f.write(json.dumps(payload, ensure_ascii=False, separators=(',', ':')))
        f.write(';\n')
    print('已写出 %s (%.1f KB)' % (dst, os.path.getsize(dst) / 1024.0))

    # 预览前 8 个重点
    print('--- 重点矿产地 Top8 ---')
    for o in [x for x in out if x['lv'] == 2][:8]:
        print('  %.4f,%.4f %s score=%.2f 矿种=%s 网格=%s' % (
            o['lon'], o['lat'], o['county'], o['score'],
            '/'.join(CAT_CN.get(c, c) for c in o['cats']), o['hs']))


if __name__ == '__main__':
    main()
