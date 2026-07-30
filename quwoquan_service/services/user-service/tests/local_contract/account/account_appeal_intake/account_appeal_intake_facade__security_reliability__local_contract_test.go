package local_contract

import (
	"bytes"
	"context"
	"strings"
	"testing"
	"time"

	rterr "quwoquan_service/runtime/errors"
	"quwoquan_service/services/user-service/internal/account/account_appeal_intake/application"
	"quwoquan_service/services/user-service/internal/account/account_appeal_intake/domain/model"
	"quwoquan_service/services/user-service/internal/account/account_appeal_intake/domain/ports"
)

// spec_ref: specs/feature-tree/user-identity-profile-relationship/settings-and-device-token/account-suspension-and-appeal-lifecycle/spec.md#gwt-004
func TestAppealCredentialIsIssuedOnlyFromVerifiedIdentityAndPersistedAsDigest(t *testing.T) {
	now := time.Date(2026, 7, 29, 9, 0, 0, 0, time.UTC)
	store := &appealStoreProbe{}
	identities := &identityProbe{evidence: ports.IdentityChallengeEvidence{
		ChallengeID: "otp_ch_appeal", AccountID: testAppealAccountID,
		ExpiresAt: now.Add(5 * time.Minute),
	}}
	facade := application.NewCommandFacade(
		store,
		identities,
		nil,
		application.WithClock(func() time.Time { return now }),
		application.WithEntropy(bytes.NewReader(bytes.Repeat([]byte{0x5a}, 64))),
	)
	result, err := facade.IssueCredential(context.Background(), application.IssueCredentialCommand{
		Phone: "+86 138-0000-0000", OTPCode: []byte("123456"),
		ChallengeID: "otp_ch_appeal",
	})
	if err != nil {
		t.Fatal(err)
	}
	if !strings.HasPrefix(result.AppealCredential, "appeal_credential_") ||
		len(store.issued) != 1 || identities.calls != 1 {
		t.Fatalf("issue result/store/identity mismatch: %+v %+v", result, store.issued)
	}
	commit := store.issued[0]
	if commit.AccountID != testAppealAccountID || commit.ChallengeID != "otp_ch_appeal" ||
		len(commit.CredentialDigest) != 64 ||
		strings.Contains(commit.CredentialID, result.AppealCredential) ||
		commit.ExpiresAt.Sub(commit.IssuedAt) != model.CredentialTTL {
		t.Fatalf("credential secret leaked or policy drifted: %+v", commit)
	}
	if identities.lastOTP != "123456" {
		t.Fatalf("identity verifier did not receive the transient OTP")
	}
}

// spec_ref: specs/feature-tree/user-identity-profile-relationship/settings-and-device-token/account-suspension-and-appeal-lifecycle/spec.md#gwt-004
func TestAppealSubmissionAndClaimCarryOnlyOpaqueDigestAndExactTuple(t *testing.T) {
	now := time.Date(2026, 7, 29, 9, 0, 0, 0, time.UTC)
	store := &appealStoreProbe{now: now}
	facade := application.NewCommandFacade(
		store,
		&identityProbe{},
		nil,
		application.WithClock(func() time.Time { return now }),
		application.WithEntropy(bytes.NewReader(bytes.Repeat([]byte{0x41}, 64))),
	)
	credential := "appeal_credential_AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
	submitted, err := facade.SubmitIntake(context.Background(), application.SubmitIntakeCommand{
		AppealCredential: credential, IdempotencyKey: "submit-1",
	})
	if err != nil {
		t.Fatal(err)
	}
	if len(store.submitted) != 1 || store.submitted[0].CredentialDigest == credential ||
		strings.Contains(store.submitted[0].CommandDigest, credential) ||
		submitted.IntakeRef == "" {
		t.Fatalf("submission secret/digest contract drift: %+v", store.submitted)
	}
	claimed, err := facade.ClaimIntake(context.Background(), application.ClaimIntakeCommand{
		IntakeRef: submitted.IntakeRef, AccountID: testAppealAccountID,
		CaseID: "appeal-case-1", IdempotencyKey: "claim-1",
	})
	if err != nil {
		t.Fatal(err)
	}
	if len(store.claimed) != 1 || claimed.IntakeRef != submitted.IntakeRef ||
		claimed.AccountID != testAppealAccountID || claimed.CaseID != "appeal-case-1" ||
		claimed.Status != "claimed" {
		t.Fatalf("claim tuple drift: result=%+v commits=%+v", claimed, store.claimed)
	}
}

