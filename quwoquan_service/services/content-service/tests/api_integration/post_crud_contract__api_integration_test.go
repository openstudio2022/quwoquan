package api_integration

import (
	"os/exec"
	"testing"
)

func TestContentServicePostCrudApiIntegration(t *testing.T) {
	cmd := exec.Command(
		"go",
		"test",
		"..",
		"-run",
		"^TestCreatePostAggregate$",
		"-count=1",
	)
	output, err := cmd.CombinedOutput()
	if err != nil {
		t.Fatalf("legacy content-service post crud api integration failed: %v\n%s", err, output)
	}
}
