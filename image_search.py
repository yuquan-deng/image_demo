from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, UnidentifiedImageError


IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
PHASH_SIZE = 8
PHASH_HIGHFREQ_FACTOR = 4
COLOR_SIZE = 8
DEFAULT_COLOR_THRESHOLD = 0.5
_IMAGEDUP_PHASH_ENCODER: Any | None = None
_IMAGEDUP_IMPORT_FAILED = False


def build_index(image_dir: str | Path) -> dict[str, Any]:
    root = Path(image_dir).expanduser().resolve()
    if not root.exists():
        raise FileNotFoundError(f"Image directory does not exist: {root}")
    if not root.is_dir():
        raise NotADirectoryError(f"Image directory is not a folder: {root}")

    items = []
    for image_path in iter_image_files(root):
        try:
            phash = compute_phash(image_path)
            color_fingerprint = compute_color_fingerprint(image_path)
        except (OSError, UnidentifiedImageError, ValueError):
            continue

        stat = image_path.stat()
        items.append(
            {
                "path": str(image_path.resolve()),
                "relative_path": str(image_path.relative_to(root)),
                "filename": image_path.name,
                "sha256": compute_sha256(image_path),
                "phash": phash,
                "color_fingerprint": color_fingerprint,
                "modified_at": datetime.fromtimestamp(
                    stat.st_mtime, timezone.utc
                ).isoformat(),
                "size_bytes": stat.st_size,
            }
        )

    return {
        "image_dir": str(root),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "hash_algorithm": phash_backend_name(),
        "items": items,
    }


