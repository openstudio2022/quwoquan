// spec_ref: specs/feature-tree/discovery-content/spec.md#dom-001
package local_contract

import (
	"bytes"
	"crypto/sha256"
	"encoding/hex"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"testing"

	"gopkg.in/yaml.v3"
)

type persistedBundleBinding struct {
	CanonicalOperationID string `yaml:"canonicalOperationId"`
	ObjectID             string `yaml:"objectId"`
	Document             string `yaml:"document"`
	OperationName        string `yaml:"operationName"`
	OperationType        string `yaml:"operationType"`
	SHA256Hash           string `yaml:"sha256Hash"`
	AssemblyProjectionID string `yaml:"assemblyProjectionId"`
	AssemblyMappings     []struct {
		TargetField         string `yaml:"targetField"`
		PresenceSourceField string `yaml:"presenceSourceField"`
		Sources             []struct {
			SourceField string `yaml:"sourceField"`
			TargetKey   string `yaml:"targetKey"`
			Strategy    string `yaml:"strategy"`
		} `yaml:"sources"`
	} `yaml:"assemblyMappings"`
	AppClientBundle struct {
		BundleID                string   `yaml:"bundleId"`
		Role                    string   `yaml:"role"`
		SupportedContentTypes   []string `yaml:"supportedContentTypes"`
		RequiredForContentTypes []string `yaml:"requiredForContentTypes"`
	} `yaml:"appClientBundle"`
	RuntimeRequest struct {
		Method                  string `yaml:"method"`
		Path                    string `yaml:"path"`
		QueryText               string `yaml:"queryText"`
		OnlineRegistration      string `yaml:"onlineRegistration"`
		Mutation                string `yaml:"mutation"`
		ContractGraphHeader     string `yaml:"contractGraphHeader"`
		TrustedServicePrincipal struct {
			Subject string `yaml:"subject"`
			Scope   string `yaml:"scope"`
		} `yaml:"trustedServicePrincipal"`
	} `yaml:"runtimeRequest"`
}

func TestContentPostOwnsTypeAwarePersistedGraphQLBundle(t *testing.T) {
	serviceRoot := findServiceModuleRoot(t)
	ownerDir := filepath.Join(
		serviceRoot,
		"services/content-service/contracts/content/post/persisted_queries",
	)
	edgeDir := filepath.Join(
		serviceRoot,
		"services/api-edge/resources/policies/graphql_read/persisted_queries",
	)
	want := map[string]struct {
		canonicalID   string
		operationName string
		role          string
		contentTypes  []string
	}{
		"content_post_detail": {
			canonicalID:   "content.post.GetPost",
			operationName: "ContentPostDetailBase", role: "base",
			contentTypes: []string{"article", "image", "micro", "video"},
		},
		"content_post_detail_semantic": {
			canonicalID:   "content.post.GetPostSemantic",
			operationName: "ContentPostDetailSemantic", role: "extension",
			contentTypes: []string{"article", "image", "micro", "video"},
		},
		"content_post_detail_media": {
			canonicalID:   "content.post.GetPostMedia",
			operationName: "ContentPostDetailMedia", role: "extension",
			contentTypes: []string{"image", "video"},
		},
		"content_post_detail_article_render_assets": {
			canonicalID:   "content.post.GetPostArticleRenderAssets",
			operationName: "ContentPostDetailArticleRenderAssets", role: "extension",
			contentTypes: []string{"article"},
		},
		"content_post_detail_article_entities": {
			canonicalID:   "content.post.GetPostArticleEntities",
			operationName: "ContentPostDetailArticleEntities", role: "extension",
			contentTypes: []string{"article"},
		},
	}
	baseCount := 0
	canonicalIDs := map[string]struct{}{}
	for stem, expected := range want {
		documentName := stem + ".graphql"
		document, err := os.ReadFile(filepath.Join(ownerDir, documentName))
		if err != nil {
			t.Fatal(err)
		}
		sum := sha256.Sum256(document)
		digest := hex.EncodeToString(sum[:])
		bindingBytes, err := os.ReadFile(filepath.Join(ownerDir, stem+".yaml"))
		if err != nil {
			t.Fatal(err)
		}
		var binding persistedBundleBinding
		if err := yaml.Unmarshal(bindingBytes, &binding); err != nil {
			t.Fatal(err)
		}
		if binding.CanonicalOperationID != expected.canonicalID ||
			binding.ObjectID != "content.post" ||
			binding.Document != documentName ||
			binding.OperationName != expected.operationName ||
			binding.OperationType != "query" ||
			binding.SHA256Hash != digest ||
			binding.AssemblyProjectionID != "content.post.ContentPostDetailSlice" ||
			binding.AppClientBundle.BundleID != "content.post.ContentPostDetail" ||
			binding.AppClientBundle.Role != expected.role ||
			binding.RuntimeRequest.Method != "POST" ||
			binding.RuntimeRequest.Path != "/internal/graphql" ||
			binding.RuntimeRequest.QueryText != "forbidden" ||
			binding.RuntimeRequest.OnlineRegistration != "forbidden" ||
			binding.RuntimeRequest.Mutation != "forbidden" ||
			binding.RuntimeRequest.ContractGraphHeader != "X-Contract-Graph-SHA256" ||
			binding.RuntimeRequest.TrustedServicePrincipal.Subject != "service:api-edge" ||
			binding.RuntimeRequest.TrustedServicePrincipal.Scope != "content.post.graphql.read" {
			t.Fatalf("owner persisted binding %s drifted: %+v", stem, binding)
		}
		if _, duplicate := canonicalIDs[binding.CanonicalOperationID]; duplicate {
			t.Fatalf("bundle reuses canonicalOperationId %q", binding.CanonicalOperationID)
		}
		canonicalIDs[binding.CanonicalOperationID] = struct{}{}
		if binding.AppClientBundle.Role == "base" {
			baseCount++
			if len(binding.AppClientBundle.RequiredForContentTypes) != 0 {
				t.Fatalf("base %s must not declare requiredForContentTypes", stem)
			}
			assertSortedEqual(t, binding.AppClientBundle.SupportedContentTypes, expected.contentTypes)
		} else {
			if len(binding.AppClientBundle.SupportedContentTypes) != 0 {
				t.Fatalf("extension %s must not declare supportedContentTypes", stem)
			}
			assertSortedEqual(t, binding.AppClientBundle.RequiredForContentTypes, expected.contentTypes)
		}
		edgeDocument, err := os.ReadFile(filepath.Join(edgeDir, documentName))
		if err != nil {
			t.Fatal(err)
		}
		if !bytes.Equal(edgeDocument, document) {
			t.Fatalf("API Edge document %s must equal object-owned source", documentName)
		}
	}
	if baseCount != 1 {
		t.Fatalf("bundle base count=%d want=1", baseCount)
	}
}

