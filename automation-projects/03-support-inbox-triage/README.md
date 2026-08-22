# Support Inbox Triage & Reply Drafter

## Problem

An e-commerce store's two support agents were drowning in ticket volume, roughly 80% routine order-status and return questions, with real complaints getting buried underneath. The client needed routine requests handled automatically, everything else escalated, and a hard guarantee the system would never promise a refund, compensation, or a delivery date it couldn't verify.

## Results

- **Deflection rate: 36%** (9 of 25 test tickets fully auto-resolved, zero human touch), measured on a deliberately edge-case-heavy stress test, not a representative traffic sample. Real-world deflection on routine WISMO volume specifically would be expected to run considerably higher, since the test set intentionally over-weighted complaints, manipulation attempts, and boundary cases to prove every branch worked correctly.
- **Guardrail violations reaching a customer: 0.** Two independent bait tests (a corrupted policy doc, and a direct customer manipulation attempt asking the bot to guarantee a refund and a delivery date) were both caught before anything sent.
- **Misrouted mixed-signal tickets: 0.** An angry-but-routine ticket, an order-number-present-but-actually-a-complaint ticket, and a return-request-that's-really-a-complaint ticket all routed correctly.
- **25 of 40 planned test tickets run**, chosen to cover every branch and edge case in the architecture rather than running the full set unprioritized. See `project-05-test-tickets.md` for the full set and methodology.

## Architecture

```
Gmail Trigger → Classify (intent, urgency, sentiment, confidence, order_number)
   → Confidence Gate (< 0.6 → escalate)
   → Intent Router
        ├─ order_status → lookup by order_number, else by email
        │     ├─ exactly 1 match → draft from real order data + policy → guardrail check → auto-send
        │     └─ 0 or 2+ matches → auto-send a clarifying reply (no claims made, no human needed)
        ├─ return → draft from policy only → guardrail annotation → Pending Approval sheet + Slack
        └─ complaint / other / fallback → escalate
   → any guardrail failure, on any path → reroute to escalation
   → all escalations → LLM summary → Slack (#support-escalations)
```

## Key Decision: The Automation Boundary

Order-status replies auto-send because they're a lookup against real data, not a judgment call, and the cost of being wrong is low and reversible. Returns always hold for a human because approving a return is a judgment call against policy, and a wrong auto-approval risks a promise the store can't honor. Complaints and anything the classifier is genuinely unsure about always escalate, no draft even generated, since a human needs to own that conversation directly.

A third case emerged during the build that the original two-bucket design didn't cover: when the order lookup finds zero or multiple matches, the safest move isn't escalation, it's an auto-sent clarifying reply that makes no claims at all. Since nothing is asserted, there's no cost if it's "wrong", so it's actually safer to automate than a judgment call, and automating it keeps ordinary typos and ambiguous emails from ever reaching the two agents this system was built to protect.

## Guardrail Design

Two independent layers: an explicit forbidden-list instruction in the system prompt, and a separate, deterministic pattern check in code that runs after generation and before any send decision. The two layers fail independently, so a prompt-level miss doesn't mean a real miss.

The forbidden list is scoped per branch, not universal. The order-status branch blocks any mention of "refund" outright, since that branch should never legitimately need the word. The return branch's entire purpose is discussing refunds, so it instead blocks premature approval language ("approved", "confirmed") instead of the word itself, a guardrail that blocks the thing a branch is supposed to say isn't safety, it's a workflow-breaker.

## Tools

n8n (local, no Docker), Google Gemini API (flash-tier models), Google Sheets (mock order DB, Pending Approval queue), Gmail (intake and auto-send), Slack (escalation notifications).

## Known Limitations

- A near-empty test message ("Where") returned exactly 0.6 confidence, landing right on the Confidence Gate's threshold and passing through as order_status. Not a failure, but a real signal the threshold may need tightening for very short, low-information messages.
- `$('NodeName').first()` is used throughout to reach back for classification data across nodes. This assumes one ticket per workflow execution. Gmail Trigger polls up to 10 messages per interval, so if multiple tickets ever land in the same poll, every item in that batch would incorrectly get tagged with the first ticket's data. Not hit in testing, worth fixing before any real production volume.
- All synthetic test customers use `@example.com`, a domain reserved specifically for documentation and testing that cannot receive real mail. Auto-sends during testing were verified by inspecting node output directly rather than actual delivery, real customer addresses would behave identically.
- 25 of 40 planned test tickets were run, prioritized for branch and edge-case coverage over raw count.

## Testing

See `project-03-test-tickets.md` for the full test set, methodology, and the precise definition of "deflected" used for this project.

## How to Run

1. n8n running locally via `nvm use 22.22.0` then `n8n start`, editor at `localhost:5678`.
2. Credentials needed: Gmail, Google Gemini API, Google Sheets, Slack.
3. Import `workflow-export.json`, seed the order DB using `sample-data/`, create the three Google Sheet tabs (`Sheet1`, `Pending Approval`) and a `#support-escalations` Slack channel.
4. Test using mock data on the Gmail Trigger node, see `project-04-test-tickets.md`.
