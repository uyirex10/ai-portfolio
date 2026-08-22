# AI Portfolio

Mechanical engineering graduate building toward AI Automation Engineering and AI Engineering, using AI as a leverage tool to design and ship real, working systems, not just tutorials.

This repo tracks two parallel tracks of hands-on, real-world project builds. Each project is treated as if built for an actual business or client: real requirements, real constraints, real testing, honest documentation of what works and what doesn't.

## Why this repo exists

I'm learning by building, not by watching. Every project here was built end-to-end, architecture, implementation, testing on real or realistic data, and documentation, before moving to the next one. The goal is a portfolio that proves capability, not just familiarity.

## Tracks

### AI Automation Engineering

Workflow automation, data pipelines, and AI-powered business tooling, mostly built in n8n with Python, LLM APIs (Gemini/Claude), and integrations like Gmail, Google Sheets, and webhooks.

| # | Project | Status | Summary |
|---|---------|--------|---------|
| 1 | Invoice Extraction Pipeline | ✅ Done | Gmail trigger → Gemini vision extraction → validation (line items + VAT vs. total) → Google Sheets logging. Tested on 13 real invoices. |
| 2 | CRM Lead Routing and Data Sync Hub | ✅ Done | Three lead sources (webhook, Airtable, Google Sheets) normalized, deduplicated, cleaned with Gemini, scored Hot/Warm/Junk, and routed to HubSpot and Slack. Includes retry logic, a dead-letter queue, and a scheduled Slack digest for failures. |
| 3 | Support Inbox Triage & Reply Drafter | ✅ Done | Classifies support tickets by intent, urgency, and sentiment; auto-resolves routine order-status questions with data grounded in a real order lookup; holds returns for human approval; escalates complaints and anything uncertain with an AI-generated summary. Two-layer guardrail (prompt instruction plus a deterministic code check, scoped per branch) blocks any drafted promise on refunds, compensation, or unverified delivery dates before it can reach a customer. 36% deflection on a deliberately edge-case-heavy 25-ticket stress test. |
| 4 | | 🔲 Not started | |
| 5 | | 🔲 Not started | |
| 6 | | 🔲 Not started | |
| 7 | | 🔲 Not started | |
| 8 | | 🔲 Not started | |
| 9 | | 🔲 Not started | |
| 10 | | 🔲 Not started | |

### AI Engineering

Applied AI/ML systems: RAG, agents, and evaluation-driven engineering, built end-to-end against real data with hand-verified eval methodology, not just demos.

| # | Project | Status | Summary |
|---|---------|--------|---------|
| 1 | Internal Knowledge Assistant: RAG Done Properly | ✅ Done | Grounded document QA over 60 real legal contracts with page-level citations. Naive baseline evolved through hand-verified eval methodology, reranking, and structure-aware chunking to 86% retrieval hit rate and zero hallucinated answers, up from 70%/98% naive. Two-layer refusal design, hybrid search evaluated and rejected with real evidence, served via FastAPI and Streamlit. |

## Tech stack

**Automation:** n8n (local, no Docker, via nvm-windows), Python, Gemini API, Google Workspace APIs, Slack API

**Engineering:** Python, FastAPI, Streamlit, Qdrant, Gemini API, Cohere

**Other:** Git/GitHub, JSON workflow exports for reproducibility

## How each project is documented

Every project folder includes:

- **README.md**: problem, architecture, build steps, testing, known limitations, results
- **workflow-export.json** (automation projects): the actual n8n workflow, exportable and reproducible, credentials and identifying IDs redacted
- **sample-data/**: anonymized or synthetic examples only, never real client data
- **screenshots/**: workflow canvas and result screenshots

## Connect

Building in public on X: https://x.com/UyiOdemwingie

Open to freelance/collaboration opportunities in AI automation and applied AI engineering
