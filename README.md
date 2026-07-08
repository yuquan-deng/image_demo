# 本地图片检索 Demo

这个 demo 用本地 Web 页面完成单图检索：把测试图片放入 `data/images/`，构建索引后上传一张查询图，系统会从本地图片集中返回视觉相同或高度相似的图片。

项目定位是轻量级本地原型，不依赖数据库、向量库或独立后端服务。核心能力集中在传统图像相似度算法与 Streamlit 页面交互上，适合验证本地图片去重、相似图召回、低成本商品图/素材图检索等场景。

## 技术栈总览

| 层级 | 技术 | 用途 |
| --- | --- | --- |
| 运行时 | Python 3.12 | 项目主语言和本地运行环境 |
| Web UI | Streamlit 1.28.1 | 构建本地 Web 页面、侧边栏配置、文件上传和结果展示 |
| 图像读取与处理 | Pillow | 打开、转换、缩放 JPG/PNG/WEBP/BMP 等图片 |
| 数值计算 | NumPy | 像素数组处理、DCT 计算、相似度计算 |
| 感知哈希 | imagededup PHash | 优先使用的 PHash 后端，用于视觉近似图片召回 |
| 本地 PHash 回退 | 自实现 DCT PHash | 当 imagededup 不可用时仍可计算感知哈希 |
| 局部特征匹配 | OpenCV headless | 使用 ORB、BFMatcher、RANSAC 识别裁剪图或局部相似图 |
| 数据存储 | JSON 文件 | 将索引写入 `data/index.json`，无数据库依赖 |
| 测试 | pytest | 覆盖核心检索链路和 UI 展示辅助函数 |

## 项目结构

```text
D:\image_demo1
├── app.py                         # Streamlit 页面入口和展示层
├── image_search.py                # 图片索引、哈希、检索和相似度算法
├── requirements.txt               # Python 依赖
├── README.md                      # 项目说明
├── data
│   ├── images                     # 本地图片集
│   └── index.json                 # 构建后的图片索引
└── tests
    ├── test_image_search.py       # 检索行为测试
    └── test_app_presentation.py   # 展示层格式化测试
```

## 安装依赖

```powershell
python -m pip install -r requirements.txt
```

主要依赖见 `requirements.txt`：

```text
streamlit==1.28.1
imagededup==0.3.3.post2
Pillow>=10.0.0
numpy>=1.24.0
pytest>=7.0.0
opencv-python-headless>=4.8
```

`imagededup` 会引入 `torch`、`torchvision`、`scikit-learn`、`matplotlib` 等间接依赖，安装体积相对较大。如果只需要基础 PHash 能力，`image_search.py` 内部也提供了本地 DCT PHash 回退实现。

## 运行

```powershell
python -m streamlit run app.py
```

默认图片集目录：

```text
D:\image_demo1\data\images
```

默认索引文件：

```text
D:\image_demo1\data\index.json
```

打开页面后，先点击侧边栏里的“构建 / 刷新索引”，再上传查询图片进行检索。

## 架构分层

### `app.py`

`app.py` 是 Streamlit 表现层，负责：

- 设置页面布局和中文 UI；
- 提供图片目录、索引路径、PHash 阈值等配置入口；
- 上传查询图片并调用检索函数；
- 展示索引概览、匹配结果、缩略图和匹配指标；
- 通过内联 CSS 调整页面视觉样式。

它不直接实现图像算法，主要调用 `image_search.py` 暴露的 `build_index()`、`load_index()`、`save_index()` 和 `search_image()`。

### `image_search.py`

`image_search.py` 是项目核心逻辑层，负责：

- 遍历本地图片目录并构建索引；
- 计算文件 SHA256、PHash、颜色指纹；
- 保存和加载 JSON 索引；
- 对查询图片执行多阶段匹配；
- 返回带有匹配类型、距离、相似度、文件大小等字段的结构化结果。

支持的图片扩展名：

```text
.jpg, .jpeg, .png, .webp, .bmp
```

当前不索引 `.avif`、`.htm` 等文件。

## 检索链路

`search_image()` 使用多阶段召回策略，按成本和确定性从高到低依次执行：

1. **SHA256 精确匹配**

   对查询图片和索引图片计算 SHA256。只要文件内容完全一致，就直接返回结果。这一步适合识别完全相同的文件，速度快、误报低。

2. **严格 PHash 匹配**

   如果没有精确命中，计算查询图的感知哈希，并与索引中的 PHash 做汉明距离比较。默认严格阈值为 `0`，用于识别视觉内容几乎完全一致的图片。

3. **兜底 PHash 匹配**

   当严格匹配没有结果时，使用更宽松的 PHash 阈值，默认是 `2`。这一步用于容忍轻微压缩、格式转换或小幅画质变化。

4. **颜色指纹过滤**

   PHash 匹配过程中会额外比较 8x8 RGB 颜色指纹，过滤形状相近但颜色明显不同的图片，降低误报。

5. **ORB 局部特征匹配**

   如果 PHash 仍没有结果，会使用 OpenCV ORB 提取局部特征，再通过 BFMatcher 和 RANSAC 验证几何一致性。这一步适合识别裁剪图、局部截图或包含同一主体但整体尺寸变化较大的图片。

6. **缩略像素兜底匹配**

   最后会把图片缩放到较小尺寸，比较像素均值差、RGB 均值距离和灰度结构相关性。它用于处理低分辨率、强压缩但整体构图仍然一致的图片。

## 索引文件

索引默认保存到 `data/index.json`，每条图片记录包含：

- `path`：图片绝对路径；
- `relative_path`：相对图片目录的路径；
- `filename`：文件名；
- `sha256`：文件内容哈希；
- `phash`：感知哈希；
- `color_fingerprint`：颜色指纹；
- `modified_at`：文件修改时间；
- `size_bytes`：文件大小。

索引使用绝对路径，因此如果移动项目目录或图片目录，需要重新构建索引。

## 测试

运行测试：

```powershell
python -m pytest -q
```

测试覆盖：

- SHA256 精确匹配；
- 重编码图片的 PHash 召回；
- 裁剪图的 ORB 局部特征匹配；
- 低分辨率压缩图片的缩略像素兜底匹配；
- 无匹配时返回空结果；
- 展示层中文标签、文件大小格式和结果指标格式化。

## 技术特点

- **本地优先**：图片、索引、检索全部在本机完成。
- **无数据库依赖**：索引使用 JSON，便于查看和调试。
- **多阶段匹配**：从确定性哈希到视觉哈希，再到局部特征和像素兜底。
- **可解释结果**：结果会显示匹配方式、相似度、PHash 距离、颜色距离、ORB 内点等指标。
- **轻量 UI**：使用 Streamlit 快速搭建交互页面，不需要额外前端工程。

## 当前边界

- 检索是线性扫描，图片规模较大时性能会下降。
- 当前不是 CLIP/向量检索系统，无法理解“语义相似”，主要识别近重复、裁剪、压缩和视觉高度相似图片。
- JSON 索引不适合多人并发写入或大型数据集。
- `data/index.json` 记录绝对路径，跨机器迁移后需要刷新索引。
- `imagededup` 依赖较重，部署到新环境时安装耗时可能较长。

## 后续可扩展方向

- 使用 SQLite 保存索引，提升结构化查询和迁移能力。
- 缓存 ORB 特征，减少搜索时重复计算。
- 增加批量查询和批量去重能力。
- 引入 CLIP embedding 和向量库，支持语义级图片检索。
- 将检索逻辑封装为 API，前端与算法服务解耦。
