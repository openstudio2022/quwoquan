// spec_ref: specs/feature-tree/runtime/runtime-test-pyramid/spec.md#req-004
// 错误契约语义双向锁：AssistantEntryView errors.yaml 声明的错误码由真实触发条件经
// HTTP 边界发射，并断言 canonical code 与 http_status。
package assistant_entry_view_test

import (
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"net/http/httptest"
	"testing"

	rtauth "quwoquan_service/runtime/auth"
	"quwoquan_service/runtime/operation"
	entryhttp "quwoquan_service/services/assistant-service/internal/assistant/assistant_entry_view/adapters/inbound/http"
	entryapplication "quwoquan_service/services/assistant-service/internal/assistant/assistant_entry_view/application"
	entrymodel "quwoquan_service/services/assistant-service/internal/assistant/assistant_entry_view/domain/model"
	pagecontextmodel "quwoquan_service/services/assistant-service/internal/assistant/page_context/domain/model"
)

type entryErrorContractReader struct{ err error }

func (reader entryErrorContractReader) Get(
	context.Context,
	string,
) (*entrymodel.View, error) {
	return nil, reader.err
}

type entryErrorContractPageContexts struct{}

func (entryErrorContractPageContexts) Current(
	context.Context,
	string,
) (*pagecontextmodel.PageContext, error) {
	return nil, nil
}

func TestAssistantEntryHTTPEmitsCanonicalErrorContract(t *testing.T) {
	t.Parallel()
	tests := []struct {
		name          string
		reader        entryErrorContractReader
		path          string
		withPrincipal bool
		wantStatus    int
		wantCode      string
	}{
		{
			name:          "missing principal is entry_unauthorized",
			reader:        entryErrorContractReader{},
			path:          "/assistant/entry",
			withPrincipal: false,
			wantStatus:    http.StatusUnauthorized,
			wantCode:      "ASSISTANT.USER.entry_unauthorized",
		},
		{
			name:          "page context mismatch is entry_invalid_argument",
			reader:        entryErrorContractReader{},
			path:          "/assistant/entry?pageType=post_detail&objectId=post-1",
			withPrincipal: true,
			wantStatus:    http.StatusBadRequest,
			wantCode:      "ASSISTANT.USER.entry_invalid_argument",
		},
		{
			name: "projection read failure is entry_projection_unavailable",
			reader: entryErrorContractReader{
				err: errors.New("redis connection refused"),
			},
			path:          "/assistant/entry",
			withPrincipal: true,
			wantStatus:    http.StatusServiceUnavailable,
			wantCode:      "ASSISTANT.SYSTEM.entry_projection_unavailable",
		},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			t.Parallel()
			mux := http.NewServeMux()
			entryhttp.NewHandler(entryapplication.NewQueryFacade(
				test.reader,
				entryErrorContractPageContexts{},
			)).RegisterRoutes(mux)
			request := httptest.NewRequest(http.MethodGet, test.path, nil)
			if test.withPrincipal {
				request = request.WithContext(rtauth.WithPrincipal(
					request.Context(),
					rtauth.Principal{Actor: operation.ActorContext{
						AccountID: "account-entry-error",
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
