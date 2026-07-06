# VietSupply Radar Migrations

- `versions/*.sql` are production-target PostgreSQL/PostGIS/Alembic-style migration artifacts.
- The runtime still uses the SQLite demo adapter until a PostgreSQL repository adapter is wired.
- Pilot/production must apply these migrations, set request session variables, and run DB-level RLS tests before accepting real SME data.

Required request session variables:

- `app.tenant_id`
- `app.actor_id`
- `app.organization_ids`
- `app.purpose`
- `app.scopes`
