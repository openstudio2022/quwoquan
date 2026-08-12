// spec_ref: specs/feature-tree/discovery-content/content-service-cloud-production/remote-content-delivery/spec.md#gwt-001
package main

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"github.com/vektah/gqlparser/v2/ast"
	"github.com/vektah/gqlparser/v2/parser"
	contractcodegen "quwoquan_service/internal/metadata/codegen"
	contractgraph "quwoquan_service/internal/metadata/graph"
)

func TestGenerateBindsPersistedDocumentCostAndCompleteOwnerSlice(t *testing.T) {
	t.Parallel()
	root := t.TempDir()
	schemaPath, schemaDigest := writeDetailSchemaFixture(t, root)
	document := "query ContentPostDetail($postId: ID!) {\n  contentPostDetail(postId: $postId) {\n    postId\n    contentType\n    status\n    visibility\n    likeCount\n    commentCount\n    shareCount\n    viewCount\n    createdAt\n    updatedAt\n  }\n}\n"
	documentHash := sha256.Sum256([]byte(document))
	queryHash := hex.EncodeToString(documentHash[:])
	costPlan := registryCostPlan{BaseComplexity: 11, ListMultipliers: []registryListMultiplier{}, MaxOwnerCalls: 1, MaxBatchKeys: 1, MaxResponseBytes: 65536}
	costPlanDigest := digestCostPlan(t, costPlan)
	appBundle := singleBundleBindingFixture()
	appBundle.SelectedFields = []string{"commentCount", "contentType", "createdAt", "likeCount", "postId", "shareCount", "status", "updatedAt", "viewCount", "visibility"}
	registryPath := writeJSON(t, root, "registry.json", map[string]any{
		"candidateDigest": canonicalDigest('1'),
		"schemaDigest":    schemaDigest,
		"entries": []any{map[string]any{
			"sha256Hash": queryHash, "operationName": "ContentPostDetail",
			"operationType": "query", "canonicalOperationId": "content.post.GetPost",
			"objectIds":        []string{"content.post"},
			"authorization":    map[string]any{"principal": "public", "scopes": []string{}, "ownershipPolicy": "visibility_filtered"},
			"costModelVersion": "graphql-cost-v1", "costPlanDigest": costPlanDigest,
			"cost":                map[string]any{"depth": 2, "topLevelFields": 1, "complexity": 11, "variablesMaxBytes": 1024, "pageSizeMax": 1, "maxOwnerCalls": 1, "maxBatchKeys": 1, "maxResponseBytes": 65536, "sloRef": "slo:gateway.graphql_read.detail"},
			"costPlan":            costPlan,
			"paginationVariables": []any{}, "executorKey": "content.post.getPost",
			"appClientBundle": appBundle,
		}},
	})
	metadataPath := writeJSON(t, root, "query_metadata.json", map[string]any{
		"schema": "graphql-read-query-metadata",
		"entries": []any{map[string]any{
			"document": "content_post_detail.graphql", "canonicalOperationId": "content.post.GetPost",
			"queryClass": "detail", "variablesMaxBytes": 1024, "maxOwnerCalls": 1,
			"maxBatchKeys": 1, "maxResponseBytes": 65536, "sloRef": "slo:gateway.graphql_read.detail",
			"executorKey": "content.post.getPost",
		}},
	})
	if err := os.WriteFile(filepath.Join(root, "content_post_detail.graphql"), []byte(document), 0o644); err != nil {
		t.Fatal(err)
	}
	graphPath := writeJSON(t, root, "contract_graph.json", graphFixture())
	lockPath := writeJSON(t, root, "app_lock.json", lockFixture(t, graphPath))

	generated, manifest, err := generateFixture(t, Options{
		RegistryPath: registryPath, MetadataPath: metadataPath,
		SchemaPath: schemaPath, ContractGraphPath: graphPath, AppLockPath: lockPath,
	})
	if err != nil {
		t.Fatalf("Generate: %v", err)
	}
	payload := string(generated)
	for _, want := range []string{
		"class GeneratedPersistedGraphQLClient",
		"Future<ContentPostDetailSlice> contentPostDetail(",
		"operationName: 'ContentPostDetail'",
		"sha256Hash: '" + queryHash + "'",
		"schemaDigest: '" + schemaDigest + "'",
		"costPlanDigest: '" + costPlanDigest + "'",
		"pathTemplate: '/graphql'",
		"'extensions': <String, Object?>{",
		"'persistedQuery': <String, Object?>{",
		"'version': 1",
		"'sha256Hash': descriptor.sha256Hash",
		"decodeContentPostDetailSlice",
	} {
		if !strings.Contains(payload, want) {
			t.Fatalf("generated Dart missing %q\n%s", want, payload)
		}
	}
	if strings.Contains(payload, "query ContentPostDetail") || strings.Contains(payload, "'query':") {
		t.Fatal("generated App client must not embed or send query text")
	}
	var decodedManifest generatedManifest
	if err := json.Unmarshal(manifest, &decodedManifest); err != nil {
		t.Fatal(err)
	}
	if decodedManifest.RegistrySHA256 == "" || decodedManifest.ContractGraphSHA256 == "" || len(decodedManifest.Outputs) != 1 {
		t.Fatalf("manifest=%+v", decodedManifest)
	}
	if got, want := decodedManifest.Outputs[0].Path, "lib/runtime/transport/graphql_read/generated/persisted_graphql_queries.g.dart"; got != want {
		t.Fatalf("generated App client path=%q want independent generator root %q", got, want)
	}
}

