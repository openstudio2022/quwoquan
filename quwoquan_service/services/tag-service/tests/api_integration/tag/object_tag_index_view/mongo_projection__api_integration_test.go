// spec_ref: specs/feature-tree/user-identity-profile-relationship/profile-homepage-redesign/spec.md#sit-006
// readiness_case: project-object-tag-index-api
package api_integration

import (
	"context"
	"encoding/json"
	"os"
	"testing"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"

	"quwoquan_service/internal/platform/testinfra"
	runtimemessaging "quwoquan_service/runtime/messaging"
	projectionstream "quwoquan_service/services/tag-service/internal/tag/object_tag_index_view/adapters/inbound/stream"
	indexports "quwoquan_service/services/tag-service/internal/tag/object_tag_index_view/domain/ports"
	indexpersistence "quwoquan_service/services/tag-service/internal/tag/object_tag_index_view/infrastructure/persistence"
)

var (
	indexMongoRuntime *testinfra.RealMongo
	indexMongoDB      *mongo.Database
)

func TestMain(m *testing.M) {
	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Minute)
	runtime, err := testinfra.StartRealMongo(ctx, testinfra.UniqueDatabaseName("object_tag_index_api_integration"))
	cancel()
	if err != nil {
		panic("ObjectTagIndexView api_integration requires real MongoDB: " + err.Error())
	}
	indexMongoRuntime = runtime
	indexMongoDB = runtime.Database
	code := m.Run()
	shutdownCtx, shutdownCancel := context.WithTimeout(context.Background(), 30*time.Second)
	_ = indexMongoRuntime.Close(shutdownCtx)
	shutdownCancel()
	os.Exit(code)
}

func TestObjectTagIndexProjectionConvergesOnHighestSourceVersion(t *testing.T) {
	collection := indexMongoDB.Collection("object_tag_index")
	if _, err := collection.DeleteMany(context.Background(), bson.M{}); err != nil {
		t.Fatal(err)
	}
	store := indexpersistence.NewMongoObjectTagIndexStore(collection)
	if err := store.EnsureIndexes(context.Background()); err != nil {
		t.Fatal(err)
	}
	now := time.Date(2026, 8, 2, 10, 0, 0, 0, time.UTC)
	newer := indexports.UserProfileTagProjection{
		EventID: "profile-tags-newer", UserID: "user-001",
		TagRefs:           []string{"Audience/用户/兴趣偏好/科技/AI"},
		TaxonomyReleaseID: "taxonomy-release-2", ProfileVersion: 2, OccurredAt: now,
	}
	applied, err := store.ApplyUserProfileTagProjection(context.Background(), newer)
	if err != nil || !applied {
		t.Fatalf("apply newer projection: applied=%v err=%v", applied, err)
	}
	stale := newer
	stale.EventID = "profile-tags-stale"
	stale.TagRefs = []string{"Audience/用户/兴趣偏好/生活/咖啡"}
	stale.TaxonomyReleaseID = "taxonomy-release-1"
	stale.ProfileVersion = 1
	stale.OccurredAt = now.Add(-time.Minute)
	applied, err = store.ApplyUserProfileTagProjection(context.Background(), stale)
	if err != nil || applied {
		t.Fatalf("stale projection applied=%v err=%v", applied, err)
	}
	index, err := store.FindByObject(context.Background(), "user-001", "user")
	if err != nil || index == nil || len(index.TagRefs) != 1 || index.TagRefs[0] != newer.TagRefs[0] {
		t.Fatalf("canonical index=%+v err=%v", index, err)
	}
}

