package local_contract

import (
	"io/fs"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestContentServicePhysicalTestDirectoryLayout(t *testing.T) {
	root := filepath.Dir(quwoquanServiceRoot(t))
	retiredPaths := []string{
		"quwoquan_service/services/content-service/tests/post_crud_contract_test.go",
	}
	for _, rel := range retiredPaths {
		if _, err := os.Stat(filepath.Join(root, rel)); !os.IsNotExist(err) {
			t.Fatalf("retired flat test path must not exist %q: %v", rel, err)
		}
	}
	for _, rel := range []string{
		"quwoquan_service/services/content-service/internal",
		"quwoquan_service/services/content-service/cmd",
	} {
		err := filepath.WalkDir(filepath.Join(root, rel), func(
			path string,
			entry fs.DirEntry,
			walkErr error,
		) error {
			if walkErr != nil {
				return walkErr
			}
			if !entry.IsDir() && strings.HasSuffix(entry.Name(), "_test.go") {
				t.Errorf("business test must be under tests/, found %q", path)
			}
			return nil
		})
		if err != nil {
			t.Fatalf("scan retired test root %q: %v", rel, err)
		}
	}
	canonicalPaths := []string{
		"quwoquan_service/services/content-service/tests/local_contract/content/post/test_directory_inventory__local_contract_test.go",
		"quwoquan_service/services/content-service/tests/api_integration/content/post/post_crud_contract__api_integration_test.go",
		"quwoquan_service/services/content-service/tests/local_contract/content/post/application/post_publication__local_contract_test.go",
	}
	for _, rel := range canonicalPaths {
		if _, err := os.Stat(filepath.Join(root, rel)); err != nil {
			t.Fatalf("canonical test missing on disk %q: %v", rel, err)
		}
	}
}

func quwoquanServiceRoot(t *testing.T) string {
	t.Helper()
	dir, err := os.Getwd()
	if err != nil {
		t.Fatal(err)
	}
	for {
		if _, statErr := os.Stat(filepath.Join(dir, "go.mod")); statErr == nil {
			if _, metadataErr := os.Stat(filepath.Join(dir, "contracts/metadata")); metadataErr == nil {
				return dir
			}
		}
		parent := filepath.Dir(dir)
		if parent == dir {
			t.Fatal("quwoquan_service root not found above test directory")
		}
		dir = parent
	}
}
