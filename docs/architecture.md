# Architecture overview

## Request path

```text
Browser → Next.js app → Next.js API proxy → FastAPI router
        → LangGraph agent → business tools and memory
        → response and trace → browser
```

The frontend owns presentation and browser-side request handling. The FastAPI
routers adapt HTTP requests to the agent. The graph owns turn orchestration;
tools own business operations, while memory and infrastructure modules own
persistence and external service access.

## Directory ownership

- `frontend/src/app/`: Next.js routes and API proxy handlers.
- `frontend/src/features/`: UI and client behavior grouped by product feature.
- `backend/src/api/`: HTTP schemas, dependencies, and routers.
- `backend/src/graph/`: agent state, nodes, routing, and tracing.
- `backend/src/tools/`: callable business tools.
- `backend/src/memory/`: working, profile, and semantic retrieval memory.
- `backend/src/services/`: clients and service adapters.
- `data/`: reference inputs and schemas. Keep existing benchmark paths stable.
- `generated/`: generated scenarios, transcripts, and related artifacts.
- `scripts/`: explicit database, seed, and development commands.
- `backend/tests/`: backend unit and integration tests.
- `tests/`: cross-service and Docker smoke tests.

The Python package is currently named `src`; commands run from the repository
root must include `backend` on `PYTHONPATH`. Docker sets this path for the
backend container.
