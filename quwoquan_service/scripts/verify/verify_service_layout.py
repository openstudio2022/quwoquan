#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path


SERVICE_ROOT = Path(__file__).resolve().parents[2]


def fail(message: str) -> None:
    raise SystemExit(f"[verify] FAIL: {message}")


def rel(path: Path) -> str:
    return path.relative_to(SERVICE_ROOT.parent).as_posix()


def main() -> None:
    forbidden_root_dirs = {
        "cmd",
        "infrastructure",
        "platform",
        "specs",
        ".control-plane-state",
        ".pytest_cache",
    }
    forbidden_root_files = {
        "architecture_review.md",
        "design.md",
        "proposal.md",
        "tasks.md",
        "工程目录设计.md",
        "技术选型.md",
        "端云协同落地方案.md",
        "codegen_app_metadata",
        "codegen_chat_service",
        "codegen_content_service",
        "codegen_rec_model_python",
        "codegen_storage",
        "import",
        "seed",
        "verify_metadata",
        "Dockerfile",
    }
    forbidden_script_dirs = {
        "deploy",
        "gamma",
        "ml",
        "seed",
    }
    forbidden_generated_dirs = {
        ".control-plane-state",
        ".pytest_cache",
        ".venv",
        "__pycache__",
        ".qwq_output",
        "state",
    }

    for name in sorted(forbidden_root_dirs):
        path = SERVICE_ROOT / name
        if path.exists():
            fail(f"forbidden service root directory exists: {rel(path)}")

    for name in sorted(forbidden_root_files):
        path = SERVICE_ROOT / name
        if path.exists():
            fail(f"forbidden service root file exists: {rel(path)}")

    for path in sorted(SERVICE_ROOT.glob("docker-compose*.y*ml")):
        fail(f"cross-service compose belongs in quwoquan_ops/environments/compose: {rel(path)}")

    scripts_root = SERVICE_ROOT / "scripts"
    for name in sorted(forbidden_script_dirs):
        path = scripts_root / name
        if path.exists():
            fail(f"script directory must move to domain owner or ops: {rel(path)}")

    for path in SERVICE_ROOT.rglob("*"):
        if not path.is_dir():
            continue
        if path.name in forbidden_generated_dirs:
            fail(f"local state/cache/output directory must not live in service tree: {rel(path)}")

    services_root = SERVICE_ROOT / "services"
    for service_dir in sorted(p for p in services_root.iterdir() if p.is_dir()):
        root_dockerfile = service_dir / "Dockerfile"
        if root_dockerfile.exists():
            fail(f"service Dockerfile must live under deploy/: {rel(root_dockerfile)}")
        for compose_file in sorted(service_dir.glob("docker-compose*.y*ml")):
            fail(f"service compose must live under deploy/ if service-owned: {rel(compose_file)}")

    print("[verify] OK: quwoquan_service layout is normalized")


if __name__ == "__main__":
    main()
