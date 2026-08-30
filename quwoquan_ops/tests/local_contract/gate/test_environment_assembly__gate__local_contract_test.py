"""local_contract: 第一方镜像身份与受治理构建镜像装配门禁的正负例。"""

from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
MODULE_PATH = ROOT / "quwoquan_ops/gate/verify_environment_assembly.py"

CLEAN_COMPOSE = """\
services:
  demo-service:
    image: "${QWQ_COMPOSE_DEMO_SERVICE_IMAGE:?fixed demo-service source image is required}"
    build:
      context: ../../../quwoquan_service
      dockerfile: services/demo-service/build/Dockerfile
      args:
        GO_BASE_IMAGE: "${QWQ_COMPOSE_GO_BASE_IMAGE:?QWQ_COMPOSE_GO_BASE_IMAGE is required}"
        ALPINE_BASE_IMAGE: "${QWQ_COMPOSE_ALPINE_BASE_IMAGE:?QWQ_COMPOSE_ALPINE_BASE_IMAGE is required}"
    environment:
      SERVICE_NAME: demo-service
      IMAGE_VERSION: "${QWQ_COMPOSE_IMAGE_VERSION:?immutable image version is required}"
"""

CLEAN_DOCKERFILE = """\
ARG GO_BASE_IMAGE
FROM --platform=${BUILDPLATFORM} ${GO_BASE_IMAGE} AS builder
ARG TARGETOS
ARG TARGETARCH
WORKDIR /src
RUN CGO_ENABLED=0 GOOS=${TARGETOS} GOARCH=${TARGETARCH} go build -o /out/demo ./cmd/demo

ARG ALPINE_BASE_IMAGE
FROM ${ALPINE_BASE_IMAGE}
COPY --from=builder /out/demo /usr/local/bin/demo
"""

CLEAN_PIPELINE = """\
jobs:
  release:
    steps:
      - id: base_images
        run: |
          python3 - <<'PY'
          import yaml
          runtime = yaml.safe_load(open("quwoquan_ops/environments/prod/runtime.yaml"))
          images = runtime["targets"]["prod-hosted"]["buildImages"]
          PY
      - name: build release image
        env:
          GO_BASE_IMAGE: ${{ steps.base_images.outputs.go_base_image }}
          ALPINE_BASE_IMAGE: ${{ steps.base_images.outputs.alpine_base_image }}
          PYTHON_BASE_IMAGE: ${{ steps.base_images.outputs.python_base_image }}
        run: |
          docker build \\
            --build-arg "GO_BASE_IMAGE=$GO_BASE_IMAGE" \\
            --build-arg "ALPINE_BASE_IMAGE=$ALPINE_BASE_IMAGE" \\
            --build-arg "PYTHON_BASE_IMAGE=$PYTHON_BASE_IMAGE" .
"""

#: control-plane 的 compose 会被构建镜像判据无条件读取，但它不声明 GO_BASE_IMAGE，
#: 也不进 gamma-local 拓扑，因此既不是第一方镜像 owner 也不参与 Go 构建判据。
PLATFORM_OPS_COMPOSE = """\
services:
  platform-ops-service:
    image: "${QWQ_COMPOSE_PLATFORM_OPS_SERVICE_IMAGE:?required}"
"""

TOPOLOGY = """\
services:
  demo-service: {}
"""


