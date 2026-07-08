from app import (
    format_file_size,
    index_table_rows,
    match_type_label,
    result_detail_items,
)


def test_format_file_size_uses_readable_units() -> None:
    assert format_file_size(0) == "0 B"
    assert format_file_size(512) == "512 B"
    assert format_file_size(1536) == "1.5 KB"
    assert format_file_size(5 * 1024 * 1024) == "5.0 MB"


def test_match_type_label_uses_chinese_user_facing_labels() -> None:
    assert match_type_label("sha256") == "完全一致"
    assert match_type_label("phash") == "视觉相似"
    assert match_type_label("custom") == "custom"


def test_index_table_rows_format_sizes_for_display() -> None:
    rows = index_table_rows(
        {
            "items": [
                {
                    "filename": "product-a.jpg",
                    "relative_path": "catalog/product-a.jpg",
                    "size_bytes": 1536,
                },
                {
                    "filename": "product-b.png",
                    "relative_path": "product-b.png",
                    "size_bytes": 0,
                },
            ]
        }
    )

    assert rows == [
        {
            "文件名": "product-a.jpg",
            "相对路径": "catalog/product-a.jpg",
            "文件大小": "1.5 KB",
        },
        {
            "文件名": "product-b.png",
            "相对路径": "product-b.png",
            "文件大小": "0 B",
        },
    ]


def test_result_detail_items_build_clean_result_copy() -> None:
    details = dict(
        result_detail_items(
            {
                "match_type": "phash",
                "similarity": 98.44,
                "distance": 1,
                "color_distance": 0.125,
                "size_bytes": 2048,
            }
        )
    )

    assert details == {
        "匹配方式": "视觉相似",
        "相似度": "98.44%",
        "PHash 距离": "1",
        "颜色距离": "0.125",
        "文件大小": "2.0 KB",
    }
