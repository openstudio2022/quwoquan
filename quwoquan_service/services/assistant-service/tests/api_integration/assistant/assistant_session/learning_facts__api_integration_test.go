// spec_ref: specs/feature-tree/assistant-run-learning/learning-event-feedback-injection/learning-event-ingestion/spec.md#gwt-001
// spec_ref: specs/feature-tree/assistant-run-learning/learning-event-feedback-injection/feedback-aggregation/spec.md#gwt-001
package api_integration

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	runtimemessaging "quwoquan_service/runtime/messaging"
	learninghttp "quwoquan_service/services/assistant-service/internal/assistant/assistant_learning_fact/adapters/inbound/http"
	learningapplication "quwoquan_service/services/assistant-service/internal/assistant/assistant_learning_fact/application"
	learningmodel "quwoquan_service/services/assistant-service/internal/assistant/assistant_learning_fact/domain/model"
	learningmessaging "quwoquan_service/services/assistant-service/internal/assistant/assistant_learning_fact/infrastructure/messaging"
	learningpersistence "quwoquan_service/services/assistant-service/internal/assistant/assistant_learning_fact/infrastructure/persistence"
	learningprojection "quwoquan_service/services/assistant-service/internal/assistant/assistant_learning_fact/infrastructure/projection"
	runpersistence "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/infrastructure"
	assistant "quwoquan_service/services/assistant-service/internal/assistant/assistant_session/domain/model"
	"quwoquan_service/services/assistant-service/tests/support/assistantingress"
)

func newLearningFactIntegrationHandler(t *testing.T) http.Handler {
	t.Helper()
	store := learningpersistence.NewMongoStore(integrationMongoDB)
	if err := store.EnsureIndexes(t.Context()); err != nil {
		t.Fatalf("ensure learning fact indexes: %v", err)
	}
	service := learningapplication.NewAssistantLearningFactAppender(
		store,
		runpersistence.NewMongoRunOwnerReader(integrationMongoDB),
		nil,
	)
	mux := http.NewServeMux()
	learninghttp.NewHandler(
		service,
		learningapplication.NewOpsQueryService(integrationLearningProjector),
	).RegisterRoutes(mux)
	mux.Handle("/", assistantingress.Routes(newIntegrationAssistantService()))
	return mux
}

func TestAssistantLearningProjectorReplacesNoncanonicalReceiptSequenceIndex(
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
			{Key: "eventId", Value: 1},
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
		"/assistant/sessions",
		userID,
		map[string]any{
			"summary":         "learning fact integration",
			"clientRequestId": requestID + ":session",
		},
	)
	if create.Code != http.StatusCreated {
		t.Fatalf("create learning fact session status=%d body=%s", create.Code, create.Body.String())
	}
	var session assistant.AssistantSession
	if err := json.Unmarshal(create.Body.Bytes(), &session); err != nil {
		t.Fatalf("decode learning fact session: %v", err)
	}
	start := assistantAPIRequest(
		t,
		handler,
		http.MethodPost,
		"/assistant/sessions/"+session.SessionID+"/runs",
		userID,
		map[string]any{
			"intent": map[string]any{
				"kind": "answer", "answer": map[string]any{"text": "记录学习事实"},
			},
			"clientRequestId": requestID + ":turn",
		},
	)
	if start.Code != http.StatusCreated {
		t.Fatalf("create learning fact turn status=%d body=%s", start.Code, start.Body.String())
	}
	var run struct {
		RunID string `json:"runId"`
	}
	if err := json.Unmarshal(start.Body.Bytes(), &run); err != nil {
		t.Fatalf("decode learning fact run: %v", err)
	}
	if run.RunID == "" {
		t.Fatal("learning fact run is missing runId")
	}
	return run.RunID
}

func learningFactRequest(
	eventID string,
	assistantTurnID string,
) map[string]any {
	return map[string]any{
		"eventId":          eventID,
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
		FindOne(ctx, bson.M{"eventId": "fact-http-1"}).
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
	summaryResponse := assistantAPIRequest(
		t,
		handler,
		http.MethodGet,
		"/assistant/ops/learning-summary",
		"learn-user",
		nil,
	)
	if summaryResponse.Code != http.StatusOK {
		t.Fatalf(
			"learning projection summary status=%d body=%s",
			summaryResponse.Code,
			summaryResponse.Body.String(),
		)
	}
	var summary learningmodel.AssistantLearningOpsSummaryView
	if err := json.Unmarshal(summaryResponse.Body.Bytes(), &summary); err != nil {
		t.Fatalf("decode learning projection summary: %v", err)
	}
	if summary.TotalFeedbackCount != 1 ||
		summary.PositiveFeedbackCount != 1 ||
		summary.LastFeedbackType != "useful" {
		t.Fatalf("learning projection summary=%+v", summary)
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
		CountDocuments(ctx, bson.M{"eventId": "fact-dedupe-1"})
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
	if _, err := integrationMongoDB.Collection(
		"assistant_learning_projection_watermarks",
	).ReplaceOne(
		ctx,
		bson.M{"_id": "active"},
		bson.M{
			"_id":          "active",
			"generationId": before.GenerationID,
			"updatedAt":    time.Now().UTC(),
		},
	); err != nil {
		t.Fatalf("install noncanonical active projection fixture: %v", err)
	}
	if _, err := integrationLearningProjector.GetLearningProjection(
		ctx,
		"rebuild-user",
	); !errors.Is(err, learningprojection.ErrDefinitionMismatch) {
		t.Fatalf("noncanonical active projection must fail closed: %v", err)
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
		before.DefinitionDigest != after.DefinitionDigest {
		t.Fatalf("rebuild changed canonical aggregates: before=%+v after=%+v", before, after)
	}
	if before.StorageID == after.StorageID {
		t.Fatalf("rebuild did not activate a distinct shadow generation: %q", after.StorageID)
	}
	var active struct {
		DefinitionDigest string `bson:"definitionDigest"`
		GenerationID     string `bson:"generationId"`
	}
	if err := integrationMongoDB.Collection(
		"assistant_learning_projection_watermarks",
	).FindOne(ctx, bson.M{"_id": "active"}).Decode(&active); err != nil {
		t.Fatalf("read active projection generation: %v", err)
	}
	if active.DefinitionDigest != learningmodel.LearningProjectionDefinitionDigest ||
		!strings.HasPrefix(active.GenerationID, "rebuild:") ||
		!learningmodel.IsLearningProjectionGenerationID(active.GenerationID) ||
		active.GenerationID == learningmodel.LearningProjectionDefinitionDigest {
		t.Fatalf("unexpected active definition=%+v", active)
	}
	for collectionName, filter := range map[string]bson.M{
		"rm_assistant_learning_projection": {
			"generationId": bson.M{"$ne": active.GenerationID},
		},
		"assistant_learning_projection_receipts": {
			"generationId": bson.M{"$ne": active.GenerationID},
		},
		"assistant_learning_projection_watermarks": {
			"_id": bson.M{"$nin": bson.A{"active", active.GenerationID}},
		},
	} {
		count, countErr := integrationMongoDB.Collection(collectionName).
			CountDocuments(ctx, filter)
		if countErr != nil || count != 0 {
			t.Fatalf(
				"non-active generation remained in %s: count=%d err=%v",
				collectionName,
				count,
				countErr,
			)
		}
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
				FactType:         learningmodel.FactTypeUserFeedback,
				AssistantTurnID:  "turn-" + personaID,
				ReferralSource:   "assistant_session",
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
