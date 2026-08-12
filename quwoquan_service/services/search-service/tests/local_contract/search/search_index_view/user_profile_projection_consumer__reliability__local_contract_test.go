// spec_ref: specs/feature-tree/global-search-experience/search-provider-routing-and-storage-topology/canonical-search-contract/spec.md#gwt-001.t7
// spec_ref: specs/feature-tree/global-search-experience/search-provider-routing-and-storage-topology/canonical-search-contract/spec.md#gwt-001.t8
package local_contract

import (
	"context"
	"encoding/json"
	"errors"
	"testing"
	"time"

	runtimemessaging "quwoquan_service/runtime/messaging"
	rtredis "quwoquan_service/runtime/redis"
	consumer "quwoquan_service/services/search-service/internal/search/search_index_view/adapters/inbound/mq"
	"quwoquan_service/services/search-service/internal/search/search_index_view/application"
)

type profileProjectionRecorder struct {
	err    error
	events []application.UserProfileSearchProjectionEvent
}

func (recorder *profileProjectionRecorder) Apply(
	_ context.Context,
	event application.UserProfileSearchProjectionEvent,
) (application.UserProfileSearchProjectionResult, error) {
	recorder.events = append(recorder.events, event)
	return application.UserProfileSearchProjectionResult{}, recorder.err
}

func TestUserProfileProjectionConsumerRetainsCheckpointUntilSearchApplySucceeds(t *testing.T) {
	redis := rtredis.NewMemoryClient()
	transport, err := runtimemessaging.NewRedisMessageTransport(redis, redis)
	if err != nil {
		t.Fatal(err)
	}
	projection := &profileProjectionRecorder{err: errors.New("provider unavailable")}
	runner, err := consumer.NewUserProfileSearchProjectionConsumer(
		transport, projection, "profile-projection-local", nil,
	)
	if err != nil {
		t.Fatal(err)
	}
	event := application.UserProfileSearchProjectionEvent{
		EventID: "ups_8", UserID: "user-8", ProfileVersion: 8,
		Operation: "upsert", Nickname: "雪山客", IdentityTags: []string{"travel"},
		UpdatedAt: time.Date(2026, 8, 12, 8, 0, 0, 0, time.UTC),
	}
	payload, _ := json.Marshal(event)
	messageID, err := transport.AppendDurable(t.Context(), runtimemessaging.DurableMessage{
		Stream: consumer.UserProfileSearchProjectionStream,
		Fields: []runtimemessaging.DurableField{
			{Name: "eventId", Value: event.EventID},
			{Name: "eventName", Value: "UserProfileSearchProjectionRequested"},
			{Name: "userId", Value: event.UserID},
			{Name: "profileVersion", Value: "8"},
			{Name: "payload", Value: string(payload)},
			{Name: "occurredAt", Value: event.UpdatedAt.Format(time.RFC3339Nano)},
		},
	})
	if err != nil {
		t.Fatal(err)
	}
	if processed, err := runner.ProcessOnce(t.Context()); processed != 0 || err == nil {
		t.Fatalf("provider failure must stay pending: processed=%d err=%v", processed, err)
	}
	pending, _, err := redis.XAutoClaim(
		t.Context(), consumer.UserProfileSearchProjectionStream,
		consumer.UserProfileSearchProjectionConsumerGroup, "inspector", 0, "0-0", 10,
	)
	if err != nil || len(pending) != 1 || pending[0].ID != messageID {
		t.Fatalf("failed projection checkpoint advanced: pending=%+v err=%v", pending, err)
	}

	projection.err = nil
	if processed, err := runner.ProcessOnce(t.Context()); processed != 1 || err != nil {
		t.Fatalf("projection replay did not converge: processed=%d err=%v", processed, err)
	}
	pending, _, err = redis.XAutoClaim(
		t.Context(), consumer.UserProfileSearchProjectionStream,
		consumer.UserProfileSearchProjectionConsumerGroup, "inspector", 0, "0-0", 10,
	)
	if err != nil || len(pending) != 0 {
		t.Fatalf("successful projection was not acknowledged: pending=%+v err=%v", pending, err)
	}
	if len(projection.events) != 2 || projection.events[0].EventID != projection.events[1].EventID {
		t.Fatalf("replay changed event identity: %+v", projection.events)
	}
}

func TestUserProfileProjectionOwnsUpdateAndDeleteDocumentMapping(t *testing.T) {
	updated := application.UserProfileSearchProjectionEvent{
		EventID: "ups_9", UserID: "user-9", ProfileVersion: 9,
		Operation: "upsert", Nickname: "旅行者", AvatarURL: "https://media/u9",
		IdentityTags: []string{"travel"}, FollowerCount: 2, PostCount: 3,
		UpdatedAt: time.Now().UTC(),
	}
	document := updated.Document()
	if document.ObjectID != "user-9" || document.Title != "旅行者" || document.Popularity != 5 {
		t.Fatalf("Search-owned update mapping drifted: %+v", document)
	}
	deleted := application.UserProfileSearchProjectionEvent{
		EventID: "ups_10", UserID: "user-9", ProfileVersion: 10,
		Operation: "delete", IdentityTags: []string{}, UpdatedAt: time.Now().UTC(),
	}
	if err := deleted.Validate(); err != nil {
		t.Fatal(err)
	}
	deleteDocument := deleted.Document()
	if deleteDocument.ObjectID != "user-9" || deleteDocument.Title != "" || len(deleteDocument.Fields) != 0 {
		t.Fatalf("Search-owned delete mapping retained profile data: %+v", deleteDocument)
	}
}
