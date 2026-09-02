# -*- coding: utf-8 -*-
"""
矿区标准化分类 —— 复合矿区拆分
规则：含多矿种、复合标识的矿区，拆分为独立单矿种条目，一个矿种一行
"""

import os, sys, json
import shapefile
import numpy as np
from shapely.geometry import Point, shape as shapely_shape

BASE = r"E:\Data\赣州稀土"
NATL_SHP = os.path.join(BASE, r"【250610】全国矿产地分布数据\原始数据", "全国矿产地分布数据.shp")
CITY_SHP = os.path.join(BASE, "市级", "赣州市_360700.shp")
OUTPUT = os.path.join(BASE, "矿区标准化分类结果")
os.makedirs(OUTPUT, exist_ok=True)

# ============================================
# 1. 编码修复
# ============================================
def latin1_to_gbk(s):
    """将 latin-1 误读的字符串修复为正确编码（UTF-8 优先，GBK/GB18030 兜底）"""
    try:
        return s.encode('latin-1').decode('utf-8')
    except (UnicodeDecodeError, UnicodeEncodeError):
        try:
            return s.encode('latin-1').decode('gbk')
        except (UnicodeDecodeError, UnicodeEncodeError):
            try:
                return s.encode('latin-1').decode('gb18030')
            except:
                return s

# ============================================
# 2. 复合矿种拆分规则
# ============================================
# 直接拆分分隔符
SPLIT_SEPS = ['-', '—', '～', '~', '、', '+', '/', '|']

# 复合矿种关键词映射 (复合名 → [单矿种列表])
COMPOUND_MAP = {
    '铅锌矿':    ['铅矿', '锌矿'],
    '锌铅矿':    ['锌矿', '铅矿'],
    '铌钽矿':    ['铌矿', '钽矿'],
    '钽铌矿':    ['钽矿', '铌矿'],
    '金银矿':    ['金矿', '银矿'],
    '银金矿':    ['银矿', '金矿'],
    '铜金矿':    ['铜矿', '金矿'],
    '铜银矿':    ['铜矿', '银矿'],
    '铁锰矿':    ['铁矿', '锰矿'],
    '铜钼矿':    ['铜矿', '钼矿'],
    '钨锡矿':    ['钨矿', '锡矿'],
    '钨钼矿':    ['钨矿', '钼矿'],
    '锡钨矿':    ['锡矿', '钨矿'],
    '铜铅锌矿':  ['铜矿', '铅矿', '锌矿'],
    '金银铅锌矿': ['金矿', '银矿', '铅矿', '锌矿'],
    '铁铜矿':    ['铁矿', '铜矿'],
    '铁锌矿':    ['铁矿', '锌矿'],
    '铜钴矿':    ['铜矿', '钴矿'],
    '铅锌银矿':  ['铅矿', '锌矿', '银矿'],
    '钨铋矿':    ['钨矿', '铋矿'],
    '稀土矿':    ['稀土矿'],   # 单矿种
    '硫铁矿':    ['硫铁矿'],    # 单矿种(已有独立分类)
    '独居石':    ['独居石'],
    '磷钇矿':    ['磷钇矿'],
}

# 矿种名称标准化映射 (别名 → 标准名)
ALIAS_MAP = {
    '钨金属矿': '钨矿',
    '钨': '钨矿',
    '铁': '铁矿',
    '铜': '铜矿',
    '铅': '铅矿',
    '锌': '锌矿',
    '金': '金矿',
    '银': '银矿',
    '锡': '锡矿',
    '钼': '钼矿',
    '锰': '锰矿',
    '钴': '钴矿',
    '镍': '镍矿',
    '锂': '锂矿',
    '铌': '铌矿',
    '钽': '钽矿',
    '锑': '锑矿',
    '铋': '铋矿',
    '汞': '汞矿',
    '锶': '锶矿',
    '锆': '锆矿',
    '铬': '铬矿',
    '钒': '钒矿',
    '钛': '钛矿',
    '铝': '铝矿',
    '镁': '镁矿',
    '铍': '铍矿',
    '锗': '锗矿',
    '镓': '镓矿',
    '铟': '铟矿',
    '镉': '镉矿',
    '铂': '铂矿',
    '钯': '钯矿',
    '稀土': '稀土矿',
    '煤': '煤矿',
    '石油': '石油',
    '天然气': '天然气',
    '油页岩': '油页岩',
    '石煤': '石煤',
    '泥炭': '泥炭',
    '铀': '铀矿',
    '钍': '钍矿',
}


