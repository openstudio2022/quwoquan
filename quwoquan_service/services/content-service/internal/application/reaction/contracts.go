package reaction

import (
	"context"
	"time"

	reactiondomain "quwoquan_service/services/content-service/internal/domain/reaction"
)

type LikePostCommand struct {
	PostID string
	Actor  reactiondomain.Actor
}

type UnlikePostCommand struct {
	PostID string
	Actor  reactiondomain.Actor
}

type ReactToCommentCommand struct {
	CommentID string
	Actor     reactiondomain.Actor
	Reaction  reactiondomain.Value
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
	Replayed     bool                 `json:"replayed,omitempty"`
	LikeCount    int64                `json:"likeCount"`
	DislikeCount int64                `json:"dislikeCount"`
}

// ContentReactionStateSlice 是读取模型，不包含可变聚合、actorId 或 receipt。
type ContentReactionStateSlice struct {
	Found     bool
	PostID    string
	Liked     bool
	Version   int64
	UpdatedAt time.Time
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

// ActiveReactionCounter 从 ContentReaction 权威集合重建 Post.likeCount projection。
type ActiveReactionCounter interface {
	CountActiveReactions(ctx context.Context, postID string) (int64, error)
}

// LikeCountProjectionWriter 仅写按 Post 维度可重建的计数投影，
// 可分别由 Post 与 DiscoveryFeed adapter 实现。
type LikeCountProjectionWriter interface {
	SetLikeCount(ctx context.Context, postID string, count int64) (bool, error)
}

// ActiveActorReactionCounter 按强类型 actor 从 ContentReaction 权威集合重算关系数。
type ActiveActorReactionCounter interface {
	CountActiveReactionsForActor(
		ctx context.Context,
		actor reactiondomain.Actor,
	) (int64, error)
}

// PersonaLikeCountProjectionWriter 仅写 persona 维度的可重建推荐特征。
// device actor 不得进入公开用户特征。
type PersonaLikeCountProjectionWriter interface {
	SetPersonaLikeCount(
		ctx context.Context,
		personaID string,
		count int64,
		occurredAt time.Time,
	) error
}
