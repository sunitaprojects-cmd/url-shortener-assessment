# Architecture Overview

The URL shortener is a stateless FastAPI service backed by PostgreSQL. Application instances retain no URL mappings in process memory, so requests can be handled by any instance connected to the same database.

```text
Client / Browser / Swagger
        ↓
FastAPI routing
app/api.py
        ↓
Pydantic request/response schemas
app/schemas.py
        ↓
Service / business logic
app/url_creation.py
app/url_resolution.py
app/url_analytics.py
        ↓
Validation / domain helpers
app/url_validation.py
app/short_code.py
app/custom_alias.py
        ↓
SQLAlchemy persistence layer
app/database.py
app/models.py
        ↓
PostgreSQL
```

- **FastAPI** receives HTTP requests, routes them by method and path, and maps service outcomes to HTTP responses.
- **Pydantic** defines request and response contracts, validates input structure, and supplies Swagger/OpenAPI metadata.
- **Service modules** own creation, redirect, and analytics behavior. This includes the decision between automatic code generation and custom-alias creation.
- **Validation helpers** validate destination URLs, generate and validate automatic codes, normalize custom aliases, and protect the routing namespace.
- **SQLAlchemy** provides the Python engine, session, model, and persistence abstractions used to interact with PostgreSQL.
- **PostgreSQL** is the source of truth for mappings and aggregate analytics. Its unique constraint is the final concurrency-safe authority for short-code uniqueness.

## API Routing

FastAPI decides **which endpoint** receives a request based on its HTTP method and URL path:

| Method and path | Responsibility |
|---|---|
| `POST /api/v1/urls` | Create an automatically generated or custom short URL |
| `GET /{code}` | Record a redirect and return `307 Temporary Redirect` |
| `GET /api/v1/urls/{code}/analytics` | Read aggregate analytics without mutation |
| `GET /health` | Application liveness |

FastAPI's `/docs`, `/redoc`, and `/openapi.json` routes, the health route, and versioned `/api/...` routes are registered ahead of the root code route. Matching reserved names are also rejected as custom aliases, so application routes cannot be claimed as short links.

FastAPI chooses the endpoint. After `POST /api/v1/urls` has been routed, the creation service makes the **business-logic decision** between automatic generation and a requested custom alias.

## URL Creation Decision Flow

```text
POST /api/v1/urls
        ↓
Pydantic request validation
        ↓
Validate destination URL
        ↓
Is custom_alias supplied?
        ↓
   ┌───────────────┴────────────────┐
   │                                │
   NO                               YES
   │                                │
   ↓                                ↓
Derive meaningful slug       Validate alias guardrails
from destination path               ↓
   ↓                         Normalize accepted input
Generate 8-character               to lowercase
Base62 suffix                        ↓
   ↓                         Use requested alias once
Build <slug>-<suffix>                │
   │                                │
   └───────────────┬────────────────┘
                   ↓
             Create UrlMapping
                   ↓
             SQLAlchemy INSERT
                   ↓
        PostgreSQL unique constraint
                   ↓
                 COMMIT
                   ↓
               HTTP 201
```

`custom_alias` is optional. Omitting it or supplying `null` preserves the Phase 1 automatic-generation behavior.

The collision paths intentionally differ:

- **Generated-code collision:** PostgreSQL rejects the duplicate; the transaction rolls back; the service generates a new candidate and retries. The limit is five attempts, after which the API returns a sanitized `503`.
- **Custom-alias collision:** PostgreSQL rejects the requested alias; the transaction rolls back; the service does not generate, retry, or substitute another value. The API returns `409 Conflict` with `custom_alias_conflict` and “Custom alias is already in use.”

### 1. Automatic Short URL Creation

Example request:

```http
POST /api/v1/urls
```

```json
{
  "url": "https://example.com/products/item"
}
```

```text
Client / Swagger
        ↓
POST /api/v1/urls
        ↓
Destination URL validation
        ↓
No custom_alias
        ↓
Meaningful path slug + secure Base62 suffix
        ↓
SQLAlchemy INSERT
        ↓
PostgreSQL uniqueness check
        ↓
COMMIT
        ↓
HTTP 201
```

A conceptual result is `item-Ab3Xy91Q`. The readable portion comes from the final useful destination path segment, with a hostname or `link` fallback. The suffix contains exactly eight Base62 characters from a cryptographically secure random source. PostgreSQL remains the final uniqueness authority.

