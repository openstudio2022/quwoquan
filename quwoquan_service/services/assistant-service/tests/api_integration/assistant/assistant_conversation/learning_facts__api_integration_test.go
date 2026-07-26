// spec_ref: specs/feature-tree/assistant-run-learning/learning-event-feedback-injection/learning-event-ingestion/spec.md#gwt-001
package api_integration

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	rtauth "quwoquan_service/runtime/auth"
	runtimemessaging "quwoquan_service/runtime/messaging"
	assistanthttp "quwoquan_service/services/assistant-service/internal/assistant/assistant_conversation/adapters/inbound/http"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_conversation/domain/assistant"
	learninghttp "quwoquan_service/services/assistant-service/internal/assistant/assistant_learning_fact/adapters/inbound/http"
	learningapplication "quwoquan_service/services/assistant-service/internal/assistant/assistant_learning_fact/application"
	learningmodel "quwoquan_service/services/assistant-service/internal/assistant/assistant_learning_fact/domain/model"
	learningmessaging "quwoquan_service/services/assistant-service/internal/assistant/assistant_learning_fact/infrastructure/messaging"
	learningpersistence "quwoquan_service/services/assistant-service/internal/assistant/assistant_learning_fact/infrastructure/persistence"
	learningprojection "quwoquan_service/services/assistant-service/internal/assistant/assistant_learning_fact/infrastructure/projection"
)

func newLearningFactIntegrationHandler(t *testing.T) http.Handler {
	t.Helper()
	store := learningpersistence.NewMongoStore(integrationMongoDB)
	if err := store.EnsureIndexes(t.Context()); err != nil {
		t.Fatalf("ensure learning fact indexes: %v", err)
	}
	service := learningapplication.NewService(
		store,
		learningpersistence.NewMongoRunOwnerReader(integrationMongoDB),
		nil,
	)
	mux := http.NewServeMux()
	learninghttp.NewHandler(service).RegisterRoutes(mux)
	mux.Handle("/", assistanthttp.NewHandler(newIntegrationAssistantService()).Routes())
	return mux
}

func TestAssistantLearningProjectorReplacesObsoleteReceiptSequenceIndex(
	t *testing.T,
) {
	resetIntegrationState(t)
	ctx := t.Context()
	const (
		collectionName = "assistant_learning_projection_receipts"
		indexName      = "uq_assistant_learning_projection_receipt_sequence"
	)
	collection := integrationMongoDB.Collection(collectionName)
	if err := collection.Indexes().DropOne(ctx, indexName); err != nil {
		t.Fatalf("drop current projection receipt index before migration fixture: %v", err)
	}
	if _, err := collection.Indexes().CreateOne(ctx, mongo.IndexModel{
		Keys: bson.D{
			{Key: "definitionVersion", Value: 1},
			{Key: "appendSequence", Value: 1},
		},
		Options: options.Index().SetName(indexName).SetUnique(true),
	}); err != nil {
		t.Fatalf("create obsolete projection receipt index: %v", err)
	}
	projector := learningprojection.NewMongoProjector(integrationMongoDB)
	if err := projector.EnsureIndexes(ctx); err != nil {
		t.Fatalf("replace obsolete projection receipt index: %v", err)
	}
	specifications, err := collection.Indexes().ListSpecifications(ctx)
	if err != nil {
		t.Fatalf("list projection receipt indexes: %v", err)
	}
	for _, specification := range specifications {
		if specification.Name != indexName {
			continue
		}
		var keys bson.D
		if err := bson.Unmarshal(specification.KeysDocument, &keys); err != nil {
			t.Fatalf("decode projection receipt index keys: %v", err)
		}
		if len(keys) != 2 ||
			keys[0].Key != "generationId" ||
			keys[1].Key != "appendSequence" ||
			specification.Unique == nil ||
			!*specification.Unique {
			t.Fatalf("projection receipt index not replaced: %+v", specification)
		}
		return
	}
	t.Fatalf("projection receipt index %q not found", indexName)
}

