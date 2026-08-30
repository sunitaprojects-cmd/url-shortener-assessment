# AI-Assisted Engineering Log

This selective log records material AI-assisted engineering decisions rather than every interaction. AI output was input to engineer review, not autonomous approval or execution.

| Stage / Task | AI Assistance | Engineer Review / Decision | Status | Rationale | Validation Evidence |
|---|---|---|---|---|---|
| Initial planning | Proposed a broader production-oriented architecture and phased plan. | Narrowed scope to a defensible assessment-sized implementation and strengthened business-to-engineering traceability. | Modified | Deliver a reliable core in the available assessment window without hiding production risks. | Approved bounded Phase 1 plan and task-by-task review. |
| Phase 1 configuration and schema | Connected environment configuration and initial schema setup. | Identified that schema creation unnecessarily required `PUBLIC_BASE_URL`; separated database-only initialization. | Modified | Schema setup should require only configuration it uses. | Database integration and full regression tests passed after refinement. |
| Phase 1 manual validation | Automated tests exercised the test database. | Investigated a Swagger `503` against `shortlink_dev`, found its schema uninitialized, initialized it, and reran successfully. | Debugged / validated | Automated tests did not prove the separately configured development environment was initialized. | Successful NASA create-and-browser-redirect flow after correction. |
| Phase 2 brownfield design | Codebase analysis identified that `create_all()` would not evolve the Phase 1 table. | Approved one explicit additive SQL migration instead of a full migration framework. | Accepted with bounded scope | Safely evolve existing rows without adding unnecessary infrastructure. | Migration and existing-row integration coverage passed. |
| Phase 2 analytics consistency | Presented transaction and availability tradeoffs. | Chose atomic database arithmetic and commit-before-redirect consistency; documented asynchronous analytics as a future option. | Accepted with documented tradeoff | Ensure every successful redirect response is represented in analytics. | Increment, timestamp, rollback, failure, and API tests passed. |
| Phase 3 ambiguity resolution | Enumerated unresolved product and routing questions. | Decided case behavior, allowed characters, length, repeated hyphens, reserved routes, conflicts, namespace interaction, and authentication/ownership deferral before implementation. | Human decision before implementation | Prevent ambiguous requirements from silently becoming unsafe API behavior. | Guardrail, conflict, routing, and compatibility tests passed. |
| Phase 3 validation refinement | Inspection and testing exposed a mechanical placement defect in strict generated-code validation. | Corrected it before final acceptance and preserved separate generated and routable validation responsibilities. | Modified after review | Custom aliases must not weaken the strict generated-code contract. | Focused and full regression validation passed. |
| Swagger usability | Existing fields were technically valid but easy to misunderstand. | Improved descriptions and examples to distinguish destination URLs from alias-only input without changing field names or behavior. | Modified | Reduce reviewer and caller ambiguity. | Focused API tests confirmed complete URLs remain invalid aliases. |
| Final validation benchmark | Implemented a deliberate benchmark across eight risk categories rather than adding arbitrary test volume. | Reviewed a benchmark-only isolation failure: three deterministic boundary aliases were missing from cleanup. Cleanup was corrected; no application defect was found. | Validation refinement | Deterministic tests must remain repeatable across standalone and full-suite runs. | Benchmark 100/100; complete regression 236/236. |

## Tool Responsibilities

**ChatGPT** supported requirement interpretation, business framing, architecture reasoning, ambiguity resolution, risk and tradeoff reasoning, validation strategy, and reviewer/interview framing.

**Codex in VS Code** supported repository-aware implementation, codebase inspection, test generation, debugging, refactoring, regression execution, and repository/documentation review.

The engineer remained responsible for final scope, architecture, implementation acceptance, correctness, maintainability, security, and production-readiness decisions. AI outputs were not automatically accepted, and every major phase was reviewed and validated before progression.

The runtime application contains no LLM dependency. No proprietary external code was supplied to or incorporated into this assessment.

> AI assists the engineer within tasks; the engineer owns execution and quality.
