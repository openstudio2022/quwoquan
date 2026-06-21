package api_integration

import (
	"os/exec"
	"testing"
)

func TestChatServiceGroupAvatarSyncApiIntegration(t *testing.T) {
	cmd := exec.Command(
		"go",
		"test",
		"..",
		"-run",
		"^TestGroupAvatar_RecomputePublishesConversationAvatarPatch$",
		"-count=1",
	)
	output, err := cmd.CombinedOutput()
	if err != nil {
		t.Fatalf("legacy chat-service group avatar sync api integration failed: %v\n%s", err, output)
	}
}
