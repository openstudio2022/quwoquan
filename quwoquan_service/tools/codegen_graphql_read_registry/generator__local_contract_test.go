// spec_ref: specs/feature-tree/gateway-orchestrator-foundation/spec.md#dom-001
package main

import (
	"bytes"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"github.com/santhosh-tekuri/jsonschema/v6"
	metadataast "quwoquan_service/internal/metadata/ast"
	contractcodegen "quwoquan_service/internal/metadata/codegen"
	"quwoquan_service/internal/metadata/graph"
	"quwoquan_service/internal/testsupport/contractsview"
)

const testCandidateDigest = "sha256:1111111111111111111111111111111111111111111111111111111111111111"

func TestGenerateComputesDeterministicDetailCostWithoutMetadataOverrides(t *testing.T) {
	t.Parallel()
	root := t.TempDir()
	schemaPath := writeFixture(t, root, "schema.graphqls", detailSchema)
	queryPath := writeFixture(t, root, "queries/detail.graphql", detailQuery)
	metadataPath := writeMetadata(t, root, metadataEntry{
		Document:             filepath.ToSlash(mustRelative(t, root, queryPath)),
		CanonicalOperationID: "content.post.GetPost",
		QueryClass:           "detail",
		VariablesMaxBytes:    1024,
		MaxOwnerCalls:        1,
		MaxBatchKeys:         1,
		MaxResponseBytes:     64 * 1024,
		SLORef:               "slo:gateway.graphql_read.detail",
		ExecutorKey:          "content.post.getPost",
	})

	first, err := generateForTest(t, Options{
		SchemaPath:      schemaPath,
		MetadataPath:    metadataPath,
		CandidateDigest: testCandidateDigest,
	})
	if err != nil {
		t.Fatalf("generate registry: %v", err)
	}
	second, err := generateForTest(t, Options{
		SchemaPath:      schemaPath,
		MetadataPath:    metadataPath,
		CandidateDigest: testCandidateDigest,
	})
	if err != nil {
		t.Fatalf("regenerate registry: %v", err)
	}
	if !bytes.Equal(first, second) {
		t.Fatal("same schema, documents, and metadata must be byte deterministic")
	}

	registry := decodeRegistry(t, first)
	if registry.SchemaDigest != digestWithPrefix([]byte(detailSchema)) {
		t.Fatalf("schemaDigest=%q", registry.SchemaDigest)
	}
	if len(registry.Entries) != 1 {
		t.Fatalf("entries=%d", len(registry.Entries))
	}
	entry := registry.Entries[0]
	wantHash := sha256.Sum256([]byte(detailQuery))
	if entry.SHA256Hash != hex.EncodeToString(wantHash[:]) {
		t.Fatalf("sha256Hash=%q", entry.SHA256Hash)
	}
	if entry.CostModelVersion != costModelVersion {
		t.Fatalf("costModelVersion=%q", entry.CostModelVersion)
	}
	if entry.Cost.Depth != 2 || entry.Cost.TopLevelFields != 1 || entry.Cost.Complexity != 13 {
		t.Fatalf("computed cost=%+v", entry.Cost)
	}
	if entry.Cost.PageSizeMax != 1 || len(entry.PaginationVariables) != 0 {
		t.Fatalf("pagination cost=%+v variables=%v", entry.Cost, entry.PaginationVariables)
	}
	if entry.CostPlan.BaseComplexity != 13 || len(entry.CostPlan.ListMultipliers) != 0 {
		t.Fatalf("costPlan=%+v", entry.CostPlan)
	}
	if entry.CostPlanDigest != digestCostPlan(t, entry.CostPlan) {
		t.Fatalf("costPlanDigest=%q", entry.CostPlanDigest)
	}

	rawMetadata, err := os.ReadFile(metadataPath)
	if err != nil {
		t.Fatal(err)
	}
	for _, computed := range []string{
		`"depth"`, `"topLevelFields"`, `"complexity"`, `"pageSizeMax"`,
		`"baseComplexity"`, `"listMultipliers"`, `"costPlanDigest"`,
		`"operationName"`, `"objectIds"`, `"authorization"`,
	} {
		if bytes.Contains(rawMetadata, []byte(computed)) {
			t.Fatalf("manual metadata contains computed field %s", computed)
		}
	}
}

