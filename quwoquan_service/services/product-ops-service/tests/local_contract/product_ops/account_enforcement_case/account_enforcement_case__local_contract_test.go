package local_contract

import (
	"context"
	"encoding/json"
	"errors"
	"io"
	"net/http"
	"strings"
	"testing"
	"time"

	"quwoquan_service/services/product-ops-service/internal/product_ops/account_enforcement_case/domain/model"
	accountenforcementuser "quwoquan_service/services/product-ops-service/internal/product_ops/account_enforcement_case/infrastructure/useraccount"
)

// spec_ref: specs/feature-tree/product-ops-growth/product-control-plane-foundation/account-moderation-and-appeal-enforcement/spec.md#gwt-001
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
	client, err := accountenforcementuser.NewHTTPClient(accountenforcementuser.HTTPClientConfig{
		BaseURL: "https://user.internal/base",
		HTTPClient: &http.Client{Transport: roundTripFunc(func(request *http.Request) (*http.Response, error) {
			captured = request.Clone(request.Context())
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
	receipt, err := client.Apply(context.Background(), model.Decision{
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
	if receipt.DecisionID != "decision-1" || receipt.AccountState != "suspended" ||
		receipt.AuthEpoch != 9 {
		t.Fatalf("unexpected delivery receipt: %+v", receipt)
	}
}

type localCredentials string

func (credentials localCredentials) AuthorizationHeader(context.Context) (string, error) {
	return string(credentials), nil
}

type roundTripFunc func(*http.Request) (*http.Response, error)

func (function roundTripFunc) RoundTrip(request *http.Request) (*http.Response, error) {
	return function(request)
}
