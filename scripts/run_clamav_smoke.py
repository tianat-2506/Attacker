from __future__ import annotations

import argparse
import json
import os
import socket
import struct
from dataclasses import asdict, dataclass
from typing import Any, Callable


SocketFactory = Callable[[tuple[str, int], float], socket.socket]
EICAR_TEST_BYTES = b"X5O!P%@AP[4\\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*"


@dataclass(frozen=True)
class SmokeCheck:
    name: str
    status: str
    message: str


def run_smoke(
    *,
    env: dict[str, str] | None = None,
    timeout_seconds: float = 10.0,
    socket_factory: SocketFactory | None = None,
) -> dict[str, Any]:
    active_env = env if env is not None else os.environ
    scanner = active_env.get("EVIDENCE_MALWARE_SCANNER", "").strip().lower()
    host = active_env.get("CLAMAV_HOST", "").strip()
    port_raw = active_env.get("CLAMAV_PORT", "").strip() or "3310"
    checks: list[SmokeCheck] = []
    try:
        port = int(port_raw)
    except ValueError:
        port = 0

    if scanner != "clamav" or not host or not (1 <= port <= 65535):
        checks.append(
            SmokeCheck(
                "clamav_config",
                "fail",
                "Missing ClamAV config. Set EVIDENCE_MALWARE_SCANNER=clamav, CLAMAV_HOST and CLAMAV_PORT.",
            )
        )
        return _report(checks, host=host, port=port)

    checks.append(SmokeCheck("clamav_config", "pass", "ClamAV config is present."))
    clean = _scan_bytes(
        b"vietsupply-clamav-clean-live-smoke\n",
        host=host,
        port=port,
        timeout_seconds=timeout_seconds,
        socket_factory=socket_factory,
    )
    if clean["status"] == "clean":
        checks.append(SmokeCheck("clamav_clean_scan", "pass", "Clean payload was accepted by ClamAV."))
    else:
        checks.append(
            SmokeCheck(
                "clamav_clean_scan",
                "fail",
                f"Clean payload returned {clean['status']}: {clean['reason']}.",
            )
        )
        return _report(checks, host=host, port=port)

    infected = _scan_bytes(
        EICAR_TEST_BYTES,
        host=host,
        port=port,
        timeout_seconds=timeout_seconds,
        socket_factory=socket_factory,
    )
    if infected["status"] == "infected":
        checks.append(SmokeCheck("clamav_eicar_scan", "pass", "EICAR test payload was detected by ClamAV."))
    else:
        checks.append(
            SmokeCheck(
                "clamav_eicar_scan",
                "fail",
                f"EICAR test payload returned {infected['status']}: {infected['reason']}.",
            )
        )
    return _report(checks, host=host, port=port)


def _scan_bytes(
    content: bytes,
    *,
    host: str,
    port: int,
    timeout_seconds: float,
    socket_factory: SocketFactory | None = None,
) -> dict[str, str]:
    try:
        factory = socket_factory or socket.create_connection
        client = factory((host, port), timeout_seconds)
        try:
            client.sendall(b"zINSTREAM\0")
            chunk_size = 1024 * 1024
            for index in range(0, len(content), chunk_size):
                chunk = content[index : index + chunk_size]
                client.sendall(struct.pack(">I", len(chunk)))
                client.sendall(chunk)
            client.sendall(struct.pack(">I", 0))
            response_parts: list[bytes] = []
            while True:
                part = client.recv(4096)
                if not part:
                    break
                response_parts.append(part)
                if b"\0" in part or b"\n" in part:
                    break
        finally:
            client.close()
    except OSError as exc:
        return {"status": "failed", "reason": f"clamav_unavailable:{exc.__class__.__name__}"}

    response = b"".join(response_parts).decode("utf-8", errors="replace").strip("\0\r\n ")
    if " FOUND" in response:
        return {"status": "infected", "reason": f"clamav:{response}"}
    if response.endswith("OK") or " OK" in response:
        return {"status": "clean", "reason": f"clamav:{response}"}
    return {"status": "failed", "reason": f"clamav_unrecognized_response:{response[:120]}"}


def _report(checks: list[SmokeCheck], *, host: str, port: int) -> dict[str, Any]:
    failed = [check for check in checks if check.status == "fail"]
    return {
        "overall_status": "fail" if failed else "pass",
        "pilot_ready": not failed,
        "host": host,
        "port": port,
        "checks": [asdict(check) for check in checks],
        "failed_checks": [check.name for check in failed],
        "notice": "Live malware scanner proof scans one clean payload and the harmless EICAR antivirus test payload.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run live ClamAV clean/infected smoke for evidence scanning.")
    parser.add_argument("--timeout", type=float, default=10.0, help="ClamAV TCP timeout in seconds.")
    parser.add_argument("--json", action="store_true", help="Print only the JSON report.")
    args = parser.parse_args()

    report = run_smoke(timeout_seconds=args.timeout)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"ClamAV smoke: {report['overall_status']}")
        for check in report["checks"]:
            print(f"- {check['status'].upper()} {check['name']}: {check['message']}")
        print(report["notice"])
    return 0 if report["overall_status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