func TestGenerateRequiresContractGraphMetadataDirectory(t *testing.T) {
	t.Parallel()
	_, err := Generate(Options{CandidateDigest: testCandidateDigest})
	if err == nil || !strings.Contains(err.Error(), "metadataDir is required") {
		t.Fatalf("error=%v", err)
	}
}

func TestGenerateExpandsAliasesFragmentsDirectivesAndAbstractTypes(t *testing.T) {
	t.Parallel()
	root := t.TempDir()
	schemaPath := writeFixture(t, root, "schema.graphqls", abstractListSchema)
	queryPath := writeFixture(t, root, "queries/search.graphql", abstractListQuery)
	metadataPath := writeMetadata(t, root, metadataEntry{
		Document:             filepath.ToSlash(mustRelative(t, root, queryPath)),
		CanonicalOperationID: "search.result.Search",
		QueryClass:           "collection",
		VariablesMaxBytes:    4096,
		MaxOwnerCalls:        1,
		MaxBatchKeys:         10,
		MaxResponseBytes:     128 * 1024,
		SLORef:               "slo:gateway.graphql_read.search",
		ExecutorKey:          "search.result.search",
	})

	encoded, err := generateForTest(t, Options{
		SchemaPath:      schemaPath,
		MetadataPath:    metadataPath,
		CandidateDigest: testCandidateDigest,
	})
	if err != nil {
		t.Fatalf("generate abstract list registry: %v", err)
	}
	entry := decodeRegistry(t, encoded).Entries[0]
	if entry.Cost.Depth != 2 || entry.Cost.TopLevelFields != 1 {
		t.Fatalf("structural cost=%+v", entry.Cost)
	}
	// Query root is free. search costs 2; the worst concrete union branch costs
	// __typename + two fragment fields = 3 per item.
	if entry.CostPlan.BaseComplexity != 8 || entry.Cost.Complexity != 32 {
		t.Fatalf("list cost=%+v plan=%+v", entry.Cost, entry.CostPlan)
	}
	wantMultiplier := ListMultiplier{
		VariablePath: "first", Coefficient: 3, DefaultValue: 2, MaximumValue: 10,
	}
	if len(entry.CostPlan.ListMultipliers) != 1 || entry.CostPlan.ListMultipliers[0] != wantMultiplier {
		t.Fatalf("listMultipliers=%+v", entry.CostPlan.ListMultipliers)
	}
	if len(entry.PaginationVariables) != 1 || entry.PaginationVariables[0] != "first" {
		t.Fatalf("paginationVariables=%v", entry.PaginationVariables)
	}
	actualAtFive := entry.CostPlan.BaseComplexity +
		entry.CostPlan.ListMultipliers[0].Coefficient*(5-entry.CostPlan.ListMultipliers[0].DefaultValue)
	if actualAtFive != 17 {
		t.Fatalf("actual complexity at first=5 is %d", actualAtFive)
	}
}

func TestGenerateUsesWorstConcreteInterfaceBranchAndStaticDirectives(t *testing.T) {
	t.Parallel()
	root := t.TempDir()
	schemaPath := writeFixture(t, root, "schema.graphqls", `interface Node { id: ID! }
type User implements Node { id: ID!, name: String! }
type Post implements Node { id: ID!, title: String! }
type Query { node: Node }
`)
	queryPath := writeFixture(t, root, "queries/node.graphql", `query NodeDetail($includeLabel: Boolean! = true) {
  node {
    id
    ... on User { label: name @include(if: $includeLabel) }
    ... on Post { label: title }
  }
  ignored: node @skip(if: true) { id }
}
`)
	entry := collectionMetadata(filepath.ToSlash(mustRelative(t, root, queryPath)))
	entry.QueryClass = "detail"
	metadataPath := writeMetadata(t, root, entry)
	encoded, err := generateForTest(t, Options{
		SchemaPath: schemaPath, MetadataPath: metadataPath,
		CandidateDigest: testCandidateDigest,
	})
	if err != nil {
		t.Fatalf("generate interface registry: %v", err)
	}
	computed := decodeRegistry(t, encoded).Entries[0].Cost
	if computed.Depth != 2 || computed.TopLevelFields != 1 || computed.Complexity != 3 {
		t.Fatalf("interface cost=%+v", computed)
	}
}

