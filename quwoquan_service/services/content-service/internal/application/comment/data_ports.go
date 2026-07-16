package comment

import (
	"context"

	reactiondomain "quwoquan_service/services/content-service/internal/domain/reaction"
)

import commentports "quwoquan_service/services/content-service/internal/domain/comment/ports"

// DataPorts 通过对象专属领域端口声明 Comment application 的全部依赖；
// 此处绝不导入 infrastructure。
type DataPorts struct {
	Aggregate    commentports.AggregateStore
	PostPage     commentports.CommentPageReader
	ReplyPage    commentports.ReplyPageReader
	ReplySummary commentports.ReplySummaryReader
	AuthorPage   commentports.AuthorCommentPageReader
	ReceivedPage commentports.ReceivedCommentPageReader
	Counts       commentports.CountReader
	Relations    commentports.CommentRelationReader
	PostRelation commentports.PostOwnershipReader
	Attachments  commentports.AttachmentReader
	Reactions    CommentReactionProjectionReader
}

// CommentReactionProjectionReader 是 Comment query compositor 对
// ContentReaction 的窄只读防腐端口。批量方法是强制要求，禁止页面 N+1。
type CommentReactionProjectionReader interface {
	ReadCommentReactionCounts(
		ctx context.Context,
		commentIDs []string,
	) (map[string]reactiondomain.CommentReactionCounts, error)
	ReadCommentReactionValues(
		ctx context.Context,
		actor reactiondomain.Actor,
		commentIDs []string,
	) (map[string]reactiondomain.Value, error)
}

func BindDataPorts(adapter interface {
	commentports.AggregateStore
	commentports.CommentPageReader
	commentports.ReplyPageReader
	commentports.ReplySummaryReader
	commentports.AuthorCommentPageReader
	commentports.ReceivedCommentPageReader
	commentports.CountReader
	commentports.CommentRelationReader
	commentports.PostOwnershipReader
}, attachments commentports.AttachmentReader, reactions CommentReactionProjectionReader) DataPorts {
	return DataPorts{
		Aggregate:    adapter,
		PostPage:     adapter,
		ReplyPage:    adapter,
		ReplySummary: adapter,
		AuthorPage:   adapter,
		ReceivedPage: adapter,
		Counts:       adapter,
		Relations:    adapter,
		PostRelation: adapter,
		Attachments:  attachments,
		Reactions:    reactions,
	}
}
