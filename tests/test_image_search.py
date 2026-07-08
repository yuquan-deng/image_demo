from pathlib import Path

from PIL import Image, ImageDraw

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


def test_search_image_returns_empty_when_no_visual_match(tmp_path: Path) -> None:
    image_dir = tmp_path / "images"
    image_dir.mkdir()
    make_memory_image(image_dir / "known.png")

    query = tmp_path / "not-present.png"
    make_memory_image(query, accent="#7048e8")

    index = build_index(image_dir)
    results = search_image(query, index, strict_threshold=0, fallback_threshold=2)

    assert results == []
