// spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-002
// readiness_case: get-research-session-attestation-local
package local_contract

import (
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	rtauth "quwoquan_service/runtime/auth"
	"quwoquan_service/runtime/auth/researchidentity"
	"quwoquan_service/runtime/operation"
	researchhttp "quwoquan_service/services/user-service/internal/account/account_session/adapters/inbound/http"
	sessionapp "quwoquan_service/services/user-service/internal/account/account_session/application"
)

const researchAttestationTestKey = "research-attestation-key-32-bytes-long"

func issueResearchAttestation(
	t *testing.T,
	accountID string,
	issuedAt time.Time,
	ttl time.Duration,
) (researchidentity.VerifiedAttestation, string) {
	t.Helper()
	authority, err := researchidentity.NewAuthority([]byte(researchAttestationTestKey))
	if err != nil {
		t.Fatal(err)
	}
	verified, token, err := authority.Issue(
		accountID,
		issuedAt,
		issuedAt.Add(ttl),
		[]byte(strings.Repeat("n", 32)),
	)
	if err != nil {
		t.Fatal(err)
	}
	return verified, token
}

func newResearchSessionQueryFacade(t *testing.T) *sessionapp.ResearchSessionQueryFacade {
	t.Helper()
	facade, err := sessionapp.NewResearchSessionQueryFacade(
		[]byte(researchAttestationTestKey),
	)
	if err != nil {
		t.Fatalf("new research session query facade: %v", err)
	}
	return facade
}

func TestGetResearchSessionAttestationReturnsVerifiedIrreversibleIdentity(
	t *testing.T,
) {
	issuedAt := time.Now().UTC().Add(-time.Minute)
	verified, token := issueResearchAttestation(t, "research-account", issuedAt, 5*time.Minute)
	facade := newResearchSessionQueryFacade(t)

	view, err := facade.GetResearchSessionAttestation(
		context.Background(),
		"research-account",
		token,
	)
	if err != nil {
		t.Fatalf("get research session attestation: %v", err)
	}
	if view.SubjectHash != verified.SubjectHash ||
		!strings.HasPrefix(view.SubjectHash, "sha256:") ||
		view.AttestationID != token ||
		!view.ExpiresAt.Equal(verified.ExpiresAt) {
		t.Fatalf("attestation readback is not bound to the verified proof: %+v", view)
	}
	if strings.Contains(view.SubjectHash, "research-account") ||
		strings.Contains(view.AttestationID, "research-account") {
		t.Fatal("attestation readback must not expose the reversible account identity")
	}
}

func TestGetResearchSessionAttestationFailsClosedOnInvalidProof(t *testing.T) {
	issuedAt := time.Now().UTC().Add(-time.Minute)
	_, token := issueResearchAttestation(t, "research-account", issuedAt, 5*time.Minute)
	expiredIssuedAt := time.Now().UTC().Add(-2 * time.Minute)
	_, expiredToken := issueResearchAttestation(t, "research-account", expiredIssuedAt, time.Minute)
	facade := newResearchSessionQueryFacade(t)

	for _, test := range []struct {
		name      string
		accountID string
		token     string
	}{
		{name: "missing attestation", accountID: "research-account", token: "   "},
		{name: "tampered attestation", accountID: "research-account", token: token + "x"},
		{name: "expired attestation", accountID: "research-account", token: expiredToken},
		{name: "account drift", accountID: "another-account", token: token},
		{name: "missing account", accountID: "", token: token},
	} {
		t.Run(test.name, func(t *testing.T) {
			view, err := facade.GetResearchSessionAttestation(
				context.Background(),
				test.accountID,
				test.token,
			)
			if !errors.Is(err, sessionapp.ErrResearchIdentityInvalid) ||
				view != (sessionapp.ResearchSessionAttestationView{}) {
				t.Fatalf("expected fail-closed invalid identity, view=%+v err=%v", view, err)
			}
		})
	}
}

