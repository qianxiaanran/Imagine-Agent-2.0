from __future__ import annotations

import io
import math
import os
import tempfile
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
from pdf2image import convert_from_bytes
from PIL import Image


_CV2 = None
_CV2_ERROR = None
_SEAL_PIPELINE = None
_SEAL_PIPELINE_ERROR = None


def _lazy_cv2():
    global _CV2, _CV2_ERROR
    if _CV2 is not None:
        return _CV2
    if _CV2_ERROR is not None:
        raise RuntimeError(_CV2_ERROR)
    try:
        import cv2  # type: ignore
    except Exception as exc:  # pragma: no cover - depends on environment
        _CV2_ERROR = (
            "OpenCV 未安装或不可用。请在项目所在磁盘的 Python 环境中安装 "
            "`opencv-python-headless==4.10.0.84`，不要使用系统盘的全局 Python。"
        )
        raise RuntimeError(_CV2_ERROR) from exc
    _CV2 = cv2
    return cv2


def _lazy_seal_pipeline():
    global _SEAL_PIPELINE, _SEAL_PIPELINE_ERROR
    if _SEAL_PIPELINE is not None:
        return _SEAL_PIPELINE
    if _SEAL_PIPELINE_ERROR is not None:
        return None
    try:
        from paddleocr import SealRecognition  # type: ignore
    except Exception as exc:  # pragma: no cover - depends on runtime
        _SEAL_PIPELINE_ERROR = str(exc)
        return None

    try:
        _SEAL_PIPELINE = SealRecognition(
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
            use_layout_detection=True,
        )
    except Exception as exc:  # pragma: no cover - depends on runtime
        _SEAL_PIPELINE_ERROR = str(exc)
        return None
    return _SEAL_PIPELINE


@dataclass
class SealExtractSettings:
    target_color: str = "#d81e2f"
    tolerance: int = 30
    gray_threshold: float = 0.06
    channel_mode: str = "auto"
    channel_ratio: int = 38
    crop_mode: str = "focus"
    fill_radius: int = 10
    extract_mode: str = "smart"
    prefer_paddle: bool = True

    @classmethod
    def from_raw(cls, raw: Optional[Dict[str, Any]] = None) -> "SealExtractSettings":
        payload = dict(raw or {})
        extract_mode = str(payload.get("extract_mode") or "smart").strip().lower()
        channel_mode = str(payload.get("channel_mode") or "auto").strip().lower()
        crop_mode = str(payload.get("crop_mode") or cls.crop_mode).strip().lower()

        if extract_mode not in {"smart", "red"}:
            extract_mode = "smart"
        if channel_mode not in {"auto", "r", "g", "b"}:
            channel_mode = "auto"
        if crop_mode not in {"full", "focus"}:
            crop_mode = "focus"

        def clamp_int(value: Any, default: int, minimum: int, maximum: int) -> int:
            try:
                numeric = int(float(value))
            except Exception:
                numeric = default
            return max(minimum, min(maximum, numeric))

        def clamp_float(value: Any, default: float, minimum: float, maximum: float) -> float:
            try:
                numeric = float(value)
            except Exception:
                numeric = default
            return max(minimum, min(maximum, numeric))

        target_color = str(payload.get("target_color") or cls.target_color).strip() or cls.target_color
        if not target_color.startswith("#"):
            target_color = f"#{target_color}"

        prefer_paddle_value = payload.get("prefer_paddle", True)
        if isinstance(prefer_paddle_value, str):
            prefer_paddle = prefer_paddle_value.strip().lower() not in {"0", "false", "no", "off"}
        else:
            prefer_paddle = bool(prefer_paddle_value)

        return cls(
            target_color=target_color[:7],
            tolerance=clamp_int(payload.get("tolerance"), cls.tolerance, 5, 100),
            gray_threshold=clamp_float(payload.get("gray_threshold"), cls.gray_threshold, 0.01, 0.4),
            channel_mode=channel_mode,
            channel_ratio=clamp_int(payload.get("channel_ratio"), cls.channel_ratio, 0, 100),
            crop_mode=crop_mode,
            fill_radius=clamp_int(payload.get("fill_radius"), cls.fill_radius, 0, 30),
            extract_mode=extract_mode,
            prefer_paddle=prefer_paddle,
        )


def _hex_to_rgb(hex_value: str) -> Tuple[int, int, int]:
    raw = str(hex_value or "").strip().replace("#", "")
    normalized = (raw + "000000")[:6]
    return tuple(int(normalized[i:i + 2], 16) for i in (0, 2, 4))


def _rgb_to_bgr(hex_value: str) -> Tuple[int, int, int]:
    r, g, b = _hex_to_rgb(hex_value)
    return b, g, r


def _load_pages(file_bytes: bytes, filename: str) -> List[np.ndarray]:
    cv2 = _lazy_cv2()
    suffix = str(filename or "").strip().lower()
    if suffix.endswith(".pdf"):
        pages = convert_from_bytes(file_bytes, dpi=240, first_page=1, last_page=3)
        frames: List[np.ndarray] = []
        for page in pages:
            rgb = np.array(page.convert("RGB"))
            frames.append(cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR))
        return frames

    data = np.frombuffer(file_bytes, dtype=np.uint8)
    image = cv2.imdecode(data, cv2.IMREAD_COLOR)
    if image is None:
        pil = Image.open(io.BytesIO(file_bytes)).convert("RGB")
        return [cv2.cvtColor(np.array(pil), cv2.COLOR_RGB2BGR)]
    return [image]


def _resize_for_processing(image_bgr: np.ndarray, max_side: int = 1800) -> Tuple[np.ndarray, float]:
    height, width = image_bgr.shape[:2]
    longest = max(height, width, 1)
    scale = min(1.0, float(max_side) / float(longest))
    if scale >= 0.999:
        return image_bgr, 1.0
    cv2 = _lazy_cv2()
    resized = cv2.resize(
        image_bgr,
        (max(1, int(round(width * scale))), max(1, int(round(height * scale)))),
        interpolation=cv2.INTER_AREA,
    )
    return resized, scale


def _normalize_box(box: Sequence[Sequence[float]]) -> Optional[Tuple[int, int, int, int]]:
    try:
        arr = np.array(box, dtype=np.float32)
    except Exception:
        return None
    if arr.ndim != 2 or arr.shape[0] < 4:
        return None
    xs = arr[:, 0]
    ys = arr[:, 1]
    return (
        int(math.floor(float(np.min(xs)))),
        int(math.floor(float(np.min(ys)))),
        int(math.ceil(float(np.max(xs)))),
        int(math.ceil(float(np.max(ys)))),
    )


def _clip_box(box: Tuple[int, int, int, int], width: int, height: int) -> Tuple[int, int, int, int]:
    x1, y1, x2, y2 = box
    return (
        max(0, min(width - 1, int(x1))),
        max(0, min(height - 1, int(y1))),
        max(0, min(width, int(x2))),
        max(0, min(height, int(y2))),
    )


def _expand_box(box: Tuple[int, int, int, int], padding: int, width: int, height: int) -> Tuple[int, int, int, int]:
    x1, y1, x2, y2 = box
    return _clip_box((x1 - padding, y1 - padding, x2 + padding, y2 + padding), width, height)


def _square_box_around(
    box: Tuple[int, int, int, int],
    width: int,
    height: int,
    *,
    padding: int = 0,
    min_side: int = 0,
) -> Tuple[int, int, int, int]:
    x1, y1, x2, y2 = box
    center_x = (x1 + x2) / 2.0
    center_y = (y1 + y2) / 2.0
    side = max(x2 - x1, y2 - y1) + max(0, padding) * 2
    side = max(side, max(1, min_side))
    half = side / 2.0
    left = int(round(center_x - half))
    top = int(round(center_y - half))
    right = int(round(center_x + half))
    bottom = int(round(center_y + half))
    return _clip_box((left, top, right, bottom), width, height)


def _merge_boxes(boxes: Sequence[Tuple[int, int, int, int]]) -> Optional[Tuple[int, int, int, int]]:
    if not boxes:
        return None
    x1 = min(box[0] for box in boxes)
    y1 = min(box[1] for box in boxes)
    x2 = max(box[2] for box in boxes)
    y2 = max(box[3] for box in boxes)
    return x1, y1, x2, y2


def _boxes_intersect(a: Tuple[int, int, int, int], b: Tuple[int, int, int, int]) -> bool:
    return not (a[2] <= b[0] or b[2] <= a[0] or a[3] <= b[1] or b[3] <= a[1])


def _touches_border(box: Tuple[int, int, int, int], width: int, height: int, margin: int = 10) -> bool:
    x1, y1, x2, y2 = box
    return x1 <= margin or y1 <= margin or x2 >= width - margin or y2 >= height - margin


def _box_iou(a: Tuple[int, int, int, int], b: Tuple[int, int, int, int]) -> float:
    ix1 = max(a[0], b[0])
    iy1 = max(a[1], b[1])
    ix2 = min(a[2], b[2])
    iy2 = min(a[3], b[3])
    if ix2 <= ix1 or iy2 <= iy1:
        return 0.0
    inter = float((ix2 - ix1) * (iy2 - iy1))
    area_a = float(max(1, a[2] - a[0]) * max(1, a[3] - a[1]))
    area_b = float(max(1, b[2] - b[0]) * max(1, b[3] - b[1]))
    return inter / max(1.0, area_a + area_b - inter)


def _box_mask_ratio(mask: np.ndarray, box: Tuple[int, int, int, int]) -> float:
    height, width = mask.shape[:2]
    x1, y1, x2, y2 = _clip_box(box, width, height)
    if x2 <= x1 or y2 <= y1:
        return 0.0
    roi = mask[y1:y2, x1:x2]
    if roi.size == 0:
        return 0.0
    active = float(np.count_nonzero(roi))
    return active / float(roi.shape[0] * roi.shape[1])


def _ensure_odd(value: int, minimum: int = 3, maximum: Optional[int] = None) -> int:
    numeric = max(minimum, int(value))
    if maximum is not None:
        numeric = min(maximum, numeric)
    if numeric % 2 == 0:
        numeric += 1
    if maximum is not None and numeric > maximum:
        numeric = maximum if maximum % 2 == 1 else max(minimum, maximum - 1)
    return max(minimum if minimum % 2 == 1 else minimum + 1, numeric)


def _normalize_to_u8(values: np.ndarray, low_percentile: float = 2.0, high_percentile: float = 98.0) -> np.ndarray:
    array = np.asarray(values, dtype=np.float32)
    valid = array[np.isfinite(array)]
    if valid.size == 0:
        return np.zeros(array.shape, dtype=np.uint8)

    low = float(np.percentile(valid, low_percentile))
    high = float(np.percentile(valid, high_percentile))
    if high <= low + 1e-6:
        low = float(np.min(valid))
        high = float(np.max(valid))
    if high <= low + 1e-6:
        return np.zeros(array.shape, dtype=np.uint8)

    normalized = (array - low) * (255.0 / (high - low))
    return np.clip(normalized, 0, 255).astype(np.uint8)


