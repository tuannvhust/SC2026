# SC2026 Mock UI — User Flows

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