func createLearningFactRun(
	t *testing.T,
	handler http.Handler,
	userID string,
	requestID string,
) string {
	t.Helper()
	create := assistantAPIRequest(
		t,
		handler,
		http.MethodPost,
		"/assistant/conversations",
		userID,
		map[string]any{
			"summary":         "learning fact integration",
			"clientRequestId": requestID + ":conversation",
		},
	)
	if create.Code != http.StatusCreated {
		t.Fatalf("create learning fact conversation status=%d body=%s", create.Code, create.Body.String())
	}
	var conversation assistant.AssistantConversation
	if err := json.Unmarshal(create.Body.Bytes(), &conversation); err != nil {
		t.Fatalf("decode learning fact conversation: %v", err)
	}
	start := assistantAPIRequest(
		t,
		handler,
		http.MethodPost,
		"/assistant/conversations/"+conversation.ConversationID+"/runs",
		userID,
		map[string]any{
			"input":           map[string]any{"text": "记录学习事实"},
			"clientRequestId": requestID + ":turn",
		},
	)
	if start.Code != http.StatusCreated {
		t.Fatalf("create learning fact turn status=%d body=%s", start.Code, start.Body.String())
	}
	var turn assistant.AssistantTurn
	if err := json.Unmarshal(start.Body.Bytes(), &turn); err != nil {
		t.Fatalf("decode learning fact turn: %v", err)
	}
	if turn.TurnID == "" {
		t.Fatal("learning fact turn is missing turnId")
	}
	return turn.TurnID
}

func learningFactRequest(
	eventID string,
	assistantTurnID string,
) map[string]any {
	return map[string]any{
		"eventId":          eventID,
		"eventVersion":     1,
		"factType":         "user_feedback",
		"assistantTurnId":  assistantTurnID,
		"referralSource":   "article",
		"domainId":         "assistant",
		"feedbackType":     "useful",
		"actionType":       "thumbs_up",
		"trainingEligible": false,
		"occurredAt":       time.Now().UTC().Format(time.RFC3339Nano),
	}
}

// TestAssistantLearningFactHTTPContract verifies that the public endpoint writes
// a durable fact, its outbox payload and rejects noncanonical provenance.
func TestAssistantLearningFactHTTPContract(t *testing.T) {
	resetIntegrationState(t)
	ctx := context.Background()
	handler := newLearningFactIntegrationHandler(t)
	turnID := createLearningFactRun(t, handler, "learn-user", "learning-http")

	valid := assistantAPIRequest(
		t,
		handler,
		http.MethodPost,
		"/assistant/learning/facts",
		"learn-user",
		learningFactRequest("fact-http-1", turnID),
	)
	if valid.Code != http.StatusOK {
		t.Fatalf("append learning fact status=%d body=%s", valid.Code, valid.Body.String())
	}
	var receipt learningmodel.Receipt
	if err := json.Unmarshal(valid.Body.Bytes(), &receipt); err != nil {
		t.Fatalf("decode learning fact receipt: %v", err)
	}
	if !receipt.Accepted || receipt.EventID != "fact-http-1" ||
		receipt.AppendSequence <= 0 {
		t.Fatalf("unexpected learning fact receipt=%+v", receipt)
	}
	var fact learningmodel.Fact
	if err := integrationMongoDB.Collection("assistant_learning_facts").
		FindOne(ctx, bson.M{"eventId": "fact-http-1", "eventVersion": 1}).
		Decode(&fact); err != nil {
		t.Fatalf("load learning fact: %v", err)
	}
	if fact.UserID != "learn-user" ||
		fact.PersonaID != "learn-user:persona" ||
		fact.AssistantTurnID != turnID ||
		fact.ReferralSource != "article" ||
		fact.FeedbackType != "useful" {
		t.Fatalf("stored learning fact provenance=%+v", fact)
	}
	outboxCount, err := integrationMongoDB.Collection("assistant_learning_fact_outbox").
		CountDocuments(ctx, bson.M{"_id": fact.StorageID})
	if err != nil || outboxCount != 1 {
		t.Fatalf("learning fact outbox count=%d err=%v", outboxCount, err)
	}
	projected, err := integrationLearningProjector.ProjectAvailable(ctx, 32)
	if err != nil || projected != 1 {
		t.Fatalf(
			"project canonical learning fact projected=%d err=%v",
			projected,
			err,
		)
	}
	summary, err := newIntegrationAssistantService().GetLearningOpsSummary(
		ctx,
		"learn-user",
	)
	if err != nil ||
		summary.TotalFeedbackCount != 1 ||
		summary.PositiveFeedbackCount != 1 ||
		summary.LastFeedbackType != "useful" {
		t.Fatalf("learning projection summary=%+v err=%v", summary, err)
	}
	if projected, err := integrationLearningProjector.ProjectAvailable(ctx, 32); err != nil || projected != 0 {
		t.Fatalf(
			"reprojected canonical fact projected=%d err=%v",
			projected,
			err,
		)
	}

	invalidBody := learningFactRequest("fact-invalid-source", turnID)
	invalidBody["referralSource"] = "untrusted-source"
	invalid := assistantAPIRequest(
		t,
		handler,
		http.MethodPost,
		"/assistant/learning/facts",
		"learn-user",
		invalidBody,
	)
	if invalid.Code != http.StatusBadRequest {
		t.Fatalf("invalid provenance status=%d body=%s", invalid.Code, invalid.Body.String())
	}
	count, err := integrationMongoDB.Collection("assistant_learning_facts").
		CountDocuments(ctx, bson.M{})
	if err != nil || count != 1 {
		t.Fatalf("invalid learning fact must not persist: count=%d err=%v", count, err)
	}
}

