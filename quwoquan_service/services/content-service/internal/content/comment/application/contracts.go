package comment

import (
	"time"

	commentmodel "quwoquan_service/services/content-service/internal/content/comment/domain/model"
)

type CreateCommentCommand struct {
	PostID                    string
	ActorID                   string
	AuthorDisplayNameSnapshot string
	AuthorAvatarURLSnapshot   string
	PersonaContextVersion     int64
	Content                   string
	ReplyToCommentID          string
	AttachmentMediaIDs        []string
	Mentions                  []commentmodel.Mention
}

type DeleteCommentCommand struct {
	PostID    string
	CommentID string
	ActorID   string
}

type HideCommentCommand struct {
	CommentID  string
	OperatorID string
	Reason     string
}

type RestoreCommentCommand struct {
	CommentID  string
	OperatorID string
	Reason     string
}

type ChangeCommentPinCommand struct {
	PostID    string
	CommentID string
	ActorID   string
	Pinned    bool
}

type BindCommentAttachmentsCommand struct {
	CommentID          string
	ActorID            string
	AttachmentMediaIDs []string
}

type ListCommentsQuery struct {
	PostID  string
	ActorID string
	Cursor  string
	Limit   int
	// Sort 是服务端排序档位原始参数（hot|latest，空值默认 hot）；
	// 未知值返回 CONTENT.USER.comment_sort_invalid。
	Sort string
}

type ListCommentRepliesQuery struct {
	PostID          string
	ParentCommentID string
	ActorID         string
	Cursor          string
	Limit           int
}

type ListCommentsByAuthorQuery struct {
	ActorID string
	Cursor  string
	Limit   int
}

type ListReceivedCommentsQuery struct {
	ActorID string
	Cursor  string
	Limit   int
}

type CommentCommandResult struct {
	ID       string              `json:"id"`
	Version  int64               `json:"version"`
	Status   commentmodel.Status `json:"status"`
	Replayed bool                `json:"replayed,omitempty"`
}

type CommentAttachmentSlice struct {
	MediaID   string `json:"mediaId"`
	MediaType string `json:"mediaType,omitempty"`
	URL       string `json:"url,omitempty"`
	Width     int    `json:"width,omitempty"`
	Height    int    `json:"height,omitempty"`
	Available bool   `json:"available"`
}

// CommentListItem 是强类型投影值，不是 Comment 聚合，不能用于发起变更。
type CommentListItem struct {
	ID                        string                   `json:"id"`
	Version                   int64                    `json:"version"`
	PostID                    string                   `json:"postId"`
	AuthorID                  string                   `json:"authorId"`
	AuthorDisplayNameSnapshot string                   `json:"authorDisplayNameSnapshot,omitempty"`
	AuthorAvatarURLSnapshot   string                   `json:"authorAvatarUrlSnapshot,omitempty"`
	PersonaContextVersion     int64                    `json:"personaContextVersion,omitempty"`
	Content                   string                   `json:"content"`
	ReplyToCommentID          string                   `json:"replyToCommentId,omitempty"`
	ReplyToUserID             string                   `json:"replyToUserId,omitempty"`
	ParentCommentID           string                   `json:"parentCommentId,omitempty"`
	AttachmentMediaIDs        []string                 `json:"attachmentMediaIds"`
	Attachments               []CommentAttachmentSlice `json:"attachments"`
	Mentions                  []commentmodel.Mention   `json:"mentions"`
	AssistantMentioned        bool                     `json:"assistantMentioned"`
	AssistantReplySource      string                   `json:"assistantReplySource,omitempty"`
	AssistantCorrectionStatus string                   `json:"assistantCorrectionStatus,omitempty"`
	AuthorIPLocation          string                   `json:"authorIpLocation,omitempty"`
	Status                    commentmodel.Status      `json:"status"`
	IsPinned                  bool                     `json:"isPinned"`
	PinnedAt                  *time.Time               `json:"pinnedAt,omitempty"`
	CreatedAt                 time.Time                `json:"createdAt"`
	UpdatedAt                 time.Time                `json:"updatedAt"`
	DeletedAt                 *time.Time               `json:"deletedAt,omitempty"`
	ReplyCount                int64                    `json:"replyCount"`
	ReplyPreview              []CommentListItem        `json:"replyPreview"`
	ReplyNextCursor           string                   `json:"replyNextCursor,omitempty"`
	LikeCount                 int64                    `json:"likeCount"`
	DislikeCount              int64                    `json:"dislikeCount"`
	ViewerReaction            string                   `json:"viewerReaction"`
	// AuthorLiked 是「Post 作者赞过这条评论」的 ContentReaction 事实投影。
	AuthorLiked bool `json:"authorLiked"`
	// ViewerRelation 是 viewer 对评论作者的关注/互关事实投影（none/following/friend）。
	ViewerRelation string `json:"viewerRelation"`
	IsAuthor       bool   `json:"isAuthor"`
	CanDelete      bool   `json:"canDelete"`
	CanReply       bool   `json:"canReply"`
	CanReport      bool   `json:"canReport"`
	CanPin         bool   `json:"canPin"`
}

type CommentPageSlice struct {
	Items      []CommentListItem `json:"items"`
	NextCursor string            `json:"nextCursor,omitempty"`
	Total      int64             `json:"total"`
}

type ReplyPageSlice struct {
	Items      []CommentListItem `json:"items"`
	NextCursor string            `json:"nextCursor,omitempty"`
	Total      int64             `json:"total"`
}

type AuthorCommentPageSlice struct {
	Items      []CommentListItem `json:"items"`
	NextCursor string            `json:"nextCursor,omitempty"`
	Total      int64             `json:"total"`
}

type ReceivedCommentPageSlice struct {
	Items      []CommentListItem `json:"items"`
	NextCursor string            `json:"nextCursor,omitempty"`
	Total      int64             `json:"total"`
}
