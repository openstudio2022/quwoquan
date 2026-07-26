// spec_ref: specs/feature-tree/circle-community/in-circle-recommendation-loop/behavior-ingestion/spec.md#gwt-001
// spec_ref: specs/feature-tree/circle-community/in-circle-recommendation-loop/spec.md#sit-001
package api_integration

import (
	"bytes"
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"

	rtauth "quwoquan_service/runtime/auth"
	"quwoquan_service/runtime/operation"
	"quwoquan_service/services/circle-service/internal/circle_management/circle/infrastructure/messaging"
	behaviorfactapp "quwoquan_service/services/circle-service/internal/circle_management/circle_behavior_fact/application"
	behaviorfactpersistence "quwoquan_service/services/circle-service/internal/circle_management/circle_behavior_fact/infrastructure/persistence"
)

func TestCircleBehaviorFactRealAppendReplayProjectionAndStream(t *testing.T) {
	cleanCollections(t)
	ctx := context.Background()
	seedMembershipCircle(t, "circle-behavior", "persona-owner", 0)

	forged := behaviorFactRequest(t, map[string]any{"circleId": "circle-behavior", "eventType": "impression"}, "behavior-key-1", "session-1")
	forged.Header.Set("X-Client-Persona-Id", "persona-viewer")
	forgedRecorder := httptest.NewRecorder()
	behaviorFactGuard().ServeHTTP(forgedRecorder, forged)
	if forgedRecorder.Code != http.StatusUnauthorized {
		t.Fatalf("forged behavior actor must fail closed: status=%d body=%s", forgedRecorder.Code, forgedRecorder.Body.String())
	}

	first := executeBehaviorFact(t, map[string]any{"circleId": "circle-behavior", "eventType": "impression"}, "behavior-key-1", "session-1", operation.ActorContext{AccountID: "account-viewer", PersonaID: "persona-viewer"})
	if first.Code != http.StatusNoContent || first.Body.Len() != 0 {
		t.Fatalf("behavior append failed: status=%d body=%s", first.Code, first.Body.String())
	}
	replay := executeBehaviorFact(t, map[string]any{"circleId": "circle-behavior", "eventType": "impression"}, "behavior-key-1", "session-1", operation.ActorContext{AccountID: "account-viewer", PersonaID: "persona-viewer"})
	if replay.Code != http.StatusNoContent {
		t.Fatalf("behavior replay failed: status=%d body=%s", replay.Code, replay.Body.String())
	}
	conflict := executeBehaviorFact(t, map[string]any{"circleId": "circle-behavior", "eventType": "click"}, "behavior-key-1", "session-1", operation.ActorContext{AccountID: "account-viewer", PersonaID: "persona-viewer"})
	if conflict.Code != http.StatusConflict || decodeBody(t, conflict)["code"] != "CIRCLE.USER.behavior_fact_idempotency_conflict" {
		t.Fatalf("behavior idempotency conflict drift: status=%d body=%s", conflict.Code, conflict.Body.String())
	}
	actorInjection := executeBehaviorFact(t, map[string]any{
		"circleId": "circle-behavior", "eventType": "click", "personaId": "forged-persona",
	}, "behavior-key-forged-body", "session-1", operation.ActorContext{AccountID: "account-viewer", PersonaID: "persona-viewer"})
	if actorInjection.Code != http.StatusBadRequest {
		t.Fatalf("actor field in business body must be rejected: status=%d body=%s", actorInjection.Code, actorInjection.Body.String())
	}

	device := executeBehaviorFact(t, map[string]any{"circleId": "circle-behavior", "eventType": "click"}, "behavior-device-1", "session-device", operation.ActorContext{DeviceActorID: "device-actor-1"})
	if device.Code != http.StatusNoContent {
		t.Fatalf("device behavior append failed: status=%d body=%s", device.Code, device.Body.String())
	}
	for collection, want := range map[string]int64{
		"circle_behavior_facts":       2,
		"circle_behavior_fact_outbox": 2,
	} {
		count, err := mongoDB.Collection(collection).CountDocuments(ctx, bson.M{})
		if err != nil || count != want {
			t.Fatalf("%s count=%d want=%d err=%v", collection, count, want, err)
		}
	}
	var personaFact bson.M
	if err := mongoDB.Collection("circle_behavior_facts").FindOne(ctx, bson.M{"personaId": "persona-viewer"}).Decode(&personaFact); err != nil {
		t.Fatal(err)
	}
	if personaFact["sessionId"] != "session-1" || personaFact["requestId"] == "" || personaFact["actorKind"] != "persona" {
		t.Fatalf("trusted behavior attribution drift: %#v", personaFact)
	}

	store := behaviorfactpersistence.NewMongoAppendSink(mongoDB)
	weeklyRelay := behaviorfactapp.NewOutboxRelay(
		store, store, behaviorfactpersistence.NewMongoWeeklyActiveProjector(mongoDB, circleCacheInvalidator),
		"circle-weekly-active-test",
	)
	if count, err := weeklyRelay.Drain(ctx, 10); err != nil || count != 2 {
		t.Fatalf("weekly-active drain count=%d err=%v", count, err)
	}
	var circle struct {
		WeeklyActiveCount int64 `bson:"weeklyActiveCount"`
	}
	if err := mongoDB.Collection("circles").FindOne(ctx, bson.M{"_id": "circle-behavior"}).Decode(&circle); err != nil {
		t.Fatal(err)
	}
	if circle.WeeklyActiveCount != 2 {
		t.Fatalf("weeklyActiveCount=%d want=2", circle.WeeklyActiveCount)
	}
	if _, err := mongoDB.Collection("circle_behavior_fact_projection_checkpoints").DeleteOne(ctx, bson.M{"_id": "circle-behavior-fact:circle-weekly-active-test"}); err != nil {
		t.Fatal(err)
	}
	if count, err := weeklyRelay.Drain(ctx, 10); err != nil || count != 2 {
		t.Fatalf("weekly-active replay count=%d err=%v", count, err)
	}

	streamRelay := behaviorfactapp.NewOutboxRelay(
		store,
		store,
		messaging.NewCircleBehaviorFactStreamPublisher(circleMessageTransport),
		"circle-behavior-fact-stream-test",
	)
	if count, err := streamRelay.Drain(ctx, 10); err != nil || count != 2 {
		t.Fatalf("behavior stream drain count=%d err=%v", count, err)
	}
	const group = "circle-behavior-api-test"
	if err := redisRouter.Scene("general").XGroupCreateMkStream(ctx, messaging.CircleBehaviorFactStream, group, "0"); err != nil {
		t.Fatal(err)
	}
	messages, err := redisRouter.Scene("general").XReadGroup(ctx, group, "reader", map[string]string{messaging.CircleBehaviorFactStream: ">"}, 10, 0)
	if err != nil || len(messages) != 2 {
		t.Fatalf("behavior stream messages=%d err=%v", len(messages), err)
	}
}

