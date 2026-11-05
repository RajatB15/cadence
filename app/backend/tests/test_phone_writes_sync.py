"""The phone write allowlist exists in share.py and in web/src/lib/phoneWrites.ts; fail loudly if they drift."""
import json
import re
from pathlib import Path

from cadence_app import share

WEB = Path(__file__).resolve().parents[2] / "web" / "src" / "lib" / "phoneWrites.ts"
ENTRY = re.compile(r'^\s*\[\s*("(?:[^"\\]|\\.)*")\s*,\s*("(?:[^"\\]|\\.)*")\s*\]\s*,?\s*$', re.M)


def _web_rules() -> list[tuple[str, str]]:
    text = WEB.read_text()
    block = text[text.index("RULES"):text.index("PHONE_WRITES =")]
    return [(json.loads(m), json.loads(p)) for m, p in ENTRY.findall(block)]


def test_web_and_backend_allowlists_match():
    web = _web_rules()
    py = [(m, rx.pattern) for m, rx in share.PHONE_WRITES]
    assert web, "could not parse any [method, regex] entries from phoneWrites.ts"
    assert len(web) == len(set(web)), "duplicate entries in phoneWrites.ts"
    only_web, only_py = sorted(set(web) - set(py)), sorted(set(py) - set(web))
    assert not only_web and not only_py, (
        "phone write allowlist drift between share.py and web/src/lib/phoneWrites.ts\n"
        f"  only in phoneWrites.ts: {only_web}\n  only in share.py PHONE_WRITES: {only_py}"
    )


def test_regexes_use_only_portable_syntax():
    # Features whose meaning differs between Python re and JS RegExp, or that exist in only one.
    banned = [r"\(\?<[=!]", r"\(\?P", r"\(\?<\w", r"\(\?[aiLmsux-]+[:)]", r"\\[AZzZ]", r"\\[pP]\{", r"\(\?#", r"[*+?}][+]"]
    for method, pattern in [(m, rx.pattern) for m, rx in share.PHONE_WRITES] + _web_rules():
        re.compile(pattern)
        for b in banned:
            assert not re.search(b, pattern), f"non-portable regex feature {b!r} in ({method}, {pattern!r})"
        assert not pattern.startswith("^") and not pattern.endswith("$"), f"entries must be unanchored: {pattern!r}"
