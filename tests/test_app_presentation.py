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


def test_match_type_label_names_local_feature_matches() -> None:
    assert match_type_label("local_feature") == "局部特征匹配"


def test_result_detail_items_show_local_feature_metrics() -> None:
    details = dict(
        result_detail_items(
            {
                "match_type": "local_feature",
                "similarity": 81.4,
                "feature_inliers": 127,
                "feature_good_matches": 156,
                "feature_inlier_ratio": 0.814,
                "size_bytes": 2048,
            }
        )
    )

    assert details == {
        "匹配方式": "局部特征匹配",
        "局部匹配置信度": "81.4%",
        "ORB 几何内点": "127",
        "ORB 有效匹配点": "156",
        "ORB 内点比例": "0.814",
        "文件大小": "2.0 KB",
    }


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




def test_match_type_label_names_resized_pixel_matches() -> None:
    assert match_type_label("resized_pixel") == "\u7f29\u7565\u56fe\u515c\u5e95\u5339\u914d"


def test_result_detail_items_show_resized_pixel_metrics() -> None:
    details = dict(
        result_detail_items(
            {
                "match_type": "resized_pixel",
                "similarity": 86.79,
                "thumbnail_mean_abs_diff": 33.673,
                "thumbnail_mean_rgb_distance": 3.821,
                "thumbnail_gray_correlation": 0.512,
                "size_bytes": 253799,
            }
        )
    )

    assert details == {
        "\u5339\u914d\u65b9\u5f0f": "\u7f29\u7565\u56fe\u515c\u5e95\u5339\u914d",
        "\u7f29\u7565\u76f8\u4f3c\u5ea6": "86.79%",
        "\u7f29\u7565\u50cf\u7d20\u5747\u5dee": "33.673",
        "\u7f29\u7565\u989c\u8272\u5747\u5dee": "3.821",
        "\u7070\u5ea6\u7ed3\u6784\u76f8\u5173": "0.512",
        "\u6587\u4ef6\u5927\u5c0f": "247.9 KB",
    }
