package api_integration

import (
	"bytes"
	"context"
	"net/http"
	"net/http/httptest"
	"testing"

	"go.mongodb.org/mongo-driver/v2/bson"

	feedbackhttp "quwoquan_service/services/search-service/internal/search/search_feedback_fact/adapters/inbound/http"
	feedbackapplication "quwoquan_service/services/search-service/internal/search/search_feedback_fact/application"
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
	for name, body := range map[string]string{
		"click":       `{"searchRequestId":"req_click","eventType":"click","objectId":"post_es","target":"article","rankPosition":2}`,
		"zero result": `{"searchRequestId":"req_zero","eventType":"zero_result"}`,
		"dwell":       `{"searchRequestId":"req_dwell","eventType":"dwell","dwellMs":1}`,
	} {
		t.Run(name, func(t *testing.T) {
			request := httptest.NewRequest(
				http.MethodPost,
				"/search/feedback",
				bytes.NewBufferString(body),
			)
			request.Header.Set("Idempotency-Key", "feedback-key-"+name)
			response := httptest.NewRecorder()
			feedbackHandler().ServeHTTP(response, request)
			if response.Code != http.StatusAccepted {
				t.Fatalf(
					"feedback must be 202, got %d body=%s",
					response.Code,
					response.Body.String(),
				)
			}
		})
	}
}

func TestFeedbackEndpointRejectsInvalidEnvelope(t *testing.T) {
	for name, body := range map[string]string{
		"missing searchRequestId": `{"eventType":"click"}`,
		"unknown field":           `{"searchRequestId":"req_1","eventType":"click","unknown":true}`,
		"trailing object":         `{"searchRequestId":"req_1","eventType":"zero_result"} {}`,
		"unknown event type":      `{"searchRequestId":"req_1","eventType":"unsupported"}`,
		"dwell without duration":  `{"searchRequestId":"req_1","eventType":"dwell"}`,
		"dwell zero duration":     `{"searchRequestId":"req_1","eventType":"dwell","dwellMs":0}`,
		"non dwell duration":      `{"searchRequestId":"req_1","eventType":"zero_result","dwellMs":1}`,
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

func TestFeedbackEndpointConvergesTransportRetriesInRealMongo(t *testing.T) {
	cleanFeedbackCollections(t)
	service := feedbackapplication.NewService(newFeedbackStore(t))
	handler := feedbackhttp.NewHandler(service, nil).Routes()
	body := `{"searchRequestId":"req_http_retry","eventType":"click","objectId":"post_http","target":"article","rankPosition":2}`
	for _, key := range []string{
		"feedback-http-key-1",
		"feedback-http-key-1",
		"feedback-http-key-2",
	} {
		response := postFeedback(t, handler, key, body)
		if response.Code != http.StatusAccepted {
			t.Fatalf(
				"feedback replay key=%s got=%d body=%s",
				key,
				response.Code,
				response.Body.String(),
			)
		}
	}
	conflict := postFeedback(
		t,
		handler,
		"feedback-http-key-conflict",
		`{"searchRequestId":"req_http_retry","eventType":"click","objectId":"post_http","target":"article","rankPosition":3}`,
	)
	if conflict.Code != http.StatusConflict {
		t.Fatalf(
			"semantic conflict got=%d body=%s",
			conflict.Code,
			conflict.Body.String(),
		)
	}

	facts, err := mongoDB.Collection("search_feedback_events").CountDocuments(
		context.Background(),
		bson.M{"searchRequestId": "req_http_retry"},
	)
	if err != nil || facts != 1 {
		t.Fatalf("feedback facts=%d want=1 err=%v", facts, err)
	}
	completed, err := mongoDB.Collection(
		"search_feedback_command_receipts",
	).CountDocuments(context.Background(), bson.M{
		"_id": bson.M{"$in": []string{
			"feedback-http-key-1",
			"feedback-http-key-2",
		}},
		"status": "completed",
	})
	if err != nil || completed != 2 {
		t.Fatalf("completed receipts=%d want=2 err=%v", completed, err)
	}
}

func postFeedback(
	t *testing.T,
	handler http.Handler,
	idempotencyKey string,
	body string,
) *httptest.ResponseRecorder {
	t.Helper()
	request := httptest.NewRequest(
		http.MethodPost,
		"/search/feedback",
		bytes.NewBufferString(body),
	)
	request.Header.Set("Idempotency-Key", idempotencyKey)
	response := httptest.NewRecorder()
	handler.ServeHTTP(response, request)
	return response
}
