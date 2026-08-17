from __future__ import annotations

from quwoquan_app.test.local_contract.runtime.verify_metadata_app_contract_gates__local_contract_test import (
    load_verifier,
)


def test_routes_gate_reads_every_generated_domain_and_graphql_routes() -> None:
    gate = load_verifier("verify_metadata_routes_vs_codegen_app")
    routes = gate.collect_yaml_routes_by_domain()
    app_routes = gate.parse_app_operation_routes(gate.OPERATION_CONTRACTS)
    generated_domains = {
        domain for domain, operations in app_routes.items() if operations
    }

    assert generated_domains
    assert generated_domains.issubset(routes)
    assert routes["gateway"]["ExecutePersistedGraphQLQuery"] == "/graphql"
    assert routes["gateway"]["SearchPage"] == "/graphql"
