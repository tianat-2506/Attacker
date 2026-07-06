from __future__ import annotations

import unittest


try:
    from backend.app.main import app
except Exception:  # pragma: no cover - optional FastAPI import path in domain-only environments.
    app = None


@unittest.skipIf(app is None, "FastAPI app is unavailable")
class ApiAuthContractTests(unittest.TestCase):
    def test_only_health_route_is_public_under_api_v1(self) -> None:
        public_paths: list[str] = []
        for route in app.routes:
            path = getattr(route, "path", "")
            if not path.startswith("/api/v1/"):
                continue
            dependency_names = {
                getattr(getattr(dependency, "call", None), "__name__", "")
                for dependency in getattr(getattr(route, "dependant", None), "dependencies", [])
            }
            if "request_context" not in dependency_names:
                public_paths.append(path)

        self.assertEqual(public_paths, ["/api/v1/health"])


if __name__ == "__main__":
    unittest.main()
