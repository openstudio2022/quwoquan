package comment

import "time"

type commentCreatedEvent struct {
	CommentID        string    `json:"commentId"`
	Version          int64     `json:"version"`
	PostID           string    `json:"postId"`
	AuthorID         string    `json:"authorId"`
	ReplyToCommentID string    `json:"replyToCommentId,omitempty"`
	ReplyToUserID    string    `json:"replyToUserId,omitempty"`
	ParentCommentID  string    `json:"parentCommentId,omitempty"`
	CreatedAt        time.Time `json:"createdAt"`
}

type commentDeletedEvent struct {
	CommentID       string    `json:"commentId"`
	Version         int64     `json:"version"`
	PostID          string    `json:"postId"`
	AuthorID        string    `json:"authorId"`
	ParentCommentID string    `json:"parentCommentId,omitempty"`
	DeletedAt       time.Time `json:"deletedAt"`
}

type commentPinChangedEvent struct {
	CommentID  string     `json:"commentId"`
	Version    int64      `json:"version"`
	PostID     string     `json:"postId"`
	OperatorID string     `json:"operatorId"`
	IsPinned   bool       `json:"isPinned"`
	PinnedAt   *time.Time `json:"pinnedAt,omitempty"`
}

type commentAttachmentsBoundEvent struct {
	CommentID          string   `json:"commentId"`
	Version            int64    `json:"version"`
	PostID             string   `json:"postId"`
	AuthorID           string   `json:"authorId"`
	AttachmentMediaIDs []string `json:"attachmentMediaIds"`
}
