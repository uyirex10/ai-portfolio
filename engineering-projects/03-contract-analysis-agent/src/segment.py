"""Clause-aware splitter for contract text.

Real CUAD contracts have no consistent structure to lean on: some files
preserve one line per paragraph, others collapse the entire contract onto a
single line, so splitting cannot rely on newlines. Numbering schemes vary
per contract (ARTICLE I / SECTION 2.3 / 1.1 / (a) / ALL-CAPS headings) and
are sometimes mixed within one document, and numbers used as headings are
not reliably sequential (renumbered amendments, skipped sections). This
module finds heading/numbering boundaries directly in the raw character
stream using regexes with "clause-boundary" context checks (preceded by
start-of-text, a sentence-ending period, or a newline) to avoid firing on
in-sentence numbers like "$10.5 million" or cross-references like
"Section 4(a) of this Agreement". It never removes or reorders text: every
clause's `text` is an exact `source[start:end]` slice, so offsets are always
valid by construction and nothing (including page-break noise) is lost.

Two-level hierarchy only: top-level clauses (ARTICLE / SECTION / "N." /
ALL-CAPS fallback) and one layer of sub-clauses nested inside them (dotted
numbering "N.M[.K...]" and lettered/roman markers "(a)", "(i)"). Sub-clause
boundaries never promote to top-level, so an inline enumeration like
"(1) pay rent; (2) maintain insurance" inside a single clause cannot
fragment that clause into multiple top-level entries.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class Clause:
    id: str
    heading: Optional[str]
    text: str
    start: int
    end: int
    subclauses: List["Clause"] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Boundary context helpers
# ---------------------------------------------------------------------------

# A position is a plausible clause/heading start if what precedes it is the
# start of the document, a sentence-ending period/semicolon/colon (any
# amount of whitespace -- including none -- after it), or a newline
# anywhere in the preceding run of whitespace. This keeps numbers inside
# sentences (prices, dates, cross-references) from being mistaken for new
# clauses, while tolerating the irregular multi-space/tab gaps real
# contract layouts produce (lookbehind in the regex itself can't do this:
# Python's re requires fixed-width lookbehind, but the whitespace gap here
# is variable-length), which is why this is a plain function instead of
# baked into the regexes below.
def _is_boundary_left(text: str, pos: int) -> bool:
    if pos == 0:
        return True
    before = text[:pos]
    stripped = before.rstrip()
    gap = before[len(stripped):]
    if '\n' in gap:
        return True
    # The gap must be non-empty: without this, the inner "5." of a dotted
    # number like "1.5." would be misread as a fresh sentence-ending period
    # immediately followed by a new top-level "5." (there's no whitespace
    # at all between "1." and "5" in that case, unlike a real sentence
    # boundary, which always has at least one space/newline after the
    # period).
    return bool(gap) and bool(stripped) and stripped[-1] in '.;:'


_ROMAN = r'[IVXLCDM]+'

# Strict roman-numeral grammar (not just "made of I/V/X/L/C/D/M letters"):
# this is what keeps a real word like "MIX" or "DID" -- which happens to
# use only roman-numeral letters -- from being treated as a heading number
# below; it's additionally required to parse to a value <= 50.
_STRICT_ROMAN = r'M{0,4}(?:CM|CD|D?C{0,3})(?:XC|XL|L?X{0,3})(?:IX|IV|V?I{0,3})'

# Heading-tail extraction is deliberately a *separate* regex applied via
# .match() at a marker's end, not baked into the marker regexes below. A
# numbered/article/section boundary is still a real boundary even when
# nothing that looks like a short heading follows it (body text starts
# immediately, and that body text may run past this cap before its first
# period/double-space/newline). Baking the two together means the whole
# marker match fails outright whenever the heading-tail can't find its
# terminator within range -- silently losing the boundary entirely, not
# just the heading -- which is worse than just leaving heading=None.
_HEADING_TAIL_RE = re.compile(
    r'(?P<heading>[A-Z][A-Za-z0-9 ,;:&/\'\-]{0,80}?)'
    r'(?=\.(?:\s|\Z)|\s{2,}|\n|\Z)'
)


def _extract_heading(text: str, pos: int) -> Optional[str]:
    m = _HEADING_TAIL_RE.match(text, pos)
    return _clean_heading(m.group('heading')) if m else None


ARTICLE_RE = re.compile(
    r'(?i:ARTICLE)\s+(?P<num>' + _ROMAN + r'|\d{1,3})\b[.:]?\s*'
)

SECTION_RE = re.compile(
    r'(?i:SECTION)\s+(?P<num>\d{1,3}(?:\.\d{1,3}){0,3})\b[.:]?\s*'
)

# Bare roman-numeral heading with no "ARTICLE"/"SECTION" word at all, e.g.
# "VIII. CONFIDENTIAL DATA". Without this, "VIII" and "CONFIDENTIAL DATA"
# would each look like their own standalone ALL-CAPS heading to
# CAPS_HEADING_RE, severing the number from its title.
BARE_ROMAN_RE = re.compile(
    r'(?<![A-Za-z])(?P<num>' + _STRICT_ROMAN + r')\.\s+'
)

# Top-level numbered heading: a single integer followed by a period, e.g.
# "4. Termination." Must not be a dotted sub-number (handled separately).
TOP_NUMBERED_RE = re.compile(
    r'(?P<num>\d{1,3})\.(?!\d)\s+'
)

# Dotted sub-numbering anywhere, e.g. "4.1", "4.1.2". Depth = dot count.
DOTTED_RE = re.compile(
    r'(?P<num>\d{1,3}(?:\.\d{1,3}){1,4})\.?\s+'
)

# Lettered / roman sub-clause markers, e.g. "(a)", "(ii)". Left context is
# deliberately unrestricted (list items commonly follow a verb with no
# punctuation at all, e.g. "may terminate (a) ... (b) ..."); false positives
# are filtered out later by requiring >=2 markers in a strictly increasing
# sequence, and cross-references like "Section 4(a) of this Agreement" are
# excluded by checking the preceding few characters.
LETTERED_RE = re.compile(
    r'\((?P<num>[a-z]{1,3}|[ivxlcdm]{1,5}|\d{1,3})\)'
)

_CROSS_REF_WORDS = re.compile(r'(section|clause|article|paragraph|exhibit)\s*$', re.I)

# Standalone ALL-CAPS heading (fallback when no numbering scheme applies at
# that position), e.g. "CONFIDENTIALITY", "GOVERNING LAW".
CAPS_HEADING_RE = re.compile(
    r'(?P<heading>[A-Z][A-Z0-9 &/,\'\-]{2,58}[A-Z0-9])'
    r'(?=\s*\n|\s{2,}(?=[A-Z][a-z])|\.(?:\s|\Z))'
)

_PAGE_NOISE_RE = re.compile(r'page\s+\d+\s+of\s+\d+', re.I)

_CAPS_CONTEXT_WINDOW = 60
_CAPS_CONTEXT_MIN_ALPHA = 15
_CAPS_CONTEXT_UPPER_RATIO = 0.85

# A disclaimer clause (which conventionally IS written entirely in caps)
# can legitimately be followed immediately by a real heading with no
# mixed-case text between them at all -- e.g. an all-caps limitation-of-
# liability clause ending right where "TERMINATION" begins. The
# before-context check alone can't tell that apart from a sentence
# restart inside the SAME disclaimer, so known canonical section-heading
# phrases are always accepted regardless of context. This is a deliberate
# compromise, not a general solution: a real heading using wording not on
# this list, immediately after another all-caps clause's tail, would
# still be suppressed.
_KNOWN_HEADING_PHRASES = {
    'GOVERNING LAW', 'LIMITATION OF LIABILITY', 'TERMINATION', 'CONFIDENTIALITY',
    'MISCELLANEOUS', 'INDEMNIFICATION', 'FORCE MAJEURE', 'ENTIRE AGREEMENT', 'NOTICES',
    'NOTICE', 'ASSIGNMENT', 'WARRANTY', 'WARRANTIES', 'DEFINITIONS', 'RECITALS',
    'SEVERABILITY', 'COUNTERPARTS', 'AMENDMENT', 'AMENDMENTS', 'WAIVER', 'ARBITRATION',
    'DISPUTE RESOLUTION', 'NON-DISCLOSURE', 'NON-COMPETE', 'EXCLUSIVITY', 'AUDIT RIGHTS',
    'INSURANCE', 'TAXES', 'INTELLECTUAL PROPERTY', 'LICENSE GRANT', 'SURVIVAL',
    'HEADINGS', 'INTERPRETATION', 'FURTHER ASSURANCES', 'SUCCESSORS AND ASSIGNS',
    'PUBLICITY', 'EXPORT CONTROL', 'DATA PROTECTION', 'SIGNATURES',
    'REPRESENTATIONS AND WARRANTIES', 'LIMITATION OF REMEDIES',
}


# Stage A bake-off, Variant B: reject a caps candidate if its heading
# text itself contains a verb or modal auxiliary (real headings are noun
# phrases; a sentence restart inside a disclaimer is a complete clause
# with a verb). An alternative to Variant A's context-ratio+allowlist
# check, not a supplement to it -- see _find_top_level_candidates's
# `caps_fallback_rule` parameter.
_VERB_OR_MODAL_WORDS = {
    'SHALL', 'WILL', 'MAY', 'MUST', 'IS', 'ARE', 'HAS', 'HAVE', 'CAN',
    'WOULD', 'SHOULD', 'COULD', 'DOES', 'DID', 'WAS', 'WERE', 'BE',
}


def _contains_verb_or_modal(heading: str) -> bool:
    return bool(set(heading.upper().split()) & _VERB_OR_MODAL_WORDS)


def _is_inside_allcaps_block(text: str, start: int, end: int) -> bool:
    """Liability/warranty disclaimer boilerplate is conventionally written
    entirely in ALL CAPS (a drafting convention for conspicuousness), so
    *every* sentence restart after a period inside one of those paragraphs
    looks exactly like a real standalone heading to CAPS_HEADING_RE --
    e.g. "...SUCH DAMAGE.\nTHIS LIMITATION WILL APPLY EVEN IF..." is not a
    heading, just the next sentence of the same all-caps clause.

    Only the text *before* the candidate is checked, deliberately: a real
    heading's own body text (e.g. "LIMITATION OF LIABILITY" followed by
    "IN NO EVENT SHALL...") is routinely all-caps too, so checking after
    the candidate rejects genuine headings. What actually distinguishes a
    real heading is what came before it -- the tail end of the *previous*
    clause, which is normal mixed-case prose for a real heading, versus
    more all-caps disclaimer text for a same-paragraph sentence restart.
    """
    window = text[max(0, start - _CAPS_CONTEXT_WINDOW):start]
    alpha = [c for c in window if c.isalpha()]
    if len(alpha) < _CAPS_CONTEXT_MIN_ALPHA:
        return False
    upper_ratio = sum(1 for c in alpha if c.isupper()) / len(alpha)
    return upper_ratio >= _CAPS_CONTEXT_UPPER_RATIO


def _looks_like_page_noise(text: str, pos: int) -> bool:
    """True only if `pos` falls inside an actual "Page X of Y" phrase --
    not merely near one elsewhere in the paragraph."""
    for m in _PAGE_NOISE_RE.finditer(text):
        if m.start() <= pos < m.end():
            return True
    return False


_MINOR_WORDS = {
    'and', 'or', 'for', 'of', 'to', 'the', 'in', 'on', 'a', 'an', 'as', 'by', 'with', 'is', 'are',
}

# Preamble connector words ("...entered into BETWEEN Party A and Party B")
# that sometimes stand alone on their own line and satisfy the ALL-CAPS
# heading shape, but are never themselves a clause heading.
_NON_HEADING_WORDS = {'between', 'and', 'among', 'by and between', 'by and among'}


def _looks_like_heading(heading: Optional[str]) -> bool:
    """Headings are short, title-cased phrases ("Initial Term",
    "GOVERNING LAW"). A regular sentence ("The Company shall deliver...")
    captured by the same regex (because no short heading was present)
    should not be mistaken for one."""
    if not heading:
        return False
    if heading.lower() in _NON_HEADING_WORDS:
        return False
    words = heading.split()
    if not words or len(words) > 10:
        return False
    content_words = [w for w in words if w.lower() not in _MINOR_WORDS]
    if not content_words:
        return False
    cap_count = sum(1 for w in content_words if w[0].isupper())
    return cap_count / len(content_words) >= 0.6


def _clean_heading(raw: Optional[str]) -> Optional[str]:
    if raw is None:
        return None
    h = raw.strip().strip('.').strip()
    if not h or not _looks_like_heading(h):
        return None
    return h


def _preceded_by_cross_ref(text: str, pos: int) -> bool:
    return bool(_CROSS_REF_WORDS.search(text[max(0, pos - 15):pos]))


def _dot_depth(num: str) -> int:
    """Nesting depth of a dotted number *relative to its top-level clause*,
    e.g. "2.1" -> 1, "2.1.3" -> 2. (Not the absolute component count.)"""
    return num.count('.')


def _letter_rank(token: str) -> int:
    token = token.lower()
    if token.isdigit():
        return int(token)
    if all(c in 'ivxlcdm' for c in token):
        roman = {'i': 1, 'v': 5, 'x': 10, 'l': 50, 'c': 100, 'd': 500, 'm': 1000}
        total, prev = 0, 0
        for ch in reversed(token):
            val = roman[ch]
            total += -val if val < prev else val
            prev = max(prev, val)
        return total
    # plain letter(s): a=1, b=2, ... z=26
    total = 0
    for ch in token:
        total = total * 26 + (ord(ch) - ord('a') + 1)
    return total


# ---------------------------------------------------------------------------
# Candidate collection
# ---------------------------------------------------------------------------

def _collect_matches(regex, text: str, kind: str) -> List[dict]:
    out = []
    for m in regex.finditer(text):
        if not _is_boundary_left(text, m.start()) or _looks_like_page_noise(text, m.start()):
            continue
        out.append({
            'start': m.start(),
            'marker_end': m.end(),
            'kind': kind,
            'number': m.group('num'),
            'heading': _extract_heading(text, m.end()),
        })
    return out


def _group_dotted_as_top_level(text: str) -> List[dict]:
    """Fallback for contracts whose only numbering scheme is dotted
    (e.g. "1.1 Scope", "1.2 Term", "2.1 Definitions") with no bare "1."
    heading ever written on its own. The first sub-item of each top-level
    integer group becomes that group's top-level boundary; there is no
    separate heading text for the group itself, so heading is left None
    (the first child, e.g. "1.1", carries its own correct heading)."""
    groups: List[dict] = []
    seen_tops: set = set()
    for m in DOTTED_RE.finditer(text):
        if not _is_boundary_left(text, m.start()) or _looks_like_page_noise(text, m.start()):
            continue
        num = m.group('num')
        top = num.split('.')[0]
        if top in seen_tops:
            continue
        seen_tops.add(top)
        groups.append({
            'start': m.start(),
            'marker_end': m.start() + len(num) + 1,
            'kind': 'numbered',
            'number': top,
            'heading': None,
        })
    groups.sort(key=lambda g: g['start'])
    return groups


def _find_top_level_candidates(text: str, caps_fallback_rule: str = 'A') -> List[dict]:
    article_matches = _collect_matches(ARTICLE_RE, text, 'article')
    section_matches = _collect_matches(SECTION_RE, text, 'section')

    numbered_matches = []
    for m in TOP_NUMBERED_RE.finditer(text):
        if not _is_boundary_left(text, m.start()) or _looks_like_page_noise(text, m.start()):
            continue
        # Don't double-count "SECTION 1." / "ARTICLE 1." — those are
        # already captured above as article/section matches.
        if _preceded_by_cross_ref(text, m.start()) or re.search(
            r'(section|article)\s*$', text[max(0, m.start() - 12):m.start()], re.I
        ):
            continue
        numbered_matches.append({
            'start': m.start(),
            'marker_end': m.end(),
            'kind': 'numbered',
            'number': m.group('num'),
            'heading': _extract_heading(text, m.end()),
        })

    for m in BARE_ROMAN_RE.finditer(text):
        num = m.group('num')
        if not num or _letter_rank(num) > 50:
            continue
        if not _is_boundary_left(text, m.start()) or _looks_like_page_noise(text, m.start()):
            continue
        if _preceded_by_cross_ref(text, m.start()) or re.search(
            r'(section|article)\s*$', text[max(0, m.start() - 12):m.start()], re.I
        ):
            continue
        numbered_matches.append({
            'start': m.start(),
            'marker_end': m.end(),
            'kind': 'numbered',
            'number': num,
            'heading': _extract_heading(text, m.end()),
        })
    numbered_matches.sort(key=lambda c: c['start'])

    # A document's *top-level* scheme is whichever is most structurally
    # specific among what it actually uses: ARTICLE outranks SECTION, which
    # outranks plain "N.". A scheme that loses out here isn't discarded --
    # it still gets picked up later as a nested sub-clause boundary inside
    # whichever top-level clause its span falls under (e.g. "SECTION 2.1"
    # nested inside "ARTICLE II").
    demoted: List[dict] = []
    if article_matches:
        numbered_or_structured = article_matches
        demoted = section_matches + numbered_matches
    elif section_matches:
        numbered_or_structured = section_matches
        demoted = numbered_matches
    elif numbered_matches:
        numbered_or_structured = numbered_matches
    else:
        # No ARTICLE/SECTION/bare "N." heading anywhere -- the document may
        # still be structured, just entirely via dotted numbers (see
        # _group_dotted_as_top_level).
        numbered_or_structured = _group_dotted_as_top_level(text)

    numbered_or_structured = sorted(numbered_or_structured, key=lambda c: c['start'])
    deduped: List[dict] = []
    for c in numbered_or_structured:
        if deduped and c['start'] - deduped[-1]['start'] <= 3:
            continue
        deduped.append(c)
    numbered_or_structured = deduped

    # ALL-CAPS fallback headings, added only where they aren't just the
    # heading text of an already-found boundary (within ~90 chars after it).
    caps_candidates = []
    for m in CAPS_HEADING_RE.finditer(text):
        if not _is_boundary_left(text, m.start()) or _looks_like_page_noise(text, m.start()):
            continue
        heading = _clean_heading(m.group('heading'))
        if not heading or len(heading.split()) > 8:
            continue
        pos = m.start()
        # Skip caps text that falls inside a boundary's own heading capture
        # (that's the heading of an already-found clause, not a new one).
        near_existing = any(
            c['start'] <= pos <= c['marker_end'] + 5 for c in numbered_or_structured
        )
        if near_existing:
            continue
        if caps_fallback_rule == 'B':
            if _contains_verb_or_modal(heading):
                continue
        else:
            if heading not in _KNOWN_HEADING_PHRASES and _is_inside_allcaps_block(text, pos, m.end()):
                continue
        caps_candidates.append({
            'start': pos,
            'marker_end': m.end(),
            'kind': 'caps',
            'number': None,
            'heading': heading,
        })

    # Scanned/filed SEC exhibits often carry a running header or footer
    # (page stamp, filer name, exhibit number) repeated verbatim on every
    # page. A real section heading is unique; the same exact caps string
    # appearing 3+ times across one document is page-break noise, not a
    # clause boundary.
    heading_counts: dict = {}
    for c in caps_candidates:
        heading_counts[c['heading']] = heading_counts.get(c['heading'], 0) + 1
    caps_candidates = [c for c in caps_candidates if heading_counts[c['heading']] < 3]

    if numbered_or_structured:
        # Mixed documents: numbered body plus unnumbered trailing sections
        # (e.g. "MISCELLANEOUS", "SIGNATURES") are valid additional boundaries.
        all_candidates = numbered_or_structured + caps_candidates
    else:
        # No numbering scheme detected anywhere: fall back to caps-only.
        all_candidates = caps_candidates

    all_candidates.sort(key=lambda c: c['start'])

    final: List[dict] = []
    for c in all_candidates:
        if final and c['start'] - final[-1]['start'] <= 3:
            continue
        final.append(c)

    final = _drop_toc_like_runs(final)

    return final, demoted


def _drop_toc_like_runs(cands: List[dict], min_gap: int = 40, min_run: int = 3) -> List[dict]:
    """A table of contents reproduces the heading pattern almost exactly
    (e.g. "19. NOTICES 19\\n\\n20. LAW 20\\n\\n..." -- heading number,
    title, page number, repeat), which would otherwise look like a run of
    real but near-empty top-level clauses. Three or more consecutive
    candidates each within `min_gap` characters of the next is that
    signature; drop the whole run rather than split on it."""
    if len(cands) < min_run:
        return cands
    drop: set = set()
    i = 0
    n = len(cands)
    while i < n - 1:
        j = i
        while j + 1 < n and cands[j + 1]['start'] - cands[j]['start'] < min_gap:
            j += 1
        if j - i + 1 >= min_run:
            drop.update(range(i, j + 1))
        i = j + 1
    return [c for idx, c in enumerate(cands) if idx not in drop]


def _find_dotted_candidates(
    text: str, span_start: int, span_end: int, top_number: Optional[str], demoted: List[dict] = (),
) -> List[dict]:
    candidates: List[dict] = []
    for m in DOTTED_RE.finditer(text[span_start:span_end]):
        num = m.group('num')
        if top_number is not None and num.split('.')[0] != str(top_number):
            continue
        pos = span_start + m.start()
        if not _is_boundary_left(text, pos) or _looks_like_page_noise(text, pos):
            continue
        candidates.append({
            'start': pos,
            'number': num,
            'depth': _dot_depth(num),
            'heading': _extract_heading(text, span_start + m.end()),
        })

    # Boundaries that a sibling top-level scheme (e.g. SECTION, when ARTICLE
    # won the top-level slot) demoted down to this clause's nesting level.
    for d in demoted:
        if span_start <= d['start'] < span_end:
            candidates.append({
                'start': d['start'],
                'number': d['number'],
                'depth': max(_dot_depth(d['number']), 1),
                'heading': d['heading'],
            })

    candidates.sort(key=lambda c: c['start'])
    deduped: List[dict] = []
    for c in candidates:
        if deduped and c['start'] - deduped[-1]['start'] <= 1:
            continue
        deduped.append(c)
    return deduped


def _build_dotted_tree(text: str, span_start: int, span_end: int, cands: List[dict]) -> List[Clause]:
    """Nest dotted-number candidates purely by relative depth, e.g.
    "2" -> ["2.1", "2.2"] -> "2.2" -> ["2.2.1", ...]."""
    if not cands:
        return []

    min_depth = min(c['depth'] for c in cands)
    tops = [c for c in cands if c['depth'] == min_depth]

    result: List[Clause] = []
    for i, cand in enumerate(tops):
        start = cand['start']
        end = tops[i + 1]['start'] if i + 1 < len(tops) else span_end
        nested = [c for c in cands if c is not cand and start < c['start'] < end and c['depth'] > min_depth]
        children = _build_dotted_tree(text, start, end, nested)
        result.append(Clause(
            id=str(cand['number']), heading=cand['heading'],
            text=text[start:end], start=start, end=end, subclauses=children,
        ))
    return result


def _find_lettered_candidates(text: str, span_start: int, span_end: int) -> List[dict]:
    sub = text[span_start:span_end]
    hits = []
    for m in LETTERED_RE.finditer(sub):
        pos = span_start + m.start()
        if _preceded_by_cross_ref(text, pos) or _looks_like_page_noise(text, pos):
            continue
        hits.append({'start': pos, 'number': m.group('num'), 'rank': _letter_rank(m.group('num'))})
    hits.sort(key=lambda c: c['start'])

    # Keep only a strictly increasing rank sequence (drops stray mismatched
    # parens like a cross-reference that slipped past the checks above),
    # and require at least two members: a lone "(a)" is more likely a
    # one-off reference than the start of a lettered sub-clause list.
    kept: List[dict] = []
    last_rank = 0
    for h in hits:
        if h['rank'] > last_rank:
            kept.append(h)
            last_rank = h['rank']
    return kept if len(kept) >= 2 else []


def _attach_lettered(text: str, clause: Clause) -> None:
    if clause.subclauses:
        for child in clause.subclauses:
            _attach_lettered(text, child)
        return
    lettered = _find_lettered_candidates(text, clause.start, clause.end)
    if not lettered:
        return
    children = []
    for i, h in enumerate(lettered):
        start = h['start']
        end = lettered[i + 1]['start'] if i + 1 < len(lettered) else clause.end
        children.append(Clause(id=h['number'], heading=None, text=text[start:end], start=start, end=end))
    clause.subclauses = children


def segment_contract(text: str, caps_fallback_rule: str = 'A') -> List[Clause]:
    """Split `text` into clause-aware segments.

    Returns top-level Clause objects in document order; each clause's
    `subclauses` holds nested dotted-number / lettered sub-clauses found
    within its span. Every clause.text is an exact source[start:end] slice.

    `caps_fallback_rule`: 'A' (default, frozen) uses the before-context
    all-caps-ratio check plus a canonical-phrase allowlist. 'B' is the
    Stage A bake-off alternative: reject a caps candidate if its heading
    text contains a verb or modal auxiliary, instead of the context
    check. Exists for scripts/bakeoff.py's comparison; not meant to be
    selected in normal use once Stage A's pre-registered choice is made.
    """
    if not text:
        return []

    top_cands, demoted = _find_top_level_candidates(text, caps_fallback_rule)

    if not top_cands:
        return [Clause(id='1', heading=None, text=text, start=0, end=len(text))]

    boundaries = []
    for i, c in enumerate(top_cands):
        start = c['start']
        end = top_cands[i + 1]['start'] if i + 1 < len(top_cands) else len(text)
        boundaries.append((start, end, c))

    clauses: List[Clause] = []

    # Preamble text before the first detected heading (common when a
    # contract opens with recitals/definitions before any numbered clause).
    first_start = boundaries[0][0]
    if first_start > 0 and text[:first_start].strip():
        clauses.append(Clause(id='0', heading=None, text=text[:first_start], start=0, end=first_start))

    seq_index = 1
    for start, end, cand in boundaries:
        clause_text = text[start:end]
        number = cand['number']
        cid = str(number) if number is not None else str(seq_index)
        seq_index += 1

        top_number = number if cand['kind'] == 'numbered' else None
        dotted_cands = _find_dotted_candidates(text, start, end, top_number, demoted)
        subclauses = _build_dotted_tree(text, start, end, dotted_cands)

        clause = Clause(
            id=cid,
            heading=cand['heading'],
            text=clause_text,
            start=start,
            end=end,
            subclauses=subclauses,
        )
        _attach_lettered(text, clause)
        clauses.append(clause)

    return clauses


def flatten(clauses: List[Clause]) -> List[Clause]:
    """Flatten a clause tree (top-level + nested) into a single list."""
    out: List[Clause] = []
    for c in clauses:
        out.append(c)
        out.extend(flatten(c.subclauses))
    return out
