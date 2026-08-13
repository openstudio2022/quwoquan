from __future__ import annotations

import hashlib
import json
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


READ_ALIAS = "quwoquan_objects"
WRITE_ALIAS = "quwoquan_objects-write"
FIRST_GENERATION = "quwoquan_objects-v1"
WRITER_SERVICES = frozenset(
    {
        "circle-service",
        "content-service",
        "entity-service",
        "search-service",
        "service-core",
        "user-service",
    }
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _sha256(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _document_inventory(hits: list[dict[str, Any]]) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    aggregate: list[dict[str, Any]] = []
    for hit in sorted(hits, key=lambda item: str(item["_id"])):
        source = hit.get("_source")
        source_digest = _sha256(_canonical_json(source))
        row = {
            "id": str(hit["_id"]),
            "sourceDigest": source_digest,
            "seqNo": int(hit.get("_seq_no", -1)),
            "primaryTerm": int(hit.get("_primary_term", -1)),
            "version": int(hit.get("_version", -1)),
        }
        rows.append(row)
        aggregate.append({"id": row["id"], "source": source})
    return {
        "count": len(rows),
        "contentDigest": _sha256(_canonical_json(aggregate)),
        "idSetDigest": _sha256(_canonical_json([row["id"] for row in rows])),
        "documents": rows,
    }


def _source_create_body(index_description: dict[str, Any]) -> dict[str, Any]:
    settings = dict(index_description.get("settings", {}).get("index", {}))
    retained_settings = {
        key: settings[key]
        for key in (
            "analysis",
            "max_result_window",
            "number_of_replicas",
            "number_of_shards",
            "refresh_interval",
        )
        if key in settings
    }
    return {
        "settings": retained_settings,
        "mappings": index_description.get("mappings", {}),
    }


class _Elasticsearch:
    def __init__(self, endpoint: str) -> None:
        parsed = urllib.parse.urlparse(endpoint)
        if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost"}:
            raise RuntimeError("local index migration requires a loopback HTTP endpoint")
        self.endpoint = endpoint.rstrip("/")

    def request(
        self,
        method: str,
        path: str,
        body: dict[str, Any] | bytes | None = None,
        *,
        expected: tuple[int, ...] = (200,),
        content_type: str = "application/json",
    ) -> Any:
        data: bytes | None
        if isinstance(body, bytes):
            data = body
        elif body is None:
            data = None
        else:
            data = _canonical_json(body)
        request = urllib.request.Request(
            self.endpoint + path,
            data=data,
            method=method,
            headers={"Content-Type": content_type},
        )
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                payload = response.read()
                status = response.status
        except urllib.error.HTTPError as exc:
            payload = exc.read()
            status = exc.code
        if status not in expected:
            raise RuntimeError(
                f"Elasticsearch {method} {path} returned {status}: "
                f"{payload[:500].decode('utf-8', errors='replace')}"
            )
        if not payload:
            return {}
        return json.loads(payload)

    def index_exists(self, index: str) -> bool:
        request = urllib.request.Request(self.endpoint + "/" + index, method="HEAD")
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                return response.status == 200
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return False
            raise

    def describe_index(self, index: str) -> dict[str, Any]:
        payload = self.request("GET", "/" + index)
        if set(payload) != {index}:
            raise RuntimeError(f"expected physical index {index!r}, got {sorted(payload)}")
        return payload[index]

    def documents(self, index: str) -> list[dict[str, Any]]:
        payload = self.request(
            "POST",
            f"/{index}/_search?seq_no_primary_term=true&version=true",
            {
                "query": {"match_all": {}},
                "size": 10000,
                "track_total_hits": True,
            },
        )
        total = int(payload["hits"]["total"]["value"])
        hits = list(payload["hits"]["hits"])
        if total != len(hits):
            raise RuntimeError(f"inventory truncated: total={total} hits={len(hits)}")
        return hits

    def create_index(self, index: str, body: dict[str, Any]) -> None:
        self.request("PUT", "/" + index, body)

    def delete_index(self, index: str) -> None:
        self.request("DELETE", "/" + index, expected=(200, 404))

    def reindex(self, source: str, destination: str) -> dict[str, Any]:
        result = self.request(
            "POST",
            "/_reindex?wait_for_completion=true&refresh=true",
            {
                "conflicts": "abort",
                "source": {"index": source},
                "dest": {"index": destination},
            },
        )
        if result.get("failures"):
            raise RuntimeError(f"reindex {source} -> {destination} failed: {result['failures']}")
        if int(result.get("version_conflicts", 0)) != 0:
            raise RuntimeError(f"reindex {source} -> {destination} had version conflicts")
        return result

    def refresh(self, index: str) -> None:
        self.request("POST", f"/{index}/_refresh")

    def convert_to_aliases(self, source: str, target: str) -> None:
        self.request(
            "POST",
            "/_aliases",
            {
                "actions": [
                    {"remove_index": {"index": source}},
                    {"add": {"index": target, "alias": READ_ALIAS}},
                    {
                        "add": {
                            "index": target,
                            "alias": WRITE_ALIAS,
                            "is_write_index": True,
                        }
                    },
                ]
            },
        )

    def alias_bindings(self) -> dict[str, Any]:
        return self.request("GET", f"/_alias/{READ_ALIAS},{WRITE_ALIAS}")


def _run(command: list[str], *, timeout: int = 180) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"command failed ({result.returncode}): {' '.join(command)}: "
            f"{result.stderr.strip() or result.stdout.strip()}"
        )
    return result


def _canonical_schema(repo_root: Path) -> dict[str, Any]:
    result = _run(
        [
            "docker",
            "run",
            "--rm",
            "-v",
            f"{repo_root}:/workspace",
            "-w",
            "/workspace/quwoquan_service",
            "golang:1.24-bookworm",
            "go",
            "run",
            "./services/search-service/cmd/search-index-schema",
        ],
        timeout=300,
    )
    return json.loads(result.stdout)


def _runtime_identity(container_name: str) -> dict[str, Any]:
    container = json.loads(_run(["docker", "inspect", container_name]).stdout)[0]
    if container["State"]["Status"] != "running":
        raise RuntimeError(f"Elasticsearch container {container_name} is not running")
    labels = container["Config"].get("Labels") or {}
    if labels.get("com.docker.compose.project") != "quwoquan_alpha_test_live":
        raise RuntimeError("Elasticsearch container is not owned by alpha-local test_live")
    mounts = [
        {"name": item.get("Name", ""), "destination": item.get("Destination", "")}
        for item in container.get("Mounts", [])
    ]
    image = json.loads(_run(["docker", "image", "inspect", container["Image"]]).stdout)[0]
    bindings = (container.get("NetworkSettings", {}).get("Ports") or {}).get(
        "9200/tcp"
    ) or []
    host_ports = {
        str(binding.get("HostPort", "")).strip()
        for binding in bindings
        if str(binding.get("HostPort", "")).strip()
    }
    if len(host_ports) != 1 or not next(iter(host_ports)).isdigit():
        raise RuntimeError("Alpha Elasticsearch must publish exactly one local HTTP port")
    host_port = next(iter(host_ports))
    return {
        "containerId": container["Id"],
        "containerImage": container["Config"]["Image"],
        "imageId": container["Image"],
        "imageArchitecture": image["Architecture"],
        "mounts": mounts,
        "endpoint": f"http://127.0.0.1:{host_port}",
    }


def _running_writer_containers() -> list[str]:
    rows = _run(
        [
            "docker",
            "ps",
            "--filter",
            "label=com.docker.compose.project=quwoquan_alpha_test_live",
            "--format",
            "{{json .}}",
        ]
    ).stdout.splitlines()
    names: list[str] = []
    for row in rows:
        parsed = json.loads(row)
        service = str(parsed.get("Label com.docker.compose.service", "")).strip()
        if not service:
            inspected = json.loads(_run(["docker", "inspect", parsed["ID"]]).stdout)[0]
            service = str(
                (inspected["Config"].get("Labels") or {}).get(
                    "com.docker.compose.service", ""
                )
            )
        if service in WRITER_SERVICES:
            names.append(str(parsed["Names"]))
    return sorted(names)


def _stop_writers() -> tuple[list[str], float]:
    names = _running_writer_containers()
    started = time.monotonic()
    if names:
        _run(["docker", "stop", "--time", "30", *names], timeout=90)
    return names, started


def _restart_writers(names: list[str]) -> None:
    if names:
        _run(["docker", "start", *names], timeout=120)


def _assert_inventory(
    expected: dict[str, Any],
    actual: dict[str, Any],
    *,
    label: str,
) -> None:
    for key in ("count", "contentDigest", "idSetDigest"):
        if expected[key] != actual[key]:
            raise RuntimeError(
                f"{label} inventory mismatch for {key}: "
                f"expected={expected[key]} actual={actual[key]}"
            )


def _rollback(
    es: _Elasticsearch,
    *,
    source_body: dict[str, Any],
    backup: str,
    target: str,
    expected_inventory: dict[str, Any],
) -> dict[str, Any]:
    es.delete_index(target)
    if es.index_exists(READ_ALIAS):
        es.delete_index(READ_ALIAS)
    es.create_index(READ_ALIAS, source_body)
    reindex = es.reindex(backup, READ_ALIAS)
    restored = _document_inventory(es.documents(READ_ALIAS))
    _assert_inventory(expected_inventory, restored, label="rollback")
    return {"reindex": reindex, "inventory": restored}


def migrate_alpha_legacy_index(
    repo_root: Path,
    report_dir: Path,
    *,
    expected_count: int,
    confirmation: bool,
    container_name: str = "quwoquan_alpha_test_live-elasticsearch-1",
) -> dict[str, Any]:
    if not confirmation:
        raise RuntimeError("explicit legacy-index migration confirmation is required")
    report_dir.mkdir(parents=True, exist_ok=True)
    receipt_path = report_dir / "search-index-alias-migration.json"
    runtime = _runtime_identity(container_name)
    es = _Elasticsearch(str(runtime["endpoint"]))
    root_identity = es.request("GET", "/")
    if runtime["containerImage"] != "quwoquan/elasticsearch-cjk:8.13.4":
        raise RuntimeError("canonical CJK Elasticsearch image is not running")
    if not es.index_exists(READ_ALIAS):
        raise RuntimeError(f"legacy physical index {READ_ALIAS!r} does not exist")
    alias_probe = es.request(
        "GET",
        f"/_alias/{READ_ALIAS}",
        expected=(200, 404),
    )
    alias_indexes = sorted(
        index
        for index, description in alias_probe.items()
        if isinstance(description, dict)
        and READ_ALIAS in (description.get("aliases") or {})
    )
    if alias_indexes:
        existing_inventory = _document_inventory(es.documents(READ_ALIAS))
        raise RuntimeError(
            f"{READ_ALIAS!r} is already an alias over {alias_indexes}; "
            f"currentCount={existing_inventory['count']} "
            f"expectedLegacyCount={expected_count} "
            f"contentDigest={existing_inventory['contentDigest']}"
        )
    if es.index_exists(FIRST_GENERATION):
        raise RuntimeError(f"target generation {FIRST_GENERATION!r} already exists")

    started_at = _utc_now()
    source_description = es.describe_index(READ_ALIAS)
    source_body = _source_create_body(source_description)
    source_hits = es.documents(READ_ALIAS)
    source_inventory = _document_inventory(source_hits)
    if source_inventory["count"] != expected_count:
        raise RuntimeError(
            f"source count changed: expected={expected_count} "
            f"actual={source_inventory['count']}"
        )
    (report_dir / "source-index-description.json").write_text(
        json.dumps(source_description, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (report_dir / "source-document-inventory.json").write_text(
        json.dumps(source_inventory, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ").lower()
    online_backup = f"{READ_ALIAS}-legacy-backup-{stamp}"
    final_backup = f"{READ_ALIAS}-legacy-backup-final-{stamp}"
    canonical_schema = _canonical_schema(repo_root)
    canonical_schema_digest = _sha256(_canonical_json(canonical_schema))
    es.create_index(online_backup, source_body)
    online_backup_reindex = es.reindex(READ_ALIAS, online_backup)
    online_backup_inventory = _document_inventory(es.documents(online_backup))
    _assert_inventory(source_inventory, online_backup_inventory, label="online backup")
    es.create_index(FIRST_GENERATION, canonical_schema)
    initial_target_reindex = es.reindex(READ_ALIAS, FIRST_GENERATION)
    initial_target_inventory = _document_inventory(es.documents(FIRST_GENERATION))
    _assert_inventory(source_inventory, initial_target_inventory, label="initial target")

    stopped_writers: list[str] = []
    admission_started = 0.0
    switched = False
    rollback_report: dict[str, Any] | None = None
    try:
        stopped_writers, admission_started = _stop_writers()
        final_hits = es.documents(READ_ALIAS)
        final_inventory = _document_inventory(final_hits)
        es.create_index(final_backup, source_body)
        final_backup_reindex = es.reindex(READ_ALIAS, final_backup)
        final_backup_inventory = _document_inventory(es.documents(final_backup))
        _assert_inventory(final_inventory, final_backup_inventory, label="final backup")

        es.delete_index(FIRST_GENERATION)
        es.create_index(FIRST_GENERATION, canonical_schema)
        final_target_reindex = es.reindex(READ_ALIAS, FIRST_GENERATION)
        final_target_inventory = _document_inventory(es.documents(FIRST_GENERATION))
        _assert_inventory(final_inventory, final_target_inventory, label="final target")

        switch_started = time.monotonic()
        es.convert_to_aliases(READ_ALIAS, FIRST_GENERATION)
        switched = True
        switch_duration_ms = int((time.monotonic() - switch_started) * 1000)
        aliases = es.alias_bindings()
        target_aliases = aliases.get(FIRST_GENERATION, {}).get("aliases", {})
        if READ_ALIAS not in target_aliases:
            raise RuntimeError("read alias does not resolve to canonical generation")
        if target_aliases.get(WRITE_ALIAS, {}).get("is_write_index") is not True:
            raise RuntimeError("write alias is missing is_write_index=true")
        promoted_inventory = _document_inventory(READ_ALIAS)
        _assert_inventory(final_inventory, promoted_inventory, label="promoted alias")
        admission_duration_ms = int((time.monotonic() - admission_started) * 1000)
        receipt = {
            "schema": "stackctl.local_search_index_alias_migration",
            "target": "alpha-local",
            "environment": "alpha",
            "status": "passed",
            "startedAt": started_at,
            "completedAt": _utc_now(),
            "cluster": {
                "name": root_identity.get("cluster_name"),
                "uuid": root_identity.get("cluster_uuid"),
                "version": (root_identity.get("version") or {}).get("number"),
            },
            "runtime": runtime,
            "source": {
                "index": READ_ALIAS,
                "descriptionPath": str(report_dir / "source-index-description.json"),
                "inventoryPath": str(report_dir / "source-document-inventory.json"),
                "inventory": source_inventory,
            },
            "backup": {
                "onlineIndex": online_backup,
                "onlineReindex": online_backup_reindex,
                "onlineInventory": online_backup_inventory,
                "finalIndex": final_backup,
                "finalReindex": final_backup_reindex,
                "finalInventory": final_backup_inventory,
            },
            "canonical": {
                "generation": FIRST_GENERATION,
                "schemaDigest": canonical_schema_digest,
                "initialReindex": initial_target_reindex,
                "initialInventory": initial_target_inventory,
                "finalReindex": final_target_reindex,
                "finalInventory": final_target_inventory,
                "readAlias": READ_ALIAS,
                "writeAlias": WRITE_ALIAS,
                "writeAliasIsWriteIndex": True,
                "aliases": aliases,
            },
            "admission": {
                "stoppedWriterContainers": stopped_writers,
                "durationMs": admission_duration_ms,
                "atomicAliasActionDurationMs": switch_duration_ms,
            },
            "rollback": {
                "available": True,
                "backupIndex": final_backup,
                "invoked": False,
            },
        }
        receipt_path.write_text(
            json.dumps(receipt, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return receipt
    except Exception:
        if switched:
            rollback_report = _rollback(
                es,
                source_body=source_body,
                backup=final_backup,
                target=FIRST_GENERATION,
                expected_inventory=_document_inventory(es.documents(final_backup)),
            )
        failure = {
            "schema": "stackctl.local_search_index_alias_migration",
            "target": "alpha-local",
            "environment": "alpha",
            "status": "rolled_back" if rollback_report else "gate_block",
            "startedAt": started_at,
            "completedAt": _utc_now(),
            "runtime": runtime,
            "sourceInventory": source_inventory,
            "rollback": {
                "available": bool(final_backup),
                "backupIndex": final_backup,
                "invoked": rollback_report is not None,
                "result": rollback_report,
            },
        }
        receipt_path.write_text(
            json.dumps(failure, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        raise
    finally:
        _restart_writers(stopped_writers)
