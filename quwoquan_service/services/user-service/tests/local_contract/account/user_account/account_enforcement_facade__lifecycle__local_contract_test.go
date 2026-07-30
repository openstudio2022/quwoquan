// spec_ref: specs/feature-tree/user-identity-profile-relationship/settings-and-device-token/account-suspension-and-appeal-lifecycle/spec.md#gwt-001
// spec_ref: specs/feature-tree/user-identity-profile-relationship/settings-and-device-token/account-suspension-and-appeal-lifecycle/spec.md#gwt-003
package local_contract

import (
	"context"
	"errors"
	"testing"
	"time"

	rterr "quwoquan_service/runtime/errors"
	"quwoquan_service/services/user-service/generated/account/user_account"
	useraccountapp "quwoquan_service/services/user-service/internal/account/user_account/application"
	accountports "quwoquan_service/services/user-service/internal/account/user_account/domain/ports"
)

type recordingEnforcementStore struct {
	accountID string
	action    accountports.EnforcementAction
	decision  accountports.EnforcementDecision
	result    accountports.EnforcementCommitResult
	err       error
	calls     int
}

func (store *recordingEnforcementStore) CommitEnforcement(
	_ context.Context,
	accountID string,
	action accountports.EnforcementAction,
	decision accountports.EnforcementDecision,
	_ time.Time,
) (accountports.EnforcementCommitResult, error) {
	store.calls++
	store.accountID = accountID
	store.action = action
	store.decision = decision
	return store.result, store.err
}

func TestAccountEnforcementFacadeSuspendsWithTrustedDecision(t *testing.T) {
	store := &recordingEnforcementStore{
		result: accountports.EnforcementCommitResult{
			AccountState: "suspended",
			AuthEpoch:    2,
			DecisionID:   "decision-1",
			OccurredAt:   time.Date(2026, time.July, 21, 0, 0, 0, 0, time.UTC),
		},
	}
	facade := useraccountapp.NewAccountEnforcementCommandFacade(store)
	outcome, err := facade.SuspendAccount(
		context.Background(),
		useraccountapp.EnforcementCommand{
			AccountID: " account-1 ",
			Decision: accountports.EnforcementDecision{
				DecisionID:     " decision-1 ",
				CaseRef:        " case-1 ",
				DecisionDigest: " digest-1 ",
				ApprovedAt:     time.Date(2026, time.July, 20, 0, 0, 0, 0, time.UTC),
			},
		},
	)
	if err != nil {
		t.Fatalf("suspend account: %v", err)
	}
	if store.calls != 1 || store.accountID != "account-1" ||
		store.action != accountports.EnforcementActionSuspend ||
		store.decision.DecisionID != "decision-1" ||
		store.decision.CaseRef != "case-1" ||
		store.decision.DecisionDigest != "digest-1" {
		t.Fatalf("trusted decision was not normalized and committed: %+v", store)
	}
	if outcome.AccountState != "suspended" || outcome.AuthEpoch != 2 ||
		outcome.DecisionID != "decision-1" || outcome.OccurredAt.IsZero() {
		t.Fatalf("unexpected suspend outcome: %+v", outcome)
	}
}

func TestAccountEnforcementFacadeRejectsIncompleteDecisionBeforePersistence(t *testing.T) {
	store := &recordingEnforcementStore{}
	facade := useraccountapp.NewAccountEnforcementCommandFacade(store)
	_, err := facade.RestoreAccount(
		context.Background(),
		useraccountapp.EnforcementCommand{
			AccountID: "account-1",
			Decision: accountports.EnforcementDecision{
				DecisionID: "decision-2",
			},
		},
	)
	if store.calls != 0 {
		t.Fatalf("incomplete decision must not reach persistence: %+v", store)
	}
	assertGeneratedAppErrorCode(
		t,
		err,
		generated.ErrAccountEnforcementDecisionInvalid,
	)
}

func TestAccountEnforcementFacadeMapsClosedRestoreConflict(t *testing.T) {
	store := &recordingEnforcementStore{
		err: accountports.ErrAccountStateConflict,
	}
	facade := useraccountapp.NewAccountEnforcementCommandFacade(store)
	_, err := facade.RestoreAccount(
		context.Background(),
		useraccountapp.EnforcementCommand{
			AccountID: "account-closed",
			Decision: accountports.EnforcementDecision{
				DecisionID:     "decision-3",
				CaseRef:        "case-3",
				DecisionDigest: "digest-3",
				ApprovedAt:     time.Date(2026, time.July, 20, 0, 0, 0, 0, time.UTC),
			},
		},
	)
	assertGeneratedAppErrorCode(t, err, generated.ErrAccountStateConflict)
}

func assertGeneratedAppErrorCode(t *testing.T, err error, expected error) {
	t.Helper()
	var appErr *rterr.AppError
	if !errors.As(err, &appErr) {
		t.Fatalf("expected AppError, got %v", err)
	}
	if appErr.Code.String() != expected.Error() {
		t.Fatalf("error code=%s want=%s", appErr.Code, expected)
	}
}
