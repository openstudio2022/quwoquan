// spec_ref: specs/feature-tree/gateway-orchestrator-foundation/spec.md#dom-001
package main

import (
	"path/filepath"
	"strings"
	"testing"

	"github.com/vektah/gqlparser/v2"
	"github.com/vektah/gqlparser/v2/ast"
)

func TestGeneratorRejectsDuplicateOperationNameAcrossPersistedDocuments(t *testing.T) {
	t.Parallel()
	root := t.TempDir()
	schemaPath := writeFixture(t, root, "schema.graphqls", detailSchema)
	first := writeFixture(t, root, "queries/base.graphql", detailQuery)
	second := writeFixture(t, root, "queries/extension.graphql", detailQuery+"\n")
	metadataPath := writeMetadata(t, root,
		metadataEntry{Document: filepath.ToSlash(mustRelative(t, root, first)), CanonicalOperationID: "content.post.GetPost", QueryClass: "detail", VariablesMaxBytes: 1024, MaxOwnerCalls: 1, MaxBatchKeys: 1, MaxResponseBytes: 65536, SLORef: "slo:gateway.graphql_read.detail", ExecutorKey: "content.post.getPost"},
		metadataEntry{Document: filepath.ToSlash(mustRelative(t, root, second)), CanonicalOperationID: "content.post.GetPostSemantic", QueryClass: "detail", VariablesMaxBytes: 1024, MaxOwnerCalls: 1, MaxBatchKeys: 1, MaxResponseBytes: 65536, SLORef: "slo:gateway.graphql_read.detail", ExecutorKey: "content.post.getPost"},
	)
	_, err := generateForTest(t, Options{SchemaPath: schemaPath, MetadataPath: metadataPath, CandidateDigest: testCandidateDigest})
	if err == nil || !strings.Contains(err.Error(), "duplicate operationName") {
		t.Fatalf("duplicate operation name error=%v", err)
	}
}

func TestAppClientBundleIsProjectedFromOwnerBindingAndAST(t *testing.T) {
	t.Parallel()
	schema, err := gqlparser.LoadSchema(&ast.Source{Name: "bundle.graphqls", Input: bundleSchema})
	if err != nil {
		t.Fatal(err)
	}
	document, queryErrors := gqlparser.LoadQuery(schema, bundleArticleQuery)
	if queryErrors != nil {
		t.Fatal(queryErrors)
	}
	owner := ownerPersistedQueryBinding{
		AssemblyProjectionID: "content.post.ContentPostDetailSlice",
		AppClientBundle: &ownerAppClientBundle{
			BundleID: "content.post.ContentPostDetail", Role: "extension",
			RequiredForContentTypes: []string{"article"},
		},
		AssemblyMappings: []AssemblyMapping{{
			TargetField:         "articleAssetManifest",
			PresenceSourceField: "articleAssetManifestSummary",
			Sources: []AssemblySource{
				{SourceField: "articleAssetManifestSummary", Strategy: "merge_object"},
				{SourceField: "articleAssets", Strategy: "assign_key", TargetKey: "assets"},
			},
		}, {
			TargetField: "articleRenderProfile",
			Sources:     []AssemblySource{{SourceField: "articleRenderProfileSummary", Strategy: "replace"}},
		}},
	}
	bundle, err := projectAppClientBundle(schema, document, document.Operations[0], owner)
	if err != nil {
		t.Fatalf("projectAppClientBundle: %v", err)
	}
	if bundle == nil || bundle.BundleID != "content.post.ContentPostDetail" || bundle.Role != "extension" {
		t.Fatalf("bundle=%+v", bundle)
	}
	wantFields := "articleAssetManifestSummary,articleAssets,articleRenderProfileSummary,contentType,postId"
	if strings.Join(bundle.SelectedFields, ",") != wantFields {
		t.Fatalf("selectedFields=%v", bundle.SelectedFields)
	}
}