def save_index(index: dict[str, Any], index_path: str | Path) -> None:
    destination = Path(index_path).expanduser().resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(index, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def load_index(index_path: str | Path) -> dict[str, Any]:
    source = Path(index_path).expanduser().resolve()
    if not source.exists():
        return empty_index()
    return json.loads(source.read_text(encoding="utf-8"))


def search_image(
    query_image_path: str | Path,
    index: dict[str, Any],
    strict_threshold: int = 0,
    fallback_threshold: int = 2,
) -> list[dict[str, Any]]:
    query_path = Path(query_image_path).expanduser().resolve()
    items = index.get("items", [])
    if not query_path.exists() or not items:
        return []

    query_sha = compute_sha256(query_path)
    exact_matches = [
        result_for_item(item, match_type="sha256", distance=0, color_distance=0.0)
        for item in items
        if item.get("sha256") == query_sha
    ]
    if exact_matches:
        return sorted(exact_matches, key=lambda result: result["relative_path"])

    query_phash = compute_phash(query_path)
    query_color = compute_color_fingerprint(query_path)

    strict_matches = phash_matches(
        items,
        query_phash=query_phash,
        query_color=query_color,
        threshold=strict_threshold,
    )
    if strict_matches:
        return strict_matches

    if fallback_threshold < strict_threshold:
        return []

    return phash_matches(
        items,
        query_phash=query_phash,
        query_color=query_color,
        threshold=fallback_threshold,
    )


def iter_image_files(image_dir: Path) -> list[Path]:
    return sorted(
        path
        for path in image_dir.rglob("*")
        if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS
    )


def compute_sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def compute_phash(path: str | Path) -> str:
    imagededup_hash = compute_imagededup_phash(path)
    if imagededup_hash is not None:
        return imagededup_hash
    return compute_local_phash(path)


def compute_imagededup_phash(path: str | Path) -> str | None:
    global _IMAGEDUP_IMPORT_FAILED, _IMAGEDUP_PHASH_ENCODER
    if _IMAGEDUP_IMPORT_FAILED:
        return None

    try:
        if _IMAGEDUP_PHASH_ENCODER is None:
            from imagededup.methods import PHash

            _IMAGEDUP_PHASH_ENCODER = PHash()
    except ImportError:
        _IMAGEDUP_IMPORT_FAILED = True
        return None

    try:
        encoded = _IMAGEDUP_PHASH_ENCODER.encode_image(image_file=str(Path(path).resolve()))
    except Exception:
        return None
    if encoded is None:
        return None
    return normalize_hash(encoded)


def compute_local_phash(path: str | Path) -> str:
    hash_size = PHASH_SIZE
    image_size = hash_size * PHASH_HIGHFREQ_FACTOR
    image = Image.open(path).convert("L").resize((image_size, image_size), Image.LANCZOS)
    pixels = np.asarray(image, dtype=np.float64)
    dct = dct_2d(pixels)
    low_freq = dct[:hash_size, :hash_size]
    comparable = low_freq.flatten()[1:]
    median = np.median(comparable)
    bits = low_freq.flatten() > median
    value = 0
    for bit in bits:
        value = (value << 1) | int(bit)
    return f"{value:0{hash_size * hash_size // 4}x}"


def compute_color_fingerprint(path: str | Path) -> str:
    image = Image.open(path).convert("RGB").resize((COLOR_SIZE, COLOR_SIZE), Image.LANCZOS)
    pixels = np.asarray(image, dtype=np.uint8) // 16
    return "".join(f"{channel:x}" for channel in pixels.flatten())


def phash_matches(
    items: list[dict[str, Any]],
    query_phash: str,
    query_color: str,
    threshold: int,
) -> list[dict[str, Any]]:
    matches = []
    for item in items:
        item_phash = item.get("phash")
        item_color = item.get("color_fingerprint")
        if not item_phash or not item_color:
            continue

        distance = hamming_distance(query_phash, item_phash)
        color_distance = color_fingerprint_distance(query_color, item_color)
        if distance <= threshold and color_distance <= DEFAULT_COLOR_THRESHOLD:
            matches.append(
                result_for_item(
                    item,
                    match_type="phash",
                    distance=distance,
                    color_distance=color_distance,
                )
            )

    return sorted(matches, key=lambda result: (result["distance"], result["filename"]))


def result_for_item(
    item: dict[str, Any],
    match_type: str,
    distance: int,
    color_distance: float,
) -> dict[str, Any]:
    return {
        "filename": item["filename"],
        "path": item["path"],
        "relative_path": item["relative_path"],
        "match_type": match_type,
        "distance": distance,
        "color_distance": round(color_distance, 3),
        "similarity": round(((64 - distance) / 64) * 100, 2),
        "modified_at": item.get("modified_at", ""),
        "size_bytes": item.get("size_bytes", 0),
    }


def hamming_distance(left: str, right: str) -> int:
    left_hash = normalize_hash(left)
    right_hash = normalize_hash(right)
    width = max(len(left_hash), len(right_hash))
    left_value = int(left_hash.zfill(width), 16)
    right_value = int(right_hash.zfill(width), 16)
    return (left_value ^ right_value).bit_count()


def color_fingerprint_distance(left: str, right: str) -> float:
    left_values = [int(char, 16) for char in left]
    right_values = [int(char, 16) for char in right]
    count = min(len(left_values), len(right_values))
    if count == 0:
        return 0.0
    total = sum(abs(left_values[index] - right_values[index]) for index in range(count))
    return total / count


def normalize_hash(value: Any) -> str:
    text = str(value).strip().lower()
    if set(text) <= {"0", "1"}:
        return f"{int(text, 2):x}"
    return text


def dct_2d(values: np.ndarray) -> np.ndarray:
    size = values.shape[0]
    matrix = dct_matrix(size)
    return matrix @ values @ matrix.T


def dct_matrix(size: int) -> np.ndarray:
    columns = np.arange(size)
    matrix = np.zeros((size, size), dtype=np.float64)
    matrix[0, :] = np.sqrt(1 / size)
    for row in range(1, size):
        matrix[row, :] = np.sqrt(2 / size) * np.cos(
            ((2 * columns + 1) * row * np.pi) / (2 * size)
        )
    return matrix


def phash_backend_name() -> str:
    try:
        from imagededup.methods import PHash  # noqa: F401
    except ImportError:
        return "local-phash"
    return "imagededup-phash"


def empty_index() -> dict[str, Any]:
    return {
        "image_dir": "",
        "generated_at": "",
        "hash_algorithm": phash_backend_name(),
        "items": [],
    }
