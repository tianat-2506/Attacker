from __future__ import annotations

import unittest
from unittest.mock import patch
from urllib.request import Request

from scripts import run_evidence_object_storage_smoke as smoke


class _FakeResponse:
    def __init__(self, status: int, body: bytes = b"") -> None:
        self.status = status
        self._body = body

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        return self._body


class EvidenceObjectStorageSmokeTests(unittest.TestCase):
    def test_live_smoke_requires_put_get_and_delete_cleanup(self) -> None:
        env = {
            "EVIDENCE_OBJECT_STORE_ENDPOINT": "https://minio.example",
            "EVIDENCE_OBJECT_STORE_BUCKET": "pilot-evidence",
            "EVIDENCE_OBJECT_STORE_ACCESS_KEY_ID": "access-key",
            "EVIDENCE_OBJECT_STORE_SECRET_ACCESS_KEY": "secret-key",
            "EVIDENCE_OBJECT_STORE_REGION": "ap-southeast-1",
        }
        calls: list[tuple[str, str]] = []

        def fake_urlopen(request: Request | str, timeout: float = 0) -> _FakeResponse:
            method = request.get_method() if isinstance(request, Request) else "GET"
            url = request.full_url if isinstance(request, Request) else request
            calls.append((method, str(url)))
            if method == "PUT":
                return _FakeResponse(200)
            if method == "GET":
                return _FakeResponse(200, b"object-smoke")
            if method == "DELETE":
                return _FakeResponse(204)
            raise AssertionError(f"Unexpected method {method}")

        with patch.object(smoke, "urlopen", side_effect=fake_urlopen):
            report = smoke.run_smoke(env=env, content=b"object-smoke")

        checks = {item["name"]: item for item in report["checks"]}
        self.assertEqual(report["overall_status"], "pass")
        self.assertTrue(report["pilot_ready"])
        self.assertEqual([method for method, _ in calls], ["PUT", "GET", "DELETE"])
        self.assertEqual(checks["object_storage_delete"]["status"], "pass")
        self.assertIn("PUT, GET and DELETE cleanup", report["notice"])
        self.assertNotIn("secret-key", str(report))

    def test_live_smoke_fails_when_delete_cleanup_fails(self) -> None:
        env = {
            "EVIDENCE_OBJECT_STORE_ENDPOINT": "https://minio.example",
            "EVIDENCE_OBJECT_STORE_BUCKET": "pilot-evidence",
            "EVIDENCE_OBJECT_STORE_ACCESS_KEY_ID": "access-key",
            "EVIDENCE_OBJECT_STORE_SECRET_ACCESS_KEY": "secret-key",
        }

        def fake_urlopen(request: Request | str, timeout: float = 0) -> _FakeResponse:
            method = request.get_method() if isinstance(request, Request) else "GET"
            if method == "PUT":
                return _FakeResponse(200)
            if method == "GET":
                return _FakeResponse(200, b"object-smoke")
            if method == "DELETE":
                return _FakeResponse(403)
            raise AssertionError(f"Unexpected method {method}")

        with patch.object(smoke, "urlopen", side_effect=fake_urlopen):
            report = smoke.run_smoke(env=env, content=b"object-smoke")

        checks = {item["name"]: item for item in report["checks"]}
        self.assertEqual(report["overall_status"], "fail")
        self.assertFalse(report["pilot_ready"])
        self.assertEqual(checks["object_storage_delete"]["status"], "fail")


if __name__ == "__main__":
    unittest.main()
