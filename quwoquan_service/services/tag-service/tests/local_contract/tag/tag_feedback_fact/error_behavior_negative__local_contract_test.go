// spec_ref: specs/feature-tree/discovery-content/spec.md#dom-002
//
// tag_feedback_fact 错误行为负例：经真实 HTTP adapter（NewTagFeedbackHandler）
// 触发 errors.yaml 声明的每个错误码，断言 wire 响应 code 与 http_status。
// typed double sink 注入幂等冲突与存储失败驱动对应码。
package tag_feedback_fact

import (
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	rtauth "quwoquan_service/runtime/auth"
	httpadapter "quwoquan_service/services/tag-service/internal/tag/tag_feedback_fact/adapters/inbound/http"
	"quwoquan_service/services/tag-service/internal/tag/tag_feedback_fact/application/tagfeedback"
	feedbackmodel "quwoquan_service/services/tag-service/internal/tag/tag_feedback_fact/domain/tagfeedback/model"
)

type stubFeedbackSink struct {
	err error
}

func (s stubFeedbackSink) Append(
	_ context.Context,
	feedback feedbackmodel.Feedback,
) (feedbackmodel.Feedback, bool, error) {
	if s.err != nil {
		return feedbackmodel.Feedback{}, false, s.err
	}
	return feedback, false, nil
}

type alwaysExistsValidator struct{}

func (alwaysExistsValidator) TagRefExists(context.Context, string) (bool, error) {
	return true, nil
}

func feedbackNegativeHandler(t *testing.T, sink stubFeedbackSink) http.Handler {
	t.Helper()
	facade, err := tagfeedback.NewFacade(sink, alwaysExistsValidator{})
	if err != nil {
		t.Fatalf("build tag feedback facade: %v", err)
	}
	mux := http.NewServeMux()
	httpadapter.NewTagFeedbackHandler(facade).Register(mux)
	return mux
}

func feedbackRequest(t *testing.T, body string) *http.Request {
	t.Helper()
	request := httptest.NewRequest(
		http.MethodPost, "/tag/feedback", strings.NewReader(body),
	)
	request.Header.Set("Idempotency-Key", "tagfb-negative-key")
	principal := rtauth.Principal{}
	principal.Actor.PersonaID = "persona_tagfb_negative"
	return request.WithContext(rtauth.WithPrincipal(request.Context(), principal))
}

func feedbackWireError(t *testing.T, recorder *httptest.ResponseRecorder) string {
	t.Helper()
	var body struct {
		Code string `json:"code"`
	}
	if err := json.Unmarshal(recorder.Body.Bytes(), &body); err != nil {
		t.Fatalf("decode error body %q: %v", recorder.Body.String(), err)
	}
	return body.Code
}

func TestTagFeedbackInvalidActionEmitsDeclaredCode(t *testing.T) {
	t.Parallel()
	handler := feedbackNegativeHandler(t, stubFeedbackSink{})

	recorder := httptest.NewRecorder()
	handler.ServeHTTP(
		recorder,
		feedbackRequest(t, `{"tagRef":"Topic/旅行","action":"not_a_valid_action"}`),
	)

	if recorder.Code != http.StatusBadRequest {
		t.Fatalf("status = %d, want 400", recorder.Code)
	}
	if code := feedbackWireError(t, recorder); code != "TAG.USER.feedback_invalid_action" {
		t.Fatalf("code = %s, want TAG.USER.feedback_invalid_action", code)
	}
}

func TestTagFeedbackIdempotencyConflictEmitsDeclaredCode(t *testing.T) {
	t.Parallel()
	handler := feedbackNegativeHandler(
		t, stubFeedbackSink{err: feedbackmodel.ErrIdempotencyConflict},
	)

	recorder := httptest.NewRecorder()
	handler.ServeHTTP(
		recorder,
		feedbackRequest(t, `{"tagRef":"Topic/旅行","action":"click"}`),
	)

	if recorder.Code != http.StatusConflict {
		t.Fatalf("status = %d, want 409", recorder.Code)
	}
	if code := feedbackWireError(t, recorder); code != "TAG.USER.feedback_idempotency_conflict" {
		t.Fatalf("code = %s, want TAG.USER.feedback_idempotency_conflict", code)
	}
}

func TestTagFeedbackStorageFailureEmitsDeclaredCode(t *testing.T) {
	t.Parallel()
	handler := feedbackNegativeHandler(
		t, stubFeedbackSink{err: errors.New("injected feedback storage failure")},
	)

	recorder := httptest.NewRecorder()
	handler.ServeHTTP(
		recorder,
		feedbackRequest(t, `{"tagRef":"Topic/旅行","action":"click"}`),
	)

	if recorder.Code != http.StatusInternalServerError {
		t.Fatalf("status = %d, want 500", recorder.Code)
	}
	if code := feedbackWireError(t, recorder); code != "TAG.SYSTEM.feedback_storage_failed" {
		t.Fatalf("code = %s, want TAG.SYSTEM.feedback_storage_failed", code)
	}
}
