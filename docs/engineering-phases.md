# Engineering Phases

## Phase 1 — Greenfield: Core URL Shortener

### Business Problem / Value

Long URLs are difficult to share, transcribe, and present in constrained channels. Phase 1 creates durable, compact URLs that reliably resolve to their original HTTP or HTTPS destinations. Persistent mappings retain value beyond one process lifetime and establish the foundation for later capabilities.

### Requirement Interpretation

The greenfield requirement became a minimum complete flow: accept a valid destination, create a readable and unique code, persist it transactionally, return a configured public URL, and resolve the code with a redirect. Correctness, durability, explicit failure behavior, and verification took priority over additional infrastructure.

### Decomposition

1. Environment-driven configuration and dependencies.
2. SQLAlchemy session management and PostgreSQL persistence.
3. HTTP/HTTPS validation with minimal normalization.
4. Meaningful generated codes with secure random suffixes.
5. Transactional creation service.
6. `POST /api/v1/urls`.
7. `GET /{code}` redirect resolution.

### Execution

The implementation connected configuration, persistence, validation, code generation, creation, and redirect behavior in bounded tasks. Manual Swagger and browser validation exercised the deployed flow after automated testing.

### Engineering Decisions

- One stateless FastAPI service using SQLAlchemy and PostgreSQL.
- `DATABASE_URL` and trusted `PUBLIC_BASE_URL` supplied through the environment.
- Meaningful slug plus an eight-character, cryptographically secure Base62 suffix.
- Named PostgreSQL unique constraint as the final collision authority.
- Rollback and retry for generated-code collisions, bounded to five attempts.
- Commit before reporting creation success.
- `307 Temporary Redirect` for resolution.
- No Redis, microservices, or queues.

### AI-Assisted Engineering / Human Oversight

AI assisted with proposals, implementation, tests, debugging, and refinement within explicit tasks. Engineer review narrowed the initial production-oriented design to assessment scope, completed a missed Ruff gate, and removed unnecessary coupling between schema initialization and `PUBLIC_BASE_URL`. Each task stopped for review before the next began.

### Validation

Phase 1 completed with 68 automated tests, PostgreSQL integration coverage, Ruff lint and formatting, Python compilation, and `git diff --check` passing.

Manual validation included:

- Creating a short URL for `https://www.nasa.gov/missions/artemis/`, receiving an `artemis-` code, and successfully redirecting in a browser.
- Confirming invalid FTP, missing-hostname, credential-bearing, and whitespace-containing destinations returned `422`, while valid HTTP/HTTPS URLs returned `201`.
- Confirming repeat submissions of one destination produced distinct codes by design.
- Confirming a modified unknown code returned sanitized `404 short_url_not_found` rather than an incorrect redirect.

The first manual request against `shortlink_dev` returned `503` even though automated tests against `shortlink_test` passed. Human investigation found the development schema had not been initialized. After initialization, the same end-to-end request succeeded. This demonstrated the value of retaining a human runtime validation gate.

### Risks / Deferred Scope

Analytics, custom aliases, caching, UI, a full migration framework, load testing, and production observability were deferred. They remained known considerations rather than being treated as solved.

### Outcome

Phase 1 delivered and validated the complete **create → persist → resolve → redirect** foundation.

## Phase 2 — Brownfield: Lightweight Redirect Analytics

### Business Problem / Value

Existing short links provided no usage visibility. Phase 2 added a small, useful measure of link activity without replacing the working Phase 1 application.

### Requirement Interpretation

Analytics meant aggregate redirect usage only: a count and latest-access timestamp updated on each successful redirect, plus a read-only endpoint. Detailed events and visitor telemetry were not implied.

### Decomposition

1. Evolve the Phase 1 schema additively.
2. Add transactional redirect analytics.
3. Add a read-only analytics endpoint.

### Execution

`redirect_count` and `last_accessed_at` were added to `UrlMapping`. An explicit SQL migration supported existing Phase 1 databases. Redirect resolution became an atomic PostgreSQL `UPDATE ... RETURNING`, and `GET /api/v1/urls/{code}/analytics` exposed the stored aggregates without mutation.

