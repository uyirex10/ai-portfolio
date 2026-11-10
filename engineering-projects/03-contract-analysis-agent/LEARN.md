# LEARN.md

Written progressively, one section per stage. Each section explains what
the stage does, maps the key files, gives a "break it on purpose"
experiment, and ends with self-test questions (answers at the bottom of
each section, under ANSWERS).

---

## Stage A: the splitter and PDF extraction

### What this stage does, and why

A contract analysis tool has to cut a contract into clauses before it
can do anything else with it (classify a clause, extract a dollar
amount, decide if it's risky). Stage A builds and hardens that cutter
(`src/segment.py`) and the PDF-to-text step that feeds it
(`src/extract.py`), and spends most of its effort checking the cutter's
work against real, messy, inconsistently-formatted contracts rather than
trusting it on faith.

**Core idea: offset-exact splitting**, explained at five levels.

- **Age 5:** Imagine cutting a long paper ribbon into pieces. Every
  single piece has to be an exact, uncut bit of the original ribbon --
  no gluing bits together, no snipping off little scraps and losing
  them. If you line all the pieces back up, you get the whole ribbon
  again, with nothing missing and nothing changed.
- **Age 10:** When the program splits a contract into clauses, each
  clause remembers exactly which characters of the original document it
  came from -- like a sticky note that says "I am characters 500 to
  800." You can always go back and check: do characters 500-800 of the
  real document say exactly what this clause says? If yes, nothing got
  mixed up or deleted on the way. Every time the splitter runs it might
  be wrong about WHERE the cuts go, but it is never allowed to be wrong
  about WHAT the text inside a piece actually says, because that text
  is always a direct slice, never a retyped copy.
- **Age 15:** This matters because every later stage (the LLM classifier,
  the rule engine, the memo generator) builds on top of these offsets. If
  a clause's text were reconstructed or cleaned up instead of sliced
  directly from the source, a bug anywhere in that reconstruction could
  silently change the legal meaning of what the system is reasoning
  about, and nobody downstream would be able to tell. Slicing instead of
  rebuilding means that kind of corruption is structurally impossible --
  `clause.text` is defined as `source[start:end]`, full stop.
- **Age 20:** This is a weaker, cheaper substitute for a real
  self-verifying parser: instead of proving the segmentation logic is
  correct, we make incorrectness in a narrow but critical dimension
  (data integrity) impossible by construction, and only allow the
  *boundary placement* to be heuristic and fallible. It is the same
  design instinct as "parse, don't validate" -- push a class of bug out
  of the realm of things that can even happen, rather than trying to
  catch it with tests.
- **Age 25:** It also buys auditability for a regulated-adjacent domain.
  A memo that says "this clause caps liability at $50,000" has to be
  traceable to the literal contract language a lawyer can pull up and
  verify, not a system's paraphrase of it -- offset-exact slicing is
  what makes every downstream claim independently checkable against the
  source PDF, which is the actual trust requirement for this kind of
  tool, not a nice-to-have.

### File map

- `src/segment.py` -- the clause splitter. Read `segment_contract()` (the
  entry point), `_find_top_level_candidates()` (decides where top-level
  clause boundaries go), and `_is_inside_allcaps_block()` /
  `_contains_verb_or_modal()` (the two competing rules for not mistaking
  a sentence inside an ALL-CAPS disclaimer for a heading).
- `src/extract.py` -- `extract_pdf_text()`, the only place PDF bytes
  become text. The 2-entry `_CHAR_MAP` is the whole fix for the U+037E
  font-encoding bug.
- `scripts/span_integrity.py` -- `find_span()` and `classify_span()`:
  how we check whether a CUAD-labeled clause lands inside one splitter
  clause or gets cut across several, on real (not synthetic) data.

### Break it on purpose

Run:

```
python -c "
import sys; sys.path.insert(0, 'src')
from segment import segment_contract
text = '1. Definitions. See terms below.\n\n2. Term. One year.\n'
clauses = segment_contract(text)
clauses[0].text = 'TAMPERED'
print(clauses[0].text == text[clauses[0].start:clauses[0].end])
"
```

Expected result: `False`. This isn't a bug -- it's the point. Nothing in
`segment_contract` stops you from mutating a `Clause` object in Python
after the fact (dataclasses aren't frozen), but every *test* in
`tests/test_segment.py` re-derives `text[c.start:c.end]` and compares it
to `c.text` rather than trusting the field -- so a real bug that broke
the offset-exact guarantee during segmentation (not this manual
tampering) would be caught by `_assert_round_trip` the moment any test
ran, not discovered later downstream.

### Self-test questions

1. Why is `extract_pdf_text`'s character map restricted to 1-character-
   for-1-character substitutions, with no deletions or multi-character
   expansions allowed?
2. The dev-set span-integrity check measures containment against *leaf*
   clauses (flattened, including sub-clauses), not top-level clauses
   only. Why does that distinction matter?
3. Variant B of the ALL-CAPS fallback (reject if the heading contains a
   verb/modal) and Variant A (context-ratio + allowlist) disagree on
   some real headings. Name one category of heading each is likely to
   get wrong that the other gets right.

---

## ANSWERS

**Stage A**

1. Because any substitution that isn't 1-for-1 would shift every
   character offset after it, breaking the offset-exact guarantee the
   splitter depends on -- a deletion or a 2-character expansion would
   mean `source[start:end]` no longer points at the text it's supposed
   to for every clause after that point in the document.
2. Because the actual unit a Stage D classifier sees is a leaf clause,
   not a top-level one. A labeled span that lands correctly inside a
   top-level clause but is split across two of that clause's
   sub-clauses would still hand the classifier a broken, incomplete
   training example -- measuring only against top-level clauses would
   hide that failure.
3. Variant A (context-based) is likely to wrongly keep a false heading
   right after normal mixed-case text even if that false heading
   happens to be a short noun phrase containing no verb (it only looks
   at context, not the phrase itself) -- and is likely to wrongly drop a
   real heading not on its allowlist if it directly follows another
   clause's all-caps tail. Variant B (verb/modal-based) is likely to
   wrongly drop a genuine heading that happens to contain one of the
   flagged words, such as an "AS IS" disclaimer tag, since "IS" trips
   the verb filter regardless of context.
