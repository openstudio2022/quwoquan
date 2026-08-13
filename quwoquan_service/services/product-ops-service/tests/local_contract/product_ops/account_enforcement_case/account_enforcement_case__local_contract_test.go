package local_contract

import (
	"context"
	"encoding/json"
	"errors"
	"io"
	"net/http"
	"reflect"
	"strings"
	"testing"
	"time"

	"quwoquan_service/services/product-ops-service/internal/product_ops/account_enforcement_case/application"
	"quwoquan_service/services/product-ops-service/internal/product_ops/account_enforcement_case/domain/model"
	"quwoquan_service/services/product-ops-service/internal/product_ops/account_enforcement_case/domain/ports"
	accountenforcementuser "quwoquan_service/services/product-ops-service/internal/product_ops/account_enforcement_case/infrastructure/useraccount"
)

// spec_ref: specs/feature-tree/product-ops-growth/product-control-plane-foundation/account-moderation-and-appeal-enforcement/spec.md#gwt-001
// readiness_case: open-account-moderation-case-local
// readiness_case: review-account-enforcement-case-local
func TestModerationCaseRequiresTwoDistinctApproversAndIssuesOneSuspendDecision(t *testing.T) {
	now := time.Date(2026, 7, 29, 1, 2, 3, 0, time.UTC)
	current, err := model.OpenModeration(model.OpenModerationParams{
		CaseID: "moderation-1", AccountID: "account-1", PolicyRef: "policy/account-safety",
		EvidenceRefs: []string{"evidence-2", "evidence-1", "evidence-1"},
		OpenedBy:     "operator-opener", OpenedAt: now,
	})
	if err != nil {
		t.Fatal(err)
	}
	first, _, decision, err := current.Review("operator-1", model.ReviewVerdictApprove, now.Add(time.Minute))
	if err != nil || decision != nil || first.Status != model.CaseStatusPendingApproval {
		t.Fatalf("first approval: case=%+v decision=%+v err=%v", first, decision, err)
	}
	if _, _, _, err := first.Review("operator-1", model.ReviewVerdictApprove, now.Add(2*time.Minute)); !errors.Is(err, model.ErrReviewConflict) {
		t.Fatalf("same reviewer error=%v, want ErrReviewConflict", err)
	}
	approved, _, decision, err := first.Review("operator-2", model.ReviewVerdictApprove, now.Add(2*time.Minute))
	if err != nil || decision == nil {
		t.Fatalf("second approval: case=%+v decision=%+v err=%v", approved, decision, err)
	}
	if approved.Status != model.CaseStatusApproved ||
		decision.Action != model.EnforcementActionSuspend ||
		decision.CaseRef != "ops.account_enforcement_case/moderation-1" ||
		len(decision.DecisionDigest) != 64 || decision.ID == "" {
		t.Fatalf("unexpected approved decision: case=%+v decision=%+v", approved, decision)
	}
	if _, _, _, err := approved.Review("operator-3", model.ReviewVerdictReject, now.Add(3*time.Minute)); !errors.Is(err, model.ErrCaseClosed) {
		t.Fatalf("closed review error=%v, want ErrCaseClosed", err)
	}
}

// spec_ref: specs/feature-tree/product-ops-growth/product-control-plane-foundation/account-moderation-and-appeal-enforcement/spec.md#gwt-002
// readiness_case: open-account-appeal-case-local
func TestAppealCaseIsExplicitAndCanOnlyIssueRestore(t *testing.T) {
	now := time.Date(2026, 7, 29, 2, 3, 4, 0, time.UTC)
	current, err := model.OpenAppeal(model.OpenAppealParams{
		CaseID: "appeal-1", AccountID: "account-1", SourceDecisionID: "suspend-decision-1",
		IntakeRef: "official-intake-1", EvidenceRefs: []string{"appeal-evidence-1"},
		OpenedBy: "operator-opener", OpenedAt: now,
	})
	if err != nil {
		t.Fatal(err)
	}
	first, _, _, err := current.Review("operator-1", model.ReviewVerdictApprove, now.Add(time.Minute))
	if err != nil {
		t.Fatal(err)
	}
	approved, _, decision, err := first.Review("operator-2", model.ReviewVerdictApprove, now.Add(2*time.Minute))
	if err != nil || decision == nil || approved.Status != model.CaseStatusApproved {
		t.Fatalf("approve appeal: case=%+v decision=%+v err=%v", approved, decision, err)
	}
	if decision.Action != model.EnforcementActionRestore {
		t.Fatalf("appeal action=%q, want restore", decision.Action)
	}
	if _, err := model.OpenAppeal(model.OpenAppealParams{
		CaseID: "appeal-invalid", AccountID: "account-1", EvidenceRefs: []string{"evidence"},
		OpenedBy: "operator", OpenedAt: now,
	}); !errors.Is(err, model.ErrInvalidArgument) {
		t.Fatalf("appeal without source/intake error=%v, want invalid", err)
	}
}

