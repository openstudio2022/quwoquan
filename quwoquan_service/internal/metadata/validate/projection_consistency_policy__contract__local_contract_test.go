package validate

import (
	"os"
	"path/filepath"
	"testing"
)

const esQueryProjectionStorageFixture = `backend: elasticsearch
role: projection
resources:
  search_documents:
    engine: elasticsearch
    role: query_projection
    required: true
`

// spec_ref: specs/feature-tree/global-search-experience/search-provider-routing-and-storage-topology/design.md#dec-002
// spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/design.md#dec-032
func TestProjectionConsistencyPolicyRequiredForElasticsearchQueryProjections(t *testing.T) {
	root := t.TempDir()
	objectPath := "search/search/search_index_view"
	writeObjectFixture(t, root, objectPath)
	writeStorageFixture(t, root, objectPath, esQueryProjectionStorageFixture)

	// 没有任何 projection 文档：必须报缺。
	issues, err := projectionConsistencyPolicyIssues(root)
	if err != nil {
		t.Fatal(err)
	}
	if !transactionScopeHasIssueCode(issues, "CONTRACT.PROJECTION.CONSISTENCY_POLICY_REQUIRED") {
		t.Fatalf("elasticsearch query projection without consistency_policy was accepted: %+v", issues)
	}

	// 有 read_model 但 policy 不完整（缺 delete_mode / rebuild_strategy）：仍然报缺。
	writeProjectionFixture(t, root, objectPath, "search_document.yaml", `read_model: SearchDocument
fields:
- {name: objectId, type: string}
consistency_policy:
  ordering_key: objectType:objectId
  source_version_field: sourceVersion
  apply_mode: strictly_newer
`)
	issues, err = projectionConsistencyPolicyIssues(root)
	if err != nil {
		t.Fatal(err)
	}
	if !transactionScopeHasIssueCode(issues, "CONTRACT.PROJECTION.CONSISTENCY_POLICY_REQUIRED") {
		t.Fatalf("incomplete consistency_policy was accepted: %+v", issues)
	}

	// 完整声明：通过。
	writeProjectionFixture(t, root, objectPath, "search_document.yaml", `read_model: SearchDocument
fields:
- {name: objectId, type: string}
consistency_policy:
  ordering_key: objectType:objectId
  source_version_field: sourceVersion
  apply_mode: strictly_newer
  delete_mode: versioned_tombstone
  rebuild_strategy: alias_replace
`)
	issues, err = projectionConsistencyPolicyIssues(root)
	if err != nil {
		t.Fatal(err)
	}
	if len(issues) != 0 {
		t.Fatalf("complete consistency_policy was rejected: %+v", issues)
	}
}

// spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/design.md#dec-032
func TestProjectionConsistencyPolicyNotRequiredWithoutElasticsearchQueryProjection(t *testing.T) {
	root := t.TempDir()
	objectPath := "content/content/comment"
	writeObjectFixture(t, root, objectPath)
	writeStorageFixture(t, root, objectPath, `backend: mongodb
role: authoritative
resources:
  comments_authority:
    engine: mongodb
    role: authority
    required: true
  comment_cache:
    engine: redis
    role: runtime
    required: true
collections:
  comments: {entity: Comment, role: authoritative}
`)
	writeProjectionFixture(t, root, objectPath, "comment_card.yaml", `read_model: CommentCard
fields:
- {name: commentId, type: string}
`)
	issues, err := projectionConsistencyPolicyIssues(root)
	if err != nil {
		t.Fatal(err)
	}
	if len(issues) != 0 {
		t.Fatalf("non-elasticsearch object must not require consistency_policy: %+v", issues)
	}
}

func writeObjectFixture(t *testing.T, root, objectPath string) {
	t.Helper()
	directory := filepath.Join(root, filepath.FromSlash(objectPath))
	if err := os.MkdirAll(directory, 0o755); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(directory, "object.yaml"), []byte("kind: projection\n"), 0o644); err != nil {
		t.Fatal(err)
	}
}

func writeProjectionFixture(t *testing.T, root, objectPath, filename, document string) {
	t.Helper()
	directory := filepath.Join(root, filepath.FromSlash(objectPath), "projections")
	if err := os.MkdirAll(directory, 0o755); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(directory, filename), []byte(document), 0o644); err != nil {
		t.Fatal(err)
	}
}
