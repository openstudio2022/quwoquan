"""Alpha test-live split-services to service-core atomic cutover."""

from __future__ import annotations

import hashlib
import json
import subprocess
import time
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

from quwoquan_ops.cli.lib.common import utc_now, write_json
from quwoquan_ops.cli.lib.service_core_composition import (
    SERVICE_CORE_MODULES,
    SERVICE_CORE_WORKLOAD,
)


PROJECT = "quwoquan_alpha_test_live"
TARGET = "alpha-local"
MANDATORY_STANDALONE = frozenset(
    {
        "recommendation-service",
        "realtime-gateway",
        "rtc-service",
        "product-ops-service",
        "platform-ops-service",
    }
)
MANDATORY_INFRA = frozenset(
    {"mongodb", "postgres", "redis", "elasticsearch"}
)
MODULE_PROBES = (
    ("search-service", 18095, "/readyz"),
    ("content-service", 18080, "/healthz"),
    ("user-service", 18081, "/readyz"),
    ("chat-service", 18081, "/healthz"),
)
USER_MIGRATION_ROOT = Path(
    "quwoquan_service/services/user-service/resources/migrations"
)

Runner = Callable[..., subprocess.CompletedProcess[str]]


class ServiceCoreCutoverError(ValueError):
    """The cutover cannot continue without violating its safety boundary."""


def _details(result: subprocess.CompletedProcess[str]) -> list[str]:
    rows = [
        row.strip()
        for row in (result.stderr + "\n" + result.stdout).splitlines()
        if row.strip()
    ]
    return rows[-20:]