// spec_ref: specs/feature-tree/user-identity-profile-relationship/settings-and-device-token/account-suspension-and-appeal-lifecycle/spec.md#gwt-004
func TestAppealFacadePreservesTypedRateAndSuspensionErrors(t *testing.T) {
	now := time.Date(2026, 7, 29, 9, 0, 0, 0, time.UTC)
	tests := []struct {
		name     string
		storeErr error
		wantCode string
	}{
		{"rate limited", ports.ErrRateLimited, "USER.ACCOUNT.account_appeal_rate_limited"},
		{"not suspended", ports.ErrAccountNotSuspended, "USER.ACCOUNT.account_appeal_not_suspended"},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			store := &appealStoreProbe{issueErr: test.storeErr}
			facade := application.NewCommandFacade(
				store,
				&identityProbe{evidence: ports.IdentityChallengeEvidence{
					ChallengeID: "otp_ch_appeal", AccountID: testAppealAccountID,
					ExpiresAt: now.Add(time.Minute),
				}},
				nil,
				application.WithClock(func() time.Time { return now }),
				application.WithEntropy(bytes.NewReader(bytes.Repeat([]byte{0x31}, 64))),
			)
			_, err := facade.IssueCredential(context.Background(), application.IssueCredentialCommand{
				Phone: "13800000000", OTPCode: []byte("123456"), ChallengeID: "otp_ch_appeal",
			})
			if code := rterr.NormalizeError(err).Code.String(); code != test.wantCode {
				t.Fatalf("error code=%s want=%s err=%v", code, test.wantCode, err)
			}
		})
	}
}

type identityProbe struct {
	evidence ports.IdentityChallengeEvidence
	err      error
	calls    int
	lastOTP  string
}

func (probe *identityProbe) VerifyAccountAppealChallenge(
	_ context.Context,
	_ string,
	otpCode []byte,
	_ string,
) (ports.IdentityChallengeEvidence, error) {
	probe.calls++
	probe.lastOTP = string(otpCode)
	return probe.evidence, probe.err
}

type appealStoreProbe struct {
	now       time.Time
	issueErr  error
	issued    []ports.IssueCredentialCommit
	submitted []ports.SubmitCommit
	claimed   []ports.ClaimCommit
}

func (probe *appealStoreProbe) IssueCredential(
	_ context.Context,
	commit ports.IssueCredentialCommit,
) (ports.CredentialReceipt, error) {
	probe.issued = append(probe.issued, commit)
	return ports.CredentialReceipt{ExpiresAt: commit.ExpiresAt}, probe.issueErr
}

func (probe *appealStoreProbe) Submit(
	_ context.Context,
	commit ports.SubmitCommit,
) (ports.CommandResult, error) {
	probe.submitted = append(probe.submitted, commit)
	intake, err := model.NewSubmitted(model.CreateParams{
		IntakeRef: commit.IntakeRef, AccountID: testAppealAccountID,
		SuspensionAuthEpoch: 2, SubmittedAt: commit.SubmittedAt,
		DeleteAfter: commit.DeleteAfter,
	})
	return ports.CommandResult{Intake: intake}, err
}

func (probe *appealStoreProbe) Claim(
	_ context.Context,
	commit ports.ClaimCommit,
) (ports.CommandResult, error) {
	probe.claimed = append(probe.claimed, commit)
	submittedAt := commit.ClaimedAt.Add(-time.Minute)
	intake, err := model.NewSubmitted(model.CreateParams{
		IntakeRef: commit.IntakeRef, AccountID: commit.AccountID,
		SuspensionAuthEpoch: 2, SubmittedAt: submittedAt,
		DeleteAfter: submittedAt.Add(model.IntakeRetention),
	})
	if err != nil {
		return ports.CommandResult{}, err
	}
	claimed, _, err := intake.Claim(commit.AccountID, commit.CaseID, commit.ClaimedAt)
	return ports.CommandResult{Intake: claimed}, err
}

func (*appealStoreProbe) PurgeExpired(
	context.Context,
	time.Time,
) (int64, int64, error) {
	return 0, 0, nil
}
