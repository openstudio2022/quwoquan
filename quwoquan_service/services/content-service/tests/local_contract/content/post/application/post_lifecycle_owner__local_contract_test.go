package post_test

import (
	"context"
	. "quwoquan_service/services/content-service/internal/content/post/application"
	"testing"

	"quwoquan_service/services/content-service/internal/content/post/application/commandmeta"
	postmodel "quwoquan_service/services/content-service/internal/content/post/domain/model"
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
