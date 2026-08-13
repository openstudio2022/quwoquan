// spec_ref: specs/feature-tree/object-homepage-network/spec.md#dom-002
//
// homepage_claim_request 错误行为负例：经真实 Facade（typed double ports）
// 触发 errors.yaml 声明的错误码，断言 AppError 的 wire code 与 http_status。
package local_contract

import (
	"context"
	"errors"
	"net/http"
	"testing"
	"time"

	rterr "quwoquan_service/runtime/errors"
	claimapp "quwoquan_service/services/entity-service/internal/entity_homepage/homepage_claim_request/application"
	claimmodel "quwoquan_service/services/entity-service/internal/entity_homepage/homepage_claim_request/domain/model"
	claimports "quwoquan_service/services/entity-service/internal/entity_homepage/homepage_claim_request/domain/ports"
)

func claimNegativeNow() time.Time {
	return time.Date(2026, time.August, 13, 10, 0, 0, 0, time.UTC)
}

type stubClaimAggregates struct {
	pending *claimmodel.HomepageClaimRequest
	loaded  *claimmodel.HomepageClaimRequest
}

func (s stubClaimAggregates) Load(
	context.Context, string,
) (*claimmodel.HomepageClaimRequest, bool, error) {
	return s.loaded, s.loaded != nil, nil
}

func (s stubClaimAggregates) FindPending(
	context.Context, string, string,
) (*claimmodel.HomepageClaimRequest, bool, error) {
	return s.pending, s.pending != nil, nil
}

func (s stubClaimAggregates) Commit(
	context.Context, claimports.Commit,
) (claimports.CommitResult, error) {
	return claimports.CommitResult{}, errors.New("commit not expected in negative path")
}

type stubClaimReceipts struct{}

func (stubClaimReceipts) FindReceipt(
	context.Context, string, string, string,
) (claimports.CommitResult, bool, error) {
	return claimports.CommitResult{}, false, nil
}

func (stubClaimReceipts) RecordNoopReceipt(
	context.Context, claimports.NoopReceipt,
) (claimports.CommitResult, error) {
	return claimports.CommitResult{}, nil
}

type stubClaimHomepageGate struct {
	state claimapp.HomepageState
	found bool
}

func (g stubClaimHomepageGate) FindHomepageState(
	context.Context, string,
) (claimapp.HomepageState, bool, error) {
	return g.state, g.found, nil
}

type stubClaimQueue struct{}

func (stubClaimQueue) ListQueue(
	context.Context, claimports.QueueQuery,
) (claimports.QueuePage, error) {
	return claimports.QueuePage{}, nil
}

func claimNegativeFacade(
	t *testing.T,
	aggregates stubClaimAggregates,
	gate stubClaimHomepageGate,
) *claimapp.Facade {
	t.Helper()
	facade, err := claimapp.NewFacade(claimapp.DataPorts{
		Aggregates: aggregates,
		Receipts:   stubClaimReceipts{},
		Homepages:  gate,
		Queue:      stubClaimQueue{},
	})
	if err != nil {
		t.Fatalf("build claim facade: %v", err)
	}
	return facade
}

func assertClaimAppError(t *testing.T, err error, wantCode string, wantStatus int) {
	t.Helper()
	var appErr *rterr.AppError
	if !errors.As(err, &appErr) {
		t.Fatalf("err = %v, want *AppError with code %s", err, wantCode)
	}
	if appErr.Code.String() != wantCode {
		t.Fatalf("code = %s, want %s", appErr.Code.String(), wantCode)
	}
	if appErr.HTTPStatus != wantStatus {
		t.Fatalf("http status = %d, want %d", appErr.HTTPStatus, wantStatus)
	}
}

func TestClaimCreateOnClaimedHomepageEmitsAlreadyClaimed(t *testing.T) {
	t.Parallel()
	facade := claimNegativeFacade(
		t,
		stubClaimAggregates{},
		stubClaimHomepageGate{
			state: claimapp.HomepageState{Status: "published", ClaimStatus: "claimed"},
			found: true,
		},
	)
	_, err := facade.Create(commandContext("claim-negative-key"), claimapp.CreateCommand{
		HomepageID:     "hp_claimed",
		ActorPersonaID: "persona_claimer",
		ClaimTier:      claimmodel.ClaimTierVerified,
	})
	assertClaimAppError(t, err, "ENTITY.USER.already_claimed", http.StatusConflict)
}

