// spec_ref: specs/feature-tree/user-identity-profile-relationship/profile-homepage-redesign/career-interest-profile-editor/spec.md#gwt-002
package api_integration

import (
	"context"
	"testing"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"

	runtimemessaging "quwoquan_service/runtime/messaging"
	recinfra "quwoquan_service/services/content-service/internal/content/post/infrastructure/recommendation"
)

func TestTagFeedbackConsumerProjectsExplicitPreferenceExactlyOnce(t *testing.T) {
	ctx := context.Background()
	redis := requireTestRouter(t).Scene("general")
	if err := redis.Del(
		ctx,
		recinfra.TagFeedbackStream,
		recinfra.TagFeedbackDLQ,
	); err != nil {
		t.Fatalf("clear tag feedback streams: %v", err)
	}
	for _, collection := range []string{
		"rm_tag_feedback_fact_inbox",
		"rm_recommend_feature",
	} {
		if _, err := mongoDB.Collection(collection).DeleteMany(ctx, bson.M{
			"userId": "persona-tag-feedback",
		}); err != nil {
			t.Fatalf("clear %s: %v", collection, err)
		}
	}
	if _, err := mongoDB.Collection("rm_tag_feedback_fact_inbox").DeleteMany(ctx, bson.M{
		"actorId": "persona-tag-feedback",
	}); err != nil {
		t.Fatalf("clear tag feedback inbox: %v", err)
	}

	transport, err := runtimemessaging.NewRedisMessageTransport(redis, redis)
	if err != nil {
		t.Fatalf("build test message transport: %v", err)
	}
	projector, err := recinfra.NewTagFeedbackFeatureProjector(mongoDB, nil)
	if err != nil {
		t.Fatalf("build tag feedback projector: %v", err)
	}
	if err := projector.EnsureIndexes(ctx); err != nil {
		t.Fatalf("ensure tag feedback inbox indexes: %v", err)
	}
	consumer, err := recinfra.NewTagFeedbackConsumer(
		transport,
		projector,
		"api-integration-tag-feedback",
		nil,
	)
	if err != nil {
		t.Fatalf("build tag feedback consumer: %v", err)
	}

	recordedAt := time.Now().UTC().Truncate(time.Millisecond)
	click := tagFeedbackDeliveryFields(
		"tag-feedback-click",
		"persona-tag-feedback",
		"Topic/旅行",
		"click",
		recordedAt,
	)
	if _, err := transport.AppendDurable(ctx, runtimemessaging.DurableMessage{
		Stream: recinfra.TagFeedbackStream,
		Fields: click,
	}); err != nil {
		t.Fatalf("append click feedback: %v", err)
	}
	if processed, err := consumer.ProcessOnce(ctx); err != nil || processed != 1 {
		t.Fatalf("consume click processed=%d err=%v", processed, err)
	}
	assertExplicitTagAffinity(t, ctx, "Topic/旅行", true)
	vector, err := recinfra.NewFeatureStore(mongoDB).GetFeatures(
		ctx,
		"persona-tag-feedback",
	)
	if err != nil || vector == nil ||
		vector.TagAffinities["Topic/旅行"] != 1.0 {
		t.Fatalf("explicit tag affinity did not reach scoring vector: %+v err=%v", vector, err)
	}

	// The source stream can redeliver a committed event under a new Stream ID.
	// The durable eventId receipt must turn that retry into a no-op.
	if _, err := transport.AppendDurable(ctx, runtimemessaging.DurableMessage{
		Stream: recinfra.TagFeedbackStream,
		Fields: click,
	}); err != nil {
		t.Fatalf("append replay click feedback: %v", err)
	}
	if processed, err := consumer.ProcessOnce(ctx); err != nil || processed != 1 {
		t.Fatalf("consume replay processed=%d err=%v", processed, err)
	}
	receipts, err := mongoDB.Collection("rm_tag_feedback_fact_inbox").CountDocuments(
		ctx,
		bson.M{"_id": "tag-feedback-click"},
	)
	if err != nil {
		t.Fatalf("count tag feedback receipts: %v", err)
	}
	if receipts != 1 {
		t.Fatalf("receipts=%d want=1", receipts)
	}

	if _, err := transport.AppendDurable(ctx, runtimemessaging.DurableMessage{
		Stream: recinfra.TagFeedbackStream,
		Fields: tagFeedbackDeliveryFields(
			"tag-feedback-ignore",
			"persona-tag-feedback",
			"Topic/旅行",
			"ignore",
			recordedAt.Add(time.Second),
		),
	}); err != nil {
		t.Fatalf("append ignore feedback: %v", err)
	}
	if processed, err := consumer.ProcessOnce(ctx); err != nil || processed != 1 {
		t.Fatalf("consume ignore processed=%d err=%v", processed, err)
	}
	assertExplicitTagAffinity(t, ctx, "Topic/旅行", false)

	pending, err := redis.XPendingCount(
		ctx,
		recinfra.TagFeedbackStream,
		recinfra.TagFeedbackConsumerGroup,
	)
	if err != nil || pending != 0 {
		t.Fatalf("pending=%d want=0 err=%v", pending, err)
	}
}

