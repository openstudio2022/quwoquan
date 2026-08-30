"""Build matrix compiles each immutable product once, then binds environments."""

# spec_ref: specs/feature-tree/runtime/design.md#dec-002

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


APP_ROOT = Path(__file__).resolve().parents[3]
SCRIPT = APP_ROOT / "scripts/device/build_startup_environment_matrix.py"


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "startup_environment_build_reuse_under_test",
        SCRIPT,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _handoff(environment: str) -> dict[str, object]:
    profile = "prod" if environment == "prod" else "nonprod"
    return {
        "environment": environment,
        "target": f"{environment}-local" if profile == "nonprod" else "prod-hosted",
        "buildProfile": profile,
        "entrypoint": "lib/main_prod.dart",
        "launchProvenance": "canonical_launcher",
        "runtimeConfigSupplyMode": "external_runtime_package",
        "runtimeConfigPackageDigest": "sha256:" + environment[0] * 64,
        "effectiveLaunchManifestDigest": "sha256:" + environment[-1] * 64,
    }


class StartupEnvironmentBuildReuseContractTest(unittest.TestCase):
    def test_matrix_compiles_five_products_and_reuses_nonprod_bytes(self) -> None:
        module = _load_module()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            app_root = root / "quwoquan_app"
            app_root.mkdir()
            output_root = root / "reports"
            calls: list[tuple[list[str], dict[str, str]]] = []

            def build(command, *, cwd, env, check):
                self.assertEqual(cwd, app_root)
                self.assertFalse(check)
                for forbidden in module.FORBIDDEN_COMPILE_ENVIRONMENT_KEYS:
                    if forbidden.endswith("*"):
                        self.assertFalse(
                            any(
                                key.startswith(forbidden[:-1]) for key in env
                            ),
                            f"runtime prefix {forbidden} entered the compiler",
                        )
                    else:
                        self.assertNotIn(forbidden, env)
                calls.append((list(command), dict(env)))
                platform = command[2]
                profile = (
                    command[command.index("--flavor") + 1]
                    if "--flavor" in command
                    else "shared"
                )
                artifact_platform = "android" if platform == "apk" else platform
                if artifact_platform == "android":
                    self.assertEqual(
                        env["QWQ_ANDROID_RUNTIME_CONFIG_ASSET_ROOT"],
                        "/tmp/android-trust",
                    )
                if artifact_platform == "ios":
                    self.assertEqual(
                        env["QWQ_IOS_RUNTIME_CONFIG_TRUST_PATH"],
                        "/tmp/ios-trust.json",
                    )
                if artifact_platform == "web":
                    self.assertNotIn("QWQ_APP_BUILD_PROFILE", env)
                    self.assertNotIn(
                        "QWQ_ANDROID_RUNTIME_CONFIG_ASSET_ROOT",
                        env,
                    )
                    self.assertNotIn("QWQ_IOS_RUNTIME_CONFIG_TRUST_PATH", env)
                artifact = module._artifact_path(artifact_platform, profile)
                if artifact_platform in {"ios", "web"}:
                    artifact.mkdir(parents=True, exist_ok=True)
                    (artifact / "payload").write_bytes(
                        f"{profile}:{artifact_platform}".encode()
                    )
                else:
                    artifact.parent.mkdir(parents=True, exist_ok=True)
                    artifact.write_bytes(f"{profile}:{artifact_platform}".encode())
                return mock.Mock(returncode=0)

            argv = [
                str(SCRIPT),
                "--output-root",
                str(output_root),
            ]
            poisoned_runtime = {
                (
                    key[:-1] + "POISON"
                    if key.endswith("*")
                    else key
                ): f"forbidden-{key}"
                for key in module.FORBIDDEN_COMPILE_ENVIRONMENT_KEYS
            }
            poisoned_runtime.update(
                {
                    "QWQ_APP_BUILD_PROFILE": "prod",
                    "QWQ_ANDROID_RUNTIME_CONFIG_ASSET_ROOT": "/tmp/android-trust",
                    "QWQ_IOS_RUNTIME_CONFIG_TRUST_PATH": "/tmp/ios-trust.json",
                }
            )
            with mock.patch.object(module, "APP_DIR", app_root), mock.patch.object(
                module,
                "ROOT",
                root,
            ), mock.patch.object(
                module,
                "_handoff",
                side_effect=_handoff,
            ), mock.patch.object(
                module.subprocess,
                "run",
                side_effect=build,
            ), mock.patch.object(
                module.time,
                "strftime",
                return_value="fixed",
            ), mock.patch.object(sys, "argv", argv), mock.patch.dict(
                module.os.environ,
                poisoned_runtime,
                clear=False,
            ):
                self.assertEqual(module.main(), 0)

            self.assertEqual(len(calls), 5)
            report = json.loads(
                (output_root / "fixed/report.json").read_text(encoding="utf-8")
            )
            self.assertEqual(report["compileExecutions"], 5)
            self.assertEqual(len(report["builds"]), 12)
            for platform in ("android", "ios", "web"):
                nonprod = [
                    item
                    for item in report["builds"]
                    if item["platform"] == platform
                    and item["runtimeEnv"] in {"alpha", "beta", "gamma"}
                ]
                self.assertEqual(
                    len({item["artifact"] for item in nonprod}),
                    1,
                )
                self.assertEqual(
                    len({item["artifactSha256"] for item in nonprod}),
                    1,
                )
            web = [item for item in report["builds"] if item["platform"] == "web"]
            self.assertEqual(len({item["artifact"] for item in web}), 1)


if __name__ == "__main__":
    unittest.main()
