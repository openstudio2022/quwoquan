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

	"quwoquan_service/services/product-ops-service/internal/product_ops/account_enforcement_case/domain/ports"
	accountenforcementuser "quwoquan_service/services/product-ops-service/internal/product_ops/account_enforcement_case/infrastructure/useraccount"
)

const (
	productTestAppealIntakeRef  = "appeal_intake_AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
	productTestAppealAccountID  = "uo_01_ph_333a_01j00000000000000000000000"
	productOtherAppealAccountID = "uo_01_ph_2cdb_01j00000000000000000000001"
)

// spec_ref: specs/feature-tree/product-ops-growth/product-control-plane-foundation/account-moderation-and-appeal-enforcement/spec.md#gwt-002
func TestAppealIntakeHTTPClientClaimsExactTupleWithLeastPrivilegeWire(t *testing.T) {
	claimedAt := time.Date(2026, 7, 29, 9, 10, 11, 0, time.UTC)
	var captured *http.Request
	var capturedBody map[string]string
	client, err := accountenforcementuser.NewAppealIntakeHTTPClient(
		accountenforcementuser.AppealIntakeHTTPClientConfig{
			BaseURL: "https://user.internal/base",
			HTTPClient: &http.Client{Transport: roundTripFunc(func(
				request *http.Request,
			) (*http.Response, error) {
				captured = request.Clone(request.Context())
				if decodeErr := json.NewDecoder(request.Body).Decode(&capturedBody); decodeErr != nil {
					return nil, decodeErr
				}
				payload, marshalErr := json.Marshal(map[string]any{
					"intakeRef": productTestAppealIntakeRef, "accountId": productTestAppealAccountID,
					"caseId": "appeal-1", "status": "claimed",
					"claimedAt": claimedAt, "idempotentReplay": false,
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
			Credentials: localCredentials("Bearer scoped-user-claim-token"),
		},
	)
	if err != nil {
		t.Fatal(err)
	}
	claim := ports.AppealIntakeClaim{
		IntakeRef: productTestAppealIntakeRef, AccountID: productTestAppealAccountID, CaseID: "appeal-1",
	}
	if err := client.Claim(context.Background(), claim); err != nil {
		t.Fatal(err)
	}
	if captured == nil || captured.Method != http.MethodPost ||
		captured.URL.EscapedPath() != "/base/internal/user/account-appeal-intakes/"+productTestAppealIntakeRef+":claim" ||
		captured.Header.Get("Authorization") != "Bearer scoped-user-claim-token" ||
		captured.Header.Get("Idempotency-Key") != "appeal-intake-claim:appeal-1" ||
		captured.Header.Get("Cache-Control") != "no-store" ||
		captured.Header.Get("Content-Type") != "application/json" {
		t.Fatalf("unexpected User claim request: %+v", captured)
	}
	if len(capturedBody) != 2 || capturedBody["accountId"] != productTestAppealAccountID ||
		capturedBody["caseId"] != "appeal-1" {
		t.Fatalf("claim payload=%v, want exact accountId/caseId tuple", capturedBody)
	}
}

// spec_ref: specs/feature-tree/product-ops-growth/product-control-plane-foundation/account-moderation-and-appeal-enforcement/spec.md#gwt-002
func TestAppealIntakeHTTPClientMapsUserTypedErrorsFailClosed(t *testing.T) {
	tests := []struct {
		name   string
		status int
		code   string
		want   error
	}{
		{
			name: "missing intake", status: http.StatusNotFound,
			code: "USER.ACCOUNT.account_appeal_intake_not_found",
			want: ports.ErrAppealIntakeInvalid,
		},
		{
			name: "account mismatch", status: http.StatusConflict,
			code: "USER.ACCOUNT.account_appeal_intake_account_mismatch",
			want: ports.ErrAppealIntakeAccountMismatch,
		},
		{
			name: "claimed by another case", status: http.StatusConflict,
			code: "USER.ACCOUNT.account_appeal_intake_claimed",
			want: ports.ErrAppealIntakeConsumed,
		},
		{
			name: "account no longer suspended", status: http.StatusConflict,
			code: "USER.ACCOUNT.account_appeal_not_suspended",
			want: ports.ErrAppealIntakeInvalid,
		},
		{
			name: "user unavailable", status: http.StatusServiceUnavailable,
			code: "USER.SYSTEM.internal_error",
			want: ports.ErrAppealIntakeUnavailable,
		},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			client := newAppealIntakeResponseClient(t, test.status, map[string]any{
				"code": test.code,
			})
			err := client.Claim(context.Background(), ports.AppealIntakeClaim{
				IntakeRef: productTestAppealIntakeRef, AccountID: productTestAppealAccountID, CaseID: "appeal-1",
			})
			if !errors.Is(err, test.want) {
				t.Fatalf("Claim error=%v, want=%v", err, test.want)
			}
		})
	}
}

// spec_ref: specs/feature-tree/product-ops-growth/product-control-plane-foundation/account-moderation-and-appeal-enforcement/spec.md#gwt-002
func TestAppealIntakeHTTPClientRejectsNonCanonicalPathAndHeaderInputsBeforeTransport(t *testing.T) {
	tests := []struct {
		name  string
		claim ports.AppealIntakeClaim
	}{
		{
			name: "intake path separator",
			claim: ports.AppealIntakeClaim{
				IntakeRef: "appeal_intake_AAAAAAAAAAAAAAA/AAAAAAAAAAAAAAAA",
				AccountID: productTestAppealAccountID, CaseID: "appeal-1",
			},
		},
		{
			name: "account transport separator",
			claim: ports.AppealIntakeClaim{
				IntakeRef: productTestAppealIntakeRef,
				AccountID: "account/1", CaseID: "appeal-1",
			},
		},
		{
			name: "case header delimiter",
			claim: ports.AppealIntakeClaim{
				IntakeRef: productTestAppealIntakeRef,
				AccountID: productTestAppealAccountID, CaseID: "appeal:1",
			},
		},
		{
			name: "case header newline",
			claim: ports.AppealIntakeClaim{
				IntakeRef: productTestAppealIntakeRef,
				AccountID: productTestAppealAccountID, CaseID: "appeal-1\r\nInjected: true",
			},
		},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			transportCalls := 0
			client, err := accountenforcementuser.NewAppealIntakeHTTPClient(
				accountenforcementuser.AppealIntakeHTTPClientConfig{
					BaseURL: "https://user.internal",
					HTTPClient: &http.Client{Transport: roundTripFunc(func(
						request *http.Request,
					) (*http.Response, error) {
						transportCalls++
						return nil, errors.New("transport must not receive invalid tuple")
					})},
					Credentials: localCredentials("Bearer scoped-user-claim-token"),
				},
			)
			if err != nil {
				t.Fatal(err)
			}
			err = client.Claim(context.Background(), test.claim)
			if !errors.Is(err, ports.ErrAppealIntakeInvalid) || transportCalls != 0 {
				t.Fatalf("Claim error=%v transportCalls=%d", err, transportCalls)
			}
		})
	}
}

// spec_ref: specs/feature-tree/product-ops-growth/product-control-plane-foundation/account-moderation-and-appeal-enforcement/spec.md#gwt-002
func TestAppealIntakeHTTPClientLeavesUserOwnedOpaqueFormatsToUserTypedValidation(t *testing.T) {
	transportCalls := 0
	client, err := accountenforcementuser.NewAppealIntakeHTTPClient(
		accountenforcementuser.AppealIntakeHTTPClientConfig{
			BaseURL: "https://user.internal",
			HTTPClient: &http.Client{Transport: roundTripFunc(func(
				request *http.Request,
			) (*http.Response, error) {
				transportCalls++
				return &http.Response{
					StatusCode: http.StatusBadRequest,
					Header:     make(http.Header),
					Body: io.NopCloser(strings.NewReader(
						`{"code":"USER.USER.invalid_argument"}`,
					)),
					Request: request,
				}, nil
			})},
			Credentials: localCredentials("Bearer scoped-user-claim-token"),
		},
	)
	if err != nil {
		t.Fatal(err)
	}
	err = client.Claim(context.Background(), ports.AppealIntakeClaim{
		IntakeRef: "transport-safe-opaque-ref",
		AccountID: "transport.safe.account",
		CaseID:    "appeal-1",
	})
	if !errors.Is(err, ports.ErrAppealIntakeInvalid) || transportCalls != 1 {
		t.Fatalf("Claim error=%v transportCalls=%d", err, transportCalls)
	}
}

// spec_ref: specs/feature-tree/product-ops-growth/product-control-plane-foundation/account-moderation-and-appeal-enforcement/spec.md#gwt-002
func TestAppealIntakeHTTPClientRejectsNonExactClaimReceipt(t *testing.T) {
	valid := map[string]any{
		"intakeRef": productTestAppealIntakeRef, "accountId": productTestAppealAccountID, "caseId": "appeal-1",
		"status": "claimed", "claimedAt": time.Date(2026, 7, 29, 10, 0, 0, 0, time.UTC),
		"idempotentReplay": true,
	}
	tests := []struct {
		name   string
		mutate func(map[string]any)
	}{
		{name: "different case", mutate: func(body map[string]any) { body["caseId"] = "appeal-other" }},
		{name: "different account", mutate: func(body map[string]any) { body["accountId"] = productOtherAppealAccountID }},
		{name: "unknown response field", mutate: func(body map[string]any) { body["credential"] = "must-not-pass" }},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			body := make(map[string]any, len(valid)+1)
			for key, value := range valid {
				body[key] = value
			}
			test.mutate(body)
			client := newAppealIntakeResponseClient(t, http.StatusOK, body)
			err := client.Claim(context.Background(), ports.AppealIntakeClaim{
				IntakeRef: productTestAppealIntakeRef, AccountID: productTestAppealAccountID, CaseID: "appeal-1",
			})
			if !errors.Is(err, ports.ErrAppealIntakeUnavailable) {
				t.Fatalf("Claim error=%v, want unavailable", err)
			}
		})
	}
}

func newAppealIntakeResponseClient(
	t *testing.T,
	status int,
	body map[string]any,
) *accountenforcementuser.AppealIntakeHTTPClient {
	t.Helper()
	payload, err := json.Marshal(body)
	if err != nil {
		t.Fatal(err)
	}
	client, err := accountenforcementuser.NewAppealIntakeHTTPClient(
		accountenforcementuser.AppealIntakeHTTPClientConfig{
			BaseURL: "https://user.internal",
			HTTPClient: &http.Client{Transport: roundTripFunc(func(
				request *http.Request,
			) (*http.Response, error) {
				return &http.Response{
					StatusCode: status,
					Header:     make(http.Header),
					Body:       io.NopCloser(strings.NewReader(string(payload))),
					Request:    request,
				}, nil
			})},
			Credentials: localCredentials("Bearer scoped-user-claim-token"),
		},
	)
	if err != nil {
		t.Fatal(err)
	}
	return client
}
