package comment_test

import (
	"context"
	"testing"

	commentapp "quwoquan_service/services/content-service/internal/content/comment/application"
	commentmodel "quwoquan_service/services/content-service/internal/content/comment/domain/model"
	commentports "quwoquan_service/services/content-service/internal/content/comment/domain/ports"
	reactiondomain "quwoquan_service/services/content-service/internal/content/content_reaction/domain/reaction"
)

func TestCommentHotScoreProjectorRecomputesParentAfterReplyModeration(t *testing.T) {
	t.Parallel()

	projection := &hotScoreProjectionFixture{
		replyCount:   2,
		likeCount:    3,
		dislikeCount: 1,
	}
	projector := commentapp.NewCommentHotScoreProjector(
		projection,
		projection,
		projection,
	)

	err := projector.Publish(context.Background(), commentports.OutboxEvent{
		EventType: "CommentModerated",
		Payload: []byte(
			`{"commentId":"reply-1","postId":"post-1","parentCommentId":"parent-1","action":"hide"}`,
		),
	})
	if err != nil {
		t.Fatalf("投影回复治理事实失败：%v", err)
	}
	if projection.writtenCommentID != "parent-1" {
		t.Fatalf("重算目标 = %q，期望 parent-1", projection.writtenCommentID)
	}
	// (3 - 1) + 2 * 2 = 6。
	if projection.writtenScore != 6 {
		t.Fatalf("重算 hotScore = %d，期望 6", projection.writtenScore)
	}
}

type hotScoreProjectionFixture struct {
	replyCount       int64
	likeCount        int64
	dislikeCount     int64
	writtenCommentID string
	writtenScore     int64
}

func (f *hotScoreProjectionFixture) ReadReplySummaries(
	_ context.Context,
	parentCommentIDs []string,
	_ int,
	_ []string,
) (map[string]commentmodel.ReplySummary, error) {
	result := make(map[string]commentmodel.ReplySummary, len(parentCommentIDs))
	for _, commentID := range parentCommentIDs {
		result[commentID] = commentmodel.ReplySummary{Count: f.replyCount}
	}
	return result, nil
}

func (f *hotScoreProjectionFixture) ReadCommentReactionCounts(
	_ context.Context,
	commentIDs []string,
) (map[string]reactiondomain.CommentReactionCounts, error) {
	result := make(
		map[string]reactiondomain.CommentReactionCounts,
		len(commentIDs),
	)
	for _, commentID := range commentIDs {
		result[commentID] = reactiondomain.CommentReactionCounts{
			LikeCount:    f.likeCount,
			DislikeCount: f.dislikeCount,
		}
	}
	return result, nil
}

func (f *hotScoreProjectionFixture) ReadCommentReactionValues(
	_ context.Context,
	_ reactiondomain.Actor,
	_ []string,
) (map[string]reactiondomain.Value, error) {
	return map[string]reactiondomain.Value{}, nil
}

func (f *hotScoreProjectionFixture) ReadAuthorLikedFlags(
	_ context.Context,
	_ map[string][]string,
) (map[string]bool, error) {
	return map[string]bool{}, nil
}

func (f *hotScoreProjectionFixture) SetCommentHotScore(
	_ context.Context,
	commentID string,
	score int64,
) (bool, error) {
	f.writtenCommentID = commentID
	f.writtenScore = score
	return true, nil
}
