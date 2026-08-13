// spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-002
// readiness_case: get-original-image-access-audit-local
package application_test

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
	rterr "quwoquan_service/runtime/errors"
	"quwoquan_service/runtime/operation"
	quotahttp "quwoquan_service/services/content-service/internal/media/original_access_quota/adapters/inbound/http"
	quotaapp "quwoquan_service/services/content-service/internal/media/original_access_quota/application"
	quotaports "quwoquan_service/services/content-service/internal/media/original_access_quota/domain/ports"
)

type memoryAuditReader struct {
	facts map[string]quotaports.AuditFact
	err   error
}

func (reader memoryAuditReader) FindOriginalAccessAudit(
	_ context.Context,
	auditID string,
) (quotaports.AuditFact, bool, error) {
	if reader.err != nil {
		return quotaports.AuditFact{}, false, reader.err
	}
	fact, found := reader.facts[auditID]
	return fact, found, nil
}

func grantedAuditFact(now time.Time) quotaports.AuditFact {
	return quotaports.AuditFact{
		AuditID:   "moa_" + strings.Repeat("a", 32),
		AssetID:   "media-original-local",
		ViewerID:  "persona-original-owner",
		Purpose:   "save",
		Outcome:   "granted",
		DecidedAt: now,
		ExpiresAt: now.Add(5 * time.Minute),
	}
}

func appErrorCode(t *testing.T, err error) string {
	t.Helper()
	var appError *rterr.AppError
	if !errors.As(err, &appError) {
		t.Fatalf("expected typed AppError, got %v", err)
	}
	return appError.Code.String()
}

func TestGetOriginalImageAccessAuditServesOnlyTheOwningViewer(t *testing.T) {
	now := time.Date(2030, time.September, 10, 11, 12, 13, 0, time.UTC)
	fact := grantedAuditFact(now)
	facade := quotaapp.NewAuditQueryFacade(memoryAuditReader{
		facts: map[string]quotaports.AuditFact{fact.AuditID: fact},
	})

	view, err := facade.GetOriginalImageAccessAudit(
		context.Background(),
		"persona-original-owner",
		fact.AuditID,
	)
	if err != nil {
		t.Fatalf("owner audit readback: %v", err)
	}
	if view.AuditID != fact.AuditID ||
		view.MediaID != "media-original-local" ||
		view.Outcome != "granted" ||
		view.TTLSeconds != 300 ||
		!view.ExpiresAt.Equal(fact.ExpiresAt) {
		t.Fatalf("audit readback drifted from the stored fact: %+v", view)
	}
}

func TestGetOriginalImageAccessAuditFailsClosedOnForeignOrMissingAudit(
	t *testing.T,
) {
	now := time.Date(2030, time.September, 10, 11, 12, 13, 0, time.UTC)
	fact := grantedAuditFact(now)
	facade := quotaapp.NewAuditQueryFacade(memoryAuditReader{
		facts: map[string]quotaports.AuditFact{fact.AuditID: fact},
	})

	foreignView, foreignErr := facade.GetOriginalImageAccessAudit(
		context.Background(), "persona-other", fact.AuditID,
	)
	missingView, missingErr := facade.GetOriginalImageAccessAudit(
		context.Background(), "persona-original-owner", "moa_missing",
	)
	if foreignErr == nil || missingErr == nil ||
		foreignView != (quotaapp.AuditView{}) || missingView != (quotaapp.AuditView{}) {
		t.Fatalf(
			"cross-persona and missing audits must fail closed: foreign=%v missing=%v",
			foreignErr, missingErr,
		)
	}
	foreignCode := appErrorCode(t, foreignErr)
	missingCode := appErrorCode(t, missingErr)
	if foreignCode != "CONTENT.USER.original_access_denied" ||
		foreignCode != missingCode {
		t.Fatalf(
			"denial must not leak audit existence: foreign=%s missing=%s",
			foreignCode, missingCode,
		)
	}
}

