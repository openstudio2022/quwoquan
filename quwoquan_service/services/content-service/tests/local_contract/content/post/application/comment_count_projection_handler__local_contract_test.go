// spec_ref: specs/feature-tree/discovery-content/publish-comment-reaction/comment-thread/spec.md#gwt-015
package post_test

import (
	"context"
	"testing"

	postapp "quwoquan_service/services/content-service/internal/content/post/application"
)

func TestCommentCountProjectionHandlerConvergesAfterPostTombstone(t *testing.T) {
	t.Parallel()

	fixture := &commentCountProjectionFixture{authoritativeCount: 0}
	handler := postapp.NewCommentCountProjectionHandler(fixture, fixture)
	if err := handler.Apply(context.Background(), postapp.CommentCountProjection{
		PostID: "post-1",
	}); err != nil {
		t.Fatalf("apply Comment count projection: %v", err)
	}
	if fixture.readPostID != "post-1" {
		t.Fatalf("authoritative count post=%q, want post-1", fixture.readPostID)
	}
	if fixture.writtenPostID != "post-1" || fixture.writtenCount != 0 {
		t.Fatalf(
			"projection write=%q/%d, want post-1/0",
			fixture.writtenPostID,
			fixture.writtenCount,
		)
	}
}

type commentCountProjectionFixture struct {
	authoritativeCount int64
	readPostID         string
	writtenPostID      string
	writtenCount       int64
}

func (f *commentCountProjectionFixture) CountByPost(
	_ context.Context,
	postID string,
) (int64, error) {
	f.readPostID = postID
	return f.authoritativeCount, nil
}

func (f *commentCountProjectionFixture) SetCommentCount(
	_ context.Context,
	postID string,
	count int64,
) (bool, error) {
	f.writtenPostID = postID
	f.writtenCount = count
	return true, nil
}
