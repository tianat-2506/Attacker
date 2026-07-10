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

    def test_admin_ops_registry_endpoints_expose_seeded_demo_manifest(self) -> None:
        client = TestClient(app)
        headers = {
            "X-Tenant-Id": "tenant-demo",
            "X-Organization-Id": "BIZ-005",
            "X-Actor-Id": "demo-admin",
            "X-Actor-Role": "demo_admin",
            "X-Purpose": "ops_governance_review",
            "X-Demo-Scopes": "demo:read policy:override",
        }

        models = client.get("/api/v1/admin/model-registry", headers=headers)
        rulesets = client.get("/api/v1/admin/ruleset-registry", headers=headers)

        self.assertEqual(models.status_code, 200)
        self.assertEqual(rulesets.status_code, 200)
        self.assertEqual(
            {(item["artifact_type"], item["model_version"]) for item in models.json()["data"]["models"]},
            {
                ("risk", "deterministic-demo-v0.1"),
                ("scenario", "deterministic-demo-v0.1"),
            },
        )
        self.assertEqual(
            {(item["artifact_type"], item["ruleset_version"]) for item in rulesets.json()["data"]["rulesets"]},
            {
                ("feature", "intake-feature-set-v0.1-demo"),
                ("matching", "supplier-shortlist-rules-v0.1"),
                ("risk", "intake-risk-rules-v0.1"),
                ("scenario", "scenario-rules-v0.1"),
            },
        )


if __name__ == "__main__":
    unittest.main()
