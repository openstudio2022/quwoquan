#!/usr/bin/env python3
"""Run app alpha/beta seed smoke from shared manifests."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
APP = ROOT / "quwoquan_app"
USER_POOL = ROOT / "quwoquan_service" / "contracts" / "metadata" / "_shared" / "test_fixtures" / "user_pool.json"
ALPHA_MANIFEST = ROOT / "quwoquan_service" / "contracts" / "metadata" / "_shared" / "test_fixtures" / "app_alpha_seed_manifest.json"


def run(cmd: list[str], cwd: Path = ROOT) -> str:
    result = subprocess.run(
        cmd,
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"command failed: {' '.join(cmd)}\n{result.stdout}")
    return result.stdout


def wait_url(url: str, timeout: int = 30) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as resp:
                if 200 <= resp.status < 300:
                    return
        except Exception:
            time.sleep(0.5)
    raise RuntimeError(f"timeout waiting for {url}")


def beta_gateway_smoke(port: int) -> dict[str, object]:
    proc = subprocess.Popen(
        [
            sys.executable,
            "agent_ops/assistant/dev_assistant_beta_gateway.py",
            "--listen-host",
            "127.0.0.1",
            "--listen-port",
            str(port),
        ],
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    try:
        base = f"http://127.0.0.1:{port}"
        checks = [
            "/healthz",
            "/v1/content/feed",
            "/v1/content/profile-subjects/fixture_user_current/posts",
            "/v1/chat/inbox",
            "/v1/chat/contacts",
            "/v1/chat/conversations",
            "/v1/circles",
            "/v1/circles/fixture_circle_photo/feed",
            "/v1/user/profile",
            "/v1/me",
            "/v1/users/fixture_user_current/works",
            "/v1/users/fixture_user_current/circles",
            "/v1/entity/homepages",
            "/v1/integration/locations/pois",
            "/v1/app-messages",
            "/v1/rtc/calls",
        ]
        for path in checks:
            wait_url(base + path)
        return {"gatewayBaseUrl": base, "checkedRoutes": checks}
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


def load_shared_pool_summary() -> dict[str, object]:
    pool = json.loads(USER_POOL.read_text(encoding="utf-8"))
    return {
        "schemaVersion": pool.get("schemaVersion"),
        "statistics": pool.get("statistics"),
        "sourceCatalogDigest": pool.get("sourceCatalogDigest"),
    }


def load_alpha_delivery_channels() -> dict[str, list[str]]:
    manifest = json.loads(ALPHA_MANIFEST.read_text(encoding="utf-8"))
    return {
        str(item.get("domain")): [str(value) for value in item.get("deliveryChannels", [])]
        for item in manifest.get("seedRefs", [])
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", default="artifacts/app_alpha_beta_seed_matrix.json")
    parser.add_argument("--gateway-port", type=int, default=18090)
    args = parser.parse_args()

    report: dict[str, object] = {
        "status": "passed",
        "sharedPool": {},
        "alpha": {},
        "beta": {},
    }
    try:
        run([sys.executable, "quwoquan_app/scripts/env/verify_app_seed_manifests.py"])
        run([sys.executable, "agent_ops/avatar/verify_avatar_user_pool_consistency.py"])
        run(["bash", "quwoquan_app/scripts/env/build_app_env_package.sh", "--env", "alpha"])
        run(["bash", "quwoquan_app/scripts/env/build_app_env_package.sh", "--env", "beta"])
        report["sharedPool"] = load_shared_pool_summary()
        alpha_output = run(
            [
                "flutter",
                "test",
                "--dart-define=CONTRACT_FIXTURE_PROFILE=full",
                "test/cloud/services/contract_seeded_mock_repository_test.dart",
            ],
            cwd=APP,
        )
        report["alpha"] = {
            "dataSource": "mock",
            "test": "test/cloud/services/contract_seeded_mock_repository_test.dart",
            "outputTail": alpha_output[-2000:],
            "deliveryChannels": load_alpha_delivery_channels(),
        }
        report["beta"] = {
            "dataSource": "remote",
            **beta_gateway_smoke(args.gateway_port),
            "gatewayProbe": run([sys.executable, "agent_ops/avatar/probe_avatar_user_pool_gateway.py"])[-1000:],
        }
    except Exception as exc:  # noqa: BLE001
        report["status"] = "failed"
        report["error"] = str(exc)
        Path(args.report).parent.mkdir(parents=True, exist_ok=True)
        Path(args.report).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(str(exc), file=sys.stderr)
        return 1

    report_path = ROOT / args.report
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"app alpha/beta seed matrix report written: {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
