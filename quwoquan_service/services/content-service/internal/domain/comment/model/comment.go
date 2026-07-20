// Package model 包含 Comment 聚合及其值对象。
package model

import (
	"errors"
	"fmt"
	"strings"
	"time"
)

var (
	ErrInvalidComment          = errors.New("invalid comment")
	ErrInvalidReplyTarget      = errors.New("invalid comment reply target")
	ErrCommentDeleted          = errors.New("comment is deleted")
	ErrDeleteForbidden         = errors.New("comment delete forbidden")
	ErrPinForbidden            = errors.New("comment pin forbidden")
	ErrPinInvalidTarget        = errors.New("comment pin invalid target")
	ErrAttachmentForbidden     = errors.New("comment attachment update forbidden")
	ErrInvalidMutationClock    = errors.New("invalid comment mutation clock")
	ErrModerationForbidden     = errors.New("comment moderation forbidden")
	ErrInvalidStatusTransition = errors.New("invalid comment status transition")
)

const MaxContentRunes = 1000

type Status string

const (
	StatusActive Status = "active"
	// StatusHidden 表示 operator 治理隐藏；前台不可见，可经 RestoreFromHidden 恢复。
	StatusHidden  Status = "hidden"
	StatusDeleted Status = "deleted"
	// StatusTombstoned 表示宿主 Post 删除后的级联终态；不可恢复。
	StatusTombstoned Status = "tombstoned"
)

// ModerationAction 是 CommentModerated 审计事实的动作枚举。
type ModerationAction string

const (
	ModerationActionHide    ModerationAction = "hide"
	ModerationActionRestore ModerationAction = "restore"
)

// Mention 是随 Comment 聚合持久化的强类型不可变值对象。
type Mention struct {
	SubjectType string `json:"subjectType" bson:"subjectType"`
	SubjectID   string `json:"subjectId" bson:"subjectId"`
	DisplayName string `json:"displayName,omitempty" bson:"displayName,omitempty"`
}

// Snapshot 是 Comment 的持久化边界，只包含值；application 与
// infrastructure 必须通过聚合方法产生新的状态，不能直接改写聚合。
type Snapshot struct {
	ID                        string
	Version                   int64
	PostID                    string
	AuthorID                  string
	AuthorDisplayNameSnapshot string
	AuthorAvatarURLSnapshot   string
	PersonaContextVersion     int64
	Content                   string
	ReplyToCommentID          string
	ReplyToUserID             string
	ParentCommentID           string
	AttachmentMediaIDs        []string
	Mentions                  []Mention
	AssistantMentioned        bool
	AssistantReplySource      string
	AssistantCorrectionStatus string
	AuthorIPLocation          string
	Status                    Status
	IsPinned                  bool
	PinnedAt                  *time.Time
	HiddenAt                  *time.Time
	CreatedAt                 time.Time
	UpdatedAt                 time.Time
	DeletedAt                 *time.Time
}

type CreateParams struct {
	ID                        string
	PostID                    string
	AuthorID                  string
	AuthorDisplayNameSnapshot string
	AuthorAvatarURLSnapshot   string
	PersonaContextVersion     int64
	Content                   string
	ReplyToCommentID          string
	ReplyToUserID             string
	ParentCommentID           string
	AttachmentMediaIDs        []string
	Mentions                  []Mention
	AssistantMentioned        bool
	AuthorIPLocation          string
	Now                       time.Time
}

// Comment 将状态保持私有。跨聚合的 Post.commentCount、回复数、反应和
// 展示投影均不属于此聚合。
type Comment struct {
	id                        string
	version                   int64
	postID                    string
	authorID                  string
	authorDisplayNameSnapshot string
	authorAvatarURLSnapshot   string
	personaContextVersion     int64
	content                   string
	replyToCommentID          string
	replyToUserID             string
	parentCommentID           string
	attachmentMediaIDs        []string
	mentions                  []Mention
	assistantMentioned        bool
	assistantReplySource      string
	assistantCorrectionStatus string
	authorIPLocation          string
	status                    Status
	isPinned                  bool
	pinnedAt                  *time.Time
	hiddenAt                  *time.Time
	createdAt                 time.Time
	updatedAt                 time.Time
	deletedAt                 *time.Time
}

