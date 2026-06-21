package local_contract

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestUserServiceTestDirectoryInventory(t *testing.T) {
	root := filepath.Clean("../../../../../")
	inventoryPath := filepath.Join(root, "specs/gates/test_directory_inventory.yaml")
	payload, err := os.ReadFile(inventoryPath)
	if err != nil {
		t.Fatalf("read test directory inventory: %v", err)
	}
	text := string(payload)
	legacyPaths := []string{
		"quwoquan_service/services/user-service/tests/auth_contract_test.go",
	}
	for _, token := range legacyPaths {
		if !strings.Contains(text, token) {
			t.Fatalf("inventory missing legacy path %q", token)
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
