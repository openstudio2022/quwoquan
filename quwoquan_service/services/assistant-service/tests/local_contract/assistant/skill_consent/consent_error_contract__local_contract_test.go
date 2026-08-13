// spec_ref: specs/feature-tree/assistant-run-learning/skill-product-integration-platform/skill-user-lifecycle/spec.md#gwt-001
// 错误契约语义双向锁：SkillConsent errors.yaml 声明的错误码由真实触发条件经 HTTP
// 边界发射，并断言 canonical code 与 http_status。
package local_contract

import (
	"bytes"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	rtauth "quwoquan_service/runtime/auth"
	"quwoquan_service/runtime/operation"
	consenthttp "quwoquan_service/services/assistant-service/internal/assistant/skill_consent/adapters/inbound/http"
	consentapplication "quwoquan_service/services/assistant-service/internal/assistant/skill_consent/application"
	skillconsenttest "quwoquan_service/services/assistant-service/tests/support/skillconsent"
)

func TestSkillConsentHTTPEmitsCanonicalErrorContract(t *testing.T) {
	t.Parallel()
	now := time.Date(2026, 8, 13, 9, 0, 0, 0, time.UTC)
	store := skillconsenttest.NewMemoryStore()
	mux := http.NewServeMux()
	consenthttp.NewHandler(
		consentapplication.NewCommandFacade(store, func() time.Time { return now }),
		consentapplication.NewQueryFacade(store),
	).RegisterRoutes(mux)

	// 无 store 的 facade 用来锁 consent_unavailable 的失败关闭语义。
	unavailableMux := http.NewServeMux()
	consenthttp.NewHandler(
		consentapplication.NewCommandFacade(nil, func() time.Time { return now }),
		consentapplication.NewQueryFacade(nil),
	).RegisterRoutes(unavailableMux)

	granted := consentGrantRequest(
		t, mux, "grant-base", "travel_companion",
		[]string{"assistant.memory.preferences.read"},
	)
	if granted.Code != http.StatusOK {
		t.Fatalf("seed grant status=%d body=%s", granted.Code, granted.Body.String())
	}

	tests := []struct {
		name       string
		handler    http.Handler
		commandID  string
		skillID    string
		scopes     []string
		wantStatus int
		wantCode   string
	}{
		{
			name:       "blank scope is consent_invalid_argument",
			handler:    mux,
			commandID:  "grant-blank-scope",
			skillID:    "travel_companion",
			scopes:     []string{" "},
			wantStatus: http.StatusBadRequest,
			wantCode:   "ASSISTANT.USER.consent_invalid_argument",
		},
		{
			name:       "reused command with different skill is consent_idempotency_conflict",
			handler:    mux,
			commandID:  "grant-base",
			skillID:    "another_skill",
			scopes:     []string{"assistant.memory.preferences.read"},
			wantStatus: http.StatusConflict,
			wantCode:   "ASSISTANT.USER.consent_idempotency_conflict",
		},
		{
			name:      "different scope set against active consent is consent_scope_conflict",
			handler:   mux,
			commandID: "grant-scope-drift",
			skillID:   "travel_companion",
			scopes: []string{
				"assistant.memory.preferences.read",
				"assistant.learning.feedback_context.read",
			},
			wantStatus: http.StatusConflict,
			wantCode:   "ASSISTANT.USER.consent_scope_conflict",
		},
		{
			name:       "missing store is consent_unavailable",
			handler:    unavailableMux,
			commandID:  "grant-unavailable",
			skillID:    "travel_companion",
			scopes:     []string{"assistant.memory.preferences.read"},
			wantStatus: http.StatusServiceUnavailable,
			wantCode:   "ASSISTANT.SYSTEM.consent_unavailable",
		},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			recorder := consentGrantRequest(
				t,
				test.handler,
				test.commandID,
				test.skillID,
				test.scopes,
			)
			var response struct {
				Code string `json:"code"`
			}
			if err := json.Unmarshal(recorder.Body.Bytes(), &response); err != nil {
				t.Fatalf("decode error response %q: %v", recorder.Body.String(), err)
			}
			if recorder.Code != test.wantStatus || response.Code != test.wantCode {
				t.Fatalf(
					"response=%d/%s, want %d/%s body=%s",
					recorder.Code,
					response.Code,
					test.wantStatus,
					test.wantCode,
					recorder.Body.String(),
				)
			}
		})
	}
}

func consentGrantRequest(
	t *testing.T,
	handler http.Handler,
	commandID string,
	skillID string,
	scopes []string,
) *httptest.ResponseRecorder {
	t.Helper()
	payload, err := json.Marshal(map[string]any{"grantedScopes": scopes})
	if err != nil {
		t.Fatalf("marshal grant body: %v", err)
	}
	request := httptest.NewRequest(
		http.MethodPost,
		"/assistant/skills/"+skillID+"/consent",
		bytes.NewReader(payload),
	)
	request.Header.Set("Content-Type", "application/json")
	request.Header.Set("Idempotency-Key", commandID)
	request = request.WithContext(rtauth.WithPrincipal(
		request.Context(),
		rtauth.Principal{Actor: operation.ActorContext{
			AccountID: "account-consent-error",
		}},
	))
	recorder := httptest.NewRecorder()
	handler.ServeHTTP(recorder, request)
	return recorder
}