func Create(params CreateParams) (*Comment, error) {
	now := params.Now.UTC()
	comment := &Comment{
		id:                        strings.TrimSpace(params.ID),
		version:                   1,
		postID:                    strings.TrimSpace(params.PostID),
		authorID:                  strings.TrimSpace(params.AuthorID),
		authorDisplayNameSnapshot: strings.TrimSpace(params.AuthorDisplayNameSnapshot),
		authorAvatarURLSnapshot:   strings.TrimSpace(params.AuthorAvatarURLSnapshot),
		personaContextVersion:     params.PersonaContextVersion,
		content:                   strings.TrimSpace(params.Content),
		replyToCommentID:          strings.TrimSpace(params.ReplyToCommentID),
		replyToUserID:             strings.TrimSpace(params.ReplyToUserID),
		parentCommentID:           strings.TrimSpace(params.ParentCommentID),
		attachmentMediaIDs:        cloneStrings(params.AttachmentMediaIDs),
		mentions:                  cloneMentions(params.Mentions),
		assistantMentioned:        params.AssistantMentioned,
		authorIPLocation:          strings.TrimSpace(params.AuthorIPLocation),
		status:                    StatusActive,
		createdAt:                 now,
		updatedAt:                 now,
	}
	if err := comment.validate(); err != nil {
		return nil, err
	}
	return comment, nil
}

func Restore(snapshot Snapshot) (*Comment, error) {
	comment := &Comment{
		id:                        strings.TrimSpace(snapshot.ID),
		version:                   snapshot.Version,
		postID:                    strings.TrimSpace(snapshot.PostID),
		authorID:                  strings.TrimSpace(snapshot.AuthorID),
		authorDisplayNameSnapshot: strings.TrimSpace(snapshot.AuthorDisplayNameSnapshot),
		authorAvatarURLSnapshot:   strings.TrimSpace(snapshot.AuthorAvatarURLSnapshot),
		personaContextVersion:     snapshot.PersonaContextVersion,
		content:                   strings.TrimSpace(snapshot.Content),
		replyToCommentID:          strings.TrimSpace(snapshot.ReplyToCommentID),
		replyToUserID:             strings.TrimSpace(snapshot.ReplyToUserID),
		parentCommentID:           strings.TrimSpace(snapshot.ParentCommentID),
		attachmentMediaIDs:        cloneStrings(snapshot.AttachmentMediaIDs),
		mentions:                  cloneMentions(snapshot.Mentions),
		assistantMentioned:        snapshot.AssistantMentioned,
		assistantReplySource:      strings.TrimSpace(snapshot.AssistantReplySource),
		assistantCorrectionStatus: strings.TrimSpace(snapshot.AssistantCorrectionStatus),
		authorIPLocation:          strings.TrimSpace(snapshot.AuthorIPLocation),
		status:                    snapshot.Status,
		isPinned:                  snapshot.IsPinned,
		pinnedAt:                  cloneTime(snapshot.PinnedAt),
		hiddenAt:                  cloneTime(snapshot.HiddenAt),
		createdAt:                 snapshot.CreatedAt.UTC(),
		updatedAt:                 snapshot.UpdatedAt.UTC(),
		deletedAt:                 cloneTime(snapshot.DeletedAt),
	}
	if err := comment.validate(); err != nil {
		return nil, err
	}
	return comment, nil
}

func (c *Comment) Hide(operatorID string, now time.Time) error {
	if strings.TrimSpace(operatorID) == "" {
		return ErrModerationForbidden
	}
	if c == nil || c.status != StatusActive {
		return ErrInvalidStatusTransition
	}
	if err := c.advance(now); err != nil {
		return err
	}
	c.status = StatusHidden
	c.isPinned = false
	c.pinnedAt = nil
	hiddenAt := c.updatedAt
	c.hiddenAt = &hiddenAt
	return nil
}

