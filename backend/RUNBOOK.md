# 全国矿点数据库 · 上手步骤（照抄即可跑）

> 目标：PostgreSQL 存全国 33144 个矿点 → FastAPI 提供「视口查询」接口。
> 全程在 `E:\Data\赣州稀土\backend\` 下操作，终端用 Git Bash。
> **2026-09-11 已全部跑通并验证**，以下是复现步骤。

## 0. 前置（已就绪，不用再做）

| 事项 | 状态 |
|---|---|
| PostgreSQL 17.10 二进制 | ✅ 直接用系统的 `C:\Program Files\PostgreSQL\17\bin`（不碰系统 5432 实例，自己 initdb 一个 5433 trust 实例） |
| `backend/.venv`（fastapi/uvicorn/psycopg2） | ✅ |
| `load_national.py`（全国 CSV → mines_cn 表） | ✅ 已导入 33144 条 |
| 接口 `/mines_cn` `/stats_cn` | ✅ 已验证 |
| PostGIS | ❌ 没装上（conda 镜像 2026-09 全灭：bfsu/tuna/ustc/NJU 缺包或超时），**自动降级纯 SQL bbox 模式**，3 万点毫秒级，够用 |

> 教训：镜像选型顺序记录在案 —— NJU conda-forge 能拿到索引但缺 `postgis` 包，且大文件 .conda 下载被代理掐死；bfsu/tuna/ustc/腾讯/阿里/华为全灭。将来 PostGIS 渠道恢复后，`load_national.py` 和接口会自动升级回 geom 模式（代码已双模自适应）。

## 1. 启动数据库实例（端口 5433，trust 免密）

```bash
cd /e/Data/赣州稀土/backend
.venv/Scripts/python.exe pg_launcher.py
```

`config.py` 默认已指向系统 PG17 的 bin，无需设环境变量。关机后重跑这条即可（initdb 自动跳过）。

停止实例：`.venv/Scripts/python.exe pg_launcher.py stop`

## 2. 导入全国矿点（已做过，重导也安全：TRUNCATE 后重灌）

```bash
.venv/Scripts/python.exe load_national.py
```

数据源：`数据/全国矿产地分布/原始数据/全国矿产地分布数据.csv`
规模：33144 条（矿点 11480 / 小型 10765 / 中型 5768 / 大型 2629 / 矿化点 2147 / 特大型 355）
表：`gannan_ore.mines_cn`（name/kind/scale/status/lon/lat）

## 3. 起接口服务（端口 8000）

```bash
.venv/Scripts/python.exe -m uvicorn app:app --host 127.0.0.1 --port 8000 --reload
```

保持终端开着；浏览器开 http://127.0.0.1:8000/docs 有可视化调试页。

## 4. 验证（另开终端）

```bash
curl -s http://127.0.0.1:8000/health
curl -s http://127.0.0.1:8000/stats_cn

# 赣州视口内的矿点
curl -s "http://127.0.0.1:8000/mines_cn?bbox=114.5,25.2,115.0,25.9&limit=5"

# 全国稀土矿（注意：这库里叫"稀土矿"，不是"稀土"！还有磷钇矿/钇矿/铈矿/镧矿）
curl -s "http://127.0.0.1:8000/mines_cn?kind=%E7%A8%80%E5%9C%9F%E7%9F%BF&limit=5"

# 赣南稀土视口（龙南-定南离子型稀土带）
curl -s "http://127.0.0.1:8000/mines_cn?bbox=114.6,24.5,115.2,25.0&kind=%E7%A8%80%E5%9C%9F%E7%9F%BF"
```

实测：赣州 bbox 内稀土矿点 20 个（定南礼亨稀土矿、下庄稀土矿点等）。

## 5. 用 SQL 直接玩（免沙箱终端 / 任意 psql 客户端）

```bash
"C:\Program Files\PostgreSQL\17\bin\psql.exe" -h 127.0.0.1 -p 5433 -U postgres -d gannan_ore
```

```sql
-- 按规模分组
SELECT scale, count(*) FROM mines_cn GROUP BY scale ORDER BY 2 DESC;

-- 中国境内任意点 50km 半径（Haversine 近似，米级）
SELECT name, kind,
  6371000 * acos(cos(radians(25.83)) * cos(radians(lat)) *
        cos(radians(lon) - radians(114.93)) + cos(radians(25.83)) *
        sin(radians(lat)) * sin(radians(lat))) AS dist_m
FROM mines_cn
WHERE lon BETWEEN 114.93-0.6 AND 114.93+0.6 AND lat BETWEEN 25.83-0.6 AND 25.83+0.6
ORDER BY dist_m LIMIT 10;
```

> ⚠ psql 在 Windows 终端里写中文 WHERE 条件可能因编码坑匹配不上（服务端是 UTF8），
> 建议复杂中文查询走 Python psycopg2 或 API。

## 下一步（接前端大屏）

把大屏里 `point_score.js` 的静态加载换成 `fetch('/mines_cn?bbox=...')`：
- 地图 `moveend` 事件里取当前视口 bbox → 请求该范围矿点 → 渲染；
- 全国缩放时用 `/stats_cn` 或后端聚合显示气泡，放大到省/市再展开单点；
- 408 赣州点数据仍保留（`mines` 表 + 原 JS），全国层做第二图层开关。