Submitting the same destination repeatedly may intentionally produce different codes; `original_url` is not unique. The returned `short_url` uses the configured `PUBLIC_BASE_URL`, not the incoming request host.

### 2. Custom Alias Creation

Example request:

```json
{
  "url": "https://example.com/products/item",
  "custom_alias": "Summer-Sale"
}
```

```text
POST /api/v1/urls
        ↓
Destination URL validation
        ↓
custom_alias supplied
        ↓
Alias guardrail validation
        ↓
Summer-Sale → summer-sale
        ↓
SQLAlchemy INSERT
        ↓
PostgreSQL uniqueness check
        ↓
COMMIT
        ↓
HTTP 201 with /summer-sale
```

Custom aliases follow these rules:

- The field is optional.
- Creation input is case-insensitive; accepted aliases are stored canonically in lowercase.
- Length is 3–32 characters.
- ASCII letters, digits, and internal hyphens are allowed.
- The first and last characters must be alphanumeric.
- Repeated internal hyphens are allowed.
- Reserved application names are rejected.
- Slashes, traversal forms, query/fragment characters, encoded routing attempts, control characters, Unicode aliases, and unsupported punctuation are rejected.
- A complete URL is not a custom alias; the caller supplies only the alias/code portion.
- Invalid aliases receive useful, sanitized `422` reasons.
- An alias already in use receives `409`.
- Apart from lowercase normalization, invalid aliases are never silently rewritten.
- A requested alias is attempted once, with no retry or substitution.

The public hostname comes exclusively from `PUBLIC_BASE_URL`; it is never supplied through `custom_alias`.

## Short URL Redirect Flow

Example: `GET /summer-sale`

```text
Browser / Client
        ↓
FastAPI GET /{code}
        ↓
Routable-code validation
        ↓
PostgreSQL atomic UPDATE ... RETURNING
        ↓
redirect_count = redirect_count + 1
last_accessed_at = database timestamp
        ↓
COMMIT
        ↓
HTTP 307 Temporary Redirect
        ↓
Stored original URL
```

Both generated codes and canonical custom aliases are routable. Generated Base62 suffixes may contain uppercase characters and remain case-sensitive, so incoming route codes are not globally lowercased. `/summer-sale` resolves when stored, while `/Summer-Sale` may return `404`.

The analytics update commits before redirect success. If the update or commit fails, the application rolls back and returns a sanitized `503`; it does not return `307`. Unknown or invalid codes return sanitized `404 short_url_not_found`.

`307 Temporary Redirect` avoids permanent client caching while expiration, editing, and other lifecycle behavior remain intentionally outside the assessment scope.

## Analytics Request Flow

Example: `GET /api/v1/urls/summer-sale/analytics`

```text
Client
        ↓
FastAPI analytics route
        ↓
Routable-code validation
        ↓
SQLAlchemy read
        ↓
PostgreSQL
        ↓
code, original_url, redirect_count,
last_accessed_at, created_at
```

Analytics reads are non-mutating: requesting analytics does not increment the count or update the timestamp. `redirect_count` represents redirect responses whose database update committed successfully. The prototype stores only the aggregate count and latest-access timestamp; there is no click-history event table.

## Validation Responsibilities

| Module | Responsibility |
|---|---|
| `app/url_validation.py` | Validates and minimally normalizes absolute HTTP(S) destination URLs while preserving path, query, and fragment semantics |
| `app/short_code.py` | Generates automatic codes, strictly validates their format, and validates the union of generated and custom routable formats |
| `app/custom_alias.py` | Lowercases and validates requested aliases using the allowlist, length, boundary, and reserved-route rules |

These responsibilities remain separate so custom aliases cannot weaken Phase 1 generated-code validation. Generated suffixes may contain uppercase Base62 characters, whereas custom aliases are stored lowercase.

## Data Model

`UrlMapping` in `app/models.py` contains:

| Field | Purpose |
|---|---|
| `id` | Internal `BIGINT IDENTITY` primary key |
| `short_code` | Globally unique generated code or custom alias |
| `original_url` | Validated destination URL |
| `redirect_count` | Non-null aggregate count, default `0` |
| `last_accessed_at` | Nullable timezone-aware timestamp of the latest committed redirect |
| `created_at` | Timezone-aware creation timestamp generated by PostgreSQL |

The named PostgreSQL unique constraint on `short_code` is the final concurrency-safe collision authority and supplies the indexed lookup used for redirects and analytics.

## Database and Schema Evolution