func TestClaimCreateWithPendingClaimEmitsDuplicatePendingClaim(t *testing.T) {
	t.Parallel()
	facade := claimNegativeFacade(
		t,
		stubClaimAggregates{pending: &claimmodel.HomepageClaimRequest{}},
		stubClaimHomepageGate{
			state: claimapp.HomepageState{Status: "published"},
			found: true,
		},
	)
	_, err := facade.Create(commandContext("claim-negative-key"), claimapp.CreateCommand{
		HomepageID:     "hp_pending",
		ActorPersonaID: "persona_claimer",
		ClaimTier:      claimmodel.ClaimTierVerified,
	})
	assertClaimAppError(
		t, err, "ENTITY.USER.duplicate_pending_claim", http.StatusConflict,
	)
}

func TestClaimCreateWithoutMaterialEmitsClaimMaterialMissing(t *testing.T) {
	t.Parallel()
	facade := claimNegativeFacade(
		t,
		stubClaimAggregates{},
		stubClaimHomepageGate{
			state: claimapp.HomepageState{Status: "published"},
			found: true,
		},
	)
	_, err := facade.Create(commandContext("claim-negative-key"), claimapp.CreateCommand{
		HomepageID:     "hp_material",
		ActorPersonaID: "persona_claimer",
		ClaimTier:      claimmodel.ClaimTierVerified,
	})
	assertClaimAppError(
		t, err, "ENTITY.USER.claim_material_missing", http.StatusBadRequest,
	)
}

func reviewableClaimAggregate(t *testing.T) *claimmodel.HomepageClaimRequest {
	t.Helper()
	aggregate, err := claimmodel.Create(claimmodel.CreateParams{
		ID:                 "hcr_review_negative",
		HomepageID:         "hp_review",
		RequesterPersonaID: "persona_requester",
		ClaimTier:          claimmodel.ClaimTierBasic,
		BusinessLicenseURL: "https://cdn.example.com/license.png",
		ContactPhone:       "+8613800000000",
		Now:                claimNegativeNow(),
	})
	if err != nil {
		t.Fatalf("build claim aggregate: %v", err)
	}
	return aggregate
}

func TestClaimSelfReviewEmitsPermissionDenied(t *testing.T) {
	t.Parallel()
	facade := claimNegativeFacade(
		t,
		stubClaimAggregates{loaded: reviewableClaimAggregate(t)},
		stubClaimHomepageGate{
			state: claimapp.HomepageState{Status: "published"},
			found: true,
		},
	)
	_, err := facade.Review(
		commandContext("claim-review-self"),
		claimapp.ReviewCommand{
			HomepageID:     "hp_review",
			ClaimRequestID: "hcr_review_negative",
			ActorAccountID: "persona_requester",
			TargetStatus:   claimmodel.StatusApproved,
		},
	)
	assertClaimAppError(t, err, "ENTITY.USER.permission_denied", http.StatusForbidden)
}

func TestClaimReviewTwiceEmitsVersionConflict(t *testing.T) {
	t.Parallel()
	aggregate := reviewableClaimAggregate(t)
	if err := aggregate.Review(claimmodel.ReviewParams{
		ReviewerAccountID: "account_reviewer",
		TargetStatus:      claimmodel.StatusApproved,
		Now:               claimNegativeNow(),
	}); err != nil {
		t.Fatalf("first review: %v", err)
	}
	facade := claimNegativeFacade(
		t,
		stubClaimAggregates{loaded: aggregate},
		stubClaimHomepageGate{
			state: claimapp.HomepageState{Status: "published"},
			found: true,
		},
	)
	_, err := facade.Review(
		commandContext("claim-review-twice"),
		claimapp.ReviewCommand{
			HomepageID:     "hp_review",
			ClaimRequestID: "hcr_review_negative",
			ActorAccountID: "account_reviewer_2",
			TargetStatus:   claimmodel.StatusRejected,
		},
	)
	assertClaimAppError(t, err, "ENTITY.USER.version_conflict", http.StatusConflict)
}

func TestClaimGetMyPendingWithoutRecordEmitsClaimNotFound(t *testing.T) {
	t.Parallel()
	facade := claimNegativeFacade(
		t,
		stubClaimAggregates{},
		stubClaimHomepageGate{
			state: claimapp.HomepageState{Status: "published"},
			found: true,
		},
	)
	_, err := facade.GetMyPending(
		context.Background(), "hp_none", "persona_claimer",
	)
	assertClaimAppError(t, err, "ENTITY.USER.claim_not_found", http.StatusNotFound)
}
