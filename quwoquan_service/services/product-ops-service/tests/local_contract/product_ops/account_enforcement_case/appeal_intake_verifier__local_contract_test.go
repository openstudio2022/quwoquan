package local_contract

import (
	"context"
	"errors"
	"testing"
	"time"

	"quwoquan_service/services/product-ops-service/internal/product_ops/account_enforcement_case/application"
	"quwoquan_service/services/product-ops-service/internal/product_ops/account_enforcement_case/domain/model"
	"quwoquan_service/services/product-ops-service/internal/product_ops/account_enforcement_case/domain/ports"
)

// spec_ref: specs/feature-tree/product-ops-growth/product-control-plane-foundation/account-moderation-and-appeal-enforcement/spec.md#gwt-002
func TestOpenAppealFailsClosedWithoutAClaimedUserOwnedIntake(t *testing.T) {
	tests := []struct {
		name     string
		verifier ports.AppealIntakeVerifier
		want     error
	}{
		{
			name: "missing verifier",
			want: ports.ErrAppealIntakeUnavailable,
		},
		{
			name: "unavailable",
			verifier: &appealIntakeVerifierProbe{
				err: ports.ErrAppealIntakeUnavailable,
			},
			want: ports.ErrAppealIntakeUnavailable,
		},
		{
			name: "invalid",
			verifier: &appealIntakeVerifierProbe{
				err: ports.ErrAppealIntakeInvalid,
			},
			want: model.ErrSourceDecisionConflict,
		},
		{
			name: "account mismatch",
			verifier: &appealIntakeVerifierProbe{
				err: ports.ErrAppealIntakeAccountMismatch,
			},
			want: model.ErrSourceDecisionConflict,
		},
		{
			name: "consumed by another case",
			verifier: &appealIntakeVerifierProbe{
				err: ports.ErrAppealIntakeConsumed,
			},
			want: model.ErrSourceDecisionConflict,
		},
		{
			name: "unknown verifier failure",
			verifier: &appealIntakeVerifierProbe{
				err: errors.New("opaque dependency failure"),
			},
			want: ports.ErrAppealIntakeUnavailable,
		},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			store := &appealClaimStoreProbe{}
			service := application.NewService(store, nil, test.verifier)
			_, err := service.OpenAppeal(
				context.Background(),
				validOpenAppealCommand(),
			)
			if !errors.Is(err, test.want) {
				t.Fatalf("OpenAppeal error=%v want=%v", err, test.want)
			}
			if store.commitCalls != 0 {
				t.Fatalf("unverified intake reached CommitOpen %d times", store.commitCalls)
			}
		})
	}
}

// spec_ref: specs/feature-tree/product-ops-growth/product-control-plane-foundation/account-moderation-and-appeal-enforcement/spec.md#gwt-002
func TestOpenAppealClaimsIntakeForTheExactAccountAndCase(t *testing.T) {
	store := &appealClaimStoreProbe{}
	verifier := &appealIntakeVerifierProbe{}
	service := application.NewService(store, nil, verifier)
	result, err := service.OpenAppeal(
		context.Background(),
		validOpenAppealCommand(),
	)
	if err != nil {
		t.Fatal(err)
	}
	if store.commitCalls != 1 || len(verifier.claims) != 1 {
		t.Fatalf(
			"claim/commit calls=%d/%d want=1/1",
			len(verifier.claims),
			store.commitCalls,
		)
	}
	claim := verifier.claims[0]
	if claim.IntakeRef != "intake-user-owned-1" ||
		claim.AccountID != "account-1" ||
		claim.CaseID != "appeal-1" {
		t.Fatalf("unexpected appeal intake claim: %+v", claim)
	}
	if result.CaseID != "appeal-1" ||
		result.CaseKind != model.CaseKindAppeal ||
		result.Status != model.CaseStatusPendingApproval {
		t.Fatalf("unexpected appeal result: %+v", result)
	}
}

// spec_ref: specs/feature-tree/product-ops-growth/product-control-plane-foundation/account-moderation-and-appeal-enforcement/spec.md#gwt-002
func TestOpenAppealIdempotentReplayDoesNotReclaimConsumedIntake(t *testing.T) {
	now := time.Date(2026, 7, 29, 8, 0, 0, 0, time.UTC)
	store := &appealClaimStoreProbe{
		replayFound: true,
		replay: ports.CaseSnapshot{CommandResult: &ports.CommandResult{
			CaseID: "appeal-1", CaseKind: model.CaseKindAppeal,
			Status: model.CaseStatusPendingApproval, Version: 1,
			UpdatedAt: now,
		}},
	}
	verifier := &appealIntakeVerifierProbe{
		err: ports.ErrAppealIntakeConsumed,
	}
	service := application.NewService(store, nil, verifier)
	result, err := service.OpenAppeal(
		context.Background(),
		validOpenAppealCommand(),
	)
	if err != nil {
		t.Fatal(err)
	}
	if len(verifier.claims) != 0 || store.commitCalls != 0 ||
		result.CaseID != "appeal-1" {
		t.Fatalf(
			"replay reclaimed intake or committed: claims=%d commits=%d result=%+v",
			len(verifier.claims),
			store.commitCalls,
			result,
		)
	}
}

func validOpenAppealCommand() application.OpenAppealCommand {
	return application.OpenAppealCommand{
		CaseID:           "appeal-1",
		AccountID:        "account-1",
		SourceDecisionID: "suspend-decision-1",
		IntakeRef:        "intake-user-owned-1",
		EvidenceRefs:     []string{"evidence-ref-1"},
		ActorID:          "operator-1",
		IdempotencyKey:   "open-appeal-1",
	}
}

type appealIntakeVerifierProbe struct {
	err    error
	claims []ports.AppealIntakeClaim
}

func (verifier *appealIntakeVerifierProbe) Claim(
	_ context.Context,
	claim ports.AppealIntakeClaim,
) error {
	if verifier.err != nil {
		return verifier.err
	}
	verifier.claims = append(verifier.claims, claim)
	return nil
}

type appealClaimStoreProbe struct {
	replay      ports.CaseSnapshot
	replayFound bool
	commitCalls int
}

func (store *appealClaimStoreProbe) Replay(
	context.Context,
	string,
	string,
) (ports.CaseSnapshot, bool, error) {
	return store.replay, store.replayFound, nil
}

func (store *appealClaimStoreProbe) CommitOpen(
	_ context.Context,
	current model.Case,
	_ ports.CommandReceipt,
) (ports.CaseSnapshot, error) {
	store.commitCalls++
	return ports.CaseSnapshot{Case: current}, nil
}

func (*appealClaimStoreProbe) Load(context.Context, string) (model.Case, error) {
	panic("unexpected Load")
}

func (*appealClaimStoreProbe) CommitReview(
	context.Context,
	int64,
	model.Case,
	model.Review,
	*model.Decision,
	ports.CommandReceipt,
) (ports.CaseSnapshot, error) {
	panic("unexpected CommitReview")
}

func (*appealClaimStoreProbe) RecoverDelivery(
	context.Context,
	string,
	ports.CommandReceipt,
	time.Time,
) (ports.CaseSnapshot, error) {
	panic("unexpected RecoverDelivery")
}
