// spec_ref: specs/feature-tree/runtime/runtime-errors/error-code-and-response-envelope/spec.md#gwt-003
package local_contract

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	callhttp "quwoquan_service/services/rtc-service/internal/rtc/call_session/adapters/inbound/http"
)

// HTTP 业务错误路径必须返回完整 RuntimeErrorResponse 信封，
// 不允许退化为裸 {"code": ...} 或自造结构。
func TestInitiateCallErrorPathUsesCompleteRuntimeErrorEnvelope(t *testing.T) {
	// 非法 JSON 在进入 orchestrator 之前被拒绝，handler 依赖可为空。
	handler := callhttp.NewCallHandler(nil).Routes()

	request := httptest.NewRequest(
		http.MethodPost,
		"/rtc/calls",
		strings.NewReader(`{not json`),
	)
	request.Header.Set("X-Request-Id", "req-envelope-rtc")
	response := httptest.NewRecorder()
	handler.ServeHTTP(response, request)

	if response.Code != http.StatusBadRequest {
		t.Fatalf("status=%d body=%s", response.Code, response.Body.String())
	}
	var envelope map[string]any
	if err := json.Unmarshal(response.Body.Bytes(), &envelope); err != nil {
		t.Fatalf("decode error envelope: %v", err)
	}
	if envelope["code"] != "RTC.USER.invalid_argument" {
		t.Fatalf("code=%v", envelope["code"])
	}
	if envelope["requestId"] != "req-envelope-rtc" {
		t.Fatalf("requestId=%v", envelope["requestId"])
	}
	for _, field := range []string{"userMessage", "kind", "origin", "nature"} {
		value, _ := envelope[field].(string)
		if value == "" {
			t.Fatalf("%s missing in envelope: %s", field, response.Body.String())
		}
	}
}
