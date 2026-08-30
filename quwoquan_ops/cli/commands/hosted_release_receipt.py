"""stackctl `hosted-release-receipt` 子命令域。

从 stackctl.py 逐字迁出 argparse 表面与编排胶水；hosted release ledger
的读取执行仍由 stackctl 命名空间共享 helper `_run_hosted_release_ledger`
拥有（deploy 等多域共用，且测试经 ``mock.patch.object(stackctl, ...)``
patch 它）。stackctl 命名空间符号一律经函数内延迟导入 `_stackctl`
属性访问，保持 monkeypatch 语义并避免顶层循环 import。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from typing import Any


def register_parser(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    receipt_parser = subparsers.add_parser("hosted-release-receipt")
    receipt_parser.add_argument("--service", required=True)
    receipt_parser.add_argument("--receipt-id", required=True)
    receipt_parser.add_argument(
        "--purpose",
        choices=("last-good", "rollback"),
        required=True,
    )
    receipt_parser.add_argument("--image-digest", required=True)
    receipt_parser.add_argument("--config-digest", required=True)
    receipt_parser.add_argument("--contract-graph-digest", required=True)
    receipt_parser.add_argument("--adapter-digest", required=True)


def command_hosted_release_receipt(args: argparse.Namespace) -> dict[str, Any]:
    """Resolve a release receipt from the hosted service plane, never local output."""
    import quwoquan_ops.cli.stackctl as _stackctl

    receipt_id = str(args.receipt_id or "").strip()
    if re.fullmatch(r"[0-9a-f]{64}", receipt_id) is None:
        return {
            "exitCode": 2,
            "summary": "hosted release receipt readback failed",
            "details": ["receipt id must be a lowercase SHA-256 value"],
        }
    expected_candidate = {
        "imageDigest": str(args.image_digest or "").strip(),
        "configDigest": str(args.config_digest or "").strip(),
        "contractGraphDigest": str(args.contract_graph_digest or "").strip(),
        "adapterDigest": str(args.adapter_digest or "").strip(),
    }
    if any(
        re.fullmatch(r"sha256:[0-9a-f]{64}", value) is None
        for value in expected_candidate.values()
    ):
        return {
            "exitCode": 2,
            "summary": "hosted release receipt readback failed",
            "details": ["candidate digests must all be canonical sha256 values"],
        }
    try:
        readback = _stackctl._run_hosted_release_ledger(
            service=str(args.service).strip(),
            action="receipt",
            receipt_id=receipt_id,
        )
        receipt = readback["receipt"]
        if not isinstance(receipt, dict):
            raise RuntimeError("hosted receipt identity is invalid")
        # Validate this exact receipt schema, closed field set, canonical request
        # projection, generation, authority and content-derived receipt id.  A
        # generic JSON object validator cannot prove release-ledger semantics.
        from quwoquan_ops.cli.prod import hosted_release_ledger

        if (
            set(receipt) != hosted_release_ledger.RECEIPT_FIELDS
            or receipt.get("schema") != hosted_release_ledger.RECEIPT_SCHEMA
            or receipt.get("authority") != hosted_release_ledger.AUTHORITY
            or receipt.get("receiptId") != receipt_id
            or hosted_release_ledger._receipt_id(receipt) != receipt_id
        ):
            raise RuntimeError("hosted release receipt schema is invalid")
        request = {
            field: receipt[field]
            for field in hosted_release_ledger.REQUEST_FIELDS
            if field != "schema"
        }
        request["schema"] = hosted_release_ledger.REQUEST_SCHEMA
        try:
            hosted_release_ledger._validate_request(request)
        except ValueError as error:
            raise RuntimeError("hosted release receipt payload is invalid") from error
        expected_generation = receipt.get("expectedGeneration")
        committed_generation = receipt.get("committedGeneration")
        if (
            not isinstance(expected_generation, int)
            or isinstance(expected_generation, bool)
            or not isinstance(committed_generation, int)
            or isinstance(committed_generation, bool)
            or committed_generation != expected_generation + 1
        ):
            raise RuntimeError("hosted release receipt generation is invalid")
        receipt_bytes = (
            json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        ).encode("utf-8")
        if receipt.get("service") != str(args.service).strip():
            raise RuntimeError("hosted receipt service does not match request")
        if any(receipt.get(field) != value for field, value in expected_candidate.items()):
            raise RuntimeError("hosted receipt candidate binding does not match UAT")
        purpose = str(args.purpose)
        if purpose == "last-good" and not (
            receipt.get("stage") == "100"
            and receipt.get("decision") == "continue"
            and receipt.get("rollbackOutcome") == "not_triggered"
            and receipt.get("lastGoodCandidateDigest")
            == receipt.get("toCandidateDigest")
        ):
            raise RuntimeError("hosted receipt is not a stable 100 last-good release")
        if purpose == "rollback" and not (
            receipt.get("decision") == "rolled_back"
            and receipt.get("rollbackOutcome") == "rolled_back"
            and receipt.get("lastGoodCandidateDigest")
            == receipt.get("toCandidateDigest")
        ):
            raise RuntimeError("hosted receipt does not prove a successful rollback")
    except (RuntimeError, json.JSONDecodeError) as error:
        return {
            "exitCode": 2,
            "summary": "hosted release receipt readback failed",
            "details": [str(error)],
        }
    digest = "sha256:" + hashlib.sha256(receipt_bytes).hexdigest()
    return {
        "exitCode": 0,
        "summary": "hosted release receipt readback verified",
        "details": [f"receipt: receipt:hosted:{receipt_id}"],
        "receiptRef": f"receipt:hosted:{receipt_id}",
        "receiptDigest": digest,
        "candidate": expected_candidate,
        "purpose": purpose,
    }
