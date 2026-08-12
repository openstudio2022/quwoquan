// spec_ref: specs/feature-tree/global-search-experience/search-provider-routing-and-storage-topology/canonical-search-contract/spec.md#gwt-002
package main

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"os"
	"path/filepath"
	"strings"
	"testing"

	contractcodegen "quwoquan_service/internal/metadata/codegen"
	contractgraph "quwoquan_service/internal/metadata/graph"
)

func TestGenerateSearchPageBindsSignedPersistedInputAndAppLock(t *testing.T) {
	t.Parallel()
	fixture := writeSearchPageFixture(t)
	generated, manifest, err := generateSearchFixture(t, fixture.options)
	if err != nil {
		t.Fatalf("generate SearchPage: %v", err)
	}
	payload := string(generated)
	for _, want := range []string{
		"final class GeneratedSearchPageGraphQLClient",
		"package:quwoquan_cloud_contracts/generated/gateway_contracts.dart",
		"Future<SearchResponseView> searchPage(SearchPageInput request",
		"operationName: 'SearchPage'",
		"canonicalOperationId: 'gateway.persisted_query_execution.SearchPage'",
		"responseKey: 'searchPage'",
		"pathTemplate: '/graphql'",
		"'variables': <String, Object?>{'input': request.toWire()}",
		"'persistedQuery': <String, Object?>{",
		"'sha256Hash': _searchPageDescriptor.sha256Hash",
		"decodeSearchResponseView(root)",
	} {
		if !strings.Contains(payload, want) {
			t.Fatalf("generated SearchPage client missing %q\n%s", want, payload)
		}
	}
	for _, forbidden := range []string{"query SearchPage", "'query':", "'/search'", "searchSearchIndexViewSearch"} {
		if strings.Contains(payload, forbidden) {
			t.Fatalf("generated SearchPage client contains forbidden REST/query-text fallback %q", forbidden)
		}
	}
	var decoded generatedManifest
	if err := json.Unmarshal(manifest, &decoded); err != nil {
		t.Fatal(err)
	}
	if decoded.Generator != searchAppClientGenerator || len(decoded.Outputs) != 1 || decoded.Outputs[0].Path != searchAppClientOutputPath {
		t.Fatalf("manifest=%+v", decoded)
	}
}

func TestGenerateSearchPageRejectsUnsignedOrDriftedBindings(t *testing.T) {
	t.Parallel()
	tests := []struct {
		name string
		edit func(t *testing.T, fixture *searchPageFixture)
		want string
	}{
		{
			name: "query text operation name",
			edit: func(t *testing.T, fixture *searchPageFixture) {
				t.Helper()
				fixture.rewriteDocument(t, strings.ReplaceAll(fixture.document, "query SearchPage", "query SearchPageAlias"), true)
			},
			want: "exactly one signed SearchPage",
		},
		{
			name: "root alias",
			edit: func(t *testing.T, fixture *searchPageFixture) {
				t.Helper()
				fixture.rewriteDocument(t, strings.ReplaceAll(fixture.document, "searchPage(input:", "result: searchPage(input:"), true)
			},
			want: "root must be unaliased",
		},
		{
			name: "request app lock drift",
			edit: func(t *testing.T, fixture *searchPageFixture) {
				t.Helper()
				fixture.lock["appExposedOperations"].([]any)[0].(map[string]any)["requestEntity"] = "CanonicalSearchQuery"
				fixture.rewriteLock(t)
			},
			want: "request type differs",
		},
		{
			name: "schema-owned response field drift",
			edit: func(t *testing.T, fixture *searchPageFixture) {
				t.Helper()
				types := fixture.graph["documents"].([]any)[0].(map[string]any)["content"].(map[string]any)["types"].(map[string]any)
				types["SearchResponseView"].(map[string]any)["fields"] = []any{map[string]any{"name": "hits"}}
				fixture.rewriteGraphAndLock(t)
			},
			want: "response fields differ from persisted selection",
		},
	}
	for _, test := range tests {
		test := test
		t.Run(test.name, func(t *testing.T) {
			t.Parallel()
			fixture := writeSearchPageFixture(t)
			test.edit(t, &fixture)
			_, _, err := generateSearchFixture(t, fixture.options)
			if err == nil || !strings.Contains(err.Error(), test.want) {
				t.Fatalf("error=%v want substring %q", err, test.want)
			}
		})
	}
}

