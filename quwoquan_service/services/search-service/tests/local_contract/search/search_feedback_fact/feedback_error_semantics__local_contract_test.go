// spec_ref: specs/feature-tree/runtime/runtime-test-pyramid/spec.md#sit-002
//
// SearchFeedbackFact 声明错误码的负例断言：经真实 HTTP handler 驱动幂等冲突
// 与存储失败路径，以字面 wire code 锁定端云契约。
package local_contract

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"net/http/httptest"
	"testing"

	searchfeedbackhttp "quwoquan_service/services/search-service/internal/search/search_feedback_fact/adapters/inbound/http"
	feedbackapplication "quwoquan_service/services/search-service/internal/search/search_feedback_fact/application"
)

type errSemFeedbackSink struct {
	err error
}

func (s errSemFeedbackSink) Record(
	context.Context, feedbackapplication.Event, feedbackapplication.CommandMeta,
) error {
	return s.err
}

func postErrSemFeedback(t *testing.T, sinkErr error) *httptest.ResponseRecorder {
	t.Helper()
	handler := searchfeedbackhttp.NewHandler(
		feedbackapplication.NewService(errSemFeedbackSink{err: sinkErr}),
		nil,
	).Routes()
	request := httptest.NewRequest(
		http.MethodPost,
		"/search/feedback",
		bytes.NewBufferString(`{"searchRequestId":"search-req-errsem","eventType":"impression"}`),
	)
	request.Header.Set("Idempotency-Key", "feedback-errsem-key")
	response := httptest.NewRecorder()
	handler.ServeHTTP(response, request)
	return response
}

func requireErrSemFeedbackCode(
	t *testing.T,
	response *httptest.ResponseRecorder,
	wantStatus int,
	wantCode string,
) {
	t.Helper()
	if response.Code != wantStatus {
		t.Fatalf("status=%d body=%s", response.Code, response.Body.String())
	}
	var envelope struct {
		Code string `json:"code"`
	}
	if err := json.Unmarshal(response.Body.Bytes(), &envelope); err != nil {
		t.Fatalf("decode error envelope: %v body=%s", err, response.Body.String())
	}
	if envelope.Code != wantCode {
		t.Fatalf("expected code %s, got %s", wantCode, envelope.Code)
	}
}

func TestReportFeedbackIdempotencyConflictEmitsFeedbackConflict(t *testing.T) {
	response := postErrSemFeedback(t, feedbackapplication.ErrIdempotencyConflict)
	requireErrSemFeedbackCode(
		t, response, http.StatusConflict, "SEARCH.USER.feedback_conflict",
	)
}

func TestReportFeedbackSinkFailureEmitsStorageWriteFailed(t *testing.T) {
	response := postErrSemFeedback(t, errors.New("mongo write timeout"))
	requireErrSemFeedbackCode(
		t, response, http.StatusInternalServerError, "SEARCH.SYSTEM.storage_write_failed",
	)
}
