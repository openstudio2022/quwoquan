package local_contract

import (
	"os/exec"
	"testing"
)

func TestPremiumPoolSourceLocalContractTest(t *testing.T) {
	cmd := exec.Command(
		"go",
		"test",
		"../../../../../internal/infrastructure/recommendation",
		"-run",
		"^(TestPremiumPoolProjectionFieldsFailClosed|TestPremiumPoolSourceGatesToPremiumStream|TestPremiumPoolProjectionFailsClosedOnRejectedAdmission|TestPremiumPoolProjectorProjectsOpsEventsFailClosed|TestPremiumPoolProjectorMarksContentTakedown|TestPremiumPoolEventConsumerProcessesOpsEnvelope)$",
		"-count=1",
	)
	output, err := cmd.CombinedOutput()
	if err != nil {
		t.Fatalf("source bridge failed for quwoquan_service/services/content-service/internal/infrastructure/recommendation/premium_pool_source_test.go: %v\n%s", err, output)
	}
}