def _estimate_target_hue(
    hue: np.ndarray,
    saturation: np.ndarray,
    red_response: np.ndarray,
    seed_mask: np.ndarray,
    fallback_hue: int,
) -> int:
    candidate = (
        (saturation.astype(np.float32) >= max(10.0, float(np.percentile(saturation, 55)) * 0.35))
        & (red_response.astype(np.float32) >= max(8.0, float(np.percentile(red_response, 65)) * 0.35))
    ) | (seed_mask > 0)
    if int(np.count_nonzero(candidate)) < 12:
        return int(fallback_hue)

    hue_int = hue.astype(np.int16)
    delta_from_fallback = np.minimum(np.abs(hue_int - int(fallback_hue)), 180 - np.abs(hue_int - int(fallback_hue)))
    near_fallback = candidate & (delta_from_fallback <= 40)
    selected = near_fallback if int(np.count_nonzero(near_fallback)) >= 12 else candidate

    weights = saturation[selected].astype(np.float32) + red_response[selected].astype(np.float32) + 1.0
    if int(np.count_nonzero(seed_mask[selected])) > 0:
        weights += (seed_mask[selected] > 0).astype(np.float32) * 42.0
    histogram = np.bincount(hue[selected].astype(np.int32), weights=weights, minlength=180)
    peak = int(np.argmax(histogram))

    peak_delta = min(abs(peak - int(fallback_hue)), 180 - abs(peak - int(fallback_hue)))
    if peak_delta > 48 and int(np.count_nonzero(near_fallback)) >= 12:
        fallback_hist = np.bincount(
            hue[near_fallback].astype(np.int32),
            weights=(saturation[near_fallback].astype(np.float32) + red_response[near_fallback].astype(np.float32) + 1.0),
            minlength=180,
        )
        peak = int(np.argmax(fallback_hist))

    return peak


def _build_circle_support_mask(shape: Tuple[int, int], circle: Optional[Tuple[int, int, int]]) -> np.ndarray:
    cv2 = _lazy_cv2()
    height, width = shape
    support = np.zeros((height, width), dtype=np.uint8)
    if not circle:
        return support

    center_x, center_y, radius = circle
    outer_radius = max(2, int(round(radius * 1.15)))
    inner_radius = max(1, int(round(radius * 0.34)))
    core_radius = max(1, int(round(radius * 0.28)))
    cv2.circle(support, (center_x, center_y), outer_radius, 255, -1)
    cv2.circle(support, (center_x, center_y), inner_radius, 0, -1)
    cv2.circle(support, (center_x, center_y), core_radius, 255, -1)
    return support


def _mask_bbox(mask: np.ndarray, threshold: int = 1) -> Optional[Tuple[int, int, int, int]]:
    ys, xs = np.where(mask > threshold)
    if xs.size <= 0 or ys.size <= 0:
        return None
    return int(np.min(xs)), int(np.min(ys)), int(np.max(xs)) + 1, int(np.max(ys)) + 1


def _detect_circle_hint(response_map: np.ndarray, reference_mask: np.ndarray) -> Optional[Tuple[int, int, int]]:
    cv2 = _lazy_cv2()
    height, width = response_map.shape[:2]
    shortest_side = min(height, width)
    if shortest_side < 48:
        return None

    blurred = cv2.medianBlur(response_map, 5)
    circles = cv2.HoughCircles(
        blurred,
        cv2.HOUGH_GRADIENT,
        dp=1.2,
        minDist=max(18.0, shortest_side / 3.0),
        param1=120,
        param2=16,
        minRadius=max(10, int(round(shortest_side * 0.16))),
        maxRadius=max(16, int(round(shortest_side * 0.62))),
    )
    if circles is None or circles.size == 0:
        return None

    moments = cv2.moments(np.where(reference_mask > 0, 255, 0).astype(np.uint8))
    if moments["m00"] > 1e-3:
        reference_center = (float(moments["m10"] / moments["m00"]), float(moments["m01"] / moments["m00"]))
    else:
        reference_center = (width / 2.0, height / 2.0)

    reference_box = None
    if int(np.count_nonzero(reference_mask)) > 0:
        ys, xs = np.where(reference_mask > 0)
        if xs.size and ys.size:
            reference_box = (int(np.min(xs)), int(np.min(ys)), int(np.max(xs)) + 1, int(np.max(ys)) + 1)

    best_circle: Optional[Tuple[int, int, int]] = None
    best_score = float("-inf")
    diagonal = math.hypot(width, height)
    for circle in np.round(circles[0]).astype(np.int32):
        center_x, center_y, radius = int(circle[0]), int(circle[1]), int(circle[2])
        if radius <= 0:
            continue

        support_mask = _build_circle_support_mask((height, width), (center_x, center_y, radius))
        overlap_pixels = float(np.count_nonzero((reference_mask > 0) & (support_mask > 0)))
        reference_pixels = float(max(1, np.count_nonzero(reference_mask)))
        overlap_ratio = overlap_pixels / reference_pixels
        distance_ratio = math.hypot(center_x - reference_center[0], center_y - reference_center[1]) / max(1.0, diagonal)
        radius_score = 0.0
        if reference_box:
            expected_radius = max(reference_box[2] - reference_box[0], reference_box[3] - reference_box[1]) / 2.0
            radius_score = max(0.0, 1.0 - abs(radius - expected_radius) / max(18.0, expected_radius))

        score = overlap_ratio * 2.4 + radius_score * 1.1 - distance_ratio * 1.6
        if score > best_score:
            best_score = score
            best_circle = (center_x, center_y, radius)

    return best_circle if best_score > -0.15 else None


