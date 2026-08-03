from __future__ import annotations

from pathlib import Path

from quwoquan_service.scripts.runtime.service_image_build_input import (
    SHARED_IMAGE_INPUTS,
    service_image_build_input_digest,
)


def _write(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")


def test_service_image_digest_covers_owner_and_shared_compiler_inputs(
    tmp_path: Path,
) -> None:
    """spec_ref: environment-topology-and-packaging/GWT-002."""

    owner = "quwoquan_service/services/api-edge"
    _write(tmp_path / owner / "cmd/api/main.go", "package main\n")
    for item in SHARED_IMAGE_INPUTS:
        path = tmp_path / item
        if path.suffix:
            _write(path, item + "\n")
        else:
            _write(path / "input.go", item + "\n")

    first, count, declared = service_image_build_input_digest(tmp_path, owner)
    assert count == 6
    assert declared[0] == owner
    assert "quwoquan_service/generated" in declared
    assert "quwoquan_service/runtime" in declared

    _write(
        tmp_path / "quwoquan_service/generated/operationsecurity/descriptors.g.go",
        "package operationsecurity\n",
    )
    generated_changed, _, _ = service_image_build_input_digest(tmp_path, owner)
    assert generated_changed != first

    _write(tmp_path / owner / "cmd/api/main.go", "package main\n// changed\n")
    owner_changed, _, _ = service_image_build_input_digest(tmp_path, owner)
    assert owner_changed != generated_changed


def test_service_image_digest_ignores_unrelated_app_source(tmp_path: Path) -> None:
    """An App-only change must not rebuild every Service image."""

    owner = "quwoquan_service/services/api-edge"
    _write(tmp_path / owner / "cmd/api/main.go", "package main\n")
    for item in SHARED_IMAGE_INPUTS:
        path = tmp_path / item
        if path.suffix:
            _write(path, item + "\n")
        else:
            _write(path / "input.go", item + "\n")
    first, _, _ = service_image_build_input_digest(tmp_path, owner)
    _write(tmp_path / "quwoquan_app/lib/main.dart", "void main() {}\n")
    second, _, _ = service_image_build_input_digest(tmp_path, owner)
    assert second == first