func TestGenerateComputesScalarListMultiplier(t *testing.T) {
	t.Parallel()
	root := t.TempDir()
	schemaPath := writeFixture(t, root, "schema.graphqls", `directive @listCost(argument: String!, defaultValue: Int!, maximumValue: Int!) on FIELD_DEFINITION
type Query {
  tags(first: Int!): [String!]! @listCost(argument: "first", defaultValue: 3, maximumValue: 7)
}
`)
	queryPath := writeFixture(t, root, "queries/tags.graphql", "query Tags($first: Int! = 3) { tags(first: $first) }\n")
	entry := collectionMetadata(filepath.ToSlash(mustRelative(t, root, queryPath)))
	entry.QueryClass = "detail"
	metadataPath := writeMetadata(t, root, entry)
	encoded, err := generateForTest(t, Options{
		SchemaPath: schemaPath, MetadataPath: metadataPath,
		CandidateDigest: testCandidateDigest,
	})
	if err != nil {
		t.Fatalf("generate scalar list registry: %v", err)
	}
	generated := decodeRegistry(t, encoded).Entries[0]
	if generated.CostPlan.BaseComplexity != 5 || generated.Cost.Complexity != 9 {
		t.Fatalf("scalar list cost=%+v plan=%+v", generated.Cost, generated.CostPlan)
	}
	want := ListMultiplier{VariablePath: "first", Coefficient: 1, DefaultValue: 3, MaximumValue: 7}
	if len(generated.CostPlan.ListMultipliers) != 1 || generated.CostPlan.ListMultipliers[0] != want {
		t.Fatalf("scalar list multiplier=%+v", generated.CostPlan.ListMultipliers)
	}
}

func TestGenerateComputesListMultiplierFromSingleInputObject(t *testing.T) {
	t.Parallel()
	root := t.TempDir()
	schemaPath := writeFixture(t, root, "schema.graphqls", `directive @listCost(argument: String!, defaultValue: Int!, maximumValue: Int!) on FIELD_DEFINITION
input SearchPageInput { query: String!, first: Int = 20 }
type SearchCard { objectRef: String!, title: String! }
type SearchPage { cards: [SearchCard!]! @listCost(argument: "input.first", defaultValue: 20, maximumValue: 20) }
type Query { searchPage(input: SearchPageInput!): SearchPage! }
`)
	queryPath := writeFixture(t, root, "queries/search_page.graphql", `query SearchPage($input: SearchPageInput!) {
  searchPage(input: $input) { cards { objectRef title } }
}
`)
	entry := collectionMetadata(filepath.ToSlash(mustRelative(t, root, queryPath)))
	metadataPath := writeMetadata(t, root, entry)
	encoded, err := generateForTest(t, Options{
		SchemaPath: schemaPath, MetadataPath: metadataPath,
		CandidateDigest: testCandidateDigest,
	})
	if err != nil {
		t.Fatalf("generate single-input collection registry: %v", err)
	}
	generated := decodeRegistry(t, encoded).Entries[0]
	want := ListMultiplier{
		VariablePath: "input.first", Coefficient: 2,
		DefaultValue: 20, MaximumValue: 20,
	}
	if len(generated.CostPlan.ListMultipliers) != 1 || generated.CostPlan.ListMultipliers[0] != want {
		t.Fatalf("single-input list multiplier=%+v", generated.CostPlan.ListMultipliers)
	}
	if len(generated.PaginationVariables) != 1 || generated.PaginationVariables[0] != "input.first" {
		t.Fatalf("pagination variables=%v", generated.PaginationVariables)
	}
}

