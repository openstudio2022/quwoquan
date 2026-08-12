// spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-002
// readiness_case: issue-whitelisted-research-session-local
package local_contract

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	rtauth "quwoquan_service/runtime/auth"
	runtimemessaging "quwoquan_service/runtime/messaging"
	"quwoquan_service/runtime/operation"
	researchhttp "quwoquan_service/services/user-service/internal/account/account_session/adapters/inbound/http"
	sessionapp "quwoquan_service/services/user-service/internal/account/account_session/application"
	researchmessaging "quwoquan_service/services/user-service/internal/account/account_session/infrastructure/messaging"
)

type researchSessionAuditProbe struct {
	records []sessionapp.ResearchSessionAuditRecord
	err     error
}

func (probe *researchSessionAuditProbe) AppendResearchSessionIssued(
	_ context.Context,
	record sessionapp.ResearchSessionAuditRecord,
) error {
	probe.records = append(probe.records, record)
	return probe.err
}

func newResearchSessionFacade(
	t *testing.T,
	audit sessionapp.ResearchSessionAuditAppender,
) *sessionapp.ResearchSessionCommandFacade {
	t.Helper()
	facade, err := sessionapp.NewResearchSessionCommandFacade(
		[]string{"research-account"},
		[]byte("research-attestation-key-32-bytes-long"),
		5*time.Minute,
		audit,
	)
	if err != nil {
		t.Fatalf("new research session facade: %v", err)
	}
	return facade
}

func TestIssueWhitelistedResearchSessionUsesIrreversibleAuditIdentity(
	t *testing.T,
) {
	audit := &researchSessionAuditProbe{}
	facade := newResearchSessionFacade(t, audit)
	before := time.Now().UTC()

	result, err := facade.IssueWhitelistedResearchSession(
		context.Background(),
		"research-account",
	)
	if err != nil {
		t.Fatalf("issue whitelisted research session: %v", err)
	}
	if !strings.HasPrefix(result.SubjectHash, "sha256:") ||
		result.SubjectHash == "research-account" ||
		result.AttestationID == "" {
		t.Fatalf("research session did not return irreversible signed identity: %+v", result)
	}
	if strings.Contains(result.AttestationID, "research-account") {
		t.Fatal("research attestation must not expose the account identity")
	}
	if result.ExpiresAt.Before(before.Add(4*time.Minute+50*time.Second)) ||
		result.ExpiresAt.After(before.Add(5*time.Minute+10*time.Second)) {
		t.Fatalf("research session expiry is outside the governed TTL: %s", result.ExpiresAt)
	}
	if len(audit.records) != 1 {
		t.Fatalf("research session must append exactly one durable audit record: %+v", audit.records)
	}
	record := audit.records[0]
	if record.SubjectHash != result.SubjectHash ||
		!strings.HasPrefix(record.AttestationIDHash, "sha256:") ||
		record.AttestationIDHash == result.AttestationID ||
		!record.ExpiresAt.Equal(result.ExpiresAt) {
		t.Fatalf("research session audit record is not safely bound: %+v", record)
	}
}

func TestIssueWhitelistedResearchSessionRejectsUnlistedAccountWithoutAudit(
	t *testing.T,
) {
	audit := &researchSessionAuditProbe{}
	facade := newResearchSessionFacade(t, audit)

	result, err := facade.IssueWhitelistedResearchSession(
		context.Background(),
		"unlisted-account",
	)
	if !errors.Is(err, sessionapp.ErrResearchIdentityForbidden) {
		t.Fatalf("unlisted account error=%v", err)
	}
	if result != (sessionapp.ResearchSessionResult{}) || len(audit.records) != 0 {
		t.Fatalf("unlisted account must not produce identity or audit: %+v", result)
	}
}