func TestCircleDiscoveryRecommendationUsesCircleOwnedLifecycleAndBehaviorFacts(t *testing.T) {
	cleanCollections(t)
	defer cleanCollections(t)

	firstCircleID := createTestCircleAs(t, "候选圈甲", "persona-owner-a")
	secondCircleID := createTestCircleAs(t, "候选圈乙", "persona-owner-b")
	path := "/circles/discovery-feed?scope=recommended&sort=active&limit=10"

	initial := doCircleDiscoveryRequest(t, path, "persona-viewer")
	if initial.Code != http.StatusOK {
		t.Fatalf("initial discovery status=%d body=%s", initial.Code, initial.Body.String())
	}
	initialCircles := decodeBody(t, initial)["circles"].([]any)
	if len(initialCircles) != 2 {
		t.Fatalf("created circles must enter discovery candidates, got=%#v", initialCircles)
	}
	targetCircleID := initialCircles[1].(map[string]any)["id"].(string)
	if targetCircleID != firstCircleID && targetCircleID != secondCircleID {
		t.Fatalf("unexpected discovery candidate %q", targetCircleID)
	}

	behavior := executeBehaviorFact(
		t,
		map[string]any{"circleId": targetCircleID, "eventType": "dwell"},
		"behavior-recommendation-rank",
		"session-recommendation-rank",
		operation.ActorContext{AccountID: "account-active-viewer", PersonaID: "persona-active-viewer"},
	)
	if behavior.Code != http.StatusNoContent {
		t.Fatalf("behavior append status=%d body=%s", behavior.Code, behavior.Body.String())
	}

	store := behaviorfactpersistence.NewMongoAppendSink(mongoDB)
	relay := behaviorfactapp.NewOutboxRelay(
		store,
		store,
		behaviorfactpersistence.NewMongoWeeklyActiveProjector(mongoDB, circleCacheInvalidator),
		"circle-discovery-recommendation-test",
	)
	if count, err := relay.Drain(t.Context(), 10); err != nil || count != 1 {
		t.Fatalf("weekly-active projection count=%d err=%v", count, err)
	}

	reranked := doCircleDiscoveryRequest(t, path, "persona-viewer")
	if reranked.Code != http.StatusOK {
		t.Fatalf("reranked discovery status=%d body=%s", reranked.Code, reranked.Body.String())
	}
	rerankedCircles := decodeBody(t, reranked)["circles"].([]any)
	if got := rerankedCircles[0].(map[string]any)["id"].(string); got != targetCircleID {
		t.Fatalf("behavior fact must invalidate cache and rank active circle first: got=%q want=%q", got, targetCircleID)
	}

	archived := executeCircleCommand(
		t,
		http.MethodDelete,
		"/circles/"+targetCircleID,
		nil,
		"archive-recommendation-candidate",
		map[string]string{firstCircleID: "persona-owner-a", secondCircleID: "persona-owner-b"}[targetCircleID],
		"ArchiveCircle",
		"/circles/{circleId}",
	)
	if archived.Code != http.StatusOK {
		t.Fatalf("archive candidate status=%d body=%s", archived.Code, archived.Body.String())
	}

	afterArchive := doCircleDiscoveryRequest(t, path, "persona-viewer")
	if afterArchive.Code != http.StatusOK {
		t.Fatalf("post-archive discovery status=%d body=%s", afterArchive.Code, afterArchive.Body.String())
	}
	remaining := decodeBody(t, afterArchive)["circles"].([]any)
	if len(remaining) != 1 || remaining[0].(map[string]any)["id"].(string) == targetCircleID {
		t.Fatalf("archived circle must leave discovery candidates: %#v", remaining)
	}
}