// TestAssistantLearningFactAppendDedupe verifies idempotent append identity and
// makes the server-assigned sequence durable across an HTTP retry.
func TestAssistantLearningFactAppendDedupe(t *testing.T) {
	resetIntegrationState(t)
	ctx := context.Background()
	handler := newLearningFactIntegrationHandler(t)
	turnID := createLearningFactRun(t, handler, "dedupe-user", "learning-dedupe")
	body := learningFactRequest("fact-dedupe-1", turnID)

	var first learningmodel.Receipt
	for attempt := 0; attempt < 2; attempt++ {
		response := assistantAPIRequest(
			t,
			handler,
			http.MethodPost,
			"/assistant/learning/facts",
			"dedupe-user",
			body,
		)
		if response.Code != http.StatusOK {
			t.Fatalf("attempt %d status=%d body=%s", attempt, response.Code, response.Body.String())
		}
		var receipt learningmodel.Receipt
		if err := json.Unmarshal(response.Body.Bytes(), &receipt); err != nil {
			t.Fatalf("decode dedupe receipt: %v", err)
		}
		if attempt == 0 {
			first = receipt
			continue
		}
		if !receipt.Deduplicated ||
			receipt.AppendSequence != first.AppendSequence ||
			receipt.PayloadDigest != first.PayloadDigest {
			t.Fatalf("dedupe receipt first=%+v replay=%+v", first, receipt)
		}
	}
	count, err := integrationMongoDB.Collection("assistant_learning_facts").
		CountDocuments(ctx, bson.M{"eventId": "fact-dedupe-1", "eventVersion": 1})
	if err != nil || count != 1 {
		t.Fatalf("dedupe must keep one fact: count=%d err=%v", count, err)
	}
}

