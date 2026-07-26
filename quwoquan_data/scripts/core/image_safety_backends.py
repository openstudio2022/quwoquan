"""CV and OCR backends for image safety assessment."""
from __future__ import annotations
import struct
import zlib
from pathlib import Path
from core.image_decode import probe_image_path
from core.image_safety import (
    COPYRIGHT_SYMBOL_TERMS, OCR_MAX_PIXELS, OCR_TIMEOUT_SECONDS,
    RIGHTS_CONTEXT_TERMS, WATERMARK_TERMS, _CV_OK, _HANDLE_RE, _HASH_OK,
    _OCR_MIN_CONF, _PLACEHOLDER_MAX_EDGE_DELTA, _ocr_available,
)
try:
    import cv2  # type: ignore
except Exception:
    cv2 = None
try:
    from PIL import Image  # type: ignore
except Exception:
    Image = None

def _detect_faces(path: Path) -> int:
    if not _CV_OK:
        return -1
    img = cv2.imread(str(path))
    if img is None:
        return -1
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
    cascade = cv2.CascadeClassifier(cascade_path)
    if cascade.empty():
        return -1
    min_face = max(48, round(min(gray.shape[:2]) * 0.08))
    candidates = cascade.detectMultiScale(
        gray,
        scaleFactor=1.12,
        minNeighbors=8,
        minSize=(min_face, min_face),
    )
    eye_path = cv2.data.haarcascades + "haarcascade_eye_tree_eyeglasses.xml"
    eye_cascade = cv2.CascadeClassifier(eye_path)
    if eye_cascade.empty():
        return -1
    confirmed = 0
    for x, y, width, height in candidates:
        upper_face = gray[y:y + max(1, round(height * 0.65)), x:x + width]
        eyes = eye_cascade.detectMultiScale(
            upper_face,
            scaleFactor=1.1,
            minNeighbors=5,
            minSize=(max(12, width // 8), max(8, height // 10)),
        )
        if len(eyes) > 0:
            confirmed += 1
    return confirmed

def _image_dimensions(path: Path) -> tuple[int, int] | None:
    probe = probe_image_path(path)
    return (probe.width, probe.height) if probe.succeeded else None

def _ocr_text_and_ratio(path: Path) -> tuple[str, float, bool]:
    """返回 (ocr_text, text_area_ratio, ocr_ran)。ocr_ran=False 表示未能跑 OCR。"""
    if not _ocr_available() or not _CV_OK:
        return "", 0.0, False
    import pytesseract  # type: ignore

    img = cv2.imread(str(path))
    if img is None:
        return "", 0.0, False
    h, w = img.shape[:2]
    total_pixels = max(1, h * w)
    if total_pixels > OCR_MAX_PIXELS:
        scale = (float(OCR_MAX_PIXELS) / float(total_pixels)) ** 0.5
        img = cv2.resize(
            img,
            (max(1, int(w * scale)), max(1, int(h * scale))),
            interpolation=cv2.INTER_AREA,
        )
        h, w = img.shape[:2]
    total = float(max(1, h * w))
    rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    try:
        data = pytesseract.image_to_data(
            rgb,
            lang=_ocr_lang(),
            output_type=pytesseract.Output.DICT,
            timeout=OCR_TIMEOUT_SECONDS,
        )
    except Exception:
        return "", 0.0, False
    words: list[str] = []
    text_area = 0.0
    n = len(data.get("text", []))
    for i in range(n):
        conf_raw = data["conf"][i]
        try:
            conf = float(conf_raw)
        except (TypeError, ValueError):
            conf = -1.0
        token = str(data["text"][i]).strip()
        if not token or conf < _OCR_MIN_CONF:
            continue
        words.append(token)
        text_area += float(data["width"][i]) * float(data["height"][i])
    return " ".join(words), min(1.0, text_area / total), True

def _ocr_lang() -> str:
    try:
        import pytesseract  # type: ignore

        langs = set(pytesseract.get_languages(config=""))
    except Exception:
        return "eng"
    if "chi_sim" in langs:
        return "chi_sim+eng" if "eng" in langs else "chi_sim"
    return "eng"

def _has_watermark(ocr_text: str) -> bool:
    if not ocr_text:
        return False
    lowered = ocr_text.lower()
    for term in WATERMARK_TERMS:
        if term.lower() in lowered:
            return True
    # OCR often misreads scenic signboards, exhibit plaques, currency marks, or
    # punctuation as a bare copyright symbol. A symbol alone is not a publish
    # blocker; it becomes a watermark/copyright signal only with rights context.
    if any(term in lowered for term in COPYRIGHT_SYMBOL_TERMS) and any(
        term.lower() in lowered for term in RIGHTS_CONTEXT_TERMS
    ):
        return True
    return bool(_HANDLE_RE.search(ocr_text))

def _png_rgb_rows(path: Path) -> tuple[int, int, list[bytes]] | None:
    data = path.read_bytes()
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        return None
    pos = 8
    width = height = 0
    idat = bytearray()
    color_type = -1
    bit_depth = -1
    while pos + 8 <= len(data):
        length = struct.unpack(">I", data[pos:pos + 4])[0]
        kind = data[pos + 4:pos + 8]
        payload = data[pos + 8:pos + 8 + length]
        pos += 12 + length
        if kind == b"IHDR":
            width, height, bit_depth, color_type = struct.unpack(">IIBB", payload[:10])
        elif kind == b"IDAT":
            idat.extend(payload)
        elif kind == b"IEND":
            break
    if width <= 0 or height <= 0 or bit_depth != 8 or color_type != 2:
        return None
    try:
        raw = zlib.decompress(bytes(idat))
    except Exception:
        return None
    stride = width * 3
    rows: list[bytes] = []
    offset = 0
    prev = bytearray(stride)
    for _ in range(height):
        if offset >= len(raw):
            return None
        filter_type = raw[offset]
        offset += 1
        row = bytearray(raw[offset:offset + stride])
        offset += stride
        if len(row) != stride:
            return None
        if filter_type == 1:
            for i in range(stride):
                row[i] = (row[i] + (row[i - 3] if i >= 3 else 0)) & 0xFF
        elif filter_type == 2:
            for i in range(stride):
                row[i] = (row[i] + prev[i]) & 0xFF
        elif filter_type != 0:
            return None
        rows.append(bytes(row))
        prev = row
    return width, height, rows

def _low_texture_placeholder(path: Path) -> bool:
    parsed = _png_rgb_rows(path)
    if parsed is None:
        return False
    width, height, rows = parsed
    if width * height < 10000:
        return False
    total_delta = 0
    samples = 0
    for y in range(0, height, max(1, height // 60)):
        row = rows[y]
        for x in range(1, width, max(1, width // 80)):
            i = x * 3
            j = (x - 1) * 3
            total_delta += abs(row[i] - row[j]) + abs(row[i + 1] - row[j + 1]) + abs(row[i + 2] - row[j + 2])
            samples += 3
    if samples == 0:
        return False
    return (total_delta / samples) <= _PLACEHOLDER_MAX_EDGE_DELTA

def is_low_texture_placeholder_graphic(path: str | Path) -> bool:
    return _low_texture_placeholder(Path(path))
