"""Memo generator: for each non-green rule finding, quote the evidence
directly from the source document by offset (never from the LLM's
self-reported string -- that's a claim, this is a slice), attach the
rule id/verdict/reason, and an LLM-suggested redline labeled as a
suggestion. Renders markdown and JSON.

The LLM is used only for the redline suggestion text (clearly labeled
as such in both outputs); everything else -- which findings exist, what
their verdict is, what the quoted evidence actually says -- is decided
by code (segment.py's offsets and src/rules/'s verdicts), not asked of
the model.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

try:
    import sys as _sys
    from pathlib import Path as _Path
    _sys.path.insert(0, str(_Path(__file__).resolve().parent / "llm"))
    from provider import LLMProvider  # noqa: E402
except ImportError:  # pragma: no cover - provider is optional for pure-quote use
    LLMProvider = None  # type: ignore


@dataclass
class MemoFinding:
    rule_id: str
    clause_type: str
    verdict: str
    reason: str
    quote: str
    quote_start: int
    quote_end: int
    redline_suggestion: Optional[str] = None
    redline_is_suggestion: bool = True


@dataclass
class ClauseFindingInput:
    clause_type: str
    clause_start: int
    clause_end: int
    rule_id: str
    verdict: str
    reason: str
    evidence: Optional[str] = None  # the LLM's claimed evidence substring, if any


def locate_quote(source: str, clause_start: int, clause_end: int, evidence: Optional[str] = None):
    """Returns (quote, start, end) such that quote == source[start:end],
    always, by construction. Tries to find `evidence` within the
    clause's own span first (a tighter, more useful quote); falls back
    to the whole clause span if evidence is missing or not actually in
    the clause text."""
    clause_text = source[clause_start:clause_end]
    if evidence:
        idx = clause_text.find(evidence)
        if idx != -1:
            start = clause_start + idx
            end = start + len(evidence)
            return source[start:end], start, end
    return clause_text, clause_start, clause_end


def build_redline_prompt(clause_type: str, clause_text: str, verdict: str, reason: str) -> str:
    return (
        f'The following "{clause_type}" clause received a {verdict.upper()} finding: {reason}\n\n'
        f"Clause text:\n{clause_text}\n\n"
        "Suggest a specific redline (revised clause language) that would address this finding. "
        "Respond with ONLY the suggested replacement text, no commentary or markdown formatting."
    )


def generate_redline_suggestion(clause_type: str, clause_text: str, verdict: str, reason: str,
                                 provider) -> Optional[str]:
    if provider is None:
        return None
    prompt = build_redline_prompt(clause_type, clause_text, verdict, reason)
    try:
        return provider.complete(prompt)
    except Exception as e:  # a failed redline suggestion must not break the memo
        return f"(redline suggestion unavailable: {e})"


def build_memo_findings(source: str, clause_findings: list[ClauseFindingInput], provider=None,
                         skip_green: bool = True) -> list[MemoFinding]:
    findings = []
    for cf in clause_findings:
        if skip_green and cf.verdict == "green":
            continue
        quote, start, end = locate_quote(source, cf.clause_start, cf.clause_end, cf.evidence)
        clause_text = source[cf.clause_start:cf.clause_end]
        redline = generate_redline_suggestion(cf.clause_type, clause_text, cf.verdict, cf.reason, provider)
        findings.append(MemoFinding(
            rule_id=cf.rule_id, clause_type=cf.clause_type, verdict=cf.verdict, reason=cf.reason,
            quote=quote, quote_start=start, quote_end=end, redline_suggestion=redline,
        ))
    return findings


def render_markdown(contract_name: str, findings: list[MemoFinding]) -> str:
    lines = [f"# Review memo: {contract_name}", ""]
    if not findings:
        lines.append("No non-green findings.")
        return "\n".join(lines)

    for f in findings:
        lines.append(f"## {f.clause_type} -- {f.verdict.upper()} ({f.rule_id})")
        lines.append("")
        lines.append(f"**Reason:** {f.reason}")
        lines.append("")
        lines.append(f"**Quoted evidence** (source offsets {f.quote_start}-{f.quote_end}):")
        lines.append("> " + f.quote.replace("\n", "\n> "))
        lines.append("")
        if f.redline_suggestion:
            lines.append("**Suggested redline (LLM suggestion, not reviewed by counsel):**")
            lines.append("")
            lines.append(f.redline_suggestion)
            lines.append("")
    return "\n".join(lines)


def render_json(contract_name: str, findings: list[MemoFinding]) -> dict:
    return {
        "contract": contract_name,
        "findings": [
            {
                "rule_id": f.rule_id,
                "clause_type": f.clause_type,
                "verdict": f.verdict,
                "reason": f.reason,
                "quote": f.quote,
                "quote_start": f.quote_start,
                "quote_end": f.quote_end,
                "redline_suggestion": f.redline_suggestion,
                "redline_is_suggestion": f.redline_is_suggestion,
            }
            for f in findings
        ],
    }