func TestContentPostOwnsGraphQLOperationsWithoutInventingRESTRoutes(t *testing.T) {
	serviceRoot := findServiceModuleRoot(t)
	operationsPath := filepath.Join(
		serviceRoot,
		"services/content-service/contracts/content/post/operations.yaml",
	)
	bytes, err := os.ReadFile(operationsPath)
	if err != nil {
		t.Fatal(err)
	}
	var document struct {
		GraphQLQueries []struct {
			Operation      string `yaml:"operation"`
			OperationType  string `yaml:"operation_type"`
			ResponseEntity string `yaml:"response_entity"`
			Authorization  struct {
				Principal       string `yaml:"principal"`
				OwnershipPolicy string `yaml:"ownership_policy"`
			} `yaml:"authorization"`
			Commercial struct {
				Status string `yaml:"status"`
			} `yaml:"commercial"`
		} `yaml:"graphql_queries"`
	}
	if err := yaml.Unmarshal(bytes, &document); err != nil {
		t.Fatal(err)
	}
	want := map[string]struct{}{
		"GetPostSemantic": {}, "GetPostMedia": {},
		"GetPostArticleRenderAssets": {}, "GetPostArticleEntities": {},
	}
	if len(document.GraphQLQueries) != len(want) {
		t.Fatalf("graphql_queries=%d want=%d", len(document.GraphQLQueries), len(want))
	}
	for _, query := range document.GraphQLQueries {
		if _, ok := want[query.Operation]; !ok {
			t.Fatalf("unexpected GraphQL operation %q", query.Operation)
		}
		if query.OperationType != "query" || query.ResponseEntity != "ContentPostDetailSlice" ||
			query.Authorization.Principal != "public" || query.Authorization.OwnershipPolicy != "visibility_filtered" ||
			query.Commercial.Status != "ready" {
			t.Fatalf("GraphQL operation %s drifted: %+v", query.Operation, query)
		}
		delete(want, query.Operation)
	}
	if len(want) != 0 {
		t.Fatalf("missing GraphQL operations: %v", want)
	}
}

func TestContentPostGraphQLOperationsOwnExactErrorEmissions(t *testing.T) {
	serviceRoot := findServiceModuleRoot(t)
	bytes, err := os.ReadFile(filepath.Join(
		serviceRoot,
		"services/content-service/contracts/content/post/errors.yaml",
	))
	if err != nil {
		t.Fatal(err)
	}
	var document struct {
		Errors []struct {
			Code      string `yaml:"code"`
			EmittedBy []struct {
				Surface    string   `yaml:"surface"`
				Operations []string `yaml:"operations"`
			} `yaml:"emitted_by"`
		} `yaml:"errors"`
	}
	if err := yaml.Unmarshal(bytes, &document); err != nil {
		t.Fatal(err)
	}
	wantCodes := map[string]struct{}{
		"CONTENT.USER.content_deleted": {}, "CONTENT.USER.post_not_found": {},
		"CONTENT.USER.invalid_argument": {}, "CONTENT.SYSTEM.storage_read_failed": {},
		"CONTENT.SYSTEM.internal_error": {},
	}
	wantOperations := []string{
		"GetPostSemantic", "GetPostMedia", "GetPostArticleRenderAssets", "GetPostArticleEntities",
	}
	for _, entry := range document.Errors {
		if _, ok := wantCodes[entry.Code]; !ok {
			continue
		}
		graphqlCount := 0
		for _, emission := range entry.EmittedBy {
			if emission.Surface != "graphql" {
				continue
			}
			graphqlCount++
			assertSortedEqual(t, emission.Operations, wantOperations)
		}
		if graphqlCount != 1 {
			t.Fatalf("error %s graphql emission count=%d", entry.Code, graphqlCount)
		}
		delete(wantCodes, entry.Code)
	}
	if len(wantCodes) != 0 {
		t.Fatalf("missing GraphQL error emissions: %v", wantCodes)
	}
}

