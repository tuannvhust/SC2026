# SC2026 Mock UI — Continuity Desk + Customer Journey

A standalone, proposal-stage mock UI for the SC2026 customer-service agent project.

## Run locally

No build tools or dependencies are required.

1. Extract the ZIP.
2. Open `index.html` in a modern browser.

Alternatively, serve this folder with any static file server.

## Included screens

- **Workspace:** interaction inbox, conversation, suggested response, customer context, and journey timeline.
- **Customers:** searchable demo customer directory.
- **Evaluation:** illustrative scenario results and demo export.
- **Improvement:** proposal-stage placeholder for future workflows.

## Interactions implemented

- Filter interactions by channel and status; search inbox.
- Switch between seeded interactions.
- Add a local demo message to the transcript.
- Update interaction status locally.
- Create a new demo interaction.
- Inspect customer history and case details.
- Simulate identity verification.
- Create a memory proposal for human review (proposal only).
- Simulate handoff state through the interaction status.
- Export an illustrative evaluation summary.

## Explicitly not integrated

No backend, LangGraph, database, LLM/API, telephony, Zalo, Facebook, production identity verification, or real handoff. All data is local mock data and resets when the page is reloaded. Evaluation metrics are illustrative only.

## Domain conventions

Customer profile, case, interaction, and runtime session are distinct concepts. A returning customer gets a new interaction record; the demo history links records only where the seeded fixture explicitly defines the relationship. Unverified identity restricts message sending and selected commit actions in the prototype.
