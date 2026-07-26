package local_contract

import (
	"context"
	"testing"

	accountorchestration "quwoquan_service/services/user-service/internal/account/user_account/application/account_orchestration"
)

// TestMigratedMain verifies the command boundary through its public application port.
func TestMigratedAcceptanceSessionMainApplicationPort(t *testing.T) {
	validator := accountorchestration.PathProfileTagValidator{}
	if err := validator.ValidateProfileTags(
		context.Background(),
		"taxonomy-release-test",
		"Audience/用户/职业/产品运营/产品经理",
		[]string{"Audience/用户/兴趣偏好/旅行摄影/旅行"},
	); err != nil {
		t.Fatalf("public profile-tag application port rejected valid input: %v", err)
	}
}
