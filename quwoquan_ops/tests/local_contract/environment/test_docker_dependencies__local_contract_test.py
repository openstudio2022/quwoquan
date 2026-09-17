"""Docker 基础镜像锁、四环境 buildImages 与 stackctl 预热入口。

spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#req-002
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from subprocess import CompletedProcess
from unittest import mock

from quwoquan_ops.cli import stackctl
from quwoquan_ops.cli.lib import docker_dependencies
from quwoquan_ops.gate.scaffold import new_service


ROOT = Path(__file__).resolve().parents[4]


class DockerDependenciesContractTest(unittest.TestCase):
    def test_registry_env_and_lock_cover_required_base_images(self) -> None:
        registry = docker_dependencies.load_registry_env()
        lock = docker_dependencies.load_lock_file()
        self.assertEqual(
            registry["QWQ_GO_BASE_IMAGE"],
            "golang:1.24-bookworm",
        )
        self.assertEqual(registry["QWQ_ALPINE_BASE_IMAGE"], "alpine:3.21")
        for name in docker_dependencies._REQUIRED_LOCAL_KEYS:
            self.assertIn(name, lock["dependencies"])
        makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
        self.assertIn(
            "python3 quwoquan_ops/cli/stackctl.py docker-dependencies --action prepare",
            makefile,
        )
        self.assertIn(
            "python3 quwoquan_ops/cli/stackctl.py docker-dependencies --action check-outdated",
            makefile,
        )

    def test_four_local_targets_declare_go_and_alpine_build_images(self) -> None:
        images = docker_dependencies.four_env_build_images()
        for target in ("alpha-local", "beta-local", "gamma-local", "prod-sim"):
            self.assertEqual(images[target]["goBaseImage"], "golang:1.24-bookworm")
            self.assertEqual(images[target]["alpineBaseImage"], "alpine:3.21")
        self.assertIn("golang:1.24-bookworm", images["prod-hosted"]["goBaseImage"])
        self.assertIn("alpine:3.22", images["prod-hosted"]["alpineBaseImage"])

    def test_service_dockerfiles_do_not_default_base_image_args(self) -> None:
        dockerfiles = sorted(
            (ROOT / "quwoquan_service/services").glob("*/build/Dockerfile")
        )
        dockerfiles.append(
            ROOT / "quwoquan_service/control-plane/platform-ops/build/Dockerfile"
        )
        dockerfiles.append(ROOT / "quwoquan_service/cmd/service-core/Dockerfile")
        for dockerfile in dockerfiles:
            text = dockerfile.read_text(encoding="utf-8")
            if "ARG GO_BASE_IMAGE" not in text:
                continue
            self.assertIn("ARG GO_BASE_IMAGE\n", text, dockerfile)
            self.assertIn("ARG ALPINE_BASE_IMAGE\n", text, dockerfile)

    def test_scaffold_dockerfile_requires_injected_base_images(self) -> None:
        text = Path(new_service.__file__).read_text(encoding="utf-8")
        self.assertIn("ARG GO_BASE_IMAGE\n", text)
        self.assertNotIn("ARG GO_BASE_IMAGE=golang:", text)
        self.assertIn("FROM --platform=${{BUILDPLATFORM}} ${{GO_BASE_IMAGE}}", text)
        self.assertIn(
            'GO_BASE_IMAGE: "${{QWQ_COMPOSE_GO_BASE_IMAGE:?QWQ_COMPOSE_GO_BASE_IMAGE is required}}"',
            text,
        )

    def test_prepare_pulls_missing_images_through_configured_mirrors(self) -> None:
        calls: list[list[str]] = []
        cached: set[str] = set()

        def fake_run(
            argv: list[str],
            *,
            cwd: Path | None = None,
            env: dict[str, str] | None = None,
            check: bool = False,
            timeout_seconds: float | None = None,
        ) -> CompletedProcess[str]:
            calls.append(list(argv))
            if argv[:3] == ["docker", "image", "inspect"]:
                name = argv[-1]
                if name in cached:
                    return CompletedProcess(
                        argv,
                        0,
                        "sha256:" + "a" * 64 + " []\n",
                        "",
                    )
                return CompletedProcess(argv, 1, "", "missing")
            if argv[:2] == ["docker", "pull"]:
                return CompletedProcess(argv, 0, "pulled\n", "")
            if argv[:2] == ["docker", "tag"]:
                cached.add(argv[-1])
                return CompletedProcess(argv, 0, "", "")
            raise AssertionError(argv)

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            env_dir = root / "quwoquan_ops/policies"
            env_dir.mkdir(parents=True)
            env_dir.joinpath("registry.env").write_text(
                (ROOT / "quwoquan_ops/policies/registry.env").read_text(
                    encoding="utf-8"
                ),
                encoding="utf-8",
            )
            lock_payload = {
                "schema": docker_dependencies.LOCK_SCHEMA,
                "generatedAt": "2026-09-17T00:00:00Z",
                "dependencies": {
                    name: {
                        "repository": f"docker.io/library/{name.split(':', 1)[0]}",
                        "tag": name.split(":", 1)[1],
                        "digest": "",
                        "pulledAt": "",
                        "source": "",
                    }
                    for name in docker_dependencies._REQUIRED_LOCAL_KEYS
                },
            }
            lock_path = env_dir / "docker-dependencies.lock.json"
            lock_path.write_text(
                json.dumps(lock_payload, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            with mock.patch.object(docker_dependencies, "ROOT", root):
                result = docker_dependencies.prepare_dependencies(
                    lock_path=lock_path,
                    registry_path=env_dir / "registry.env",
                    run_command=fake_run,
                    persist_lock=True,
                )
            self.assertEqual(
                result["dependencies"]["golang:1.24-bookworm"]["status"],
                "pulled",
            )
            self.assertTrue(
                any(
                    argv[:2] == ["docker", "pull"]
                    and argv[2].startswith("docker.m.daocloud.io/")
                    for argv in calls
                )
            )
            saved = json.loads(lock_path.read_text(encoding="utf-8"))
            self.assertTrue(
                saved["dependencies"]["golang:1.24-bookworm"]["digest"].startswith(
                    "sha256:"
                )
            )

    def test_ensure_prepared_skips_pull_when_cache_is_warm(self) -> None:
        def fake_run(argv: list[str], **_kwargs: object) -> CompletedProcess[str]:
            if argv[:3] == ["docker", "image", "inspect"]:
                return CompletedProcess(
                    argv,
                    0,
                    "sha256:" + "b" * 64 + " []\n",
                    "",
                )
            raise AssertionError(argv)

        status = docker_dependencies.ensure_prepared(run_command=fake_run)
        self.assertEqual(status["status"], "cached")

    def test_stackctl_parser_exposes_docker_dependencies_actions(self) -> None:
        parser = stackctl.build_parser()
        parsed = parser.parse_args(
            ["docker-dependencies", "--action", "verify"]
        )
        self.assertEqual(parsed.command, "docker-dependencies")
        self.assertEqual(parsed.action, "verify")
        self.assertIn(
            "docker-dependencies",
            stackctl.stackctl_dispatch._STACKCTL_HANDLER_NAMES,
        )


if __name__ == "__main__":
    unittest.main()
