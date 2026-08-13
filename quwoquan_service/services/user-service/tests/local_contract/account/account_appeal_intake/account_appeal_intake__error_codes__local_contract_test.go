package local_contract

import (
	"bytes"
	"context"
	"errors"
	"testing"
	"time"

	runtimeerrors "quwoquan_service/runtime/errors"
	"quwoquan_service/services/user-service/internal/account/account_appeal_intake/application"
	"quwoquan_service/services/user-service/internal/account/account_appeal_intake/domain/ports"
)

func assertAppealErrorCode(t *testing.T, err error, wantCode string) {
	t.Helper()
	var appErr *runtimeerrors.AppError
	if !errors.As(err, &appErr) || appErr.Code.String() != wantCode {
		t.Fatalf("expected %s, got %T: %v", wantCode, err, err)
	}
}

// claimNotFoundAppealStore 模拟 claim 一个不存在或已被清除的 intake。
type claimNotFoundAppealStore struct {
	appealStoreProbe
}

func (*claimNotFoundAppealStore) Claim(
	context.Context,
	ports.ClaimCommit,
) (ports.CommandResult, error) {
	return ports.CommandResult{}, ports.ErrIntakeNotFound
}

func TestAppealIssueCredentialRejectsExpiredIdentityEvidence(t *testing.T) {
	now := time.Date(2026, 8, 12, 9, 0, 0, 0, time.UTC)
	facade := application.NewCommandFacade(
		&appealStoreProbe{},
		&identityProbe{evidence: ports.IdentityChallengeEvidence{
			ChallengeID: "otp_ch_expired",
			AccountID:   testAppealAccountID,
			// 身份验证证据已过期,不得据此签发申诉凭据。
			ExpiresAt: now.Add(-time.Minute),
		}},
		nil,
		application.WithClock(func() time.Time { return now }),
		application.WithEntropy(bytes.NewReader(bytes.Repeat([]byte{0x27}, 64))),
	)

	_, err := facade.IssueCredential(
		context.Background(),
		application.IssueCredentialCommand{
			Phone:       "13800000000",
			OTPCode:     []byte("123456"),
			ChallengeID: "otp_ch_expired",
		},
	)
	assertAppealErrorCode(
		t, err, "USER.ACCOUNT.account_appeal_credential_invalid",
	)
}

func TestAppealClaimIntakeSurfacesIntakeNotFound(t *testing.T) {
	now := time.Date(2026, 8, 12, 9, 0, 0, 0, time.UTC)
	facade := application.NewCommandFacade(
		&claimNotFoundAppealStore{},
		&identityProbe{},
		nil,
		application.WithClock(func() time.Time { return now }),
		application.WithEntropy(bytes.NewReader(bytes.Repeat([]byte{0x33}, 64))),
	)

	_, err := facade.ClaimIntake(
		context.Background(),
		application.ClaimIntakeCommand{
			IntakeRef:      "appeal_intake_AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
			AccountID:      testAppealAccountID,
			CaseID:         "appeal-case-missing",
			IdempotencyKey: "claim-missing-intake",
		},
	)
	assertAppealErrorCode(
		t, err, "USER.ACCOUNT.account_appeal_intake_not_found",
	)
}
