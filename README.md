# AI Portfolio

Mechanical engineering graduate building toward AI Automation Engineering and AI Engineering, using AI as a leverage tool to design and ship real, working systems, not just tutorials.

This repo tracks two parallel tracks of hands-on, real-world project builds. Each project is treated as if built for an actual business or client: real requirements, real constraints, real testing, honest documentation of what works and what doesn't.

## Why this repo exists

I'm learning by building, not by watching. Every project here was built end-to-end — architecture, implementation, testing on real or realistic data, and documentation — before moving to the next one. The goal is a portfolio that proves capability, not just familiarity.

## Tracks

### AI Automation Engineering
Workflow automation, data pipelines, and AI-powered business tooling, mostly built in n8n with Python, LLM APIs (Gemini/Claude), and integrations like Gmail, Google Sheets, and webhooks.

| # | Project | Status | Summary |
|---|---------|--------|---------|
| 1 | [Invoice Extraction Pipeline](./automation-projects/01-invoice-extraction) | ✅ Done | Gmail trigger → Gemini vision extraction → validation (line items + VAT vs. total) → Google Sheets logging. Tested on 13 real invoices. |
| 2 | | 🔲 Not started | |
| 3 | | 🔲 Not started | |
| 4 | | 🔲 Not started | |
| 5 | | 🔲 Not started | |
| 6 | | 🔲 Not started | |
| 7 | | 🔲 Not started | |
| 8 | | 🔲 Not started | |
| 9 | | 🔲 Not started | |
| 10 | | 🔲 Not started | |

### AI Engineering
Applied AI/ML projects across automotive, manufacturing, robotics, and medical device domains — leaning on my mechanical engineering background. Coming soon.

| # | Project | Status | Summary |
|---|---------|--------|---------|
| 1 | | 🔲 Not started | |

## Tech stack

- **Automation:** n8n (local, no Docker, via nvm-windows), Python, Gemini API, Google Workspace APIs
- **Engineering:** Python, FastAPI, LangChain (planned)
- **Other:** Git/GitHub, JSON workflow exports for reproducibility

## How each project is documented

Every project folder includes:
- `README.md`: problem, architecture, build steps, testing, known limitations, results
- `workflow-export.json` (automation projects): the actual n8n workflow, exportable and reproducible
- `sample-data/`: anonymized or synthetic examples only, never real client data
- `screenshots/`: workflow canvas and result screenshots

## Connect

- Building in public on X: https://x.com/UyiOdemwingie
- Open to freelance/collaboration opportunities in AI automation and applied AI engineering