func TestGenerateRendersCanonicalFiveSliceBundleFromSignedRegistry(t *testing.T) {
	t.Parallel()
	workingDirectory, err := os.Getwd()
	if err != nil {
		t.Fatal(err)
	}
	serviceRoot := filepath.Clean(filepath.Join(workingDirectory, "..", ".."))
	registryPath := filepath.Join(serviceRoot, "services/api-edge/resources/policies/graphql_read/persisted_query_registry.example.json")
	metadataPath := filepath.Join(serviceRoot, "services/api-edge/resources/policies/graphql_read/query_metadata.json")
	schemaPath := filepath.Join(serviceRoot, "services/api-edge/resources/policies/graphql_read/schema.graphqls")
	graphBytes, err := os.ReadFile(filepath.Join(serviceRoot, "generated/contract_graph.json"))
	if err != nil {
		t.Fatal(err)
	}
	var graph contractGraphDocument
	if err := json.Unmarshal(graphBytes, &graph); err != nil {
		t.Fatal(err)
	}
	for index := range graph.Operations {
		if graph.Operations[index].ID == gatewayOperationID {
			graph.Operations[index].ResponseAdmission.MaximumBodyBytes = 300000
		}
	}
	base, err := exactGraphOperation(graph.Operations, detailOperationID)
	if err != nil {
		t.Fatal(err)
	}
	registryBytes, err := os.ReadFile(registryPath)
	if err != nil {
		t.Fatal(err)
	}
	var registry registryDocument
	if err := json.Unmarshal(registryBytes, &registry); err != nil {
		t.Fatal(err)
	}
	var bundleEntries []registryEntry
	for _, entry := range registry.Entries {
		if entry.AppClientBundle != nil && entry.AppClientBundle.BundleID == detailBundleID {
			bundleEntries = append(bundleEntries, entry)
			operationPresent := false
			for _, operation := range graph.Operations {
				if operation.ID == entry.CanonicalOperationID {
					operationPresent = true
					break
				}
			}
			if !operationPresent {
				clone := base
				clone.ID = entry.CanonicalOperationID
				clone.LocalOperationID = entry.OperationName
				graph.Operations = append(graph.Operations, clone)
			}
		}
	}
	if len(bundleEntries) != 5 {
		t.Fatalf("canonical signed ContentPostDetail bundle entries=%d want=5", len(bundleEntries))
	}
	root := t.TempDir()
	graphPath := writeJSON(t, root, "contract_graph.json", graph)
	lockBytes, err := os.ReadFile(filepath.Join(serviceRoot, "../quwoquan_app/tool/cloud_codegen/contract_graph.lock.json"))
	if err != nil {
		t.Fatal(err)
	}
	var lock appLockDocument
	if err := json.Unmarshal(lockBytes, &lock); err != nil {
		t.Fatal(err)
	}
	writtenGraph, err := os.ReadFile(graphPath)
	if err != nil {
		t.Fatal(err)
	}
	graphDigest := sha256.Sum256(writtenGraph)
	lock.ContractGraph = appLockGraphBinding{
		Path: "quwoquan_service/generated/contract_graph.json", SHA256: hex.EncodeToString(graphDigest[:]),
	}
	lockPath := writeJSON(t, root, "app_lock.json", lock)

	generated, _, err := generateFixture(t, Options{
		RegistryPath: registryPath, MetadataPath: metadataPath, SchemaPath: schemaPath,
		ContractGraphPath: graphPath, AppLockPath: lockPath,
	})
	if err != nil {
		t.Fatalf("generate canonical five-slice bundle: %v", err)
	}
	payload := string(generated)
	for _, entry := range bundleEntries {
		if !strings.Contains(payload, "operationName: "+dartString(entry.OperationName)) ||
			!strings.Contains(payload, "sha256Hash: "+dartString(entry.SHA256Hash)) {
			t.Fatalf("generated bundle omitted signed entry %s", entry.OperationName)
		}
	}
	for _, want := range []string{
		"presenceSourceField: 'articleAssetManifestSummary'",
		"PersistedGraphQLAssemblyStrategy.assignKey",
		"if (target[entry.key] != entry.value)",
		"null presence source conflicts with",
		"'operationName': descriptor.operationName",
		"'sha256Hash': descriptor.sha256Hash",
	} {
		if !strings.Contains(payload, want) {
			t.Fatalf("generated five-slice client missing %q", want)
		}
	}
	if strings.Contains(payload, "query ContentPostDetail") || strings.Contains(payload, "'query':") {
		t.Fatal("generated App client must not embed or send query text")
	}
}

