from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


# spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-001
ROOT = Path(__file__).resolve().parents[3]
STACKCTL = ROOT / "quwoquan_ops" / "cli" / "stackctl.py"
PURITY_GATE = (
    ROOT / "quwoquan_app" / "scripts" / "env" / "verify_prod_package_purity.py"
)
PROD_APP_SOURCE = ROOT / "quwoquan_app" / "configs" / "prod" / "app_runtime.yaml"


def test_prod_app_packages_project_isolated_targets_without_mutating_source(
    tmp_path: Path,
) -> None:
    deploy_root = tmp_path / "deploy"
    output_root = tmp_path / "output"
    source_before = PROD_APP_SOURCE.read_bytes()
    environment = os.environ.copy()
    environment.update(
        {
            "PYTHONDONTWRITEBYTECODE": "1",
            "QWQ_DEPLOY_WORK_ROOT": str(deploy_root),
            "QWQ_OUTPUT_ROOT": str(output_root),
        }
    )

    expected = {
        "prod-sim": {
            "gateway": "https://api.sim.quwoquan.com:20000",
            "legal": "https://api.sim.quwoquan.com:20000/legal",
            "realtime": "wss://api.sim.quwoquan.com:20000",
            "avatar": "https://cdn.sim.quwoquan.com:20100",
            "rtc": "wss://rtc.sim.quwoquan.com:20000",
        },
        "prod-hosted": {
            "gateway": "https://api.quwoquan.com",
            "legal": "https://quwoquan.com/legal",
            "realtime": "wss://api.quwoquan.com",
            "avatar": "https://cdn.quwoquan.com",
            "rtc": "wss://rtc.quwoquan.com",
        },
    }

    for target, target_urls in expected.items():
        result = subprocess.run(
            [
                sys.executable,
                str(STACKCTL),
                "package",
                "--env",
                "prod",
                "--target",
                target,
                "--report-dir",
                str(tmp_path / f"report-{target}"),
            ],
            cwd=ROOT,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )

        assert result.returncode == 0, result.stdout + result.stderr
        package_root = deploy_root / target / "packages" / "app"
        package_report = json.loads(
            (package_root / "report.json").read_text(encoding="utf-8")
        )
        environment_runtime = json.loads(
            (package_root / "environment_runtime.yaml").read_text(encoding="utf-8")
        )
        app_runtime = (package_root / "app_runtime.yaml").read_text(encoding="utf-8")

        assert package_report["env"] == "prod"
        assert package_report["target"] == target
        assert environment_runtime["environment"] == "prod"
        assert environment_runtime["target"]["name"] == target
        assert package_report["gatewayBaseUrl"] == target_urls["gateway"]
        assert package_report["legalBaseUrl"] == target_urls["legal"]
        assert package_report["realtimeBaseUrl"] == target_urls["realtime"]
        assert package_report["avatarCdnBaseUrl"] == target_urls["avatar"]
        assert package_report["rtcMediaConnectionUrl"] == target_urls["rtc"]
        assert f"gatewayBaseUrl: {target_urls['gateway']}" in app_runtime
        assert f"rtcMediaConnectionUrl: {target_urls['rtc']}" in app_runtime
        assert "APP_DATA_SOURCE=mock" not in app_runtime
        assert "seedRefs" not in app_runtime

        purity = subprocess.run(
            [
                sys.executable,
                str(PURITY_GATE),
                "--scope",
                "app",
                "--target",
                target,
            ],
            cwd=ROOT,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        assert purity.returncode == 0, purity.stdout + purity.stderr

    assert (
        deploy_root / "prod-sim" / "packages" / "app"
    ) != deploy_root / "prod-hosted" / "packages" / "app"
    hosted_runtime = (
        deploy_root / "prod-hosted" / "packages" / "app" / "app_runtime.yaml"
    )
    assert ".test" not in hosted_runtime.read_text(encoding="utf-8")
    hosted_runtime.write_text(
        hosted_runtime.read_text(encoding="utf-8")
        + "# forbidden regression: https://api.sim.quwoquan.com\n",
        encoding="utf-8",
    )
    hosted_purity = subprocess.run(
        [
            sys.executable,
            str(PURITY_GATE),
            "--scope",
            "app",
            "--target",
            "prod-hosted",
        ],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert hosted_purity.returncode == 1
    assert "contains forbidden token '.test'" in hosted_purity.stdout
    assert PROD_APP_SOURCE.read_bytes() == source_before
