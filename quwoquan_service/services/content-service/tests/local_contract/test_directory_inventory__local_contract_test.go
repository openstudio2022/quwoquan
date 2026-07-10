package local_contract

import (
	"os"
	"path/filepath"
	"testing"
)

func TestContentServicePhysicalTestDirectoryLayout(t *testing.T) {
	root := filepath.Clean("../../../../../")
	retiredPaths := []string{
		"quwoquan_service/services/content-service/tests/post_crud_contract_test.go",
	}
	for _, rel := range retiredPaths {
		if _, err := os.Stat(filepath.Join(root, rel)); !os.IsNotExist(err) {
			t.Fatalf("retired flat test path must not exist %q: %v", rel, err)
		}
	}
	canonicalPaths := []string{
		"quwoquan_service/services/content-service/tests/local_contract/test_directory_inventory__local_contract_test.go",
		"quwoquan_service/services/content-service/tests/api_integration/post_crud_contract__api_integration_test.go",
	}
	for _, rel := range canonicalPaths {
		if _, err := os.Stat(filepath.Join(root, rel)); err != nil {
			t.Fatalf("canonical test missing on disk %q: %v", rel, err)
		}
	}
}