func TestAssistantLearningFactOutboxClaimSurvivesReplicaHandoff(t *testing.T) {
	resetIntegrationState(t)
	ctx := t.Context()
	handler := newLearningFactIntegrationHandler(t)
	turnID := createLearningFactRun(
		t,
		handler,
		"relay-owner",
		"learning-relay-claim",
	)
	response := assistantAPIRequest(
		t,
		handler,
		http.MethodPost,
		"/assistant/learning/facts",
		"relay-owner",
		learningFactRequest("fact-relay-claim", turnID),
	)
	if response.Code != http.StatusOK {
		t.Fatalf(
			"append relay fact status=%d body=%s",
			response.Code,
			response.Body.String(),
		)
	}
	store := learningpersistence.NewMongoStore(integrationMongoDB)
	first, err := store.ClaimPendingOutbox(ctx, "replica-a", time.Minute, 1)
	if err != nil || len(first) != 1 {
		t.Fatalf("first claim=%+v err=%v", first, err)
	}
	second, err := store.ClaimPendingOutbox(ctx, "replica-b", time.Minute, 1)
	if err != nil || len(second) != 0 {
		t.Fatalf("concurrent claim=%+v err=%v", second, err)
	}
	if err := store.ReleaseOutboxClaim(ctx, first[0].ID, "replica-a"); err != nil {
		t.Fatalf("release first claim: %v", err)
	}
	second, err = store.ClaimPendingOutbox(ctx, "replica-b", time.Minute, 1)
	if err != nil || len(second) != 1 || second[0].ID != first[0].ID {
		t.Fatalf("handoff claim=%+v err=%v", second, err)
	}
	if err := store.MarkOutboxPublished(
		ctx,
		second[0].ID,
		"replica-a",
		"stream-wrong",
		time.Now().UTC(),
	); !errors.Is(err, learningpersistence.ErrOutboxClaimLost) {
		t.Fatalf("wrong owner checkpoint error=%v", err)
	}
	if err := store.MarkOutboxPublished(
		ctx,
		second[0].ID,
		"replica-b",
		"stream-1",
		time.Now().UTC(),
	); err != nil {
		t.Fatalf("mark handoff claim published: %v", err)
	}
	remaining, err := store.ClaimPendingOutbox(ctx, "replica-a", time.Minute, 1)
	if err != nil || len(remaining) != 0 {
		t.Fatalf("published outbox reclaimed=%+v err=%v", remaining, err)
	}
}

func TestAssistantLearningFactRelayPublishesCanonicalDurableEvent(t *testing.T) {
	resetIntegrationState(t)
	ctx := t.Context()
	handler := newLearningFactIntegrationHandler(t)
	turnID := createLearningFactRun(
		t,
		handler,
		"relay-stream-owner",
		"learning-relay-stream",
	)
	requestPayload := learningFactRequest("fact-relay-stream", turnID)
	requestPayload["queryText"] = "private query for digest only"
	response := assistantAPIRequest(
		t,
		handler,
		http.MethodPost,
		"/assistant/learning/facts",
		"relay-stream-owner",
		requestPayload,
	)
	if response.Code != http.StatusOK {
		t.Fatalf(
			"append relay fact status=%d body=%s",
			response.Code,
			response.Body.String(),
		)
	}

	transport := newIntegrationMessageTransport()
	if err := transport.SetDurableRetention(
		ctx,
		learningmessaging.LearningFactStream,
		time.Hour,
	); err != nil {
		t.Fatalf("set learning stream retention: %v", err)
	}
	relay, err := learningmessaging.NewOutboxRelay(
		learningpersistence.NewMongoStore(integrationMongoDB),
		transport,
		time.Second,
		32,
		nil,
	)
	if err != nil {
		t.Fatalf("NewOutboxRelay() error = %v", err)
	}
	if published, err := relay.FlushOnce(ctx); err != nil || published != 1 {
		t.Fatalf("FlushOnce() published=%d error=%v", published, err)
	}
	const group = "assistant-learning-fact-contract"
	if err := transport.EnsureDurableConsumerGroup(
		ctx,
		learningmessaging.LearningFactStream,
		group,
		"0",
	); err != nil {
		t.Fatalf("ensure learning fact consumer group: %v", err)
	}
	deliveries, err := transport.ReadDurable(
		ctx,
		runtimemessaging.StreamReadRequest{
			Stream:   learningmessaging.LearningFactStream,
			Group:    group,
			Consumer: "contract-reader",
			Count:    1,
			Block:    100 * time.Millisecond,
		},
	)
	if err != nil || len(deliveries) != 1 {
		t.Fatalf("durable deliveries=%+v error=%v", deliveries, err)
	}
	fields := make(map[string]string, len(deliveries[0].Fields))
	for _, field := range deliveries[0].Fields {
		fields[field.Name] = field.Value
	}
	if fields["eventType"] != "AssistantLearningFactAppended" ||
		fields["aggregateType"] != "AssistantLearningFact" ||
		fields["aggregateId"] != "fact-relay-stream" ||
		fields["aggregateVersion"] != "1" {
		t.Fatalf("canonical event fields = %#v", fields)
	}
	var payload learningmodel.RedactedPayload
	if err := json.Unmarshal([]byte(fields["payload"]), &payload); err != nil {
		t.Fatalf("decode redacted event payload: %v", err)
	}
	if payload.EventID != "fact-relay-stream" ||
		payload.AssistantTurnID != turnID ||
		payload.QueryTextDigest == "" {
		t.Fatalf("redacted event payload = %+v", payload)
	}
	if bytes.Contains(
		[]byte(fields["payload"]),
		[]byte("private query for digest only"),
	) {
		t.Fatalf("durable payload leaked raw query: %s", fields["payload"])
	}
	if err := transport.AckDurable(
		ctx,
		learningmessaging.LearningFactStream,
		group,
		deliveries[0].ID,
	); err != nil {
		t.Fatalf("ack learning fact delivery: %v", err)
	}
}