func TestObjectTagIndexConsumerAppliesAcknowledgesAndPersistsWithMongo(t *testing.T) {
	collection := indexMongoDB.Collection("object_tag_index")
	if _, err := collection.DeleteMany(context.Background(), bson.M{}); err != nil {
		t.Fatal(err)
	}
	store := indexpersistence.NewMongoObjectTagIndexStore(collection)
	if err := store.EnsureIndexes(context.Background()); err != nil {
		t.Fatal(err)
	}
	payload, err := json.Marshal(map[string]any{
		"userId":            "user-consumer-001",
		"tagRefs":           []string{"Audience/用户/兴趣偏好/科技/AI"},
		"taxonomyReleaseId": "taxonomy-release-consumer",
		"profileVersion":    7,
		"occurredAt":        "2026-08-06T10:00:00Z",
	})
	if err != nil {
		t.Fatal(err)
	}
	transport := &mongoConsumerTransport{fresh: []runtimemessaging.StreamDelivery{{
		ID: "consumer-100-1",
		Fields: []runtimemessaging.DurableField{
			{Name: "eventId", Value: "profile-tags-consumer-1"},
			{Name: "eventName", Value: "UserProfileTagsChanged"},
			{Name: "accountId", Value: "user-consumer-001"},
			{Name: "accountVersion", Value: "7"},
			{Name: "payload", Value: string(payload)},
			{Name: "occurredAt", Value: "2026-08-06T10:00:00Z"},
		},
	}}}
	consumer, err := projectionstream.NewUserProfileTagConsumer(
		transport,
		store,
		"object-tag-index-api-integration",
		nil,
	)
	if err != nil {
		t.Fatalf("construct owning consumer: %v", err)
	}
	processed, err := consumer.ProcessOnce(context.Background())
	if err != nil {
		t.Fatalf("process durable profile-tag event: %v", err)
	}
	if processed != 1 || len(transport.acked) != 1 || transport.acked[0] != "consumer-100-1" {
		t.Fatalf("processed=%d acked=%v", processed, transport.acked)
	}
	index, err := store.FindByObject(context.Background(), "user-consumer-001", "user")
	if err != nil || index == nil || index.SourceAggregateVersion != 7 ||
		len(index.TagRefs) != 1 || index.TagRefs[0] != "Audience/用户/兴趣偏好/科技/AI" {
		t.Fatalf("persisted consumer projection=%+v err=%v", index, err)
	}
}

type mongoConsumerTransport struct {
	fresh []runtimemessaging.StreamDelivery
	acked []string
}

func (*mongoConsumerTransport) PublishEphemeral(context.Context, runtimemessaging.EphemeralMessage) error {
	return nil
}

func (*mongoConsumerTransport) SubscribeEphemeral(context.Context, ...string) (runtimemessaging.EphemeralSubscription, error) {
	return nil, nil
}

func (*mongoConsumerTransport) AppendDurable(context.Context, runtimemessaging.DurableMessage) (string, error) {
	return "1-0", nil
}

func (*mongoConsumerTransport) EnsureDurableConsumerGroup(context.Context, string, string, string) error {
	return nil
}

func (transport *mongoConsumerTransport) ReadDurable(context.Context, runtimemessaging.StreamReadRequest) ([]runtimemessaging.StreamDelivery, error) {
	fresh := transport.fresh
	transport.fresh = nil
	return fresh, nil
}

func (transport *mongoConsumerTransport) AckDurable(_ context.Context, _ string, _ string, ids ...string) error {
	transport.acked = append(transport.acked, ids...)
	return nil
}

func (*mongoConsumerTransport) ReclaimDurable(context.Context, string, string, string, time.Duration, string, int64) ([]runtimemessaging.StreamDelivery, string, error) {
	return nil, "0-0", nil
}

func (*mongoConsumerTransport) PublishDeadLetter(context.Context, runtimemessaging.DeadLetterMessage) (string, error) {
	return "2-0", nil
}

func (*mongoConsumerTransport) ClaimDurableDelivery(context.Context, string, string, time.Duration) (bool, error) {
	return true, nil
}

func (*mongoConsumerTransport) ReleaseDurableDelivery(context.Context, string) error {
	return nil
}

func (*mongoConsumerTransport) SetDurableRetention(context.Context, string, time.Duration) error {
	return nil
}
