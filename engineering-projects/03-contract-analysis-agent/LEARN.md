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

## Stages B-F: sealed test, clause types, and the LLM/rules/memo pipeline

### What these stages do, and why

Stage B spent the splitter's one shot at the sealed test split (never
inspected case by case, never tuned against). Stage C picked the 8
clause types the rest of the system watches for, by a rule written down
*before* looking at the ranking it would produce. Stages D-F build the
part of the system that actually reads a clause and decides something
about it: an LLM reads free-form legal text and turns it into a small
number of structured values (which of the 8 types does this clause
match? what dollar amount, date, or notice period does it state?) --
and from that point on, not one more decision is left to the model.

**Core idea: LLM perceives, code decides**, explained at five levels.

- **Age 5:** Imagine a friend who is really good at reading messy
  handwriting but bad at doing math. You don't ask them "is this a good
  deal?" -- you ask them "what number is written here?", and then *you*
  do the math yourself with a calculator. The friend's job is just to
  read; your job is to decide.
- **Age 10:** The LLM's only job is to turn a paragraph of contract
  language into a few plain values -- "this clause caps liability at
  $50,000," "this clause lets either party cancel with 5 days notice."
  It never gets asked "is this good or bad?" Once those values exist, a
  separate piece of plain Python code (no AI involved at all) looks them
  up against fixed thresholds and decides green, amber, red, or
  needs_review. If the code decides something is wrong, you can read
  exactly which line of code and which number caused it -- there's
  nothing to "ask the model why."
- **Age 15:** This split exists because LLMs are good at the fuzzy part
  (language understanding) and unreliable at the strict part
  (consistently applying a fixed numeric threshold the same way every
  single time, with no drift). `src/rules/` is tested to prove it can
  never return "green" for input it doesn't actually have evidence for,
  independent of anything the model says -- the same playbook rule run
  against the same values will always produce the same verdict, forever,
  which is not a guarantee you can make about an LLM's judgment call.
- **Age 20:** It also makes the failure mode legible. If a value is
  wrong because the LLM misread the clause, that's a perception bug,
  diagnosable by looking at the extracted value against the clause text
  (which the grounding check does automatically -- an extracted value
  that doesn't literally appear in the clause, after normalization, is
  discarded and flagged, not trusted). If a verdict is wrong given a
  correct value, that's a decision bug, diagnosable by reading
  `src/rules/rules.py`, a few dozen lines of ordinary Python with no
  model in the loop. Conflating the two would make every wrong answer a
  mystery instead of a located bug.
- **Age 25:** This is the same boundary a well-designed system puts
  between an unreliable, high-variance subsystem and a reliable,
  low-variance one -- treat the LLM as a sensor with known failure
  modes (hallucination, inconsistency under rephrasing, no guaranteed
  determinism) and firewall it behind a validation layer (the grounding
  check) before anything downstream is allowed to trust its output as
  fact, rather than threading model judgment through every decision
  point and losing the ability to audit any single one of them.

### File map

- `src/llm/provider.py` -- `LLMProvider.complete()`: cache-check, call,
  cache-write, with backoff/quota handling. `GeminiProvider`/
  `AnthropicProvider`'s lazy `_ensure_client()` is why `scripts/demo.py`
  works with zero API key, as long as the cache covers the run.
- `src/llm/extract_values.py` -- `ground_check()`: the actual boundary
  between "LLM perceives" and "code decides." Every field the model
  proposes gets checked against the clause's own text before anything
  downstream is allowed to see it as non-null.
- `src/rules/rules.py` and `src/rules/engine.py` -- one small function
  per playbook rule, each fail-closed by construction; `evaluate_rule()`
  wraps every call so even a buggy rule can't accidentally return green.
- `src/memo.py` -- `locate_quote()`: the second place code, not the
  model, has final say -- the quoted evidence in a memo is always a
  direct slice of the source document, never the LLM's self-reported
  string.
- `src/pipeline.py` -- `analyze_contract()`: the one place all of the
  above gets wired together in order.

### Break it on purpose

Run:

```
python -c "
import sys; sys.path.insert(0, 'src/rules')
from engine import evaluate_rule
from rule_types import ClauseInput
rule_def = {'id': 'cap_on_liability_present_and_reasonable', 'clause_type': 'Cap On Liability',
            'params': {'min_reasonable_amount': 50000}}
# Pretend the LLM claimed a huge cap, but it was never grounded (None).
r = evaluate_rule(rule_def, ClauseInput(present=True, amount=None))
print(r.verdict, '--', r.reason)
"
```

Expected result: `Verdict.AMBER -- Liability cap clause found but the amount could not be grounded.`
No matter how confidently an LLM might have claimed a number, if
`amount` is `None` by the time it reaches the rule (because
`ground_check()` already nulled it, or because it was simply never
extracted), the rule cannot return green -- there's no code path from
"amount is None" to "green" anywhere in `rules.py`.

### Self-test questions

1. `extract_clause_values()` calls the LLM once, gets back a JSON object
   with 8 possible fields, and only *then* runs `ground_check()`. Why
   not have the LLM itself decide whether its answer is grounded, since
   it can see the clause text right there in the prompt?
2. `classify_clauses()` fails closed on malformed JSON (treats it as "no
   labels," not "all labels" or a crash). Why is "no labels" the correct
   fail-closed default here, rather than, say, retrying the call?
3. The memo's redline suggestion is explicitly labeled "LLM suggestion,
   not reviewed by counsel" in both the markdown and JSON output, even
   though the quote right above it in the same finding has no such
   caveat. Why is that asymmetry correct rather than inconsistent?

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

**Stages B-F**

1. Because the LLM has no reliable way to grade its own homework --
   asking it "is this grounded?" just gets you a second LLM judgment
   with the same failure modes as the first (it can hallucinate a
   confident "yes" as easily as it hallucinated the value itself). A
   plain substring check after normalization is deterministic, has no
   failure mode of its own beyond the normalization rules, and costs
   nothing extra to run -- it doesn't need to be the model's job because
   it's a job code is strictly better at.
2. Because this is a classification task where false positives (a
   clause confidently mislabeled as, say, "Governing Law" when the
   response was garbage) are worse than false negatives (a clause that
   should have had a label but got none). A malformed response gives no
   evidence either way, so the safe default is the one that can't
   fabricate a finding -- "no labels" costs a missed classification,
   while blindly retrying could burn quota on a call that will keep
   failing the same way, and "assume all labels" could manufacture
   verdicts out of nothing.
3. Because they're different kinds of claim. The quote is not an LLM
   claim at all -- `locate_quote()` is a direct slice of the source
   document, true by construction, with no model involved in deciding
   what it says. The redline is genuinely the model's proposal for how
   to rewrite the clause, with no code-level check on whether it's good
   legal drafting (unlike the quote, there's no "ground truth" to slice
   it from). Labeling exactly the thing that's a guess, and nothing
   else, is more honest than hedging everything uniformly -- a reader
   should trust the quote completely and the redline not at all without
   their own review.
