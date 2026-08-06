// spec_ref: specs/feature-tree/assistant-run-learning/assistant-runtime-foundation/spec.md#sit-001
package api_integration

import (
	"bytes"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"

	rtauth "quwoquan_service/runtime/auth"
	"quwoquan_service/runtime/operation"
	assistant "quwoquan_service/services/assistant-service/internal/assistant/assistant_session/domain/model"
	sessionmessaging "quwoquan_service/services/assistant-service/internal/assistant/assistant_session/infrastructure/messaging"
	"quwoquan_service/services/assistant-service/tests/support/assistantingress"
)

// TestAssistantSessionCommitsAggregateAndOutboxAtomically drives the real
// CreateAssistantSession route against real MongoDB and proves the aggregate
// and its declared AssistantSessionCreated event are committed in one
// transaction, that an idempotent replay appends no second event, and that the
// relay only marks what durable transport confirmed.
func TestAssistantSessionCommitsAggregateAndOutboxAtomically(t *testing.T) {
	resetIntegrationState(t)
	handler := assistantingress.Routes(newIntegrationAssistantService())

	first := createAssistantSessionRequest(t, handler, "user-session-outbox", "request-session-outbox")
	if first.Code != http.StatusOK && first.Code != http.StatusCreated {
		t.Fatalf("create session status=%d body=%s", first.Code, first.Body.String())
	}
	var created assistant.AssistantSession
	if err := json.Unmarshal(first.Body.Bytes(), &created); err != nil {
		t.Fatalf("decode created session: %v", err)
	}
	assertSessionCollectionCount(t, "assistant_sessions", bson.M{"_id": created.SessionID}, 1)
	assertSessionCollectionCount(t, "assistant_session_outbox", bson.M{
		"_id":         assistant.SessionCreatedEventType + ":" + created.SessionID,
		"eventType":   assistant.SessionCreatedEventType,
		"sessionId":   created.SessionID,
		"publishedAt": bson.M{"$exists": false},
	}, 1)

	replayed := createAssistantSessionRequest(t, handler, "user-session-outbox", "request-session-outbox")
	if replayed.Code != http.StatusOK && replayed.Code != http.StatusCreated {
		t.Fatalf("replay session status=%d body=%s", replayed.Code, replayed.Body.String())
	}
	var replay assistant.AssistantSession
	if err := json.Unmarshal(replayed.Body.Bytes(), &replay); err != nil {
		t.Fatalf("decode replayed session: %v", err)
	}
	if replay.SessionID != created.SessionID {
		t.Fatalf("replay created another aggregate: %s != %s", replay.SessionID, created.SessionID)
	}
	assertSessionCollectionCount(t, "assistant_sessions", bson.M{}, 1)
	assertSessionCollectionCount(t, "assistant_session_outbox", bson.M{}, 1)

	transport := newIntegrationMessageTransport()
	relay, err := sessionmessaging.NewSessionOutboxRelay(
		integrationSessionStore,
		transport,
		time.Second,
		16,
		nil,
	)
	if err != nil {
		t.Fatalf("build session outbox relay: %v", err)
	}
	published, err := relay.FlushOnce(t.Context())
	if err != nil || published != 1 {
		t.Fatalf("flush session outbox: published=%d err=%v", published, err)
	}
	assertSessionCollectionCount(t, "assistant_session_outbox", bson.M{
		"_id":          assistant.SessionCreatedEventType + ":" + created.SessionID,
		"publishedAt":  bson.M{"$exists": true},
		"publishedRef": bson.M{"$exists": true},
	}, 1)
	republished, err := relay.FlushOnce(t.Context())
	if err != nil || republished != 0 {
		t.Fatalf("published event was replayed: %d %v", republished, err)
	}
}

func createAssistantSessionRequest(
	t *testing.T,
	handler http.Handler,
	accountID string,
	clientRequestID string,
) *httptest.ResponseRecorder {
	t.Helper()
	payload, err := json.Marshal(map[string]any{
		"clientRequestId": clientRequestID,
	})
	if err != nil {
		t.Fatalf("marshal create session request: %v", err)
	}
	request := httptest.NewRequest(
		http.MethodPost,
		"/assistant/sessions",
		bytes.NewReader(payload),
	)
	request.Header.Set("Content-Type", "application/json")
	request.Header.Set("Idempotency-Key", clientRequestID)
	request = request.WithContext(rtauth.WithPrincipal(
		request.Context(),
		rtauth.Principal{
			Claims: rtauth.Claims{Subject: accountID},
			Actor: operation.ActorContext{
				AccountID: accountID,
				PersonaID: accountID + ":persona",
			},
		},
	))
	recorder := httptest.NewRecorder()
	handler.ServeHTTP(recorder, request)
	return recorder
}

func assertSessionCollectionCount(
	t *testing.T,
	collection string,
	filter bson.M,
	want int64,
) {
	t.Helper()
	count, err := integrationMongoDB.Collection(collection).CountDocuments(
		t.Context(),
		filter,
	)
	if err != nil || count != want {
		t.Fatalf("%s count=%d err=%v want=%d", collection, count, err, want)
	}
}