def _load_module():
    spec = importlib.util.spec_from_file_location("verify_environment_assembly", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _materialize(
    root: Path,
    *,
    compose: str = CLEAN_COMPOSE,
    dockerfile: str | None = CLEAN_DOCKERFILE,
    pipeline: str = CLEAN_PIPELINE,
) -> None:
    """铺出满足两条判据所需的最小自治服务树。

    `first_party_service_names` 要求 owner 同时持有 `config/schema.yaml`、
    `deploy/compose.yaml` 并出现在 canonical gamma-local 拓扑里，三者缺一就退化成
    空 owner 集合——那时判据循环体一次都不执行，负例会假绿。
    """
    service = root / "quwoquan_service/services/demo-service"
    (service / "config").mkdir(parents=True)
    (service / "config/schema.yaml").write_text("service: demo-service\n", encoding="utf-8")
    (service / "deploy").mkdir(parents=True)
    (service / "deploy/compose.yaml").write_text(compose, encoding="utf-8")
    if dockerfile is not None:
        (service / "build").mkdir(parents=True)
        (service / "build/Dockerfile").write_text(dockerfile, encoding="utf-8")

    platform_ops = root / "quwoquan_service/control-plane/platform-ops/deploy"
    platform_ops.mkdir(parents=True)
    (platform_ops / "compose.yaml").write_text(PLATFORM_OPS_COMPOSE, encoding="utf-8")

    topology = root / "quwoquan_ops/environments/compose"
    topology.mkdir(parents=True)
    (topology / "docker-compose.gamma-local.yaml").write_text(TOPOLOGY, encoding="utf-8")

    workflows = root / ".github/workflows"
    workflows.mkdir(parents=True)
    (workflows / "service_pipeline.yml").write_text(pipeline, encoding="utf-8")


class FirstPartyImageCompositionTest(unittest.TestCase):
    def _issues(self, **kwargs) -> list[str]:
        module = _load_module()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _materialize(root, **kwargs)
            module.ROOT = root
            return module.validate_first_party_image_composition_contract()

    def test_clean_compose_is_accepted(self) -> None:
        self.assertEqual(self._issues(), [])

    def test_synthetic_tree_actually_discovers_the_owner(self) -> None:
        """夹具自证：owner 集合必须非空，否则后面每条负例都只是在测空循环。"""
        module = _load_module()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _materialize(root)
            module.ROOT = root
            self.assertEqual(
                sorted(module._first_party_compose_files()),
                ["demo-service"],
            )

    def test_mutable_latest_tag_is_rejected(self) -> None:
        compose = CLEAN_COMPOSE.replace(
            '"${QWQ_COMPOSE_DEMO_SERVICE_IMAGE:?fixed demo-service source image is required}"',
            "quwoquan/demo-service:latest",
        )
        issues = self._issues(compose=compose)
        self.assertTrue(
            any("contains mutable :latest" in issue for issue in issues),
            msg=issues,
        )

    def test_image_version_fallback_is_rejected(self) -> None:
        """`:-` 默认值会让缺失的不可变版本静默变成某个可用值，镜像身份随之失真。"""
        compose = CLEAN_COMPOSE.replace(
            "QWQ_COMPOSE_IMAGE_VERSION:?immutable image version is required",
            "QWQ_COMPOSE_IMAGE_VERSION:-dev",
        )
        issues = self._issues(compose=compose)
        self.assertTrue(
            any("contains a fallback IMAGE_VERSION" in issue for issue in issues),
            msg=issues,
        )

    def test_image_key_belonging_to_another_owner_is_rejected(self) -> None:
        compose = CLEAN_COMPOSE.replace(
            "QWQ_COMPOSE_DEMO_SERVICE_IMAGE",
            "QWQ_COMPOSE_CONTENT_SERVICE_IMAGE",
        )
        issues = self._issues(compose=compose)
        self.assertTrue(
            any(
                "must require QWQ_COMPOSE_DEMO_SERVICE_IMAGE" in issue
                for issue in issues
            ),
            msg=issues,
        )

    def test_missing_image_version_requirement_is_rejected(self) -> None:
        compose = CLEAN_COMPOSE.replace(
            '      IMAGE_VERSION: "${QWQ_COMPOSE_IMAGE_VERSION:?immutable image version is required}"\n',
            "",
        )
        issues = self._issues(compose=compose)
        self.assertTrue(
            any("must require QWQ_COMPOSE_IMAGE_VERSION" in issue for issue in issues),
            msg=issues,
        )

    def test_compose_without_build_workload_is_rejected(self) -> None:
        compose = """\
services:
  demo-service:
    image: "${QWQ_COMPOSE_DEMO_SERVICE_IMAGE:?required}"
"""
        issues = self._issues(compose=compose, dockerfile=None)
        self.assertTrue(
            any("has no first-party build workload" in issue for issue in issues),
            msg=issues,
        )

    def test_compose_without_services_is_rejected(self) -> None:
        issues = self._issues(compose="services: {}\n", dockerfile=None)
        self.assertTrue(
            any("has no services" in issue for issue in issues),
            msg=issues,
        )

    def test_invalid_compose_yaml_is_reported_instead_of_raised(self) -> None:
        """解析失败必须落成一条可读判据；抛异常会让整条门禁在第一份坏 compose 上停摆。"""
        issues = self._issues(compose="services: [unclosed\n", dockerfile=None)
        self.assertTrue(
            any("is invalid YAML" in issue for issue in issues),
            msg=issues,
        )

    def test_real_repository_first_party_composition_holds(self) -> None:
        module = _load_module()
        self.assertEqual(module.validate_first_party_image_composition_contract(), [])


class ServiceBuildImageContractTest(unittest.TestCase):
    def _issues(self, **kwargs) -> list[str]:
        module = _load_module()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _materialize(root, **kwargs)
            module.ROOT = root
            return module.validate_service_build_image_contract()

    def test_clean_build_inputs_are_accepted(self) -> None:
        self.assertEqual(self._issues(), [])

    def test_unrequired_go_base_image_is_rejected(self) -> None:
        compose = CLEAN_COMPOSE.replace(
            '"${QWQ_COMPOSE_GO_BASE_IMAGE:?QWQ_COMPOSE_GO_BASE_IMAGE is required}"',
            "golang:1.24-alpine",
        )
        issues = self._issues(compose=compose)
        self.assertTrue(
            any("must require QWQ_COMPOSE_GO_BASE_IMAGE" in issue for issue in issues),
            msg=issues,
        )

    def test_retired_go_alpine_input_is_rejected(self) -> None:
        compose = CLEAN_COMPOSE.replace(
            "        ALPINE_BASE_IMAGE:",
            "        GO_ALPINE_BASE_IMAGE: \"${QWQ_COMPOSE_ALPINE_BASE_IMAGE:?required}\"\n        ALPINE_BASE_IMAGE:",
        )
        issues = self._issues(compose=compose)
        self.assertTrue(
            any("contains retired Go image input" in issue for issue in issues),
            msg=issues,
        )

    def test_defaulted_base_image_arg_is_rejected(self) -> None:
        """`ARG GO_BASE_IMAGE=<tag>` 会让构建在缺注入时悄悄用上未受治理的镜像。"""
        dockerfile = CLEAN_DOCKERFILE.replace(
            "ARG GO_BASE_IMAGE\n",
            "ARG GO_BASE_IMAGE=golang:1.24\n",
            1,
        )
        issues = self._issues(dockerfile=dockerfile)
        self.assertTrue(
            any("must not default GO_BASE_IMAGE" in issue for issue in issues),
            msg=issues,
        )

    def test_native_platform_build_is_rejected(self) -> None:
        """构建平台必须是 BUILDPLATFORM 且交叉编译到目标架构，否则 arm64 机器会产出错架构镜像。"""
        dockerfile = CLEAN_DOCKERFILE.replace(
            "FROM --platform=${BUILDPLATFORM} ${GO_BASE_IMAGE} AS builder",
            "FROM ${GO_BASE_IMAGE} AS builder",
        ).replace(
            "RUN CGO_ENABLED=0 GOOS=${TARGETOS} GOARCH=${TARGETARCH} go build -o /out/demo ./cmd/demo",
            "RUN CGO_ENABLED=0 go build -o /out/demo ./cmd/demo",
        )
        issues = self._issues(dockerfile=dockerfile)
        joined = "\n".join(issues)
        self.assertIn("must build Go on BUILDPLATFORM", joined)
        self.assertIn("must cross-compile Go for the image target", joined)

    def test_unsigned_package_installation_is_rejected(self) -> None:
        dockerfile = CLEAN_DOCKERFILE + "RUN apk add --allow-untrusted ca-certificates\n"
        issues = self._issues(dockerfile=dockerfile)
        self.assertTrue(
            any(
                "must not bypass package signature checks" in issue for issue in issues
            ),
            msg=issues,
        )

    def test_missing_dockerfile_is_rejected(self) -> None:
        issues = self._issues(dockerfile=None)
        self.assertTrue(
            any("references a missing Dockerfile" in issue for issue in issues),
            msg=issues,
        )

    def test_pipeline_must_read_governed_prod_hosted_build_images(self) -> None:
        pipeline = CLEAN_PIPELINE.replace(
            'runtime["targets"]["prod-hosted"]["buildImages"]',
            'runtime["buildImages"]',
        )
        issues = self._issues(pipeline=pipeline)
        self.assertIn(
            "service pipeline must read prod-hosted governed build images",
            issues,
        )

    def test_governed_image_lookup_tolerates_line_wrapping(self) -> None:
        """收敛的是取值来源，不是取值表达式换行在哪里；折叠空白后下标链仍须成立。"""
        pipeline = CLEAN_PIPELINE.replace(
            'runtime["targets"]["prod-hosted"]["buildImages"]',
            'runtime["targets"][\n              "prod-hosted"\n          ]["buildImages"]',
        )
        self.assertEqual(self._issues(pipeline=pipeline), [])

    def test_pipeline_must_pass_each_base_image_to_the_build(self) -> None:
        """只读到受治理镜像还不够：不传进 build-arg 等于读了个寂寞。"""
        pipeline = CLEAN_PIPELINE.replace(
            '            --build-arg "ALPINE_BASE_IMAGE=$ALPINE_BASE_IMAGE" \\\n',
            "",
        )
        issues = self._issues(pipeline=pipeline)
        self.assertIn(
            "service pipeline must pass ALPINE_BASE_IMAGE to release image builds",
            issues,
        )

    def test_real_repository_build_image_contract_holds(self) -> None:
        module = _load_module()
        self.assertEqual(module.validate_service_build_image_contract(), [])


if __name__ == "__main__":
    unittest.main()
