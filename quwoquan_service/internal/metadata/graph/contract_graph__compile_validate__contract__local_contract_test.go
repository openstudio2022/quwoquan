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

func TestContractGraphCompilesObjectFirstPacket(t *testing.T) {
	metadataDir := t.TempDir()
	writeObjectFixture(t, metadataDir, "content/content/post", aggregateObject("Post"), commercialQuery("Post", "GetPost", "/content/posts/{postId}"))

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
		t.Fatalf("reload metadata: %v", err)
	}
	contractGraph := graph.Build(catalog)
	if len(contractGraph.Objects) != 1 || contractGraph.Objects[0].ID != "content.post" {
		t.Fatalf("objects=%+v", contractGraph.Objects)
	}
	if contractGraph.Objects[0].Kind != "aggregate_root" {
		t.Fatalf("kind=%q", contractGraph.Objects[0].Kind)
	}
	if len(contractGraph.BusinessObjectMaps) != 1 || len(contractGraph.BusinessObjectMaps[0].Objects) != 1 {
		t.Fatalf("derived object index=%+v", contractGraph.BusinessObjectMaps)
	}
	for _, document := range contractGraph.Documents {
		if strings.HasPrefix(document.Path, "_schemas/") {
			t.Fatalf("schema leaked into generator document: %s", document.Path)
		}
	}

	issues, err := validate.All(contractGraph, validate.ProfileCommercial, metadataDir)
	if err != nil {
		t.Fatalf("validate metadata: %v", err)
	}
	if len(issues) != 0 {
		t.Fatalf("commercial validation issues: %+v", issues)
	}
	if err := validate.ContractGraphSchema(metadataDir, contractGraph); err != nil {
		t.Fatalf("validate ContractGraph schema: %v", err)
	}

	encoded, err := json.Marshal(contractGraph)
	if err != nil {
		t.Fatal(err)
	}
	for _, retired := range []string{"schemaVersion", "registryRevision"} {
		if bytes.Contains(encoded, []byte(`"`+retired+`"`)) {
			t.Fatalf("ContractGraph contains retired field %q", retired)
		}
	}
	first, err := contractcodegen.MarshalGraph(contractGraph)
	if err != nil {
		t.Fatal(err)
	}
	second, err := contractcodegen.MarshalGraph(graph.Build(catalog))
	if err != nil {
		t.Fatal(err)
	}
	if !bytes.Equal(first, second) {
		t.Fatal("graph JSON is not deterministic")
	}
}

func TestContractGraphRejectsDuplicateTransport(t *testing.T) {
	metadataDir := t.TempDir()
	writeObjectFixture(t, metadataDir, "content/content/post", aggregateObject("Post"), commercialQuery("Post", "GetPost", "/content/shared"))
	writeObjectFixture(t, metadataDir, "content/trust_safety/report", aggregateObject("Report"), commercialQuery("Report", "GetReport", "/content/shared"))
	catalog, err := load.Load(metadataDir)
	if err != nil {
		t.Fatal(err)
	}
	if issues := validate.Run(graph.Build(catalog), validate.ProfileCommercial); !hasIssueCode(issues, "CONTRACT.DUPLICATE.TRANSPORT") {
		t.Fatalf("expected duplicate transport, got %+v", issues)
	}
}

func TestObjectFirstLoaderRejectsRepeatedPathIdentity(t *testing.T) {
	metadataDir := t.TempDir()
	object := aggregateObject("Post") + "\ndomain: content\n"
	writeObjectFixture(t, metadataDir, "content/content/post", object, commercialQuery("Post", "GetPost", "/content/posts/{postId}"))
	_, err := load.Load(metadataDir)
	if err == nil || !strings.Contains(err.Error(), "unknown top-level fields: domain") {
		t.Fatalf("expected repeated identity rejection, got %v", err)
	}
}

func TestObjectFirstLoaderRejectsRetiredKindAlias(t *testing.T) {
	metadataDir := t.TempDir()
	writeSchemas(t, metadataDir)
	writeFile(t, filepath.Join(metadataDir, "content/content/context.yaml"), contextPacket())
	writeFile(t, filepath.Join(metadataDir, "content/content/post/object.yaml"), `
kind: separate_aggregate
description: retired alias
identity: {fields: [id], version_source: store_commit}
access: {commands: aggregate_facade, queries: named_reader, cross_context: public_contract_only}
relationships: []
`)
	if _, err := load.Load(metadataDir); err == nil {
		t.Fatal("separate_aggregate alias must be rejected")
	}
}

func TestProjectionCommandIsRejected(t *testing.T) {
	metadataDir := t.TempDir()
	writeObjectFixture(t, metadataDir, "content/content/post_search", projectionObject(), commandOperation("PostSearch", "RebuildPostSearch", "/internal/content/post-search:rebuild"))
	catalog, err := load.Load(metadataDir)
	if err != nil {
		t.Fatal(err)
	}
	issues := validate.Run(graph.Build(catalog), validate.ProfileCommercial)
	if !hasIssueCode(issues, "CONTRACT.OPERATION.PROJECTION_COMMAND_FORBIDDEN") {
		t.Fatalf("projection command accepted: %+v", issues)
	}
}

