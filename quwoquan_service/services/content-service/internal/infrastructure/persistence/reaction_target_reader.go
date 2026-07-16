package persistence

import (
	"context"
	"fmt"

	reactionapp "quwoquan_service/services/content-service/internal/application/reaction"
	commentmodel "quwoquan_service/services/content-service/internal/domain/comment/model"
	reactiondomain "quwoquan_service/services/content-service/internal/domain/reaction"
)

type postReactionTargetReader interface {
	PostExists(ctx context.Context, postID string) (bool, error)
}

type commentReactionTargetReader interface {
	FindReplyTarget(
		ctx context.Context,
		commentID string,
	) (commentmodel.ReplyTarget, bool, error)
}

// ReactionTargetReader 是 ContentReaction 到 Post/Comment 的窄防腐读端口。
// 它只回答目标是否可互动，不返回或拼装任何目标聚合。
type ReactionTargetReader struct {
	posts    postReactionTargetReader
	comments commentReactionTargetReader
}

func NewReactionTargetReader(
	posts postReactionTargetReader,
	comments commentReactionTargetReader,
) *ReactionTargetReader {
	if posts == nil || comments == nil {
		panic("ReactionTargetReader requires Post and Comment readers")
	}
	return &ReactionTargetReader{posts: posts, comments: comments}
}

func (r *ReactionTargetReader) ReactionTargetExists(
	ctx context.Context,
	target reactiondomain.Target,
) (bool, error) {
	if err := target.Validate(); err != nil {
		return false, err
	}
	switch target.Kind {
	case reactiondomain.TargetKindPost:
		return r.posts.PostExists(ctx, target.ID)
	case reactiondomain.TargetKindComment:
		comment, found, err := r.comments.FindReplyTarget(ctx, target.ID)
		return found && comment.Status == commentmodel.StatusActive, err
	default:
		return false, fmt.Errorf("unsupported ContentReaction target kind %q", target.Kind)
	}
}

var _ reactionapp.ReactionTargetReader = (*ReactionTargetReader)(nil)
