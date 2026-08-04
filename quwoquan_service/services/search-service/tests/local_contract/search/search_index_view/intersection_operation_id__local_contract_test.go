package local_contract

import (
	"os"
	"path/filepath"
	"runtime"
	"strings"
	"testing"
)

func TestSearchIntersectionClientUsesCanonicalOperationID(t *testing.T) {
	_, file, _, ok := runtime.Caller(0)
	if !ok {
		t.Fatal("runtime.Caller failed")
	}
	// tests/local_contract/search/search_index_view -> search-service root
	clientPath := filepath.Clean(filepath.Join(
		filepath.Dir(file),
		"..",
		"..",
		"..",
		"..",
		"internal",
		"search",
		"search_index_view",
		"infrastructure",
		"intersectionclient",
		"client.go",
	))
	source, err := os.ReadFile(clientPath)
	if err != nil {
		t.Fatalf("read intersection client: %v", err)
	}
	content := string(source)
	if !strings.Contains(
		content,
		`getObjectIntersectionsOperation = "content.intersection_visit_state.GetObjectIntersections"`,
	) {
		t.Fatal("search intersection client must use canonical content.intersection_visit_state.GetObjectIntersections")
	}
	if strings.Contains(content, `"content.post.GetObjectIntersections"`) {
		t.Fatal("stale content.post.GetObjectIntersections must not remain in search intersection client")
	}
}