def _cleanup_mask_components(mask: np.ndarray, support_mask: Optional[np.ndarray] = None) -> np.ndarray:
    cv2 = _lazy_cv2()
    binary = np.where(mask > 0, 255, 0).astype(np.uint8)
    if int(np.count_nonzero(binary)) <= 0:
        return binary

    height, width = binary.shape[:2]
    image_area = float(height * width)
    component_count, labels, stats, _ = cv2.connectedComponentsWithStats(binary, connectivity=8)
    areas = [int(stats[idx, cv2.CC_STAT_AREA]) for idx in range(1, component_count) if int(stats[idx, cv2.CC_STAT_AREA]) > 0]
    if not areas:
        return binary

    area_array = np.array(areas, dtype=np.float32)
    min_area = max(3, int(min(32.0, max(3.0, float(np.percentile(area_array, 25)) * 0.28))))
    max_area = image_area * 0.82
    filtered = np.zeros_like(binary)

    for component_idx in range(1, component_count):
        area = int(stats[component_idx, cv2.CC_STAT_AREA])
        if area < min_area:
            continue
        x = int(stats[component_idx, cv2.CC_STAT_LEFT])
        y = int(stats[component_idx, cv2.CC_STAT_TOP])
        box_width = int(stats[component_idx, cv2.CC_STAT_WIDTH])
        box_height = int(stats[component_idx, cv2.CC_STAT_HEIGHT])
        if box_width <= 0 or box_height <= 0:
            continue

        box = (x, y, x + box_width, y + box_height)
        overlap_ratio = _box_mask_ratio(support_mask, box) if support_mask is not None and int(np.count_nonzero(support_mask)) > 0 else 0.0
        aspect = max(box_width / max(1.0, box_height), box_height / max(1.0, box_width))
        touches_border = _touches_border(box, width, height, margin=max(2, min(width, height) // 45))

        if area > max_area and overlap_ratio < 0.08:
            continue
        if touches_border and area > image_area * 0.22 and overlap_ratio < 0.08:
            continue
        if aspect > 16.0 and area > max(min_area * 6, int(image_area * 0.002)) and overlap_ratio < 0.12:
            continue

        filtered[labels == component_idx] = 255

    if int(np.count_nonzero(filtered)) <= 0:
        filtered = binary

    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    return cv2.morphologyEx(filtered, cv2.MORPH_CLOSE, kernel, iterations=1)


def _build_page_response(image_bgr: np.ndarray) -> np.ndarray:
    cv2 = _lazy_cv2()
    b_channel, g_channel, r_channel = cv2.split(image_bgr)
    lab = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2LAB)
    a_channel = lab[:, :, 1]
    clahe = cv2.createCLAHE(clipLimit=2.6, tileGridSize=(8, 8))
    a_equalized = clahe.apply(a_channel)
    red_delta = np.clip(
        r_channel.astype(np.int16) - ((g_channel.astype(np.int16) + b_channel.astype(np.int16)) / 2.0),
        0,
        255,
    ).astype(np.uint8)
    red_equalized = clahe.apply(red_delta)
    return cv2.addWeighted(a_equalized, 0.58, red_equalized, 0.42, 0)


def _remove_border_line_noise(mask: np.ndarray) -> np.ndarray:
    cv2 = _lazy_cv2()
    binary = np.where(mask > 0, 255, 0).astype(np.uint8)
    if int(np.count_nonzero(binary)) <= 0:
        return binary

    height, width = binary.shape[:2]
    shortest_side = min(height, width)
    image_area = float(max(1, height * width))
    component_count, labels, stats, _ = cv2.connectedComponentsWithStats(binary, connectivity=8)
    filtered = np.zeros_like(binary)

    for component_idx in range(1, component_count):
        area = int(stats[component_idx, cv2.CC_STAT_AREA])
        if area <= 0:
            continue
        x = int(stats[component_idx, cv2.CC_STAT_LEFT])
        y = int(stats[component_idx, cv2.CC_STAT_TOP])
        box_width = int(stats[component_idx, cv2.CC_STAT_WIDTH])
        box_height = int(stats[component_idx, cv2.CC_STAT_HEIGHT])
        box = (x, y, x + box_width, y + box_height)
        touches_border = _touches_border(box, width, height, margin=max(6, shortest_side // 40))
        aspect = max(box_width / max(1.0, box_height), box_height / max(1.0, box_width))
        long_side_ratio = max(box_width, box_height) / max(1.0, float(shortest_side))
        area_ratio = area / image_area

        if touches_border and (aspect > 5.5 or long_side_ratio > 0.22 or area_ratio > 0.006):
            continue
        filtered[labels == component_idx] = 255

    if int(np.count_nonzero(filtered)) <= 0:
        filtered = binary

    edges = cv2.Canny(filtered, 50, 150, apertureSize=3)
    line_threshold = max(20, int(round(shortest_side * 0.08)))
    min_line_length = max(40, int(round(shortest_side * 0.16)))
    max_line_gap = max(6, int(round(shortest_side * 0.02)))
    lines = cv2.HoughLinesP(
        edges,
        1,
        math.pi / 180.0,
        threshold=line_threshold,
        minLineLength=min_line_length,
        maxLineGap=max_line_gap,
    )
    if lines is not None and len(lines) > 0:
        remove_mask = np.zeros_like(filtered)
        border_margin = max(10, int(round(shortest_side * 0.04)))
        thickness = max(3, int(round(shortest_side * 0.01)))
        for line in lines[:, 0]:
            x1, y1, x2, y2 = [int(value) for value in line]
            length = math.hypot(x2 - x1, y2 - y1)
            if length < min_line_length:
                continue
            angle = abs(math.degrees(math.atan2(y2 - y1, x2 - x1)))
            horizontal = angle < 10.0 or angle > 170.0
            vertical = 80.0 < angle < 100.0
            near_border = (
                min(x1, x2) <= border_margin
                or min(y1, y2) <= border_margin
                or max(x1, x2) >= width - border_margin
                or max(y1, y2) >= height - border_margin
            )
            if near_border and (horizontal or vertical):
                cv2.line(remove_mask, (x1, y1), (x2, y2), 255, thickness=thickness)
        filtered = np.where(remove_mask > 0, 0, filtered).astype(np.uint8)

    return _cleanup_mask_components(filtered)


def _normalize_xyxy_box(raw: Any) -> Optional[Tuple[int, int, int, int]]:
    if isinstance(raw, (list, tuple)) and len(raw) >= 4:
        try:
            x1 = int(round(float(raw[0])))
            y1 = int(round(float(raw[1])))
            x2 = int(round(float(raw[2])))
            y2 = int(round(float(raw[3])))
        except Exception:
            return None
        if x2 <= x1 or y2 <= y1:
            return None
        return x1, y1, x2, y2
    return None


def _extract_result_payload(result_obj: Any) -> Dict[str, Any]:
    if isinstance(result_obj, dict):
        payload = result_obj.get("res")
        if isinstance(payload, dict):
            return payload
        return result_obj
    payload = getattr(result_obj, "res", None)
    if isinstance(payload, dict):
        return payload
    json_payload = getattr(result_obj, "json", None)
    if isinstance(json_payload, dict):
        return json_payload
    return {}


def _locate_stamp_with_paddle_pipeline(page_bgr: np.ndarray) -> Tuple[Optional[Tuple[int, int, int, int]], Dict[str, Any]]:
    cv2 = _lazy_cv2()
    pipeline = _lazy_seal_pipeline()
    if not pipeline:
        return None, {"stamp_locator": "paddle_seal_pipeline_unavailable"}

    temp_path = ""
    try:
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            temp_path = tmp.name
        ok, encoded = cv2.imencode(".png", page_bgr)
        if not ok:
            return None, {"stamp_locator": "paddle_seal_pipeline_encode_failed"}
        with open(temp_path, "wb") as file_obj:
            file_obj.write(encoded.tobytes())

        results = list(pipeline.predict(temp_path))
        if not results:
            return None, {"stamp_locator": "paddle_seal_pipeline_empty"}

        payload = _extract_result_payload(results[0])
        best_box = None
        best_score = float("-inf")

        layout_det_res = payload.get("layout_det_res")
        layout_boxes = []
        if isinstance(layout_det_res, dict):
            layout_boxes = layout_det_res.get("boxes") or []
        for item in layout_boxes:
            if not isinstance(item, dict):
                continue
            if str(item.get("label") or "").strip().lower() != "seal":
                continue
            box = _normalize_xyxy_box(item.get("coordinate"))
            if not box:
                continue
            score = float(item.get("score") or 0.0)
            if score > best_score:
                best_score = score
                best_box = box

        if best_box is not None:
            return best_box, {"stamp_locator": "paddle_seal_pipeline_layout", "stamp_score": round(best_score, 4)}

        seal_res_list = payload.get("seal_res_list") or []
        polygon_boxes: List[Tuple[int, int, int, int]] = []
        for item in seal_res_list:
            if isinstance(item, dict):
                dt_polys = item.get("dt_polys") or item.get("seal_box_list") or []
                for poly in dt_polys:
                    box = _normalize_box(poly) if not _normalize_xyxy_box(poly) else _normalize_xyxy_box(poly)
                    if box:
                        polygon_boxes.append(box)

        merged_box = _merge_boxes(polygon_boxes)
        if merged_box:
            return merged_box, {"stamp_locator": "paddle_seal_pipeline_polys"}

        return None, {"stamp_locator": "paddle_seal_pipeline_no_seal"}
    except Exception as exc:  # pragma: no cover - depends on runtime
        return None, {"stamp_locator": "paddle_seal_pipeline_error", "stamp_warning": str(exc)}
    finally:
        if temp_path:
            try:
                os.remove(temp_path)
            except OSError:
                pass


def _keep_components_near_box(mask: np.ndarray, target_box: Tuple[int, int, int, int]) -> np.ndarray:
    cv2 = _lazy_cv2()
    binary = np.where(mask > 0, 255, 0).astype(np.uint8)
    if int(np.count_nonzero(binary)) <= 0:
        return binary

    height, width = binary.shape[:2]
    target_size = max(target_box[2] - target_box[0], target_box[3] - target_box[1], 1)
    keep_box = _square_box_around(
        target_box,
        width,
        height,
        padding=max(18, int(round(target_size * 0.42))),
        min_side=max(140, int(round(target_size * 1.95))),
    )

    component_count, labels, stats, _ = cv2.connectedComponentsWithStats(binary, connectivity=8)
    filtered = np.zeros_like(binary)
    for component_idx in range(1, component_count):
        area = int(stats[component_idx, cv2.CC_STAT_AREA])
        if area <= 0:
            continue
        x = int(stats[component_idx, cv2.CC_STAT_LEFT])
        y = int(stats[component_idx, cv2.CC_STAT_TOP])
        box_width = int(stats[component_idx, cv2.CC_STAT_WIDTH])
        box_height = int(stats[component_idx, cv2.CC_STAT_HEIGHT])
        component_box = (x, y, x + box_width, y + box_height)
        if _boxes_intersect(component_box, keep_box) or _boxes_intersect(_expand_box(component_box, 10, width, height), keep_box):
            filtered[labels == component_idx] = 255

    return filtered if int(np.count_nonzero(filtered)) > 0 else binary


def _score_circle_candidate(
    circle: Tuple[int, int, int],
    mask: np.ndarray,
    support_box: Tuple[int, int, int, int],
) -> float:
    height, width = mask.shape[:2]
    center_x, center_y, radius = circle
    if radius <= 0:
        return float("-inf")

    support_mask = _build_circle_support_mask((height, width), circle)
    overlap = float(np.count_nonzero((mask > 0) & (support_mask > 0))) / max(1.0, float(np.count_nonzero(support_mask)))
    support_center_x = (support_box[0] + support_box[2]) / 2.0
    support_center_y = (support_box[1] + support_box[3]) / 2.0
    support_size = max(support_box[2] - support_box[0], support_box[3] - support_box[1], 1)
    center_distance = math.hypot(center_x - support_center_x, center_y - support_center_y) / max(1.0, support_size * 2.6)
    support_overlap = _box_iou(
        (int(center_x - radius), int(center_y - radius), int(center_x + radius), int(center_y + radius)),
        support_box,
    )
    border_penalty = 0.0
    if center_x - radius <= 4 or center_y - radius <= 4 or center_x + radius >= width - 4 or center_y + radius >= height - 4:
        border_penalty = 1.2

    return overlap * 4.8 + support_overlap * 3.4 - center_distance * 1.7 - border_penalty


def _detect_circle_from_support(
    response_map: np.ndarray,
    mask: np.ndarray,
    support_box: Tuple[int, int, int, int],
) -> Optional[Tuple[int, int, int]]:
    cv2 = _lazy_cv2()
    height, width = response_map.shape[:2]
    support_size = max(support_box[2] - support_box[0], support_box[3] - support_box[1], 1)
    search_box = _square_box_around(
        support_box,
        width,
        height,
        padding=max(32, int(round(support_size * 1.85))),
        min_side=max(220, int(round(support_size * 6.0))),
    )
    sx1, sy1, sx2, sy2 = search_box
    local_response = response_map[sy1:sy2, sx1:sx2]
    local_mask = mask[sy1:sy2, sx1:sx2]
    if local_response.size == 0 or int(np.count_nonzero(local_mask)) <= 0:
        return None

    blurred = cv2.GaussianBlur(local_response, (0, 0), sigmaX=1.25, sigmaY=1.25)
    local_support = (support_box[0] - sx1, support_box[1] - sy1, support_box[2] - sx1, support_box[3] - sy1)
    local_support = _clip_box(local_support, local_response.shape[1], local_response.shape[0])
    local_support_size = max(local_support[2] - local_support[0], local_support[3] - local_support[1], 1)

    passes = [
        {
            "min_radius": max(18, int(round(local_support_size * 0.8))),
            "max_radius": int(round(local_support_size * 4.0)),
            "param2": 14,
        },
        {
            "min_radius": max(14, int(round(local_support_size * 0.55))),
            "max_radius": int(round(local_support_size * 5.0)),
            "param2": 11,
        },
    ]

    best_circle: Optional[Tuple[int, int, int]] = None
    best_score = float("-inf")
    max_allowed_radius = int(round(min(local_response.shape[:2]) * 0.48))
    for detection_pass in passes:
        min_radius = min(detection_pass["min_radius"], max_allowed_radius)
        max_radius = min(max(min_radius + 8, detection_pass["max_radius"]), max_allowed_radius)
        if max_radius <= min_radius:
            continue
        circles = cv2.HoughCircles(
            blurred,
            cv2.HOUGH_GRADIENT,
            dp=1.2,
            minDist=max(24.0, local_support_size * 1.2),
            param1=120,
            param2=detection_pass["param2"],
            minRadius=min_radius,
            maxRadius=max_radius,
        )
        if circles is None or circles.size == 0:
            continue
        for circle in np.round(circles[0]).astype(np.int32):
            local_circle = (int(circle[0]), int(circle[1]), int(circle[2]))
            score = _score_circle_candidate(local_circle, local_mask, local_support)
            if score > best_score:
                best_score = score
                best_circle = (sx1 + local_circle[0], sy1 + local_circle[1], local_circle[2])

    return best_circle if best_score > 0.35 else None


def _estimate_circle_from_mask_points(
    mask: np.ndarray,
    support_box: Tuple[int, int, int, int],
) -> Optional[Tuple[int, int, int]]:
    cv2 = _lazy_cv2()
    height, width = mask.shape[:2]
    support_size = max(support_box[2] - support_box[0], support_box[3] - support_box[1], 1)
    region_box = _square_box_around(
        support_box,
        width,
        height,
        padding=max(24, int(round(support_size * 1.5))),
        min_side=max(180, int(round(support_size * 4.8))),
    )
    x1, y1, x2, y2 = region_box
    region_mask = mask[y1:y2, x1:x2]
    ys, xs = np.where(region_mask > 0)
    if xs.size < 28 or ys.size < 28:
        return None

    points = np.column_stack((xs.astype(np.float32), ys.astype(np.float32)))
    center, radius = cv2.minEnclosingCircle(points)
    local_circle = (int(round(center[0])), int(round(center[1])), int(round(radius)))
    score = _score_circle_candidate(local_circle, region_mask, (support_box[0] - x1, support_box[1] - y1, support_box[2] - x1, support_box[3] - y1))
    if score <= 0.12:
        return None
    return (x1 + local_circle[0], y1 + local_circle[1], local_circle[2])


def _localize_stamp_box(
    image_bgr: np.ndarray,
    full_mask: np.ndarray,
    candidate_box: Tuple[int, int, int, int],
) -> Tuple[Tuple[int, int, int, int], Dict[str, Any]]:
    height, width = image_bgr.shape[:2]
    clean_mask = _remove_border_line_noise(full_mask)
    candidate_size = max(candidate_box[2] - candidate_box[0], candidate_box[3] - candidate_box[1], 1)
    support_box = _square_box_around(
        candidate_box,
        width,
        height,
        padding=max(10, int(round(candidate_size * 0.35))),
        min_side=max(60, int(round(candidate_size * 1.6))),
    )

    response_map = _build_page_response(image_bgr)
    circle = _detect_circle_from_support(response_map, clean_mask, support_box)
    locator = "hough_circle"
    if circle is None:
        circle = _estimate_circle_from_mask_points(clean_mask, support_box)
        locator = "min_enclosing_circle"

    if circle is not None:
        center_x, center_y, radius = circle
        localized_box = _square_box_around(
            (center_x - radius, center_y - radius, center_x + radius, center_y + radius),
            width,
            height,
            padding=max(18, int(round(radius * 0.42))),
            min_side=max(int(round(radius * 2.55)), 140),
        )
        return localized_box, {
            "stamp_locator": locator,
            "stamp_circle": [int(center_x), int(center_y), int(radius)],
        }

    fallback_box = _expand_box(support_box, max(18, int(round(candidate_size * 0.65))), width, height)
    return fallback_box, {"stamp_locator": "support_box_fallback"}


def _filter_mask_to_support_group(
    mask: np.ndarray,
    support_box: Optional[Tuple[int, int, int, int]],
) -> Tuple[np.ndarray, Optional[Tuple[int, int, int, int]], str]:
    cv2 = _lazy_cv2()
    binary = np.where(mask > 0, 255, 0).astype(np.uint8)
    if support_box is None or int(np.count_nonzero(binary)) <= 0:
        return binary, None, "mask_only"

    height, width = binary.shape[:2]
    local_support = _clip_box(support_box, width, height)
    if local_support[2] <= local_support[0] or local_support[3] <= local_support[1]:
        return binary, None, "mask_only"

    candidate = _find_best_candidate(binary, [local_support])
    if not candidate:
        return binary, None, "mask_only"

    focus_box, detection_source = candidate
    keep_box = _expand_box(
        focus_box,
        max(10, int(round(max(focus_box[2] - focus_box[0], focus_box[3] - focus_box[1]) * 0.18))),
        width,
        height,
    )

    component_count, labels, stats, _ = cv2.connectedComponentsWithStats(binary, connectivity=8)
    filtered = np.zeros_like(binary)
    for component_idx in range(1, component_count):
        area = int(stats[component_idx, cv2.CC_STAT_AREA])
        if area <= 0:
            continue
        x = int(stats[component_idx, cv2.CC_STAT_LEFT])
        y = int(stats[component_idx, cv2.CC_STAT_TOP])
        box_width = int(stats[component_idx, cv2.CC_STAT_WIDTH])
        box_height = int(stats[component_idx, cv2.CC_STAT_HEIGHT])
        component_box = (x, y, x + box_width, y + box_height)
        if _boxes_intersect(component_box, keep_box) or _boxes_intersect(_expand_box(component_box, 8, width, height), keep_box):
            filtered[labels == component_idx] = 255

    if int(np.count_nonzero(filtered)) <= 0:
        filtered = binary

    return filtered, focus_box, detection_source


def _score_mask_quality(
    mask: np.ndarray,
    response_map: np.ndarray,
    support_zone: Optional[np.ndarray] = None,
    circle_support: Optional[np.ndarray] = None,
) -> float:
    cv2 = _lazy_cv2()
    binary = np.where(mask > 0, 255, 0).astype(np.uint8)
    foreground = int(np.count_nonzero(binary))
    if foreground <= 0:
        return float("-inf")

    height, width = binary.shape[:2]
    image_area = float(height * width)
    foreground_ratio = foreground / max(1.0, image_area)
    component_count, _, stats, _ = cv2.connectedComponentsWithStats(binary, connectivity=8)
    component_areas = np.array([int(stats[idx, cv2.CC_STAT_AREA]) for idx in range(1, component_count)], dtype=np.float32)
    significant_components = component_areas[component_areas >= 4]
    medium_components = component_areas[(component_areas >= 4) & (component_areas <= image_area * 0.035)]
    largest_ratio = float(np.max(component_areas) / max(1.0, foreground)) if component_areas.size else 1.0

    contours_info = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    contours = contours_info[0] if len(contours_info) == 2 else contours_info[1]
    total_perimeter = float(sum(cv2.arcLength(contour, True) for contour in contours))
    perimeter_score = min(3.0, total_perimeter / max(60.0, math.sqrt(image_area) * 4.0))
    response_score = float(np.mean(response_map[binary > 0])) / 255.0

    score = response_score * 2.4
    score += min(2.6, len(significant_components) / 10.0)
    score += min(1.6, len(medium_components) / 8.0)
    score += perimeter_score
    score += max(0.0, 1.9 - abs(foreground_ratio - 0.14) * 8.0)

    if support_zone is not None and int(np.count_nonzero(support_zone)) > 0:
        support_ratio = float(np.count_nonzero((binary > 0) & (support_zone > 0))) / max(1.0, foreground)
        score += support_ratio * 1.4

    if circle_support is not None and int(np.count_nonzero(circle_support)) > 0:
        circle_ratio = float(np.count_nonzero((binary > 0) & (circle_support > 0))) / max(1.0, foreground)
        score += circle_ratio * 1.0

    if largest_ratio > 0.82:
        score -= 1.4
    if foreground_ratio > 0.46 or foreground_ratio < 0.003:
        score -= 2.1

    return score


def _refine_crop_mask(roi_bgr: np.ndarray, seed_mask: np.ndarray, settings: SealExtractSettings) -> Tuple[np.ndarray, Dict[str, Any]]:
    cv2 = _lazy_cv2()
    height, width = roi_bgr.shape[:2]
    if height <= 0 or width <= 0:
        return np.zeros((max(1, height), max(1, width)), dtype=np.uint8), {
            "auto_profile": "empty",
            "auto_hue": None,
            "refine_variant": "empty",
            "circle_hint": None,
        }

    seed = np.where(seed_mask > 0, 255, 0).astype(np.uint8)
    b_channel, g_channel, r_channel = cv2.split(roi_bgr)
    hsv = cv2.cvtColor(roi_bgr, cv2.COLOR_BGR2HSV)
    lab = cv2.cvtColor(roi_bgr, cv2.COLOR_BGR2LAB)
    hue = hsv[:, :, 0]
    saturation = hsv[:, :, 1]
    value = hsv[:, :, 2]

    clip_limit = 2.2 + settings.tolerance / 35.0
    clahe = cv2.createCLAHE(clipLimit=clip_limit, tileGridSize=(8, 8))
    a_channel = lab[:, :, 1]
    a_equalized = clahe.apply(a_channel)

    red_primary = np.clip(
        r_channel.astype(np.int16) - np.maximum(g_channel.astype(np.int16), b_channel.astype(np.int16)),
        0,
        255,
    ).astype(np.uint8)
    red_secondary = np.clip(
        r_channel.astype(np.int16) - ((g_channel.astype(np.int16) + b_channel.astype(np.int16)) / 2.0),
        0,
        255,
    ).astype(np.uint8)
    red_equalized = clahe.apply(red_secondary)
    combined_response = cv2.addWeighted(a_equalized, 0.58, red_equalized, 0.42, 0)

    target_bgr = np.uint8([[list(_rgb_to_bgr(settings.target_color))]])
    base_hue = int(cv2.cvtColor(target_bgr, cv2.COLOR_BGR2HSV)[0, 0, 0])
    auto_hue = _estimate_target_hue(hue, saturation, red_equalized, seed, base_hue)
    hue_delta = np.minimum(np.abs(hue.astype(np.int16) - auto_hue), 180 - np.abs(hue.astype(np.int16) - auto_hue))

    analysis_mask = (
        (seed > 0)
        | (red_equalized >= np.percentile(red_equalized, 68))
        | (a_equalized >= np.percentile(a_equalized, 70))
    )
    if int(np.count_nonzero(analysis_mask)) < 24:
        analysis_mask = np.ones((height, width), dtype=bool)

    analysis_values = combined_response[analysis_mask]
    saturation_values = saturation[analysis_mask]
    red_values = red_secondary[analysis_mask]

    soft_threshold = max(18.0, float(np.percentile(analysis_values, 58)) - 6.0)
    balanced_threshold = max(24.0, float(np.percentile(analysis_values, 72)))
    strict_threshold = max(30.0, float(np.percentile(analysis_values, 84)))

    saturation_soft = max(5.0, float(np.percentile(saturation_values, 45)) * 0.45)
    saturation_balanced = max(10.0, float(np.percentile(saturation_values, 60)) * 0.58)
    red_soft = max(4.0, float(np.percentile(red_values, 58)) * 0.58)
    red_balanced = max(8.0, float(np.percentile(red_values, 74)) * 0.72)
    faded_profile = float(np.percentile(saturation_values, 80)) < 78.0 or float(np.percentile(red_values, 80)) < 54.0

    hue_limit_soft = max(12, int(round(12 + settings.tolerance * 0.68)))
    hue_limit_balanced = max(8, int(round(8 + settings.tolerance * 0.46)))
    hue_limit_loose = hue_limit_soft + 10

    if settings.extract_mode == "red":
        soft_bool = (
            (hue_delta <= hue_limit_soft)
            & (combined_response >= soft_threshold)
            & ((saturation >= saturation_soft) | (red_secondary >= red_soft) | (seed > 0))
            & (value >= 18)
        )
        balanced_bool = (
            (hue_delta <= hue_limit_balanced)
            & (combined_response >= balanced_threshold)
            & ((saturation >= saturation_balanced) | (red_secondary >= red_balanced) | (seed > 0))
            & (value >= 18)
        )
    else:
        soft_bool = (
            (
                ((combined_response >= soft_threshold) & (hue_delta <= hue_limit_soft))
                | ((red_equalized >= soft_threshold - 6) & (red_secondary >= red_soft))
                | ((a_equalized >= balanced_threshold - 2) & (red_secondary >= max(3.0, red_soft * 0.76)))
                | (seed > 0)
            )
            & (value >= 16)
        )
        balanced_bool = (
            (
                ((combined_response >= balanced_threshold) & (hue_delta <= hue_limit_balanced))
                | ((red_equalized >= balanced_threshold - 4) & (red_secondary >= red_balanced) & (saturation >= saturation_soft * 0.75))
                | ((a_equalized >= strict_threshold - 4) & (red_secondary >= red_soft))
                | (seed > 0)
            )
            & (value >= 16)
        )

    soft_mask = np.where(soft_bool, 255, 0).astype(np.uint8)
    balanced_mask = np.where(balanced_bool, 255, 0).astype(np.uint8)

    blurred_response = cv2.GaussianBlur(combined_response, (0, 0), sigmaX=1.15, sigmaY=1.15)
    block_size = _ensure_odd(int(round(min(height, width) * 0.18)), minimum=21, maximum=101)
    adaptive_c = max(2, int(round(settings.tolerance / 11.0)))
    adaptive_mask = cv2.adaptiveThreshold(
        blurred_response,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        block_size,
        adaptive_c,
    )
    _, otsu_mask = cv2.threshold(blurred_response, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

    loose_color_gate = (
        (hue_delta <= hue_limit_loose)
        & (
            (saturation >= max(4.0, saturation_soft * 0.7))
            | (red_secondary >= max(3.0, red_soft * 0.78))
            | (a_equalized >= soft_threshold - 10)
        )
    ) | (seed > 0)
    gate_mask = np.where(loose_color_gate, 255, 0).astype(np.uint8)
    adaptive_mask = cv2.bitwise_and(adaptive_mask, gate_mask)
    otsu_mask = cv2.bitwise_and(otsu_mask, gate_mask)

    support_base = cv2.bitwise_or(seed, soft_mask)
    circle_hint = _detect_circle_hint(blurred_response, support_base)
    circle_support = _build_circle_support_mask((height, width), circle_hint)

    support_kernel_size = _ensure_odd(
        int(round(max(height, width) * (0.055 if faded_profile else 0.04))),
        minimum=5,
        maximum=21,
    )
    support_kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (support_kernel_size, support_kernel_size))
    support_zone = cv2.dilate(support_base, support_kernel, iterations=1)
    if int(np.count_nonzero(circle_support)) > 0:
        support_zone = cv2.bitwise_or(support_zone, circle_support)

    hybrid_mask = cv2.bitwise_or(soft_mask, cv2.bitwise_and(adaptive_mask, support_zone))
    hybrid_mask = cv2.bitwise_or(hybrid_mask, cv2.bitwise_and(otsu_mask, support_zone))
    detail_mask = cv2.bitwise_or(balanced_mask, cv2.bitwise_and(adaptive_mask, support_zone))

    candidates: Dict[str, np.ndarray] = {
        "balanced": _cleanup_mask_components(balanced_mask, support_zone),
        "soft": _cleanup_mask_components(soft_mask, support_zone),
        "hybrid": _cleanup_mask_components(hybrid_mask, support_zone),
        "detail": _cleanup_mask_components(detail_mask, support_zone),
    }

    best_name = "balanced"
    best_mask = candidates["balanced"]
    best_score = _score_mask_quality(best_mask, blurred_response, support_zone, circle_support)

    if int(np.count_nonzero(best_mask)) <= 0:
        fallback_candidates = {
            name: candidate_mask
            for name, candidate_mask in candidates.items()
            if name != "balanced"
        }
        best_score = float("-inf")
        for name, candidate_mask in fallback_candidates.items():
            candidate_score = _score_mask_quality(candidate_mask, blurred_response, support_zone, circle_support)
            if candidate_score > best_score:
                best_score = candidate_score
                best_name = name
                best_mask = candidate_mask

    if int(np.count_nonzero(best_mask)) <= 0:
        best_mask = _cleanup_mask_components(cv2.bitwise_or(seed, soft_mask), support_zone)
        best_name = "fallback"

    return best_mask, {
        "auto_profile": "faded_red_seal" if faded_profile else "standard_red_seal",
        "auto_hue": int(auto_hue),
        "refine_variant": best_name,
        "circle_hint": [int(value) for value in circle_hint] if circle_hint else None,
        "refine_score": float(best_score),
    }


def _build_color_mask(image_bgr: np.ndarray, settings: SealExtractSettings) -> np.ndarray:
    cv2 = _lazy_cv2()
    target_bgr = np.uint8([[list(_rgb_to_bgr(settings.target_color))]])
    target_hsv = cv2.cvtColor(target_bgr, cv2.COLOR_BGR2HSV)[0, 0].astype(np.int16)
    target_lab = cv2.cvtColor(target_bgr, cv2.COLOR_BGR2LAB)[0, 0].astype(np.int16)

    hsv = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2HSV).astype(np.int16)
    lab = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2LAB).astype(np.int16)

    b_channel, g_channel, r_channel = cv2.split(image_bgr.astype(np.int16))
    channel_map = {"b": b_channel, "g": g_channel, "r": r_channel}
    selected_channel = None
    if settings.channel_mode in channel_map:
        selected_channel = settings.channel_mode
    else:
        target_rgb = _hex_to_rgb(settings.target_color)
        selected_channel = ("r", "g", "b")[int(np.argmax(np.array(target_rgb, dtype=np.int16)))]
    selected_plane = channel_map[selected_channel]
    other_planes = [plane for key, plane in channel_map.items() if key != selected_channel]
    other_max = np.maximum(other_planes[0], other_planes[1])

    hue = hsv[:, :, 0]
    saturation = hsv[:, :, 1]
    value = hsv[:, :, 2]
    hue_delta = np.minimum(np.abs(hue - target_hsv[0]), 180 - np.abs(hue - target_hsv[0]))
    hue_limit = max(6, int(round(8 + settings.tolerance * 0.55)))

    lab_delta = np.sqrt(np.sum((lab - target_lab) ** 2, axis=2))
    lab_limit = 20.0 + settings.tolerance * 2.6

    grayness = (np.maximum.reduce([r_channel, g_channel, b_channel]) - np.minimum.reduce([r_channel, g_channel, b_channel])) / np.maximum(
        1.0,
        np.maximum.reduce([r_channel, g_channel, b_channel]),
    )
    ratio_limit = 1.1 + settings.channel_ratio / 55.0
    channel_ratio = selected_plane / np.maximum(1.0, other_max)
    channel_delta = (selected_plane - other_max) / 255.0

    mask_hsv = (hue_delta <= hue_limit) & (saturation >= max(28, target_hsv[1] * 0.35)) & (value >= 25)
    mask_lab = lab_delta <= lab_limit
    mask_channel = (channel_ratio >= ratio_limit) | (channel_delta >= 0.06)
    mask_gray = grayness >= settings.gray_threshold

    if settings.extract_mode == "red":
        base_mask = mask_hsv & mask_lab & mask_channel & mask_gray
    else:
        base_mask = (
            (mask_hsv & (mask_channel | mask_lab))
            | (mask_lab & mask_channel & mask_gray)
            | ((channel_delta >= 0.11) & (saturation >= 32) & mask_gray)
        )

    mask = np.where(base_mask, 255, 0).astype(np.uint8)

    close_kernel_size = _ensure_odd(max(3, min(7, settings.fill_radius // 2 + 1)), minimum=3, maximum=7)
    close_kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (close_kernel_size, close_kernel_size))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, close_kernel, iterations=1)
    if settings.extract_mode == "smart":
        open_kernel_size = _ensure_odd(max(3, min(5, settings.fill_radius // 3 + 1)), minimum=3, maximum=5)
        open_kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (open_kernel_size, open_kernel_size))
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, open_kernel, iterations=1)

    min_area = max(36, int(mask.shape[0] * mask.shape[1] * 0.00001))
    component_count, labels, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    filtered = np.zeros_like(mask)
    for component_idx in range(1, component_count):
        area = int(stats[component_idx, cv2.CC_STAT_AREA])
        if area < min_area:
            continue
        filtered[labels == component_idx] = 255
    return filtered


def _collect_paddle_support_boxes(
    file_bytes: bytes,
    filename: str,
    page_index: int,
    mask: np.ndarray,
    scale: float,
    ocr_engine: Any,
) -> Tuple[List[Tuple[int, int, int, int]], bool, List[str]]:
    if not ocr_engine or not hasattr(ocr_engine, "recognize"):
        return [], False, []
    warnings: List[str] = []
    try:
        result = ocr_engine.recognize(file_bytes, filename, engine="standard")
    except Exception as exc:  # pragma: no cover - depends on runtime
        warnings.append(f"PaddleOCR 辅助定位失败，已回退纯 OpenCV：{exc}")
        return [], False, warnings

    lines = result.get("lines") if isinstance(result, dict) else None
    if not isinstance(lines, list) or not lines:
        return [], True, warnings

    selected: List[Tuple[int, int, int, int]] = []
    for line in lines:
        if not isinstance(line, dict):
            continue
        if int(line.get("page", 0) or 0) != page_index:
            continue
        box = _normalize_box(line.get("box") or [])
        if not box:
            continue
        scaled_box = (
            int(round(box[0] * scale)),
            int(round(box[1] * scale)),
            int(round(box[2] * scale)),
            int(round(box[3] * scale)),
        )
        if _box_mask_ratio(mask, scaled_box) >= 0.012:
            selected.append(scaled_box)
    return selected, True, warnings


def _find_candidate_groups(
    mask: np.ndarray,
    support_boxes: Sequence[Tuple[int, int, int, int]],
    *,
    max_candidates: int = 6,
) -> List[Dict[str, Any]]:
    cv2 = _lazy_cv2()
    if int(np.count_nonzero(mask)) <= 0 and support_boxes:
        merged = _merge_boxes(support_boxes)
        if merged:
            return [{"box": merged, "source": "paddleocr_text_boxes", "score": 0.0}]
        return []

    image_height, image_width = mask.shape[:2]
    image_area = float(image_height * image_width)
    min_area = max(120.0, image_area * 0.00004)
    support_union = _merge_boxes(support_boxes)
    component_count, labels, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    components: List[Dict[str, Any]] = []
    for component_idx in range(1, component_count):
        pixel_area = int(stats[component_idx, cv2.CC_STAT_AREA])
        if pixel_area < min_area:
            continue
        x = int(stats[component_idx, cv2.CC_STAT_LEFT])
        y = int(stats[component_idx, cv2.CC_STAT_TOP])
        w = int(stats[component_idx, cv2.CC_STAT_WIDTH])
        h = int(stats[component_idx, cv2.CC_STAT_HEIGHT])
        if w <= 0 or h <= 0:
            continue
        box = (x, y, x + w, y + h)
        component_mask = np.where(labels[y : y + h, x : x + w] == component_idx, 255, 0).astype(np.uint8)
        contours_info = cv2.findContours(component_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        contours = contours_info[0] if len(contours_info) == 2 else contours_info[1]
        contour = max(contours, key=cv2.contourArea) if contours else None
        circularity = 0.0
        if contour is not None:
            perimeter = float(cv2.arcLength(contour, True))
            if perimeter > 1e-3:
                contour_area = float(cv2.contourArea(contour))
                circularity = float(4.0 * math.pi * contour_area / max(1.0, perimeter * perimeter))
        components.append(
            {
                "box": box,
                "pixel_area": float(pixel_area),
                "aspect": max(w / max(1.0, h), h / max(1.0, w)),
                "density": pixel_area / max(1.0, float(w * h)),
                "circularity": circularity,
                "touches_border": _touches_border(box, image_width, image_height),
            }
        )

    if not components:
        merged = _merge_boxes(support_boxes)
        if merged:
            return [{"box": merged, "source": "paddleocr_text_boxes", "score": 0.0}]
        return []

    groups: List[Dict[str, Any]] = []
    visited: set[int] = set()

    def are_linked(box_a: Tuple[int, int, int, int], box_b: Tuple[int, int, int, int]) -> bool:
        width_a = box_a[2] - box_a[0]
        height_a = box_a[3] - box_a[1]
        width_b = box_b[2] - box_b[0]
        height_b = box_b[3] - box_b[1]
        padding = max(16, int(min(max(width_a, height_a), max(width_b, height_b)) * 0.45))
        return _boxes_intersect(
            _expand_box(box_a, padding, image_width, image_height),
            _expand_box(box_b, padding, image_width, image_height),
        )

    for index, component in enumerate(components):
        if index in visited:
            continue
        queue = [index]
        visited.add(index)
        member_indexes = [index]
        while queue:
            current = queue.pop()
            current_box = components[current]["box"]
            for other_index, other_component in enumerate(components):
                if other_index in visited:
                    continue
                if are_linked(current_box, other_component["box"]):
                    visited.add(other_index)
                    queue.append(other_index)
                    member_indexes.append(other_index)
        member_components = [components[item] for item in member_indexes]
        merged_box = _merge_boxes([item["box"] for item in member_components])
        if not merged_box:
            continue
        pixel_area = float(sum(item["pixel_area"] for item in member_components))
        box_area = float(max(1, (merged_box[2] - merged_box[0]) * (merged_box[3] - merged_box[1])))
        avg_circularity = float(sum(item["circularity"] * item["pixel_area"] for item in member_components) / max(1.0, pixel_area))
        avg_aspect = float(sum(item["aspect"] * item["pixel_area"] for item in member_components) / max(1.0, pixel_area))
        groups.append(
            {
                "box": merged_box,
                "pixel_area": pixel_area,
                "density": pixel_area / box_area,
                "circularity": avg_circularity,
                "aspect": avg_aspect,
                "touches_border": any(item["touches_border"] for item in member_components),
                "components": member_components,
            }
        )

    if not groups:
        merged = _merge_boxes(support_boxes)
        if merged:
            return [{"box": merged, "source": "paddleocr_text_boxes", "score": 0.0}]
        return []

    non_border_available = any(not group["touches_border"] for group in groups)
    scored_groups: List[Dict[str, Any]] = []

    for group in groups:
        box = group["box"]
        width = max(1, box[2] - box[0])
        height = max(1, box[3] - box[1])
        box_area_ratio = (width * height) / image_area
        pixel_area_ratio = group["pixel_area"] / image_area
        elongation = max(width / max(1.0, height), height / max(1.0, width))
        support_overlap = _box_iou(box, support_union) if support_union else 0.0
        support_near = bool(support_union and _boxes_intersect(_expand_box(box, 28, image_width, image_height), support_union))

        score = 0.0
        score += min(pixel_area_ratio * 120.0, 2.8)
        score += group["density"] * 2.4
        score += max(0.0, 1.2 - abs(elongation - 1.0) * 0.85)
        score += group["circularity"] * 1.5

        if support_overlap > 0:
            score += 7.5 * support_overlap
            source = "paddleocr_text_boxes+opencv_color_mask"
        elif support_near:
            score += 1.2
            source = "paddleocr_text_boxes+opencv_color_mask"
        else:
            source = "opencv_color_mask"

        if group["touches_border"]:
            score -= 2.5 if non_border_available and support_overlap <= 0 else 0.8
        if elongation > 2.6:
            score -= min(4.8, (elongation - 2.6) * 2.2)
        if box_area_ratio > 0.12:
            score -= min(4.2, (box_area_ratio - 0.12) * 32.0)
        if group["density"] < 0.06:
            score -= 0.9

        scored_groups.append(
            {
                **group,
                "source": source,
                "score": float(score),
            }
        )

    if not scored_groups:
        merged = _merge_boxes(support_boxes)
        if merged:
            return [{"box": merged, "source": "paddleocr_text_boxes", "score": 0.0}]
        return []

    scored_groups.sort(key=lambda item: float(item.get("score") or 0.0), reverse=True)
    deduped: List[Dict[str, Any]] = []
    for candidate in scored_groups:
        box = candidate["box"]
        overlaps_existing = any(
            _box_iou(box, existing["box"]) >= 0.42
            or (
                _boxes_intersect(box, existing["box"])
                and _box_iou(_expand_box(box, 10, image_width, image_height), _expand_box(existing["box"], 10, image_width, image_height)) >= 0.3
            )
            for existing in deduped
        )
        if overlaps_existing:
            continue
        deduped.append(candidate)
        if len(deduped) >= max_candidates:
            break

    return deduped


def _find_best_candidate(
    mask: np.ndarray,
    support_boxes: Sequence[Tuple[int, int, int, int]],
) -> Optional[Tuple[Tuple[int, int, int, int], str]]:
    candidates = _find_candidate_groups(mask, support_boxes, max_candidates=1)
    if not candidates:
        return None
    return candidates[0]["box"], str(candidates[0].get("source") or "opencv_color_mask")


def _render_highres_detail_output(
    crop_bgr: np.ndarray,
    hard_mask: np.ndarray,
    seed_mask: np.ndarray,
    settings: SealExtractSettings,
) -> Tuple[np.ndarray, Dict[str, Any]]:
    cv2 = _lazy_cv2()
    crop_binary = np.where(hard_mask > 0, 255, 0).astype(np.uint8)
    seed_binary = np.where(seed_mask > 0, 255, 0).astype(np.uint8)
    if crop_bgr.size == 0 or crop_binary.size == 0:
        target_bgr = _rgb_to_bgr(settings.target_color)
        fallback = np.zeros((max(1, crop_binary.shape[0]), max(1, crop_binary.shape[1]), 4), dtype=np.uint8)
        fallback[:, :, 0] = target_bgr[0]
        fallback[:, :, 1] = target_bgr[1]
        fallback[:, :, 2] = target_bgr[2]
        fallback[:, :, 3] = crop_binary
        return fallback, {"render_mode": "hard_mask_fallback", "render_scale": 1}

    height, width = crop_bgr.shape[:2]
    longest_side = max(height, width)
    render_scale = 3 if longest_side <= 360 else 2 if longest_side <= 680 else 1
    target_bgr = np.array(_rgb_to_bgr(settings.target_color), dtype=np.uint8)

    if render_scale > 1:
        render_bgr = cv2.resize(crop_bgr, (width * render_scale, height * render_scale), interpolation=cv2.INTER_CUBIC)
        render_hard = cv2.resize(crop_binary, (width * render_scale, height * render_scale), interpolation=cv2.INTER_NEAREST)
        render_seed = cv2.resize(seed_binary, (width * render_scale, height * render_scale), interpolation=cv2.INTER_NEAREST)
    else:
        render_bgr = crop_bgr.copy()
        render_hard = crop_binary
        render_seed = seed_binary

    support_mask = cv2.bitwise_or(render_hard, render_seed)
    if int(np.count_nonzero(support_mask)) <= 0:
        support_mask = render_hard

    if int(np.count_nonzero(support_mask)) <= 0:
        output = np.zeros((render_hard.shape[0], render_hard.shape[1], 4), dtype=np.uint8)
        output[:, :, 0] = target_bgr[0]
        output[:, :, 1] = target_bgr[1]
        output[:, :, 2] = target_bgr[2]
        output[:, :, 3] = render_hard
        return output, {"render_mode": "hard_mask_fallback", "render_scale": int(render_scale)}

    support_kernel_size = _ensure_odd(3 + render_scale * 2, minimum=5, maximum=11)
    support_kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (support_kernel_size, support_kernel_size))
    extended_support = cv2.dilate(support_mask, support_kernel, iterations=1)

    lab = cv2.cvtColor(render_bgr, cv2.COLOR_BGR2LAB)
    hsv = cv2.cvtColor(render_bgr, cv2.COLOR_BGR2HSV)
    b_channel, g_channel, r_channel = cv2.split(render_bgr.astype(np.float32))
    a_channel = lab[:, :, 1].astype(np.float32)
    saturation = hsv[:, :, 1].astype(np.float32)
    red_signal = np.clip(r_channel - ((g_channel + b_channel) / 2.0), 0.0, 255.0)

    background_sigma = 2.2 * float(render_scale)
    a_background = cv2.GaussianBlur(a_channel, (0, 0), sigmaX=background_sigma, sigmaY=background_sigma)
    red_background = cv2.GaussianBlur(red_signal, (0, 0), sigmaX=background_sigma, sigmaY=background_sigma)
    detail_signal = np.clip(
        (a_channel - a_background + 18.0) * 0.64
        + (red_signal - red_background + 18.0) * 0.9
        + saturation * 0.16,
        0.0,
        255.0,
    ).astype(np.float32)

    support_values = detail_signal[extended_support > 0]
    if support_values.size < 32:
        output = np.zeros((render_hard.shape[0], render_hard.shape[1], 4), dtype=np.uint8)
        output[:, :, 0] = target_bgr[0]
        output[:, :, 1] = target_bgr[1]
        output[:, :, 2] = target_bgr[2]
        output[:, :, 3] = render_hard
        return output, {"render_mode": "hard_mask_fallback", "render_scale": int(render_scale)}

    lower = float(np.percentile(support_values, 24))
    upper = float(np.percentile(support_values, 99.6))
    if upper <= lower + 1.0:
        output = np.zeros((render_hard.shape[0], render_hard.shape[1], 4), dtype=np.uint8)
        output[:, :, 0] = target_bgr[0]
        output[:, :, 1] = target_bgr[1]
        output[:, :, 2] = target_bgr[2]
        output[:, :, 3] = render_hard
        return output, {"render_mode": "hard_mask_fallback", "render_scale": int(render_scale)}

    detail_alpha = np.clip((detail_signal - lower) / max(1.0, upper - lower), 0.0, 1.0)
    detail_alpha = np.power(detail_alpha, 0.84)
    alpha = np.clip(detail_alpha * 255.0, 0.0, 255.0).astype(np.uint8)
    alpha = cv2.bitwise_and(alpha, extended_support)
    alpha = np.where(alpha > 10, alpha, 0).astype(np.uint8)
    render_mode = "highres_detail_alpha"

    support_ys, support_xs = np.where(support_mask > 0)
    if support_xs.size >= 48 and support_ys.size >= 48:
        center, radius = cv2.minEnclosingCircle(
            np.column_stack((support_xs.astype(np.float32), support_ys.astype(np.float32)))
        )
        center_x = float(center[0])
        center_y = float(center[1])
        radius = float(radius)
        if radius > 0.0:
            grid_y, grid_x = np.ogrid[: render_hard.shape[0], : render_hard.shape[1]]
            distance = np.sqrt((grid_x - center_x) ** 2 + (grid_y - center_y) ** 2)
            angle_map = (np.arctan2(grid_y - center_y, grid_x - center_x) + 2.0 * math.pi) % (2.0 * math.pi)
            annulus_mask = (distance >= radius * 0.52) & (distance <= radius * 0.88)
            seed_zone = cv2.dilate(
                render_seed,
                cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (_ensure_odd(9 + render_scale * 2, minimum=9, maximum=15),) * 2),
                iterations=1,
            ) > 0
            weak_zone = cv2.dilate(
                np.where(alpha >= 20, 255, 0).astype(np.uint8),
                cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (_ensure_odd(7 + render_scale * 2, minimum=7, maximum=13),) * 2),
                iterations=1,
            ) > 0
            annulus_support = annulus_mask & ((saturation >= 9.0) | (red_signal >= 4.0)) & (seed_zone | weak_zone)
            annulus_values = detail_signal[annulus_support]
            if annulus_values.size >= 48:
                sector_count = 72
                sector_width = 2.0 * math.pi / float(sector_count)
                sector_boost = np.zeros_like(alpha)
                for sector_index in range(sector_count):
                    sector_center = (sector_index + 0.5) * sector_width
                    sector_delta = np.abs((angle_map - sector_center + math.pi) % (2.0 * math.pi) - math.pi)
                    sector_mask = annulus_support & (sector_delta <= sector_width * 0.95)
                    sector_values = detail_signal[sector_mask]
                    if sector_values.size < 28:
                        continue
                    sector_lower = float(np.percentile(sector_values, 50))
                    sector_upper = float(np.percentile(sector_values, 99.0))
                    if sector_upper <= sector_lower + 1.0:
                        continue
                    local_boost = np.clip(
                        (detail_signal - sector_lower) / max(1.0, sector_upper - sector_lower),
                        0.0,
                        1.0,
                    )
                    local_boost = np.power(local_boost, 0.72)
                    local_boost = np.clip(local_boost * 255.0, 0.0, 255.0).astype(np.uint8)
                    local_boost = np.where(sector_mask, local_boost, 0).astype(np.uint8)
                    local_boost = np.where(local_boost >= 128, local_boost, 0).astype(np.uint8)
                    sector_boost = np.maximum(sector_boost, local_boost)

                if int(np.count_nonzero(sector_boost)) > 0:
                    component_count, labels, stats, _ = cv2.connectedComponentsWithStats(
                        np.where(sector_boost > 0, 255, 0).astype(np.uint8),
                        connectivity=8,
                    )
                    filtered_boost = np.zeros_like(sector_boost)
                    min_boost_area = max(18, int(8 * render_scale))
                    for component_idx in range(1, component_count):
                        area = int(stats[component_idx, cv2.CC_STAT_AREA])
                        if area < min_boost_area:
                            continue
                        filtered_boost[labels == component_idx] = sector_boost[labels == component_idx]

                    if int(np.count_nonzero(filtered_boost)) > 0:
                        alpha = np.maximum(alpha, filtered_boost)
                        render_mode = "highres_detail_alpha_sector_boost"

    if int(np.count_nonzero(alpha)) <= 0:
        output = np.zeros((render_hard.shape[0], render_hard.shape[1], 4), dtype=np.uint8)
        output[:, :, 0] = target_bgr[0]
        output[:, :, 1] = target_bgr[1]
        output[:, :, 2] = target_bgr[2]
        output[:, :, 3] = render_hard
        return output, {"render_mode": "hard_mask_fallback", "render_scale": int(render_scale)}

    target_layer = np.zeros_like(render_bgr)
    target_layer[:, :, 0] = target_bgr[0]
    target_layer[:, :, 1] = target_bgr[1]
    target_layer[:, :, 2] = target_bgr[2]

    output = np.zeros((alpha.shape[0], alpha.shape[1], 4), dtype=np.uint8)
    output[:, :, 0:3] = target_layer
    output[:, :, 3] = alpha
    return output, {"render_mode": render_mode, "render_scale": int(render_scale)}


def _build_output(
    image_bgr: np.ndarray,
    mask: np.ndarray,
    candidate_box: Tuple[int, int, int, int],
    settings: SealExtractSettings,
) -> Tuple[bytes, Dict[str, Any]]:
    cv2 = _lazy_cv2()
    image_height, image_width = image_bgr.shape[:2]
    support_box = _clip_box(candidate_box, image_width, image_height)
    cleaned_mask = _remove_border_line_noise(mask)
    if int(np.count_nonzero(cleaned_mask)) <= 0:
        cleaned_mask = np.where(mask > 0, 255, 0).astype(np.uint8)
    if int(np.count_nonzero(cleaned_mask)) <= 0:
        raise RuntimeError("未检测到足够清晰的印章前景，请调高容差或更换更清晰的图片。")

    focused_seed = _keep_components_near_box(cleaned_mask, support_box)
    if int(np.count_nonzero(focused_seed)) <= 0:
        focused_seed = cleaned_mask

    focus_size = max(support_box[2] - support_box[0], support_box[3] - support_box[1], 1)
    roi_box = _square_box_around(
        support_box,
        image_width,
        image_height,
        padding=max(20, int(round(focus_size * 0.34))),
        min_side=max(180, int(round(focus_size * 1.72))),
    )
    rx1, ry1, rx2, ry2 = roi_box
    roi_bgr = image_bgr[ry1:ry2, rx1:rx2]
    roi_seed = focused_seed[ry1:ry2, rx1:rx2]
    if roi_bgr.size == 0 or roi_seed.size == 0:
        raise RuntimeError("印章定位框无效，无法完成局部精修。")

    refined_local, refine_meta = _refine_crop_mask(roi_bgr, roi_seed, settings)
    seed_clean = _cleanup_mask_components(np.where(roi_seed > 0, 255, 0).astype(np.uint8), np.where(roi_seed > 0, 255, 0).astype(np.uint8))
    response_map = _build_page_response(roi_bgr)
    seed_quality = _score_mask_quality(seed_clean, response_map, roi_seed, None)
    seed_based_result = False
    if refined_local.size == 0 or int(np.count_nonzero(refined_local)) == 0:
        refined_local = seed_clean
        refine_meta["guard_mode"] = "seed_only"
        seed_based_result = True
    else:
        anchor_kernel_size = _ensure_odd(int(round(max(roi_bgr.shape[:2]) * 0.028)), minimum=3, maximum=9)
        anchor_kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (anchor_kernel_size, anchor_kernel_size))
        seed_anchor = cv2.dilate(np.where(roi_seed > 0, 255, 0).astype(np.uint8), anchor_kernel, iterations=1)
        anchored_local = cv2.bitwise_and(refined_local, seed_anchor)
        if int(np.count_nonzero(anchored_local)) > 0 and int(np.count_nonzero(anchored_local)) >= int(np.count_nonzero(refined_local)) * 0.18:
            refined_local = anchored_local
            refine_meta["guard_mode"] = "seed_anchor"
        else:
            refine_meta["guard_mode"] = "local_refine"

    final_local = _cleanup_mask_components(refined_local, np.where(roi_seed > 0, 255, 0).astype(np.uint8))
    refined_quality = _score_mask_quality(final_local, response_map, roi_seed, None) if int(np.count_nonzero(final_local)) > 0 else float("-inf")
    if int(np.count_nonzero(final_local)) <= 0:
        final_local = seed_clean
        refine_meta["guard_mode"] = "seed_fallback"
        seed_based_result = True

    local_bbox = _mask_bbox(final_local)
    if local_bbox:
        lx1, ly1, lx2, ly2 = local_bbox
        local_area = max(1, (lx2 - lx1) * (ly2 - ly1))
        local_fill_ratio = float(np.count_nonzero(final_local)) / float(local_area)
        if local_fill_ratio >= 0.58:
            seed_candidate = _cleanup_mask_components(roi_seed, np.where(roi_seed > 0, 255, 0).astype(np.uint8))
            seed_bbox = _mask_bbox(seed_candidate)
            if seed_bbox:
                sx1, sy1, sx2, sy2 = seed_bbox
                seed_area = max(1, (sx2 - sx1) * (sy2 - sy1))
                seed_fill_ratio = float(np.count_nonzero(seed_candidate)) / float(seed_area)
                if seed_fill_ratio + 0.06 < local_fill_ratio and int(np.count_nonzero(seed_candidate)) >= max(24, int(np.count_nonzero(final_local) * 0.42)):
                    final_local = seed_candidate
                    local_bbox = seed_bbox
                    refine_meta["guard_mode"] = "solid_blob_seed_fallback"
                    refined_quality = seed_quality
                    seed_based_result = True

    final_bbox = _mask_bbox(final_local)
    if final_bbox:
        fx1, fy1, fx2, fy2 = final_bbox
        bbox_area = max(1, (fx2 - fx1) * (fy2 - fy1))
        bbox_fill_ratio = float(np.count_nonzero(final_local)) / float(bbox_area)
        roi_area = float(max(1, final_local.shape[0] * final_local.shape[1]))
        bbox_area_ratio = bbox_area / roi_area
        if (
            seed_quality >= refined_quality + 0.85
            or (bbox_fill_ratio >= 0.52 and seed_quality >= refined_quality - 0.1)
            or (bbox_area_ratio >= 0.74 and seed_quality >= refined_quality - 0.25)
        ):
            final_local = seed_clean
            refine_meta["guard_mode"] = "seed_quality_fallback"
            refined_quality = seed_quality
            seed_based_result = True

    if seed_based_result and int(np.count_nonzero(final_local)) > 0:
        thin_kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
        thinned_seed = cv2.erode(final_local, thin_kernel, iterations=1)
        thinned_pixels = int(np.count_nonzero(thinned_seed))
        thin_quality = _score_mask_quality(thinned_seed, response_map, roi_seed, None) if thinned_pixels > 0 else float("-inf")
        if (
            thinned_pixels >= int(np.count_nonzero(final_local)) * 0.72
            and thin_quality >= refined_quality - 0.22
        ):
            final_local = thinned_seed
            refined_quality = thin_quality
            refine_meta["guard_mode"] = "seed_thin_refine"

    if int(np.count_nonzero(final_local)) <= 0:
        raise RuntimeError("未检测到印章邻域前景，无法按印章框截取。")

    localized_box = _mask_bbox(final_local)
    localized_box_global = (
        rx1 + localized_box[0],
        ry1 + localized_box[1],
        rx1 + localized_box[2],
        ry1 + localized_box[3],
    ) if localized_box else support_box
    refine_meta["localized_box"] = [int(value) for value in localized_box_global]
    refine_meta["localized_source"] = "full_mask_roi_refine"
    refine_meta["seed_score"] = float(seed_quality)
    refine_meta["final_score"] = float(refined_quality)

    alpha = np.where(final_local > 0, 255, 0).astype(np.uint8)
    edge_sigma = 0.26 if str(refine_meta.get("guard_mode") or "").strip() == "seed_thin_refine" else 0.4
    soft_mask = cv2.GaussianBlur(alpha, (0, 0), sigmaX=edge_sigma, sigmaY=edge_sigma)
    edge_cap = 28 if str(refine_meta.get("guard_mode") or "").strip() == "seed_thin_refine" else 42
    alpha = np.where(alpha > 0, 255, np.minimum(soft_mask, edge_cap)).astype(np.uint8)
    alpha = np.where(alpha > 8, alpha, 0).astype(np.uint8)

    if settings.crop_mode == "full":
        crop_x1, crop_y1, crop_x2, crop_y2 = 0, 0, alpha.shape[1], alpha.shape[0]
    else:
        alpha_bbox = _mask_bbox(alpha, threshold=10)
        if alpha_bbox:
            padding = max(8, settings.fill_radius + 5)
            crop_x1 = max(0, alpha_bbox[0] - padding)
            crop_y1 = max(0, alpha_bbox[1] - padding)
            crop_x2 = min(alpha.shape[1], alpha_bbox[2] + padding)
            crop_y2 = min(alpha.shape[0], alpha_bbox[3] + padding)
        else:
            crop_x1, crop_y1, crop_x2, crop_y2 = 0, 0, alpha.shape[1], alpha.shape[0]

    x1 = rx1 + crop_x1
    y1 = ry1 + crop_y1
    x2 = rx1 + crop_x2
    y2 = ry1 + crop_y2

    crop_bgr = roi_bgr[crop_y1:crop_y2, crop_x1:crop_x2]
    crop_hard_mask = final_local[crop_y1:crop_y2, crop_x1:crop_x2]
    crop_seed_mask = roi_seed[crop_y1:crop_y2, crop_x1:crop_x2]
    output, render_meta = _render_highres_detail_output(crop_bgr, crop_hard_mask, crop_seed_mask, settings)

    ok, encoded = cv2.imencode(".png", output)
    if not ok:
        raise RuntimeError("透明电子章 PNG 编码失败。")

    result_bytes = encoded.tobytes()
    pixel_count = int(np.count_nonzero(output[:, :, 3] > 10))
    meta = {
        "crop_box": [int(x1), int(y1), int(x2), int(y2)],
        "output_width": int(output.shape[1]),
        "output_height": int(output.shape[0]),
        "pixel_count": pixel_count,
        "result_size_bytes": len(result_bytes),
        "crop_strategy": "full_mask_then_paddle_crop",
        "roi_box": [int(rx1), int(ry1), int(rx2), int(ry2)],
        **render_meta,
        **refine_meta,
    }
    return result_bytes, meta


