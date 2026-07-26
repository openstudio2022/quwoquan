package local_contract

import (
	"context"
	"testing"

	accountorchestration "quwoquan_service/services/user-service/internal/account/user_account/application/account_orchestration"
)

// TestMigratedAccountSecurityGate validates the account command boundary without HTTP-adapter internals.
func TestMigratedAccountSecurityGateApplicationPort(t *testing.T) {
	if err := (accountorchestration.PathProfileTagValidator{}).ValidateProfileTags(
		context.Background(),
		"taxonomy-release-test",
		"Audience/用户/职业/产品运营/产品经理",
		[]string{"Audience/用户/兴趣偏好/旅行摄影/旅行"},
	); err != nil {
		t.Fatalf("public account application port rejected valid profile tags: %v", err)
	}
}
