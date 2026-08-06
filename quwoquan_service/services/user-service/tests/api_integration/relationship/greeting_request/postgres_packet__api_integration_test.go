// spec_ref: specs/feature-tree/chat-conversation/contact-and-session-governance/greeting-request-inbox-and-upgrade/spec.md#gwt-001
// readiness_case: send-greeting-request-api
// readiness_case: list-greeting-inbox-api
// readiness_case: list-greeting-outbox-api
// readiness_case: reply-greeting-request-api
// readiness_case: ignore-greeting-request-api
// readiness_case: cancel-greeting-request-api
package api_integration

import (
	"bytes"
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/jackc/pgx/v5/pgxpool"
	"quwoquan_service/runtime/operation"
	greetinghttp "quwoquan_service/services/user-service/internal/relationship/greeting_request/adapters/inbound/http"
	greetingapp "quwoquan_service/services/user-service/internal/relationship/greeting_request/application"
	greetingmodel "quwoquan_service/services/user-service/internal/relationship/greeting_request/domain/model"
	greetingports "quwoquan_service/services/user-service/internal/relationship/greeting_request/domain/ports"
	greetingpersistence "quwoquan_service/services/user-service/internal/relationship/greeting_request/infrastructure/persistence"
	relationshipmodel "quwoquan_service/services/user-service/internal/relationship/persona_relationship/domain/model"
	usersupport "quwoquan_service/services/user-service/tests/support"
)

type apiRelationships struct{}

func (apiRelationships) GetRelationship(context.Context, string, string) (relationshipmodel.RelationshipState, error) {
	return relationshipmodel.RelationshipState{}, nil
}

type apiConversationGateway struct{}

func (apiConversationGateway) PromoteGreetingToDirect(_ context.Context, _, _ string, promotion greetingapp.GreetingPromotion) (string, error) {
	return "conversation-" + promotion.GreetingRequestID, nil
}

func (apiConversationGateway) HasDirectBetween(context.Context, string, string) (bool, error) {
	return false, nil
}

type apiEventPublisher struct{}

func (apiEventPublisher) PublishUserEvent(context.Context, string, string, string, map[string]any) error {
	return nil
}

type apiGreetingStream struct{}

func (apiGreetingStream) PublishGreetingEvent(context.Context, greetingapp.GreetingStreamEvent) error {
	return nil
}

type apiGreetingPolicy struct{}

func (apiGreetingPolicy) AllowsStrangerGreeting(context.Context, string) (bool, error) {
	return true, nil
}

