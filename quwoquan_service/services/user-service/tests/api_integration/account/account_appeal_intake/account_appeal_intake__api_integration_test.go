// spec_ref: specs/feature-tree/user-identity-profile-relationship/settings-and-device-token/account-suspension-and-appeal-lifecycle/spec.md#gwt-004
package api_integration

import (
	"bytes"
	"context"
	"crypto/sha256"
	"encoding/hex"
	"net/http"
	"strings"
	"testing"
	"time"

	appealapp "quwoquan_service/services/user-service/internal/account/account_appeal_intake/application"
	credentialapp "quwoquan_service/services/user-service/internal/account/credential_binding/application"
	credentialmodel "quwoquan_service/services/user-service/internal/account/credential_binding/domain/model"
	useraccountapp "quwoquan_service/services/user-service/internal/account/user_account/application"
	accountports "quwoquan_service/services/user-service/internal/account/user_account/domain/ports"
	userapisupport "quwoquan_service/services/user-service/tests/support"
)

const (
	testAppealAccountID = "uo_01_ph_333a_01j00000000000000000000000"
	testOtherAccountID  = "uo_01_ph_2cdb_01j00000000000000000000001"
	testAppealPhone     = "+86 138-0000-0000"
)

func TestAccountAppealIntakeRealPostgreSQLHTTPBoundary(t *testing.T) {
	if appealIntakePGPool == nil {
		t.Fatal("real PostgreSQL pool was not initialized")
	}
	ctx, cancel := context.WithTimeout(context.Background(), 90*time.Second)
	defer cancel()
	runtime := newRealAppealRuntime(t, ctx, appealIntakePGPool)

	assertPublicOperationsRemainCommerciallyBlocked(t, runtime)
	seedSuspendedAppealIdentity(t, ctx, runtime)
	seedAppealChallenge(t, ctx, runtime, "appeal-challenge-real-1", "123456")

	wrongOTP := postJSON(t, runtime.activatedServer.Client(), runtime.activatedServer.URL,
		"/account-appeals/credentials", "", "", map[string]any{
			"phone": testAppealPhone, "otpCode": "000000",
			"challengeId": "appeal-challenge-real-1",
		})
	assertRuntimeError(t, wrongOTP, http.StatusBadRequest, "USER.AUTH.otp_mismatch")

	issued := postJSON(t, runtime.activatedServer.Client(), runtime.activatedServer.URL,
		"/account-appeals/credentials", "", "", map[string]any{
			"phone": testAppealPhone, "otpCode": "123456",
			"challengeId": "appeal-challenge-real-1",
		})
	assertStatus(t, issued, http.StatusCreated)
	assertNoStore(t, issued)
	credentialOne := decodeJSON[appealapp.CredentialIssueResult](t, issued)
	if credentialOne.AppealCredential == "" || !credentialOne.ExpiresAt.After(time.Now().UTC()) {
		t.Fatalf("credential issue receipt is incomplete: %+v", credentialOne)
	}
	assertCredentialPersistedOnlyAsDigest(
		t, ctx, "appeal-challenge-real-1", credentialOne.AppealCredential,
	)

	duplicateIssue := postJSON(t, runtime.activatedServer.Client(), runtime.activatedServer.URL,
		"/account-appeals/credentials", "", "", map[string]any{
			"phone": testAppealPhone, "otpCode": "123456",
			"challengeId": "appeal-challenge-real-1",
		})
	assertRuntimeError(
		t, duplicateIssue, http.StatusTooManyRequests,
		"USER.ACCOUNT.account_appeal_rate_limited",
	)

	missingIdempotency := postJSON(t, runtime.activatedServer.Client(), runtime.activatedServer.URL,
		"/account-appeals/intakes", "", "", map[string]any{
			"appealCredential": credentialOne.AppealCredential,
		})
	assertRuntimeError(
		t, missingIdempotency, http.StatusBadRequest,
		"GATEWAY.USER.invalid_argument",
	)

	firstSubmission := postJSON(t, runtime.activatedServer.Client(), runtime.activatedServer.URL,
		"/account-appeals/intakes", "appeal-submit-real-1", "", map[string]any{
			"appealCredential": credentialOne.AppealCredential,
		})
	assertStatus(t, firstSubmission, http.StatusCreated)
	assertNoStore(t, firstSubmission)
	if bytes.Contains(firstSubmission.body, []byte(testAppealAccountID)) {
		t.Fatalf("public intake receipt leaked accountId: %s", firstSubmission.body)
	}
	submission := decodeJSON[appealapp.IntakeSubmissionResult](t, firstSubmission)
	if submission.IntakeRef == "" || submission.IdempotentReplay ||
		!submission.DeleteAfter.After(submission.SubmittedAt) {
		t.Fatalf("first submission receipt is invalid: %+v", submission)
	}
	assertCredentialConsumption(t, ctx, credentialOne.AppealCredential, submission.IntakeRef)

	replayedSubmission := postJSON(
		t, runtime.activatedServer.Client(), runtime.activatedServer.URL,
		"/account-appeals/intakes", "appeal-submit-real-1", "", map[string]any{
			"appealCredential": credentialOne.AppealCredential,
		},
	)
	assertStatus(t, replayedSubmission, http.StatusCreated)
	replay := decodeJSON[appealapp.IntakeSubmissionResult](t, replayedSubmission)
	if !replay.IdempotentReplay || replay.IntakeRef != submission.IntakeRef ||
		!replay.SubmittedAt.Equal(submission.SubmittedAt) ||
		!replay.DeleteAfter.Equal(submission.DeleteAfter) {
		t.Fatalf("exact submission replay changed its receipt: first=%+v replay=%+v", submission, replay)
	}

	consumedWithAnotherRequestIdentity := postJSON(
		t, runtime.activatedServer.Client(), runtime.activatedServer.URL,
		"/account-appeals/intakes", "appeal-submit-real-2", "", map[string]any{
			"appealCredential": credentialOne.AppealCredential,
		},
	)
	assertRuntimeError(
		t, consumedWithAnotherRequestIdentity, http.StatusConflict,
		"USER.ACCOUNT.account_appeal_credential_consumed",
	)

	assertClaimAuthorizationAndTupleSemantics(t, runtime, submission.IntakeRef)

	seedAppealChallenge(t, ctx, runtime, "appeal-challenge-real-2", "654321")
	secondIssue := postJSON(t, runtime.activatedServer.Client(), runtime.activatedServer.URL,
		"/account-appeals/credentials", "", "", map[string]any{
			"phone": testAppealPhone, "otpCode": "654321",
			"challengeId": "appeal-challenge-real-2",
		})
	assertStatus(t, secondIssue, http.StatusCreated)
	credentialTwo := decodeJSON[appealapp.CredentialIssueResult](t, secondIssue)

	submissionKeyConflict := postJSON(
		t, runtime.activatedServer.Client(), runtime.activatedServer.URL,
		"/account-appeals/intakes", "appeal-submit-real-1", "", map[string]any{
			"appealCredential": credentialTwo.AppealCredential,
		},
	)
	assertRuntimeError(
		t, submissionKeyConflict, http.StatusConflict,
		"USER.ACCOUNT.account_appeal_idempotency_conflict",
	)
	assertCredentialStillUnused(t, ctx, credentialTwo.AppealCredential)

	expireCredential(t, ctx, credentialTwo.AppealCredential)
	expiredSubmission := postJSON(
		t, runtime.activatedServer.Client(), runtime.activatedServer.URL,
		"/account-appeals/intakes", "appeal-submit-expired", "", map[string]any{
			"appealCredential": credentialTwo.AppealCredential,
		},
	)
	assertRuntimeError(
		t, expiredSubmission, http.StatusGone,
		"USER.ACCOUNT.account_appeal_credential_expired",
	)
	assertCredentialRetentionPurge(t, ctx, runtime, credentialTwo.AppealCredential)

	restored, err := runtime.enforcement.RestoreAccount(ctx, useraccountapp.EnforcementCommand{
		AccountID: testAppealAccountID,
		Decision: accountports.EnforcementDecision{
			DecisionID: "appeal-integration-restore", CaseRef: "appeal-case-restore",
			DecisionDigest: strings.Repeat("b", 64), ApprovedAt: time.Now().UTC(),
		},
	})
	if err != nil || restored.AccountState != "active" {
		t.Fatalf("restore appeal integration account: result=%+v err=%v", restored, err)
	}
	seedAppealChallenge(t, ctx, runtime, "appeal-challenge-real-3", "112233")
	notSuspended := postJSON(t, runtime.activatedServer.Client(), runtime.activatedServer.URL,
		"/account-appeals/credentials", "", "", map[string]any{
			"phone": testAppealPhone, "otpCode": "112233",
			"challengeId": "appeal-challenge-real-3",
		})
	assertRuntimeError(
		t, notSuspended, http.StatusConflict,
		"USER.ACCOUNT.account_appeal_not_suspended",
	)
}

