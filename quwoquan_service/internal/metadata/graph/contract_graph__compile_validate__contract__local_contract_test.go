package graph_test

import (
	"bytes"
	"encoding/json"
	"os"
	"path/filepath"
	"strings"
	"testing"

	contractcodegen "quwoquan_service/internal/metadata/codegen"
	"quwoquan_service/internal/metadata/graph"
	"quwoquan_service/internal/metadata/load"
	contractopenapi "quwoquan_service/internal/metadata/openapi"
	"quwoquan_service/internal/metadata/validate"
)

func TestContractGraphCompileValidateCommercial(t *testing.T) {
	metadataDir := t.TempDir()
	writeObjectFixture(t, metadataDir, "content/post", `
version: 1
domain: content
aggregate_root: Post
object_kind: aggregate_root
description: Post lifecycle
storage_backend: mongodb
members: []
business_rules: [author_owns_post]
lifecycle:
  states: [draft, published]
`, `
version: 1
service:
  name: content-service
  domain: content
  owner: content-team
api_routes:
  - method: GET
    path: /v1/content/posts/{postId}
    operation: GetPost
    actor: persona_or_device
    auth: optional
    application:
      kind: query
      facet: PostQueryFacade
      method: getPost
      reader: PostDetailReader
      slice: PostDetailSlice
    authorization:
      principal: public
      ownership_policy: public_read
    commercial:
      status: ready
    reliability:
      timeout_ms: 1000
      cancellation: supported
      retry_mode: idempotent
      max_attempts: 2
      idempotency: none
    error_codes: [CONTENT.SYSTEM.unavailable]
    privacy:
      request_classification: PUBLIC
      response_classification: PUBLIC
      log_policy: metadata_only
    telemetry:
      metric: content_post_get
      trace: true
    slo:
      latency_p95_ms: 300
      availability_percent: 99.9
  - method: POST
    path: /v1/content/posts/{postId}:publish
    operation: PublishPost
    actor: persona
    auth: required
    application:
      kind: command
      facet: PostCommandFacade
      method: publish
      aggregate_owner: Post
      mutation_target: Post
      invariant_target: Post
    authorization:
      principal: persona
      ownership_policy: owner
    commercial:
      status: ready
    reliability:
      timeout_ms: 2000
      cancellation: supported
      retry_mode: idempotent
      max_attempts: 2
      idempotency: required
    error_codes: [CONTENT.USER.invalid]
    privacy:
      request_classification: PUBLIC
      response_classification: PUBLIC
      log_policy: metadata_only
    telemetry:
      metric: content_post_publish
      trace: true
    slo:
      latency_p95_ms: 500
      availability_percent: 99.9
`)
	writeFile(t, filepath.Join(metadataDir, "content/post/projections/post_detail.yaml"), `
version: 1
read_model: PostDetailSlice
client_projection:
  dart_class: PostDetailSlice
`)
	writeFile(t, filepath.Join(metadataDir, "content/post/fields.yaml"), `
version: 1
aggregate: Post
entities:
  Post:
    fields:
      - name: id
        type: string
`)
	writeFile(t, filepath.Join(metadataDir, "content/business_object_map.yaml"), `
domain: content
decision_refs: [DDD-OBJ-001]
bounded_contexts:
  - name: Content
    context_id: content.content
    role: core
    access_policy:
      commands: aggregate_facade_only
      queries: named_reader_slice_only
      child_objects: aggregate_root_only
      cross_context: public_contract_only
objects:
  - canonical_object: Post
    bounded_context: Content
    object_kind: aggregate_root
    identity:
      fields: [id]
      version_source: store_commit
    invariant_refs: [content/post/aggregate.yaml#business_rules]
    member_bounds: {}
    storage_role: authoritative
    mutation_entrypoints: [PublishPost]
    event_consumers: []
    lifecycle_refs: [content/post/aggregate.yaml#lifecycle]
    storage_backend: mongodb
    source_document: content/post/fields.yaml
    source_entity: Post
    access:
      commands: aggregate_facade
      queries: named_reader
      cross_context: public_contract_only
    relationships: []
    field_roles:
      authoritative_state: [id]
      owned_value: []
      reference: []
      append_only_fact: []
      projection: []
      transport_only: []
`)
	sourceCatalog, err := load.Load(metadataDir)
	if err != nil {
		t.Fatalf("load source metadata: %v", err)
	}
	snapshots, err := contractopenapi.Generate(graph.Build(sourceCatalog))
	if err != nil {
		t.Fatalf("generate OpenAPI fixture: %v", err)
	}
	if err := contractopenapi.WriteDirectory(metadataDir, snapshots); err != nil {
		t.Fatalf("write OpenAPI fixture: %v", err)
	}

	catalog, err := load.Load(metadataDir)
	if err != nil {
		t.Fatalf("load metadata: %v", err)
	}
	contractGraph := graph.Build(catalog)
	encodedGraph, err := json.Marshal(contractGraph)
	if err != nil {
		t.Fatalf("encode ContractGraph: %v", err)
	}
	for _, retired := range []string{"schemaVersion", "registryRevision"} {
		if bytes.Contains(encodedGraph, []byte(`"`+retired+`"`)) {
			t.Fatalf("ContractGraph contains retired field %q", retired)
		}
	}
	if len(contractGraph.Documents) == 0 ||
		len(contractGraph.Documents) >= len(contractGraph.Sources) {
		t.Fatalf(
			"documents=%d sources=%d; schemas must stay provenance-only",
			len(contractGraph.Documents),
			len(contractGraph.Sources),
		)
	}
	for _, document := range contractGraph.Documents {
		if strings.HasPrefix(document.Path, "_schemas/") {
			t.Fatalf("compiler schema leaked into generator document %s", document.Path)
		}
	}
	var aggregateDocument map[string]any
	if err := contractGraph.DecodeDocument(
		"content/post/aggregate.yaml",
		&aggregateDocument,
	); err != nil {
		t.Fatalf("decode aggregate from ContractGraph: %v", err)
	}
	if aggregateDocument["aggregate_root"] != "Post" {
		t.Fatalf("embedded aggregate=%v", aggregateDocument["aggregate_root"])
	}
	issues, err := validate.All(contractGraph, validate.ProfileCommercial, metadataDir)
	if err != nil {
		t.Fatalf("validate metadata schemas: %v", err)
	}
	if len(issues) != 0 {
		t.Fatalf("commercial validation issues: %+v", issues)
	}
	if err := validate.ContractGraphSchema(metadataDir, contractGraph); err != nil {
		t.Fatalf("validate ContractGraph schema: %v", err)
	}

	if got, want := contractGraph.Operations[0].ID, "content.post.GetPost"; got != want {
		t.Fatalf("canonical operation id = %q, want %q", got, want)
	}
	first, err := contractcodegen.MarshalGraph(contractGraph)
	if err != nil {
		t.Fatalf("marshal graph: %v", err)
	}
	second, err := contractcodegen.MarshalGraph(graph.Build(catalog))
	if err != nil {
		t.Fatalf("marshal graph again: %v", err)
	}
	if !bytes.Equal(first, second) {
		t.Fatal("graph JSON is not deterministic")
	}
}