func TestGenerateRejectsUnboundedAndNestedLists(t *testing.T) {
	t.Parallel()
	tests := []struct {
		name    string
		schema  string
		query   string
		message string
	}{
		{
			name:    "list has no cost policy",
			schema:  strings.Replace(abstractListSchema, ` @listCost(argument: "first", defaultValue: 2, maximumValue: 10)`, "", 1),
			query:   abstractListQuery,
			message: "bounded @listCost",
		},
		{
			name:   "pagination argument is literal",
			schema: abstractListSchema,
			query: strings.Replace(strings.Replace(
				abstractListQuery,
				"$first: Int! = 2, ",
				"",
				1,
			), "search(first: $first)", "search(first: 2)", 1),
			message: "pagination variable",
		},
		{
			name: "nested list",
			schema: strings.Replace(
				abstractListSchema,
				"name: String!",
				"name: String!\n  friends(first: Int!): [User!]! @listCost(argument: \"first\", defaultValue: 2, maximumValue: 10)",
				1,
			),
			query: strings.Replace(
				abstractListQuery,
				"displayName: name @include(if: $includeNames)",
				"displayName: name @include(if: $includeNames)\n    friends(first: $first) { id }",
				1,
			),
			message: "nested list",
		},
		{
			name: "nested list return type",
			schema: `directive @listCost(argument: String!, defaultValue: Int!, maximumValue: Int!) on FIELD_DEFINITION
type Query {
  matrix(first: Int!): [[String!]!]! @listCost(argument: "first", defaultValue: 2, maximumValue: 10)
}
`,
			query:   "query Search($first: Int! = 2) { matrix(first: $first) }\n",
			message: "nested list",
		},
	}
	for _, test := range tests {
		test := test
		t.Run(test.name, func(t *testing.T) {
			t.Parallel()
			root := t.TempDir()
			schemaPath := writeFixture(t, root, "schema.graphqls", test.schema)
			queryPath := writeFixture(t, root, "queries/search.graphql", test.query)
			metadataPath := writeMetadata(t, root, collectionMetadata(filepath.ToSlash(mustRelative(t, root, queryPath))))
			_, err := generateForTest(t, Options{
				SchemaPath: schemaPath, MetadataPath: metadataPath,
				CandidateDigest: testCandidateDigest,
			})
			if err == nil || !strings.Contains(err.Error(), test.message) {
				t.Fatalf("error=%v, want substring %q", err, test.message)
			}
		})
	}
}

func TestGenerateEnforcesStructuralAndQueryClassExceptions(t *testing.T) {
	t.Parallel()
	tests := []struct {
		name      string
		schema    string
		query     string
		class     string
		mutate    func(*metadataEntry)
		wantError string
	}{
		{
			name:   "depth four requires exception",
			schema: deepSchema,
			query:  "query Deep { root { child { leaf { value } } } }\n",
			class:  "detail", wantError: "depthExceptionRef",
		},
		{
			name:      "depth six is forbidden",
			schema:    deepSchema,
			query:     "query Deep { root { child { leaf { deeper { final { value } } } } } }\n",
			class:     "detail",
			mutate:    func(entry *metadataEntry) { entry.DepthExceptionRef = "spec:review/depth" },
			wantError: "depth=6",
		},
		{
			name:   "four top level fields require exception",
			schema: "type Query { a: String! b: String! c: String! d: String! }\n",
			query:  "query Wide { a b c d }\n",
			class:  "detail", wantError: "topLevelExceptionRef",
		},
		{
			name:   "detail over one hundred requires exception",
			schema: "directive @cost(weight: Int!) on FIELD_DEFINITION\ntype Query { expensive: String! @cost(weight: 101) }\n",
			query:  "query Expensive { expensive }\n",
			class:  "detail", wantError: "complexityExceptionRef",
		},
		{
			name:      "collection over three hundred requires exception",
			schema:    "directive @cost(weight: Int!) on FIELD_DEFINITION\ntype Query { expensive: String! @cost(weight: 301) }\n",
			query:     "query Expensive { expensive }\n",
			class:     "collection",
			wantError: "complexityExceptionRef",
		},
		{
			name:      "page composite over five hundred requires exception",
			schema:    "directive @cost(weight: Int!) on FIELD_DEFINITION\ntype Query { expensive: String! @cost(weight: 501) }\n",
			query:     "query Expensive { expensive }\n",
			class:     "page_composite",
			wantError: "complexityExceptionRef",
		},
		{
			name:      "global complexity over one thousand is forbidden",
			schema:    "directive @cost(weight: Int!) on FIELD_DEFINITION\ntype Query { expensive: String! @cost(weight: 1001) }\n",
			query:     "query Expensive { expensive }\n",
			class:     "page_composite",
			mutate:    func(entry *metadataEntry) { entry.ComplexityExceptionRef = "spec:review/complexity" },
			wantError: "complexity=1001",
		},
	}
	for _, test := range tests {
		test := test
		t.Run(test.name, func(t *testing.T) {
			t.Parallel()
			root := t.TempDir()
			schemaPath := writeFixture(t, root, "schema.graphqls", test.schema)
			queryPath := writeFixture(t, root, "queries/query.graphql", test.query)
			entry := collectionMetadata(filepath.ToSlash(mustRelative(t, root, queryPath)))
			entry.QueryClass = test.class
			if test.mutate != nil {
				test.mutate(&entry)
			}
			metadataPath := writeMetadata(t, root, entry)
			_, err := generateForTest(t, Options{
				SchemaPath: schemaPath, MetadataPath: metadataPath,
				CandidateDigest: testCandidateDigest,
			})
			if err == nil || !strings.Contains(err.Error(), test.wantError) {
				t.Fatalf("error=%v, want substring %q", err, test.wantError)
			}
		})
	}
}