type searchPageFixture struct {
	root         string
	document     string
	documentPath string
	registry     map[string]any
	registryPath string
	graph        map[string]any
	graphPath    string
	lock         map[string]any
	lockPath     string
	options      Options
}

func writeSearchPageFixture(t *testing.T) searchPageFixture {
	t.Helper()
	root := t.TempDir()
	const schema = `directive @listCost(argument: String!, defaultValue: Int!, maximumValue: Int!) on FIELD_DEFINITION
schema { query: Query }
enum SearchPageMode { SUGGEST RESULT }
input SearchPageInput { query: String!, mode: SearchPageMode!, first: Int = 20 }
type SearchHitView { objectRef: String!, title: String! }
type SearchResponseView {
  hits: [SearchHitView!]! @listCost(argument: "input.first", defaultValue: 20, maximumValue: 20)
  nextCursor: String
}
type Query { searchPage(input: SearchPageInput!): SearchResponseView! }
`
	schemaPath := filepath.Join(root, "schema.graphqls")
	if err := os.WriteFile(schemaPath, []byte(schema), 0o644); err != nil {
		t.Fatal(err)
	}
	schemaHash := sha256.Sum256([]byte(schema))
	schemaDigest := "sha256:" + hex.EncodeToString(schemaHash[:])
	document := "query SearchPage($input: SearchPageInput!) {\n  searchPage(input: $input) {\n    hits { objectRef title }\n    nextCursor\n  }\n}\n"
	documentPath := filepath.Join(root, "search_page.graphql")
	if err := os.WriteFile(documentPath, []byte(document), 0o644); err != nil {
		t.Fatal(err)
	}
	documentHash := sha256.Sum256([]byte(document))
	costPlan := registryCostPlan{
		BaseComplexity:  3,
		ListMultipliers: []registryListMultiplier{{VariablePath: "input.first", Coefficient: 2, DefaultValue: 20, MaximumValue: 20}},
		MaxOwnerCalls:   1, MaxBatchKeys: 20, MaxResponseBytes: 65536,
	}
	registry := map[string]any{
		"candidateDigest": canonicalDigest('7'), "schemaDigest": schemaDigest,
		"entries": []any{map[string]any{
			"sha256Hash": hex.EncodeToString(documentHash[:]), "operationName": searchPageOperationName,
			"operationType": "query", "canonicalOperationId": searchPageOperationID,
			"objectIds": []string{"gateway.persisted_query_execution"}, "costModelVersion": "graphql-cost-v1",
			"authorization":  map[string]any{"principal": "public", "scopes": []string{}, "ownershipPolicy": "visibility_filtered"},
			"costPlanDigest": digestCostPlan(t, costPlan), "executorKey": "search.search_index_view.search",
			"cost": map[string]any{
				"depth": 3, "topLevelFields": 1, "complexity": 43, "variablesMaxBytes": 4096,
				"pageSizeMax": 20, "maxOwnerCalls": 1, "maxBatchKeys": 20,
				"maxResponseBytes": 65536, "sloRef": "slo:gateway.persisted_query_execution.search_page",
			},
			"costPlan": costPlan, "paginationVariables": []string{"input.first"},
		}},
	}
	registryPath := writeJSON(t, root, "registry.json", registry)
	metadataPath := writeJSON(t, root, "query_metadata.json", map[string]any{
		"schema": "graphql-read-query-metadata",
		"entries": []any{map[string]any{
			"document": "search_page.graphql", "canonicalOperationId": searchPageOperationID,
			"queryClass": "page_composite", "variablesMaxBytes": 4096,
			"maxOwnerCalls": 1, "maxBatchKeys": 20, "maxResponseBytes": 65536,
			"sloRef": "slo:gateway.persisted_query_execution.search_page", "executorKey": "search.search_index_view.search",
		}},
	})
	graph := searchGraphFixture()
	graphPath := writeJSON(t, root, "contract_graph.json", graph)
	lock := searchLockFixture(t, graphPath)
	lockPath := writeJSON(t, root, "app_lock.json", lock)
	return searchPageFixture{
		root: root, document: document, documentPath: documentPath,
		registry: registry, registryPath: registryPath,
		graph: graph, graphPath: graphPath, lock: lock, lockPath: lockPath,
		options: Options{
			RegistryPath: registryPath, MetadataPath: metadataPath, SchemaPath: schemaPath,
			ContractGraphPath: graphPath, AppLockPath: lockPath,
		},
	}
}