// spec_ref: specs/feature-tree/product-ops-growth/product-control-plane-foundation/account-moderation-and-appeal-enforcement/spec.md#gwt-001
// spec_ref: specs/feature-tree/product-ops-growth/product-control-plane-foundation/account-moderation-and-appeal-enforcement/spec.md#gwt-001.t4
func TestRejectClosesCaseWithoutDecision(t *testing.T) {
	now := time.Date(2026, 7, 29, 3, 4, 5, 0, time.UTC)
	current, err := model.OpenModeration(model.OpenModerationParams{
		CaseID: "moderation-reject", AccountID: "account-2", PolicyRef: "policy-1",
		EvidenceRefs: []string{"evidence-1"}, OpenedBy: "operator-1", OpenedAt: now,
	})
	if err != nil {
		t.Fatal(err)
	}
	rejected, _, decision, err := current.Review("operator-2", model.ReviewVerdictReject, now.Add(time.Minute))
	if err != nil || decision != nil || rejected.Status != model.CaseStatusRejected {
		t.Fatalf("reject: case=%+v decision=%+v err=%v", rejected, decision, err)
	}
}

// spec_ref: specs/feature-tree/product-ops-growth/product-control-plane-foundation/account-moderation-and-appeal-enforcement/spec.md#gwt-001
func TestUserAccountDeliveryUsesStableMinimalWireAndEscapedAccountPath(t *testing.T) {
	approvedAt := time.Date(2026, 7, 29, 4, 5, 6, 0, time.UTC)
	var captured *http.Request
	var capturedPayload map[string]any
	client, err := accountenforcementuser.NewHTTPClient(accountenforcementuser.HTTPClientConfig{
		BaseURL: "https://user.internal/base",
		HTTPClient: &http.Client{Transport: roundTripFunc(func(request *http.Request) (*http.Response, error) {
			captured = request.Clone(request.Context())
			if decodeErr := json.NewDecoder(request.Body).Decode(&capturedPayload); decodeErr != nil {
				return nil, decodeErr
			}
			payload, marshalErr := json.Marshal(map[string]any{
				"accountState": "suspended", "authEpoch": 9,
				"decisionId": "decision-1", "idempotentReplay": false,
				"occurredAt": approvedAt.Add(time.Second),
			})
			if marshalErr != nil {
				return nil, marshalErr
			}
			return &http.Response{
				StatusCode: http.StatusOK,
				Header:     make(http.Header),
				Body:       io.NopCloser(strings.NewReader(string(payload))),
				Request:    request,
			}, nil
		})},
		Credentials: localCredentials("Bearer product-ops-service-token"),
	})
	if err != nil {
		t.Fatal(err)
	}
	receipt, err := client.Publish(context.Background(), model.Decision{
		ID: "decision-1", CaseID: "case-1", AccountID: "account / opaque",
		Action: model.EnforcementActionSuspend, CaseRef: "ops.account_enforcement_case/case-1",
		DecisionDigest: strings.Repeat("a", 64), ApprovedAt: approvedAt,
	})
	if err != nil {
		t.Fatal(err)
	}
	if captured == nil ||
		captured.URL.EscapedPath() != "/base/internal/user/accounts/account%20%2F%20opaque/suspend" ||
		captured.Header.Get("Authorization") != "Bearer product-ops-service-token" ||
		captured.Header.Get("Idempotency-Key") != "decision-1" ||
		captured.Header.Get("Cache-Control") != "no-store" {
		t.Fatalf("unexpected UserAccount request: %+v", captured)
	}
	wantPayload := map[string]any{
		"decisionId": "decision-1", "caseRef": "ops.account_enforcement_case/case-1",
		"decisionDigest": strings.Repeat("a", 64), "approvedAt": approvedAt.Format(time.RFC3339Nano),
	}
	if !reflect.DeepEqual(capturedPayload, wantPayload) {
		t.Fatalf("UserAccount payload = %#v, want %#v", capturedPayload, wantPayload)
	}
	if receipt.DecisionID != "decision-1" || receipt.AccountState != "suspended" ||
		receipt.AuthEpoch != 9 {
		t.Fatalf("unexpected delivery receipt: %+v", receipt)
	}
}

