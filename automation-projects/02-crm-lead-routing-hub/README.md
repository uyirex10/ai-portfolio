# Project 2: CRM Lead Routing and Data Sync Hub

**Roadmap position:** A6
**Status:** Complete
**n8n workflow name:** `Project 2 - CRM Lead Routing Hub`

## Problem

Leads arrive from three different sources, a web form, an Airtable base, and a Google Sheet, with no shared structure and no way to tell if the same lead has already come in before. Nothing scores or prioritizes them, and nothing tells a human when a genuinely hot lead shows up. This workflow normalizes all three sources into one schema, deduplicates by email, scores each lead automatically, and routes it to the right destination, HubSpot, Slack, or just a database record, based on how likely it is to be a real opportunity.

## Architecture

Three independent trigger chains (Webhook, Airtable Trigger, Google Sheets Trigger) each normalize their source's raw data into a shared shape, then converge into one pipeline:

1. **Cleanup gate**: a cheap, code-only check decides whether a lead's phone and company fields are already clean. Only messy leads get sent to Gemini for normalization, clean ones skip the AI call entirely.
2. **AI cleanup**: Gemini normalizes phone numbers to E.164 format and extracts company names buried in free text, only when needed.
3. **Dedupe**: an Airtable search by email decides if this lead already exists before anything gets created.
4. **Scoring and routing**: a points-based scorer tags each lead Hot, Warm, or Junk. Hot goes to HubSpot and Slack. Warm goes to HubSpot only. Junk is recorded but not escalated.
5. **Error layer**: every external API call (Gemini, Airtable, HubSpot, Slack) has retry-with-backoff configured, and routes genuine failures to a dead-letter Google Sheet rather than crashing the run. A separate scheduled flow reads that sheet daily and posts a summary digest to Slack.

## Tools

n8n (self-hosted, local), Gemini API (`gemini-flash-latest`, text-only for this project), Airtable (Lead Intake base), HubSpot (private app, App Token auth), Slack (bot token), Google Sheets.

## Key decisions

- **Polling over webhooks** for both Airtable and Google Sheets sources. Airtable's native outbound webhook action requires a paid Team plan; Google Sheets doesn't have a comparable native push option either. Both poll every minute instead. A real trade-off: less real-time, but zero added cost and much simpler to build and maintain.
- **Cheap pre-check before the LLM.** Every lead doesn't need an AI call. A regex-based check runs first, and only leads that genuinely need judgment (messy phone formats, a company name buried inside a message) get sent to Gemini. Saves cost and latency on the majority of already-clean leads.
- **Single-select `Tier` field, not three boolean columns.** A lead can only be one tier at a time, Hot, Warm, or Junk, so it's modeled as one field with one selected value, not three separate yes/no columns that could theoretically disagree with each other.
- **Reach-back node references (`$('NodeName').item.json`) as the standard pattern.** Any node that calls an external API (Gemini, Airtable Search, HubSpot) replaces the current item's data with its own response rather than merging it in. This tripped up this build three separate times before the pattern was recognized. The fix used throughout: always pull original lead data from the last node known to hold it intact, by name, rather than trusting whatever `$json` currently contains.
- **Pinned, named Gemini model over a "-latest" alias.** `gemini-flash-latest` is a rolling alias that can silently repoint to a different underlying model with different access requirements. After hitting an unexplained 403 on it mid-build, the workflow was tested against explicit, named model versions instead for predictability.

## Known limitations

- **Gemini account billing-tier issue, unresolved on Google's side.** Partway through this build, the original Gemini API key began returning `403 PERMISSION_DENIED` across every model tried, despite having worked cleanly minutes earlier. Isolated via a controlled test (identical fresh project on the original Google account still failed; the same setup on a brand-new Google account worked immediately), confirming this is an account-level billing/tier assignment problem on Google's end, not a configuration issue in this project. Worked around using a secondary account's API key. The original account's underlying issue was never resolved and may need direct follow-up with Google support if the secondary account route becomes inconvenient long-term.
- **Occasional 503s on newer preview-tier Gemini models.** `gemini-3.5-flash` returned intermittent "Service Unavailable" errors under light testing. The workflow currently runs on `gemini-flash-latest` under the working account as a more reliably available fallback, despite the alias risk noted above. Worth revisiting if Google's newer models stabilize.
- **Scoring is a first-pass heuristic, not tuned.** The Hot/Warm/Junk point thresholds (buying-intent keywords, presence of company, clean phone format) are a reasonable starting framework, not validated against real conversion outcomes. Worth revisiting once real lead data accumulates.
- **Google Sheets source has a known header quirk.** The `Company` column in the source sheet originally had a trailing space in its header, requiring bracket notation (`$json['Company ']`) to reference correctly. Worth re-checking if that header is ever edited.

## Files in this folder

- `README.md`: this file
- `workflow-export.json`: the full n8n workflow, exported and redacted (Airtable base/table IDs, Google Sheets document ID, and personal account email replaced with placeholder values)
- `sample-data/example-leads.json`: synthetic example lead payloads, one showing a raw lead pre-cleanup, one Hot, one Warm, each with the expected outcome documented
- `screenshots/`: canvas views of the full pipeline, the Switch node's routing rules, and the dead-letter queue with real logged test failures

## Testing

- Both dedupe-check branches (cleanup-needed and already-clean) tested independently and confirmed to converge correctly.
- Idempotency proven directly: identical lead payload submitted twice, first submission created a record, second submission correctly detected the duplicate and created nothing further.
- Both Hot and Warm routing paths tested end to end with real webhook submissions, confirmed correct destinations (HubSpot + Slack for Hot, HubSpot only for Warm) and correct Airtable `Tier` values.
- Error layer deliberately tested twice: a malformed payload (missing required field) correctly failed at HubSpot, retried per configuration, and landed in the dead-letter sheet with full context, while the rest of the run completed normally. A revoked Slack credential was tested the same way, confirming isolated failure handling per node rather than a single point of failure taking down the whole execution.
- Daily digest flow manually triggered (via Schedule Trigger's manual execution) and confirmed to accurately read and summarize real dead-letter entries.

## Walkthrough

No recorded walkthrough for this project. The build process, including the real infrastructure debugging covered under Known Limitations, was shared step by step on X during development.
