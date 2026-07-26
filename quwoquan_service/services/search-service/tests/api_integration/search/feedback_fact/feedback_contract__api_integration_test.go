package api_integration

import (
	"bytes"
	"context"
	"net/http"
	"net/http/httptest"
	"testing"

	feedbackhttp "quwoquan_service/services/search-service/internal/search/feedback_fact/adapters/inbound/http"
	feedbackapplication "quwoquan_service/services/search-service/internal/search/feedback_fact/application"
)

type acceptingFeedbackSink struct{}

func (acceptingFeedbackSink) Record(
	context.Context,
	feedbackapplication.Event,
	feedbackapplication.CommandMeta,
) error {
	return nil
}

func feedbackHandler() http.Handler {
	service := feedbackapplication.NewService(acceptingFeedbackSink{})
	return feedbackhttp.NewHandler(service, nil).Routes()
}

func TestFeedbackEndpointAcceptsEvent(t *testing.T) {
	request := httptest.NewRequest(
		http.MethodPost,
		"/search/feedback",
		bytes.NewBufferString(
			`{"searchRequestId":"req_1","eventType":"click","objectId":"post_es","target":"article","rankPosition":2}`,
		),
	)
	request.Header.Set("Idempotency-Key", "feedback-key-1")
	response := httptest.NewRecorder()
	feedbackHandler().ServeHTTP(response, request)
	if response.Code != http.StatusAccepted {
		t.Fatalf(
			"feedback must be 202, got %d body=%s",
			response.Code,
			response.Body.String(),
		)
	}
}

func TestFeedbackEndpointRejectsInvalidEnvelope(t *testing.T) {
	for name, body := range map[string]string{
		"missing searchRequestId": `{"eventType":"click"}`,
		"unknown field":           `{"searchRequestId":"req_1","eventType":"click","unknown":true}`,
		"trailing object":         `{"searchRequestId":"req_1","eventType":"zero_result"} {}`,
	} {
		t.Run(name, func(t *testing.T) {
			request := httptest.NewRequest(
				http.MethodPost,
				"/search/feedback",
				bytes.NewBufferString(body),
			)
			request.Header.Set("Idempotency-Key", "feedback-key-invalid")
			response := httptest.NewRecorder()
			feedbackHandler().ServeHTTP(response, request)
			if response.Code != http.StatusBadRequest {
				t.Fatalf(
					"invalid feedback must be 400, got %d body=%s",
					response.Code,
					response.Body.String(),
				)
			}
		})
	}
}