func TestTagFeedbackConsumerDeadLettersMalformedEnvelope(t *testing.T) {
	ctx := context.Background()
	redis := requireTestRouter(t).Scene("general")
	if err := redis.Del(
		ctx,
		recinfra.TagFeedbackStream,
		recinfra.TagFeedbackDLQ,
	); err != nil {
		t.Fatalf("clear tag feedback streams: %v", err)
	}
	transport, err := runtimemessaging.NewRedisMessageTransport(redis, redis)
	if err != nil {
		t.Fatalf("build test message transport: %v", err)
	}
	projector, err := recinfra.NewTagFeedbackFeatureProjector(mongoDB, nil)
	if err != nil {
		t.Fatalf("build tag feedback projector: %v", err)
	}
	consumer, err := recinfra.NewTagFeedbackConsumer(
		transport,
		projector,
		"api-integration-tag-feedback-malformed",
		nil,
	)
	if err != nil {
		t.Fatalf("build tag feedback consumer: %v", err)
	}
	if _, err := transport.AppendDurable(ctx, runtimemessaging.DurableMessage{
		Stream: recinfra.TagFeedbackStream,
		Fields: []runtimemessaging.DurableField{
			{Name: "eventName", Value: "TagFeedbackRecorded"},
			{Name: "eventId", Value: "sensitive-event-id"},
		},
	}); err != nil {
		t.Fatalf("append malformed feedback: %v", err)
	}
	if processed, err := consumer.ProcessOnce(ctx); err != nil || processed != 1 {
		t.Fatalf("consume malformed processed=%d err=%v", processed, err)
	}
	if err := transport.EnsureDurableConsumerGroup(
		ctx,
		recinfra.TagFeedbackDLQ,
		"api-integration-tag-feedback-dlq",
		"0",
	); err != nil {
		t.Fatalf("ensure tag feedback DLQ consumer group: %v", err)
	}
	deliveries, err := transport.ReadDurable(ctx, runtimemessaging.StreamReadRequest{
		Stream:   recinfra.TagFeedbackDLQ,
		Group:    "api-integration-tag-feedback-dlq",
		Consumer: "assert",
		Count:    1,
		Block:    time.Second,
	})
	if err != nil {
		t.Fatalf("read tag feedback DLQ: %v", err)
	}
	if len(deliveries) != 1 ||
		containsDurableField(deliveries[0].Fields, "actorId") ||
		containsDurableField(deliveries[0].Fields, "tagRef") {
		t.Fatalf("unexpected tag feedback DLQ delivery: %+v", deliveries)
	}
}

func tagFeedbackDeliveryFields(
	eventID string,
	actorID string,
	tagRef string,
	action string,
	recordedAt time.Time,
) []runtimemessaging.DurableField {
	return []runtimemessaging.DurableField{
		{Name: "eventName", Value: "TagFeedbackRecorded"},
		{Name: "eventId", Value: eventID},
		{Name: "id", Value: eventID},
		{Name: "actorId", Value: actorID},
		{Name: "actorKind", Value: "persona"},
		{Name: "tagRef", Value: tagRef},
		{Name: "action", Value: action},
		{Name: "recordedAt", Value: recordedAt.Format(time.RFC3339Nano)},
	}
}

func assertExplicitTagAffinity(
	t *testing.T,
	ctx context.Context,
	tagRef string,
	wantPresent bool,
) {
	t.Helper()
	var feature struct {
		UserFeatures struct {
			ExplicitTagAffinities map[string]float64 `bson:"explicitTagAffinities"`
		} `bson:"userFeatures"`
	}
	if err := mongoDB.Collection("rm_recommend_feature").FindOne(
		ctx,
		bson.M{"userId": "persona-tag-feedback"},
	).Decode(&feature); err != nil {
		t.Fatalf("read recommendation feature: %v", err)
	}
	value, present := feature.UserFeatures.ExplicitTagAffinities[tagRef]
	if present != wantPresent || (wantPresent && value != 1.0) {
		t.Fatalf(
			"explicitTagAffinities[%q]=%v present=%v wantPresent=%v",
			tagRef,
			value,
			present,
			wantPresent,
		)
	}
}

func containsDurableField(
	fields []runtimemessaging.DurableField,
	name string,
) bool {
	for _, field := range fields {
		if field.Name == name {
			return true
		}
	}
	return false
}