func (c *Comment) RestoreFromHidden(operatorID string, now time.Time) error {
	if strings.TrimSpace(operatorID) == "" {
		return ErrModerationForbidden
	}
	if c == nil || c.status != StatusHidden {
		return ErrInvalidStatusTransition
	}
	if err := c.advance(now); err != nil {
		return err
	}
	c.status = StatusActive
	c.hiddenAt = nil
	return nil
}

func (c *Comment) Delete(actorID string, now time.Time) error {
	if c == nil || c.status == StatusDeleted {
		return ErrCommentDeleted
	}
	if c.status != StatusActive {
		return ErrInvalidStatusTransition
	}
	if strings.TrimSpace(actorID) == "" || strings.TrimSpace(actorID) != c.authorID {
		return ErrDeleteForbidden
	}
	if err := c.advance(now); err != nil {
		return err
	}
	c.status = StatusDeleted
	c.isPinned = false
	c.pinnedAt = nil
	deletedAt := c.updatedAt
	c.deletedAt = &deletedAt
	return nil
}

func (c *Comment) ChangePin(operatorID, postAuthorID string, pinned bool, now time.Time) error {
	if c == nil || c.status == StatusDeleted || c.status == StatusTombstoned {
		return ErrCommentDeleted
	}
	if c.status != StatusActive {
		return ErrInvalidStatusTransition
	}
	if strings.TrimSpace(operatorID) == "" || strings.TrimSpace(operatorID) != strings.TrimSpace(postAuthorID) {
		return ErrPinForbidden
	}
	if c.parentCommentID != "" {
		return ErrPinInvalidTarget
	}
	if err := c.advance(now); err != nil {
		return err
	}
	c.isPinned = pinned
	if pinned {
		pinnedAt := c.updatedAt
		c.pinnedAt = &pinnedAt
	} else {
		c.pinnedAt = nil
	}
	return nil
}

func (c *Comment) BindAttachments(actorID string, attachmentMediaIDs []string, now time.Time) error {
	if c == nil || c.status == StatusDeleted || c.status == StatusTombstoned {
		return ErrCommentDeleted
	}
	if c.status != StatusActive {
		return ErrInvalidStatusTransition
	}
	if strings.TrimSpace(actorID) == "" || strings.TrimSpace(actorID) != c.authorID {
		return ErrAttachmentForbidden
	}
	if err := c.advance(now); err != nil {
		return err
	}
	c.attachmentMediaIDs = cloneStrings(attachmentMediaIDs)
	return nil
}

func (c *Comment) ID() string {
	if c == nil {
		return ""
	}
	return c.id
}

func (c *Comment) Version() int64 {
	if c == nil {
		return 0
	}
	return c.version
}

func (c *Comment) Status() Status {
	if c == nil {
		return ""
	}
	return c.status
}

func (c *Comment) Snapshot() Snapshot {
	if c == nil {
		return Snapshot{}
	}
	return Snapshot{
		ID:                        c.id,
		Version:                   c.version,
		PostID:                    c.postID,
		AuthorID:                  c.authorID,
		AuthorDisplayNameSnapshot: c.authorDisplayNameSnapshot,
		AuthorAvatarURLSnapshot:   c.authorAvatarURLSnapshot,
		PersonaContextVersion:     c.personaContextVersion,
		Content:                   c.content,
		ReplyToCommentID:          c.replyToCommentID,
		ReplyToUserID:             c.replyToUserID,
		ParentCommentID:           c.parentCommentID,
		AttachmentMediaIDs:        cloneStrings(c.attachmentMediaIDs),
		Mentions:                  cloneMentions(c.mentions),
		AssistantMentioned:        c.assistantMentioned,
		AssistantReplySource:      c.assistantReplySource,
		AssistantCorrectionStatus: c.assistantCorrectionStatus,
		AuthorIPLocation:          c.authorIPLocation,
		Status:                    c.status,
		IsPinned:                  c.isPinned,
		PinnedAt:                  cloneTime(c.pinnedAt),
		HiddenAt:                  cloneTime(c.hiddenAt),
		CreatedAt:                 c.createdAt,
		UpdatedAt:                 c.updatedAt,
		DeletedAt:                 cloneTime(c.deletedAt),
	}
}