// spec_ref: specs/feature-tree/product-ops-growth/product-control-plane-foundation/account-moderation-and-appeal-enforcement/spec.md#gwt-001
// readiness_case: retry-account-enforcement-delivery-local
// readiness_case: get-account-enforcement-case-local
func TestRetryDeliveryAndGetUseTheCanonicalCaseStore(t *testing.T) {
	now := time.Date(2026, 8, 5, 10, 0, 0, 0, time.UTC)
	current, err := model.OpenModeration(model.OpenModerationParams{
		CaseID: "moderation-readiness", AccountID: "account-readiness",
		PolicyRef: "policy/account-safety", EvidenceRefs: []string{"evidence-readiness"},
		OpenedBy: "operator-readiness", OpenedAt: now,
	})
	if err != nil {
		t.Fatal(err)
	}
	store := &readinessCaseStore{current: current}
	service := application.NewService(store, nil, nil)

	got, err := service.Get(context.Background(), current.ID)
	if err != nil || got.CaseID != current.ID || got.Version != current.Version {
		t.Fatalf("Get() = %+v, %v", got, err)
	}
	retried, err := service.RetryDelivery(context.Background(), application.RetryDeliveryCommand{
		CaseID: current.ID, ActorID: "operator-recovery", IdempotencyKey: "retry-readiness",
	})
	if err != nil || retried.CaseID != current.ID || !store.recovered {
		t.Fatalf("RetryDelivery() = %+v, recovered=%v, err=%v", retried, store.recovered, err)
	}
	if store.recoveryReceipt.CaseID != current.ID ||
		store.recoveryReceipt.IdempotencyKey != "retry-readiness" {
		t.Fatalf("recovery receipt = %+v", store.recoveryReceipt)
	}
}

type readinessCaseStore struct {
	current         model.Case
	recovered       bool
	recoveryReceipt ports.CommandReceipt
}

func (*readinessCaseStore) Replay(
	context.Context,
	string,
	string,
) (ports.CaseSnapshot, bool, error) {
	return ports.CaseSnapshot{}, false, nil
}

func (*readinessCaseStore) CommitOpen(
	context.Context,
	model.Case,
	ports.CommandReceipt,
) (ports.CaseSnapshot, error) {
	return ports.CaseSnapshot{}, errors.New("unexpected CommitOpen")
}

func (store *readinessCaseStore) Load(
	_ context.Context,
	caseID string,
) (model.Case, error) {
	if caseID != store.current.ID {
		return model.Case{}, model.ErrCaseNotFound
	}
	return store.current, nil
}

func (*readinessCaseStore) CommitReview(
	context.Context,
	int64,
	model.Case,
	model.Review,
	*model.Decision,
	ports.CommandReceipt,
) (ports.CaseSnapshot, error) {
	return ports.CaseSnapshot{}, errors.New("unexpected CommitReview")
}

func (store *readinessCaseStore) RecoverDelivery(
	_ context.Context,
	caseID string,
	receipt ports.CommandReceipt,
	_ time.Time,
) (ports.CaseSnapshot, error) {
	if caseID != store.current.ID {
		return ports.CaseSnapshot{}, model.ErrCaseNotFound
	}
	store.recovered = true
	store.recoveryReceipt = receipt
	return ports.CaseSnapshot{Case: store.current}, nil
}

var _ ports.CaseStore = (*readinessCaseStore)(nil)

type localCredentials string

func (credentials localCredentials) AuthorizationHeader(context.Context) (string, error) {
	return string(credentials), nil
}

type roundTripFunc func(*http.Request) (*http.Response, error)

func (function roundTripFunc) RoundTrip(request *http.Request) (*http.Response, error) {
	return function(request)
}
