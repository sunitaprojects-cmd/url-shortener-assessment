# URL Shortener — AI-Assisted Engineering Assessment

## Overview

This repository contains a production-oriented URL shortener prototype built with FastAPI and PostgreSQL. It evolved through three engineering phases: a greenfield core, a brownfield analytics enhancement, and clarification of an ambiguous custom-alias requirement. AI accelerated engineering work but is not part of the running application.

## Business Capabilities

- **Phase 1 — Greenfield:** creates meaningful generated short URLs, persists mappings, and redirects callers to their destinations.
- **Phase 2 — Brownfield:** records `redirect_count` and `last_accessed_at`, exposes a read-only analytics API, and evolves existing databases through an additive migration.
- **Phase 3 — Ambiguous requirement:** supports normalized custom aliases with routing guardrails, explicit conflict handling, and compatibility with existing generated codes.

## Architecture at a Glance

```text
Client / Swagger
      ↓
FastAPI
      ↓
Pydantic
      ↓
Service Layer
      ↓
Validation / Code Generation
      ↓
SQLAlchemy
      ↓
PostgreSQL
```

See [Architecture](docs/architecture.md) for routes, data flows, persistence, and design decisions.

## Prerequisites

- Python 3.12 or a compatible newer Python 3 release
- PostgreSQL
- `pip`

Docker is not required. Reviewers may use any suitable local or remote PostgreSQL installation.

## Setup

Create and activate a virtual environment, then install the project and development tools:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
```

Set the required environment variables:

```bash
export DATABASE_URL='postgresql+psycopg:///shortlink_dev'
export PUBLIC_BASE_URL='http://localhost:8000'
```

`DATABASE_URL` may use any reviewer-managed PostgreSQL database name and valid PostgreSQL connection string. `PUBLIC_BASE_URL` is the trusted HTTP(S) origin used to construct returned short URLs; it must not include a path prefix.

Initialize or evolve the configured database schema:

```bash
python -m app.schema
```

Run the service:

```bash
python -m uvicorn app.main:app --reload
```

## Swagger / Manual Testing

Open [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs). The API provides:

- `POST /api/v1/urls` — create a short URL
- `GET /{code}` — redirect and record aggregate analytics
- `GET /api/v1/urls/{code}/analytics` — read analytics
- `GET /health` — health check

Automatic code example:

```json
{
  "url": "https://example.com/products/item"
}
```

Custom alias example:

```json
{
  "url": "https://example.com/products/item",
  "custom_alias": "Summer-Sale"
}
```

Accepted custom aliases are normalized to lowercase, so this example returns `summer-sale`. Open the returned `short_url` directly to test the `307` redirect, then request `/api/v1/urls/summer-sale/analytics` to inspect its count and latest access time.

## Automated Validation

Final recorded results:

- Engineering validation benchmark: **100/100 passed**
- Complete regression suite: **236/236 passed**
- Ruff lint: passed
- Ruff formatting: passed
- Python compilation: passed
- `git diff --check`: passed

Run the complete suite and static checks with valid configuration:

```bash
DATABASE_URL='postgresql+psycopg:///shortlink_test' \
PUBLIC_BASE_URL='http://localhost:8000' \
python -m pytest -q

ruff check .
ruff format --check .
```

See [Testing Strategy](docs/testing.md) for test layers, benchmark coverage, manual checks, and limitations.

## Documentation

- [Architecture](docs/architecture.md)
- [Engineering Phases](docs/engineering-phases.md)
- [Testing Strategy](docs/testing.md)
- [Risks and Tradeoffs](docs/risks-tradeoffs.md)
- [AI-Assisted Engineering Log](docs/ai-assisted-engineering-log.md)

## AI-Assisted Engineering Approach

ChatGPT supported requirement interpretation, business framing, architecture, ambiguity resolution, risk analysis, and validation strategy. Codex in VS Code supported repository-aware implementation, testing, debugging, and review. The engineer reviewed, refined, and approved outputs and retained responsibility for correctness, security, maintainability, and production-readiness decisions. The application itself has no runtime LLM dependency.

> AI assists the engineer within tasks; the engineer owns execution and quality.

## Known Limitations

This assessment does not include formal penetration testing; load, concurrency, soak, or capacity testing; authentication or link ownership; detailed click-event history; a formal privacy audit; or external destination reputation and reachability checks. See [Risks and Tradeoffs](docs/risks-tradeoffs.md) for the rationale and deferred production work.
