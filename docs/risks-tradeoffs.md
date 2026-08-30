# Risks and Tradeoffs

## PostgreSQL as Source of Truth

PostgreSQL provides one durable authority for mappings, uniqueness, and aggregate analytics. This keeps the assessment simple and consistent. Redis or another cache is deferred until measured traffic justifies cache and invalidation complexity.

## Generated-Code Collisions

The PostgreSQL unique constraint is the final concurrency-safe authority. Generated collisions roll back and retry with a new candidate, bounded to five attempts. Exhaustion returns a sanitized service-unavailable error rather than claiming success.

## Custom-Alias Collisions

A requested alias conflict returns `409` without silent substitution or reuse. Without authentication or ownership, returning an existing mapping could be misleading and could disclose information about another caller's link.

## Strict Analytics Consistency

The redirect count and latest timestamp commit before a successful `307`, so every successful redirect response is represented in the aggregate. The tradeoff is that an analytics database failure blocks the redirect. A production system could decouple analytics asynchronously if redirect availability becomes more important than strict count consistency.

## `307 Temporary Redirect`

A temporary redirect avoids encouraging long-lived permanent client caching while expiration, editing, and link mutability remain deliberately simple.

## Minimal URL Normalization

Validation lowercases scheme and hostname but preserves path, query, fragment, explicit port, and encoding semantics. This avoids unintentionally changing destinations through aggressive canonicalization.

## No Destination Deduplication

The same original URL may intentionally create multiple generated links. Uniqueness applies to `short_code`, not `original_url`.

## Custom-Alias Casing

Custom-alias creation is case-insensitive and stores canonical lowercase. Generated Base62 suffixes retain case sensitivity, so incoming redirect codes are not globally lowercased.

## Security Boundary

Structured URL validation and alias allowlists protect application and routing behavior. The prototype does not provide malware/phishing reputation screening, destination reachability verification, or formal penetration testing.

## Privacy

Analytics store only an aggregate redirect count and latest-access timestamp. The service does not persist IP addresses, user-agents, geographic data, visitor identities, or detailed click events. This limited collection is not a formal privacy audit.

## Scalability

The stateless FastAPI application can conceptually scale horizontally against PostgreSQL. No proven capacity claim is made because concurrency, load, soak, and capacity testing were not performed.

## Deferred Scope

- Authentication and ownership
- Expiration, editing, and moderation
- Redis or another cache
- Queues, event streaming, and detailed click events
- Full migration framework such as Alembic
- Production logging, metrics, tracing, and alerting
- Formal security and privacy testing
- Load, concurrency, soak, and capacity testing