func TestResearchSessionAttestationHTTPSecurity(t *testing.T) {
	issuedAt := time.Now().UTC().Add(-time.Minute)
	verified, token := issueResearchAttestation(t, "research-account", issuedAt, 5*time.Minute)
	expiredIssuedAt := time.Now().UTC().Add(-2 * time.Minute)
	_, expiredToken := issueResearchAttestation(t, "research-account", expiredIssuedAt, time.Minute)

	tests := []struct {
		name        string
		accountID   string
		attestation string
		wantStatus  int
	}{
		{
			name:        "verified account with valid attestation",
			accountID:   "research-account",
			attestation: token,
			wantStatus:  http.StatusOK,
		},
		{
			name:        "anonymous request is denied",
			attestation: token,
			wantStatus:  http.StatusUnauthorized,
		},
		{
			name:       "missing attestation header is denied",
			accountID:  "research-account",
			wantStatus: http.StatusForbidden,
		},
		{
			name:        "tampered attestation is denied",
			accountID:   "research-account",
			attestation: token + "x",
			wantStatus:  http.StatusForbidden,
		},
		{
			name:        "expired attestation is denied",
			accountID:   "research-account",
			attestation: expiredToken,
			wantStatus:  http.StatusForbidden,
		},
		{
			name:        "attestation bound to another account is denied",
			accountID:   "another-account",
			attestation: token,
			wantStatus:  http.StatusForbidden,
		},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			handler, err := researchhttp.NewResearchSessionAttestationHandler(
				newResearchSessionQueryFacade(t),
			)
			if err != nil {
				t.Fatal(err)
			}
			mux := http.NewServeMux()
			handler.RegisterRoutes(mux)
			request := httptest.NewRequest(
				http.MethodGet,
				researchhttp.ResearchSessionAttestationPath,
				nil,
			)
			if test.attestation != "" {
				request.Header.Set(
					researchhttp.ResearchIdentityAttestationHeader,
					test.attestation,
				)
			}
			if test.accountID != "" {
				request = request.WithContext(rtauth.WithPrincipal(
					request.Context(),
					rtauth.Principal{Actor: operation.ActorContext{AccountID: test.accountID}},
				))
			}
			response := httptest.NewRecorder()
			mux.ServeHTTP(response, request)
			if response.Code != test.wantStatus {
				t.Fatalf(
					"status=%d want=%d body=%s",
					response.Code, test.wantStatus, response.Body.String(),
				)
			}
			if test.accountID != "" &&
				strings.Contains(response.Body.String(), test.accountID) {
				t.Fatalf("response exposed account identity: %s", response.Body.String())
			}
			if test.wantStatus != http.StatusOK {
				return
			}
			var view struct {
				SubjectHash   string    `json:"subjectHash"`
				AttestationID string    `json:"attestationId"`
				ExpiresAt     time.Time `json:"expiresAt"`
			}
			if err := json.Unmarshal(response.Body.Bytes(), &view); err != nil {
				t.Fatalf("decode attestation readback: %v", err)
			}
			if view.SubjectHash != verified.SubjectHash ||
				view.AttestationID != token ||
				!view.ExpiresAt.Equal(verified.ExpiresAt) {
				t.Fatalf("attestation readback drifted from issued proof: %+v", view)
			}
		})
	}
}

func TestUnavailableResearchSessionQueryFacadeFailsClosed(t *testing.T) {
	issuedAt := time.Now().UTC().Add(-time.Minute)
	_, token := issueResearchAttestation(t, "research-account", issuedAt, 5*time.Minute)
	facade := sessionapp.NewUnavailableResearchSessionQueryFacade()
	view, err := facade.GetResearchSessionAttestation(
		context.Background(),
		"research-account",
		token,
	)
	if !errors.Is(err, sessionapp.ErrResearchIdentityUnavailable) ||
		view != (sessionapp.ResearchSessionAttestationView{}) {
		t.Fatalf("unavailable facade must fail closed, view=%+v err=%v", view, err)
	}
}
