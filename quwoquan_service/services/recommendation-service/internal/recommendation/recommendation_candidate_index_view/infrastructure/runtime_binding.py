"""生产组合消费canonical部署注入，并从实际Mongo索引验证schema身份。"""
import os
from generated.recommendation.ranked_recommendation_window.models.request_response import ReleaseQueryPreparationBinding
from ..application.release_candidate import digest, valid_digest, ReleaseNotReady, canonical


class RuntimeReleaseBinding:
    def __init__(self, database, *, environment, binding_digest, namespace, schema_generation):
        if environment not in {"alpha", "beta", "gamma", "prod"} or not valid_digest(binding_digest) or not valid_digest(schema_generation) or not namespace or database.name != namespace:
            raise ReleaseNotReady("canonical recommendation binding missing or namespace mismatch")
        self.database = database
        self.environment = environment
        self.binding_digest = binding_digest
        self.schema_generation = schema_generation
        self.verify_schema()

    def verify_schema(self):
        rows = []
        for collection in ("recommendation_release_source_checkpoints", "rm_release_discovery_candidates", "rm_release_premium_candidates"):
            for index in self.database[collection].list_indexes():
                if index["name"].startswith("uq_rec_release_"):
                    rows.append({"collection": collection, "name": index["name"], "keys": dict(index["key"]), "unique": bool(index.get("unique", False))})
        if len(rows) != 3 or digest(sorted(rows, key=lambda r: r["name"])) != self.schema_generation:
            raise ReleaseNotReady("recommendation actual index schema generation drift")

    def __call__(self, release):
        self.verify_schema()
        if release.environment != self.environment or release.sourceOwner != "qwq_data":
            raise ReleaseNotReady("release differs from deployed environment")
        return ReleaseQueryPreparationBinding(release=canonical(release), slice="recommendation", providerBindingGeneration=self.binding_digest, schemaGeneration=self.schema_generation)


def compose_release_binding(database, runtime_config, *, environment, environ=None):
    environ = os.environ if environ is None else environ
    section = runtime_config.get("release_candidate", {})
    values = {}
    for field in ("binding_digest", "mongodb_namespace", "schema_generation"):
        key = "RECOMMENDATION_RELEASE_CANDIDATE_" + field.upper()
        injected, configured = environ.get(key, ""), section.get(field, "")
        if injected and configured and injected != configured:
            raise ReleaseNotReady("deployment binding and runtime config conflict")
        value = injected or configured
        if not isinstance(value, str) or not value.strip():
            raise ReleaseNotReady("missing canonical recommendation binding field " + field)
        values[field] = value
    return RuntimeReleaseBinding(database, environment=environment, binding_digest=values["binding_digest"], namespace=values["mongodb_namespace"], schema_generation=values["schema_generation"])
