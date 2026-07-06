# Maintenance and Scalability Guide

## 1. Versioning policy

| Artifact | Version format | Notes |
| --- | --- | --- |
| API | `/api/v1` | Do not break old response fields without new version |
| Risk formula | `risk-v1`, `risk-v2` | Record weights, features, changelog |
| Match formula | `match-v1`, `match-v2` | Record feature changes and tests |
| Dataset schema | `schema-v1` | Migration notes required |
| Seed data | `seed-YYYYMMDD` | Deterministic generation |

## 2. Updating data schema

Process:

1. Add proposal in changelog: new field, type, required/optional, default.
2. Update `docs/03-data-dictionary.md`.
3. Update Pydantic/TypeScript types.
4. Update seed generator and validation script.
5. Add migration for existing CSV/DB.
6. Add tests for old and new data.

Example:

- Add `cold_chain_required: boolean` to products.
- Match formula can penalize suppliers without cold chain.

## 3. Adding a new industry

Steps:

1. Define product taxonomy and specs.
2. Define quality/certification requirements.
3. Tune match weights if industry needs differ.
4. Create synthetic seed scenario.
5. Add demo story and Q&A.

Example:

- Add `pharmaceutical_distribution`.
- New specs: temperature range, license, batch traceability, expiry handling.
- Higher weight for compliance and cold-chain reliability.

## 4. Adding a scoring feature

Steps:

1. Define business meaning and data source.
2. Add normalization function.
3. Decide weight and threshold impact.
4. Update `risk-v2` docs.
5. Write unit tests and sensitivity tests.
6. Backtest if pilot data exists.
7. Explain user-facing message.

Do not silently change score weights in production.

## 5. Adding a matching algorithm

Options:

- `match-v1`: weighted score.
- `match-v2`: weighted score + hard constraints by category/compliance.
- `match-v3`: learning-to-rank when there is enough interaction/outcome data.

Rules:

- Keep reason codes.
- Keep deterministic fallback.
- Compare new ranking against old with fixed fixtures.
- Track hit_rate@3 and conversion rate.

## 6. Migrating CSV/JSON to PostgreSQL/PostGIS

Phase path:

1. Create tables matching data dictionary.
2. Load CSV into staging tables.
3. Validate PK/FK/ranges.
4. Add indexes on `business_id`, `province`, `product_category`.
5. Use PostGIS geometry for lat/lng.
6. Keep API responses unchanged.

Nguon: [PostgreSQL docs](https://www.postgresql.org/docs/current/), [PostGIS docs](https://postgis.net/documentation/).

## 7. Migrating graph to Neo4j or graph service

Stay with relational/adjacency list while:

- Graph < 100k edges.
- Queries are simple downstream traversal and neighborhood lookup.

Consider Neo4j when:

- Multi-hop pathfinding becomes frequent.
- Need relationship queries, centrality/community detection at scale.
- Business users ask graph exploration beyond map.

Nguon: [Neo4j Cypher Manual](https://neo4j.com/docs/cypher-manual/current/), [NetworkX](https://networkx.org/documentation/stable/reference/algorithms/centrality.html).

## 8. API versioning

- Additive fields allowed in `/api/v1`.
- Removing/renaming fields requires `/api/v2`.
- Deprecated fields get `deprecated_at` and migration note.
- Error codes remain stable.
- OpenAPI schema checked in CI.

Nguon: [OpenAPI Specification](https://spec.openapis.org/oas/latest.html).

## 9. Monitoring

MVP:

- Log request ID, route, latency, status code.
- Log data validation failures.
- Log shock simulation failures.

Pilot/production:

- API latency p50/p95.
- Error rate by endpoint.
- Data import success/failure.
- Recommendation empty rate.
- Risk score distribution drift.
- Consent/audit events.
- Security events.

## 10. Backup and restore

MVP:

- Git-tracked seed files.
- Backup demo video.

Pilot/production:

- Daily database backup.
- Object storage backup for uploaded raw files.
- Restore rehearsal monthly.
- Separate backup of env/deploy config.
- Document RPO/RTO.

## 11. Dependency and security patching

- Pin dependencies.
- Use Dependabot/Renovate or scheduled update.
- Run tests before merge.
- Monitor security advisories.
- Rotate secrets after incident.
- Keep `.env.example` updated, never commit real `.env`.

Nguon: [OWASP Secrets Management](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html), [Twelve-Factor Config](https://12factor.net/config).

## 12. Changelog template

```md
## YYYY-MM-DD

### Added
- ...

### Changed
- ...

### Fixed
- ...

### Risk/Model Notes
- Formula version:
- Impact:
- Tests:
```

## 13. Operational runbook

| Symptom | Check | Action |
| --- | --- | --- |
| Map blank | API graph, tile provider, console error | Switch mock data or cached map |
| Shock returns no affected nodes | Seed edges, product filter, shock node | Use default shock node, run validation |
| Recommendation empty | Candidate filters too strict | Show no-candidate reasons, loosen optional filters |
| Risk score weird | Feature normalization | Run risk unit tests and inspect drivers |
| API 500 | Logs by request_id | Return safe error, open issue |

## 14. Scale roadmap by component

| Component | MVP | Pilot | Production |
| --- | --- | --- | --- |
| Data | CSV/JSON | PostgreSQL | PostgreSQL + PostGIS + data lake |
| Graph | In-memory adjacency | SQL adjacency + NetworkX jobs | Neo4j/graph service if needed |
| AI | Rule-based + templates | Backtesting + calibration | ML model + monitoring |
| Security | Synthetic only | Auth/RBAC/consent | Full governance/audit/compliance |
| Deploy | Manual/simple cloud | Docker + staging | CI/CD + observability |
