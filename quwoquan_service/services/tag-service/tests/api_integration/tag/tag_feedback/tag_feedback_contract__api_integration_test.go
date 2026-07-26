package api_integration // TagFeedback HTTP contract

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"go.mongodb.org/mongo-driver/v2/bson"

	httpadapter "quwoquan_service/services/tag-service/internal/tag/tag_feedback/adapters/inbound/http"
	"quwoquan_service/services/tag-service/internal/tag/tag_feedback/application/tagfeedback"
	"quwoquan_service/services/tag-service/internal/tag/tag_feedback/infrastructure/tagfeedbackstore"
)

func newFeedbackHandler(t *testing.T) http.Handler {
	t.Helper()
	sink := tagfeedbackstore.NewSink(mongoDB)
	if err := sink.EnsureIndexes(context.Background()); err != nil {
		t.Fatalf("ensure feedback indexes: %v", err)
	}
	facade, err := tagfeedback.NewFacade(sink, tagService)
	if err != nil {
		t.Fatalf("new feedback facade: %v", err)
	}
	mux := http.NewServeMux()
	httpadapter.NewTagFeedbackHandler(facade).Register(mux)
	return mux
}

func feedbackRequest(t *testing.T, handler http.Handler, persona, idemKey string, body any) *httptest.ResponseRecorder {
	t.Helper()
	payload, err := json.Marshal(body)
	if err != nil {
		t.Fatalf("marshal feedback: %v", err)
	}
	request := httptest.NewRequest(http.MethodPost, "/tag/feedback", strings.NewReader(string(payload)))
	request.Header.Set("Content-Type", "application/json")
	if persona != "" {
		request.Header.Set("X-Client-Sub-Account-Id", persona)
	}
	if idemKey != "" {
		request.Header.Set("Idempotency-Key", idemKey)
	}
	recorder := httptest.NewRecorder()
	handler.ServeHTTP(recorder, request)
	return recorder
}

func TestTagFeedbackAppendDedupe(t *testing.T) {
	cleanCollections(t)
	if _, err := mongoDB.Collection("tag_feedback").DeleteMany(context.Background(), bson.M{}); err != nil {
		t.Fatalf("clean tag_feedback: %v", err)
	}
	seedLaunchSubset(t)
	handler := newFeedbackHandler(t)

	body := map[string]any{"tagRef": "Topic/旅行", "action": "ignore"}
	first := feedbackRequest(t, handler, "persona-fb-1", "fb-key-1", body)
	if first.Code != http.StatusOK {
		t.Fatalf("first append status=%d body=%s", first.Code, first.Body.String())
	}
	replay := feedbackRequest(t, handler, "persona-fb-1", "fb-key-1", body)
	if replay.Code != http.StatusOK {
		t.Fatalf("replay status=%d body=%s", replay.Code, replay.Body.String())
	}
	count, err := mongoDB.Collection("tag_feedback").CountDocuments(context.Background(), bson.M{
		"actorId": "persona-fb-1",
	})
	if err != nil || count != 1 {
		t.Fatalf("dedupe must keep one fact: count=%d err=%v", count, err)
	}

	// 同 key 不同 payload → 幂等冲突 409。
	conflict := feedbackRequest(t, handler, "persona-fb-1", "fb-key-1",
		map[string]any{"tagRef": "Topic/旅行", "action": "click"})
	if conflict.Code != http.StatusConflict {
		t.Fatalf("digest conflict status=%d body=%s", conflict.Code, conflict.Body.String())
	}

	// 非法 action 与未知 tagRef。
	invalid := feedbackRequest(t, handler, "persona-fb-1", "fb-key-2",
		map[string]any{"tagRef": "Topic/旅行", "action": "smash"})
	if invalid.Code != http.StatusBadRequest {
		t.Fatalf("invalid action status=%d", invalid.Code)
	}
	missing := feedbackRequest(t, handler, "persona-fb-1", "fb-key-3",
		map[string]any{"tagRef": "Topic/不存在的标签", "action": "click"})
	if missing.Code != http.StatusNotFound {
		t.Fatalf("unknown tagRef status=%d body=%s", missing.Code, missing.Body.String())
	}

	// 缺身份与缺幂等键 fail-fast。
	anonymous := feedbackRequest(t, handler, "", "fb-key-4", body)
	if anonymous.Code != http.StatusBadRequest {
		t.Fatalf("anonymous status=%d", anonymous.Code)
	}
	noKey := feedbackRequest(t, handler, "persona-fb-1", "", body)
	if noKey.Code != http.StatusBadRequest {
		t.Fatalf("missing Idempotency-Key status=%d", noKey.Code)
	}
}