func TestGetOriginalImageAccessAuditRejectsAnonymousAndStorageFailure(
	t *testing.T,
) {
	now := time.Date(2030, time.September, 10, 11, 12, 13, 0, time.UTC)
	fact := grantedAuditFact(now)

	anonymousFacade := quotaapp.NewAuditQueryFacade(memoryAuditReader{
		facts: map[string]quotaports.AuditFact{fact.AuditID: fact},
	})
	view, err := anonymousFacade.GetOriginalImageAccessAudit(
		context.Background(), "  ", fact.AuditID,
	)
	if err == nil || view != (quotaapp.AuditView{}) ||
		appErrorCode(t, err) != "CONTENT.USER.unauthorized" {
		t.Fatalf("anonymous audit readback must be unauthorized: view=%+v err=%v", view, err)
	}

	failingFacade := quotaapp.NewAuditQueryFacade(memoryAuditReader{
		err: errors.New("storage offline"),
	})
	view, err = failingFacade.GetOriginalImageAccessAudit(
		context.Background(), "persona-original-owner", fact.AuditID,
	)
	if err == nil || view != (quotaapp.AuditView{}) ||
		appErrorCode(t, err) != "CONTENT.SYSTEM.storage_read_failed" {
		t.Fatalf("storage failure must fail closed as read failure: view=%+v err=%v", view, err)
	}
}

func TestOriginalImageAccessAuditHTTPSecurity(t *testing.T) {
	now := time.Date(2030, time.September, 10, 11, 12, 13, 0, time.UTC)
	fact := grantedAuditFact(now)
	handler := quotahttp.NewHandler(
		quotaapp.NewService(
			newMemoryQuotaStore(),
			newMemoryAuditAppender(),
			readyOriginalAccessAsset{},
			visibleOriginalAccessPost{},
			originalAccessSigner{},
			quotaapp.WithClock(func() time.Time { return now }),
		),
		quotahttp.WithAuditQuery(quotaapp.NewAuditQueryFacade(memoryAuditReader{
			facts: map[string]quotaports.AuditFact{fact.AuditID: fact},
		})),
	)
	mux := http.NewServeMux()
	mux.HandleFunc(
		"GET /content/media/original-access-audits/{auditId}",
		handler.GetAudit,
	)

	tests := []struct {
		name       string
		personaID  string
		auditID    string
		wantStatus int
	}{
		{
			name:       "owner reads its own audit",
			personaID:  "persona-original-owner",
			auditID:    fact.AuditID,
			wantStatus: http.StatusOK,
		},
		{
			name:       "anonymous request is denied",
			auditID:    fact.AuditID,
			wantStatus: http.StatusUnauthorized,
		},
		{
			name:       "foreign persona is denied",
			personaID:  "persona-other",
			auditID:    fact.AuditID,
			wantStatus: http.StatusForbidden,
		},
		{
			name:       "missing audit is denied without existence oracle",
			personaID:  "persona-original-owner",
			auditID:    "moa_missing",
			wantStatus: http.StatusForbidden,
		},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			request := httptest.NewRequest(
				http.MethodGet,
				"/content/media/original-access-audits/"+test.auditID,
				nil,
			)
			if test.personaID != "" {
				request = request.WithContext(rtauth.WithPrincipal(
					request.Context(),
					rtauth.Principal{Actor: operation.ActorContext{
						AccountID: "account-1",
						PersonaID: test.personaID,
					}},
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
			if test.wantStatus != http.StatusOK {
				return
			}
			var view struct {
				AuditID    string    `json:"auditId"`
				MediaID    string    `json:"mediaId"`
				Outcome    string    `json:"outcome"`
				TTLSeconds int       `json:"ttlSeconds"`
				ExpiresAt  time.Time `json:"expiresAt"`
			}
			if err := json.Unmarshal(response.Body.Bytes(), &view); err != nil {
				t.Fatalf("decode audit readback: %v", err)
			}
			if view.AuditID != fact.AuditID ||
				view.MediaID != "media-original-local" ||
				view.Outcome != "granted" ||
				view.TTLSeconds != 300 ||
				!view.ExpiresAt.Equal(fact.ExpiresAt) {
				t.Fatalf("HTTP audit readback drifted: %+v", view)
			}
		})
	}
}
