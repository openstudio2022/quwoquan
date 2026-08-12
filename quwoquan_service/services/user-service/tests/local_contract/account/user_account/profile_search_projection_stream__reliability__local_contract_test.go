// spec_ref: specs/feature-tree/user-identity-profile-relationship/auth-profile-snapshot/profile-snapshot-versioning/spec.md#gwt-002
package local_contract

import (
	"context"
	"encoding/json"
	"testing"
	"time"

	runtimemessaging "quwoquan_service/runtime/messaging"
	rtredis "quwoquan_service/runtime/redis"
	userports "quwoquan_service/services/user-service/internal/account/user_account/domain/user/ports"
	"quwoquan_service/services/user-service/internal/account/user_account/infrastructure/profileprojection"
)

func TestProfileSearchPublisherAppendsSelfContainedDurableFact(t *testing.T) {
	redis := rtredis.NewMemoryClient()
	transport, err := runtimemessaging.NewRedisMessageTransport(redis, redis)
	if err != nil {
		t.Fatal(err)
	}
	publisher, err := profileprojection.NewStreamPublisher(transport)
	if err != nil {
		t.Fatal(err)
	}
	payload, err := json.Marshal(userports.UserProfileSearchProjectionPayload{
		EventID: "ups_profile_7", UserID: "user-7", ProfileVersion: 7,
		Operation: "upsert", Nickname: "旅行者", AvatarURL: "https://media.example/u7.png",
		Bio: "雪山", IdentityTags: []string{"travel"}, FollowerCount: 8, PostCount: 3,
		UpdatedAt: time.Date(2026, 8, 12, 7, 0, 0, 0, time.UTC),
	})
	if err != nil {
		t.Fatal(err)
	}
	event := userports.UserProfileSearchOutboxEvent{
		EventID: "ups_profile_7", UserID: "user-7", ProfileVersion: 7,
		EventType: "UserProfileUpdated", PayloadJSON: payload,
		OccurredAt: time.Date(2026, 8, 12, 7, 0, 0, 0, time.UTC),
	}
	if err := publisher.PublishUserProfileSearch(context.Background(), event); err != nil {
		t.Fatal(err)
	}
	records, err := transport.ReadDurableAfter(t.Context(), runtimemessaging.CursorReadRequest{
		Stream: profileprojection.UserProfileSearchProjectionStream, Cursor: "0-0", Count: 1,
	})
	if err != nil || len(records) != 1 {
		t.Fatalf("records=%+v err=%v", records, err)
	}
	fields := profileProjectionFieldMap(records[0].Fields)
	if fields["eventName"] != "UserProfileSearchProjectionRequested" ||
		fields["eventId"] != event.EventID || fields["profileVersion"] != "7" {
		t.Fatalf("durable projection envelope drifted: %+v", fields)
	}
	var published userports.UserProfileSearchProjectionPayload
	if err := json.Unmarshal([]byte(fields["payload"]), &published); err != nil {
		t.Fatal(err)
	}
	if published.Nickname != "旅行者" || len(published.IdentityTags) != 1 {
		t.Fatalf("durable projection is not self-contained: %+v", published)
	}
}

func TestProfileSearchPublisherRejectsCoordinatePayloadDrift(t *testing.T) {
	redis := rtredis.NewMemoryClient()
	transport, _ := runtimemessaging.NewRedisMessageTransport(redis, redis)
	publisher, _ := profileprojection.NewStreamPublisher(transport)
	payload, _ := json.Marshal(userports.UserProfileSearchProjectionPayload{
		EventID: "other", UserID: "user-7", ProfileVersion: 7,
		Operation: "delete", IdentityTags: []string{}, UpdatedAt: time.Now().UTC(),
	})
	err := publisher.PublishUserProfileSearch(t.Context(), userports.UserProfileSearchOutboxEvent{
		EventID: "expected", UserID: "user-7", ProfileVersion: 7,
		OccurredAt: time.Now().UTC(), PayloadJSON: payload,
	})
	if err == nil {
		t.Fatal("payload drift must fail before durable append")
	}
}

func profileProjectionFieldMap(fields []runtimemessaging.DurableField) map[string]string {
	result := make(map[string]string, len(fields))
	for _, field := range fields {
		result[field.Name] = field.Value
	}
	return result
}
