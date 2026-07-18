package post

import (
	"context"
	"testing"

	"quwoquan_service/services/content-service/internal/application/commandmeta"
	postmodel "quwoquan_service/services/content-service/internal/domain/post/model"
	"quwoquan_service/services/content-service/internal/testsupport"
)

func TestPostLifecycleCommandsRequireAuthorPersona(t *testing.T) {
	t.Parallel()

	service := NewPostService(BindDataPorts(testsupport.NewPostStore(nil)))
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
