package local_contract

import (
	"os"
	"path/filepath"
	"testing"
)

func TestChatServicePhysicalTestDirectoryLayout(t *testing.T) {
	root := filepath.Clean("../../../../../../../")
	retiredPaths := []string{
		"quwoquan_service/services/chat-service/tests/group_avatar_sync_contract_test.go",
	}
	for _, rel := range retiredPaths {
		if _, err := os.Stat(filepath.Join(root, rel)); !os.IsNotExist(err) {
			t.Fatalf("retired flat test path must not exist %q: %v", rel, err)
		}
	}
	canonicalPaths := []string{
		"quwoquan_service/services/chat-service/tests/local_contract/chat/conversation/test_directory_inventory__local_contract_test.go",
		"quwoquan_service/services/chat-service/tests/api_integration/chat/conversation/group_avatar_sync_contract__api_integration_test.go",
	}
	for _, rel := range canonicalPaths {
		if _, err := os.Stat(filepath.Join(root, rel)); err != nil {
			t.Fatalf("canonical test missing on disk %q: %v", rel, err)
		}
	}
}
