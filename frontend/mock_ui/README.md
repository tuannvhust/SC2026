# SC2026 Mock UI — Agent Workspace + Customer Experience

A standalone, proposal-stage mock UI for the SC2026 customer-service agent project.

## Run locally

No build tools or dependencies are required.

1. Extract the ZIP.
2. Open `index.html` in a modern browser.

Alternatively, serve this folder with any static file server.

## Included screens

- **Workspace:** interaction inbox, conversation, suggested response, customer context, and journey timeline.
- **Customers:** searchable demo customer directory and linked interaction history.
- **Products:** searchable product catalog with category and availability filters, product detail views, stock, warranty, features, and linked promotion examples.
- **Promotions:** searchable offers with status/type filters, validity dates, codes, eligibility conditions, minimum order, and eligible product links.
- **Store policies:** searchable policy library split into current policies and archived versions, with category/date sorting, read-only archive notices, policy detail views, and per-topic version history.
- **Evaluation:** illustrative scenario results and demo export.
- **Improvement:** proposal-stage placeholder for future workflows.
- **Account portal:** open separate administrator and customer areas. The customer area requires a name, a selected channel, and the matching Facebook ID, Zalo ID, or phone number before showing the conversation.
- **Customer experience:** Facebook, Zalo, and phone each have their own customer conversation view. Facebook and Zalo use distinct platform-inspired layouts; phone supports local audio playback with clearly labeled illustrative ASR and chatbot audio.

## Preview the customer experience

1. Open `index.html` in a modern browser (or serve this folder with a static file server).
2. Choose **Tài khoản khách hàng** from the account portal.
3. Select Facebook, Zalo, or SĐT, then enter your name and the matching channel ID or phone number.
4. Send a text message, or on the phone channel upload an audio file to see its local player and illustrative ASR. The chatbot response uses fixed mock text and a short sample sound on the phone channel.
5. End the session to see the ended state. Use **Đăng xuất** to return to the account portal. The administrator account opens the existing workspace separately.

All customer-side identity resolution, chat replies, product/promotion details, ASR text, and chatbot audio are illustrative local mock data. Uploaded audio is played locally in the browser; it is not sent to a service. Nothing is persisted or transmitted.

## Catalog data status

The intended source files are `data/catalog/products.js` and `data/catalog/promotions.js`. They were **not present in the inspected `features/langgraph` branch** of the linked repository; its `data/` directory exposed `processed/` and `schema/` instead. Therefore the Products and Promotions screens currently use clearly labeled **illustrative fixtures** in `index.html`, not the real project catalog. Replace the `products` and `promotions` arrays in the script with the real module data when those files are available. Prices, stock, warranty, promotion dates, terms, and mappings must not be treated as real business facts.

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
- Search/filter products and open product detail modals.
- Search/filter promotions and inspect offer terms and eligible products.
- Search/filter store policies, inspect effective dates and approval metadata, and navigate between current and archived versions.
- Export an illustrative evaluation summary.
- Choose an account from the portal; customer login requires a channel, name, and matching ID/phone before opening the customer conversation. Send text, upload/play phone audio, inspect ASR mock text, end the session, and return to the portal with logout.

## Policy archive design notes

- Current and archived policy versions are rendered in separate sections so an old rule is not mistaken for the current one.
- Archived versions are explicitly labeled read-only and historical; the detail view includes the supersession note and links across versions of the same topic.
- Search and category filters apply to both sections, allowing a supervisor to find a policy by topic, ID, keyword, or text. Sorting can prioritize effective dates or titles.
- Policy text, dates, owners, and approval labels are illustrative fixtures only. A production system should use immutable approved versions, explicit effective intervals, audit logs, access control, and date-aware retrieval against the interaction date.

## Explicitly not integrated

No backend, LangGraph, database, LLM/API, telephony, Zalo, Facebook, production identity verification, live product inventory, live promotion validation, or real handoff. All data is local mock data and resets when the page is reloaded. Evaluation metrics are illustrative only.

## Domain conventions

Customer profile, case, interaction, and runtime session are distinct concepts. A returning customer gets a new interaction record; the demo history links records only where the seeded fixture explicitly defines the relationship. Unverified identity restricts message sending and selected commit actions in the prototype.