func TestGenerateAcceptsRequiredExceptionReferences(t *testing.T) {
	t.Parallel()
	root := t.TempDir()
	schemaPath := writeFixture(t, root, "schema.graphqls", deepSchema)
	queryPath := writeFixture(t, root, "queries/deep.graphql", "query Deep { root { child { leaf { value } } } }\n")
	entry := collectionMetadata(filepath.ToSlash(mustRelative(t, root, queryPath)))
	entry.QueryClass = "detail"
	entry.DepthExceptionRef = "spec:review/graphql-depth-4"
	metadataPath := writeMetadata(t, root, entry)
	encoded, err := generateForTest(t, Options{
		SchemaPath: schemaPath, MetadataPath: metadataPath,
		CandidateDigest: testCandidateDigest,
	})
	if err != nil {
		t.Fatalf("generate depth exception: %v", err)
	}
	if got := decodeRegistry(t, encoded).Entries[0].Cost.DepthExceptionRef; got != entry.DepthExceptionRef {
		t.Fatalf("depthExceptionRef=%q", got)
	}
}

func TestGenerateAcceptsQueryClassComplexityException(t *testing.T) {
	t.Parallel()
	root := t.TempDir()
	schemaPath := writeFixture(t, root, "schema.graphqls", "directive @cost(weight: Int!) on FIELD_DEFINITION\ntype Query { expensive: String! @cost(weight: 501) }\n")
	queryPath := writeFixture(t, root, "queries/expensive.graphql", "query Expensive { expensive }\n")
	entry := collectionMetadata(filepath.ToSlash(mustRelative(t, root, queryPath)))
	entry.QueryClass = "page_composite"
	entry.ComplexityExceptionRef = "spec:review/graphql-complexity-501"
	metadataPath := writeMetadata(t, root, entry)
	encoded, err := generateForTest(t, Options{
		SchemaPath: schemaPath, MetadataPath: metadataPath,
		CandidateDigest: testCandidateDigest,
	})
	if err != nil {
		t.Fatalf("generate complexity exception: %v", err)
	}
	if got := decodeRegistry(t, encoded).Entries[0].Cost.ComplexityExceptionRef; got != entry.ComplexityExceptionRef {
		t.Fatalf("complexityExceptionRef=%q", got)
	}
}

