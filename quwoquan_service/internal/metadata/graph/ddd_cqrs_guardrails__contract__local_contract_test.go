package graph_test

import (
	"path/filepath"
	"strings"
	"testing"

	"quwoquan_service/internal/metadata/ast"
	"quwoquan_service/internal/metadata/graph"
	"quwoquan_service/internal/metadata/load"
	"quwoquan_service/internal/metadata/validate"
)

func TestAggregateRejectsNestedAggregateRoot(t *testing.T) {
	contractGraph := &graph.ContractGraph{Objects: []ast.Object{{
		ID: "assistant.assistant_run", Domain: "assistant", Name: "AssistantRun",
		Kind: ast.ObjectKindAggregateRoot, KindExplicit: true,
		SourcePath: "assistant/assistant/assistant_run/object.yaml",
		Members:    []ast.Member{{Name: "AssistantConversation", Kind: ast.ObjectKindAggregateRoot, Cardinality: "1:1"}},
	}}}
	if issues := validate.Run(contractGraph, validate.ProfileCommercial); !hasIssueCode(issues, "CONTRACT.MEMBER.INVALID_KIND") {
		t.Fatalf("nested aggregate root accepted: %+v", issues)
	}
}

func TestObjectPacketRejectsCrossObjectCommandOwner(t *testing.T) {
	metadataDir := t.TempDir()
	operation := commandOperation("Report", "ReportPost", "/content/posts/{postId}:report")
	writeObjectFixture(t, metadataDir, "content/content/post", aggregateObject("Post"), operation)
	writeObjectFixture(t, metadataDir, "content/trust_safety/report", aggregateObject("Report"), "api_routes: []")
	catalog, err := load.Load(metadataDir)
	if err != nil {
		t.Fatal(err)
	}
	issues := validate.Run(graph.Build(catalog), validate.ProfileCommercial)
	if !hasIssueCode(issues, "CONTRACT.OPERATION.CROSS_OBJECT_COMMAND_OWNER") {
		t.Fatalf("cross-object owner accepted: %+v", issues)
	}
}

func TestQueryBindingRejectsWeakReaderAndSliceNames(t *testing.T) {
	metadataDir := t.TempDir()
	operation := commercialQuery("Post", "GetPost", "/content/posts/{postId}")
	operation = strings.Replace(operation, "reader: PostReader", "reader: map", 1)
	operation = strings.Replace(operation, "slice: PostSlice", "slice: Map", 1)
	writeObjectFixture(t, metadataDir, "content/content/post", aggregateObject("Post"), operation)
	catalog, err := load.Load(metadataDir)
	if err != nil {
		t.Fatal(err)
	}
	issues := validate.Run(graph.Build(catalog), validate.ProfileCommercial)
	for _, code := range []string{"CONTRACT.OPERATION.INVALID_QUERY_READER", "CONTRACT.OPERATION.INVALID_QUERY_SLICE"} {
		if !hasIssueCode(issues, code) {
			t.Fatalf("expected %s, got %+v", code, issues)
		}
	}
}

func TestRuntimeSessionOwnsSessionOperation(t *testing.T) {
	metadataDir := t.TempDir()
	writeSchemas(t, metadataDir)
	writeFile(t, filepath.Join(metadataDir, "realtime/realtime/context.yaml"), contextPacket())
	writeFile(t, filepath.Join(metadataDir, "realtime/realtime/connection/object.yaml"), `
kind: runtime_session
description: transient connection
identity: {fields: [id], version_source: session}
access: {commands: session_owner, queries: named_reader, cross_context: public_contract_only}
relationships: []
`)
	writeFile(t, filepath.Join(metadataDir, "realtime/realtime/connection/operations.yaml"), `
api_routes:
  - method: GET
    path: /realtime/ws
    operation: WebSocketUpgrade
    actor: account
    security: {auth_mode: required}
    application: {kind: session, facet: ConnectionSessionFacet, method: openWebSocket, session_owner: Connection}
    authorization: {principal: account, ownership_policy: owner}
    commercial: {status: ready}
    reliability: {timeout_ms: 1000, cancellation: supported, retry_mode: none, max_attempts: 1, idempotency: none}
    error_codes: [REALTIME.SYSTEM.unavailable]
    privacy: {request_classification: INTERNAL, response_classification: INTERNAL, log_policy: metadata_only}
    telemetry: {metric: realtime_upgrade, trace: true}
    slo: {latency_p95_ms: 300, availability_percent: 99.9}
`)
	catalog, err := load.Load(metadataDir)
	if err != nil {
		t.Fatal(err)
	}
	issues := validate.Run(graph.Build(catalog), validate.ProfileCommercial)
	for _, code := range []string{"CONTRACT.OPERATION.MISSING_SESSION_OWNER", "CONTRACT.OPERATION.INVALID_SESSION_OWNER_KIND", "CONTRACT.OPERATION.CROSS_OBJECT_SESSION_OWNER"} {
		if hasIssueCode(issues, code) {
			t.Fatalf("valid runtime session emitted %s: %+v", code, issues)
		}
	}
}

func TestAggregateCannotOwnSessionOperation(t *testing.T) {
	metadataDir := t.TempDir()
	operation := strings.Replace(
		commercialQuery("Connection", "WebSocketUpgrade", "/realtime/ws"),
		"kind: query\n      facet: ConnectionQueryFacade\n      method: get\n      reader: ConnectionReader\n      slice: ConnectionSlice",
		"kind: session\n      facet: ConnectionSessionFacet\n      method: openWebSocket\n      session_owner: Connection",
		1,
	)
	writeObjectFixture(t, metadataDir, "realtime/realtime/connection", aggregateObject("Connection"), operation)
	catalog, err := load.Load(metadataDir)
	if err != nil {
		t.Fatal(err)
	}
	issues := validate.Run(graph.Build(catalog), validate.ProfileCommercial)
	if !hasIssueCode(issues, "CONTRACT.OPERATION.INVALID_SESSION_OWNER_KIND") {
		t.Fatalf("aggregate accepted as runtime session: %+v", issues)
	}
}
