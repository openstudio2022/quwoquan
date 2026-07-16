package persistence

import (
	"strings"
	"time"

	commentmodel "quwoquan_service/services/content-service/internal/domain/comment/model"
)

type commentAggregateDocument struct {
	ID                        string                 `bson:"_id"`
	Version                   int64                  `bson:"version"`
	PostID                    string                 `bson:"postId"`
	AuthorID                  string                 `bson:"authorId"`
	AuthorDisplayNameSnapshot string                 `bson:"authorDisplayNameSnapshot"`
	AuthorAvatarURLSnapshot   string                 `bson:"authorAvatarUrlSnapshot"`
	PersonaContextVersion     int64                  `bson:"personaContextVersion"`
	Content                   string                 `bson:"content"`
	ReplyToCommentID          string                 `bson:"replyToCommentId"`
	ReplyToUserID             string                 `bson:"replyToUserId"`
	ParentCommentID           string                 `bson:"parentCommentId"`
	AttachmentMediaIDs        []string               `bson:"attachmentMediaIds"`
	Mentions                  []commentmodel.Mention `bson:"mentions"`
	AssistantMentioned        bool                   `bson:"assistantMentioned"`
	AssistantReplySource      string                 `bson:"assistantReplySource"`
	AssistantCorrectionStatus string                 `bson:"assistantCorrectionStatus"`
	Status                    string                 `bson:"status"`
	IsPinned                  bool                   `bson:"isPinned"`
	PinnedAt                  *time.Time             `bson:"pinnedAt,omitempty"`
	CreatedAt                 time.Time              `bson:"createdAt"`
	UpdatedAt                 time.Time              `bson:"updatedAt"`
	DeletedAt                 *time.Time             `bson:"deletedAt,omitempty"`
}

func commentAggregateDocumentFromSnapshot(snapshot commentmodel.Snapshot) commentAggregateDocument {
	return commentAggregateDocument{
		ID:                        snapshot.ID,
		Version:                   snapshot.Version,
		PostID:                    snapshot.PostID,
		AuthorID:                  snapshot.AuthorID,
		AuthorDisplayNameSnapshot: snapshot.AuthorDisplayNameSnapshot,
		AuthorAvatarURLSnapshot:   snapshot.AuthorAvatarURLSnapshot,
		PersonaContextVersion:     snapshot.PersonaContextVersion,
		Content:                   snapshot.Content,
		ReplyToCommentID:          snapshot.ReplyToCommentID,
		ReplyToUserID:             snapshot.ReplyToUserID,
		ParentCommentID:           snapshot.ParentCommentID,
		AttachmentMediaIDs:        cloneStrings(snapshot.AttachmentMediaIDs),
		Mentions:                  cloneMentions(snapshot.Mentions),
		AssistantMentioned:        snapshot.AssistantMentioned,
		AssistantReplySource:      snapshot.AssistantReplySource,
		AssistantCorrectionStatus: snapshot.AssistantCorrectionStatus,
		Status:                    string(snapshot.Status),
		IsPinned:                  snapshot.IsPinned,
		PinnedAt:                  cloneTime(snapshot.PinnedAt),
		CreatedAt:                 snapshot.CreatedAt.UTC(),
		UpdatedAt:                 snapshot.UpdatedAt.UTC(),
		DeletedAt:                 cloneTime(snapshot.DeletedAt),
	}
}

func (d commentAggregateDocument) aggregate() (*commentmodel.Comment, error) {
	return commentmodel.Restore(commentmodel.Snapshot{
		ID:                        d.ID,
		Version:                   d.Version,
		PostID:                    d.PostID,
		AuthorID:                  d.AuthorID,
		AuthorDisplayNameSnapshot: d.AuthorDisplayNameSnapshot,
		AuthorAvatarURLSnapshot:   d.AuthorAvatarURLSnapshot,
		PersonaContextVersion:     d.PersonaContextVersion,
		Content:                   d.Content,
		ReplyToCommentID:          d.ReplyToCommentID,
		ReplyToUserID:             d.ReplyToUserID,
		ParentCommentID:           d.ParentCommentID,
		AttachmentMediaIDs:        cloneStrings(d.AttachmentMediaIDs),
		Mentions:                  cloneMentions(d.Mentions),
		AssistantMentioned:        d.AssistantMentioned,
		AssistantReplySource:      d.AssistantReplySource,
		AssistantCorrectionStatus: d.AssistantCorrectionStatus,
		Status:                    commentmodel.Status(d.Status),
		IsPinned:                  d.IsPinned,
		PinnedAt:                  cloneTime(d.PinnedAt),
		CreatedAt:                 d.CreatedAt.UTC(),
		UpdatedAt:                 d.UpdatedAt.UTC(),
		DeletedAt:                 cloneTime(d.DeletedAt),
	})
}

type commentCommandReceiptDocument struct {
	ID               string                   `bson:"_id"`
	AggregateID      string                   `bson:"aggregateId"`
	AggregateVersion int64                    `bson:"aggregateVersion"`
	CommandName      string                   `bson:"commandName"`
	CommandDigest    string                   `bson:"commandDigest"`
	Result           commentAggregateDocument `bson:"result"`
	CreatedAt        time.Time                `bson:"createdAt"`
	ExpiresAt        time.Time                `bson:"expiresAt"`
}