func TestGenerateRejectsComputedMetadataAndMutations(t *testing.T) {
	t.Parallel()
	root := t.TempDir()
	schemaPath := writeFixture(t, root, "schema.graphqls", detailSchema)
	queryPath := writeFixture(t, root, "queries/detail.graphql", strings.Replace(detailQuery, "query ContentPostDetail", "mutation ContentPostDetail", 1))
	metadataPath := writeMetadata(t, root, collectionMetadata(filepath.ToSlash(mustRelative(t, root, queryPath))))
	metadataBytes, err := os.ReadFile(metadataPath)
	if err != nil {
		t.Fatal(err)
	}
	metadataBytes = bytes.Replace(metadataBytes, []byte(`"queryClass"`), []byte(`"complexity":13,"queryClass"`), 1)
	if err := os.WriteFile(metadataPath, metadataBytes, 0o600); err != nil {
		t.Fatal(err)
	}
	_, err = generateForTest(t, Options{
		SchemaPath: schemaPath, MetadataPath: metadataPath,
		CandidateDigest: testCandidateDigest,
	})
	if err == nil || !strings.Contains(err.Error(), "unknown field") {
		t.Fatalf("computed metadata error=%v", err)
	}

	mutationMetadata := collectionMetadata(filepath.ToSlash(mustRelative(t, root, queryPath)))
	metadataPath = writeMetadata(t, root, mutationMetadata)
	_, err = generateForTest(t, Options{
		SchemaPath: schemaPath, MetadataPath: metadataPath,
		CandidateDigest: testCandidateDigest,
	})
	if err == nil || !strings.Contains(err.Error(), "parse persisted query") {
		t.Fatalf("mutation error=%v", err)
	}
}

func TestCheckedInRegistryExampleIsGeneratedFromCanonicalInputs(t *testing.T) {
	serviceRoot := filepath.Clean(filepath.Join("..", ".."))
	policyRoot := filepath.Join(serviceRoot, "services", "api-edge", "resources", "policies", "graphql_read")
	encoded, err := Generate(Options{
		SchemaPath:      filepath.Join(policyRoot, "schema.graphqls"),
		MetadataPath:    filepath.Join(policyRoot, "query_metadata.json"),
		MetadataDir:     contractsview.Build(t),
		CandidateDigest: testCandidateDigest,
	})
	if err != nil {
		t.Fatalf("generate canonical registry example: %v", err)
	}
	checkedIn, err := os.ReadFile(filepath.Join(policyRoot, "persisted_query_registry.example.json"))
	if err != nil {
		t.Fatal(err)
	}
	if !bytes.Equal(encoded, checkedIn) {
		t.Fatal("checked-in persisted query registry example is stale")
	}
	registry := decodeRegistry(t, encoded)
	if len(registry.Entries) != 6 {
		t.Fatalf("canonical registry entries=%d want=6", len(registry.Entries))
	}
	baseCount := 0
	presenceBound := false
	searchBound := false
	for _, entry := range registry.Entries {
		if entry.AppClientBundle == nil {
			if entry.CanonicalOperationID != "gateway.persisted_query_execution.SearchPage" ||
				entry.OperationName != "SearchPage" || entry.Cost.Depth != 3 ||
				entry.Cost.TopLevelFields != 1 || entry.Cost.Complexity != 208 {
				t.Fatalf("non-bundle canonical operation is invalid: %+v", entry)
			}
			searchBound = true
			continue
		}
		if entry.AppClientBundle.Role == "base" {
			baseCount++
		}
		for _, mapping := range entry.AppClientBundle.AssemblyMappings {
			if mapping.TargetField == "articleAssetManifest" &&
				mapping.PresenceSourceField == "articleAssetManifestSummary" {
				presenceBound = true
			}
		}
	}
	if baseCount != 1 || !presenceBound || !searchBound {
		t.Fatalf(
			"canonical registry baseCount=%d presenceBound=%t searchBound=%t",
			baseCount,
			presenceBound,
			searchBound,
		)
	}
}

func TestCanonicalQueryMetadataContainsNoContractGraphSecondTruth(t *testing.T) {
	t.Parallel()
	path := filepath.Join(
		"..", "..", "services", "api-edge", "resources", "policies",
		"graphql_read", "query_metadata.json",
	)
	encoded, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}
	for _, forbidden := range []string{
		`"operationName"`, `"objectIds"`, `"authorization"`, `"operationType"`,
		`"appClientBundle"`, `"assemblyMappings"`, `"selectedFields"`,
		`"supportedContentTypes"`, `"requiredForContentTypes"`,
	} {
		if bytes.Contains(encoded, []byte(forbidden)) {
			t.Fatalf("query metadata contains ContractGraph second truth %s", forbidden)
		}
	}
}