func TestGenerateRejectsPartialGraphQLSelectionForExistingDetailView(t *testing.T) {
	t.Parallel()
	root := t.TempDir()
	schemaPath, schemaDigest := writeDetailSchemaFixture(t, root)
	document := "query ContentPostDetail($postId: ID!) { contentPostDetail(postId: $postId) { postId contentType status visibility createdAt updatedAt } }\n"
	hash := sha256.Sum256([]byte(document))
	costPlan := registryCostPlan{BaseComplexity: 7, ListMultipliers: []registryListMultiplier{}, MaxOwnerCalls: 1, MaxBatchKeys: 1, MaxResponseBytes: 65536}
	appBundle := singleBundleBindingFixture()
	appBundle.SelectedFields = []string{"contentType", "createdAt", "postId", "status", "updatedAt", "visibility"}
	registryPath := writeJSON(t, root, "registry.json", map[string]any{
		"candidateDigest": canonicalDigest('1'), "schemaDigest": schemaDigest,
		"entries": []any{map[string]any{
			"sha256Hash": hex.EncodeToString(hash[:]), "operationName": "ContentPostDetail",
			"operationType": "query", "canonicalOperationId": "content.post.GetPost",
			"objectIds": []string{"content.post"}, "costModelVersion": "graphql-cost-v1",
			"costPlanDigest": digestCostPlan(t, costPlan), "executorKey": "content.post.getPost",
			"cost":            map[string]any{"depth": 2, "topLevelFields": 1, "complexity": 7, "variablesMaxBytes": 1024, "pageSizeMax": 1, "maxOwnerCalls": 1, "maxBatchKeys": 1, "maxResponseBytes": 65536, "sloRef": "slo:gateway.graphql_read.detail"},
			"costPlan":        costPlan,
			"appClientBundle": appBundle,
		}},
	})
	metadataPath := writeJSON(t, root, "query_metadata.json", map[string]any{
		"schema": "graphql-read-query-metadata",
		"entries": []any{map[string]any{
			"document": "content_post_detail.graphql", "canonicalOperationId": "content.post.GetPost",
			"queryClass": "detail", "variablesMaxBytes": 1024, "maxOwnerCalls": 1,
			"maxBatchKeys": 1, "maxResponseBytes": 65536, "sloRef": "slo:gateway.graphql_read.detail",
			"executorKey": "content.post.getPost",
		}},
	})
	if err := os.WriteFile(filepath.Join(root, "content_post_detail.graphql"), []byte(document), 0o644); err != nil {
		t.Fatal(err)
	}
	graphPath := writeJSON(t, root, "contract_graph.json", graphFixture())
	_, _, err := generateFixture(t, Options{
		RegistryPath: registryPath, MetadataPath: metadataPath,
		SchemaPath:        schemaPath,
		ContractGraphPath: graphPath,
		AppLockPath:       writeJSON(t, root, "app_lock.json", lockFixture(t, graphPath)),
	})
	if err == nil || !strings.Contains(err.Error(), "missing assembly projection fields") || !strings.Contains(err.Error(), "likeCount") {
		t.Fatalf("error=%v", err)
	}
}