func (c *Comment) advance(now time.Time) error {
	now = now.UTC()
	if now.IsZero() || now.Before(c.updatedAt) {
		return fmt.Errorf("%w: transition timestamp must be monotonic", ErrInvalidMutationClock)
	}
	c.version++
	c.updatedAt = now
	return nil
}

func (c *Comment) validate() error {
	if c == nil ||
		c.id == "" ||
		c.version < 1 ||
		c.postID == "" ||
		c.authorID == "" ||
		c.content == "" ||
		len([]rune(c.content)) > MaxContentRunes ||
		!isKnownStatus(c.status) ||
		c.createdAt.IsZero() ||
		c.updatedAt.IsZero() ||
		c.updatedAt.Before(c.createdAt) {
		return fmt.Errorf("%w: required state is missing or malformed", ErrInvalidComment)
	}
	if c.replyToCommentID == "" {
		if c.replyToUserID != "" || c.parentCommentID != "" {
			return fmt.Errorf("%w: top-level comment cannot carry reply linkage", ErrInvalidReplyTarget)
		}
	} else if c.replyToUserID == "" || c.parentCommentID == "" {
		return fmt.Errorf("%w: reply must carry target author and normalized parent", ErrInvalidReplyTarget)
	}
	if c.parentCommentID == c.id || c.replyToCommentID == c.id {
		return fmt.Errorf("%w: comment cannot reply to itself", ErrInvalidReplyTarget)
	}
	if c.status == StatusDeleted {
		if c.deletedAt == nil || c.isPinned || c.pinnedAt != nil || c.hiddenAt != nil {
			return fmt.Errorf("%w: deleted comment state is inconsistent", ErrInvalidComment)
		}
	} else if c.deletedAt != nil {
		return fmt.Errorf("%w: non-deleted comment cannot have deletedAt", ErrInvalidComment)
	}
	if c.status == StatusHidden {
		if c.hiddenAt == nil || c.isPinned || c.pinnedAt != nil {
			return fmt.Errorf("%w: hidden comment state is inconsistent", ErrInvalidComment)
		}
	} else if c.hiddenAt != nil {
		return fmt.Errorf("%w: non-hidden comment cannot have hiddenAt", ErrInvalidComment)
	}
	if c.status == StatusTombstoned && (c.isPinned || c.pinnedAt != nil) {
		return fmt.Errorf("%w: tombstoned comment cannot stay pinned", ErrInvalidComment)
	}
	if c.isPinned && (c.parentCommentID != "" || c.pinnedAt == nil) {
		return fmt.Errorf("%w: only top-level comment can be pinned", ErrInvalidComment)
	}
	if !c.isPinned && c.pinnedAt != nil {
		return fmt.Errorf("%w: unpinned comment cannot have pinnedAt", ErrInvalidComment)
	}
	for _, mention := range c.mentions {
		if strings.TrimSpace(mention.SubjectType) == "" || strings.TrimSpace(mention.SubjectID) == "" {
			return fmt.Errorf("%w: mention requires type and subject", ErrInvalidComment)
		}
	}
	return nil
}

func isKnownStatus(status Status) bool {
	switch status {
	case StatusActive, StatusHidden, StatusDeleted, StatusTombstoned:
		return true
	default:
		return false
	}
}

func cloneStrings(values []string) []string {
	if len(values) == 0 {
		return []string{}
	}
	cloned := make([]string, 0, len(values))
	for _, value := range values {
		if value = strings.TrimSpace(value); value != "" {
			cloned = append(cloned, value)
		}
	}
	return cloned
}

func cloneMentions(values []Mention) []Mention {
	if len(values) == 0 {
		return []Mention{}
	}
	cloned := make([]Mention, len(values))
	for index, value := range values {
		cloned[index] = Mention{
			SubjectType: strings.TrimSpace(value.SubjectType),
			SubjectID:   strings.TrimSpace(value.SubjectID),
			DisplayName: strings.TrimSpace(value.DisplayName),
		}
	}
	return cloned
}

func cloneTime(value *time.Time) *time.Time {
	if value == nil {
		return nil
	}
	cloned := value.UTC()
	return &cloned
}