func TestContractGraphRejectsDuplicateTransport(t *testing.T) {
	metadataDir := t.TempDir()
	writeObjectFixture(t, metadataDir, "content/post", commercialAggregate("content", "Post"), commercialQueryService("content", "Post", "GetPost", "/v1/content/shared"))
	writeObjectFixture(t, metadataDir, "content/report", commercialAggregate("content", "Report"), commercialQueryService("content", "Report", "GetReport", "/v1/content/shared"))

	catalog, err := load.Load(metadataDir)
	if err != nil {
		t.Fatalf("load metadata: %v", err)
	}
	issues := validate.Run(graph.Build(catalog), validate.ProfileCommercial)
	if !hasIssueCode(issues, "CONTRACT.DUPLICATE.TRANSPORT") {
		t.Fatalf("expected duplicate transport issue, got %+v", issues)
	}
}

func TestContractGraphRejectsUnknownTopLevelField(t *testing.T) {
	metadataDir := t.TempDir()
	writeObjectFixture(t, metadataDir, "content/post", commercialAggregate("content", "Post")+"\nunsupported_repository: true\n", commercialQueryService("content", "Post", "GetPost", "/v1/content/posts/{postId}"))

	_, err := load.Load(metadataDir)
	if err == nil || !strings.Contains(err.Error(), "unknown top-level fields: unsupported_repository") {
		t.Fatalf("expected unknown-field failure, got %v", err)
	}
}