func seedSuspendedAppealIdentity(
	t *testing.T,
	ctx context.Context,
	runtime *realAppealRuntime,
) {
	t.Helper()
	if err := userapisupport.CreateAccount(
		ctx, appealIntakePGPool, testAppealAccountID, "Appeal integration owner",
	); err != nil {
		t.Fatal(err)
	}
	phoneKey := credentialmodel.NormalizePhoneCredentialKey(testAppealPhone)
	if _, err := runtime.credentials.BindVerifiedCredential(
		ctx,
		testAppealAccountID,
		credentialapp.BindCredentialCommand{
			CredentialType: credentialmodel.CredentialTypePhone,
			CredentialKey:  phoneKey,
			DisplayLabel:   "***0000",
		},
	); err != nil {
		t.Fatalf("bind real appeal phone identity: %v", err)
	}
	suspended, err := runtime.enforcement.SuspendAccount(ctx, useraccountapp.EnforcementCommand{
		AccountID: testAppealAccountID,
		Decision: accountports.EnforcementDecision{
			DecisionID: "appeal-integration-suspend", CaseRef: "moderation-case-appeal",
			DecisionDigest: strings.Repeat("a", 64), ApprovedAt: time.Now().UTC(),
		},
	})
	if err != nil || suspended.AccountState != "suspended" || suspended.AuthEpoch != 2 {
		t.Fatalf("suspend appeal integration account: result=%+v err=%v", suspended, err)
	}
}

func credentialDigest(credential string) string {
	sum := sha256.Sum256([]byte(credential))
	return hex.EncodeToString(sum[:])
}
