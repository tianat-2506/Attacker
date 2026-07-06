from __future__ import annotations

import unittest


try:
    from backend.app.main import app
except Exception:  # pragma: no cover - optional FastAPI import path in domain-only environments.
    app = None

try:
    from fastapi.testclient import TestClient
except Exception:  # pragma: no cover - TestClient requires optional httpx2 in this environment.
    TestClient = None  # type: ignore[assignment]


@unittest.skipIf(app is None, "FastAPI app is unavailable")
class AdminOpsRouteRegistrationTests(unittest.TestCase):
    def test_admin_ops_routes_are_registered(self) -> None:
        route_paths = {getattr(route, "path", "") for route in app.routes}
        self.assertIn("/api/v1/admin/model-registry", route_paths)
        self.assertIn("/api/v1/admin/ruleset-registry", route_paths)
        self.assertIn("/api/v1/admin/recompute-jobs", route_paths)


@unittest.skipIf(TestClient is None or app is None, "FastAPI TestClient is unavailable")
class AdminOpsApiTests(unittest.TestCase):
    def test_admin_ops_endpoints_require_admin_policy(self) -> None:
        client = TestClient(app)

        allowed = client.get(
            "/api/v1/admin/recompute-jobs",
            headers={
                "X-Tenant-Id": "tenant-demo",
                "X-Organization-Id": "BIZ-009",
                "X-Actor-Id": "demo-admin",
                "X-Actor-Role": "demo_admin",
                "X-Purpose": "ops_governance_review",
                "X-Demo-Scopes": "demo:read policy:override",
            },
        )
        denied = client.get(
            "/api/v1/admin/recompute-jobs",
            headers={
                "X-Tenant-Id": "tenant-demo",
                "X-Organization-Id": "BIZ-009",
                "X-Actor-Id": "org-admin",
                "X-Actor-Role": "org_admin",
                "X-Purpose": "ops_governance_review",
                "X-Demo-Scopes": "demo:read",
            },
        )

        self.assertEqual(allowed.status_code, 200)
        self.assertIn("jobs", allowed.json()["data"])
        self.assertEqual(denied.status_code, 403)
        self.assertEqual(denied.json()["detail"]["code"], "ACCESS_DENIED")


if __name__ == "__main__":
    unittest.main()
