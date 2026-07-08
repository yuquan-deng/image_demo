import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance

from image_search import build_index, search_image


def make_memory_image(path: Path, accent: str = "#2f9e44", fmt: str | None = None) -> None:
    image = Image.new("RGB", (240, 120), "#f4f6f8")
    draw = ImageDraw.Draw(image)
    draw.rectangle((24, 34, 216, 86), fill="#263238", outline="#111111", width=3)
    for x in range(44, 190, 32):
        draw.rectangle((x, 46, x + 16, 74), fill=accent)
    for x in range(38, 202, 18):
        draw.rectangle((x, 88, x + 8, 98), fill="#d9b44a")
    image.save(path, format=fmt)


def make_feature_rich_image(path: Path) -> None:
    rng = random.Random(42)
    image = Image.new("RGB", (640, 480), "#f3f5f7")
    draw = ImageDraw.Draw(image)
    for index in range(260):
        x = rng.randrange(8, 600)
        y = rng.randrange(8, 440)
        width = rng.randrange(8, 34)
        height = rng.randrange(8, 30)
        color = (
            rng.randrange(20, 230),
            rng.randrange(20, 230),
            rng.randrange(20, 230),
        )
        if index % 3 == 0:
            draw.ellipse((x, y, x + width, y + height), fill=color, outline="#101828")
        else:
            draw.rectangle((x, y, x + width, y + height), fill=color, outline="#101828")
        draw.line(
            (x - rng.randrange(5, 18), y + height + 4, x + width + rng.randrange(5, 18), y - 4),
            fill=(rng.randrange(20, 230), rng.randrange(20, 230), rng.randrange(20, 230)),
            width=2,
        )
    draw.text((215, 210), "RAM-LOCAL-FEATURE-SEARCH", fill="#101828")
    image.save(path)


def make_memory_rack_image(path: Path) -> None:
    image = Image.new("RGB", (1363, 410), "#171717")
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, 1362, 90), fill="#050607")
    x = 18
    for index in range(17):
        width = 66
        base = "#aa9d78" if index % 2 else "#b8ad86"
        draw.rectangle((x, 112, x + width, 355), fill=base, outline="#0f0f0f", width=4)
        for y in range(132, 330, 38):
            draw.rectangle((x + 7, y, x + width - 7, y + 16), fill="#d2c391")
            draw.rectangle((x + 19, y + 4, x + width - 18, y + 12), fill="#181818")
        draw.rectangle((x + 4, 345, x + width - 4, 366), fill="#6e6449")
        x += 78
    draw.rectangle((1285, 0, 1360, 72), fill="#f8f4ff")
    draw.rectangle((1320, 15, 1350, 52), fill="#7b4fe3")
    image.save(path, quality=95)


def make_compressed_rack_query(source: Path, query: Path) -> None:
    with Image.open(source) as image:
        resized = image.convert("RGB").resize((210, 83), Image.LANCZOS)
        enhanced = ImageEnhance.Contrast(resized).enhance(1.4)
        enhanced.save(query, format="JPEG", quality=55)

def test_search_image_finds_exact_file_by_sha256(tmp_path: Path) -> None:
    image_dir = tmp_path / "images"
    image_dir.mkdir()
    target = image_dir / "seller-a-memory.png"
    make_memory_image(target)
    make_memory_image(image_dir / "seller-b-memory.png", accent="#d9480f")

    index = build_index(image_dir)
    results = search_image(target, index)

    assert results
    assert results[0]["filename"] == "seller-a-memory.png"
    assert results[0]["match_type"] == "sha256"
    assert results[0]["distance"] == 0


def test_search_image_finds_visually_same_recompressed_image(tmp_path: Path) -> None:
    image_dir = tmp_path / "images"
    image_dir.mkdir()
    indexed = image_dir / "warehouse-source.png"
    query = tmp_path / "query-recompressed.jpg"
    make_memory_image(indexed)
    make_memory_image(query, fmt="JPEG")

    index = build_index(image_dir)
    results = search_image(query, index, strict_threshold=0, fallback_threshold=2)

    assert results
    assert results[0]["filename"] == "warehouse-source.png"
    assert results[0]["match_type"] in {"phash", "sha256"}
    assert results[0]["distance"] <= 2


def test_search_image_finds_full_image_from_cropped_query(tmp_path: Path) -> None:
    image_dir = tmp_path / "images"
    image_dir.mkdir()
    indexed = image_dir / "feature-rich-source.png"
    query = tmp_path / "cropped-query.png"
    make_feature_rich_image(indexed)

    with Image.open(indexed) as source:
        source.crop((90, 70, 530, 400)).save(query)

    index = build_index(image_dir)
    results = search_image(query, index, strict_threshold=0, fallback_threshold=2)

    assert results
    assert results[0]["filename"] == "feature-rich-source.png"
    assert results[0]["match_type"] == "local_feature"
    assert results[0]["feature_inliers"] >= 80
    assert results[0]["feature_good_matches"] >= 90
    assert results[0]["feature_inlier_ratio"] >= 0.55


def test_search_image_finds_low_resolution_compressed_same_image(tmp_path: Path) -> None:
    image_dir = tmp_path / "images"
    image_dir.mkdir()
    indexed = image_dir / "memory-rack.jpg"
    query = tmp_path / "compressed-query.jpg"
    make_memory_rack_image(indexed)
    make_compressed_rack_query(indexed, query)

    index = build_index(image_dir)
    results = search_image(query, index, strict_threshold=0, fallback_threshold=2)

    assert results
    assert results[0]["filename"] == "memory-rack.jpg"
    assert results[0]["match_type"] == "resized_pixel"
    assert results[0]["thumbnail_mean_abs_diff"] <= 45.0
    assert results[0]["thumbnail_mean_rgb_distance"] <= 6.0
    assert results[0]["thumbnail_gray_correlation"] >= 0.45

def test_search_image_returns_empty_when_no_visual_match(tmp_path: Path) -> None:
    image_dir = tmp_path / "images"
    image_dir.mkdir()
    make_memory_image(image_dir / "known.png")

    query = tmp_path / "not-present.png"
    make_memory_image(query, accent="#7048e8")

    index = build_index(image_dir)
    results = search_image(query, index, strict_threshold=0, fallback_threshold=2)

    assert results == []


