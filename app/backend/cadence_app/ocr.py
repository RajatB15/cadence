"""On-device text recognition for class screenshots. Nothing leaves the machine running Cadence.

Apple Vision (the engine behind Live Text) on a Mac; the Tesseract command-line tool elsewhere (the Linux server:
`apt install tesseract-ocr`). Vision is preferred when both exist.
"""

from __future__ import annotations

import io
import shutil
import subprocess

MAX_IMAGE_BYTES = 15 * 1024 * 1024
TESSERACT_TIMEOUT_S = 60
FULL_EDGE = 1800  # long edge of the image that is read
PROBE_EDGE = 900  # long edge of the copy used to pick the rotation
VISION_ORIENTATIONS = (1, 6, 8, 3)
WORD_CONFIDENCE = 80
UPRIGHT_ENOUGH = 8  # real words in the upright read above which the page is taken as it is


def _has_vision() -> bool:
    try:
        import Vision  # noqa: F401  # pylint: disable=import-outside-toplevel,unused-import
    except ImportError:
        return False
    return True


def available() -> bool:
    return _has_vision() or shutil.which("tesseract") is not None


def image_text(data: bytes) -> str:
    """Recognised lines, top to bottom (left to right within a row)."""
    return _vision_text(data) if _has_vision() else _tesseract_text(data)


def _upright(data: bytes):
    """Decoded with EXIF orientation applied and any transparency flattened onto white."""
    from PIL import Image, ImageOps, UnidentifiedImageError  # pylint: disable=import-outside-toplevel

    try:
        img = ImageOps.exif_transpose(Image.open(io.BytesIO(data)))
        if img.mode in ("RGBA", "LA", "P"):
            img = img.convert("RGBA")
            page = Image.new("RGBA", img.size, "white")
            page.alpha_composite(img)
            img = page
        return img.convert("RGB")
    except (UnidentifiedImageError, OSError, ValueError):
        raise ValueError("Couldn't read the image (unsupported or damaged file)") from None


def _tesseract(png: bytes, *args: str) -> str:
    try:
        run = subprocess.run(["tesseract", "stdin", "stdout", "--psm", "6", *args], input=png, capture_output=True, timeout=TESSERACT_TIMEOUT_S, check=False)
    except subprocess.TimeoutExpired:
        raise ValueError("Couldn't read the image (text recognition timed out)") from None
    if run.returncode != 0:
        raise ValueError("Couldn't read the image (unsupported or damaged file)")
    return run.stdout.decode("utf-8", "replace")


def _png(img) -> bytes:
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def _real_words(img) -> int:
    """Confidently read words of 3+ letters. Rotated or inverted pages produce scraps of junk, not words, so this
    separates the right orientation far better than mean confidence."""
    count = 0
    for row in _tesseract(_png(img), "tsv").splitlines()[1:]:
        cols = row.split("\t")
        if len(cols) == 12 and float(cols[10]) >= WORD_CONFIDENCE and len(cols[11]) >= 3 and cols[11].isalpha():
            count += 1
    return count


def _tesseract_text(data: bytes) -> str:
    """Tesseract wants dark text on a light page, upright. Photos of a phone screen are often light-on-dark and sideways,
    so: apply EXIF orientation, grey + stretch contrast, invert if dark, then (only if the upright read is poor) pick the
    rotation with the most real words on a small copy. Plain `psm 6` suits a list of exercise lines."""
    from PIL import ImageOps, ImageStat  # pylint: disable=import-outside-toplevel

    img = _upright(data).convert("L")
    img.thumbnail((FULL_EDGE, FULL_EDGE))
    img = ImageOps.autocontrast(img, cutoff=1)
    if ImageStat.Stat(img).mean[0] < 128:
        img = ImageOps.invert(img)
    probe = img.copy()
    probe.thumbnail((PROBE_EDGE, PROBE_EDGE))
    best, best_score = 0, _real_words(probe)
    if best_score < UPRIGHT_ENOUGH:
        for angle in (90, 270, 180):
            score = _real_words(probe.rotate(angle, expand=True))
            if score > best_score:
                best, best_score = angle, score
    if best:
        img = img.rotate(best, expand=True)
    return "\n".join(line for line in map(_trim_noise, _tesseract(_png(img)).splitlines()) if line)


def _trim_noise(line: str) -> str:
    """Drops stray one-character tokens the background leaves at the end of a line (`Air Squats s`, `Warm up : |`)."""
    words = line.split()
    while len(words) > 1 and (len(words[-1]) == 1 and not words[-1].isdigit() and not words[-1].isupper() or not any(c.isalnum() for c in words[-1])):
        words.pop()
    return " ".join(words)


def _vision_text(data: bytes) -> str:
    """Vision reads rotated text but reports positions in the unrotated image, so try the four orientations (a photo of
    a phone is often sideways). Sideways lines come out taller than wide and upside-down text reads with low confidence,
    so the orientation scores only wide lines, by confidence x characters."""
    # pylint: disable=import-outside-toplevel
    import Vision
    from Foundation import NSData

    img = _upright(data)
    png = _png(img)
    ns_data = NSData.dataWithBytes_length_(png, len(png))
    best_score, best_rows = -1.0, []
    for orientation in VISION_ORIENTATIONS:  # CGImagePropertyOrientation: up, right, left, down
        width, height = img.size if orientation in (1, 3) else img.size[::-1]
        handler = Vision.VNImageRequestHandler.alloc().initWithData_orientation_options_(ns_data, orientation, None)
        request = Vision.VNRecognizeTextRequest.alloc().init()
        request.setRecognitionLevel_(Vision.VNRequestTextRecognitionLevelAccurate)
        request.setUsesLanguageCorrection_(True)
        ok, error = handler.performRequests_error_([request], None)
        if not ok:
            raise ValueError(f"Couldn't read the image ({error.localizedDescription() if error else 'unknown error'})")
        rows, score = [], 0.0
        for obs in request.results() or []:
            candidates = obs.topCandidates_(1)
            if not candidates:
                continue
            box = obs.boundingBox()  # normalised to the oriented image, origin bottom-left
            text = str(candidates[0].string())
            rows.append((1 - (box.origin.y + box.size.height), box.origin.x, text))
            if box.size.width * width > box.size.height * height:
                score += float(candidates[0].confidence()) * len(text)
        if score > best_score:
            best_score, best_rows = score, rows
    best_rows.sort(key=lambda r: (round(r[0], 2), r[1]))
    return "\n".join(r[2] for r in best_rows)
