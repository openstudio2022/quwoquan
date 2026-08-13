// spec_ref: specs/feature-tree/runtime/runtime-test-pyramid/spec.md#req-004
// 错误契约语义双向锁：PageContext errors.yaml 声明的错误码由真实触发条件经 HTTP
// 边界发射，并断言 canonical code 与 http_status。
package page_context_test

import (
	"bytes"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	rtauth "quwoquan_service/runtime/auth"
	"quwoquan_service/runtime/operation"
	pagehttp "quwoquan_service/services/assistant-service/internal/assistant/page_context/adapters/inbound/http"
	pageapplication "quwoquan_service/services/assistant-service/internal/assistant/page_context/application"
)

func TestPageContextHTTPEmitsCanonicalErrorContract(t *testing.T) {
	t.Parallel()
	tests := []struct {
		name          string
		body          string
		withPrincipal bool
		wantStatus    int
		wantCode      string
	}{
		{
			name:          "missing persona principal is page_context_unauthorized",
			body:          `{"contextSnapshot":{"pageType":"post_detail"}}`,
			withPrincipal: false,
			wantStatus:    http.StatusUnauthorized,
			wantCode:      "ASSISTANT.USER.page_context_unauthorized",
		},
		{
			name:          "malformed report body is page_context_invalid_argument",
			body:          "{malformed",
			withPrincipal: true,
			wantStatus:    http.StatusBadRequest,
			wantCode:      "ASSISTANT.USER.page_context_invalid_argument",
		},
		{
			name:          "missing store is page_context_unavailable",
			body:          `{"contextSnapshot":{"pageType":"post_detail"}}`,
			withPrincipal: true,
			wantStatus:    http.StatusServiceUnavailable,
			wantCode:      "ASSISTANT.SYSTEM.page_context_unavailable",
		},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			t.Parallel()
			mux := http.NewServeMux()
			pagehttp.NewHandler(pageapplication.NewFacade(nil, nil)).RegisterRoutes(mux)
			request := httptest.NewRequest(
				http.MethodPost,
				"/assistant/page-context",
				bytes.NewReader([]byte(test.body)),
			)
			request.Header.Set("Content-Type", "application/json")
			if test.withPrincipal {
				request = request.WithContext(rtauth.WithPrincipal(
					request.Context(),
					rtauth.Principal{Actor: operation.ActorContext{
						AccountID: "account-page-error",
						PersonaID: "persona-page-error",
					}},
				))
			}
			recorder := httptest.NewRecorder()
			mux.ServeHTTP(recorder, request)
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