func TestContractGraphCommercialConsumesVersionedSchema(t *testing.T) {
	metadataDir := t.TempDir()
	writeSchemas(t, metadataDir)
	service := commercialQueryService("content", "Post", "GetPost", "/v1/content/posts/{postId}")
	service = strings.Replace(service, "      slice: PostSlice", "      slice: PostSlice\n      unsupported_dispatch: true", 1)
	writeObjectFixture(t, metadataDir, "content/post", commercialAggregate("content", "Post"), service)

	catalog, err := load.Load(metadataDir)
	if err != nil {
		t.Fatalf("load metadata: %v", err)
	}
	issues, err := validate.All(graph.Build(catalog), validate.ProfileCommercial, metadataDir)
	if err != nil {
		t.Fatalf("validate commercial metadata: %v", err)
	}
	if !hasIssueCode(issues, "CONTRACT.SCHEMA.INVALID") {
		t.Fatalf("expected schema issue for unsupported application field, got %+v", issues)
	}
}

func TestContractGraphRejectsSeparateAggregateAlias(t *testing.T) {
	metadataDir := t.TempDir()
	writeSchemas(t, metadataDir)
	writeFile(t, filepath.Join(metadataDir, "content/report/entity.yaml"), `
version: 1
domain: content
entity: Report
object_kind: separate_aggregate
description: moderation report
storage_backend: postgres
`)

	if _, err := load.Load(metadataDir); err == nil {
		t.Fatal("separate_aggregate alias must be rejected")
	}
}

func TestContractGraphRejectsCrossObjectCommandOwner(t *testing.T) {
	metadataDir := t.TempDir()
	writeSchemas(t, metadataDir)
	writeObjectFixture(t, metadataDir, "content/post", commercialAggregate("content", "Post"), `
version: 1
service:
  name: content-service
  domain: content
  owner: content-team
api_routes:
  - method: POST
    path: /v1/content/posts/{postId}:report
    operation: ReportPost
    actor: persona
    commercial:
      status: ready
    application:
      kind: command
      facet: ReportCommandFacet
      method: create
      aggregate_owner: Report
      mutation_target: Report
      invariant_target: Report
`)
	writeFile(t, filepath.Join(metadataDir, "content/report/entity.yaml"), `
version: 1
domain: content
entity: Report
object_kind: aggregate_root
description: moderation report
storage_backend: postgres
`)

	catalog, err := load.Load(metadataDir)
	if err != nil {
		t.Fatalf("load metadata: %v", err)
	}
	issues := validate.Run(graph.Build(catalog), validate.ProfileCommercial)
	if !hasIssueCode(issues, "CONTRACT.OPERATION.CROSS_OBJECT_COMMAND_OWNER") {
		t.Fatalf("expected cross-object owner issue, got %+v", issues)
	}
}

func TestContractGraphRejectsOwnedEntityStoreAndProjectionCommand(t *testing.T) {
	metadataDir := t.TempDir()
	writeSchemas(t, metadataDir)
	writeObjectFixture(t, metadataDir, "content/post", commercialAggregate("content", "Post"), commercialQueryService("content", "Post", "GetPost", "/v1/content/posts/{postId}"))
	writeFile(t, filepath.Join(metadataDir, "content/post_draft/entity.yaml"), `
version: 1
domain: content
entity: PostDraft
object_kind: owned_entity
aggregate_owner: Post
description: bounded draft state
storage_backend: mongodb
`)
	writeFile(t, filepath.Join(metadataDir, "content/post_search/entity.yaml"), `
version: 1
domain: content
entity: PostSearch
object_kind: projection
description: search projection
`)
	writeFile(t, filepath.Join(metadataDir, "content/post_search/service.yaml"), `
version: 1
service:
  name: content-service
  domain: content
  owner: content-team
api_routes:
  - method: POST
    path: /v1/content/post-search:rebuild
    operation: RebuildPostSearch
    actor: account
    commercial:
      status: ready
    application:
      kind: command
      facet: PostSearchCommandFacet
      method: rebuild
      aggregate_owner: PostSearch
      mutation_target: PostSearch
      invariant_target: PostSearch
`)

	catalog, err := load.Load(metadataDir)
	if err != nil {
		t.Fatalf("load metadata: %v", err)
	}
	issues := validate.Run(graph.Build(catalog), validate.ProfileCommercial)
	for _, code := range []string{
		"CONTRACT.OBJECT.OWNED_ENTITY_HAS_STORE",
		"CONTRACT.OPERATION.INVALID_COMMAND_OWNER_KIND",
		"CONTRACT.OPERATION.PROJECTION_COMMAND_FORBIDDEN",
	} {
		if !hasIssueCode(issues, code) {
			t.Fatalf("expected %s, got %+v", code, issues)
		}
	}
}

