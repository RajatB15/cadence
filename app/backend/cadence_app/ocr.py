"""On-device text recognition for class screenshots (Apple Vision, the engine behind Live Text). Nothing leaves the Mac."""

from __future__ import annotations

MAX_IMAGE_BYTES = 15 * 1024 * 1024


def available() -> bool:
    try:
        import Vision  # noqa: F401  # pylint: disable=import-outside-toplevel,unused-import
    except ImportError:
        return False
    return True


def image_text(data: bytes) -> str:
    """Recognised lines, top to bottom (left to right within a row)."""
    # pylint: disable=import-outside-toplevel
    import Vision
    from Foundation import NSData

    handler = Vision.VNImageRequestHandler.alloc().initWithData_options_(NSData.dataWithBytes_length_(data, len(data)), None)
    request = Vision.VNRecognizeTextRequest.alloc().init()
    request.setRecognitionLevel_(Vision.VNRequestTextRecognitionLevelAccurate)
    request.setUsesLanguageCorrection_(True)
    ok, error = handler.performRequests_error_([request], None)
    if not ok:
        raise ValueError(f"Couldn't read the image ({error.localizedDescription() if error else 'unknown error'})")
    rows = []
    for obs in request.results() or []:
        candidates = obs.topCandidates_(1)
        if not candidates:
            continue
        box = obs.boundingBox()  # normalised, origin bottom-left
        rows.append((1 - (box.origin.y + box.size.height), box.origin.x, str(candidates[0].string())))
    rows.sort(key=lambda r: (round(r[0], 2), r[1]))
    return "\n".join(r[2] for r in rows)