// spec_ref: specs/feature-tree/assistant-run-learning/learning-event-feedback-injection/feedback-aggregation/spec.md#gwt-001
func TestAssistantLearningProjectionRebuildActivatesEquivalentGeneration(
	t *testing.T,
) {
	resetIntegrationState(t)
	ctx := context.Background()
	handler := newLearningFactIntegrationHandler(t)
	turnID := createLearningFactRun(
		t,
		handler,
		"rebuild-user",
		"learning-rebuild",
	)
	for _, eventID := range []string{"fact-rebuild-1", "fact-rebuild-2"} {
		response := assistantAPIRequest(
			t,
			handler,
			http.MethodPost,
			"/assistant/learning/facts",
			"rebuild-user",
			learningFactRequest(eventID, turnID),
		)
		if response.Code != http.StatusOK {
			t.Fatalf("append %s status=%d body=%s", eventID, response.Code, response.Body.String())
		}
	}
	if projected, err := integrationLearningProjector.ProjectAvailable(
		ctx,
		32,
	); err != nil || projected != 2 {
		t.Fatalf("initial projection projected=%d err=%v", projected, err)
	}
	before, err := integrationLearningProjector.GetLearningProjection(
		ctx,
		"rebuild-user",
	)
	if err != nil || before == nil {
		t.Fatalf("read initial projection=%+v err=%v", before, err)
	}

	rebuilt, err := integrationLearningProjector.Rebuild(ctx)
	if err != nil || rebuilt != 2 {
		t.Fatalf("rebuild projected=%d err=%v", rebuilt, err)
	}
	after, err := integrationLearningProjector.GetLearningProjection(
		ctx,
		"rebuild-user",
	)
	if err != nil || after == nil {
		t.Fatalf("read rebuilt projection=%+v err=%v", after, err)
	}
	if before.TotalFeedbackCount != after.TotalFeedbackCount ||
		before.PositiveFeedbackCount != after.PositiveFeedbackCount ||
		before.WatermarkSequence != after.WatermarkSequence ||
		before.DefinitionVersion != after.DefinitionVersion {
		t.Fatalf("rebuild changed canonical aggregates: before=%+v after=%+v", before, after)
	}
	if before.StorageID == after.StorageID {
		t.Fatalf("rebuild did not activate a distinct shadow generation: %q", after.StorageID)
	}
	var active struct {
		DefinitionVersion string `bson:"definitionVersion"`
		GenerationID      string `bson:"generationId"`
	}
	if err := integrationMongoDB.Collection(
		"assistant_learning_projection_watermarks",
	).FindOne(ctx, bson.M{"_id": "active"}).Decode(&active); err != nil {
		t.Fatalf("read active projection generation: %v", err)
	}
	if active.DefinitionVersion != learningmodel.LearningProjectionDefinitionVersion ||
		active.GenerationID == "" ||
		active.GenerationID == learningmodel.LearningProjectionDefinitionVersion {
		t.Fatalf("unexpected active definition=%+v", active)
	}
}

