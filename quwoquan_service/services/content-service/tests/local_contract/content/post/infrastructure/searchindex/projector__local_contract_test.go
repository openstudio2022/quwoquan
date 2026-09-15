package searchindex_test

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

// spec_ref: specs/feature-tree/global-search-experience/search-provider-routing-and-storage-topology/canonical-search-contract/spec.md#gwt-004
// 原普通Post写入正负例迁入Search真实durable/ES集成测试，此处锁定旧生产轨不存在。
func TestOrdinaryPostSearchWriterRetired(t *testing.T) {
	root := filepath.Join("..", "..", "..", "..", "..", "..")
	for _, file := range []string{"projector.go", "backfill.go"} {
		path := filepath.Join(root, "internal/content/post/infrastructure/searchindex", file)
		if _, err := os.Stat(path); !os.IsNotExist(err) {
			t.Fatalf("retired writer exists or unreadable %s: %v", path, err)
		}
	}
	source, err := os.ReadFile(filepath.Join(root, "cmd/api/composition_root.go"))
	if err != nil {
		t.Fatal(err)
	}
	if strings.Contains(string(source), "content-search-projection") || strings.Contains(string(source), "searchBuilt.Projector") {
		t.Fatal("ordinary writer relay remains")
	}
	for _, legal := range []string{"placeindex.NewProjector", "accountclosure.NewSearchIndexerDeleter", "content-post-lifecycle-stream"} {
		if !strings.Contains(string(source), legal) {
			t.Fatal("legal binding/relay removed", legal)
		}
	}
}
