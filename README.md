# 本地图片检索 Demo

这个 demo 用本地 Web 页面完成单图检索：把测试图片放入 `data/images/`，构建索引后上传一张查询图，系统返回本地图片集中视觉相同的图片。

## 安装依赖

```powershell
python -m pip install -r requirements.txt
```

## 运行

```powershell
python -m streamlit run app.py
```

默认图片集目录：

```text
D:\image_demo1\data\images
```

## 检索逻辑

- 先用 SHA256 判断文件内容完全相同的图片。
- 如果没有精确命中，再用 PHash 判断视觉相同图片。
- PHash 默认严格阈值为 `0`，兜底阈值为 `2`，可在页面侧边栏调整。
- 内部额外使用颜色指纹过滤明显不同的图片，降低形状相似图片的误报。
