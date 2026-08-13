// spec_ref: specs/feature-tree/runtime/runtime-errors/error-code-and-response-envelope/spec.md#gwt-003
package local_contract

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	httpadapter "quwoquan_service/services/notification-service/internal/notification_delivery/notification/adapters/inbound/http"
	"quwoquan_service/services/notification-service/internal/notification_delivery/notification/application"
)

// HTTP 业务错误路径必须返回完整 RuntimeErrorResponse 信封，
// 不允许退化为裸 {"code": ...} 或自造结构。
func TestCreateAppMessageErrorPathUsesCompleteRuntimeErrorEnvelope(t *testing.T) {
	ports := newAppMessageMemoryPorts()
	commands, err := application.NewAppMessageCommandFacade(ports, ports, ports)
	if err != nil {
		t.Fatalf("construct command facade: %v", err)
	}
	queries, err := application.NewAppMessageQueryFacade(ports, ports, ports)
	if err != nil {
		t.Fatalf("construct query facade: %v", err)
	}
	handler, err := httpadapter.NewHandler(httpadapter.HandlerDependencies{
		AppMessageCommands: commands,
		AppMessageQueries:  queries,
	})
	if err != nil {
		t.Fatalf("construct handler: %v", err)
	}

	request := httptest.NewRequest(
		http.MethodPost,
		"/internal/app-messages",
		strings.NewReader(`{not json`),
	)
	request.Header.Set("X-Request-Id", "req-envelope-notification")
	response := httptest.NewRecorder()
	handler.Routes().ServeHTTP(response, request)

	if response.Code != http.StatusBadRequest {
		t.Fatalf("status=%d body=%s", response.Code, response.Body.String())
	}
	var envelope map[string]any
	if err := json.Unmarshal(response.Body.Bytes(), &envelope); err != nil {
		t.Fatalf("decode error envelope: %v", err)
	}
	if envelope["code"] != "NOTIFICATION.USER.invalid_argument" {
		t.Fatalf("code=%v", envelope["code"])
	}
	if envelope["requestId"] != "req-envelope-notification" {
		t.Fatalf("requestId=%v", envelope["requestId"])
	}
	for _, field := range []string{"userMessage", "kind", "origin", "nature"} {
		value, _ := envelope[field].(string)
		if value == "" {
			t.Fatalf("%s missing in envelope: %s", field, response.Body.String())
		}
	}
}