def _write_text_atomic(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(content, encoding="utf-8")
    temporary.replace(path)


def _capture_candidate_failure_evidence(
    runner: Runner,
    container: Mapping[str, Any],
    report_dir: Path,
) -> dict[str, Any]:
    container_id = str(container.get("Id") or "")
    if not container_id:
        raise ServiceCoreCutoverError(
            "failed service-core container has no stable identity"
        )
    evidence_dir = report_dir / "failed-candidate" / container_id[:12]
    logs = runner(
        ["docker", "logs", "--timestamps", container_id],
        env={},
        timeout_seconds=60,
    )
    inspected = runner(
        ["docker", "inspect", container_id],
        env={},
        timeout_seconds=30,
    )
    current = dict(container)
    if inspected.returncode == 0:
        try:
            payload = json.loads(inspected.stdout)
            if isinstance(payload, list) and len(payload) == 1:
                current = dict(payload[0])
        except (TypeError, ValueError, json.JSONDecodeError):
            pass
    config = current.get("Config") or {}
    state = current.get("State") or {}
    environment_keys = sorted(
        {
            str(item).partition("=")[0]
            for item in config.get("Env") or ()
            if str(item).partition("=")[0]
        }
    )
    evidence = {
        "schema": "stackctl.service_core_candidate_failure",
        "capturedAt": utc_now(),
        "container": {
            "id": container_id,
            "name": str(current.get("Name") or "").lstrip("/"),
            "image": str(config.get("Image") or ""),
            "imageId": str(current.get("Image") or ""),
            "configHash": str(
                (config.get("Labels") or {}).get(
                    "com.docker.compose.config-hash",
                    "",
                )
            ),
            "state": {
                "status": state.get("Status"),
                "exitCode": state.get("ExitCode"),
                "oomKilled": state.get("OOMKilled"),
                "error": state.get("Error"),
                "startedAt": state.get("StartedAt"),
                "finishedAt": state.get("FinishedAt"),
                "health": state.get("Health"),
            },
            "effectiveEnvironmentKeys": environment_keys,
            "labels": config.get("Labels") or {},
            "mounts": current.get("Mounts") or [],
            "networks": (current.get("NetworkSettings") or {}).get(
                "Networks",
                {},
            ),
        },
        "logs": {
            "path": str(evidence_dir / "container.log"),
            "exitCode": logs.returncode,
            "captureErrors": _details(logs) if logs.returncode != 0 else [],
        },
        "inspect": {
            "exitCode": inspected.returncode,
            "captureErrors": (
                _details(inspected) if inspected.returncode != 0 else []
            ),
        },
    }
    _write_text_atomic(
        evidence_dir / "container.log",
        logs.stdout + logs.stderr,
    )
    write_json(evidence_dir / "evidence.json", evidence)
    return {
        "containerId": container_id,
        "evidencePath": str(evidence_dir / "evidence.json"),
        "logsPath": str(evidence_dir / "container.log"),
        "preservedStopped": True,
    }


def _run(
    runner: Runner,
    command: Sequence[str],
    *,
    environment: Mapping[str, str] | None = None,
    timeout_seconds: float = 120,
) -> subprocess.CompletedProcess[str]:
    result = runner(
        list(command),
        env=dict(environment or {}),
        timeout_seconds=timeout_seconds,
    )
    if result.returncode != 0:
        raise ServiceCoreCutoverError(
            f"command failed ({' '.join(command)}): " + "; ".join(_details(result))
        )
    return result


def _compose_base(rendered: Mapping[str, Any]) -> list[str]:
    plan = rendered["plan"]
    command = ["docker", "compose", "-p", str(plan["composeProject"])]
    for path in rendered["composeFiles"]:
        command.extend(("-f", str(path)))
    for profile in rendered["composeProfiles"]:
        command.extend(("--profile", str(profile)))
    return command


def _inspect_project(runner: Runner) -> list[dict[str, Any]]:
    lookup = _run(
        runner,
        [
            "docker",
            "ps",
            "-aq",
            "--filter",
            f"label=com.docker.compose.project={PROJECT}",
        ],
        timeout_seconds=30,
    )
    ids = [row.strip() for row in lookup.stdout.splitlines() if row.strip()]
    if not ids:
        raise ServiceCoreCutoverError("Alpha Compose project has no containers")
    inspected = _run(runner, ["docker", "inspect", *ids], timeout_seconds=30)
    payload = json.loads(inspected.stdout)
    if not isinstance(payload, list):
        raise ServiceCoreCutoverError("Alpha container inspection is invalid")
    return payload


def _service(container: Mapping[str, Any]) -> str:
    return str(
        ((container.get("Config") or {}).get("Labels") or {}).get(
            "com.docker.compose.service"
        )
        or ""
    )


def _state_issue(container: Mapping[str, Any]) -> str:
    state = container.get("State") or {}
    status = str(state.get("Status") or "")
    if status != "running":
        return f"status={status or 'missing'}"
    health = state.get("Health")
    if isinstance(health, Mapping) and health.get("Status") != "healthy":
        return f"health={health.get('Status') or 'missing'}"
    return ""


def _wait_service(
    runner: Runner,
    service: str,
    *,
    timeout_seconds: float,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    last_issue = "container missing"
    while time.monotonic() < deadline:
        matches = [
            row for row in _inspect_project(runner) if _service(row) == service
        ]
        if len(matches) == 1:
            last_issue = _state_issue(matches[0])
            if not last_issue:
                return matches[0]
            if (matches[0].get("State") or {}).get("Status") in {
                "dead",
                "exited",
            }:
                raise ServiceCoreCutoverError(
                    f"{service} terminated before readiness: {last_issue}"
                )
        elif len(matches) > 1:
            last_issue = f"found {len(matches)} containers"
        time.sleep(1)
    raise ServiceCoreCutoverError(
        f"{service} did not become ready: {last_issue}"
    )


def _container_manifest(container: Mapping[str, Any]) -> dict[str, Any]:
    config = container.get("Config") or {}
    labels = config.get("Labels") or {}
    network_settings = container.get("NetworkSettings") or {}
    host_config = container.get("HostConfig") or {}
    return {
        "service": _service(container),
        "name": str(container.get("Name") or "").removeprefix("/"),
        "id": str(container.get("Id") or ""),
        "image": str(config.get("Image") or ""),
        "imageId": str(container.get("Image") or ""),
        "configHash": str(labels.get("com.docker.compose.config-hash") or ""),
        "configFiles": str(
            labels.get("com.docker.compose.project.config_files") or ""
        ),
        "networks": sorted((network_settings.get("Networks") or {}).keys()),
        "ports": host_config.get("PortBindings") or {},
        "recoveryCommand": "docker start " + str(container.get("Id") or ""),
    }


def _environment(container: Mapping[str, Any]) -> dict[str, str]:
    rows = ((container.get("Config") or {}).get("Env") or [])
    return {
        row.split("=", 1)[0]: row.split("=", 1)[1]
        for row in rows
        if isinstance(row, str) and "=" in row
    }


def _validate_mongo_recommendation_topology(
    by_service: Mapping[str, Sequence[Mapping[str, Any]]],
) -> dict[str, Any]:
    mongo_rows = by_service.get("mongodb", ())
    recommendation_rows = by_service.get("recommendation-service", ())
    if len(mongo_rows) != 1 or len(recommendation_rows) != 1:
        raise ServiceCoreCutoverError(
            "MongoDB/Recommendation container identity is ambiguous"
        )
    mongo = mongo_rows[0]
    recommendation = recommendation_rows[0]
    mongo_networks = (mongo.get("NetworkSettings") or {}).get("Networks") or {}
    recommendation_networks = (
        (recommendation.get("NetworkSettings") or {}).get("Networks") or {}
    )
    shared_networks = sorted(set(mongo_networks) & set(recommendation_networks))
    if not shared_networks:
        raise ServiceCoreCutoverError(
            "MongoDB and Recommendation share no Compose network"
        )
    if not any(
        "mongodb" in set((mongo_networks[name] or {}).get("Aliases") or ())
        for name in shared_networks
    ):
        raise ServiceCoreCutoverError(
            "MongoDB has no mongodb DNS alias on a shared network"
        )
    recommendation_environment = _environment(recommendation)
    if recommendation_environment.get("MONGODB_URI") != (
        "mongodb://mongodb:27017/?directConnection=true"
    ):
        raise ServiceCoreCutoverError(
            "Recommendation MongoDB URI drifted from canonical local binding"
        )
    if recommendation_environment.get("MONGODB_DATABASE") != (
        "quwoquan_recommendation"
    ):
        raise ServiceCoreCutoverError(
            "Recommendation MongoDB database identity drifted"
        )
    mongo_data_mounts = [
        mount
        for mount in mongo.get("Mounts") or ()
        if isinstance(mount, Mapping) and mount.get("Destination") == "/data/db"
    ]
    if (
        len(mongo_data_mounts) != 1
        or mongo_data_mounts[0].get("Type") != "volume"
        or mongo_data_mounts[0].get("RW") is not True
    ):
        raise ServiceCoreCutoverError(
            "MongoDB /data/db is not one writable named volume"
        )
    return {
        "sharedNetworks": shared_networks,
        "mongoAlias": "mongodb",
        "mongoVolume": str(mongo_data_mounts[0].get("Name") or ""),
        "mongoUri": recommendation_environment["MONGODB_URI"],
        "mongoDatabase": recommendation_environment["MONGODB_DATABASE"],
    }


def _user_migration_source_checksums(repo_root: Path) -> dict[str, str]:
    migration_root = repo_root / USER_MIGRATION_ROOT
    checksums: dict[str, str] = {}
    for path in sorted(migration_root.rglob("*.up.sql")):
        relative = path.relative_to(migration_root).as_posix()
        ledger_name = (
            path.name
            if relative.startswith("account/user_account/")
            else relative
        )
        checksums[ledger_name] = hashlib.sha256(path.read_bytes()).hexdigest()
    return checksums


def _validate_user_migration_integrity(
    *,
    ledger_checksums: Mapping[str, str],
    source_checksums: Mapping[str, str],
) -> dict[str, Any]:
    missing = sorted(set(ledger_checksums) - set(source_checksums))
    drifted = sorted(
        name
        for name in set(ledger_checksums) & set(source_checksums)
        if ledger_checksums[name] != source_checksums[name]
    )
    if missing or drifted:
        details: list[str] = []
        if missing:
            details.append("applied migrations missing from source: " + ",".join(missing))
        if drifted:
            details.append(
                "applied migration checksum drift: "
                + ",".join(
                    f"{name}[applied={ledger_checksums[name]},"
                    f"source={source_checksums[name]}]"
                    for name in drifted
                )
            )
        raise ServiceCoreCutoverError("; ".join(details))
    return {
        "appliedCount": len(ledger_checksums),
        "sourceCount": len(source_checksums),
        "status": "passed",
    }


def _validate_missing_migration_ledger(
    *,
    business_object_count: int,
) -> None:
    if business_object_count < 0:
        raise ServiceCoreCutoverError(
            "PostgreSQL business object count must not be negative"
        )
    if business_object_count != 0:
        raise ServiceCoreCutoverError(
            "service_schema_migrations is missing from a non-empty database: "
            f"businessObjectCount={business_object_count}"
        )


def _verify_user_migration_integrity(
    runner: Runner,
    postgres: Mapping[str, Any],
) -> dict[str, Any]:
    state_query = """
WITH user_namespaces AS (
  SELECT oid, nspname
  FROM pg_namespace
  WHERE nspname NOT LIKE 'pg_%'
    AND nspname <> 'information_schema'
),
business_objects AS (
  SELECT c.oid
  FROM pg_class AS c
  JOIN user_namespaces AS n ON n.oid = c.relnamespace
  WHERE c.relkind IN ('r', 'p', 'v', 'm', 'S', 'f')
  UNION
  SELECT p.oid
  FROM pg_proc AS p
  JOIN user_namespaces AS n ON n.oid = p.pronamespace
  UNION
  SELECT t.oid
  FROM pg_type AS t
  JOIN user_namespaces AS n ON n.oid = t.typnamespace
  WHERE t.typtype IN ('c', 'd', 'e', 'r')
  UNION
  SELECT n.oid
  FROM user_namespaces AS n
  WHERE n.nspname <> 'public'
)
SELECT
  CASE
    WHEN to_regclass('public.service_schema_migrations') IS NULL THEN '0'
    ELSE '1'
  END,
  count(*)
FROM business_objects
""".strip()
    state = _run(
        runner,
        [
            "docker",
            "exec",
            str(postgres["Id"]),
            "psql",
            "-U",
            "quwoquan",
            "-d",
            "quwoquan",
            "-At",
            "-F",
            "\t",
            "-c",
            state_query,
        ],
        timeout_seconds=30,
    )
    state_row = state.stdout.strip()
    ledger_exists_text, separator, business_object_count_text = (
        state_row.partition("\t")
    )
    if (
        not separator
        or ledger_exists_text not in {"0", "1"}
        or not business_object_count_text.isdigit()
    ):
        raise ServiceCoreCutoverError(
            "PostgreSQL migration ledger state query returned malformed output"
        )
    ledger_exists = ledger_exists_text == "1"
    business_object_count = int(business_object_count_text)
    repo_root = Path(__file__).resolve().parents[3]
    source_checksums = _user_migration_source_checksums(repo_root)
    if not ledger_exists:
        _validate_missing_migration_ledger(
            business_object_count=business_object_count,
        )
        result = _validate_user_migration_integrity(
            ledger_checksums={},
            source_checksums=source_checksums,
        )
        return {
            **result,
            "businessObjectCount": business_object_count,
            "emptyDatabaseBootstrap": True,
        }

    query = (
        "SELECT filename,checksum FROM service_schema_migrations "
        "WHERE service_name='user-service' ORDER BY filename"
    )
    result = _run(
        runner,
        [
            "docker",
            "exec",
            str(postgres["Id"]),
            "psql",
            "-U",
            "quwoquan",
            "-d",
            "quwoquan",
            "-At",
            "-F",
            "\t",
            "-c",
            query,
        ],
        timeout_seconds=30,
    )
    ledger_checksums: dict[str, str] = {}
    for row in result.stdout.splitlines():
        filename, separator, checksum = row.partition("\t")
        if not separator or not filename or not checksum:
            raise ServiceCoreCutoverError(
                "user-service migration ledger query returned malformed rows"
            )
        ledger_checksums[filename] = checksum
    result = _validate_user_migration_integrity(
        ledger_checksums=ledger_checksums,
        source_checksums=source_checksums,
    )
    return {
        **result,
        "businessObjectCount": business_object_count,
        "emptyDatabaseBootstrap": False,
    }


def _validate_projection(payload: Mapping[str, Any]) -> dict[str, Any]:
    services = payload.get("services")
    if not isinstance(services, Mapping):
        raise ServiceCoreCutoverError("canonical Compose has no service map")
    actual = set(services)
    if SERVICE_CORE_WORKLOAD not in actual:
        raise ServiceCoreCutoverError("canonical Compose has no service-core")
    leaked = sorted(set(SERVICE_CORE_MODULES) & actual)
    if leaked:
        raise ServiceCoreCutoverError(
            "canonical Compose still contains split core: " + ",".join(leaked)
        )
    missing = sorted((MANDATORY_STANDALONE | MANDATORY_INFRA) - actual)
    if missing:
        raise ServiceCoreCutoverError(
            "canonical Compose misses required workloads: " + ",".join(missing)
        )
    core = services[SERVICE_CORE_WORKLOAD]
    networks = core.get("networks") if isinstance(core, Mapping) else None
    default_network = (
        networks.get("default") if isinstance(networks, Mapping) else None
    )
    aliases = (
        default_network.get("aliases")
        if isinstance(default_network, Mapping)
        else None
    )
    if set(aliases or ()) != set(SERVICE_CORE_MODULES):
        raise ServiceCoreCutoverError(
            "service-core network aliases do not match all 11 modules"
        )
    return {
        "services": sorted(actual),
        "coreModules": list(SERVICE_CORE_MODULES),
        "coreAliases": sorted(aliases),
        "infraImages": {
            service: str((services[service] or {}).get("image") or "")
            for service in sorted(MANDATORY_INFRA)
        },
    }


def _validate_infra_projection_identity(
    by_service: Mapping[str, Sequence[Mapping[str, Any]]],
    projection: Mapping[str, Any],
) -> None:
    expected_images = projection.get("infraImages")
    if not isinstance(expected_images, Mapping):
        raise ServiceCoreCutoverError(
            "canonical Compose infrastructure image identity is missing"
        )
    for service in sorted(MANDATORY_INFRA):
        rows = by_service.get(service, ())
        if len(rows) != 1:
            raise ServiceCoreCutoverError(
                f"{service} runtime identity is ambiguous"
            )
        actual = str((rows[0].get("Config") or {}).get("Image") or "")
        expected = str(expected_images.get(service) or "")
        if not expected or actual != expected:
            raise ServiceCoreCutoverError(
                f"{service} runtime image identity is stale: "
                f"actual={actual!r} expected={expected!r}"
            )


def _probe_modules(runner: Runner, container_id: str) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for module, port, path in MODULE_PROBES:
        command = [
            "docker",
            "exec",
            container_id,
            "wget",
            "-qO-",
            "--header",
            f"Host: {module}",
            f"http://127.0.0.1:{port}{path}",
        ]
        result = _run(runner, command, timeout_seconds=20)
        results.append(
            {
                "module": module,
                "path": path,
                "status": "passed",
                "response": result.stdout.strip()[:500],
            }
        )
    return results


def execute(
    *,
    target: str,
    compose_project: str,
    preserve_volumes: bool,
    report_dir: Path,
    rendered: Mapping[str, Any],
    workspace_before: Mapping[str, Any],
    workspace_after_build: Callable[[], Mapping[str, Any]],
    leases: Sequence[Mapping[str, Any]],
    runner: Runner,
    commit_runtime: Callable[[Mapping[str, Any]], Mapping[str, Any]],
) -> dict[str, Any]:
    """Execute one exact Alpha-only cutover with automatic rollback."""

    if (
        target != TARGET
        or compose_project != PROJECT
        or rendered["plan"].get("composeProject") != PROJECT
    ):
        raise ServiceCoreCutoverError(
            "service-core cutover is restricted to exact alpha-local test-live project"
        )
    if preserve_volumes is not True:
        raise ServiceCoreCutoverError("--preserve-volumes must be explicit")
    if leases:
        raise ServiceCoreCutoverError("active Alpha consumer lease blocks cutover")

    report_dir.mkdir(parents=True, exist_ok=True)
    base = _compose_base(rendered)
    config = _run(
        runner,
        [*base, "config", "--format", "json"],
        environment=rendered["environment"],
        timeout_seconds=90,
    )
    projection = _validate_projection(json.loads(config.stdout))

    before = _inspect_project(runner)
    by_service: dict[str, list[dict[str, Any]]] = {}
    for container in before:
        by_service.setdefault(_service(container), []).append(container)
    _validate_infra_projection_identity(by_service, projection)
    dependency_topology = _validate_mongo_recommendation_topology(by_service)
    for service in SERVICE_CORE_MODULES:
        if len(by_service.get(service, ())) != 1:
            raise ServiceCoreCutoverError(
                f"expected exactly one old {service} container"
            )
    postgres_rows = by_service.get("postgres", ())
    if len(postgres_rows) != 1:
        raise ServiceCoreCutoverError("postgres container identity is ambiguous")
    migration_integrity = _verify_user_migration_integrity(
        runner,
        postgres_rows[0],
    )
    failed_core = by_service.get(SERVICE_CORE_WORKLOAD, ())
    if failed_core:
        if (
            len(failed_core) != 1
            or (failed_core[0].get("State") or {}).get("Status") != "exited"
        ):
            raise ServiceCoreCutoverError(
                "running or ambiguous service-core already exists before cutover"
            )
        previous_failure_evidence = _capture_candidate_failure_evidence(
            runner,
            failed_core[0],
            report_dir,
        )
        previous_failure_evidence["preservedStopped"] = False
        previous_failure_evidence["removalPolicy"] = "remove_after_capture"
        write_json(
            report_dir / "preexisting-failed-candidate-removal.json",
            previous_failure_evidence,
        )
        _run(
            runner,
            ["docker", "rm", str(failed_core[0]["Id"])],
            timeout_seconds=60,
        )
        by_service.pop(SERVICE_CORE_WORKLOAD, None)

    for service in MANDATORY_INFRA:
        rows = by_service.get(service, ())
        if len(rows) != 1 or _state_issue(rows[0]):
            raise ServiceCoreCutoverError(
                f"required infrastructure is not healthy: {service}"
            )

    # Recommendation is independent and must recover after the earlier Mongo
    # outage. Recreating this one authored workload is the only pre-cutover
    # runtime repair; core, infra, volumes and every other workload are untouched.
    recommendation = by_service.get("recommendation-service", ())
    if len(recommendation) != 1:
        raise ServiceCoreCutoverError("recommendation-service identity is ambiguous")
    if _state_issue(recommendation[0]):
        _run(
            runner,
            ["docker", "restart", str(recommendation[0]["Id"])],
            timeout_seconds=120,
        )
        _wait_service(runner, "recommendation-service", timeout_seconds=180)

    for service in MANDATORY_STANDALONE:
        matches = [
            row for row in _inspect_project(runner) if _service(row) == service
        ]
        if len(matches) != 1 or _state_issue(matches[0]):
            raise ServiceCoreCutoverError(
                f"required standalone workload is not healthy: {service}"
            )

    build = _run(
        runner,
        [*base, "build", SERVICE_CORE_WORKLOAD],
        environment=rendered["environment"],
        timeout_seconds=3600,
    )
    workspace_after = dict(workspace_after_build())
    workspace_changed_during_preflight = (
        workspace_after != dict(workspace_before)
    )

    old_containers = [
        row
        for row in _inspect_project(runner)
        if _service(row) in set(SERVICE_CORE_MODULES)
    ]
    rollback_manifest = {
        "schema": "stackctl.service_core_cutover_rollback",
        "target": TARGET,
        "composeProject": PROJECT,
        "preserveVolumes": True,
        "createdAt": utc_now(),
        "containers": [
            _container_manifest(row)
            for row in sorted(old_containers, key=_service)
        ],
        "recoveryCommands": [
            "docker start " + str(row.get("Id") or "")
            for row in sorted(old_containers, key=_service)
        ],
    }
    rollback_path = report_dir / "rollback-manifest.json"
    write_json(rollback_path, rollback_manifest)
    write_json(
        report_dir / "projection.json",
        {
            **projection,
            "dependencyTopology": dependency_topology,
            "migrationIntegrity": migration_integrity,
        },
    )

    old_ids = [str(row["Id"]) for row in old_containers]
    transaction_started_at = utc_now()
    transaction_started = time.monotonic()
    rollback_triggered = False
    probes: list[dict[str, Any]] = []
    try:
        _run(runner, ["docker", "stop", *old_ids], timeout_seconds=120)
        _run(
            runner,
            [*base, "up", "-d", "--no-deps", SERVICE_CORE_WORKLOAD],
            environment=rendered["environment"],
            timeout_seconds=420,
        )
        core = _wait_service(runner, SERVICE_CORE_WORKLOAD, timeout_seconds=240)
        probes = _probe_modules(runner, str(core["Id"]))
        committed_receipt = dict(commit_runtime(rendered["plan"]))
    except Exception as exc:
        rollback_triggered = True
        core_rows = [
            row
            for row in _inspect_project(runner)
            if _service(row) == SERVICE_CORE_WORKLOAD
        ]
        candidate_evidence: list[dict[str, Any]] = []
        if core_rows:
            for row in core_rows:
                try:
                    candidate_evidence.append(
                        _capture_candidate_failure_evidence(
                            runner,
                            row,
                            report_dir,
                        )
                    )
                except Exception as evidence_error:
                    candidate_evidence.append(
                        {
                            "containerId": str(row.get("Id") or ""),
                            "captureError": str(evidence_error),
                            "preservedStopped": True,
                        }
                    )
            runner(
                ["docker", "stop", str(core_rows[0]["Id"])],
                timeout_seconds=60,
            )
        restart = runner(["docker", "start", *old_ids], timeout_seconds=120)
        result = {
            "exitCode": 2,
            "status": "gate_block",
            "blockerKind": "service_core_cutover_rolled_back",
            "details": [str(exc), *_details(restart)],
            "rollbackTriggered": True,
            "rollbackManifest": str(rollback_path),
            "candidateEvidence": candidate_evidence,
            "transactionStartedAt": transaction_started_at,
            "downtimeMs": round((time.monotonic() - transaction_started) * 1000),
        }
        write_json(report_dir / "report.json", result)
        return result

    downtime_ms = round((time.monotonic() - transaction_started) * 1000)
    _run(runner, ["docker", "rm", *old_ids], timeout_seconds=120)
    after = _inspect_project(runner)
    remaining_old = [
        _service(row) for row in after if _service(row) in set(SERVICE_CORE_MODULES)
    ]
    core_rows = [
        row for row in after if _service(row) == SERVICE_CORE_WORKLOAD
    ]
    if remaining_old or len(core_rows) != 1 or _state_issue(core_rows[0]):
        raise ServiceCoreCutoverError(
            "post-cutover topology did not converge after old core removal"
        )
    result = {
        "exitCode": 0,
        "status": "passed",
        "blockerKind": "",
        "details": ["11 split core containers replaced by one service-core"],
        "rollbackTriggered": rollback_triggered,
        "rollbackManifest": str(rollback_path),
        "transactionStartedAt": transaction_started_at,
        "downtimeMs": downtime_ms,
        "projection": projection,
        "dependencyTopology": dependency_topology,
        "migrationIntegrity": migration_integrity,
        "moduleProbes": probes,
        "beforeContainers": rollback_manifest["containers"],
        "afterContainers": [
            _container_manifest(row)
            for row in sorted(after, key=_service)
        ],
        "buildDetails": _details(build),
        "runtimePlan": dict(rendered["plan"]),
        "startupAttempt": committed_receipt,
        "workspaceChangedDuringPreflight": workspace_changed_during_preflight,
        "warnings": (
            [
                "mutable workspace changed after the exact non-promotable "
                "test-live build snapshot was selected"
            ]
            if workspace_changed_during_preflight
            else []
        ),
    }
    write_json(report_dir / "report.json", result)
    return result
