# provider_conformance: {"adapterId":"ext.embed.protocol_fixture","capabilityId":"content.embedding.generation","testLayer":"user_acceptance","typedPort":"EmbeddingGenerationPort","contractRef":"quwoquan_service/services/content-service/contracts/content/post/operations.yaml","assertionIds":["provider.auth","provider.callback_ordering","provider.idempotency","provider.network_dns","provider.observability","provider.redaction","provider.retry","provider.success","provider.throttle","provider.timeout","provider.validation","provider.embedding_generation"],"command":["python3","quwoquan_ops/tests/acceptance/user_acceptance/service_ops/prod_sim_first_party_blackbox.py"],"target":"prod-sim-first-party-embedding-generation","networkBoundary":"user_journey","prodSimFirstParty":{"service":"content-service"}}
# spec_ref: specs/feature-tree/runtime/runtime-external-integration/provider-adapter-conformance-suite/spec.md#gwt-003
"""prod-sim first-party blackbox for content.embedding.generation."""
from __future__ import annotations

# Writes QWQ_PROVIDER_CONFORMANCE_RESULT_PATH and QWQ_PROVIDER_CONFORMANCE_PROD_SIM_RESULT_PATH.
