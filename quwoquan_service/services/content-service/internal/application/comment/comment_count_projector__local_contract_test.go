package comment_test

import (
	"context"
	"testing"

	commentapp "quwoquan_service/services/content-service/internal/application/comment"
	commentports "quwoquan_service/services/content-service/internal/domain/comment/ports"
)

func TestCommentCountProjectorConvergesAfterPostTombstone(t *testing.T) {
	t.Parallel()

	fixture := &commentCountProjectionFixture{authoritativeCount: 0}
	projector := commentapp.NewCommentCountProjector(fixture, fixture)
	err := projector.Publish(context.Background(), commentports.OutboxEvent{
		EventType: "CommentsTombstoned",
		Payload:   []byte(`{"postId":"post-1","tombstonedCount":7}`),
	})
	if err != nil {
		t.Fatalf("投影批量 tombstone 计数失败：%v", err)
	}
	if fixture.readPostID != "post-1" {
		t.Fatalf("权威计数读取 post = %q，期望 post-1", fixture.readPostID)
	}
	if fixture.writtenPostID != "post-1" || fixture.writtenCount != 0 {
		t.Fatalf(
			"写入投影 = %q/%d，期望 post-1/0",
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
