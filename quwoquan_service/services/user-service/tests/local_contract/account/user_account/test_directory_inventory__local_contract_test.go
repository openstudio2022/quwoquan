package local_contract

import (
	"os"
	"path/filepath"
	"testing"
)

func TestUserServicePhysicalTestDirectoryLayout(t *testing.T) {
	retiredPaths := []string{
		"../../../auth_contract_test.go",
	}
	for _, rel := range retiredPaths {
		if _, err := os.Stat(filepath.Clean(rel)); !os.IsNotExist(err) {
			t.Fatalf("retired flat test path must not exist %q: %v", rel, err)
		}
	}
	canonicalPaths := []string{
		"test_directory_inventory__local_contract_test.go",
		"../../../api_integration/account/user_account/auth_contract__api_integration_test.go",
	}
	for _, rel := range canonicalPaths {
		if _, err := os.Stat(filepath.Clean(rel)); err != nil {
			t.Fatalf("canonical test missing on disk %q: %v", rel, err)
		}
	}
}