func TestContractGraphRejectsFactUpdateOrDelete(t *testing.T) {
	metadataDir := t.TempDir()
	writeSchemas(t, metadataDir)
	writeFile(t, filepath.Join(metadataDir, "behavior/event/entity.yaml"), `
version: 1
domain: behavior
entity: BehaviorEvent
object_kind: append_only_fact
description: immutable behavior fact
storage_backend: mongodb
`)
	writeFile(t, filepath.Join(metadataDir, "behavior/event/service.yaml"), `
version: 1
service:
  name: behavior-service
  domain: behavior
  owner: behavior-team
api_routes:
  - method: DELETE
    path: /v1/behaviors/{eventId}
    operation: DeleteBehavior
    actor: account
    commercial:
      status: ready
    application:
      kind: command
      facet: BehaviorEventSink
      method: delete
      append_sink: BehaviorEvent
      mutation_target: BehaviorEvent
      invariant_target: BehaviorEvent
`)

	catalog, err := load.Load(metadataDir)
	if err != nil {
		t.Fatalf("load metadata: %v", err)
	}
	issues := validate.Run(graph.Build(catalog), validate.ProfileCommercial)
	if !hasIssueCode(issues, "CONTRACT.OPERATION.FACT_MUTATION_FORBIDDEN") {
		t.Fatalf("expected append-only fact mutation issue, got %+v", issues)
	}
}

func TestBusinessObjectMapRequiresExactFieldClassification(t *testing.T) {
	metadataDir := t.TempDir()
	writeSchemas(t, metadataDir)
	writeFile(t, filepath.Join(metadataDir, "content/post/aggregate.yaml"), commercialAggregate("content", "Post"))
	writeFile(t, filepath.Join(metadataDir, "content/post/fields.yaml"), `
version: 1
aggregate: Post
entities:
  Post:
    fields:
      - name: id
        type: string
      - name: status
        type: string
`)
	writeFile(t, filepath.Join(metadataDir, "content/business_object_map.yaml"), `
domain: content
decision_refs: [DDD-OBJ-001]
bounded_contexts:
  - name: Content
    context_id: content.content
    role: core
    access_policy:
      commands: aggregate_facade_only
      queries: named_reader_slice_only
      child_objects: aggregate_root_only
      cross_context: public_contract_only
objects:
  - canonical_object: Post
    bounded_context: Content
    object_kind: aggregate_root
    identity:
      fields: [id]
      version_source: store_commit
    invariant_refs: [content/post/aggregate.yaml#invariants]
    member_bounds: {}
    storage_role: authoritative
    mutation_entrypoints: []
    event_consumers: [content.PostHydrated.v1]
    lifecycle_refs: [content/post/aggregate.yaml#lifecycle]
    storage_backend: mongodb
    source_document: content/post/fields.yaml
    source_entity: Post
    access:
      commands: aggregate_facade
      queries: named_reader
      cross_context: public_contract_only
    relationships: []
    field_roles:
      authoritative_state: [id]
      owned_value: []
      reference: []
      append_only_fact: []
      projection: []
      transport_only: []
`)

	catalog, err := load.Load(metadataDir)
	if err != nil {
		t.Fatalf("load metadata: %v", err)
	}
	issues := validate.Run(graph.Build(catalog), validate.ProfileCommercial)
	if !hasIssueCode(issues, "CONTRACT.OBJECT_MAP.UNCLASSIFIED_FIELD") {
		t.Fatalf("expected unclassified field issue, got %+v", issues)
	}
}