func TestIssueWhitelistedResearchSessionFailsClosedWhenAuditAppendFails(
	t *testing.T,
) {
	audit := &researchSessionAuditProbe{err: errors.New("audit unavailable")}
	facade := newResearchSessionFacade(t, audit)

	result, err := facade.IssueWhitelistedResearchSession(
		context.Background(),
		"research-account",
	)
	if !errors.Is(err, sessionapp.ErrResearchIdentityUnavailable) {
		t.Fatalf("audit failure error=%v", err)
	}
	if result != (sessionapp.ResearchSessionResult{}) || len(audit.records) != 1 {
		t.Fatalf("audit failure must not return a session: result=%+v records=%+v", result, audit.records)
	}
}

func TestResearchSessionHTTPUsesOnlyVerifiedPrincipal(t *testing.T) {
	tests := []struct {
		name       string
		accountID  string
		wantStatus int
		wantAudit  int
	}{
		{name: "verified allowlisted account", accountID: "research-account", wantStatus: http.StatusOK, wantAudit: 1},
		{name: "verified unlisted account", accountID: "unlisted-account", wantStatus: http.StatusForbidden},
		{name: "missing verified principal", wantStatus: http.StatusUnauthorized},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			audit := &researchSessionAuditProbe{}
			handler, err := researchhttp.NewResearchSessionHandler(
				newResearchSessionFacade(t, audit),
			)
			if err != nil {
				t.Fatal(err)
			}
			mux := http.NewServeMux()
			handler.RegisterRoutes(mux)
			request := httptest.NewRequest(http.MethodPost, researchhttp.ResearchSessionPath, nil)
			if test.accountID != "" {
				request = request.WithContext(rtauth.WithPrincipal(
					request.Context(),
					rtauth.Principal{Actor: operation.ActorContext{AccountID: test.accountID}},
				))
			}
			response := httptest.NewRecorder()
			mux.ServeHTTP(response, request)
			if response.Code != test.wantStatus {
				t.Fatalf("status=%d want=%d body=%s", response.Code, test.wantStatus, response.Body.String())
			}
			if len(audit.records) != test.wantAudit {
				t.Fatalf("audit records=%d want=%d", len(audit.records), test.wantAudit)
			}
			if strings.Contains(response.Body.String(), test.accountID) && test.accountID != "" {
				t.Fatalf("response exposed account identity: %s", response.Body.String())
			}
		})
	}
}

type researchDurableTransportProbe struct {
	messages  []runtimemessaging.DurableMessage
	stream    string
	retention time.Duration
}

func (probe *researchDurableTransportProbe) AppendDurable(
	_ context.Context,
	message runtimemessaging.DurableMessage,
) (string, error) {
	probe.messages = append(probe.messages, message)
	return "1-0", nil
}

func (probe *researchDurableTransportProbe) SetDurableRetention(
	_ context.Context,
	stream string,
	retention time.Duration,
) error {
	probe.stream = stream
	probe.retention = retention
	return nil
}

func TestResearchSessionAuditPublisherPersistsOnlyIrreversibleIdentity(t *testing.T) {
	transport := &researchDurableTransportProbe{}
	publisher, err := researchmessaging.NewResearchSessionAuditPublisher(transport)
	if err != nil {
		t.Fatal(err)
	}
	attestation := "signed-secret-attestation"
	digest := sha256.Sum256([]byte(attestation))
	err = publisher.AppendResearchSessionIssued(
		context.Background(),
		sessionapp.ResearchSessionAuditRecord{
			SubjectHash:       "sha256:" + strings.Repeat("a", 64),
			AttestationIDHash: "sha256:" + hex.EncodeToString(digest[:]),
			ExpiresAt:         time.Date(2026, 8, 12, 14, 5, 0, 0, time.UTC),
		},
	)
	if err != nil {
		t.Fatal(err)
	}
	if len(transport.messages) != 1 ||
		transport.messages[0].Stream != researchmessaging.ResearchSessionAuditStream ||
		transport.stream != researchmessaging.ResearchSessionAuditStream ||
		transport.retention != 30*24*time.Hour {
		t.Fatalf("durable audit binding mismatch: %+v", transport)
	}
	for _, field := range transport.messages[0].Fields {
		if strings.Contains(field.Value, attestation) || strings.Contains(field.Value, "research-account") {
			t.Fatalf("durable audit exposed reversible identity: %+v", field)
		}
	}
}
