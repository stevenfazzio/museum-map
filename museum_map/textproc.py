"""Text surgery for the three variants.

Variant (b) needs the first sentence removed; variant (c) needs location entities
removed. Both have to work across ~100 languages and several scripts, so neither
can lean on English-specific assumptions.
"""

from __future__ import annotations

import re
import unicodedata

# --------------------------------------------------------- sentence splitting

# Latin-style terminators need a following space; CJK/Devanagari-style ones don't.
_SPACED_TERM = ".!?؟۔։。！？"
_HARD_TERM = "。！？｡।॥။។᠃"

# Tokens that end in "." without ending a sentence, across the big Wikipedia languages.
_ABBREV = {
    # en
    "mr", "mrs", "ms", "dr", "prof", "st", "mt", "no", "vs", "etc", "approx", "ca", "c",
    "inc", "ltd", "co", "jr", "sr", "vol", "fig", "op", "cf", "ed", "est", "e.g", "i.e",
    # de
    "bzw", "ggf", "usw", "u.a", "z.b", "d.h", "nr", "jh", "jt", "geb", "gest", "bspw",
    "sog", "evtl", "einschl", "ehem", "urspr", "bes", "gegr",
    # fr / es / it / pt
    "av", "bd", "env", "cf", "chap", "ex", "num", "pag", "sec", "sig", "sra", "srta",
    "aprox", "esq", "art", "ss", "pp", "ecc", "sec", "sez", "n", "v", "p",
    # nl / sv / da / no / pl / cs / ru transliterated
    "bijv", "blz", "dhr", "mevr", "resp", "t.o.v", "o.a", "bl", "resp", "np", "tj",
    "atd", "tzv", "resp", "im", "ul", "im", "tj",
}

_CJK_RE = re.compile(
    r"[぀-ヿ㐀-䶿一-鿿豈-﫿"
    r"가-힯฀-๿ក-៿က-႟]"
)


def _is_boundary(text: str, i: int) -> bool:
    """Is the terminator at index i a real end-of-sentence?"""
    ch = text[i]
    if ch in _HARD_TERM:
        return True

    # Must be followed by whitespace (or end of text).
    j = i + 1
    while j < len(text) and text[j] in ".!?)”’\"'":
        j += 1
    if j >= len(text):
        return True
    if not text[j].isspace():
        return False

    # Next non-space char should start a new sentence.
    k = j
    while k < len(text) and text[k].isspace():
        k += 1
    if k >= len(text):
        return True
    nxt = text[k]
    if not (nxt.isupper() or _CJK_RE.match(nxt) or nxt in "“«\"'("):
        # Lowercase continuation -> almost always an abbreviation or a list.
        return False

    if ch == ".":
        # Preceding token: digits ("am 1. Januar"), single initial ("J. M. W."),
        # or a known abbreviation are all non-boundaries.
        m = re.search(r"([^\s]+)$", text[:i])
        tok = (m.group(1) if m else "").lower().rstrip(".")
        if not tok:
            return False
        if tok.isdigit():
            return False
        if len(tok) == 1 and tok.isalpha():
            return False
        if tok in _ABBREV:
            return False
    return True


def split_first_sentence(text: str) -> tuple[str, str]:
    """Return (first_sentence, remainder). Remainder is '' if no boundary is found."""
    text = text.strip()
    depth = 0
    for i, ch in enumerate(text):
        if ch in "([（【":
            depth += 1
        elif ch in ")]）】":
            depth = max(0, depth - 1)
        elif depth == 0 and ch in _SPACED_TERM and _is_boundary(text, i):
            j = i + 1
            while j < len(text) and text[j] in ".!?)”’\"'":
                j += 1
            return text[:j].strip(), text[j:].strip()
    return text, ""


# --------------------------------------------------------- location stripping


# Inflecting languages attach endings to place names and demonyms
# ("französische", "deutschen", "Berliner", "warszawski"). Allowing a short
# suffix catches those; requiring the match to still end on a word boundary
# keeps "Paris" from eating "Parisienne".
_SUFFIX_MIN_LEN = 5
_SUFFIX_MAX = 3


def _usable_term(term: str) -> bool:
    """Reject gazetteer entries that would cause collateral damage."""
    t = term.strip()
    if not any(c.isalpha() for c in t):
        return False
    # CJK place names are genuinely 2 characters (東京, 日本, パリ), so a
    # script-blind length floor would silently disable stripping for them.
    if _CJK_RE.search(t):
        return len(t) >= 2
    if len(t) < 3:
        return False
    # "IT", "USA"-style codes match far too much inside other words/acronyms.
    if len(t) <= 3 and t.isupper():
        return False
    return True


def build_pattern(terms: set[str]) -> re.Pattern | None:
    """One alternation, longest-first so 'New York City' wins over 'New York'."""
    usable = sorted({t.strip() for t in terms if _usable_term(t)}, key=len, reverse=True)
    if not usable:
        return None
    parts = []
    for t in usable:
        esc = re.escape(t)
        if _CJK_RE.search(t):
            # No word boundaries in scripts without spaces.
            parts.append(esc)
        elif len(t) >= _SUFFIX_MIN_LEN:
            parts.append(rf"(?<!\w){esc}\w{{0,{_SUFFIX_MAX}}}(?!\w)")
        else:
            parts.append(rf"(?<!\w){esc}(?!\w)")
    return re.compile("|".join(parts), re.IGNORECASE | re.UNICODE)


_CLEANUP = [
    (re.compile(r"\(\s*[,;:]?\s*\)"), ""),              # emptied parentheses
    (re.compile(r"\[\s*\]"), ""),
    (re.compile(r"\s+([,;:.!?])"), r"\1"),              # space before punctuation
    (re.compile(r"([,;:])\s*(?=[,;:])"), ""),           # doubled separators
    (re.compile(r"[ \t ]{2,}"), " "),
    (re.compile(r"\s*\n\s*"), "\n"),
]


def tidy(text: str) -> str:
    for pat, repl in _CLEANUP:
        text = pat.sub(repl, text)
    return text.strip()


def strip_locations(
    text: str, pattern: re.Pattern | None, ner_spans: list[tuple[int, int]] | None = None
) -> str:
    """Remove gazetteer matches and NER LOC spans, then tidy the wreckage."""
    spans: list[tuple[int, int]] = list(ner_spans or [])
    if pattern is not None:
        spans.extend((m.start(), m.end()) for m in pattern.finditer(text))
    if not spans:
        return tidy(text)

    spans.sort()
    merged: list[list[int]] = []
    for s, e in spans:
        if merged and s <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], e)
        else:
            merged.append([s, e])

    out, prev = [], 0
    for s, e in merged:
        out.append(text[prev:s])
        prev = e
    out.append(text[prev:])
    return tidy("".join(out))


def normalize_ws(text: str) -> str:
    text = unicodedata.normalize("NFC", text)
    text = re.sub(r"[ \t ]+", " ", text)
    text = re.sub(r"\n{2,}", "\n", text)
    return text.strip()
