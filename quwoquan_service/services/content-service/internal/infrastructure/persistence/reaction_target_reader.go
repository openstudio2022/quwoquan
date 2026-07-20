package persistence

import (
	"context"
	"fmt"

	reactionapp "quwoquan_service/services/content-service/internal/application/reaction"
	commentmodel "quwoquan_service/services/content-service/internal/domain/comment/model"
	reactiondomain "quwoquan_service/services/content-service/internal/domain/reaction"
)

type postReactionTargetReader interface {
	FindPostOwnership(
		ctx context.Context,
		postID string,
	) (commentmodel.PostOwnership, bool, error)
}

type commentReactionTargetReader interface {
	FindReplyTarget(
		ctx context.Context,
		commentID string,
	) (commentmodel.ReplyTarget, bool, error)
}

// ReactionTargetReader 是 ContentReaction 到 Post/Comment 的窄防腐读端口。
// 它只回答目标是否可互动以及作者是谁（通知接收者），不返回或拼装任何目标聚合。
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

func (r *ReactionTargetReader) FindReactionTarget(
	ctx context.Context,
	target reactiondomain.Target,
) (reactionapp.ReactionTargetSlice, error) {
	if err := target.Validate(); err != nil {
		return reactionapp.ReactionTargetSlice{}, err
	}
	switch target.Kind {
	case reactiondomain.TargetKindPost:
		ownership, found, err := r.posts.FindPostOwnership(ctx, target.ID)
		if err != nil {
			return reactionapp.ReactionTargetSlice{}, err
		}
		return reactionapp.ReactionTargetSlice{
			Exists:   found && ownership.Active,
			AuthorID: ownership.AuthorID,
		}, nil
	case reactiondomain.TargetKindComment:
		comment, found, err := r.comments.FindReplyTarget(ctx, target.ID)
		if err != nil {
			return reactionapp.ReactionTargetSlice{}, err
		}
		return reactionapp.ReactionTargetSlice{
			Exists:   found && comment.Status == commentmodel.StatusActive,
			AuthorID: comment.AuthorID,
		}, nil
	default:
		return reactionapp.ReactionTargetSlice{},
			fmt.Errorf("unsupported ContentReaction target kind %q", target.Kind)
	}
}

var _ reactionapp.ReactionTargetReader = (*ReactionTargetReader)(nil)