func (fixture *searchPageFixture) rewriteDocument(t *testing.T, document string, updateRegistryHash bool) {
	t.Helper()
	fixture.document = document
	if err := os.WriteFile(fixture.documentPath, []byte(document), 0o644); err != nil {
		t.Fatal(err)
	}
	if updateRegistryHash {
		digest := sha256.Sum256([]byte(document))
		fixture.registry["entries"].([]any)[0].(map[string]any)["sha256Hash"] = hex.EncodeToString(digest[:])
		fixture.registryPath = writeJSON(t, fixture.root, "registry.json", fixture.registry)
		fixture.options.RegistryPath = fixture.registryPath
	}
}

func (fixture *searchPageFixture) rewriteGraphAndLock(t *testing.T) {
	t.Helper()
	fixture.graphPath = writeJSON(t, fixture.root, "contract_graph.json", fixture.graph)
	fixture.options.ContractGraphPath = fixture.graphPath
	fixture.lock = searchLockFixture(t, fixture.graphPath)
	fixture.rewriteLock(t)
}

func (fixture *searchPageFixture) rewriteLock(t *testing.T) {
	t.Helper()
	fixture.lockPath = writeJSON(t, fixture.root, "app_lock.json", fixture.lock)
	fixture.options.AppLockPath = fixture.lockPath
}

func generateSearchFixture(t *testing.T, options Options) ([]byte, []byte, error) {
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
	return generateSearchWithSource(options, source)
}

func searchGraphFixture() map[string]any {
	graph := graphFixture()
	operations := graph["operations"].([]any)
	operations = append(operations, map[string]any{
		"id": searchPageOperationID, "localId": searchPageOperationName,
		"domain": "gateway", "objectId": "gateway.persisted_query_execution", "kind": "query",
		"method": "POST", "pathTemplate": "/graphql", "requestEntity": "SearchPageInput",
		"responseEntity": "SearchResponseView", "responseAdmission": map[string]any{"maximumBodyBytes": 65536},
		"sourcePath": "gateway/graphql_read/persisted_query_execution/operations.yaml",
	})
	graph["operations"] = operations
	graph["projections"] = []any{}
	graph["documents"] = []any{map[string]any{
		"path":   "gateway/graphql_read/persisted_query_execution/fields.yaml",
		"sha256": strings.Repeat("a", 64), "mediaType": "application/yaml",
		"content": map[string]any{"types": map[string]any{
			"SearchPageInput": map[string]any{"fields": []any{
				map[string]any{"name": "query"}, map[string]any{"name": "mode"}, map[string]any{"name": "first"},
			}},
			"SearchResponseView": map[string]any{"fields": []any{
				map[string]any{"name": "hits"}, map[string]any{"name": "nextCursor"},
			}},
		}},
	}}
	return graph
}

func searchLockFixture(t *testing.T, graphPath string) map[string]any {
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
			"canonicalOperationId": searchPageOperationID, "requestEntity": "SearchPageInput",
			"surfaceIds": []string{"search"},
			"clientContract": map[string]any{
				"responseType": "SearchResponseView", "responseDecoder": "decodeSearchResponseView",
			},
		}},
	}
}