Phase 1 used SQLAlchemy `create_all()` as a lightweight greenfield schema mechanism. In Phase 2, the application became brownfield: `create_all()` could create a fresh table with analytics fields but could not evolve an existing Phase 1 table.

The explicit additive migration `app/migrations/002_add_redirect_analytics.sql` therefore adds and backfills `redirect_count` and adds nullable `last_accessed_at`. `app/schema.py` creates missing tables and applies the known migration. This remains intentionally lightweight; no migration framework or Alembic history was introduced for the assessment.

## Configuration

| Environment variable | Purpose |
|---|---|
| `DATABASE_URL` | Selects and configures the PostgreSQL database connection |
| `PUBLIC_BASE_URL` | Defines the trusted public origin used to construct returned short URLs |

Examples:

```text
Local:      http://localhost:8000/summer-sale
Production: https://short.example.com/summer-sale
```

Localhost is only a development/testing configuration. Changing to a production hostname requires configuration, not an application code change. The application does not use an incoming `Host` header to construct public short URLs.

## Guardrails and Security Boundaries

Destination URL guardrails include:

- Absolute HTTP or HTTPS URL only.
- Required valid hostname and port.
- No embedded username or password.
- No whitespace or control characters.
- Structured parser-based validation.
- No unsupported schemes such as `ftp:`, `javascript:`, or `file:`.
- No DNS resolution, reachability checks, redirect following, or aggressive canonicalization.

Custom alias guardrails include:

- Strict ASCII allowlist and length boundaries.
- No leading or trailing hyphen.
- No slash, backslash, traversal input, query or fragment characters, encoded routing attempts, controls, unsupported punctuation, Unicode/homoglyph/emoji aliases, complete URLs, or reserved application names.

Errors are sanitized. API responses do not expose SQL statements, table or constraint details, connection strings, driver exceptions, stack traces, or implementation internals.

These are application-level validation and guardrail tests, not a formal penetration test.

## Privacy Scope

The model intentionally does not persist:

- Visitor IP address.
- User-agent.
- Geographic information.
- Visitor identity.
- Detailed click-history telemetry.

Analytics are limited to `redirect_count` and `last_accessed_at`. This reduces unnecessary data collection but is not a formal privacy audit.

## Key Architecture Decisions

- FastAPI for routing and the HTTP layer.
- Pydantic for API contracts, structural validation, and OpenAPI metadata.
- SQLAlchemy for engine, session, model, and persistence abstraction.
- PostgreSQL as the durable source of truth.
- A database unique constraint as the final collision authority.
- One stateless application service rather than microservices.
- Environment-driven `DATABASE_URL` and `PUBLIC_BASE_URL`.
- No Redis until measured scale justifies caching and invalidation complexity.
- No authentication or ownership in the assessment scope.
- No alias expiration, editing, or moderation.
- No destination-reputation or malware service.
- No click-event pipeline, queue, or event stream.
- No runtime LLM dependency.

## AI-Assisted Engineering Boundary

AI/Codex accelerated requirement interpretation, decomposition, implementation, test generation, debugging, refinement, documentation, and review preparation. Each bounded task stopped for engineer review. The engineer retained responsibility for decisions, correctness, validation, security, maintainability, and production-readiness judgment.

The running URL-shortener application does not call OpenAI, Codex, Claude, Gemini, or another LLM.

## Phase Evolution

### Phase 1 — Greenfield Core

**Business need:** Create durable, shareable short links.

**Delivered:** Destination validation, meaningful generated codes, PostgreSQL persistence, concurrency-safe uniqueness, bounded collision retries, commit-before-response creation, configured public URLs, `307` redirects, and health/API validation.

### Phase 2 — Brownfield Analytics

**Business need:** Add lightweight usage visibility without replacing the working Phase 1 service.

**Delivered:** Additive analytics columns, an explicit schema migration for existing rows, atomic redirect count/timestamp updates committed before `307`, and a read-only analytics endpoint. Existing creation and redirect contracts remained intact.

### Phase 3 — Ambiguous Custom Alias Requirement

**Business need:** Let callers choose the memorable alias portion of a short URL.

**Clarified and delivered:** Optional `custom_alias`, lowercase canonical storage, explicit allowlist and routing guardrails, global uniqueness, `409` conflicts with no alias substitution, compatibility with case-sensitive generated Base62 codes, and unchanged Phase 1 automatic generation when the field is omitted or `null`.

Across all three phases, the architecture evolved additively: one service, one source of truth, clear service boundaries, and regression-validated compatibility rather than unnecessary infrastructure expansion.
