// spec_ref: specs/feature-tree/user-identity-profile-relationship/settings-and-device-token/account-suspension-and-appeal-lifecycle/spec.md#gwt-001
// spec_ref: specs/feature-tree/user-identity-profile-relationship/settings-and-device-token/account-suspension-and-appeal-lifecycle/spec.md#gwt-003
// readiness_case: suspend-account-api
// readiness_case: restore-account-api
package api_integration

import (
	"fmt"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

const enforcementDecisionBody = `{"decisionId":"decision-http-suspend","caseRef":"moderation-case-opaque","decisionDigest":"sha256-opaque","approvedAt":"2026-07-28T10:00:00Z"}`

func TestAccountEnforcementHTTPRejectsUntrustedOrUnscopedCallers(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })
	const accountID = "enforcement-http-denied"
	createTestProfile(t, accountID, "Enforcement HTTP Denied")

	for name, headers := range map[string]map[string]string{
		"different scoped service": serviceHeadersFor(
			"service:content-service",
			"user.account.enforcement.write",
		),
		"product ops missing scope": serviceHeadersFor(
			"service:product-ops-service",
			"product.ops.read",
		),
		"end user": authHeaders(accountID),
	} {
		t.Run(name, func(t *testing.T) {
			headers["Idempotency-Key"] = "decision-http-suspend"
			response := doAccountEnforcementRequest(
				t,
				http.MethodPost,
				"/internal/user/accounts/"+accountID+"/suspend",
				enforcementDecisionBody,
				headers,
			)
			if response.Code != http.StatusForbidden {
				t.Fatalf(
					"untrusted enforcement status=%d body=%s",
					response.Code,
					response.Body.String(),
				)
			}
		})
	}
}

func TestAccountEnforcementHTTPBindsDecisionToIdempotencyAndStrictBody(
	t *testing.T,
) {
	t.Cleanup(func() { cleanAll(t) })
	const accountID = "enforcement-http-invalid"
	createTestProfile(t, accountID, "Enforcement HTTP Invalid")
	trusted := serviceHeadersFor(
		"service:product-ops-service",
		"user.account.enforcement.write",
	)
	trusted["Idempotency-Key"] = "different-decision"
	response := doAccountEnforcementRequest(
		t,
		http.MethodPost,
		"/internal/user/accounts/"+accountID+"/suspend",
		enforcementDecisionBody,
		trusted,
	)
	if response.Code != http.StatusBadRequest {
		t.Fatalf(
			"idempotency mismatch status=%d body=%s",
			response.Code,
			response.Body.String(),
		)
	}

	trusted["Idempotency-Key"] = "decision-http-suspend"
	unknownFieldBody := strings.TrimSuffix(enforcementDecisionBody, "}") +
		`,"evidence":"must-not-cross-boundary"}`
	response = doAccountEnforcementRequest(
		t,
		http.MethodPost,
		"/internal/user/accounts/"+accountID+"/suspend",
		unknownFieldBody,
		trusted,
	)
	if response.Code != http.StatusBadRequest {
		t.Fatalf(
			"unknown decision evidence status=%d body=%s",
			response.Code,
			response.Body.String(),
		)
	}
}

func TestAccountEnforcementHTTPExecutesTrustedSuspendReplayAndRestore(
	t *testing.T,
) {
	t.Cleanup(func() { cleanAll(t) })
	const accountID = "enforcement-http-trusted"
	createTestProfile(t, accountID, "Enforcement HTTP Trusted")
	trusted := serviceHeadersFor(
		"service:product-ops-service",
		"user.account.enforcement.write",
	)
	trusted["Idempotency-Key"] = "decision-http-suspend"
	path := "/internal/user/accounts/" + accountID + "/suspend"

	response := doAccountEnforcementRequest(
		t,
		http.MethodPost,
		path,
		enforcementDecisionBody,
		trusted,
	)
	if response.Code != http.StatusOK {
		t.Fatalf("trusted suspend status=%d body=%s", response.Code, response.Body.String())
	}
	body := parseJSON(t, response)
	if body["accountState"] != "suspended" || body["authEpoch"] != float64(2) ||
		body["idempotentReplay"] != false {
		t.Fatalf("trusted suspend response=%#v", body)
	}

	response = doAccountEnforcementRequest(
		t,
		http.MethodPost,
		path,
		enforcementDecisionBody,
		trusted,
	)
	if response.Code != http.StatusOK || parseJSON(t, response)["idempotentReplay"] != true {
		t.Fatalf("trusted suspend replay status=%d body=%s", response.Code, response.Body.String())
	}

	trusted["Idempotency-Key"] = "decision-http-restore"
	restoreBody := `{"decisionId":"decision-http-restore","caseRef":"appeal-case-opaque","decisionDigest":"sha256-restore-opaque","approvedAt":"2026-07-28T11:00:00Z"}`
	response = doAccountEnforcementRequest(
		t,
		http.MethodPost,
		"/internal/user/accounts/"+accountID+"/restore",
		restoreBody,
		trusted,
	)
	if response.Code != http.StatusOK {
		t.Fatalf("trusted restore status=%d body=%s", response.Code, response.Body.String())
	}
	body = parseJSON(t, response)
	if body["accountState"] != "active" || body["authEpoch"] != float64(3) {
		t.Fatalf("trusted restore response=%#v", body)
	}
}

func doAccountEnforcementRequest(
	t *testing.T,
	method string,
	path string,
	body string,
	headers map[string]string,
) *httptest.ResponseRecorder {
	t.Helper()
	request := httptest.NewRequest(method, path, strings.NewReader(body))
	request.Header.Set("Content-Type", "application/json")
	request.Header.Set(
		"Idempotency-Key",
		fmt.Sprintf("enforcement-http-%s", t.Name()),
	)
	for key, value := range headers {
		request.Header.Set(key, value)
	}
	response := httptest.NewRecorder()
	testAccountEnforcementHandler.ServeHTTP(response, request)
	return response
}