# 矿种 → 大类分类映射（依据《矿产资源分类细目》2019 + GB/T 17766-2020）
MINERAL_CATEGORY_MAP = {
    # 黑色金属矿产
    '铁矿': '黑色金属矿产',
    '锰矿': '黑色金属矿产',
    '钛矿': '黑色金属矿产',
    # 有色金属矿产
    '铜矿': '有色金属矿产',
    '铅矿': '有色金属矿产',
    '锌矿': '有色金属矿产',
    '钨矿': '有色金属矿产',
    '锡矿': '有色金属矿产',
    '钼矿': '有色金属矿产',
    '铋矿': '有色金属矿产',
    '钴矿': '有色金属矿产',
    # 贵金属矿产
    '金矿': '贵金属矿产',
    '砂金': '贵金属矿产',
    '银矿': '贵金属矿产',
    # 稀有金属矿产
    '钽矿': '稀有金属矿产',
    '铌矿': '稀有金属矿产',
    '铍矿': '稀有金属矿产',
    '锆矿': '稀有金属矿产',
    '铪矿': '稀有金属矿产',
    # 稀土金属矿产
    '稀土矿': '稀土金属矿产',
    '磷钇矿': '稀土金属矿产',
    '钇矿': '稀土金属矿产',
    # 非金属矿产
    '石灰岩': '非金属矿产',
    '水泥用灰岩': '非金属矿产',
    '水泥配料用粘土': '非金属矿产',
    '水泥配料用砂岩': '非金属矿产',
    '水泥配料页岩（含板岩）': '非金属矿产',
    '高岭土': '非金属矿产',
    '萤石': '非金属矿产',
    '盐矿': '非金属矿产',
    '硫铁矿': '非金属矿产',
}


def get_mineral_category(mineral_name):
    """获取矿种所属大类"""
    return MINERAL_CATEGORY_MAP.get(mineral_name, '其他矿产')


def split_mineral(kz_str):
    """
    拆分复合矿种为单矿种列表
    返回: [(矿种名, 是否拆分), ...]
    """
    kz = kz_str.strip()
    if not kz:
        return [('未知', False)]

    # 1. 先检查复合矿种映射
    if kz in COMPOUND_MAP:
        parts = COMPOUND_MAP[kz]
        return [(p, len(parts) > 1) for p in parts]

    # 2. 按分隔符拆分
    for sep in SPLIT_SEPS:
        if sep in kz:
            parts = [p.strip() for p in kz.split(sep) if p.strip()]
            if len(parts) > 1:
                result = []
                for p in parts:
                    # 递归处理（可能有嵌套复合）
                    sub = split_mineral(p)
                    result.extend(sub)
                return result

    # 3. 单矿种，标准化
    std = ALIAS_MAP.get(kz, kz)
    return [(std, False)]


# ============================================
# 3. 主流程：读取 → 裁剪 → 拆分 → 输出
# ============================================
print("=" * 60)
print("赣州矿区标准化分类与复合矿区拆分")
print("=" * 60)

# 加载赣州边界
print("\n[1] 加载赣州边界...")
city_sf = shapefile.Reader(CITY_SHP, encoding='gbk')
city_parts = []
for shp in city_sf.shapes():
    ps = list(shp.parts) + [len(shp.points)]
    for i in range(len(ps) - 1):
        ring = shp.points[ps[i]:ps[i+1]]
        if ring:
            from shapely.geometry import Polygon as ShapelyPolygon, MultiPolygon
            city_parts.append(ShapelyPolygon(ring))