func TestDetailVariableBindingIsExact(t *testing.T) {
	t.Parallel()
	for _, test := range []struct {
		name      string
		document  string
		wantError bool
	}{
		{name: "canonical", document: "query ContentPostDetail($postId: ID!) { contentPostDetail(postId: $postId) { postId } }"},
		{name: "optional", document: "query ContentPostDetail($postId: ID) { contentPostDetail(postId: $postId) { postId } }", wantError: true},
		{name: "wrong variable", document: "query ContentPostDetail($id: ID!) { contentPostDetail(postId: $id) { postId } }", wantError: true},
	} {
		test := test
		t.Run(test.name, func(t *testing.T) {
			t.Parallel()
			document, err := parser.ParseQuery(&ast.Source{Name: test.name, Input: test.document})
			if err != nil {
				t.Fatal(err)
			}
			entry := registryEntry{PaginationVariables: []string{}, CostPlan: registryCostPlan{ListMultipliers: []registryListMultiplier{}}}
			err = validateDetailVariables(document.Operations.ForName(detailOperationName), entry)
			if (err != nil) != test.wantError {
				t.Fatalf("error=%v wantError=%t", err, test.wantError)
			}
		})
	}
}

func TestMetadataCostBindingCannotDriftFromRegistry(t *testing.T) {
	t.Parallel()
	registry := registryEntry{
		CanonicalOperationID: detailOperationID, ExecutorKey: "content.post.getPost",
		Cost: registryCost{
			VariablesMaxBytes: 1024, MaxOwnerCalls: 1, MaxBatchKeys: 1,
			MaxResponseBytes: 65536, SLORef: "slo:gateway.graphql_read.detail",
		},
	}
	metadata := queryMetadataEntry{
		Document:             "persisted_queries/content_post_detail.graphql",
		CanonicalOperationID: detailOperationID, QueryClass: "detail",
		VariablesMaxBytes: 1024, MaxOwnerCalls: 1, MaxBatchKeys: 1,
		MaxResponseBytes: 65536, SLORef: "slo:gateway.graphql_read.detail",
		ExecutorKey: "content.post.getPost",
	}
	document := queryMetadataDocument{Schema: "graphql-read-query-metadata", Entries: []queryMetadataEntry{metadata}}
	if _, err := exactMetadataEntry(document, registry); err != nil {
		t.Fatalf("canonical binding: %v", err)
	}
	document.Entries[0].MaxResponseBytes++
	if _, err := exactMetadataEntry(document, registry); err == nil || !strings.Contains(err.Error(), "cost and executor") {
		t.Fatalf("drift error=%v", err)
	}
}

func TestGatewayResponseEnvelopeBudgetMustExceedSignedDataBudget(t *testing.T) {
	t.Parallel()
	gateway := graphOperation{
		Method: "POST", PathTemplate: "/graphql", Kind: "query", AuthMode: "optional",
		ActorRequirement: "none", RequestEntity: "PersistedGraphQLRequest", RequestBodyKind: "object",
		Transport: "json", ResponseEntity: "GraphQLReadResponse", ResponseBodyKind: "object",
		Reliability:       graphReliability{TimeoutMilliseconds: 3000, RetryMode: "idempotent", MaxAttempts: 2},
		ErrorCodes:        []string{"GATEWAY.USER.persisted_query_unknown"},
		ResponseAdmission: graphResponseAdmission{MaximumBodyBytes: 65536},
	}
	entry := registryEntry{Cost: registryCost{MaxResponseBytes: 65536}}
	if err := validateGatewayOperation(gateway, entry); err == nil || !strings.Contains(err.Error(), "response admission") {
		t.Fatalf("error=%v", err)
	}
}

func canonicalDigest(fill byte) string { return "sha256:" + strings.Repeat(string(fill), 64) }

func singleBundleBindingFixture() appClientBundleBinding {
	return appClientBundleBinding{
		BundleID: detailBundleID, Role: "base",
		SupportedContentTypes: []string{"micro"},
		AssemblyMappings:      []assemblyMapping{},
	}
}

func digestCostPlan(t *testing.T, plan registryCostPlan) string {
	t.Helper()
	encoded, err := json.Marshal(plan)
	if err != nil {
		t.Fatal(err)
	}
	digest := sha256.Sum256(encoded)
	return "sha256:" + hex.EncodeToString(digest[:])
}

func writeJSON(t *testing.T, root, name string, value any) string {
	t.Helper()
	encoded, err := json.MarshalIndent(value, "", "  ")
	if err != nil {
		t.Fatal(err)
	}
	path := filepath.Join(root, name)
	if err := os.WriteFile(path, append(encoded, '\n'), 0o644); err != nil {
		t.Fatal(err)
	}
	return path
}

