package local_contract

import (
	"os"
	"path/filepath"
	"testing"
)

func TestUserServicePhysicalTestDirectoryLayout(t *testing.T) {
	root := filepath.Clean("../../../../../")
	retiredPaths := []string{
		"quwoquan_service/services/user-service/tests/auth_contract_test.go",
	}
	for _, rel := range retiredPaths {
		if _, err := os.Stat(filepath.Join(root, rel)); !os.IsNotExist(err) {
			t.Fatalf("retired flat test path must not exist %q: %v", rel, err)
		}
	}
	canonicalPaths := []string{
		"quwoquan_service/services/user-service/tests/local_contract/test_directory_inventory__local_contract_test.go",
		"quwoquan_service/services/user-service/tests/api_integration/auth_contract__api_integration_test.go",
	}
	for _, rel := range canonicalPaths {
		if _, err := os.Stat(filepath.Join(root, rel)); err != nil {
			t.Fatalf("canonical test missing on disk %q: %v", rel, err)
		}
	}
}