from shapely.ops import unary_union
from shapely.prepared import prep
city_geom = unary_union(city_parts)
prepared_city = prep(city_geom)
print(f"  边界加载完成")

# 加载全国矿产地数据
print("\n[2] 加载全国矿产地数据...")
natl_sf = shapefile.Reader(NATL_SHP, encoding='latin-1')
fields_raw = [f[0] for f in natl_sf.fields[1:]]
# 修复字段名编码
fields = [latin1_to_gbk(f) for f in fields_raw]
print(f"  字段: {fields}")
print(f"  总记录: {len(natl_sf.records())}")

kz_idx = fields.index('kz')
mc_idx = fields.index('mc')
lon_idx = fields.index('lon')
lat_idx = fields.index('lat')

# 字段索引（用于复制属性）
field_indices = {f: i for i, f in enumerate(fields)}

# ============================================
# 4. 筛选赣州矿点 + 拆分
# ============================================
print("\n[3] 筛选赣州矿点并拆分复合矿区...")

gz_records_original = []  # 原始记录
gz_records_split = []     # 拆分后记录

batch_size = 5000
total = len(natl_sf.records())
n_batches = (total + batch_size - 1) // batch_size

for batch in range(n_batches):
    start = batch * batch_size
    end = min(start + batch_size, total)
    shapes_batch = natl_sf.shapes()[start:end]
    records_batch = natl_sf.records()[start:end]

    for shp, rec in zip(shapes_batch, records_batch):
        pt = Point(shp.points[0])
        if not (prepared_city.contains(pt) or prepared_city.intersects(pt)):
            continue

        # 修复编码
        rec_fixed = []
        for i, val in enumerate(rec):
            if isinstance(val, str):
                rec_fixed.append(latin1_to_gbk(val))
            else:
                rec_fixed.append(val)

        gz_records_original.append(rec_fixed)

        # 拆分矿种
        kz_raw = rec_fixed[kz_idx]
        mineral_parts = split_mineral(kz_raw)

        for mineral_name, was_split in mineral_parts:
            new_rec = rec_fixed.copy()
            new_rec[kz_idx] = mineral_name  # 替换为单矿种名
            gz_records_split.append((new_rec, shp, was_split))

    if (batch + 1) % 2 == 0:
        sys.stdout.write(f"\r  处理中: {end}/{total}, 赣州原始: {len(gz_records_original)}, 拆分后: {len(gz_records_split)}")
        sys.stdout.flush()

print(f"\r  处理完成: {total}/{total}")
print(f"  赣州原始矿点: {len(gz_records_original)} 条")
print(f"  拆分后矿点:   {len(gz_records_split)} 条")
print(f"  拆分新增:     {len(gz_records_split) - len(gz_records_original)} 条")

# ============================================
# 5. 统计分类
# ============================================
print("\n[4] 标准化分类统计...")

kz_count = {}
for rec, _, _ in gz_records_split:
    kz = rec[kz_idx]
    kz_count[kz] = kz_count.get(kz, 0) + 1

print(f"  Unique minerals after split: {len(kz_count)}")
# Write to file to avoid console encoding issues
with open(os.path.join(OUTPUT, "mineral_distribution.txt"), 'w', encoding='utf-8') as f:
    for kz, cnt in sorted(kz_count.items(), key=lambda x: -x[1]):
        f.write(f"[{cnt:4d}] {kz}\n")
print("  (distribution written to file)")

# ============================================
# 6. 导出拆分后 shapefile
# ============================================
print("\n[5] 导出结果...")

# 6a. 拆分后完整数据
out_shp = os.path.join(OUTPUT, "赣州矿场点_拆分后.shp")
w = shapefile.Writer(out_shp, shapeType=1, encoding='utf-8')
# 添加字段
for f in fields:
    w.field(f, 'C', 254)
