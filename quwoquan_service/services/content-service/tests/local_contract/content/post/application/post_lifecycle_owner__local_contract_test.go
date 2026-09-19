// readiness_case: update-post-settings-local
// spec_ref: specs/feature-tree/discovery-content/publish-comment-reaction/post-create-update/spec.md#gwt-009
// 覆盖作者权限、设置持久化及既有内容投影保持；其余端云子句仍由对应 OPEN 追踪。
package post_test

import (
	"context"
	"encoding/json"
	. "quwoquan_service/services/content-service/internal/content/post/application"
	"testing"
	"time"

	"quwoquan_service/runtime/commandmeta"
	postmodel "quwoquan_service/services/content-service/generated/content/post/contract/model"
	"quwoquan_service/services/content-service/internal/content/post/infrastructure/testsupport"
	semanticfixture "quwoquan_service/services/content-service/tests/support/semanticfixture"
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
				ContentType:      "article",
				ArticleMarkdown:  "owner-only publication",
				MarkdownDialect:  "qwq-rich-md",
				SemanticDocument: semanticfixture.Envelope(t),
				Body:             "owner-only publication",
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
				ContentType:       "article",
				ArticleMarkdown:   "settings must not erase projection fields",
				MarkdownDialect:   "qwq-rich-md",
				SemanticDocument:  semanticfixture.Envelope(t),
				Body:              "settings must not erase projection fields",
				TagRefs:           []string{"Topic/旅行"},
				PrimaryHomepageId: "homepage-001",
				PrimaryHomepageSnapshot: postmodel.PostHomepageSnapshot{
					CanonicalEntityId: "entity-001",
					Title:             "公开对象页",
					Subtitle:          "公开副标题",
					CoverUrl:          "https://cdn.example/homepage-001.jpg",
				},
				VisitedAt: time.Date(2026, 8, 1, 12, 0, 0, 0, time.UTC),
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
		map[string]any{"assistantUsePolicy": "exclude", "visibility": "private"},
	)
	if err != nil {
		t.Fatalf("UpdatePostSettings() error = %v", err)
	}
	persisted, exists := store.FindByID(context.Background(), receipt.PostID)
	if !exists || persisted.AssistantUsePolicy != "exclude" || persisted.Visibility != "private" {
		t.Fatalf("settings were not persisted: %+v", persisted)
	}
	if persisted.ContentType != "article" || persisted.Body != "settings must not erase projection fields" ||
		persisted.ArticleMarkdown != "settings must not erase projection fields" {
		t.Fatalf("settings changed immutable content: %+v", persisted)
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
		"postId", "authorId", "contentType", "status",
		"visibility", "moderationStatus", "publishedAt", "updatedAt",
		"tagRefs", "entityRefs", "semanticMentions", "primaryHomepageSnapshot", "visitedAt",
	} {
		if _, exists := payload[field]; !exists {
			t.Fatalf("PostSettingsUpdated payload missing canonical field %q: %+v", field, payload)
		}
	}
	if _, present := payload["contentIdentity"]; present {
		t.Fatalf("PostSettingsUpdated must omit retired contentIdentity: %+v", payload)
	}
	tagRefs, ok := payload["tagRefs"].([]any)
	if !ok || len(tagRefs) != 1 || tagRefs[0] != "Topic/旅行" {
		t.Fatalf("PostSettingsUpdated tagRefs = %#v, want preserved canonical tags", payload["tagRefs"])
	}
	homepageSnapshot, ok := payload["primaryHomepageSnapshot"].(map[string]any)
	if !ok || homepageSnapshot["canonicalEntityId"] != "entity-001" ||
		homepageSnapshot["title"] != "公开对象页" {
		t.Fatalf("PostSettingsUpdated primaryHomepageSnapshot = %#v", payload["primaryHomepageSnapshot"])
	}
}
