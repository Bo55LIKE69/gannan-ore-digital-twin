# ⛰️ 赣南矿脉数字孪生大屏

> **作者**：谢泓铎 · GIS实验室
> 基于 **CesiumJS 1.114** 的赣南稀土矿脉三维数字孪生可视化大屏：
> 用本地 **30m DEM** 自建真三维地形 Primitive（**不依赖任何 terrainProvider**），
> 叠加 **408 个矿点**（统一渲染、逐点标识、穿透地表锚点），
> 并把 **核密度 / LISA / Gi\* 冷热点 / 县级统计** 等空间分析结果
> **贴合到 DEM 起伏表面**渲染，而非贴椭球面。

> 全部地形构网、高程采样、图层贴地、着色器配色均为手写代码，
> **未使用任何第三方地形服务或商业底图**，可在纯离线环境下打开（Cesium 库本身走 CDN，可自行本地化）。

---

## ✨ 功能特性

| 环节 | 说明 |
|------|------|
| 🏔️ 真三维地形 | 本地 DEM 重采样后构建自定义 `Primitive` 三角网，暖土黄/赭石/金配色 + 山体阴影 + 雾效 |
| 📈 高程夸张 | 提供夸张系数滑杆，`EXAG` 变化时地形与分析图层同步重建（图层始终贴着山体走） |
| 🗺️ 等高线 | 1000m 主等高线（暗褐描边）+ 200m 次等高线（浅金），随地形起伏绘制 |
| 📍 矿点渲染 | 408 个矿点统一处理，每点带地表锚点 + 光柱 + 名称标识，`disableDepthTestDistance` 穿透不被山体遮挡 |
| 🔥 冷热点 | 按**县级行政边界**（非方格网）上色，红=热点聚集、蓝=冷点 |
| 📊 空间分析图层 | 核密度 / LISA 空间自相关 / Gi\* 冷热点(网格) / 县级矿山统计，共 4 个图层可视化开关 |
| 🎛️ 图层贴地 | 多边形自适应细分（目标 ~900m）后**逐顶点按 DEM 采样抬升 +70m**，顶点色 + 自定义 Appearance，单 draw call |
| 🧭 章节导览 | 6 个预设章节（总览 / 地形 / 矿点 / 空间分析 / 工艺演进 / 治理），自动飞行 + 图层联动 |
| 💡 无水印 | 已移除 Cesium 版权水印与默认控件，界面为暗色大屏风格 |

## 🚀 快速开始

页面通过 `<script src>` 加载本地数据 js，**需通过 HTTP 打开**（`file://` 协议下部分浏览器会拦截）。

```bash
# 任意静态服务器均可
python -m http.server 8123
```

浏览器访问 **http://127.0.0.1:8123/赣南矿脉_数字孪生大屏.html**

> 若嫌中文路径麻烦，把 5 个 `*.js` 与 `.html` 放同一目录后改名为 `index.html` 即可。

### 无需构建

项目是**纯静态页面**，没有 npm、没有打包步骤、没有后端。
只要 `赣南矿脉_数字孪生大屏.html` 与同目录 5 个数据 js 齐全即可运行。

## 🧑‍💻 使用流程

1. **打开页面** → 等待 DEM 构网完成，自动飞入赣南全景
2. **切章节** → 点顶栏/侧栏章节按钮，相机自动飞到对应视角并联动图层
3. **开关图层** → 右侧「显示图层」控制矿点/等高线/县域边界；「空间分析图层」控制 4 个分析结果
4. **调高程夸张** → 拖动滑杆，地形与所有贴地图层会同步重建（约 1~2 秒）
5. **点矿点** → 弹出该矿点详情（矿种、县区、规模、评分）

## 🗂️ 目录结构

```
├── 赣南矿脉_数字孪生大屏.html   # 主页面（全部逻辑内联，约 84KB）
├── dem_terrain_data.js          # DEM 高程/山体阴影数据（window.DEM_DATA，4.2MB）
├── analysis_layers.js           # 8 类空间分析结果几何（window.AL + AL_META，4.4MB）
├── dash_data.js                 # 矿点、县界、统计、工艺等大屏数据（window.D）
├── hotspot_data.js              # 县级冷热点结果
├── point_score.js               # 矿点综合评分
├── 脚本/
│   ├── build_dem_terrain.py     # DEM → dem_terrain_data.js（rasterio）
│   ├── build_analysis_layers.py # shapefile → analysis_layers.js（ogr2ogr + 坐标压缩）
│   ├── build_hotspot.py         # 县级冷热点计算 → hotspot_data.js
│   ├── build_point_score.py     # 矿点评分 → point_score.js
│   ├── spatial_analysis.py      # 核密度 / 最近邻 / 泰森多边形
│   ├── lisa_cluster_map.py      # LISA 局部空间自相关
│   ├── hotspot_analysis.py      # Gi* 冷热点
│   ├── hotspot_county.py        # 县级统计与热点县识别
│   ├── mineral_classification.py# 矿种分类
│   ├── ch2_leaflet_map.py       # 第二章 Leaflet 底图
│   ├── create_charts.py         # 统计图表
│   └── archive/ ndvi/           # 归档与 NDVI 相关脚本
├── docs/                        # 预览截图
└── README.md
```

## 🔧 数据重建（可选）

仓库中已包含**构建好的数据 js**，直接打开页面即可。
若需从原始 DEM / shapefile 重新生成：

```bash
pip install numpy rasterio          # 另需 GDAL 的 ogr2ogr（conda 安装 gdal 即可）

python 脚本/build_dem_terrain.py     # 读 数据/DEM/ganzhou_dem.tif → dem_terrain_data.js
python 脚本/build_point_score.py     # → point_score.js
python 脚本/build_hotspot.py         # → hotspot_data.js
python 脚本/build_analysis_layers.py # 读 结果输出/*.shp → analysis_layers.js
```

> `脚本/build_analysis_layers.py` 里的 `OGR` 路径指向本机 conda 的 `ogr2ogr.exe`，换机器需自行修改。

## 🧠 三个关键实现坑（写给要改代码的人）

1. **`Appearance` 基类不保存 `options.uniforms`**
   创建后必须手动 `appearance.uniforms = { ... }`，且 uniform 值必须是**普通值**：
   `getUniformFunction` 会再包一层，传函数进去 `uniform.value` 会变成函数对象。

2. **拾取通道自动引用 `batchId`**
   自定义几何必须声明 `in float batchId` 并补一条全 0 的 `Float32Array` 属性，
   否则编译报 `undeclared identifier 'batchId'`。也可用 `allowPicking: false` 跳过拾取通道。

3. **`GroundPrimitive` 贴不到自建 DEM 上**
   本 DEM 是自定义 `Primitive`，**没有 terrainProvider**，
   `GroundPrimitive` 只会贴到椭球面（高 0），直接被山体埋掉。
   必须自己按 DEM 逐顶点采样高程、构建三角网抬升。

> 另：Cesium 渲染后会释放 geometry，测试时读不到 `geometryInstances`，
> 需在 mesh 上挂自定义统计字段再断言。

## 🛠️ 技术栈

CesiumJS 1.114 · 自写 GLSL（顶点色 + 自定义 Appearance）· Python（numpy / rasterio / GDAL）· 原生 HTML/CSS/JS

## 📄 许可

MIT

## 👤 作者

**谢泓铎** · GIS实验室

- GitHub：[@Bo55LIKE69](https://github.com/Bo55LIKE69)
- 项目仓库：<https://github.com/Bo55LIKE69/gannan-ore-digital-twin>