func TestAppClientBundleRejectsInvalidAssemblyTypesAndBundleSet(t *testing.T) {
	t.Parallel()
	schema, err := gqlparser.LoadSchema(&ast.Source{Name: "bundle.graphqls", Input: bundleSchema})
	if err != nil {
		t.Fatal(err)
	}
	document, queryErrors := gqlparser.LoadQuery(schema, bundleArticleQuery)
	if queryErrors != nil {
		t.Fatal(queryErrors)
	}
	validOwner := ownerPersistedQueryBinding{
		AssemblyProjectionID: "content.post.ContentPostDetailSlice",
		AppClientBundle: &ownerAppClientBundle{
			BundleID: "content.post.ContentPostDetail", Role: "extension",
			RequiredForContentTypes: []string{"article"},
		},
		AssemblyMappings: []AssemblyMapping{{
			TargetField:         "articleAssetManifest",
			PresenceSourceField: "articleAssetManifestSummary",
			Sources: []AssemblySource{
				{SourceField: "articleAssetManifestSummary", Strategy: "merge_object"},
				{SourceField: "articleAssets", Strategy: "assign_key", TargetKey: "assets"},
			},
		}},
	}

	wrongType := validOwner
	wrongType.AssemblyMappings = []AssemblyMapping{{
		TargetField: "articleRenderProfile",
		Sources:     []AssemblySource{{SourceField: "articleAssetManifestSummary", Strategy: "replace"}},
	}}
	if _, err := projectAppClientBundle(schema, document, document.Operations[0], wrongType); err == nil ||
		!strings.Contains(err.Error(), "exact type") {
		t.Fatalf("wrong replace type error=%v", err)
	}

	wrongPresence := validOwner
	wrongPresence.AssemblyMappings = append([]AssemblyMapping(nil), validOwner.AssemblyMappings...)
	wrongPresence.AssemblyMappings[0].PresenceSourceField = "articleAssets"
	if _, err := projectAppClientBundle(schema, document, document.Operations[0], wrongPresence); err == nil ||
		!strings.Contains(err.Error(), "nullable object") {
		t.Fatalf("wrong presence type error=%v", err)
	}

	entries := []RegistryEntry{
		{OperationName: "Base", AppClientBundle: &AppClientBundle{
			BundleID: "content.post.ContentPostDetail", Role: "base",
			SupportedContentTypes: []string{"article", "image"},
			SelectedFields:        []string{"contentType", "postId"}, AssemblyMappings: []AssemblyMapping{},
		}},
		{OperationName: "Article", AppClientBundle: &AppClientBundle{
			BundleID: "content.post.ContentPostDetail", Role: "extension",
			RequiredForContentTypes: []string{"article"},
			SelectedFields:          []string{"articleAssetManifestSummary", "articleAssets"},
			AssemblyMappings:        validOwner.AssemblyMappings,
		}},
	}
	if err := validateRegistryBundles(entries); err != nil {
		t.Fatalf("valid bundle set: %v", err)
	}

	twoBases := append([]RegistryEntry(nil), entries...)
	twoBases[1].AppClientBundle = cloneAppClientBundle(entries[0].AppClientBundle)
	if err := validateRegistryBundles(twoBases); err == nil || !strings.Contains(err.Error(), "exactly one base") {
		t.Fatalf("two base error=%v", err)
	}

	outside := append([]RegistryEntry(nil), entries...)
	outside[1].AppClientBundle = cloneAppClientBundle(entries[1].AppClientBundle)
	outside[1].AppClientBundle.RequiredForContentTypes = []string{"video"}
	if err := validateRegistryBundles(outside); err == nil || !strings.Contains(err.Error(), "outside") {
		t.Fatalf("outside content type error=%v", err)
	}
}

const bundleSchema = `schema { query: Query }
type Query { article(postId: ID!): ArticleSlice }
type ArticleSlice {
  postId: ID!
  contentType: String!
  articleAssetManifestSummary: ManifestSummary
  articleAssets: [Asset!]!
  articleRenderProfileSummary: RenderProfile
}
type ManifestSummary { schema: String!, documentSha256: String! }
type Manifest { schema: String!, documentSha256: String!, assets: [Asset!]! }
type Asset { id: ID! }
type RenderProfile { template: String }
type ContentPostDetailSlice {
  postId: ID!
  contentType: String!
  articleAssetManifest: Manifest
  articleRenderProfile: RenderProfile
}
`

const bundleArticleQuery = `query Article($postId: ID!) {
  article(postId: $postId) {
    postId
    contentType
    articleAssetManifestSummary { schema documentSha256 }
    articleAssets { id }
    articleRenderProfileSummary { template }
  }
}
`