func TestCheckedInRegistryExampleMatchesClosedJSONSchema(t *testing.T) {
	serviceRoot := filepath.Clean(filepath.Join("..", ".."))
	policyRoot := filepath.Join(serviceRoot, "services", "api-edge", "resources", "policies", "graphql_read")
	compiled, err := jsonschema.NewCompiler().Compile(
		filepath.Join(policyRoot, "persisted_query_registry.schema.json"),
	)
	if err != nil {
		t.Fatalf("compile persisted query registry schema: %v", err)
	}
	example, err := os.ReadFile(filepath.Join(policyRoot, "persisted_query_registry.example.json"))
	if err != nil {
		t.Fatal(err)
	}
	var document any
	if err := json.Unmarshal(example, &document); err != nil {
		t.Fatalf("decode persisted query registry example: %v", err)
	}
	if err := compiled.Validate(document); err != nil {
		t.Fatalf("validate persisted query registry example: %v", err)
	}
}

func collectionMetadata(document string) metadataEntry {
	return metadataEntry{
		Document:             document,
		CanonicalOperationID: "search.result.Search",
		QueryClass:           "collection", VariablesMaxBytes: 4096,
		MaxOwnerCalls: 1, MaxBatchKeys: 100, MaxResponseBytes: 128 * 1024,
		SLORef: "slo:gateway.graphql_read.search", ExecutorKey: "search.result.search",
	}
}

func generateForTest(t *testing.T, options Options) ([]byte, error) {
	t.Helper()
	metadata, err := loadMetadata(options.MetadataPath)
	if err != nil {
		return nil, err
	}
	contractGraph := &graph.ContractGraph{}
	for _, entry := range metadata.Entries {
		parts := strings.Split(entry.CanonicalOperationID, ".")
		if len(parts) != 3 {
			t.Fatalf("canonical operation fixture=%q", entry.CanonicalOperationID)
		}
		objectID := strings.Join(parts[:2], ".")
		ownerDir := filepath.ToSlash(filepath.Join(parts[0], parts[0], parts[1]))
		documentPath := filepath.Join(
			filepath.Dir(options.MetadataPath),
			filepath.FromSlash(entry.Document),
		)
		document, readErr := os.ReadFile(documentPath)
		if readErr != nil {
			return nil, readErr
		}
		fields := strings.Fields(string(document))
		if len(fields) < 2 {
			t.Fatalf("persisted query fixture has no named operation: %s", documentPath)
		}
		operationName := strings.SplitN(fields[1], "(", 2)[0]
		principal := "account"
		ownershipPolicy := "account_visible"
		var scopes []string
		if objectID == "content.post" {
			principal = "public"
			ownershipPolicy = "visibility_filtered"
		} else {
			scopes = []string{parts[0] + ":read"}
		}
		contractGraph.Operations = append(contractGraph.Operations, metadataast.Operation{
			ID: entry.CanonicalOperationID, ObjectID: objectID,
			Kind: metadataast.OperationKindQuery, KindExplicit: true,
			Principal: principal, Scopes: scopes, OwnershipPolicy: ownershipPolicy,
			Commercial: metadataast.CommercialBinding{Status: "ready", Explicit: true},
			SourcePath: filepath.ToSlash(filepath.Join(ownerDir, "operations.yaml")),
		})
		documentDigest := sha256.Sum256(document)
		documentHash := hex.EncodeToString(documentDigest[:])
		documentBase := filepath.Base(documentPath)
		ownerDocumentPath := filepath.ToSlash(filepath.Join(ownerDir, "persisted_queries", documentBase))
		ownerBindingPath := strings.TrimSuffix(ownerDocumentPath, ".graphql") + ".yaml"
		ownerBinding, marshalErr := json.Marshal(ownerPersistedQueryBinding{
			Schema: ownerPersistedQuerySchema, CanonicalOperationID: entry.CanonicalOperationID,
			ObjectID: objectID, Document: documentBase, OperationName: operationName,
			OperationType: "query", SHA256Hash: documentHash,
		})
		if marshalErr != nil {
			t.Fatal(marshalErr)
		}
		contractGraph.Documents = append(contractGraph.Documents, metadataast.SourceDocument{
			Path: ownerBindingPath, MediaType: "application/yaml", Content: ownerBinding,
		})
		contractGraph.Sources = append(contractGraph.Sources, metadataast.SourceDigest{
			Path: ownerDocumentPath, SHA256: documentHash,
		})
	}
	return generateWithSource(
		options,
		contractcodegen.NewSourceFromGraph("metadata", contractGraph),
	)
}

