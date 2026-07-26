from pathlib import Path
import unittest


class CircleServiceContainerBuildContractTest(unittest.TestCase):
    def test_circle_service_builds_a_static_binary_for_its_alpine_runtime(self) -> None:
        root = Path(__file__).resolve().parents[3]
        dockerfile = (
            root
            / "quwoquan_service/services/circle-service/build/Dockerfile"
        ).read_text(encoding="utf-8")

        self.assertIn("ARG GO_BUILD_FLAGS=-p=1", dockerfile)
        self.assertIn("ARG GO_BUILD_FLAGS", dockerfile)
        self.assertIn(
            "RUN CGO_ENABLED=0 go build ${GO_BUILD_FLAGS} -o /circle-service ",
            dockerfile,
        )
        self.assertIn("FROM ${ALPINE_BASE_IMAGE}", dockerfile)
        self.assertIn(
            "COPY --from=builder /circle-service /usr/local/bin/circle-service",
            dockerfile,
        )


if __name__ == "__main__":
    unittest.main()
