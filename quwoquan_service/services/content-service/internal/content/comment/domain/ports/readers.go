package ports

import (
	"context"

	commentmodel "quwoquan_service/services/content-service/internal/content/comment/domain/model"
)

type PageRequest struct {
	Cursor            string
	Limit             int
	ExcludedAuthorIDs []string
	// Sort 仅对一级评论列表生效；零值按 SortHot 处理。回复/作者/收到列表忽略。
	Sort commentmodel.SortMode
}

// CommentPageReader 持有具名一级评论 CommentPage 读切片。
type CommentPageReader interface {
	ListByPost(
		ctx context.Context,
		postID string,
		request PageRequest,
	) (commentmodel.Page, error)
}

// ReplyPageReader 持有具名二级回复 ReplyPage 读切片。
type ReplyPageReader interface {
	ListReplies(
		ctx context.Context,
		postID string,
		parentCommentID string,
		request PageRequest,
	) (commentmodel.Page, error)
}

// ReplySummaryReader 批量返回一级 Comment 的回复计数和有界预览，供页面
// compositor 使用；禁止 query service 对每条一级评论发起独立查询。
type ReplySummaryReader interface {
	ReadReplySummaries(
		ctx context.Context,
		parentCommentIDs []string,
		previewLimit int,
		excludedAuthorIDs []string,
	) (map[string]commentmodel.ReplySummary, error)
}

// AuthorCommentPageReader 持有 persona 已发表 Comment 切片。
type AuthorCommentPageReader interface {
	ListByAuthor(
		ctx context.Context,
		authorID string,
		request PageRequest,
	) (commentmodel.Page, error)
}

// ReceivedCommentPageReader 持有 Post 作者收到的 Comment 切片。
type ReceivedCommentPageReader interface {
	ListReceivedByPostAuthor(
		ctx context.Context,
		postAuthorID string,
		postIDs []string,
		request PageRequest,
	) (commentmodel.Page, error)
}

type CountReader interface {
	CountByPost(ctx context.Context, postID string) (int64, error)
}

// CommentRelationReader 返回用于保证回复不变量的窄投影，不能返回 Comment 聚合。
type CommentRelationReader interface {
	FindReplyTarget(
		ctx context.Context,
		commentID string,
	) (commentmodel.ReplyTarget, bool, error)
}

// PostOwnershipReader 是防腐关系端口。其实现可投影 posts 集合，但不得向
// Comment application 解码或暴露 Post 聚合。
type PostOwnershipReader interface {
	FindPostOwnership(
		ctx context.Context,
		postID string,
	) (commentmodel.PostOwnership, bool, error)
	ListOwnedPostIDs(ctx context.Context, postAuthorID string) ([]string, error)
	FindPostOwnerships(
		ctx context.Context,
		postIDs []string,
	) (map[string]commentmodel.PostOwnership, error)
}

type AttachmentReader interface {
	ValidateCommentAttachments(ctx context.Context, actorID string, mediaIDs []string) error
	ReadCommentAttachments(
		ctx context.Context,
		mediaIDs []string,
	) (map[string]commentmodel.AttachmentProjection, error)
}