w.field('was_split', 'C', 10)  # 标记是否被拆分

for rec, shp, was_split in gz_records_split:
    w.record(*rec, 'Y' if was_split else 'N')
    w.point(*shp.points[0])
w.close()

# 复制 prj
import shutil
shutil.copy(NATL_SHP.replace('.shp', '.prj'), out_shp.replace('.shp', '.prj'))
print(f"  已保存: {out_shp}")

# 6b. 按矿种分类导出（各矿种单独 shapefile）
print("\n[6] 按矿种分类导出...")
mineral_groups = {}
for rec, shp, was_split in gz_records_split:
    kz = rec[kz_idx]
    if kz not in mineral_groups:
        mineral_groups[kz] = []
    mineral_groups[kz].append((rec, shp, was_split))

# 导出主要矿种（数量 >= 5）
main_minerals_dir = os.path.join(OUTPUT, "按矿种分类")
os.makedirs(main_minerals_dir, exist_ok=True)

for kz, items in sorted(mineral_groups.items(), key=lambda x: -len(x[1])):
    if len(items) < 5:
        continue
    safe_name = kz.replace('/', '_').replace('\\', '_').replace(':', '_')[:50]
    m_shp = os.path.join(main_minerals_dir, f"矿种_{safe_name}.shp")
    w = shapefile.Writer(m_shp, shapeType=1, encoding='utf-8')
    for f in fields:
        w.field(f, 'C', 254)
    w.field('was_split', 'C', 10)

    for rec, shp, was_split in items:
        w.record(*rec, 'Y' if was_split else 'N')
        w.point(*shp.points[0])
    w.close()
    shutil.copy(NATL_SHP.replace('.shp', '.prj'), m_shp.replace('.shp', '.prj'))

n_shp = len([x for x in os.listdir(main_minerals_dir) if x.endswith('.shp')])
print(f"  按矿种分类 shapefile: {main_minerals_dir}/ ({n_shp} files)")

# ============================================
# 7. 按矿种大类分类导出
# ============================================
print("\n[7] 按矿种大类分类导出...")

category_groups = {}
for rec, shp, was_split in gz_records_split:
    kz = rec[kz_idx]
    cat = get_mineral_category(kz)
    if cat not in category_groups:
        category_groups[cat] = []
    category_groups[cat].append((rec, shp, was_split))

category_dir = os.path.join(OUTPUT, "按矿种大类")
os.makedirs(category_dir, exist_ok=True)

for cat, items in sorted(category_groups.items(), key=lambda x: -len(x[1])):
    safe_cat = cat
    cat_shp = os.path.join(category_dir, f"{safe_cat}.shp")
    w = shapefile.Writer(cat_shp, shapeType=1, encoding='utf-8')
    for f in fields:
        w.field(f, 'C', 254)
    w.field('was_split', 'C', 10)
    w.field('大类', 'C', 50)

    for rec, shp, was_split in items:
        w.record(*rec, 'Y' if was_split else 'N', cat)
        w.point(*shp.points[0])
    w.close()
    shutil.copy(NATL_SHP.replace('.shp', '.prj'), cat_shp.replace('.shp', '.prj'))

n_cat_shp = len([x for x in os.listdir(category_dir) if x.endswith('.shp')])
print(f"  按矿种大类 shapefile: {category_dir}/ ({n_cat_shp} files)")

# ============================================
# 8. 生成分类统计报告
# ============================================
print("\n[8] 生成统计报告...")

