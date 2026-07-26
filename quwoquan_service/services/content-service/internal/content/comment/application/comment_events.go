package comment

import (
	"time"

	commentmodel "quwoquan_service/services/content-service/internal/content/comment/domain/model"
)

type commentCreatedEvent struct {
	CommentID        string    `json:"commentId"`
	Version          int64     `json:"version"`
	PostID           string    `json:"postId"`
	PostAuthorID     string    `json:"postAuthorId"`
	AuthorID         string    `json:"authorId"`
	ReplyToCommentID string    `json:"replyToCommentId,omitempty"`
	ReplyToUserID    string    `json:"replyToUserId,omitempty"`
	ParentCommentID  string    `json:"parentCommentId,omitempty"`
	MentionedUserIDs []string  `json:"mentionedUserIds,omitempty"`
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

type commentModeratedEvent struct {
	CommentID       string                        `json:"commentId"`
	Version         int64                         `json:"version"`
	PostID          string                        `json:"postId"`
	ParentCommentID string                        `json:"parentCommentId,omitempty"`
	OperatorID      string                        `json:"operatorId"`
	Action          commentmodel.ModerationAction `json:"action"`
	Reason          string                        `json:"reason"`
	OccurredAt      time.Time                     `json:"occurredAt"`
}

type commentPinChangedEvent struct {
	CommentID       string     `json:"commentId"`
	Version         int64      `json:"version"`
	PostID          string     `json:"postId"`
	CommentAuthorID string     `json:"commentAuthorId"`
	OperatorID      string     `json:"operatorId"`
	IsPinned        bool       `json:"isPinned"`
	PinnedAt        *time.Time `json:"pinnedAt,omitempty"`
}

type commentAttachmentsBoundEvent struct {
	CommentID          string   `json:"commentId"`
	Version            int64    `json:"version"`
	PostID             string   `json:"postId"`
	AuthorID           string   `json:"authorId"`
	AttachmentMediaIDs []string `json:"attachmentMediaIds"`
}