// TestAssistantLearningFactOwnerAndWireValidation verifies that the fact owner
// only comes from the verified principal and that unknown request fields are
// rejected instead of being silently accepted.
func TestAssistantLearningFactOwnerAndWireValidation(t *testing.T) {
	resetIntegrationState(t)
	ctx := context.Background()
	handler := newLearningFactIntegrationHandler(t)
	ownerTurnID := createLearningFactRun(t, handler, "trusted-owner", "learning-owner")

	foreign := assistantAPIRequest(
		t,
		handler,
		http.MethodPost,
		"/assistant/learning/facts",
		"intruder",
		learningFactRequest("fact-forged-owner", ownerTurnID),
	)
	if foreign.Code != http.StatusForbidden {
		t.Fatalf("foreign owner status=%d body=%s", foreign.Code, foreign.Body.String())
	}

	unknownField := learningFactRequest("fact-unknown-field", ownerTurnID)
	unknownField["userId"] = "forged-in-body"
	rejected := assistantAPIRequest(
		t,
		handler,
		http.MethodPost,
		"/assistant/learning/facts",
		"trusted-owner",
		unknownField,
	)
	if rejected.Code != http.StatusBadRequest {
		t.Fatalf("unknown request field status=%d body=%s", rejected.Code, rejected.Body.String())
	}
	mixedPayload := learningFactRequest("fact-mixed-payload", ownerTurnID)
	mixedPayload["metricId"] = "turn_completion"
	mixedPayload["metricValue"] = 1
	mixedPayload["metricSource"] = "client"
	rejected = assistantAPIRequest(
		t,
		handler,
		http.MethodPost,
		"/assistant/learning/facts",
		"trusted-owner",
		mixedPayload,
	)
	if rejected.Code != http.StatusBadRequest {
		t.Fatalf("mixed public payload status=%d body=%s", rejected.Code, rejected.Body.String())
	}

	anonymous := httptest.NewRequest(
		http.MethodPost,
		"/assistant/learning/facts",
		nil,
	)
	anonymous.Header.Set("Content-Type", "application/json")
	recorder := httptest.NewRecorder()
	handler.ServeHTTP(recorder, anonymous)
	if recorder.Code != http.StatusUnauthorized {
		t.Fatalf("anonymous status=%d body=%s", recorder.Code, recorder.Body.String())
	}
	count, err := integrationMongoDB.Collection("assistant_learning_facts").
		CountDocuments(ctx, bson.M{})
	if err != nil || count != 0 {
		t.Fatalf("rejected facts must not persist: count=%d err=%v", count, err)
	}
}

