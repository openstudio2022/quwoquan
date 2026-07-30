#!/usr/bin/env python3
"""Bind one mobile CI job to one physical Mac and one exclusively leased device."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import secrets
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


PLATFORMS = ("android", "ios")
DIGEST_PATTERN = re.compile(r"sha256:[0-9a-f]{64}")
DEFAULT_LEASE_ROOT = Path("/private/tmp/quwoquan-device-leases")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    host = subparsers.add_parser("host")
    host.add_argument("--github-output", required=True, type=Path)

    acquire = subparsers.add_parser("acquire")
    acquire.add_argument("--platform", required=True, choices=PLATFORMS)
    acquire.add_argument("--expected-host-digest", required=True)
    acquire.add_argument("--runner-label", required=True)
    acquire.add_argument("--run-id", required=True)
    acquire.add_argument("--run-attempt", required=True)
    acquire.add_argument("--preferred-device-id", default="")
    acquire.add_argument("--lease-root", type=Path, default=DEFAULT_LEASE_ROOT)
    acquire.add_argument("--evidence-output", required=True, type=Path)
    acquire.add_argument("--github-output", required=True, type=Path)

    release = subparsers.add_parser("release")
    release.add_argument("--lease-evidence", required=True, type=Path)
    release.add_argument("--lease-token", required=True)
    release.add_argument("--lease-root", type=Path, default=DEFAULT_LEASE_ROOT)
    return parser


def _digest(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


def host_digest() -> str:
    result = subprocess.run(
        ["/usr/sbin/ioreg", "-rd1", "-c", "IOPlatformExpertDevice"],
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise ValueError("cannot read the macOS IOPlatformUUID")
    match = re.search(r'"IOPlatformUUID"\s*=\s*"([^"]+)"', result.stdout)
    if match is None or not match.group(1).strip():
        raise ValueError("macOS IOPlatformUUID is missing")
    return _digest("quwoquan-mobile-runner\0" + match.group(1).strip().lower())


def _flutter_devices() -> list[dict[str, Any]]:
    result = subprocess.run(
        ["flutter", "devices", "--machine"],
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise ValueError("flutter devices --machine failed")
    raw = result.stdout or ""
    start = raw.find("[")
    end = raw.rfind("]")
    if start < 0 or end < start:
        raise ValueError("flutter devices --machine did not return a JSON array")
    payload = json.loads(raw[start : end + 1])
    if not isinstance(payload, list):
        raise ValueError("flutter devices --machine payload is invalid")
    return [item for item in payload if isinstance(item, dict)]


def select_device(platform: str, preferred_device_id: str = "") -> str:
    candidates: list[str] = []
    for device in _flutter_devices():
        target = str(device.get("targetPlatform") or "").lower()
        device_id = str(device.get("id") or "").strip()
        if not device_id:
            continue
        if platform == "android" and target.startswith("android"):
            candidates.append(device_id)
        elif platform == "ios" and target == "ios":
            candidates.append(device_id)
    if preferred_device_id:
        if preferred_device_id not in candidates:
            raise ValueError(f"preferred {platform} device is not present on this runner")
        return preferred_device_id
    if not candidates:
        raise ValueError(f"no {platform} device is present on this runner")
    return sorted(candidates)[0]


def _lease_key(platform: str, host: str, device_id_digest: str) -> str:
    return hashlib.sha256(
        f"{platform}\0{host}\0{device_id_digest}".encode("utf-8")
    ).hexdigest()


def _write_github_output(path: Path, values: dict[str, str]) -> None:
    with path.open("a", encoding="utf-8") as handle:
        for name, value in values.items():
            if "\n" in value or "\r" in value:
                raise ValueError(f"GitHub output {name} contains a newline")
            handle.write(f"{name}={value}\n")


def acquire(
    *,
    platform: str,
    expected_host_digest: str,
    runner_label: str,
    run_id: str,
    run_attempt: str,
    preferred_device_id: str,
    lease_root: Path,
    evidence_output: Path,
    github_output: Path,
) -> dict[str, str]:
    if DIGEST_PATTERN.fullmatch(expected_host_digest) is None:
        raise ValueError("expected host digest is invalid")
    expected_label = f"mobile-{platform}"
    if runner_label != expected_label:
        raise ValueError(f"runner label must be {expected_label}")
    actual_host_digest = host_digest()
    if actual_host_digest != expected_host_digest:
        raise ValueError("platform runner is not the Beta stack host")
    device_id = select_device(platform, preferred_device_id)
    device_id_digest = _digest("quwoquan-mobile-device\0" + device_id)
    lease_key = _lease_key(platform, actual_host_digest, device_id_digest)
    lease_root = lease_root.expanduser()
    if lease_root.is_symlink():
        raise ValueError("device lease root must not be a symlink")
    lease_root = lease_root.resolve()
    lease_root.mkdir(mode=0o700, parents=True, exist_ok=True)
    lock_dir = lease_root / f"{platform}-{lease_key}"
    try:
        lock_dir.mkdir(mode=0o700)
    except FileExistsError as error:
        raise ValueError(f"{platform} device already has an active lease") from error

    token = secrets.token_urlsafe(32)
    acquired_at = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    lease_id = _digest(
        "\0".join(
            (
                "quwoquan-device-lease",
                run_id,
                run_attempt,
                platform,
                actual_host_digest,
                device_id_digest,
                acquired_at,
            )
        )
    )
    owner = {
        "leaseId": lease_id,
        "tokenDigest": _digest(token),
        "runId": run_id,
        "runAttempt": run_attempt,
    }
    evidence = {
        "status": "held",
        "platform": platform,
        "hostDigest": actual_host_digest,
        "deviceIdDigest": device_id_digest,
        "leaseId": lease_id,
        "runnerLabel": runner_label,
        "acquiredAt": acquired_at,
    }
    owner_path = lock_dir / "owner.json"
    try:
        if evidence_output.is_symlink():
            raise ValueError("device lease evidence output must not be a symlink")
        owner_path.write_text(
            json.dumps(owner, ensure_ascii=False, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        evidence_output.parent.mkdir(parents=True, exist_ok=True)
        evidence_output.write_text(
            json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        values = {
            "host_digest": actual_host_digest,
            "device_id": device_id,
            "device_id_digest": device_id_digest,
            "lease_id": lease_id,
            "lease_evidence": str(evidence_output.resolve()),
            "lease_token": token,
        }
        _write_github_output(github_output, values)
        return values
    except Exception:
        if owner_path.is_file() and not owner_path.is_symlink():
            owner_path.unlink()
        lock_dir.rmdir()
        raise


def release(*, lease_evidence: Path, lease_token: str, lease_root: Path) -> None:
    evidence = json.loads(lease_evidence.read_text(encoding="utf-8"))
    if not isinstance(evidence, dict) or evidence.get("status") != "held":
        raise ValueError("device lease evidence is not held")
    platform = str(evidence.get("platform") or "")
    host = str(evidence.get("hostDigest") or "")
    device_id_digest = str(evidence.get("deviceIdDigest") or "")
    lease_id = str(evidence.get("leaseId") or "")
    if platform not in PLATFORMS or any(
        DIGEST_PATTERN.fullmatch(value) is None
        for value in (host, device_id_digest, lease_id)
    ):
        raise ValueError("device lease evidence identity is invalid")
    lease_root = lease_root.expanduser()
    if lease_root.is_symlink():
        raise ValueError("device lease root must not be a symlink")
    lease_root = lease_root.resolve()
    lock_dir = lease_root / f"{platform}-{_lease_key(platform, host, device_id_digest)}"
    owner_path = lock_dir / "owner.json"
    if lock_dir.is_symlink() or owner_path.is_symlink() or not owner_path.is_file():
        raise ValueError("owned device lease is missing or unsafe")
    owner = json.loads(owner_path.read_text(encoding="utf-8"))
    if (
        not isinstance(owner, dict)
        or owner.get("leaseId") != lease_id
        or owner.get("tokenDigest") != _digest(lease_token)
    ):
        raise ValueError("device lease ownership token does not match")
    owner_path.unlink()
    lock_dir.rmdir()


def main() -> int:
    args = _parser().parse_args()
    try:
        if args.command == "host":
            digest = host_digest()
            _write_github_output(args.github_output, {"host_digest": digest})
            print(f"host_digest={digest}")
        elif args.command == "acquire":
            values = acquire(
                platform=args.platform,
                expected_host_digest=args.expected_host_digest,
                runner_label=args.runner_label,
                run_id=args.run_id,
                run_attempt=args.run_attempt,
                preferred_device_id=args.preferred_device_id,
                lease_root=args.lease_root,
                evidence_output=args.evidence_output,
                github_output=args.github_output,
            )
            print(
                json.dumps(
                    {
                        "status": "held",
                        "hostDigest": values["host_digest"],
                        "deviceIdDigest": values["device_id_digest"],
                        "leaseId": values["lease_id"],
                    },
                    sort_keys=True,
                )
            )
        else:
            release(
                lease_evidence=args.lease_evidence,
                lease_token=args.lease_token,
                lease_root=args.lease_root,
            )
            print("device lease released")
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"device_runner_lease: GATE_BLOCK: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