func TestContentPostBundleOwnsOnlyNonIdentityAssemblyMappings(t *testing.T) {
	serviceRoot := findServiceModuleRoot(t)
	ownerDir := filepath.Join(
		serviceRoot,
		"services/content-service/contracts/content/post/persisted_queries",
	)
	for _, stem := range []string{
		"content_post_detail",
		"content_post_detail_semantic",
		"content_post_detail_media",
		"content_post_detail_article_entities",
	} {
		bindingBytes, err := os.ReadFile(filepath.Join(ownerDir, stem+".yaml"))
		if err != nil {
			t.Fatal(err)
		}
		var binding persistedBundleBinding
		if err := yaml.Unmarshal(bindingBytes, &binding); err != nil {
			t.Fatal(err)
		}
		if len(binding.AssemblyMappings) != 0 {
			t.Fatalf("identity-mapped slice %s declares mappings=%v", stem, binding.AssemblyMappings)
		}
	}
	bindingBytes, err := os.ReadFile(filepath.Join(
		ownerDir, "content_post_detail_article_render_assets.yaml",
	))
	if err != nil {
		t.Fatal(err)
	}
	var binding persistedBundleBinding
	if err := yaml.Unmarshal(bindingBytes, &binding); err != nil {
		t.Fatal(err)
	}
	if len(binding.AssemblyMappings) != 2 {
		t.Fatalf("assemblyMappings=%v", binding.AssemblyMappings)
	}
	manifest := binding.AssemblyMappings[0]
	if manifest.TargetField != "articleAssetManifest" ||
		manifest.PresenceSourceField != "articleAssetManifestSummary" || len(manifest.Sources) != 2 ||
		manifest.Sources[0].SourceField != "articleAssetManifestSummary" ||
		manifest.Sources[0].Strategy != "merge_object" ||
		manifest.Sources[1].SourceField != "articleAssets" ||
		manifest.Sources[1].TargetKey != "assets" ||
		manifest.Sources[1].Strategy != "assign_key" {
		t.Fatalf("manifest assembly mapping=%+v", manifest)
	}
	render := binding.AssemblyMappings[1]
	if render.TargetField != "articleRenderProfile" || len(render.Sources) != 1 ||
		render.Sources[0].SourceField != "articleRenderProfileSummary" ||
		render.Sources[0].Strategy != "replace" {
		t.Fatalf("render assembly mapping=%+v", render)
	}
}

func TestArticleAssetAssemblyUsesExactNonNullListTypes(t *testing.T) {
	serviceRoot := findServiceModuleRoot(t)
	schema, err := os.ReadFile(filepath.Join(
		serviceRoot,
		"services/api-edge/resources/policies/graphql_read/schema.graphqls",
	))
	if err != nil {
		t.Fatal(err)
	}
	text := string(schema)
	for _, declaration := range []string{
		"articleAssets(first: Int!): [PostArticleAsset!]!",
		"assets: [PostArticleAsset!]!",
	} {
		if !strings.Contains(text, declaration) {
			t.Fatalf("GraphQL assembly schema is missing exact type %q", declaration)
		}
	}
}

func assertSortedEqual(t *testing.T, got []string, want []string) {
	t.Helper()
	gotCopy := append([]string(nil), got...)
	wantCopy := append([]string(nil), want...)
	sort.Strings(gotCopy)
	sort.Strings(wantCopy)
	if len(gotCopy) != len(wantCopy) {
		t.Fatalf("content types=%v want=%v", got, want)
	}
	for index := range wantCopy {
		if gotCopy[index] != wantCopy[index] {
			t.Fatalf("content types=%v want=%v", got, want)
		}
	}
}

func findServiceModuleRoot(t *testing.T) string {
	t.Helper()
	directory, err := os.Getwd()
	if err != nil {
		t.Fatal(err)
	}
	for {
		if _, err := os.Stat(filepath.Join(directory, "go.mod")); err == nil {
			return directory
		}
		parent := filepath.Dir(directory)
		if parent == directory {
			t.Fatal("quwoquan_service module root not found")
		}
		directory = parent
	}
}