func TestAssistantServiceLearningFactRequiresServicePrincipal(t *testing.T) {
	resetIntegrationState(t)
	handler := newLearningFactIntegrationHandler(t)
	turnID := createLearningFactRun(
		t,
		handler,
		"service-score-owner",
		"learning-service-score",
	)
	payload, err := json.Marshal(map[string]any{
		"eventId":          "service-scorecard-1",
		"eventVersion":     1,
		"factType":         "service_scorecard",
		"assistantTurnId":  turnID,
		"referralSource":   "assistant_conversation",
		"domainId":         "assistant",
		"metricId":         "turn_completion",
		"metricValue":      1,
		"metricSource":     "service_auto",
		"trainingEligible": false,
		"occurredAt":       time.Now().UTC().Format(time.RFC3339Nano),
	})
	if err != nil {
		t.Fatalf("marshal service scorecard: %v", err)
	}
	request := httptest.NewRequest(
		http.MethodPost,
		"/internal/assistant/learning/facts",
		bytes.NewReader(payload),
	)
	request.Header.Set("Content-Type", "application/json")
	request = request.WithContext(rtauth.WithPrincipal(
		request.Context(),
		rtauth.Principal{Claims: rtauth.Claims{
			Subject: "service:assistant-scorecard",
		}},
	))
	recorder := httptest.NewRecorder()
	handler.ServeHTTP(recorder, request)
	if recorder.Code != http.StatusOK {
		t.Fatalf(
			"service scorecard status=%d body=%s",
			recorder.Code,
			recorder.Body.String(),
		)
	}

	request = httptest.NewRequest(
		http.MethodPost,
		"/internal/assistant/learning/facts",
		bytes.NewReader(payload),
	)
	request.Header.Set("Content-Type", "application/json")
	request = request.WithContext(rtauth.WithPrincipal(
		request.Context(),
		rtauth.Principal{Claims: rtauth.Claims{
			Subject: "account-not-service",
		}},
	))
	recorder = httptest.NewRecorder()
	handler.ServeHTTP(recorder, request)
	if recorder.Code != http.StatusUnauthorized {
		t.Fatalf(
			"account principal internal scorecard status=%d body=%s",
			recorder.Code,
			recorder.Body.String(),
		)
	}
}

// spec_ref: specs/feature-tree/assistant-run-learning/learning-event-feedback-injection/feedback-context-injection/spec.md#gwt-001
func TestAssistantLearningProjectionSeparatesPersonaOwners(t *testing.T) {
	resetIntegrationState(t)
	ctx := t.Context()
	recordedAt := time.Date(2026, time.July, 26, 0, 0, 0, 0, time.UTC)
	appendPersonaFact := func(personaID string, eventID string) {
		t.Helper()
		fact, err := learningmodel.Build(
			learningmodel.AppendCommand{
				EventID:          eventID,
				EventVersion:     1,
				FactType:         learningmodel.FactTypeUserFeedback,
				AssistantTurnID:  "turn-" + personaID,
				ReferralSource:   "assistant_conversation",
				DomainID:         "assistant",
				FeedbackType:     "useful",
				ActionType:       "useful",
				TrainingEligible: false,
				OccurredAt:       recordedAt,
			},
			learningmodel.TrustedContext{
				UserID:    "owner-shared-account",
				PersonaID: personaID,
			},
			recordedAt,
		)
		if err != nil {
			t.Fatalf("build persona fact %s: %v", personaID, err)
		}
		if _, err := integrationLearningFactStore.Append(ctx, fact); err != nil {
			t.Fatalf("append persona fact %s: %v", personaID, err)
		}
	}

	appendPersonaFact("persona-a", "persona-owner-a-feedback")
	appendPersonaFact("persona-b", "persona-owner-b-feedback")
	if projected, err := integrationLearningProjector.ProjectAvailable(ctx, 8); err != nil || projected != 2 {
		t.Fatalf("project persona facts = %d, %v", projected, err)
	}

	for _, personaID := range []string{"persona-a", "persona-b"} {
		projection, err := integrationLearningProjector.GetLearningProjectionForPersona(
			ctx,
			"owner-shared-account",
			personaID,
		)
		if err != nil {
			t.Fatalf("read persona projection %s: %v", personaID, err)
		}
		if projection == nil ||
			projection.UserID != "owner-shared-account" ||
			projection.PersonaID != personaID ||
			projection.TotalFeedbackCount != 1 ||
			projection.PositiveFeedbackCount != 1 {
			t.Fatalf("persona projection %s = %+v", personaID, projection)
		}
	}
}