def extract_transparent_seal(
    file_bytes: bytes,
    filename: str,
    settings: Optional[Dict[str, Any]] = None,
    *,
    ocr_engine: Any = None,
) -> Dict[str, Any]:
    cv2 = _lazy_cv2()
    if not file_bytes:
        raise RuntimeError("上传文件为空。")

    normalized = SealExtractSettings.from_raw(settings)
    pages = _load_pages(file_bytes, filename)
    if not pages:
        raise RuntimeError("无法解析当前文件，请上传 JPG、PNG、WebP 或可识别的 PDF。")

    warnings: List[str] = []
    candidate_payloads: List[Dict[str, Any]] = []

    for page_index, page_bgr in enumerate(pages):
        resized_bgr, scale = _resize_for_processing(page_bgr)
        processing_mask = _build_color_mask(resized_bgr, normalized)
        cleaned_processing_mask = _remove_border_line_noise(processing_mask)
        full_mask = _build_color_mask(page_bgr, normalized)
        cleaned_full_mask = _remove_border_line_noise(full_mask)
        support_boxes: List[Tuple[int, int, int, int]] = []
        paddle_used = False
        page_candidates: List[Dict[str, Any]] = []

        def boxes_similar(box_a: Tuple[int, int, int, int], box_b: Tuple[int, int, int, int]) -> bool:
            return _box_iou(box_a, box_b) >= 0.38 or (
                _boxes_intersect(box_a, box_b)
                and _box_iou(
                    _expand_box(box_a, 10, page_bgr.shape[1], page_bgr.shape[0]),
                    _expand_box(box_b, 10, page_bgr.shape[1], page_bgr.shape[0]),
                )
                >= 0.28
            )

        def register_candidate(
            initial_box: Tuple[int, int, int, int],
            detection_source: str,
            *,
            localization_meta: Optional[Dict[str, Any]] = None,
            localized_box: Optional[Tuple[int, int, int, int]] = None,
            candidate_score: float = 0.0,
        ) -> None:
            clipped_initial_box = _clip_box(initial_box, page_bgr.shape[1], page_bgr.shape[0])
            if clipped_initial_box[2] <= clipped_initial_box[0] or clipped_initial_box[3] <= clipped_initial_box[1]:
                return
            if any(boxes_similar(clipped_initial_box, item["initial_box"]) for item in page_candidates):
                return

            resolved_localization_meta = dict(localization_meta or {})
            resolved_localized_box = localized_box
            if resolved_localized_box is None:
                resolved_localized_box, fallback_meta = _localize_stamp_box(page_bgr, cleaned_full_mask, clipped_initial_box)
                resolved_localization_meta = fallback_meta

            stamp_locator = str(resolved_localization_meta.get("stamp_locator") or "").strip().lower()
            output_anchor_box = resolved_localized_box
            if not stamp_locator.startswith("paddle_seal_pipeline"):
                output_anchor_box = clipped_initial_box

            page_candidates.append(
                {
                    "initial_box": clipped_initial_box,
                    "localized_box": _clip_box(output_anchor_box, page_bgr.shape[1], page_bgr.shape[0]),
                    "detection_source": detection_source,
                    "localization_meta": resolved_localization_meta,
                    "candidate_score": float(candidate_score),
                }
            )

        if normalized.prefer_paddle:
            paddle_box, pipeline_meta = _locate_stamp_with_paddle_pipeline(page_bgr)
            if paddle_box:
                clipped_paddle_box = _clip_box(paddle_box, page_bgr.shape[1], page_bgr.shape[0])
                register_candidate(
                    clipped_paddle_box,
                    str(pipeline_meta.get("stamp_locator") or "paddle_seal_pipeline"),
                    localization_meta=dict(pipeline_meta),
                    localized_box=clipped_paddle_box,
                    candidate_score=1000.0,
                )
                paddle_used = True
            else:
                pipeline_warning = str(pipeline_meta.get("stamp_warning") or "").strip()
                if pipeline_warning:
                    warnings.append(f"PaddleOCR 印章定位失败，已回退颜色定位：{pipeline_warning}")
            support_boxes, paddle_support_used, paddle_warnings = _collect_paddle_support_boxes(
                file_bytes,
                filename,
                page_index,
                processing_mask,
                scale,
                ocr_engine,
            )
            paddle_used = paddle_used or paddle_support_used
            warnings.extend(paddle_warnings)

        candidate_source_mask = cleaned_processing_mask if int(np.count_nonzero(cleaned_processing_mask)) > 0 else processing_mask
        scaled_candidates = _find_candidate_groups(candidate_source_mask, support_boxes, max_candidates=8)
        for candidate in scaled_candidates:
            candidate_box = candidate["box"]
            full_candidate_box = (
                int(round(candidate_box[0] / scale)),
                int(round(candidate_box[1] / scale)),
                int(round(candidate_box[2] / scale)),
                int(round(candidate_box[3] / scale)),
            )
            register_candidate(
                full_candidate_box,
                str(candidate.get("source") or "opencv_color_mask"),
                candidate_score=float(candidate.get("score") or 0.0),
            )

        if not page_candidates:
            continue

        page_candidates.sort(
            key=lambda item: (
                -float(item.get("candidate_score") or 0.0),
                int(item["initial_box"][1]),
                int(item["initial_box"][0]),
            )
        )

        for page_candidate_index, page_candidate in enumerate(page_candidates):
            try:
                result_png, output_meta = _build_output(
                    page_bgr,
                    cleaned_full_mask,
                    page_candidate["localized_box"],
                    normalized,
                )
            except RuntimeError as exc:
                warnings.append(f"第 {page_index + 1} 页候选印章 {page_candidate_index + 1} 提取失败，已跳过：{exc}")
                continue

            candidate_payloads.append(
                {
                    "result_png": result_png,
                    "page_index": int(page_index),
                    "source_width": int(page_bgr.shape[1]),
                    "source_height": int(page_bgr.shape[0]),
                    "bbox": [int(value) for value in page_candidate["localized_box"]],
                    "initial_bbox": [int(value) for value in page_candidate["initial_box"]],
                    "detection_source": page_candidate["detection_source"],
                    "paddle_used": bool(paddle_used),
                    "ocr_support_box_count": int(len(support_boxes)),
                    "_page_sort_y": int(page_candidate["initial_box"][1]),
                    "_page_sort_x": int(page_candidate["initial_box"][0]),
                    **page_candidate["localization_meta"],
                    **output_meta,
                }
            )

    if not candidate_payloads:
        raise RuntimeError("未检测到印章区域，请尝试提高容差、切换图片或改用仅保留红色模式。")

    candidate_payloads.sort(
        key=lambda item: (
            int(item.get("page_index") or 0),
            int(item.get("_page_sort_y") or 0),
            int(item.get("_page_sort_x") or 0),
        )
    )

    items: List[Dict[str, Any]] = []
    for candidate_index, payload in enumerate(candidate_payloads):
        item_payload = dict(payload)
        item_payload.pop("_page_sort_y", None)
        item_payload.pop("_page_sort_x", None)
        item_payload["candidate_index"] = int(candidate_index)
        item_payload["candidate_label"] = f"印章 {candidate_index + 1}"
        items.append(item_payload)

    selected_index = 0
    selected_payload = dict(items[selected_index])
    result_png = selected_payload["result_png"]
    selected_payload["item_count"] = int(len(items))
    selected_payload["selected_index"] = int(selected_index)
    selected_payload["items"] = items
    selected_payload["warnings"] = warnings[:5]
    return {
        "result_png": result_png,
        **selected_payload,
    }
