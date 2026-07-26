package comment

import (
	"context"

	commentmodel "quwoquan_service/services/content-service/internal/content/comment/domain/model"
	reactiondomain "quwoquan_service/services/content-service/internal/content/content_reaction/domain/reaction"
)

import commentports "quwoquan_service/services/content-service/internal/content/comment/domain/ports"

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
	// ViewerRelations 是 viewer→评论作者关注/互关事实的窄只读防腐端口
	// （persona_follow_projection）；批量方法是强制要求，禁止页面 N+1。
	ViewerRelations CommentViewerRelationReader
	// ViewerBlocks 返回与 viewer 任一方向存在拉黑关系的 persona 集合。
	// 该事实来自 user 域投影，评论读路径不得信任客户端自报集合。
	ViewerBlocks CommentViewerBlockReader
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
	// ReadAuthorLikedFlags 批量返回「各 Post 作者是否赞过该评论」事实：
	// 入参按 postAuthorId 分组 commentIds，一次查询返回 commentId → liked。
	ReadAuthorLikedFlags(
		ctx context.Context,
		commentIDsByPostAuthor map[string][]string,
	) (map[string]bool, error)
}

// CommentViewerRelationReader 批量判定 viewer 对一组评论作者的关注/互关事实。
type CommentViewerRelationReader interface {
	ReadViewerRelations(
		ctx context.Context,
		viewerPersonaID string,
		authorPersonaIDs []string,
	) (map[string]commentmodel.ViewerRelation, error)
}

type CommentViewerBlockReader interface {
	ListBlockedPersonaIDs(
		ctx context.Context,
		viewerPersonaID string,
	) ([]string, error)
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
}, attachments commentports.AttachmentReader,
	reactions CommentReactionProjectionReader,
	viewerRelations CommentViewerRelationReader,
	viewerBlocks CommentViewerBlockReader,
) DataPorts {
	return DataPorts{
		Aggregate:       adapter,
		PostPage:        adapter,
		ReplyPage:       adapter,
		ReplySummary:    adapter,
		AuthorPage:      adapter,
		ReceivedPage:    adapter,
		Counts:          adapter,
		Relations:       adapter,
		PostRelation:    adapter,
		Attachments:     attachments,
		Reactions:       reactions,
		ViewerRelations: viewerRelations,
		ViewerBlocks:    viewerBlocks,
	}
}