func writeMetadata(t *testing.T, root string, entries ...metadataEntry) string {
	t.Helper()
	encoded, err := json.MarshalIndent(metadataFile{
		Schema: metadataSchema, Entries: entries,
	}, "", "  ")
	if err != nil {
		t.Fatal(err)
	}
	return writeFixture(t, root, "query_metadata.json", string(encoded)+"\n")
}

func writeFixture(t *testing.T, root, relative, content string) string {
	t.Helper()
	path := filepath.Join(root, filepath.FromSlash(relative))
	if err := os.MkdirAll(filepath.Dir(path), 0o700); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(path, []byte(content), 0o600); err != nil {
		t.Fatal(err)
	}
	return path
}

func mustRelative(t *testing.T, base, path string) string {
	t.Helper()
	relative, err := filepath.Rel(base, path)
	if err != nil {
		t.Fatal(err)
	}
	return relative
}

func decodeRegistry(t *testing.T, encoded []byte) RegistryDocument {
	t.Helper()
	var registry RegistryDocument
	if err := json.Unmarshal(encoded, &registry); err != nil {
		t.Fatalf("decode registry: %v", err)
	}
	return registry
}

func digestCostPlan(t *testing.T, plan CostPlan) string {
	t.Helper()
	encoded, err := json.Marshal(plan)
	if err != nil {
		t.Fatal(err)
	}
	return digestWithPrefix(encoded)
}

func digestWithPrefix(encoded []byte) string {
	digest := sha256.Sum256(encoded)
	return "sha256:" + hex.EncodeToString(digest[:])
}

const detailSchema = `schema { query: Query }

directive @cost(weight: Int!) on FIELD_DEFINITION
directive @listCost(argument: String!, defaultValue: Int!, maximumValue: Int!) on FIELD_DEFINITION

type Query {
  contentPostDetail(postId: ID!): ContentPostDetail
}

type ContentPostDetail {
  postId: ID!
  contentType: String!
  title: String
  body: String
  summary: String
  authorId: ID
  authorDisplayName: String
  coverUrl: String
  status: String!
  visibility: String!
  createdAt: String!
  updatedAt: String!
}
`

const detailQuery = `query ContentPostDetail($postId: ID!) {
  contentPostDetail(postId: $postId) {
    postId
    contentType
    title
    body
    summary
    authorId
    authorDisplayName
    coverUrl
    status
    visibility
    createdAt
    updatedAt
  }
}
`

const abstractListSchema = `schema { query: Query }

directive @cost(weight: Int!) on FIELD_DEFINITION
directive @listCost(argument: String!, defaultValue: Int!, maximumValue: Int!) on FIELD_DEFINITION

interface Node { id: ID! }
type User implements Node { id: ID!, name: String! }
type Post implements Node { id: ID!, title: String! }
union SearchResult = User | Post
type Query {
  search(first: Int!): [SearchResult!]! @listCost(argument: "first", defaultValue: 2, maximumValue: 10)
}
`

const abstractListQuery = `query Search($first: Int! = 2, $includeNames: Boolean! = true) {
  results: search(first: $first) {
    __typename
    ...UserFields
    ... on Post {
      id
      headline: title
    }
  }
}

fragment UserFields on User {
  id
  displayName: name @include(if: $includeNames)
}
`

const deepSchema = `type Query { root: LevelOne! }
type LevelOne { child: LevelTwo! }
type LevelTwo { leaf: LevelThree! }
type LevelThree { value: String!, deeper: LevelFour! }
type LevelFour { final: LevelFive! }
type LevelFive { value: String! }
`
