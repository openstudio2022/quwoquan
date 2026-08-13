// spec_ref: specs/feature-tree/runtime/runtime-test-pyramid/spec.md#req-004
// 错误契约语义双向锁：AssistantTaskView 的 task_unauthorized 由缺失可信 principal
// 的真实请求触发，并断言 canonical code 与 http_status。
package assistant_task_view_test

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	taskhttp "quwoquan_service/services/assistant-service/internal/assistant/assistant_task_view/adapters/inbound/http"
	taskapplication "quwoquan_service/services/assistant-service/internal/assistant/assistant_task_view/application"
)

func TestAssistantTaskListRejectsAnonymousRequestWithCanonicalCode(t *testing.T) {
	t.Parallel()
	mux := http.NewServeMux()
	taskhttp.NewHandler(taskapplication.NewQueryFacade(nil)).RegisterRoutes(mux)
	request := httptest.NewRequest(http.MethodGet, "/assistant/tasks", nil)
	recorder := httptest.NewRecorder()
	mux.ServeHTTP(recorder, request)
	var response struct {
		Code string `json:"code"`
	}
	if err := json.Unmarshal(recorder.Body.Bytes(), &response); err != nil {
		t.Fatalf("decode error response %q: %v", recorder.Body.String(), err)
	}
	if recorder.Code != http.StatusUnauthorized ||
		response.Code != "ASSISTANT.USER.task_unauthorized" {
		t.Fatalf(
			"response=%d/%s, want 401/ASSISTANT.USER.task_unauthorized body=%s",
			recorder.Code,
			response.Code,
			recorder.Body.String(),
		)
	}
}