func TestBusinessObjectMapRequiresIdentityLikeFieldSemantics(t *testing.T) {
	metadataDir := t.TempDir()
	writeSchemas(t, metadataDir)
	writeFile(t, filepath.Join(metadataDir, "content/post/aggregate.yaml"), commercialAggregate("content", "Post"))
	writeFile(t, filepath.Join(metadataDir, "content/post/fields.yaml"), `
version: 1
aggregate: Post
entities:
  Post:
    fields:
      - name: id
        type: string
      - name: tenantId
        type: string
      - name: status
        type: string
`)

	objectMapPath := filepath.Join(metadataDir, "content/business_object_map.yaml")
	objectMap := `
domain: content
decision_refs: [DDD-OBJ-001]
bounded_contexts:
  - name: Content
    context_id: content.content
    role: core
    access_policy:
      commands: aggregate_facade_only
      queries: named_reader_slice_only
      child_objects: aggregate_root_only
      cross_context: public_contract_only
objects:
  - canonical_object: Post
    bounded_context: Content
    object_kind: aggregate_root
    identity:
      fields: [id]
      version_source: store_commit
    invariant_refs: [content/post/aggregate.yaml#invariants]
    member_bounds: {}
    storage_role: authoritative
    mutation_entrypoints: []
    event_consumers: [content.PostHydrated.v1]
    lifecycle_refs: [content/post/aggregate.yaml#lifecycle]
    storage_backend: mongodb
    source_document: content/post/fields.yaml
    source_entity: Post
    access:
      commands: aggregate_facade
      queries: named_reader
      cross_context: public_contract_only
    relationships: []
    field_roles:
      authoritative_state: [id, tenantId, status]
      owned_value: []
      reference: []
      append_only_fact: []
      projection: []
      transport_only: []
`
	writeFile(t, objectMapPath, objectMap)

	catalog, err := load.Load(metadataDir)
	if err != nil {
		t.Fatalf("load metadata: %v", err)
	}
	issues := validate.Run(graph.Build(catalog), validate.ProfileCommercial)
	if !hasIssueCode(issues, "CONTRACT.OBJECT_REGISTRY.UNCLASSIFIED_ID_FIELD") {
		t.Fatalf("expected unclassified identity-like field issue, got %+v", issues)
	}

	objectMap = strings.Replace(
		objectMap,
		"    relationships: []\n",
		"    relationships: []\n    local_identity_reasons:\n      tenantId: tenant is a local partition key, not a domain object reference\n",
		1,
	)
	writeFile(t, objectMapPath, objectMap)
	catalog, err = load.Load(metadataDir)
	if err != nil {
		t.Fatalf("reload metadata: %v", err)
	}
	issues = validate.Run(graph.Build(catalog), validate.ProfileCommercial)
	if hasIssueCode(issues, "CONTRACT.OBJECT_REGISTRY.UNCLASSIFIED_ID_FIELD") {
		t.Fatalf("declared local identity reason must classify tenantId, got %+v", issues)
	}
}

func commercialAggregate(domain, name string) string {
	return `
version: 1
domain: ` + domain + `
aggregate_root: ` + name + `
object_kind: aggregate_root
description: test aggregate
storage_backend: mongodb
members: []
`
}

func commercialQueryService(domain, object, operation, path string) string {
	return `
version: 1
service:
  name: ` + domain + `-service
  domain: ` + domain + `
  owner: test-team
api_routes:
  - method: GET
    path: ` + path + `
    operation: ` + operation + `
    actor: persona_or_device
    auth: public
    application:
      kind: query
      facet: ` + object + `QueryFacade
      method: get
      reader: ` + object + `Reader
      slice: ` + object + `Slice
    authorization:
      principal: public
      ownership_policy: public_read
    commercial:
      status: ready
    reliability:
      timeout_ms: 1000
      cancellation: supported
      retry_mode: idempotent
      max_attempts: 2
      idempotency: none
    error_codes: [CONTENT.SYSTEM.unavailable]
    privacy:
      request_classification: PUBLIC
      response_classification: PUBLIC
      log_policy: metadata_only
    telemetry:
      metric: contract_query
      trace: true
    slo:
      latency_p95_ms: 300
      availability_percent: 99.9
`
}

func writeObjectFixture(t *testing.T, metadataDir, relativeDir, aggregate, service string) {
	t.Helper()
	writeSchemas(t, metadataDir)
	writeFile(t, filepath.Join(metadataDir, relativeDir, "aggregate.yaml"), aggregate)
	writeFile(t, filepath.Join(metadataDir, relativeDir, "service.yaml"), service)
}

func writeSchemas(t *testing.T, metadataDir string) {
	t.Helper()
	repositorySchemaRoot := filepath.Join("..", "..", "..", "contracts", "metadata", "_schemas")
	for _, name := range []string{
		"aggregate.schema.json",
		"business_object_map.schema.json",
		"entity.schema.json",
		"readiness.schema.json",
		"service.schema.json",
		"contract_graph.schema.json",
	} {
		source := filepath.Join(repositorySchemaRoot, name)
		data, err := os.ReadFile(source)
		if err != nil {
			t.Fatalf("read schema %s: %v", source, err)
		}
		writeFile(t, filepath.Join(metadataDir, "_schemas", name), string(data))
	}
}

func writeFile(t *testing.T, path, content string) {
	t.Helper()
	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		t.Fatalf("create fixture dir: %v", err)
	}
	if err := os.WriteFile(path, []byte(strings.TrimSpace(content)+"\n"), 0o644); err != nil {
		t.Fatalf("write fixture: %v", err)
	}
}

func hasIssueCode(issues []validate.Issue, code string) bool {
	for _, current := range issues {
		if current.Code == code {
			return true
		}
	}
	return false
}