type commentOutboxDocument struct {
	ID               string    `bson:"_id"`
	EventType        string    `bson:"eventType"`
	AggregateID      string    `bson:"aggregateId"`
	AggregateVersion int64     `bson:"aggregateVersion"`
	Payload          []byte    `bson:"payload"`
	OccurredAt       time.Time `bson:"occurredAt"`
}

type commentCheckpointDocument struct {
	ID         string    `bson:"_id"`
	Checkpoint string    `bson:"checkpoint"`
	UpdatedAt  time.Time `bson:"updatedAt"`
}

type commentReadDocument struct {
	ID                        string                 `bson:"_id"`
	Version                   int64                  `bson:"version"`
	PostID                    string                 `bson:"postId"`
	AuthorID                  string                 `bson:"authorId"`
	AuthorDisplayNameSnapshot string                 `bson:"authorDisplayNameSnapshot"`
	AuthorAvatarURLSnapshot   string                 `bson:"authorAvatarUrlSnapshot"`
	PersonaContextVersion     int64                  `bson:"personaContextVersion"`
	Content                   string                 `bson:"content"`
	ReplyToCommentID          string                 `bson:"replyToCommentId"`
	ReplyToUserID             string                 `bson:"replyToUserId"`
	ParentCommentID           string                 `bson:"parentCommentId"`
	AttachmentMediaIDs        []string               `bson:"attachmentMediaIds"`
	Mentions                  []commentmodel.Mention `bson:"mentions"`
	AssistantMentioned        bool                   `bson:"assistantMentioned"`
	AssistantReplySource      string                 `bson:"assistantReplySource"`
	AssistantCorrectionStatus string                 `bson:"assistantCorrectionStatus"`
	Status                    string                 `bson:"status"`
	IsPinned                  bool                   `bson:"isPinned"`
	PinnedAt                  *time.Time             `bson:"pinnedAt,omitempty"`
	CreatedAt                 time.Time              `bson:"createdAt"`
	UpdatedAt                 time.Time              `bson:"updatedAt"`
	DeletedAt                 *time.Time             `bson:"deletedAt,omitempty"`
}

func (d commentReadDocument) readModel() commentmodel.ReadModel {
	return commentmodel.ReadModel{
		ID:                        d.ID,
		Version:                   d.Version,
		PostID:                    d.PostID,
		AuthorID:                  d.AuthorID,
		AuthorDisplayNameSnapshot: d.AuthorDisplayNameSnapshot,
		AuthorAvatarURLSnapshot:   d.AuthorAvatarURLSnapshot,
		PersonaContextVersion:     d.PersonaContextVersion,
		Content:                   d.Content,
		ReplyToCommentID:          d.ReplyToCommentID,
		ReplyToUserID:             d.ReplyToUserID,
		ParentCommentID:           d.ParentCommentID,
		AttachmentMediaIDs:        cloneStrings(d.AttachmentMediaIDs),
		Mentions:                  cloneMentions(d.Mentions),
		AssistantMentioned:        d.AssistantMentioned,
		AssistantReplySource:      d.AssistantReplySource,
		AssistantCorrectionStatus: d.AssistantCorrectionStatus,
		Status:                    commentmodel.Status(d.Status),
		IsPinned:                  d.IsPinned,
		PinnedAt:                  cloneTime(d.PinnedAt),
		CreatedAt:                 d.CreatedAt.UTC(),
		UpdatedAt:                 d.UpdatedAt.UTC(),
		DeletedAt:                 cloneTime(d.DeletedAt),
	}
}

type commentRelationDocument struct {
	ID              string `bson:"_id"`
	PostID          string `bson:"postId"`
	AuthorID        string `bson:"authorId"`
	ParentCommentID string `bson:"parentCommentId"`
	Status          string `bson:"status"`
}

type postOwnershipDocument struct {
	ID       string `bson:"_id"`
	AuthorID string `bson:"authorId"`
	Status   string `bson:"status"`
}

type postIDDocument struct {
	ID string `bson:"_id"`
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

func uniqueNonEmptyStrings(values []string) []string {
	seen := make(map[string]struct{}, len(values))
	unique := make([]string, 0, len(values))
	for _, value := range values {
		value = strings.TrimSpace(value)
		if value == "" {
			continue
		}
		if _, found := seen[value]; found {
			continue
		}
		seen[value] = struct{}{}
		unique = append(unique, value)
	}
	return unique
}

func cloneMentions(values []commentmodel.Mention) []commentmodel.Mention {
	if len(values) == 0 {
		return []commentmodel.Mention{}
	}
	cloned := make([]commentmodel.Mention, len(values))
	copy(cloned, values)
	return cloned
}

func cloneReadModels(values []commentmodel.ReadModel) []commentmodel.ReadModel {
	cloned := make([]commentmodel.ReadModel, len(values))
	for index, value := range values {
		cloned[index] = value.Clone()
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
