# Testing Strategy

Testing combines focused isolation with PostgreSQL-backed evidence and manual review:

- **Unit tests** cover configuration, destination validation, short-code generation, custom-alias guardrails, and service decisions.
- **Database integration tests** cover schema creation/evolution, persistence, unique constraints, transactions, and fresh-session reads.
- **API tests** verify response contracts, status and error mappings, configured public URLs, redirects, and analytics.
- **End-to-end flow tests** cross service boundaries for generated and custom creation, resolution, and analytics.
- **Manual Swagger/browser validation** confirms the running application and configured development database behave together.
- **Deterministic engineering benchmark** provides a fixed, reviewable cross-phase validation set.

## Engineering Validation Benchmark

`tests/test_engineering_benchmark.py` defines exactly 100 parameterized scenarios and asserts both the total and expected category distribution:

| Category | Result |
|---|---:|
| Core functional flows | 20/20 |
| Boundary and edge cases | 15/15 |
| Guardrails and security/input abuse | 20/20 |
| Routing and namespace integrity | 10/10 |
| Persistence and failure handling | 10/10 |
| Cross-phase regression compatibility | 10/10 |
| Destination URL semantic preservation | 10/10 |
| Information exposure and privacy | 5/5 |
| **Total** | **100/100** |

The benchmark is deterministic and reuses controlled fixtures and injected failure paths. It is an engineering validation benchmark, not a penetration test.

## Complete Validation State

- Engineering benchmark: **100/100 passed**
- Complete regression suite: **236/236 passed**
- Ruff lint: passed
- Ruff formatting: passed
- Python compilation: passed
- `git diff --check`: passed

## Manual Validation

Completed Swagger and browser checks included:

- Generated URL creation and browser redirect.
- Invalid destination validation, including unsupported scheme and malformed hostname.
- Rejection of embedded credentials and whitespace.
- Repeated creation of one destination producing distinct generated codes by design.
- An unknown modified code returning sanitized `404 short_url_not_found`.
- Analytics at zero before redirect and incremented after redirect.
- Uppercase custom alias input normalized to lowercase.
- Custom-alias redirect and analytics behavior.
- Duplicate custom alias returning `409 custom_alias_conflict`.

## Defect / Test Harness Finding

The first complete-suite rerun after the standalone benchmark exposed a benchmark isolation issue. Three deterministic boundary aliases were absent from benchmark cleanup and remained in the test database, causing correct `409` conflicts on the second run.

Benchmark cleanup was corrected; no application code changed. After correction, the benchmark passed 100/100 and the complete regression suite passed 236/236. This finding demonstrates that test harnesses themselves require iterative validation and review.

## Testing Limitations

- Deterministic application validation, not formal penetration testing.
- No concurrency, load, soak, capacity, or performance benchmark.
- Database failure paths use controlled injection.
- No formal privacy audit.
- No destination reachability or external reputation checks.
- Analytics contain aggregate count and latest-access time only.
- The accepted `TestClient` deprecation warning remains a maintenance observation; dependencies were not changed solely to suppress it.
