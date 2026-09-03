from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import yaml

from quwoquan_ops.cli.lib.runtime_topology_package import (
    load_runtime_topology_package,
    materialize_runtime_topology_package,
)


ROOT = Path(__file__).resolve().parents[4]
CONTENT_ENVIRONMENT_ARTIFACT = (
    "runtime-topology/services/content-service/environment.compose.yaml"
)


class ContentServiceSearchRuntimeTopologyTest(unittest.TestCase):
    def test_content_release_selects_search_dependency_without_product_ops_overlay(self) -> None:
        for environment in ("alpha", "beta", "gamma"):
            with self.subTest(environment=environment), tempfile.TemporaryDirectory() as temporary:
                candidate = Path(temporary) / "candidate"
                shared = candidate / "packages" / "runtime-shared"
                shared.mkdir(parents=True)
                materialize_runtime_topology_package(
                    environment,
                    f"{environment}-local",
                    shared,
                    repo_root=ROOT,
                )

                selected = {}
                for workload in ("full", "content-commercial", "content-release"):
                    topology = load_runtime_topology_package(
                        candidate,
                        environment=environment,
                        target=f"{environment}-local",
                        workload=workload,
                    )
                    selected[workload] = {
                        path.relative_to(shared).as_posix()
                        for path in topology["composeFiles"]
                    }

                self.assertIn(CONTENT_ENVIRONMENT_ARTIFACT, selected["full"])
                self.assertIn(
                    CONTENT_ENVIRONMENT_ARTIFACT,
                    selected["content-commercial"],
                )
                self.assertNotIn(
                    CONTENT_ENVIRONMENT_ARTIFACT,
                    selected["content-release"],
                )
                self.assertIn(
                    "runtime-topology/dependencies/search/elasticsearch.compose.yaml",
                    selected["content-release"],
                )

                environment_compose = next(
                    path
                    for path in load_runtime_topology_package(
                        candidate,
                        environment=environment,
                        target=f"{environment}-local",
                        workload="full",
                    )["composeFiles"]
                    if path.relative_to(shared).as_posix()
                    == CONTENT_ENVIRONMENT_ARTIFACT
                )
                content = yaml.safe_load(environment_compose.read_text(encoding="utf-8"))
                self.assertEqual(
                    content["services"]["service-core"]["depends_on"][
                        "elasticsearch"
                    ],
                    {"condition": "service_healthy"},
                )


if __name__ == "__main__":
    unittest.main()