func TestAppendOnlyFactDeleteIsRejected(t *testing.T) {
	metadataDir := t.TempDir()
	operation := strings.Replace(commandOperation("BehaviorEvent", "DeleteBehavior", "/behaviors/{eventId}"), "method: POST", "method: DELETE", 1)
	operation = strings.Replace(operation, "aggregate_owner: BehaviorEvent", "append_sink: BehaviorEvent", 1)
	writeObjectFixture(t, metadataDir, "behavior/behavior/behavior_event", factObject(), operation)
	catalog, err := load.Load(metadataDir)
	if err != nil {
		t.Fatal(err)
	}
	issues := validate.Run(graph.Build(catalog), validate.ProfileCommercial)
	if !hasIssueCode(issues, "CONTRACT.OPERATION.FACT_MUTATION_FORBIDDEN") {
		t.Fatalf("fact delete accepted: %+v", issues)
	}
}

func aggregateObject(name string) string {
	return `
kind: aggregate_root
description: ` + name + ` lifecycle
identity:
  fields: [id]
  version_source: store_commit
access:
  commands: aggregate_facade
  queries: named_reader
  cross_context: public_contract_only
relationships: []
business_rules: [identity_is_stable]
lifecycle:
  states: [active]
`
}

func projectionObject() string {
	return `
kind: projection
description: read model
identity: {fields: [id], version_source: checkpoint}
access: {commands: none, queries: named_reader, cross_context: public_contract_only}
relationships: []
`
}

func factObject() string {
	return `
kind: append_only_fact
description: immutable fact
identity: {fields: [id], version_source: immutable}
access: {commands: append_only_sink, queries: named_reader, cross_context: public_contract_only}
relationships: []
`
}

func contextPacket() string {
	return `
role: core
access:
  commands: aggregate_facade_only
  queries: named_reader_slice_only
  child_objects: aggregate_root_only
  cross_context: public_contract_only
`
}

func commercialQuery(object, operation, path string) string {
	return `
api_routes:
  - method: GET
    path: ` + path + `
    operation: ` + operation + `
    actor: persona_or_device
    security: {auth_mode: public}
    application:
      kind: query
      facet: ` + object + `QueryFacade
      method: get
      reader: ` + object + `Reader
      slice: ` + object + `Slice
    authorization: {principal: public, ownership_policy: public_read}
    commercial: {status: ready}
    reliability: {timeout_ms: 1000, cancellation: supported, retry_mode: idempotent, max_attempts: 2, idempotency: none}
    error_codes: [CONTENT.SYSTEM.unavailable]
    privacy: {request_classification: PUBLIC, response_classification: PUBLIC, log_policy: metadata_only}
    telemetry: {metric: contract_query, trace: true}
    slo: {latency_p95_ms: 300, availability_percent: 99.9}
`
}

func commandOperation(object, operation, path string) string {
	return `
api_routes:
  - method: POST
    path: ` + path + `
    operation: ` + operation + `
    actor: account
    security: {auth_mode: required}
    application:
      kind: command
      facet: ` + object + `CommandFacade
      method: execute
      aggregate_owner: ` + object + `
      mutation_target: ` + object + `
      invariant_target: ` + object + `
    authorization: {principal: account, ownership_policy: owner}
    commercial: {status: ready}
    reliability: {timeout_ms: 1000, cancellation: supported, retry_mode: idempotent, max_attempts: 2, idempotency: required}
    error_codes: [CONTENT.SYSTEM.unavailable]
    privacy: {request_classification: INTERNAL, response_classification: INTERNAL, log_policy: metadata_only}
    telemetry: {metric: contract_command, trace: true}
    slo: {latency_p95_ms: 300, availability_percent: 99.9}
`
}

func writeObjectFixture(t *testing.T, metadataDir, relativeDir, object, operations string) {
	t.Helper()
	writeSchemas(t, metadataDir)
	parts := strings.Split(relativeDir, "/")
	writeFile(t, filepath.Join(metadataDir, parts[0], parts[1], "context.yaml"), contextPacket())
	writeFile(t, filepath.Join(metadataDir, relativeDir, "object.yaml"), object)
	writeFile(t, filepath.Join(metadataDir, relativeDir, "operations.yaml"), operations)
	writeFile(t, filepath.Join(metadataDir, relativeDir, "fields.yaml"), `
fields:
  - name: id
    type: string
    role: authoritative_state
`)
	role := "authoritative"
	backend := "mongodb"
	if strings.Contains(object, "kind: projection") {
		role = "projection"
	}
	if strings.Contains(object, "kind: append_only_fact") {
		role = "append_only"
	}
	writeFile(t, filepath.Join(metadataDir, relativeDir, "storage.yaml"), "backend: "+backend+"\nrole: "+role)
	writeFile(t, filepath.Join(metadataDir, relativeDir, "events.yaml"), `
events: []
subscriptions: [test.ObjectHydrated]
`)
}

func writeSchemas(t *testing.T, metadataDir string) {
	t.Helper()
	repositorySchemaRoot := filepath.Join("..", "..", "..", "contracts", "metadata", "_schemas")
	for _, name := range []string{
		"context.schema.json", "object.schema.json", "fields.schema.json",
		"operations.schema.json", "storage.schema.json", "events.schema.json",
		"contract_graph.schema.json",
	} {
		data, err := os.ReadFile(filepath.Join(repositorySchemaRoot, name))
		if err != nil {
			t.Fatalf("read schema %s: %v", name, err)
		}
		writeFile(t, filepath.Join(metadataDir, "_schemas", name), string(data))
	}
}

func writeFile(t *testing.T, path, content string) {
	t.Helper()
	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(path, []byte(strings.TrimSpace(content)+"\n"), 0o644); err != nil {
		t.Fatal(err)
	}
}

func hasIssueCode(issues []validate.Issue, code string) bool {
	for _, issue := range issues {
		if issue.Code == code {
			return true
		}
	}
	return false
}
