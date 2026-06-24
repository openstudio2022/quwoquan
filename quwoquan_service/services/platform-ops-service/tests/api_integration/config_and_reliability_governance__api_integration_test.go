package api_integration

import (
	"os/exec"
	"testing"
)

func TestConfigAndReliabilityGovernanceApiIntegration(t *testing.T) {
	cmd := exec.Command(
		"go",
		"test",
		"../../cmd/api",
		"-run",
		"^(TestPlatformMutableEndpointsEmitAudit|TestPlatformConfigResolveAndInstanceReports|TestRuntimeConfigSnapshotFiltersDriftByScope|TestPlatformReleaseWorkflowRequiresApprovalAndReturnsWorkflowContext)$",
		"-count=1",
	)
	output, err := cmd.CombinedOutput()
	if err != nil {
		t.Fatalf("platform-ops api_integration bridge failed: %v\n%s", err, output)
	}
}
