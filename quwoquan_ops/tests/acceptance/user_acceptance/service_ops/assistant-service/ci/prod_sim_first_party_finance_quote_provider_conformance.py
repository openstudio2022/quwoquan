# provider_conformance: {"adapterId":"ext.finance.protocol_fixture","capabilityId":"assistant.finance.quote","testLayer":"user_acceptance","typedPort":"FinanceQuotePort","contractRef":"quwoquan_service/services/assistant-service/contracts/assistant/assistant_session/operations.yaml","assertionIds":["provider.auth","provider.callback_ordering","provider.idempotency","provider.network_dns","provider.observability","provider.redaction","provider.retry","provider.success","provider.throttle","provider.timeout","provider.validation","provider.finance_quote"],"command":["python3","quwoquan_ops/tests/acceptance/user_acceptance/service_ops/prod_sim_first_party_blackbox.py"],"target":"prod-sim-first-party-finance-quote","networkBoundary":"user_journey","prodSimFirstParty":{"service":"assistant-service"}}
# spec_ref: specs/feature-tree/runtime/runtime-external-integration/provider-adapter-conformance-suite/spec.md#gwt-003
"""prod-sim first-party blackbox for assistant.finance.quote."""
from __future__ import annotations

# Writes QWQ_PROVIDER_CONFORMANCE_RESULT_PATH and QWQ_PROVIDER_CONFORMANCE_PROD_SIM_RESULT_PATH.
