from __future__ import annotations

import base64
import html
import mimetypes
import tempfile
from pathlib import Path
from typing import Any

import streamlit as st

from image_search import build_index, load_index, save_index, search_image


ROOT = Path(__file__).parent.resolve()
DEFAULT_IMAGE_DIR = ROOT / "data" / "images"
DEFAULT_INDEX_PATH = ROOT / "data" / "index.json"


def main() -> None:
    st.set_page_config(
        page_title="本地图片检索 Demo",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    inject_chinese_style()
    DEFAULT_IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    DEFAULT_INDEX_PATH.parent.mkdir(parents=True, exist_ok=True)

    render_header()

    image_dir_text, index_path_text, strict_threshold, fallback_threshold = render_sidebar()
    index = st.session_state.get("index") or load_index(index_path_text)
    item_count = len(index.get("items", []))

    left, right = st.columns([1.05, 1.2], gap="large")
    with left:
        render_index_overview(index, item_count)

    with right:
        render_search_panel(index, item_count, strict_threshold, fallback_threshold)


def render_header() -> None:
    st.markdown(
        """
        <div class="hero-shell">
            <div>
                <p class="eyebrow">LOCAL IMAGE SEARCH</p>
                <h1>本地图片检索 Demo</h1>
                <p class="hero-copy">
                    上传一张查询图片，从本地图片集中快速找出视觉相同或高度相似的图片。
                </p>
            </div>
            <div class="hero-steps" aria-label="检索流程">
                <span>准备图片集</span>
                <span>构建索引</span>
                <span>上传检索</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_sidebar() -> tuple[str, str, int, int]:
    with st.sidebar:
        st.markdown(
            """
            <div class="sidebar-heading">
                <p>配置中心</p>
                <strong>图片集与匹配参数</strong>
            </div>
            """,
            unsafe_allow_html=True,
        )
        image_dir_text = st.text_input("本地图片集目录", value=str(DEFAULT_IMAGE_DIR))
        index_path_text = st.text_input("索引文件", value=str(DEFAULT_INDEX_PATH))

        st.divider()
        st.markdown("#### 匹配阈值")
        strict_threshold = st.slider(
            "严格 PHash 阈值",
            0,
            8,
            0,
            help="数值越低，匹配越严格。",
        )
        fallback_threshold = st.slider(
            "兜底 PHash 阈值",
            0,
            8,
            2,
            help="严格匹配无结果时使用。",
        )

        st.divider()
        if st.button("构建 / 刷新索引", type="primary", use_container_width=True):
            try:
                index = build_index(image_dir_text)
                save_index(index, index_path_text)
                st.session_state["index"] = index
                st.success(f"已索引 {len(index['items'])} 张图片")
            except Exception as exc:
                st.error(f"索引构建失败：{exc}")

    return image_dir_text, index_path_text, strict_threshold, fallback_threshold


def render_index_overview(index: dict[str, Any], item_count: int) -> None:
    st.markdown(
        """
        <div class="section-heading">
            <p>INDEX</p>
            <h2>当前索引</h2>
        </div>
        """,
        unsafe_allow_html=True,
    )

    metric_cols = st.columns(3)
    metric_cols[0].metric("图片数量", item_count)
    metric_cols[1].metric("索引状态", "已就绪" if item_count else "未构建")
    metric_cols[2].metric("哈希方式", index.get("hash_algorithm") or "-")

    if index.get("generated_at"):
        st.caption(f"生成时间：{index['generated_at']}")

    if item_count:
        st.dataframe(
            index_table_rows(index),
            hide_index=True,
            use_container_width=True,
        )
    else:
        st.info("请把测试图片放进图片集目录，然后点击“构建 / 刷新索引”。")


def render_search_panel(
    index: dict[str, Any],
    item_count: int,
    strict_threshold: int,
    fallback_threshold: int,
) -> None:
    st.markdown(
        """
        <div class="section-heading">
            <p>SEARCH</p>
            <h2>单图检索</h2>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.caption("支持 JPG、JPEG、PNG、WEBP、BMP。拖入图片或点击按钮选择文件。")

    uploaded = st.file_uploader(
        "上传查询图片",
        type=["jpg", "jpeg", "png", "webp", "bmp"],
        accept_multiple_files=False,
    )

    if uploaded is not None:
        st.image(uploaded, caption="查询图片", use_column_width=True)

    if st.button("开始检索", type="primary", use_container_width=True):
        if uploaded is None:
            st.warning("请先上传一张查询图片。")
        elif not item_count:
            st.warning("请先构建图片集索引。")
        else:
            with tempfile.NamedTemporaryFile(
                suffix=Path(uploaded.name).suffix,
                delete=False,
            ) as temp_file:
                temp_file.write(uploaded.getbuffer())
                query_path = Path(temp_file.name)

            try:
                results = search_image(
                    query_path,
                    index,
                    strict_threshold=strict_threshold,
                    fallback_threshold=fallback_threshold,
                )
            except Exception as exc:
                st.error(f"检索失败：{exc}")
                results = []
            finally:
                query_path.unlink(missing_ok=True)

            render_results(results)


def inject_chinese_style() -> None:
    st.markdown(
        """
        <style>
        :root {
            --page-bg: #f5f7fb;
            --surface: #ffffff;
            --surface-soft: #f8fafc;
            --line: #dbe3ef;
            --text: #182230;
            --muted: #667085;
            --accent: #0f766e;
            --accent-soft: #e6f4f1;
        }

        #MainMenu, footer, [data-testid="stToolbar"] {
            visibility: hidden;
        }

        [data-testid="stAppViewContainer"] {
            background: var(--page-bg);
        }

        [data-testid="block-container"] {
            max-width: 1180px;
            padding: 2rem 2.25rem 3rem;
        }

        section[data-testid="stSidebar"] {
            background: var(--surface);
            border-right: 1px solid var(--line);
        }

        section[data-testid="stSidebar"] [data-testid="stVerticalBlock"] {
            gap: 1rem;
        }

        .hero-shell {
            display: flex;
            align-items: flex-end;
            justify-content: space-between;
            gap: 1.5rem;
            padding: 1.35rem 1.45rem;
            margin-bottom: 1.4rem;
            border: 1px solid var(--line);
            border-radius: 8px;
            background: var(--surface);
            box-shadow: 0 14px 36px rgba(16, 24, 40, 0.06);
        }

        .hero-shell h1 {
            margin: 0.1rem 0 0.35rem;
            color: var(--text);
            font-size: 2rem;
            line-height: 1.15;
            letter-spacing: 0;
        }

        .eyebrow, .section-heading p, .sidebar-heading p {
            margin: 0;
            color: var(--accent);
            font-size: 0.74rem;
            font-weight: 700;
            letter-spacing: 0.08em;
            text-transform: uppercase;
        }

        .hero-copy {
            max-width: 42rem;
            margin: 0;
            color: var(--muted);
            font-size: 0.98rem;
            line-height: 1.7;
        }

        .hero-steps {
            display: flex;
            flex-wrap: wrap;
            justify-content: flex-end;
            gap: 0.5rem;
            min-width: 18rem;
        }

        .hero-steps span {
            display: inline-flex;
            align-items: center;
            min-height: 2rem;
            padding: 0.35rem 0.75rem;
            border: 1px solid var(--line);
            border-radius: 999px;
            background: var(--surface-soft);
            color: #344054;
            font-size: 0.84rem;
            font-weight: 600;
            white-space: nowrap;
        }

        .sidebar-heading {
            padding: 0.2rem 0 0.35rem;
        }

        .sidebar-heading strong {
            display: block;
            margin-top: 0.15rem;
            color: var(--text);
            font-size: 1rem;
            line-height: 1.4;
        }

        .section-heading {
            margin-bottom: 0.75rem;
        }

        .section-heading h2 {
            margin: 0.1rem 0 0;
            color: var(--text);
            font-size: 1.32rem;
            line-height: 1.3;
            letter-spacing: 0;
        }

        [data-testid="stMetric"] {
            padding: 0.9rem 1rem;
            border: 1px solid var(--line);
            border-radius: 8px;
            background: var(--surface);
        }

        [data-testid="stMetricLabel"] {
            color: var(--muted);
        }

        [data-testid="stMetricValue"] {
            color: var(--text);
            font-size: 1.35rem;
        }

        .stTextInput input,
        .stSlider,
        [data-testid="stFileUploader"] {
            color: var(--text);
        }

        .stTextInput input {
            border-radius: 8px;
        }

        .stButton > button,
        [data-testid="baseButton-primary"],
        [data-testid="baseButton-secondary"] {
            min-height: 2.75rem;
            border-radius: 8px;
            font-weight: 700;
        }

        [data-testid="baseButton-primary"] {
            border: 1px solid #0f766e;
            background: #0f766e;
        }

        [data-testid="stFileUploadDropzone"] {
            min-height: 9rem;
            border: 1px dashed #9fb2c8;
            border-radius: 8px;
            background: #f8fbff;
        }

        [data-testid="stFileUploadDropzone"]:hover {
            border-color: var(--accent);
            background: var(--accent-soft);
        }

        [data-testid="stFileDropzoneInstructions"] div > span,
        [data-testid="stFileDropzoneInstructions"] small {
            font-size: 0 !important;
        }

        [data-testid="stFileDropzoneInstructions"] div > span::before {
            content: "拖拽图片到这里";
            color: var(--text);
            font-size: 1rem;
            font-weight: 700;
        }

        [data-testid="stFileDropzoneInstructions"] small::before {
            content: "单个文件最大 200MB，支持 JPG、JPEG、PNG、WEBP、BMP";
            color: var(--muted);
            font-size: 0.82rem;
        }

        [data-testid="stFileUploadDropzone"] button {
            font-size: 0 !important;
        }

        [data-testid="stFileUploadDropzone"] button::before {
            content: "浏览文件";
            font-size: 0.9rem;
        }

        div[data-testid="stAlert"] {
            border-radius: 8px;
            border: 1px solid var(--line);
        }

        [data-testid="stDataFrame"] {
            overflow: hidden;
            border: 1px solid var(--line);
            border-radius: 8px;
        }

        .result-card {
            display: grid;
            grid-template-columns: minmax(150px, 0.9fr) minmax(0, 1.45fr);
            gap: 1rem;
            align-items: stretch;
            padding: 0.9rem;
            margin: 0.75rem 0;
            border: 1px solid var(--line);
            border-radius: 8px;
            background: var(--surface);
            box-shadow: 0 10px 24px rgba(16, 24, 40, 0.05);
        }

        .result-thumb {
            min-height: 150px;
            border: 1px solid var(--line);
            border-radius: 8px;
            background: var(--surface-soft);
            overflow: hidden;
        }

        .result-thumb img {
            width: 100%;
            height: 100%;
            min-height: 150px;
            object-fit: contain;
            display: block;
        }

        .missing-image {
            display: flex;
            align-items: center;
            justify-content: center;
            min-height: 150px;
            color: var(--muted);
            font-weight: 700;
        }

        .result-body h3 {
            margin: 0 0 0.2rem;
            color: var(--text);
            font-size: 1rem;
            line-height: 1.35;
            letter-spacing: 0;
            word-break: break-word;
        }

        .result-path {
            margin: 0 0 0.75rem;
            color: var(--muted);
            font-size: 0.8rem;
            line-height: 1.45;
            word-break: break-all;
        }

        .result-details {
            display: grid;
            grid-template-columns: repeat(2, minmax(0, 1fr));
            gap: 0.55rem;
        }

        .detail-item {
            padding: 0.58rem 0.65rem;
            border: 1px solid var(--line);
            border-radius: 8px;
            background: var(--surface-soft);
        }

        .detail-item span {
            display: block;
            color: var(--muted);
            font-size: 0.72rem;
            line-height: 1.25;
        }

        .detail-item strong {
            display: block;
            margin-top: 0.15rem;
            color: var(--text);
            font-size: 0.9rem;
            line-height: 1.35;
            word-break: break-word;
        }

        @media (max-width: 780px) {
            [data-testid="block-container"] {
                padding: 1.25rem 1rem 2.25rem;
            }

            .hero-shell {
                align-items: flex-start;
                flex-direction: column;
                padding: 1.1rem;
            }

            .hero-shell h1 {
                font-size: 1.6rem;
            }

            .hero-steps {
                justify-content: flex-start;
                min-width: 0;
            }

            .result-card,
            .result-details {
                grid-template-columns: 1fr;
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_results(results: list[dict]) -> None:
    st.markdown(
        """
        <div class="section-heading results-heading">
            <p>RESULTS</p>
            <h2>匹配结果</h2>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if not results:
        st.error("未找到匹配图片。")
        return

    st.success(f"找到 {len(results)} 张匹配图片")
    for result in results:
        st.markdown(result_card_html(result), unsafe_allow_html=True)


def result_card_html(result: dict[str, Any]) -> str:
    image_path = Path(str(result.get("path", "")))
    filename = html.escape(str(result.get("filename", "未知文件")))
    path_text = html.escape(str(result.get("path", "")))
    thumbnail = result_thumbnail_html(image_path)
    detail_html = "".join(
        f"""
        <div class="detail-item">
            <span>{html.escape(label)}</span>
            <strong>{html.escape(value)}</strong>
        </div>
        """
        for label, value in result_detail_items(result)
    )

    return f"""
    <div class="result-card">
        <div class="result-thumb">{thumbnail}</div>
        <div class="result-body">
            <h3>{filename}</h3>
            <p class="result-path">{path_text}</p>
            <div class="result-details">{detail_html}</div>
        </div>
    </div>
    """


def result_thumbnail_html(image_path: Path) -> str:
    if not image_path.exists():
        return '<div class="missing-image">图片文件已不存在</div>'

    mime_type = mimetypes.guess_type(image_path.name)[0] or "image/jpeg"
    encoded = base64.b64encode(image_path.read_bytes()).decode("ascii")
    safe_name = html.escape(image_path.name)
    return f'<img src="data:{mime_type};base64,{encoded}" alt="{safe_name}">'


def index_table_rows(index: dict[str, Any]) -> list[dict[str, str]]:
    return [
        {
            "文件名": str(item.get("filename", "")),
            "相对路径": str(item.get("relative_path", "")),
            "文件大小": format_file_size(item.get("size_bytes", 0)),
        }
        for item in index.get("items", [])
    ]


def result_detail_items(result: dict[str, Any]) -> list[tuple[str, str]]:
    return [
        ("匹配方式", match_type_label(str(result.get("match_type", "")))),
        ("相似度", f"{result.get('similarity', 0)}%"),
        ("PHash 距离", str(result.get("distance", "-"))),
        ("颜色距离", str(result.get("color_distance", "-"))),
        ("文件大小", format_file_size(result.get("size_bytes", 0))),
    ]


def match_type_label(match_type: str) -> str:
    labels = {
        "sha256": "完全一致",
        "phash": "视觉相似",
    }
    return labels.get(match_type, match_type)


def format_file_size(size_bytes: Any) -> str:
    size = max(int(size_bytes or 0), 0)
    if size < 1024:
        return f"{size} B"

    units = ["KB", "MB", "GB", "TB"]
    value = float(size)
    for unit in units:
        value /= 1024
        if value < 1024 or unit == units[-1]:
            return f"{value:.1f} {unit}"

    return f"{value:.1f} TB"


if __name__ == "__main__":
    main()