func behaviorFactGuard() http.Handler {
	return rtauth.RequireGeneratedOperationAuthorizationForRoute(
		[]rtauth.OperationSecurityDescriptor{{
			CanonicalOperationID: "circle.circle_behavior_fact.ReportCircleBehavior",
			ContractGraphSHA256:  "circle-behavior-api-integration",
			Method:               http.MethodPost, PathTemplate: "/circles/behaviors",
			OperationKind: "command", MutationTarget: "CircleBehaviorFact", InvariantTarget: "CircleBehaviorFact",
			AuthMode: "required", ActorRequirement: "persona_or_device", Principal: "public",
			CommercialStatus: "ready", TimeoutMilliseconds: 1000,
		}}, http.MethodPost, "/circles/behaviors",
	)(testHandler)
}

func executeBehaviorFact(t *testing.T, body any, idempotencyKey, sessionID string, actor operation.ActorContext) *httptest.ResponseRecorder {
	t.Helper()
	request := behaviorFactRequest(t, body, idempotencyKey, sessionID)
	request = request.WithContext(operation.WithContext(request.Context(), operation.Context{
		RequestID: "request-" + idempotencyKey, TraceID: "trace-" + idempotencyKey, SessionID: sessionID,
	}))
	request = request.WithContext(rtauth.WithPrincipal(request.Context(), rtauth.Principal{Actor: actor}))
	recorder := httptest.NewRecorder()
	behaviorFactGuard().ServeHTTP(recorder, request)
	return recorder
}

func behaviorFactRequest(t *testing.T, body any, idempotencyKey, sessionID string) *http.Request {
	t.Helper()
	var buffer bytes.Buffer
	if err := json.NewEncoder(&buffer).Encode(body); err != nil {
		t.Fatal(err)
	}
	request := httptest.NewRequest(http.MethodPost, "/circles/behaviors", &buffer)
	request.Header.Set("Content-Type", "application/json")
	request.Header.Set("Idempotency-Key", idempotencyKey)
	request.Header.Set("X-Request-Id", "request-"+idempotencyKey)
	request.Header.Set("X-Trace-Id", "trace-"+idempotencyKey)
	request.Header.Set("X-Client-Surface-Id", "circleDetail")
	request.Header.Set("X-Client-Session-Id", sessionID)
	request.Header.Set("X-Client-Page-Id", "circle.behaviors.report")
	request.Header.Set("X-Request-Started-At", time.Now().UTC().Format(time.RFC3339Nano))
	return request
}
