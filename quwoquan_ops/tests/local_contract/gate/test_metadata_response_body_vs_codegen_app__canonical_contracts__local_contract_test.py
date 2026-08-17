from __future__ import annotations

import io
from contextlib import redirect_stderr, redirect_stdout
from unittest import mock

from quwoquan_app.test.local_contract.runtime.verify_metadata_app_contract_gates__local_contract_test import (
    load_verifier,
)


def test_response_gate_reads_declarations_and_rejects_empty_green() -> None:
    gate = load_verifier("verify_metadata_response_body_vs_codegen_app")
    declarations = gate.collect_response_decls()

    assert sum(len(operations) for operations in declarations.values()) > 0
    assert {"content", "chat"}.issubset(declarations)
    with (
        mock.patch.object(gate, "collect_projection_index", return_value={}),
        mock.patch.object(gate, "collect_response_decls", return_value={}),
        redirect_stdout(io.StringIO()),
        redirect_stderr(io.StringIO()),
    ):
        assert gate.main() == 1


def test_response_gate_rejects_app_parity_drift_for_plain_typed_dto() -> None:
    gate = load_verifier("verify_metadata_response_body_vs_codegen_app")
    metadata = {
        "content": {
            "GetTypedDto": {
                "entity": "TypedDto",
                "body": "",
                "kind": "object",
                "source": "content/operations.yaml",
            }
        }
    }
    app = {
        "content": {
            "GetTypedDto": {
                "entity": "WrongDto",
                "body": "legacy_body",
                "kind": "ack",
            }
        }
    }
    with (
        mock.patch.object(
            gate,
            "collect_projection_index",
            return_value={"TypedDto": ("", "", "")},
        ),
        mock.patch.object(gate, "collect_response_decls", return_value=metadata),
        mock.patch.object(gate, "parse_app_response_contracts", return_value=app),
        redirect_stdout(io.StringIO()),
        redirect_stderr(io.StringIO()),
    ):
        assert gate.main() == 1
