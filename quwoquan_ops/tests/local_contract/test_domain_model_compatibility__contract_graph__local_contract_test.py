#!/usr/bin/env python3
"""local_contract for the object-level model-version release gate.

spec_ref: specs/feature-tree/spec.md#req-010
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = (
    ROOT
    / "quwoquan_service/scripts/verify/contract_graph/verify_domain_model_compatibility.py"
)
SPEC = importlib.util.spec_from_file_location("domain_model_compatibility", SCRIPT)
assert SPEC and SPEC.loader
GATE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = GATE
SPEC.loader.exec_module(GATE)


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _field(
    name: str,
    type_name: str = "string",
    *,
    nullable: bool = False,
    role: str = "authoritative_state",
    enum_ref: str | None = None,
) -> dict[str, object]:
    value: dict[str, object] = {
        "name": name,
        "type": type_name,
        "constraints": ["NULLABLE" if nullable else "NOT_NULL"],
        "role": role,
    }
    if enum_ref:
        value["enum_ref"] = enum_ref
    return value


def _graph(*, model_version: str = "1.0") -> dict[str, object]:
    object_path = "sample/context/widget/object.yaml"
    fields_path = "sample/context/widget/fields.yaml"
    storage_path = "sample/context/widget/storage.yaml"
    errors_path = "sample/context/widget/errors.yaml"
    return {
        "objects": [
            {
                "id": "sample.widget",
                "domain": "sample",
                "name": "Widget",
                "kind": "aggregate_root",
                "kindExplicit": True,
                "sourcePath": object_path,
            }
        ],
        "operations": [
            {
                "id": "sample.widget.GetWidget",
                "objectId": "sample.widget",
                "kind": "query",
                "method": "GET",
                "pathTemplate": "/widgets/{widgetId}",
                "responseEntity": "WidgetResponse",
                "security": {"auth_mode": "required", "principal": "owner"},
                "authMode": "required",
                "principal": "persona",
                "ownershipPolicy": "requester_self",
            },
            {
                "id": "sample.widget.UpdateWidget",
                "objectId": "sample.widget",
                "kind": "command",
                "method": "POST",
                "pathTemplate": "/widgets/{widgetId}:update",
                "requestEntity": "UpdateWidgetCommand",
                "requestBodyKind": "object",
                "responseEntity": "WidgetResponse",
                "security": {"auth_mode": "required", "principal": "owner"},
                "authMode": "required",
                "principal": "persona",
                "ownershipPolicy": "requester_self",
                "reliability": {"idempotency": "required"},
                "errorCodes": ["SAMPLE.USER.widget_invalid"],
            },
        ],
        "documents": [
            {
                "path": object_path,
                "content": {
                    "kind": "aggregate_root",
                    "model_version": model_version,
                    "identity": {"fields": ["widgetId"], "version_source": "field"},
                },
            },
            {
                "path": fields_path,
                "content": {
                    "fields": [
                        _field("widgetId"),
                        _field("title"),
                    ],
                    "types": {
                        "WidgetResponse": {
                            "fields": [
                                _field("widgetId"),
                                _field("title"),
                                _field("state", "enum", enum_ref="WidgetState"),
                            ]
                        },
                        "UpdateWidgetCommand": {
                            "fields": [
                                _field("widgetId"),
                                _field("title", nullable=True),
                            ]
                        },
                    },
                    "enums": {
                        "WidgetState": {"values": ["draft", "published"]}
                    },
                },
            },
            {
                "path": storage_path,
                "content": {
                    "backend": "postgresql",
                    "role": "authoritative",
                    "tables": {
                        "widgets": {
                            "pk": ["widget_id"],
                            "columns": [
                                {
                                    "name": "widget_id",
                                    "type": "text",
                                    "constraints": ["NOT_NULL"],
                                },
                                {
                                    "name": "title",
                                    "type": "text",
                                    "constraints": ["NOT_NULL"],
                                },
                            ],
                            "indexes": [
                                {
                                    "name": "idx_widgets_title",
                                    "columns": ["title"],
                                }
                            ],
                        }
                    },
                },
            },
            {
                "path": errors_path,
                "content": {
                    "errors": [
                        {
                            "code": "SAMPLE.USER.widget_invalid",
                            "http_status": 400,
                            "recovery_action": "surface",
                            "disruption_level": "inlineCard",
                        }
                    ]
                },
            },
        ],
    }


def _receipt_readback(graph_path: Path, *, stage: str = "100") -> dict[str, object]:
    digest = _digest(graph_path)
    receipt: dict[str, object] = {
        "schema": GATE.HOSTED_RECEIPT_SCHEMA,
        "authority": GATE.HOSTED_AUTHORITY,
        "service": "prod-stack",
        "stage": stage,
        "triggerStage": stage,
        "decision": "continue",
        "rollbackOutcome": "not_triggered",
        "contractGraphDigest": digest,
        "committedGeneration": 7,
    }
    receipt_id = GATE._receipt_id(receipt)
    receipt["receiptId"] = receipt_id
    return {
        "schema": GATE.HOSTED_READBACK_SCHEMA,
        "authority": GATE.HOSTED_AUTHORITY,
        "receipt": receipt,
        "receiptRef": f"receipt:hosted:{receipt_id}",
    }


class DomainModelCompatibilityLocalContractTest(unittest.TestCase):
    def _run(
        self,
        root: Path,
        baseline: dict[str, object],
        current: dict[str, object],
        *,
        window: dict[str, object] | None = None,
        migration: dict[str, object] | None = None,
    ) -> tuple[int, dict[str, object], bytes]:
        baseline_path = root / "baseline-graph.json"
        current_path = root / "current-graph.json"
        receipt_path = root / "baseline-receipt.json"
        report_path = root / "report.json"
        _write_json(baseline_path, baseline)
        _write_json(current_path, current)
        _write_json(receipt_path, _receipt_readback(baseline_path))
        arguments = [
            "--baseline-receipt",
            str(receipt_path),
            "--baseline-graph",
            str(baseline_path),
            "--current-graph",
            str(current_path),
            "--report",
            str(report_path),
        ]
        if window is not None:
            window["baselineContractGraphDigest"] = _digest(baseline_path)
            window_path = root / "compatibility-window.json"
            _write_json(window_path, window)
            arguments.extend(["--compatibility-window", str(window_path)])
        if migration is not None:
            migration["currentContractGraphDigest"] = _digest(current_path)
            migration_path = root / "migration-plan.json"
            _write_json(migration_path, migration)
            arguments.extend(["--storage-migration-plan", str(migration_path)])
        result = GATE.main(arguments)
        report_bytes = report_path.read_bytes() if report_path.exists() else b""
        report = json.loads(report_bytes) if report_bytes else {}
        return result, report, report_bytes

    def test_additive_query_command_storage_changes_require_one_minor_bump(self) -> None:
        baseline = _graph()
        current = deepcopy(baseline)
        object_document = current["documents"][0]["content"]
        object_document["model_version"] = "1.1"
        fields = current["documents"][1]["content"]
        fields["fields"].append(_field("subtitle", nullable=True))
        fields["types"]["WidgetResponse"]["fields"].append(
            _field("subtitle", nullable=True)
        )
        fields["types"]["UpdateWidgetCommand"]["fields"].append(
            _field("subtitle", nullable=True)
        )
        fields["enums"]["WidgetState"]["values"].append("archived")
        storage = current["documents"][2]["content"]
        storage["tables"]["widgets"]["columns"].append(
            {"name": "subtitle", "type": "text", "constraints": ["NULLABLE"]}
        )
        storage["tables"]["widgets"]["indexes"].append(
            {"name": "idx_widgets_subtitle", "columns": ["subtitle"]}
        )
        with tempfile.TemporaryDirectory() as temporary:
            code, report, first_bytes = self._run(
                Path(temporary), baseline, current
            )
            self.assertEqual(code, 0, report)
            item = report["objects"][0]
            self.assertEqual(item["requiredModelVersion"], "1.1")
            self.assertEqual(
                item["changeImpact"],
                {"query": "compatible", "command": "compatible", "storage": "compatible"},
            )
            code_again, _, second_bytes = self._run(
                Path(temporary), baseline, current
            )
            self.assertEqual(code_again, 0)
            self.assertEqual(first_bytes, second_bytes)

    def test_breaking_changes_fail_closed_until_window_and_quiesced_plan_close(self) -> None:
        baseline = _graph()
        current = deepcopy(baseline)
        current["documents"][0]["content"]["model_version"] = "2.0"
        current["documents"][0]["content"]["identity"]["fields"] = ["tenantId", "widgetId"]
        current["operations"][0]["security"]["principal"] = "admin"
        current["operations"][1]["reliability"]["idempotency"] = "none"
        response_fields = current["documents"][1]["content"]["types"]["WidgetResponse"]["fields"]
        response_fields[:] = [field for field in response_fields if field["name"] != "title"]
        command_fields = current["documents"][1]["content"]["types"]["UpdateWidgetCommand"]["fields"]
        command_fields[:] = [field for field in command_fields if field["name"] != "title"]
        current["documents"][2]["content"]["tables"]["widgets"]["pk"] = ["tenant_id", "widget_id"]
        current["documents"][2]["content"]["tables"]["widgets"]["columns"][1]["type"] = "jsonb"
        with tempfile.TemporaryDirectory() as temporary:
            code, report, _ = self._run(Path(temporary), baseline, current)
            self.assertEqual(code, 2)
            issue_codes = {item["code"] for item in report["issues"]}
            self.assertIn("COMPATIBILITY_WINDOW.OPEN", issue_codes)
            self.assertIn("STORAGE.MIGRATION.BLOCKED", issue_codes)
            item = report["objects"][0]
            self.assertEqual(item["requiredModelVersion"], "2.0")
            self.assertEqual(item["migrationMode"], "quiesced_atomic")

            window = {
                "schema": GATE.WINDOW_SCHEMA,
                "minimumSupportedBuilds": {"android": 17000, "ios": 17000, "web": 17000},
                "operations": [
                    {
                        "operationId": "sample.widget.GetWidget",
                        "windowClosed": True,
                        "usageCount": 0,
                        "affectedAppBuilds": {"android": [], "ios": [], "web": []},
                    },
                    {
                        "operationId": "sample.widget.UpdateWidget",
                        "windowClosed": True,
                        "usageCount": 0,
                        "affectedAppBuilds": {"android": [], "ios": [], "web": []},
                    },
                ],
            }
            migration = {
                "schema": GATE.MIGRATION_SCHEMA,
                "objects": [
                    {
                        "objectId": "sample.widget",
                        "mode": "quiesced_atomic",
                        "commandsPaused": True,
                        "backupVerified": True,
                        "validationVerified": True,
                        "atomicCutover": True,
                        "singleReaderWriter": True,
                        "dualRead": False,
                        "dualWrite": False,
                        "backupDigest": "sha256:" + "a" * 64,
                        "validationDigest": "sha256:" + "b" * 64,
                    }
                ],
            }
            code, report, _ = self._run(
                Path(temporary), baseline, current, window=window, migration=migration
            )
            self.assertEqual(code, 0, report)

    def test_dual_read_or_write_migration_is_always_rejected(self) -> None:
        baseline = _graph()
        current = deepcopy(baseline)
        current["documents"][0]["content"]["model_version"] = "2.0"
        current["documents"][2]["content"]["tables"]["widgets"]["pk"] = ["other_id"]
        migration = {
            "schema": GATE.MIGRATION_SCHEMA,
            "objects": [
                {
                    "objectId": "sample.widget",
                    "mode": "quiesced_atomic",
                    "commandsPaused": True,
                    "backupVerified": True,
                    "validationVerified": True,
                    "atomicCutover": True,
                    "singleReaderWriter": True,
                    "dualRead": True,
                    "dualWrite": False,
                    "backupDigest": "sha256:" + "a" * 64,
                    "validationDigest": "sha256:" + "b" * 64,
                }
            ],
        }
        with tempfile.TemporaryDirectory() as temporary:
            code, report, _ = self._run(
                Path(temporary), baseline, current, migration=migration
            )
            self.assertEqual(code, 2)
            self.assertIn("dual_read_or_dual_write_forbidden", str(report["issues"]))

    def test_graphql_documents_detect_enum_tightening_and_authorization_change(self) -> None:
        baseline = _graph()
        current = deepcopy(baseline)
        baseline["documents"].append(
            {
                "path": "sample/context/widget/graphql.yaml",
                "content": {
                    "persisted_queries": [
                        {
                            "operation_id": "sample.widget.WidgetCard",
                            "object_id": "sample.widget",
                            "response_entity": "WidgetResponse",
                            "authorization": {"principal": "persona"},
                        }
                    ]
                },
            }
        )
        current["documents"].append(deepcopy(baseline["documents"][-1]))
        current["documents"][0]["content"]["model_version"] = "2.0"
        graphql = current["documents"][-1]["content"]["persisted_queries"][0]
        graphql["authorization"]["principal"] = "admin"
        enum_values = current["documents"][1]["content"]["enums"]["WidgetState"]["values"]
        enum_values.remove("draft")
        window = {
            "schema": GATE.WINDOW_SCHEMA,
            "minimumSupportedBuilds": {"android": 17000},
            "operations": [
                {
                    "operationId": "sample.widget.GetWidget",
                    "windowClosed": True,
                    "usageCount": 0,
                    "affectedAppBuilds": {"android": []},
                },
                {
                    "operationId": "sample.widget.WidgetCard",
                    "windowClosed": True,
                    "usageCount": 0,
                    "affectedAppBuilds": {"android": []},
                }
            ],
        }
        with tempfile.TemporaryDirectory() as temporary:
            code, report, _ = self._run(
                Path(temporary), baseline, current, window=window
            )
            self.assertEqual(code, 0, report)
            changes = report["objects"][0]["changes"]
            codes = {item["code"] for item in changes}
            self.assertIn("query_authorization_changed", codes)
            self.assertIn("query_response_enum_tightened", codes)

    def test_arbitrary_or_digest_mismatched_baseline_receipt_is_input_error(self) -> None:
        baseline = _graph()
        current = _graph()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            baseline_path = root / "baseline.json"
            current_path = root / "current.json"
            receipt_path = root / "receipt.json"
            report_path = root / "report.json"
            _write_json(baseline_path, baseline)
            _write_json(current_path, current)
            _write_json(
                receipt_path,
                {"schema": "local-receipt", "contractGraphDigest": _digest(baseline_path)},
            )
            code = GATE.main(
                [
                    "--baseline-receipt",
                    str(receipt_path),
                    "--baseline-graph",
                    str(baseline_path),
                    "--current-graph",
                    str(current_path),
                    "--report",
                    str(report_path),
                ]
            )
            self.assertEqual(code, 1)
            self.assertFalse(report_path.exists())


if __name__ == "__main__":
    unittest.main()
