package local_contract

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestChatServiceTestDirectoryInventory(t *testing.T) {
	root := filepath.Clean("../../../../../")
	inventoryPath := filepath.Join(root, "specs/gates/test_directory_inventory.yaml")
	payload, err := os.ReadFile(inventoryPath)
	if err != nil {
		t.Fatalf("read test directory inventory: %v", err)
	}
	text := string(payload)
	sourcePaths := []string{
		"quwoquan_service/services/chat-service/tests/group_avatar_sync_contract_test.go",
	}
	for _, token := range sourcePaths {
		if !strings.Contains(text, token) {
			t.Fatalf("inventory missing source path %q", token)
		}
	}
	canonicalPaths := []string{
		"quwoquan_service/services/chat-service/tests/local_contract/test_directory_inventory__local_contract_test.go",
		"quwoquan_service/services/chat-service/tests/api_integration/group_avatar_sync_contract__api_integration_test.go",
	}
	for _, rel := range canonicalPaths {
		if _, err := os.Stat(filepath.Join(root, rel)); err != nil {
			t.Fatalf("canonical test missing on disk %q: %v", rel, err)
		}
	}
}