### Engineering Decisions

- Additive migration because SQLAlchemy `create_all()` creates missing tables but does not evolve existing ones.
- Existing rows receive count `0` and nullable latest-access time.
- Database-side arithmetic prevents application-level lost updates.
- Commit the analytics update before returning `307`.
- Preserve sanitized `404` and `503` behavior.
- No asynchronous event pipeline, Redis, or detailed click history.

### AI-Assisted Engineering / Human Oversight

AI-assisted impact analysis identified the schema-evolution constraint and consistency choices. The engineer approved a bounded SQL migration instead of Alembic and deliberately selected strict commit-before-redirect consistency while retaining ownership of the availability tradeoff.

### Validation

Database, service, API, and regression tests covered defaults, migration, atomic increments, timestamps, read-only analytics, and failures. Manual validation exercised **create → analytics 0 → redirect → analytics 1**. Phase 1 creation and redirect behavior remained compatible.

### Risks / Deferred Scope

Strict consistency means an analytics database failure can block a redirect. Concurrency/load testing, asynchronous delivery, event history, dashboards, and production analytics infrastructure were deferred.

### Outcome

Phase 2 added useful aggregate visibility through an additive brownfield change without redesigning the Phase 1 service.

## Phase 3 — Ambiguous Requirement: Custom Aliases

### Business Problem / Value

The original request—“Users should be able to choose their own short URL.”—sought memorable, campaign-friendly links but did not define the safety or ownership rules needed to implement them correctly.

### Requirement Interpretation

Engineer clarification resolved case behavior, allowed characters, length, reserved routes, conflict semantics, global uniqueness, generated/custom namespace interaction, expiration, authentication and ownership, editing, and moderation before implementation.

### Decomposition

1. Add custom-alias normalization, guardrails, and routable-code validation.
2. Add transactional custom-alias creation to the existing API and service.
3. Validate end-to-end compatibility across creation, redirects, analytics, and generated codes.

### Execution

`POST /api/v1/urls` gained an optional `custom_alias`. The existing automatic path remains unchanged when it is omitted or `null`. Requested aliases are validated before persistence, normalized to lowercase, attempted once, and stored in the existing globally unique `short_code` column.

### Engineering Decisions

- Creation accepts uppercase letters and stores canonical lowercase.
- Length is 3–32 characters.
- ASCII letters, digits, and internal hyphens are permitted.
- Aliases must begin and end with an alphanumeric character; repeated internal hyphens are valid.
- Reserved application routes are rejected.
- Generated and custom codes share one global namespace.
- Custom conflicts return `409`; the service does not retry, substitute, or reveal the existing mapping.
- Generated Base62 codes remain case-sensitive.
- Incoming redirect codes are not globally lowercased.
- Expiration, authentication, ownership, editing, and moderation are out of scope.

### AI-Assisted Engineering / Human Oversight

AI helped enumerate ambiguity and implementation impact. The engineer made the behavioral decisions before code was changed, reviewed each bounded task, and refined validation and Swagger descriptions without changing the established API contract.

### Validation

Focused and end-to-end tests covered custom creation, lowercase normalization, redirect, analytics before and after redirects, duplicate conflicts, guardrails, and generated-code backward compatibility. Manual Swagger validation supplemented automation. Final validation recorded a deterministic 100/100 engineering benchmark and a 236/236 complete regression suite with no Phase 1 or Phase 2 regression.

### Risks / Deferred Scope

Without authentication or ownership, aliases are first-come globally and cannot be edited or reclaimed. Moderation, expiration, abuse workflows, and account-level controls remain deferred production concerns.

### Outcome

Phase 3 converted an ambiguous request into explicit, guarded behavior while preserving automatic generated codes, redirects, and analytics.

## Overall AI-Assisted Delivery Model

The engineer retained ownership of scope, architecture, correctness, security, validation, and acceptance. AI outputs were reviewed and sometimes modified rather than accepted automatically. The application has no runtime LLM dependency.
