package validate

import (
	"os"
	"path/filepath"
	"testing"

	"quwoquan_service/internal/metadata/ast"
	"quwoquan_service/internal/metadata/graph"
)

func TestCommercialProfileRejectsStaleAndOrphanOpenAPISnapshots(t *testing.T) {
	metadataDir := t.TempDir()
	contractGraph := &graph.ContractGraph{
		Operations: []ast.Operation{
			{
				ID:           "content.post.GetPost",
				LocalID:      "GetPost",
				Domain:       "content",
				ObjectID:     "content.post",
				Method:       "GET",
				PathTemplate: "/content/posts/{postId}",
				SourcePath:   "content/post/service.yaml",
				Kind:         ast.OperationKindQuery,
			},
		},
	}
	for _, relativePath := range []string{
		"content/openapi.yaml",
		"unexpected/openapi.yaml",
	} {
		target := filepath.Join(metadataDir, filepath.FromSlash(relativePath))
		if err := os.MkdirAll(filepath.Dir(target), 0o755); err != nil {
			t.Fatalf("mkdir %s: %v", relativePath, err)
		}
		if err := os.WriteFile(
			target,
			[]byte("openapi: 3.0.3\npaths: {}\n"),
			0o644,
		); err != nil {
			t.Fatalf("write %s: %v", relativePath, err)
		}
	}

	issues := validateOpenAPISnapshots(contractGraph, metadataDir)

	assertIssueCode(t, issues, "CONTRACT.OPENAPI.STALE_SNAPSHOT")
	assertIssueCode(t, issues, "CONTRACT.OPENAPI.ORPHAN_SNAPSHOT")
}

func assertIssueCode(t *testing.T, issues []Issue, code string) {
	t.Helper()
	for _, current := range issues {
		if current.Code == code {
			return
		}
	}
	t.Fatalf("missing issue %s: %+v", code, issues)
}
