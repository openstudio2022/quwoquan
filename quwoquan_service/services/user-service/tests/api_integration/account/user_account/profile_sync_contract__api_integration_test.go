package api_integration

import (
	"context"
	"encoding/json"
	"net/http"
	"testing"
	"time"
)

func TestUpdateProfile_AvatarVersionAndSyncPatch(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })
	personaID := createProfileUpdateFixture(
		t,
		"user_avatar_sync",
		"avatar_sync",
	)

	rec := doRequest(
		t,
		http.MethodPatch,
		"/user/profile",
		`{"avatarAssetId":"ua_user_avatar_sync","avatarUrl":"https://cdn.example.com/u1.png?v=2"}`,
		authHeadersForPersona("user_avatar_sync", personaID),
	)
	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d: %s", rec.Code, rec.Body.String())
	}
	profile := parseJSON(t, rec)
	if profile["avatarAssetId"] != "ua_user_avatar_sync" {
		t.Fatalf("expected avatarAssetId to be set, got %v", profile["avatarAssetId"])
	}
	avatarVersion, _ := profile["avatarVersion"].(float64)
	if int(avatarVersion) != 1 {
		t.Fatalf("expected avatarVersion=1 got %v", profile["avatarVersion"])
	}

	syncRec := doRequest(
		t,
		http.MethodPost,
		"/user/sync",
		`{"afterSeq":0,"limit":10}`,
		authHeaders("user_avatar_sync"),
	)
	if syncRec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d: %s", syncRec.Code, syncRec.Body.String())
	}
	result := parseJSON(t, syncRec)
	patches, ok := result["patches"].([]any)
	if !ok || len(patches) != 1 {
		t.Fatalf("expected exactly 1 patch, got %v", result["patches"])
	}
	patch, _ := patches[0].(map[string]any)
	if patch["kind"] != "user_avatar_updated" {
		t.Fatalf("expected user_avatar_updated patch, got %v", patch["kind"])
	}
	payload, _ := patch["userAvatarUpdated"].(map[string]any)
	if payload["userId"] != "user_avatar_sync" ||
		payload["avatarUrl"] != "https://cdn.example.com/u1.png?v=1" ||
		int(payload["avatarVersion"].(float64)) != 1 {
		t.Fatalf("unexpected typed user avatar patch payload: %v", payload)
	}
	if _, found := patch["type"]; found {
		t.Fatalf("retired patch type must not be exposed: %v", patch)
	}
	if _, found := patch["payload"]; found {
		t.Fatalf("generic patch payload must not be exposed: %v", patch)
	}
}

func TestPullUserSyncRejectsUnknownOrInvalidCursorBody(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })
	createProfileUpdateFixture(t, "user_sync_invalid", "sync_invalid")
	for _, body := range []string{
		`{"afterSeq":0,"limit":10,"retiredCursor":"1"}`,
		`{"afterSeq":-1,"limit":10}`,
		`{"afterSeq":0,"limit":501}`,
	} {
		rec := doRequest(
			t,
			http.MethodPost,
			"/user/sync",
			body,
			authHeaders("user_sync_invalid"),
		)
		if rec.Code != http.StatusBadRequest {
			t.Fatalf(
				"invalid sync request must return 400, got %d: %s",
				rec.Code,
				rec.Body.String(),
			)
		}
	}
}

func TestUpdateProfile_PublishesUserAvatarUpdatedEvent(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })
	personaID := createProfileUpdateFixture(
		t,
		"user_avatar_event",
		"avatar_event",
	)

	ctx, cancel := context.WithTimeout(context.Background(), 3*time.Second)
	defer cancel()
	sub, err := redisClient.Subscribe(ctx, "event:user-profile")
	if err != nil {
		t.Fatalf("subscribe event:user-profile: %v", err)
	}
	defer sub.Close()
	ch := sub.Channel()
	time.Sleep(50 * time.Millisecond)

	rec := doRequest(
		t,
		http.MethodPatch,
		"/user/profile",
		`{"avatarAssetId":"ua_user_avatar_event","avatarUrl":"https://cdn.example.com/u2.png?v=3"}`,
		authHeadersForPersona("user_avatar_event", personaID),
	)
	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d: %s", rec.Code, rec.Body.String())
	}

	for {
		select {
		case msg := <-ch:
			var event map[string]any
			if err := json.Unmarshal([]byte(msg.Payload), &event); err != nil {
				t.Fatalf("decode event payload: %v", err)
			}
			if event["type"] != "UserAvatarUpdated" {
				continue
			}
			payload, _ := event["payload"].(map[string]any)
			if payload["avatarAssetId"] != "ua_user_avatar_event" {
				t.Fatalf("expected avatarAssetId in event payload, got %v", payload["avatarAssetId"])
			}
			if payload["userId"] != "user_avatar_event" {
				t.Fatalf("expected userId in event payload, got %v", payload["userId"])
			}
			return
		case <-ctx.Done():
			t.Fatal("expected UserAvatarUpdated event to be published")
		}
	}
}
