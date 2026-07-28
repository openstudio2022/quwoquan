"""本地 alpha/beta Postgres 迁移 checksum 漂移探针（秒级，避免 readiness 空等）。"""
from __future__ import annotations

import hashlib
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence


ROOT = Path(__file__).resolve().parents[3]
MIGRATIONS_ROOT = (
    ROOT
    / "quwoquan_service"
    / "services"
    / "user-service"
    / "resources"
    / "migrations"
)

ALPHA_COMPOSE_PROJECT = "quwoquan-alpha-content-release"
BETA_COMPOSE_PROJECT = "quwoquan-beta-backing"


@dataclass(frozen=True)
class MigrationDriftFinding:
    filename: str
    applied_checksum: str
    current_checksum: str


@dataclass(frozen=True)
class MigrationDriftProbeResult:
    status: str  # ok | drift | unavailable | skipped
    target: str
    container: str
    findings: tuple[MigrationDriftFinding, ...]
    detail: str

    @property
    def has_drift(self) -> bool:
        return self.status == "drift" and bool(self.findings)


def _sha256_hex(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def current_migration_checksums() -> dict[str, str]:
    checksums: dict[str, str] = {}
    if not MIGRATIONS_ROOT.is_dir():
        return checksums
    for path in sorted(MIGRATIONS_ROOT.rglob("*.up.sql")):
        relative = path.relative_to(MIGRATIONS_ROOT).as_posix()
        checksums[relative] = _sha256_hex(path)
    return checksums


def _compose_postgres_container(project: str) -> str:
    result = subprocess.run(
        [
            "docker",
            "ps",
            "-a",
            "--filter",
            f"label=com.docker.compose.project={project}",
            "--filter",
            "label=com.docker.compose.service=postgres",
            "--format",
            "{{.Names}}",
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    names = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    return names[0] if names else ""


def _volume_names(project: str, *, substring: str = "postgres") -> list[str]:
    result = subprocess.run(
        ["docker", "volume", "ls", "--format", "{{.Name}}"],
        text=True,
        capture_output=True,
        check=False,
    )
    names: list[str] = []
    for line in result.stdout.splitlines():
        name = line.strip()
        if project in name and substring in name:
            names.append(name)
    return names


def probe_migration_drift(target_name: str) -> MigrationDriftProbeResult:
    if target_name == "alpha-local":
        project = ALPHA_COMPOSE_PROJECT
    elif target_name == "beta-local":
        project = BETA_COMPOSE_PROJECT
    else:
        return MigrationDriftProbeResult(
            status="skipped",
            target=target_name,
            container="",
            findings=(),
            detail="migration drift probe only applies to alpha-local/beta-local",
        )

    container = _compose_postgres_container(project)
    if not container:
        return MigrationDriftProbeResult(
            status="unavailable",
            target=target_name,
            container="",
            findings=(),
            detail=f"postgres container for {project} is not present",
        )

    # Healthy or recently started postgres can accept queries; fail soft if not ready.
    query = (
        "SELECT filename, checksum FROM service_schema_migrations "
        "WHERE service_name = 'user-service' ORDER BY filename;"
    )
    result = subprocess.run(
        [
            "docker",
            "exec",
            container,
            "psql",
            "-U",
            "quwoquan",
            "-d",
            "quwoquan",
            "-At",
            "-F",
            "|",
            "-c",
            query,
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        stderr = (result.stderr or result.stdout or "").strip()
        if "does not exist" in stderr or "relation" in stderr.lower():
            return MigrationDriftProbeResult(
                status="ok",
                target=target_name,
                container=container,
                findings=(),
                detail="migration ledger missing; fresh volume will apply current files",
            )
        return MigrationDriftProbeResult(
            status="unavailable",
            target=target_name,
            container=container,
            findings=(),
            detail=stderr[:300] or "psql probe failed",
        )

    applied: dict[str, str] = {}
    for line in result.stdout.splitlines():
        if "|" not in line:
            continue
        filename, checksum = line.split("|", 1)
        applied[filename.strip()] = checksum.strip()

    current = current_migration_checksums()
    findings: list[MigrationDriftFinding] = []
    for filename, applied_checksum in applied.items():
        current_checksum = current.get(filename)
        if current_checksum and current_checksum != applied_checksum:
            findings.append(
                MigrationDriftFinding(
                    filename=filename,
                    applied_checksum=applied_checksum,
                    current_checksum=current_checksum,
                )
            )
    if findings:
        return MigrationDriftProbeResult(
            status="drift",
            target=target_name,
            container=container,
            findings=tuple(findings),
            detail=f"{len(findings)} migration checksum drift(s)",
        )
    return MigrationDriftProbeResult(
        status="ok",
        target=target_name,
        container=container,
        findings=(),
        detail="migration checksums match current files",
    )


def wipe_local_postgres_volumes(target_name: str) -> tuple[bool, str]:
    """Tear down compose project volumes for local postgres (destructive, local only)."""
    if target_name == "alpha-local":
        project = ALPHA_COMPOSE_PROJECT
        compose_files = [
            ROOT / "quwoquan_ops" / "environments" / "compose" / "docker-compose.local-content-backing.yaml",
        ]
        # Alpha content-release uses its own project; prefer docker compose -p down -v.
        cmd = ["docker", "compose", "-p", project, "down", "-v"]
    elif target_name == "beta-local":
        project = BETA_COMPOSE_PROJECT
        cmd = [
            "docker",
            "compose",
            "-p",
            project,
            "-f",
            str(ROOT / "quwoquan_ops" / "environments" / "compose" / "docker-compose.beta-backing.yaml"),
            "down",
            "-v",
        ]
    else:
        return False, f"wipe not supported for {target_name}"

    # First stop project if running.
    stop = subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True, check=False)
    if stop.returncode != 0:
        # Fallback: remove known volumes by name after killing containers.
        containers = subprocess.run(
            [
                "docker",
                "ps",
                "-aq",
                "--filter",
                f"label=com.docker.compose.project={project}",
            ],
            text=True,
            capture_output=True,
            check=False,
        )
        ids = [line.strip() for line in containers.stdout.splitlines() if line.strip()]
        if ids:
            subprocess.run(["docker", "rm", "-f", *ids], check=False, capture_output=True)
        volumes = _volume_names(project)
        if volumes:
            rm = subprocess.run(
                ["docker", "volume", "rm", "-f", *volumes],
                text=True,
                capture_output=True,
                check=False,
            )
            if rm.returncode != 0:
                return False, (rm.stderr or stop.stderr or "volume rm failed")[:400]
            return True, f"wiped volumes={','.join(volumes)}"
        return False, (stop.stderr or stop.stdout or "compose down -v failed")[:400]
    return True, f"compose down -v completed for {project}"


def format_drift_gate_block(result: MigrationDriftProbeResult) -> str:
    parts = [
        f"GATE_BLOCK: postgres migration checksum drift on {result.target}",
        result.detail,
    ]
    for finding in result.findings[:5]:
        parts.append(
            f"{finding.filename}: applied={finding.applied_checksum[:12]}… "
            f"current={finding.current_checksum[:12]}…"
        )
    parts.append("local-env-gate will wipe declared postgres volume and retry once")
    return "; ".join(parts)
