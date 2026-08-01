package post_test

import (
	"context"
	"encoding/json"
	. "quwoquan_service/services/content-service/internal/content/post/application"
	"testing"

	postmodel "quwoquan_service/services/content-service/generated/content/post/contract/model"
	"quwoquan_service/services/content-service/internal/content/post/application/commandmeta"
	"quwoquan_service/services/content-service/internal/content/post/infrastructure/testsupport"
)

func TestPostLifecycleCommandsRequireAuthorPersona(t *testing.T) {
	t.Parallel()

	service := NewPostService(
		BindDataPorts(testsupport.NewPostStore(nil)),
		WithPublicationAdmission(
			testsupport.AllowPublicationRateGate{},
			testsupport.FixedPublicationSafetyGate{},
		),
	)
	receipt, err := service.SubmitPostPublication(
		commandmeta.WithIdempotencyKey(context.Background(), "post-owner-publish"),
		SubmitPostPublicationCommand{
			PublishIntentID: "post-owner-publish",
			LocalDraftID:    "post-owner-draft",
			AuthorID:        "persona-owner",
			Content: postmodel.Post{
				ContentType: "micro",
				Body:        "owner-only publication",
			},
		},
	)
	if err != nil {
		t.Fatalf("SubmitPostPublication() error = %v", err)
	}

	_, err = service.UpdatePostSettings(
		commandmeta.WithIdempotencyKey(context.Background(), "post-owner-update"),
		receipt.PostID,
		"persona-outsider",
		map[string]any{"visibility": "private"},
	)
	if err == nil {
		t.Fatal("UpdatePostSettings() must reject a non-owner persona")
	}
}

func TestPostSettingsUpdatedCarriesCanonicalProjectionSnapshot(t *testing.T) {
	t.Parallel()

	store := testsupport.NewPostStore(nil)
	service := NewPostService(
		BindDataPorts(store),
		WithPublicationAdmission(
			testsupport.AllowPublicationRateGate{},
			testsupport.FixedPublicationSafetyGate{},
		),
	)
	receipt, err := service.SubmitPostPublication(
		commandmeta.WithIdempotencyKey(context.Background(), "post-settings-snapshot-publish"),
		SubmitPostPublicationCommand{
			PublishIntentID: "post-settings-snapshot-publish",
			LocalDraftID:    "post-settings-snapshot-draft",
			AuthorID:        "persona-owner",
			Content: postmodel.Post{
				ContentType: "micro",
				Body:        "settings must not erase projection fields",
				TagRefs:     []string{"Topic/旅行"},
			},
		},
	)
	if err != nil {
		t.Fatalf("SubmitPostPublication() error = %v", err)
	}

	_, err = service.UpdatePostSettings(
		commandmeta.WithIdempotencyKey(context.Background(), "post-settings-snapshot-update"),
		receipt.PostID,
		"persona-owner",
		map[string]any{"assistantUsePolicy": "excluded"},
	)
	if err != nil {
		t.Fatalf("UpdatePostSettings() error = %v", err)
	}
	events := store.OutboxEvents()
	if len(events) != 2 || events[1].EventType != "PostSettingsUpdated" {
		t.Fatalf("outbox events = %+v, want publication then PostSettingsUpdated", events)
	}
	var payload map[string]any
	if err := json.Unmarshal(events[1].Payload, &payload); err != nil {
		t.Fatalf("decode PostSettingsUpdated payload: %v", err)
	}
	for _, field := range []string{
		"postId", "authorId", "contentType", "contentIdentity", "status",
		"visibility", "moderationStatus", "publishedAt", "updatedAt",
		"tagRefs", "entityRefs", "semanticMentions",
	} {
		if _, exists := payload[field]; !exists {
			t.Fatalf("PostSettingsUpdated payload missing canonical field %q: %+v", field, payload)
		}
	}
	tagRefs, ok := payload["tagRefs"].([]any)
	if !ok || len(tagRefs) != 1 || tagRefs[0] != "Topic/旅行" {
		t.Fatalf("PostSettingsUpdated tagRefs = %#v, want preserved canonical tags", payload["tagRefs"])
	}
}
