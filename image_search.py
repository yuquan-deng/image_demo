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
LOCAL_FEATURE_NFEATURES = 2000
LOCAL_FEATURE_RATIO_TEST = 0.75
LOCAL_FEATURE_RANSAC_THRESHOLD = 5.0
LOCAL_FEATURE_MIN_INLIERS = 80
LOCAL_FEATURE_MIN_GOOD_MATCHES = 90
LOCAL_FEATURE_MIN_INLIER_RATIO = 0.55
RESIZED_PIXEL_MAX_DIMENSION = 320
RESIZED_PIXEL_MAX_MEAN_ABS_DIFF = 45.0
RESIZED_PIXEL_MAX_MEAN_RGB_DISTANCE = 6.0
RESIZED_PIXEL_MIN_GRAY_CORRELATION = 0.45
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

    if fallback_threshold >= strict_threshold:
        fallback_matches = phash_matches(
            items,
            query_phash=query_phash,
            query_color=query_color,
            threshold=fallback_threshold,
        )
        if fallback_matches:
            return fallback_matches

    local_matches = local_feature_matches(query_path, items)
    if local_matches:
        return local_matches

    return resized_pixel_matches(query_path, items)


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


def local_feature_matches(
    query_image_path: str | Path,
    items: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    try:
        import cv2
    except ImportError:
        return []

    query_image = read_feature_image(query_image_path, cv2)
    if query_image is None:
        return []

    detector = cv2.ORB_create(nfeatures=LOCAL_FEATURE_NFEATURES)
    query_keypoints, query_descriptors = detector.detectAndCompute(query_image, None)
    if query_descriptors is None or len(query_keypoints) < 4:
        return []

    matcher = cv2.BFMatcher(cv2.NORM_HAMMING)
    matches = []
    for item in items:
        image_path = Path(str(item.get("path", "")))
        if not image_path.exists():
            continue

        try:
            target_image = read_feature_image(image_path, cv2)
            if target_image is None:
                continue
            score = local_feature_score(
                cv2=cv2,
                detector=detector,
                matcher=matcher,
                query_keypoints=query_keypoints,
                query_descriptors=query_descriptors,
                target_image=target_image,
            )
        except Exception:
            continue

        if is_local_feature_match(score):
            matches.append(result_for_local_feature(item, score))

    return sorted(
        matches,
        key=lambda result: (
            -int(result["feature_inliers"]),
            -float(result["feature_inlier_ratio"]),
            -int(result["feature_good_matches"]),
            result["filename"],
        ),
    )


def resized_pixel_matches(
    query_image_path: str | Path,
    items: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    try:
        query_image = comparison_image(query_image_path)
    except (OSError, UnidentifiedImageError, ValueError):
        return []

    query_pixels = np.asarray(query_image, dtype=np.float32)
    query_gray = np.asarray(query_image.convert("L"), dtype=np.float32)
    matches = []
    for item in items:
        image_path = Path(str(item.get("path", "")))
        if not image_path.exists():
            continue

        try:
            target_image = Image.open(image_path).convert("RGB").resize(
                query_image.size,
                Image.LANCZOS,
            )
        except (OSError, UnidentifiedImageError, ValueError):
            continue

        target_pixels = np.asarray(target_image, dtype=np.float32)
        score = resized_pixel_score(query_pixels, query_gray, target_pixels)
        if is_resized_pixel_match(score):
            matches.append(result_for_resized_pixel(item, score))

    return sorted(
        matches,
        key=lambda result: (
            float(result["thumbnail_mean_abs_diff"]),
            -float(result["thumbnail_gray_correlation"]),
            float(result["thumbnail_mean_rgb_distance"]),
            result["filename"],
        ),
    )


def comparison_image(path: str | Path) -> Image.Image:
    image = Image.open(path).convert("RGB")
    width, height = image.size
    max_dimension = max(width, height)
    if max_dimension <= RESIZED_PIXEL_MAX_DIMENSION:
        return image

    scale = RESIZED_PIXEL_MAX_DIMENSION / max_dimension
    size = (max(1, round(width * scale)), max(1, round(height * scale)))
    return image.resize(size, Image.LANCZOS)


def resized_pixel_score(
    query_pixels: np.ndarray,
    query_gray: np.ndarray,
    target_pixels: np.ndarray,
) -> dict[str, float]:
    diff = np.abs(query_pixels - target_pixels)
    query_mean_rgb = query_pixels.reshape(-1, 3).mean(axis=0)
    target_mean_rgb = target_pixels.reshape(-1, 3).mean(axis=0)
    target_gray = np.asarray(
        Image.fromarray(np.clip(target_pixels, 0, 255).astype(np.uint8)).convert("L"),
        dtype=np.float32,
    )

    return {
        "mean_abs_diff": float(diff.mean()),
        "mean_rgb_distance": float(np.abs(query_mean_rgb - target_mean_rgb).mean()),
        "gray_correlation": gray_correlation(query_gray, target_gray),
    }


def gray_correlation(left: np.ndarray, right: np.ndarray) -> float:
    left_centered = left - left.mean()
    right_centered = right - right.mean()
    denominator = float(np.linalg.norm(left_centered) * np.linalg.norm(right_centered))
    if denominator == 0:
        return 0.0
    return float((left_centered * right_centered).sum() / denominator)


def is_resized_pixel_match(score: dict[str, float]) -> bool:
    return (
        score["mean_abs_diff"] <= RESIZED_PIXEL_MAX_MEAN_ABS_DIFF
        and score["mean_rgb_distance"] <= RESIZED_PIXEL_MAX_MEAN_RGB_DISTANCE
        and score["gray_correlation"] >= RESIZED_PIXEL_MIN_GRAY_CORRELATION
    )


def result_for_resized_pixel(item: dict[str, Any], score: dict[str, float]) -> dict[str, Any]:
    mean_abs_diff = score["mean_abs_diff"]
    return {
        "filename": item["filename"],
        "path": item["path"],
        "relative_path": item["relative_path"],
        "match_type": "resized_pixel",
        "distance": None,
        "color_distance": None,
        "similarity": round(max(0.0, (1 - mean_abs_diff / 255) * 100), 2),
        "thumbnail_mean_abs_diff": round(mean_abs_diff, 3),
        "thumbnail_mean_rgb_distance": round(score["mean_rgb_distance"], 3),
        "thumbnail_gray_correlation": round(score["gray_correlation"], 3),
        "modified_at": item.get("modified_at", ""),
        "size_bytes": item.get("size_bytes", 0),
    }

def read_feature_image(path: str | Path, cv2: Any) -> np.ndarray | None:
    try:
        data = np.fromfile(str(Path(path)), dtype=np.uint8)
    except OSError:
        return None
    if data.size == 0:
        return None
    return cv2.imdecode(data, cv2.IMREAD_GRAYSCALE)


def local_feature_score(
    cv2: Any,
    detector: Any,
    matcher: Any,
    query_keypoints: list[Any],
    query_descriptors: np.ndarray,
    target_image: np.ndarray,
) -> dict[str, float | int]:
    target_keypoints, target_descriptors = detector.detectAndCompute(target_image, None)
    if target_descriptors is None or len(target_keypoints) < 4:
        return {"good_matches": 0, "inliers": 0, "inlier_ratio": 0.0}

    knn_matches = matcher.knnMatch(query_descriptors, target_descriptors, k=2)
    good_matches = []
    for pair in knn_matches:
        if len(pair) != 2:
            continue
        match, neighbor = pair
        if match.distance < LOCAL_FEATURE_RATIO_TEST * neighbor.distance:
            good_matches.append(match)

    inliers = 0
    if len(good_matches) >= 4:
        query_points = np.float32(
            [query_keypoints[match.queryIdx].pt for match in good_matches]
        ).reshape(-1, 1, 2)
        target_points = np.float32(
            [target_keypoints[match.trainIdx].pt for match in good_matches]
        ).reshape(-1, 1, 2)
        _, mask = cv2.findHomography(
            query_points,
            target_points,
            cv2.RANSAC,
            LOCAL_FEATURE_RANSAC_THRESHOLD,
        )
        if mask is not None:
            inliers = int(mask.ravel().sum())

    return {
        "good_matches": len(good_matches),
        "inliers": inliers,
        "inlier_ratio": inliers / max(len(good_matches), 1),
    }


def is_local_feature_match(score: dict[str, float | int]) -> bool:
    return (
        int(score["inliers"]) >= LOCAL_FEATURE_MIN_INLIERS
        and int(score["good_matches"]) >= LOCAL_FEATURE_MIN_GOOD_MATCHES
        and float(score["inlier_ratio"]) >= LOCAL_FEATURE_MIN_INLIER_RATIO
    )


def result_for_local_feature(
    item: dict[str, Any],
    score: dict[str, float | int],
) -> dict[str, Any]:
    inlier_ratio = float(score["inlier_ratio"])
    return {
        "filename": item["filename"],
        "path": item["path"],
        "relative_path": item["relative_path"],
        "match_type": "local_feature",
        "distance": None,
        "color_distance": None,
        "similarity": round(inlier_ratio * 100, 2),
        "feature_inliers": int(score["inliers"]),
        "feature_good_matches": int(score["good_matches"]),
        "feature_inlier_ratio": round(inlier_ratio, 3),
        "modified_at": item.get("modified_at", ""),
        "size_bytes": item.get("size_bytes", 0),
    }


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

