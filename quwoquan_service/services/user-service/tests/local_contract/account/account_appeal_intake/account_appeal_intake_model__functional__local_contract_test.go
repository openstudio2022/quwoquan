package local_contract

import (
	"errors"
	"testing"
	"time"

	"quwoquan_service/services/user-service/internal/account/account_appeal_intake/domain/model"
)

const (
	testAppealAccountID      = "uo_01_ph_333a_01j00000000000000000000000"
	testOtherAppealAccountID = "uo_01_ph_2cdb_01j00000000000000000000001"
	testAppealIntakeRef      = "appeal_intake_AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
)

// spec_ref: specs/feature-tree/user-identity-profile-relationship/settings-and-device-token/account-suspension-and-appeal-lifecycle/spec.md#gwt-004
func TestAccountAppealIntakeClaimIsBoundToOneAccountAndCaseTuple(t *testing.T) {
	submittedAt := time.Date(2026, 7, 29, 9, 0, 0, 0, time.UTC)
	intake, err := model.NewSubmitted(model.CreateParams{
		IntakeRef: testAppealIntakeRef, AccountID: testAppealAccountID,
		SuspensionAuthEpoch: 2, SubmittedAt: submittedAt,
		DeleteAfter: submittedAt.Add(model.IntakeRetention),
	})
	if err != nil {
		t.Fatal(err)
	}
	claimed, replayed, err := intake.Claim(
		testAppealAccountID, "appeal-case-1", submittedAt.Add(time.Minute),
	)
	if err != nil || replayed {
		t.Fatalf("first claim: replayed=%t err=%v", replayed, err)
	}
	replay, replayed, err := claimed.Claim(
		testAppealAccountID, "appeal-case-1", submittedAt.Add(2*time.Minute),
	)
	if err != nil || !replayed || replay.State().Version != claimed.State().Version {
		t.Fatalf("same tuple replay: replayed=%t err=%v", replayed, err)
	}
	if _, _, err := claimed.Claim(
		testOtherAppealAccountID, "appeal-case-1", submittedAt.Add(2*time.Minute),
	); !errors.Is(err, model.ErrAccountMismatch) {
		t.Fatalf("cross-account claim error=%v", err)
	}
	if _, _, err := claimed.Claim(
		testAppealAccountID, "appeal-case-2", submittedAt.Add(2*time.Minute),
	); !errors.Is(err, model.ErrAlreadyClaimed) {
		t.Fatalf("cross-case claim error=%v", err)
	}
}

// spec_ref: specs/feature-tree/user-identity-profile-relationship/settings-and-device-token/account-suspension-and-appeal-lifecycle/spec.md#gwt-004
func TestAccountAppealIntakeRejectsIncompleteClaimAndRetentionState(t *testing.T) {
	now := time.Date(2026, 7, 29, 9, 0, 0, 0, time.UTC)
	if _, err := model.NewSubmitted(model.CreateParams{
		IntakeRef: testAppealIntakeRef, AccountID: testAppealAccountID,
		SuspensionAuthEpoch: 0, SubmittedAt: now,
		DeleteAfter: now.Add(model.IntakeRetention),
	}); !errors.Is(err, model.ErrInvalidIntake) {
		t.Fatalf("zero auth epoch error=%v", err)
	}
	intake, err := model.NewSubmitted(model.CreateParams{
		IntakeRef: testAppealIntakeRef, AccountID: testAppealAccountID,
		SuspensionAuthEpoch: 2, SubmittedAt: now,
		DeleteAfter: now.Add(model.IntakeRetention),
	})
	if err != nil {
		t.Fatal(err)
	}
	if _, _, err := intake.Claim(
		testAppealAccountID, "appeal-case-1", now.Add(model.IntakeRetention),
	); !errors.Is(err, model.ErrInvalidIntake) {
		t.Fatalf("claim at retention boundary error=%v", err)
	}
}

// spec_ref: specs/feature-tree/user-identity-profile-relationship/settings-and-device-token/account-suspension-and-appeal-lifecycle/spec.md#gwt-004
func TestAccountAppealIntakeRejectsNonCanonicalCrossDomainIdentifiers(t *testing.T) {
	if model.CanonicalIntakeRef("appeal_intake_AAAAAAAAAAAAAAA/AAAAAAAAAAAAAAAA") {
		t.Fatal("path separator was accepted in intakeRef")
	}
	if model.CanonicalOwnerAccountID("account-1") {
		t.Fatal("legacy/noncanonical accountId was accepted")
	}
	if model.CanonicalAppealCaseID("appeal-1\r\nInjected: true") {
		t.Fatal("header delimiter was accepted in caseId")
	}
	if !model.CanonicalIntakeRef(testAppealIntakeRef) ||
		!model.CanonicalOwnerAccountID(testAppealAccountID) ||
		!model.CanonicalAppealCaseID("appeal-case-1") {
		t.Fatal("canonical cross-domain tuple was rejected")
	}
}
