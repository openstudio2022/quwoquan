package local_contract

import (
	"os/exec"
	"testing"
)

func TestVideoImportCoverProjectionLocalContract(t *testing.T) {
	cmd := exec.Command(
		"go",
		"test",
		"../../../../cmd/import",
		"-run",
		"^TestLoadManifestOnlyVideoPostAndCoverContract$",
		"-count=1",
	)
	output, err := cmd.CombinedOutput()
	if err != nil {
		t.Fatalf("video import cover projection contract failed: %v\n%s", err, output)
	}
}
