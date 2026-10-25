# SC2026 Mock UI — User Flows

## Separate account entry and customer login

```mermaid
flowchart TD
  A[SC2026 account portal] -->|Admin account| ADM[Open employee workspace]
  A -->|Customer account| B[Customer login page]
  B --> C{Choose channel}
  C -->|Facebook| D[Enter name + fb_id]
  C -->|Zalo| E[Enter name + zalo_id]
  C -->|Phone| F[Enter name + phone number]
  D --> G[Open Facebook-style conversation]
  E --> H[Open Zalo OA-style conversation]
  F --> I[Open phone conversation]
  G --> J[Send text]
  H --> J
  I -->|Optional| K[Upload audio + see player and illustrative ASR]
  I --> J
  J --> L[See fixed chatbot reply]
  K --> L
  L -->|Phone only| M[Play sample chatbot audio]
  L --> N[End session or log out]
```

The administrator workspace and customer portal are separate entries. Customer login is required before opening its conversation. IDs and phone numbers only simulate identity resolution. Replies and ASR are fixtures, chatbot audio is a short embedded demo sound, and uploaded audio remains local to the browser. Facebook uses a Messenger-inspired header and blue sent bubbles; Zalo uses a blue OA bar, verified-account cue, and card-like message layout.

## Policy lookup and historical review

```mermaid
flowchart TD
  A[Open Store policies] --> B[Search by topic, policy ID, keyword, or text]
  B --> C{Which version is needed?}
  C -->|Current answer| D[Open Current policies section]
  D --> E[Review effective date, owner, approval metadata, and policy text]
  E --> F[Verify against the approved source before answering]
  C -->|Past interaction / dispute| G[Open Archived policy versions]
  G --> H[Check effective date and supersession note]
  H --> I[Open version history for the same policy topic]
  I --> J[Compare historical text and version dates]
```

## Design rules

- Current and archived versions appear in separate sections.
- Archived versions are marked read-only and include a warning not to use them for new customer requests.
- Search and category filters cover both sections; sorting supports effective date and title.
- Each detail view shows version metadata and links to other versions of the same topic.
- The mock data is illustrative. Production retrieval should select the approved policy version effective at the time of the interaction when investigating historical cases, and the current approved version for new answers.

## Product question

```mermaid
flowchart TD
  A[Customer asks about product] --> B[Open Products]
  B --> C[Search / filter catalog]
  C --> D[Inspect product facts]
  D --> E[Check linked promotions if relevant]
  E --> F[Verify live source before making a commitment]
```

## Promotion eligibility

```mermaid
flowchart TD
  A[Customer asks about an offer] --> B[Open Promotions]
  B --> C[Search code or offer name]
  C --> D[Inspect status, dates, terms, eligible products]
  D --> E[Verify live eligibility and checkout rules]
```