func TestGreetingRequestPostgresStateReceiptAndOutboxAreAtomic(t *testing.T) {
	usersupport.WithUserPostgres(t, func(ctx context.Context, pool *pgxpool.Pool) {
		store := greetingpersistence.NewPgGreetingStore(pool)
		now := time.Now().UTC()
		greeting := &greetingmodel.GreetingRequest{
			ID: "11111111-1111-4111-8111-111111111111", RequesterPersonaID: "requester", TargetPersonaID: "target",
			RequestMessage: "你好", Status: greetingmodel.GreetingStatusPending, Source: "homepage", CreatedAt: now, UpdatedAt: now,
		}
		if err := store.CommitCommand(ctx, greetingports.GreetingCommit{
			Greeting: greeting, Insert: true, ActorPersonaID: greeting.RequesterPersonaID,
			IdempotencyKey: "greeting-send-key", Operation: "SendGreetingRequest",
			EventID: "greeting-event-1", EventName: "GreetingRequestSent", EventPayload: map[string]any{"id": greeting.ID}, OccurredAt: now,
		}); err != nil {
			t.Fatal(err)
		}
		replayed, found, err := store.LoadCommandReceipt(ctx, greeting.RequesterPersonaID, "greeting-send-key", "SendGreetingRequest")
		if err != nil || !found || replayed.ID != greeting.ID {
			t.Fatalf("GreetingRequest receipt drift: value=%+v found=%v err=%v", replayed, found, err)
		}
		var outboxCount int
		if err := pool.QueryRow(ctx, `SELECT COUNT(*) FROM greeting_request_outbox WHERE aggregate_id=$1`, greeting.ID).Scan(&outboxCount); err != nil || outboxCount != 1 {
			t.Fatalf("GreetingRequest outbox=%d err=%v", outboxCount, err)
		}

		if err := usersupport.SeedAccountPersona(ctx, pool, "greeting-http-requester-account", "greeting-http-requester"); err != nil {
			t.Fatal(err)
		}
		if err := usersupport.SeedAccountPersona(ctx, pool, "greeting-http-target-account", "greeting-http-target"); err != nil {
			t.Fatal(err)
		}
		service := greetingapp.NewGreetingService(
			store,
			store,
			apiRelationships{},
			apiConversationGateway{},
			apiEventPublisher{},
			apiGreetingStream{},
			apiGreetingPolicy{},
		)
		handler, err := greetinghttp.NewHandler(service)
		if err != nil {
			t.Fatal(err)
		}
		mux := http.NewServeMux()
		handler.RegisterRoutes(mux)
		serve := func(method, path, actorID, idempotencyKey, body string) *httptest.ResponseRecorder {
			request := httptest.NewRequest(method, path, bytes.NewBufferString(body))
			request.Header.Set("Content-Type", "application/json")
			request.Header.Set("Idempotency-Key", idempotencyKey)
			request = request.WithContext(operation.WithContext(request.Context(), operation.Context{
				OperationID:    "greeting-api-integration",
				RequestID:      "greeting-api-integration",
				TraceID:        "greeting-api-integration",
				IdempotencyKey: idempotencyKey,
				Actor:          operation.ActorContext{PersonaID: actorID},
			}))
			response := httptest.NewRecorder()
			mux.ServeHTTP(response, request)
			return response
		}
		send := func(key string) string {
			response := serve(
				http.MethodPost,
				"/user/greeting-request",
				"greeting-http-requester",
				key,
				`{"targetPersonaId":"greeting-http-target","requestMessage":"你好","source":"profile"}`,
			)
			if response.Code != http.StatusCreated {
				t.Fatalf("production SendGreetingRequest(%s) status=%d body=%s", key, response.Code, response.Body.String())
			}
			var payload map[string]any
			if err := json.Unmarshal(response.Body.Bytes(), &payload); err != nil {
				t.Fatal(err)
			}
			id, _ := payload["id"].(string)
			if id == "" {
				t.Fatalf("production SendGreetingRequest missing id: %s", response.Body.String())
			}
			return id
		}

		firstID := send("greeting-http-send-1")
		inbox := serve(http.MethodGet, "/user/greeting-request/inbox?status=pending", "greeting-http-target", "", "")
		if inbox.Code != http.StatusOK || !bytes.Contains(inbox.Body.Bytes(), []byte(firstID)) {
			t.Fatalf("production ListGreetingInbox status=%d body=%s", inbox.Code, inbox.Body.String())
		}
		outbox := serve(http.MethodGet, "/user/greeting-request/outbox?status=pending", "greeting-http-requester", "", "")
		if outbox.Code != http.StatusOK || !bytes.Contains(outbox.Body.Bytes(), []byte(firstID)) {
			t.Fatalf("production ListGreetingOutbox status=%d body=%s", outbox.Code, outbox.Body.String())
		}
		reply := serve(http.MethodPost, "/user/greeting-request/"+firstID+"/reply", "greeting-http-target", "greeting-http-reply-1", "{}")
		if reply.Code != http.StatusOK || !bytes.Contains(reply.Body.Bytes(), []byte(`"status":"replied"`)) {
			t.Fatalf("production ReplyGreetingRequest status=%d body=%s", reply.Code, reply.Body.String())
		}

		secondID := send("greeting-http-send-2")
		ignore := serve(http.MethodPost, "/user/greeting-request/"+secondID+"/ignore", "greeting-http-target", "greeting-http-ignore-1", "{}")
		if ignore.Code != http.StatusOK || !bytes.Contains(ignore.Body.Bytes(), []byte(`"status":"ignored"`)) {
			t.Fatalf("production IgnoreGreetingRequest status=%d body=%s", ignore.Code, ignore.Body.String())
		}

		thirdID := send("greeting-http-send-3")
		cancel := serve(http.MethodDelete, "/user/greeting-request/"+thirdID, "greeting-http-requester", "greeting-http-cancel-1", "")
		if cancel.Code != http.StatusOK || !bytes.Contains(cancel.Body.Bytes(), []byte(`"status":"cancelled"`)) {
			t.Fatalf("production CancelGreetingRequest status=%d body=%s", cancel.Code, cancel.Body.String())
		}
		var terminalCount int
		if err := pool.QueryRow(
			ctx,
			`SELECT COUNT(*) FROM greeting_requests WHERE id = ANY($1) AND status IN ('replied','ignored','cancelled')`,
			[]string{firstID, secondID, thirdID},
		).Scan(&terminalCount); err != nil || terminalCount != 3 {
			t.Fatalf("production GreetingRequest terminal rows=%d err=%v", terminalCount, err)
		}
	})
}
