package api_integration

import (
	"os/exec"
	"testing"
)

func TestUserServiceAuthDefaultNicknameApiIntegration(t *testing.T) {
	cmd := exec.Command(
		"go",
		"test",
		"..",
		"-run",
		"^TestAuth_FirstLogin_UsesCloudDefaultNicknamePattern$",
		"-count=1",
	)
	output, err := cmd.CombinedOutput()
	if err != nil {
		t.Fatalf("legacy user-service auth api integration failed: %v\n%s", err, output)
	}
}
