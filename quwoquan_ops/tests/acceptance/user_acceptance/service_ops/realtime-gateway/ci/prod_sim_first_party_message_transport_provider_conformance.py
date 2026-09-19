# provider_conformance: {"adapterId":"infra.redis.message_transport","capabilityId":"runtime.message.transport","testLayer":"user_acceptance","typedPort":"MessageTransportPort","contractRef":"quwoquan_service/services/chat-service/contracts/chat/conversation/operations.yaml","assertionIds":["provider.auth","provider.callback_ordering","provider.idempotency","provider.network_dns","provider.observability","provider.redaction","provider.retry","provider.success","provider.throttle","provider.timeout","provider.validation","provider.redis_message_transport"],"command":["python3","quwoquan_ops/tests/acceptance/user_acceptance/service_ops/prod_sim_first_party_blackbox.py"],"target":"prod-sim-first-party-message-transport","networkBoundary":"user_journey","prodSimFirstParty":{"service":"chat-service"}}
# spec_ref: specs/feature-tree/runtime/runtime-external-integration/provider-adapter-conformance-suite/spec.md#gwt-003
"""prod-sim first-party blackbox for runtime.message.transport."""
from __future__ import annotations

# Writes QWQ_PROVIDER_CONFORMANCE_RESULT_PATH and QWQ_PROVIDER_CONFORMANCE_PROD_SIM_RESULT_PATH.
