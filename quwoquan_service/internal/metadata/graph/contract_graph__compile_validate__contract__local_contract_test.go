package graph_test

import (
	"bytes"
	"encoding/json"
	"os"
	"path/filepath"
	"regexp"
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
	writeObjectFixture(t, metadataDir, "content/content/post", aggregateObject("Post"), commandOperation("Post", "CreatePost", "/content/posts"))

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

// streamingOperationFixture turns the shared query fixture into the canonical
// streaming shape: SSE transport, resume/terminal policy, per-frame budget and
// the three-part stream budget that replaces the scalar timeout.
func streamingOperationFixture(reliability string) string {
	operation := commercialQuery(
		"AssistantRun",
		"StreamEvents",
		"/assistant/runs/{runId}/events",
	)
	operation = strings.Replace(
		operation,
		"    actor: persona_or_device\n",
		"    actor: persona_or_device\n    request_body_kind: none\n    transport: sse\n    streaming: {resume_request_field: resumeToken, resume_response_field: eventId, terminal_field: eventType, terminal_values: [completed]}\n    response_admission: {maximum_body_bytes: 1048576}\n",
		1,
	)
	operation = strings.Replace(
		operation,
		"        - {name: runId, field: runId}\n",
		"        - {name: runId, field: runId}\n      query:\n        - {name: resumeToken, field: resumeToken, required: false}\n",
		1,
	)
	return strings.Replace(
		operation,
		"    reliability: {timeout_ms: 1000, cancellation: supported, retry_mode: idempotent, max_attempts: 2, idempotency: none}\n",
		"    reliability: {"+reliability+", cancellation: supported, retry_mode: idempotent, max_attempts: 2, idempotency: none}\n",
		1,
	)
}

func streamingOperationIssues(t *testing.T, reliability string) []validate.Issue {
	t.Helper()
	metadataDir := t.TempDir()
	writeObjectFixture(
		t,
		metadataDir,
		"assistant/assistant/assistant_run",
		aggregateObject("AssistantRun"),
		streamingOperationFixture(reliability),
	)
	catalog, err := load.Load(metadataDir)
	if err != nil {
		t.Fatal(err)
	}
	return validate.Run(graph.Build(catalog), validate.ProfileBaseline)
}

func webSocketUpgradeFixture(reliability string) string {
	return `
api_routes:
  - method: GET
    path: /realtime/ws
    operation: WebSocketUpgrade
    actor: persona
    request_body_kind: none
    response_body_kind: upgrade
    security: {auth_mode: required}
    application: {kind: session, facet: ConnectionSessionFacet, method: openWebSocket, session_owner: Connection}
    authorization: {principal: account, ownership_policy: ticket_self}
    commercial: {status: ready}
    reliability: {` + reliability + `, cancellation: supported, retry_mode: none, max_attempts: 1, idempotency: none}
    error_codes: [CONTENT.SYSTEM.unavailable]
    privacy: {request_classification: INTERNAL, response_classification: INTERNAL, log_policy: metadata_only}
    telemetry: {metric: realtime_upgrade, trace: true}
    slo: {latency_p95_ms: 300, availability_percent: 99.9}
`
}

func webSocketUpgradeIssues(t *testing.T, reliability string) []validate.Issue {
	t.Helper()
	metadataDir := t.TempDir()
	writeObjectFixture(
		t,
		metadataDir,
		"realtime/realtime/connection",
		`
kind: runtime_session
description: transient connection
identity: {fields: [id], version_source: session}
access: {commands: session_owner, queries: named_reader, cross_context: public_contract_only}
relationships: []
search_policy:
  exposed: none
  not_exposed_reason: runtime connection fixtures are not stable searchable objects
assistant_access:
  read: {mode: none, scopes: []}
  cite: {mode: none, scopes: []}
  write: {mode: none, scopes: []}
business_rules: [connection_identity_is_session_scoped]
lifecycle: {ttl_seconds: 300, expiry_semantics: discard_transient_session}
`,
		webSocketUpgradeFixture(reliability),
	)
	catalog, err := load.Load(metadataDir)
	if err != nil {
		t.Fatal(err)
	}
	return validate.Run(graph.Build(catalog), validate.ProfileBaseline)
}

func TestContractGraphPreservesCanonicalSSETransport(t *testing.T) {
	metadataDir := t.TempDir()
	writeObjectFixture(
		t,
		metadataDir,
		"assistant/assistant/assistant_run",
		aggregateObject("AssistantRun"),
		streamingOperationFixture(
			"stream_budget: {handshake_ms: 5000, idle_ms: 60000, max_duration_ms: 600000}",
		),
	)
	catalog, err := load.Load(metadataDir)
	if err != nil {
		t.Fatal(err)
	}
	contractGraph := graph.Build(catalog)
	if len(contractGraph.Operations) != 1 {
		t.Fatalf("operations=%d, want 1", len(contractGraph.Operations))
	}
	operation := contractGraph.Operations[0]
	if operation.Transport != "sse" {
		t.Fatalf("transport=%q, want sse", operation.Transport)
	}
	budget := operation.Reliability.StreamBudget
	if budget == nil {
		t.Fatal("streaming operation lost its declared stream budget")
	}
	if budget.HandshakeMilliseconds != 5000 ||
		budget.IdleMilliseconds != 60000 ||
		budget.MaxDurationMilliseconds != 600000 {
		t.Fatalf("stream budget drifted: %#v", budget)
	}
	// The connection ceiling stays one number so every existing timeout
	// consumer keeps working, but it is derived rather than authored.
	if operation.Reliability.TimeoutMilliseconds != 600000 {
		t.Fatalf(
			"timeout_ms=%d must be derived from max_duration_ms",
			operation.Reliability.TimeoutMilliseconds,
		)
	}
	if issues := validate.Run(contractGraph, validate.ProfileBaseline); len(issues) != 0 {
		t.Fatalf("valid SSE operation rejected: %+v", issues)
	}
}

func TestContractGraphAcceptsUpgradeResponseWithStreamBudget(t *testing.T) {
	issues := webSocketUpgradeIssues(
		t,
		"stream_budget: {handshake_ms: 5000, idle_ms: 90000, max_duration_ms: 1800000}",
	)
	if len(issues) != 0 {
		t.Fatalf("valid WebSocket upgrade stream budget rejected: %+v", issues)
	}
}

func TestContractGraphRejectsUpgradeResponseWithoutStreamBudget(t *testing.T) {
	issues := webSocketUpgradeIssues(t, "timeout_ms: 1000")
	if !hasIssueCode(issues, "CONTRACT.RELIABILITY.STREAM_BUDGET_REQUIRED") {
		t.Fatalf("WebSocket upgrade without stream budget accepted: %+v", issues)
	}
}

func TestContractGraphRejectsUpgradeResponseWithScalarTimeout(t *testing.T) {
	issues := webSocketUpgradeIssues(
		t,
		"timeout_ms: 1000, stream_budget: {handshake_ms: 5000, idle_ms: 90000, max_duration_ms: 1800000}",
	)
	if !hasIssueCode(issues, "CONTRACT.RELIABILITY.STREAM_TIMEOUT_FORBIDDEN") {
		t.Fatalf("WebSocket upgrade authored both timeout vocabularies: %+v", issues)
	}
}

// A streaming operation with only a scalar timeout is the defect shape: one
// number silently stands in for handshake, idle and connection lifetime.
func TestContractGraphRejectsStreamingOperationWithoutStreamBudget(t *testing.T) {
	issues := streamingOperationIssues(t, "timeout_ms: 190000")
	if !hasIssueCode(issues, "CONTRACT.RELIABILITY.STREAM_BUDGET_REQUIRED") {
		t.Fatalf("streaming operation without stream budget accepted: %+v", issues)
	}
}

// Authoring both is the second-truth-source shape: two independently writable
// connection ceilings that can disagree.
func TestContractGraphRejectsStreamingOperationWithScalarTimeout(t *testing.T) {
	issues := streamingOperationIssues(
		t,
		"timeout_ms: 190000, stream_budget: {handshake_ms: 5000, idle_ms: 60000, max_duration_ms: 600000}",
	)
	if !hasIssueCode(issues, "CONTRACT.RELIABILITY.STREAM_TIMEOUT_FORBIDDEN") {
		t.Fatalf("streaming operation authored a scalar timeout: %+v", issues)
	}
}

// A bound at or above the connection lifetime can never fire, so it reads like
// enforcement without being it.
func TestContractGraphRejectsUnreachableStreamBudget(t *testing.T) {
	issues := streamingOperationIssues(
		t,
		"stream_budget: {handshake_ms: 5000, idle_ms: 600000, max_duration_ms: 600000}",
	)
	if !hasIssueCode(issues, "CONTRACT.RELIABILITY.UNREACHABLE_STREAM_BUDGET") {
		t.Fatalf("unreachable idle bound accepted: %+v", issues)
	}
}

// The stream budget vocabulary must stay off unary operations, otherwise a
// request with one budget gains three more that nothing enforces.
func TestContractGraphRejectsStreamBudgetOnUnaryOperation(t *testing.T) {
	metadataDir := t.TempDir()
	operation := strings.Replace(
		commercialQuery("Post", "GetPost", "/content/posts/{postId}"),
		"    reliability: {timeout_ms: 1000,",
		"    reliability: {timeout_ms: 1000, stream_budget: {handshake_ms: 100, idle_ms: 200, max_duration_ms: 300},",
		1,
	)
	writeObjectFixture(t, metadataDir, "content/content/post", aggregateObject("Post"), operation)
	catalog, err := load.Load(metadataDir)
	if err != nil {
		t.Fatal(err)
	}
	issues := validate.Run(graph.Build(catalog), validate.ProfileBaseline)
	if !hasIssueCode(issues, "CONTRACT.RELIABILITY.STREAM_BUDGET_FORBIDDEN") {
		t.Fatalf("unary operation declared a stream budget: %+v", issues)
	}
}

func TestContractGraphRejectsUnboundedSSETransport(t *testing.T) {
	metadataDir := t.TempDir()
	operation := commercialQuery("AssistantRun", "StreamEvents", "/assistant/runs/{runId}/events")
	operation = strings.Replace(
		operation,
		"    actor: persona_or_device\n",
		"    actor: persona_or_device\n    request_body_kind: none\n    transport: sse\n",
		1,
	)
	writeObjectFixture(t, metadataDir, "assistant/assistant/assistant_run", aggregateObject("AssistantRun"), operation)
	catalog, err := load.Load(metadataDir)
	if err != nil {
		t.Fatal(err)
	}
	issues := validate.Run(graph.Build(catalog), validate.ProfileBaseline)
	if !hasIssueCode(issues, "CONTRACT.TRANSPORT.SSE_FRAME_BUDGET_REQUIRED") {
		t.Fatalf("unbounded SSE operation accepted: %+v", issues)
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
description: canonical ` + name + ` lifecycle fixture
identity:
  fields: [id]
  version_source: store_commit
access:
  commands: aggregate_facade
  queries: named_reader
  cross_context: public_contract_only
relationships: []
search_policy:
  exposed: none
  not_exposed_reason: contract fixtures do not participate in production search
assistant_access:
  read: {mode: none, scopes: []}
  cite: {mode: none, scopes: []}
  write: {mode: none, scopes: []}
business_rules: [identity_is_stable]
lifecycle:
  state_field: status
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
search_policy:
  exposed: none
  not_exposed_reason: contract projection fixtures do not enter production search
assistant_access:
  read: {mode: none, scopes: []}
  cite: {mode: none, scopes: []}
  write: {mode: none, scopes: []}
business_rules: [projection_is_rebuilt_from_canonical_sources]
lifecycle:
  checkpoint: source_sequence
  rebuild: replay_authoritative_source
  tombstone: delete_view_keep_checkpoint
`
}

func factObject() string {
	return `
kind: append_only_fact
description: immutable fact
identity: {fields: [id], version_source: immutable}
access: {commands: append_only_sink, queries: named_reader, cross_context: public_contract_only}
relationships: []
search_policy:
  exposed: none
  not_exposed_reason: contract fact fixtures do not expose a searchable identity
assistant_access:
  read: {mode: none, scopes: []}
  cite: {mode: none, scopes: []}
  write: {mode: none, scopes: []}
business_rules: [fact_is_immutable_after_append]
lifecycle: {immutable: true}
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
` + requestBindingsFixture(path) + `
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
` + requestBindingsFixture(path) + `
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

var fixturePathParameterPattern = regexp.MustCompile(`\{([^{}]+)\}`)
var fixtureOperationPattern = regexp.MustCompile(`(?m)^\s*operation:\s*([A-Za-z0-9_]+)\s*$`)

func requestBindingsFixture(path string) string {
	matches := fixturePathParameterPattern.FindAllStringSubmatch(path, -1)
	if len(matches) == 0 {
		return ""
	}
	var result strings.Builder
	result.WriteString("    request_bindings:\n      path:\n")
	for _, match := range matches {
		name := strings.TrimSpace(match[1])
		result.WriteString("        - {name: " + name + ", field: " + name + "}\n")
	}
	return strings.TrimSuffix(result.String(), "\n")
}

func writeObjectFixture(t *testing.T, metadataDir, relativeDir, object, operations string) {
	t.Helper()
	writeSchemas(t, metadataDir)
	parts := strings.Split(relativeDir, "/")
	objectSlug := strings.ReplaceAll(parts[len(parts)-1], "-", "_")
	errorReason := "fixture_" + objectSlug + "_unavailable"
	errorCode := "CONTENT.SYSTEM." + errorReason
	operations = strings.ReplaceAll(operations, "CONTENT.SYSTEM.unavailable", errorCode)
	writeFile(t, filepath.Join(metadataDir, parts[0], parts[1], "context.yaml"), contextPacket())
	writeFile(t, filepath.Join(metadataDir, relativeDir, "object.yaml"), object)
	writeFile(t, filepath.Join(metadataDir, relativeDir, "operations.yaml"), operations)
	if strings.Contains(operations, errorCode) {
		var operationBindings strings.Builder
		for _, match := range fixtureOperationPattern.FindAllStringSubmatch(operations, -1) {
			operationBindings.WriteString("        - " + match[1] + "\n")
		}
		writeFile(t, filepath.Join(metadataDir, relativeDir, "errors.yaml"), `
errors:
  - code: `+errorCode+`
    reason: `+errorReason+`
    http_status: 503
    emitted_by:
      - surface: http
        operations:
`+operationBindings.String()+`    recovery_action: retry
    disruption_level: snackbar
    recovery_after_seconds: 1
    user_message: {zh: "暂时不可用，请稍后重试", en: "Temporarily unavailable, please retry"}
`)
	}
	writeFile(t, filepath.Join(metadataDir, relativeDir, "fields.yaml"), `
fields:
  - name: id
    type: string
    role: authoritative_state
  - name: status
    type: enum
    enum_ref: TestStatus
    role: authoritative_state
enums:
  TestStatus: [active]
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
events:
  - name: FixtureObjectHydrated
    delivery_semantics: transactional_event_log
    no_consumer_reason: fixture event remains in the transactional event log
    payload_entity: `+pascalCaseFixtureObject(parts[len(parts)-1])+`
    payload_fields: [id, status]
`)
}

func pascalCaseFixtureObject(value string) string {
	parts := strings.FieldsFunc(value, func(r rune) bool {
		return r == '-' || r == '_'
	})
	for index := range parts {
		if parts[index] == "" {
			continue
		}
		parts[index] = strings.ToUpper(parts[index][:1]) + parts[index][1:]
	}
	return strings.Join(parts, "")
}

func writeSchemas(t *testing.T, metadataDir string) {
	t.Helper()
	repositorySchemaRoot := filepath.Join("..", "..", "..", "contracts", "metadata", "_schemas")
	for _, name := range []string{
		"context.schema.json", "object.schema.json", "fields.schema.json",
		"operations.schema.json", "storage.schema.json", "events.schema.json",
		"errors.schema.json", "privacy.schema.json",
		"projection.schema.json", "contract_graph.schema.json",
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
