package post

import (
	"context"
	"testing"

	"quwoquan_service/services/content-service/internal/application/commandmeta"
	"quwoquan_service/services/content-service/internal/testsupport"
)

func TestPostLifecycleCommandsRequireAuthorPersona(t *testing.T) {
	t.Parallel()

	service := NewPostService(BindDataPorts(testsupport.NewPostStore(nil)))
	created, err := service.CreatePost(
		commandmeta.WithIdempotencyKey(context.Background(), "post-owner-create"),
		map[string]any{
			"contentType": "micro",
			"authorId":    "persona-owner",
			"body":        "owner-only draft",
		},
	)
	if err != nil {
		t.Fatalf("CreatePost() error = %v", err)
	}

	_, err = service.UpdatePost(
		commandmeta.WithIdempotencyKey(context.Background(), "post-owner-update"),
		created.ID,
		"persona-outsider",
		map[string]any{"body": "attempted takeover"},
	)
	if err == nil {
		t.Fatal("UpdatePost() must reject a non-owner persona")
	}
}