func generateFixture(t *testing.T, options Options) ([]byte, []byte, error) {
	t.Helper()
	graphBytes, err := os.ReadFile(options.ContractGraphPath)
	if err != nil {
		t.Fatal(err)
	}
	var graph contractgraph.ContractGraph
	if err := json.Unmarshal(graphBytes, &graph); err != nil {
		t.Fatal(err)
	}
	source := contractcodegen.NewSourceFromGraph(t.TempDir(), &graph)
	return generateWithSource(options, source)
}

func writeDetailSchemaFixture(t *testing.T, root string) (string, string) {
	t.Helper()
	const schema = `schema { query: Query }
type Query { contentPostDetail(postId: ID!): ContentPostDetailSlice! }
type ContentPostDetailSlice {
  postId: ID!
  contentType: String!
  status: String!
  visibility: String!
  likeCount: Int!
  commentCount: Int!
  shareCount: Int!
  viewCount: Int!
  createdAt: String!
  updatedAt: String!
}
`
	path := filepath.Join(root, "schema.graphqls")
	if err := os.WriteFile(path, []byte(schema), 0o644); err != nil {
		t.Fatal(err)
	}
	digest := sha256.Sum256([]byte(schema))
	return path, "sha256:" + hex.EncodeToString(digest[:])
}

func graphFixture() map[string]any {
	return map[string]any{
		"operations": []any{
			map[string]any{
				"id": detailOperationID, "localId": "GetPost", "domain": "content", "objectId": "content.post",
				"method": "GET", "pathTemplate": "/content/posts/{postId}", "kind": "query",
				"responseAdmission": map[string]any{"maximumBodyBytes": 65536},
			},
			map[string]any{
				"id": "gateway.persisted_query_execution.ExecutePersistedGraphQLQuery", "localId": "ExecutePersistedGraphQLQuery",
				"domain": "gateway", "objectId": "gateway.persisted_query_execution", "method": "POST", "pathTemplate": "/graphql",
				"kind": "query", "facet": "PersistedQueryExecutionQueryFacade", "facadeMethod": "execute",
				"actorRequirement": "none", "authMode": "optional", "principal": "public", "ownershipPolicy": "signed_registry_entry_authorization",
				"commercial":        map[string]any{"status": "blocked", "blockReason": "hosted evidence pending"},
				"reliability":       map[string]any{"timeoutMilliseconds": 3000, "cancellation": "supported", "retryMode": "idempotent", "maxAttempts": 2, "idempotency": "none"},
				"errorCodes":        []string{"GATEWAY.USER.graphql_request_invalid", "GATEWAY.USER.persisted_query_unknown"},
				"privacy":           map[string]any{"requestClassification": "SENSITIVE", "responseClassification": "SENSITIVE", "logPolicy": "metadata_only"},
				"responseAdmission": map[string]any{"maximumBodyBytes": 69632},
				"telemetry":         map[string]any{"metric": "gateway_graphql_read_execute", "trace": true, "attributes": []string{"operation", "outcome"}},
				"slo":               map[string]any{"latencyP95Milliseconds": 1000, "availabilityPercent": 99.9},
				"requestEntity":     "PersistedGraphQLRequest", "requestBodyKind": "object", "transport": "json",
				"responseEntity": "GraphQLReadResponse", "responseBody": "GraphQLReadResponse", "responseBodyKind": "object",
			},
		},
		"projections": []any{map[string]any{
			"id": "content.post.ContentPostDetailSlice", "fieldNames": []string{
				"postId", "contentType", "status", "visibility", "likeCount", "commentCount", "shareCount", "viewCount", "createdAt", "updatedAt",
			},
		}},
	}
}

func lockFixture(t *testing.T, graphPath string) map[string]any {
	t.Helper()
	graphBytes, err := os.ReadFile(graphPath)
	if err != nil {
		t.Fatal(err)
	}
	graphDigest := sha256.Sum256(graphBytes)
	return map[string]any{
		"generator": "app-cloud-handoff",
		"contractGraph": map[string]any{
			"path": "quwoquan_service/generated/contract_graph.json", "sha256": hex.EncodeToString(graphDigest[:]),
		},
		"appExposedOperations": []any{map[string]any{
			"canonicalOperationId": "content.post.GetPost", "localOperationId": "GetPost", "domain": "content", "objectId": "content.post",
			"requestEntity": "ContentPostDetailQuery", "surfaceIds": []string{"workBrowser"},
			"clientContract": map[string]any{"dartImport": "../content/content_operation_contracts.g.dart", "responseType": "ContentPostDetailSlice", "responseDecoder": "decodeContentPostDetailSlice"},
		}},
	}
}