report = f"""============================================================
赣州矿区标准化分类与复合矿区拆分报告
============================================================

数据来源: 全国矿产地分布数据 (2025)
处理范围: 赣州市行政边界内
处理日期: 2026-07-21

------------------------------------------------------------
拆分统计
------------------------------------------------------------
原始矿点记录:     {len(gz_records_original)} 条
拆分后矿点记录:   {len(gz_records_split)} 条
新增记录:         {len(gz_records_split) - len(gz_records_original)} 条
拆分后矿种种类:   {len(kz_count)} 种

------------------------------------------------------------
拆分规则
------------------------------------------------------------
1. 复合分隔符拆分: "-" "—" "~" "、" "+" "/" "|"
2. 复合矿种关键词识别: 铅锌矿→铅矿+锌矿, 铌钽矿→铌矿+钽矿 等
3. 矿种名称标准化映射
4. 每个拆分后的矿体/矿种单独占一行,原始属性完整保留

------------------------------------------------------------
拆分后矿种分布 (前50)
------------------------------------------------------------
"""
for kz, cnt in sorted(kz_count.items(), key=lambda x: -x[1])[:50]:
    report += f"  [{cnt:4d}] {kz}\n"

report += f"""
------------------------------------------------------------
拆分示例
------------------------------------------------------------
"""

# 找几个拆分案例
split_examples = []
for orig_rec in gz_records_original:
    kz = orig_rec[kz_idx]
    parts = split_mineral(kz)
    if len(parts) > 1:
        split_examples.append((orig_rec[mc_idx], kz, [p[0] for p in parts]))
        if len(split_examples) >= 10:
            break

for mc, orig_kz, new_kzs in split_examples:
    report += f"  {mc}: [{orig_kz}] → {new_kzs}\n"

# 大类统计
report += f"""
------------------------------------------------------------
矿种大类分布
------------------------------------------------------------
"""
cat_count = {}
for rec, _, _ in gz_records_split:
    kz = rec[kz_idx]
    cat = get_mineral_category(kz)
    cat_count[cat] = cat_count.get(cat, 0) + 1

for cat, cnt in sorted(cat_count.items(), key=lambda x: -x[1]):
    pct = cnt / len(gz_records_split) * 100
    report += f"  [{cnt:4d}] {cat} ({pct:.1f}%)\n"

with open(os.path.join(OUTPUT, "矿区分类拆分报告.txt"), 'w', encoding='utf-8') as f:
    f.write(report)

print("  报告已保存")

# CSV统计表
csv_path = os.path.join(OUTPUT, "矿种分类统计.csv")
with open(csv_path, 'w', encoding='utf-8-sig') as f:
    f.write("矿种名称,矿点数\n")
    for kz, cnt in sorted(kz_count.items(), key=lambda x: -x[1]):
        f.write(f"{kz},{cnt}\n")

print(f"  CSV已保存: {csv_path}")

# 大类CSV统计表
cat_csv_path = os.path.join(OUTPUT, "矿种大类统计.csv")
with open(cat_csv_path, 'w', encoding='utf-8-sig') as f:
    f.write("矿种大类,矿点数,占比(%)\n")
    for cat, cnt in sorted(cat_count.items(), key=lambda x: -x[1]):
        pct = cnt / len(gz_records_split) * 100
        f.write(f"{cat},{cnt},{pct:.1f}\n")
print(f"  大类CSV已保存: {cat_csv_path}")

# ============================================
# 汇总
# ============================================
print(f"\n{'='*60}")
print("Output file listing written to: " + os.path.join(OUTPUT, "输出文件清单.txt"))
# Write file listing to disk (UTF-8) to avoid console encoding issues
with open(os.path.join(OUTPUT, "输出文件清单.txt"), 'w', encoding='utf-8') as f:
    n_total_shp = 0
    for fname in sorted(os.listdir(OUTPUT)):
        fpath = os.path.join(OUTPUT, fname)
        if os.path.isdir(fpath):
            n_files = len([x for x in os.listdir(fpath) if x.endswith('.shp')])
            n_total_shp += n_files
            f.write(f"  {fname}/ ({n_files} shapefiles)\n")
        else:
            size = os.path.getsize(fpath)
            f.write(f"  {fname} ({size:,} bytes)\n")
    f.write(f"\nTotal shapefiles: {n_total_shp}\n")
print(f"Total shapefiles exported: {n_total_shp}")

print(f"\nDone! Output: {OUTPUT}/")
