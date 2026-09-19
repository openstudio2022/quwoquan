package reaction

import (
	"context"
	"time"

	reactiondomain "quwoquan_service/services/content-service/internal/content/content_reaction/domain/reaction"
)

type LikePostCommand struct {
	PostID   string
	Actor    reactiondomain.Actor
	Evidence MutationEvidence
}

type UnlikePostCommand struct {
	PostID   string
	Actor    reactiondomain.Actor
	Evidence MutationEvidence
}

type ReactToCommentCommand struct {
	CommentID string
	Actor     reactiondomain.Actor
	Reaction  reactiondomain.Value
	Evidence  MutationEvidence
}

type GetContentReactionMutationBasisQuery struct{ Identity reactiondomain.Identity }
type ContentReactionMutationBasisSlice struct {
	TargetKind      string
	TargetID        string
	MutationBasis   string
	ExpectedVersion int64
}

type GetContentReactionStateQuery struct {
	PostID string
	Actor  reactiondomain.Actor
}

type ContentReactionCommandResult struct {
	ReactionID string
	Version    int64
	Reaction   reactiondomain.Value
	Liked      bool
	Changed    bool
	Replayed   bool
}

type CommentReactionCommandResult struct {
	ReactionID   string               `json:"reactionId"`
	Version      int64                `json:"version"`
	Reaction     reactiondomain.Value `json:"reaction"`
	Changed      bool                 `json:"changed"`
	Replayed     bool                 `json:"replayed"`
	LikeCount    int64                `json:"likeCount"`
	DislikeCount int64                `json:"dislikeCount"`
}

// ContentReactionStateSlice 是读取模型，不包含可变聚合、actorId 或 receipt。
type ContentReactionStateSlice struct {
	Found         bool
	PostID        string
	Liked         bool
	Version       int64
	UpdatedAt     time.Time
	MutationBasis string
}

type ContentReactionCommandRecoveryResult struct {
	IdempotencyKey   string
	Outcome          string
	Replayed         bool
	CommittedVersion *int64
	Changed          *bool
}
type RecoverContentReactionCommand struct {
	Identity       reactiondomain.Identity
	CommandName    string
	IdempotencyKey string
}
type FinalizeExpiredContentReactionCommand struct {
	Identity       reactiondomain.Identity
	CommandName    string
	Desired        reactiondomain.Value
	IdempotencyKey string
	Evidence       MutationEvidence
}

// ContentReactionStateReader 的返回值只能是 Slice。
type ContentReactionStateReader interface {
	ReadContentReactionState(
		ctx context.Context,
		identity reactiondomain.Identity,
	) (ContentReactionStateSlice, error)
}

// ReactionTargetSlice 是 reaction 引用目标的窄读结果：
// 只回答目标是否可互动以及作者是谁（通知接收者），不加载目标聚合。
type ReactionTargetSlice struct {
	Exists   bool
	AuthorID string
}

// ReactionTargetReader 只读取 reaction 引用目标的存在性与作者，不加载目标聚合。
type ReactionTargetReader interface {
	FindReactionTarget(
		ctx context.Context,
		target reactiondomain.Target,
	) (ReactionTargetSlice, error)
}

// CommentReactionCountReader 从 ContentReaction 权威集合派生评论赞踩计数。
type CommentReactionCountReader interface {
	CountCommentReactions(ctx context.Context, commentID string) (likeCount, dislikeCount int64, err error)
}

// ActivePostReactionReader 为 PostDeleted lifecycle consumer 返回待迁移的
// active ContentReaction identity，不暴露持久化文档。
type ActivePostReactionReader interface {
	ListActiveReactionsForPost(
		ctx context.Context,
		postID string,
		limit int,
	) ([]reactiondomain.Identity, error)
}
