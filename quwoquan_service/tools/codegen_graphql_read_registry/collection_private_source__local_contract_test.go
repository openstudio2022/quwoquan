package main

// spec_ref: specs/feature-tree/runtime/runtime-control-plane-foundation/domain-onboarding-acceptance-governance/spec.md#gwt-005.t1
// spec_ref: specs/feature-tree/discovery-content/publish-comment-reaction/ordered-post-collection/spec.md#gwt-002.t1
import (
	"encoding/json"
	"os"
	"path/filepath"
	metadataast "quwoquan_service/internal/metadata/ast"
	codegen "quwoquan_service/internal/metadata/codegen"
	"quwoquan_service/internal/metadata/validate"
	"quwoquan_service/internal/testsupport/contractsview"
	"strings"
	"testing"
)

func TestCollectionPrivateReadySourceDoesNotPromoteRealBlocked(t *testing.T) {
	metadataDir := contractsview.Build(t)
	source, e := codegen.NewSource(metadataDir, validate.ProfileBaseline)
	if e != nil {
		t.Fatal(e)
	}
	repo, e := filepath.Abs("../..")
	if e != nil {
		t.Fatal(e)
	}
	root := t.TempDir()
	schema, e := os.ReadFile(filepath.Join(repo, "services/api-edge/resources/policies/graphql_read/schema.graphqls"))
	if e != nil {
		t.Fatal(e)
	}
	if e = os.WriteFile(filepath.Join(root, "schema.graphqls"), schema, 0600); e != nil {
		t.Fatal(e)
	}
	entries := []metadataEntry{}
	for _, pair := range [][2]string{{"GetPostCollection", "post_collection"}, {"GetPostCollectionManagement", "post_collection_management"}} {
		name := pair[1] + ".graphql"
		document, e := os.ReadFile(filepath.Join(repo, "services/content-service/contracts/content/post_collection/persisted_queries", name))
		if e != nil {
			t.Fatal(e)
		}
		if e = os.WriteFile(filepath.Join(root, name), document, 0600); e != nil {
			t.Fatal(e)
		}
		entries = append(entries, metadataEntry{Document: name, CanonicalOperationID: "content.post_collection." + pair[0], QueryClass: "page_composite", VariablesMaxBytes: 2048, MaxOwnerCalls: 3, MaxBatchKeys: 1, MaxResponseBytes: 262144, SLORef: "slo:gateway.graphql_read.detail", ExecutorKey: "content.postCollection.query"})
	}
	raw, _ := json.Marshal(metadataFile{Schema: metadataSchema, Entries: entries})
	if e = os.WriteFile(filepath.Join(root, "metadata.json"), raw, 0600); e != nil {
		t.Fatal(e)
	}
	original := map[string]string{}
	for i := range source.Graph().Operations {
		op := &source.Graph().Operations[i]
		if op.ObjectID == "content.post_collection" && op.Kind == metadataast.OperationKindQuery {
			original[op.ID] = op.Commercial.Status
			op.Commercial.Status = "blocked"
			op.Commercial.Explicit = true
		}
	}
	options := Options{MetadataDir: metadataDir, MetadataPath: filepath.Join(root, "metadata.json"), SchemaPath: filepath.Join(root, "schema.graphqls"), CandidateDigest: testCandidateDigest}
	if _, e = generateWithSource(options, source); e == nil || !strings.Contains(e.Error(), "commercial ready") {
		t.Fatalf("real blocked source not rejected: %v", e)
	}
	for i := range source.Graph().Operations {
		op := &source.Graph().Operations[i]
		if op.ObjectID == "content.post_collection" && op.Kind == metadataast.OperationKindQuery {
			op.Commercial.Status = "ready"
			op.Commercial.Explicit = true
		}
	}
	generated, e := generateWithSource(options, source)
	if e != nil {
		t.Fatal(e)
	}
	var registry struct {
		Entries []RegistryEntry `json:"entries"`
	}
	if e = json.Unmarshal(generated, &registry); e != nil {
		t.Fatal(e)
	}
	if len(registry.Entries) != 2 {
		t.Fatal("private source did not generate both queries")
	}
	real, e := codegen.NewSource(metadataDir, validate.ProfileBaseline)
	if e != nil {
		t.Fatal(e)
	}
	for _, op := range real.Graph().Operations {
		if op.ObjectID == "content.post_collection" && op.Kind == metadataast.OperationKindQuery && op.Commercial.Status != original[op.ID] {
			t.Fatal("private ready fixture promoted real source")
		}
	}
}
