package profileinteraction

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"strings"
	"time"

	commentports "quwoquan_service/services/content-service/internal/content/comment/domain/ports"
	reactionports "quwoquan_service/services/content-service/internal/content/content_reaction/domain/reaction/ports"
	shareports "quwoquan_service/services/content-service/internal/content/outbound_share_fact/domain/ports"
	postports "quwoquan_service/services/content-service/internal/content/post/domain/ports"
	activitymodel "quwoquan_service/services/content-service/internal/content/profile_interaction_activity_view/domain/model"
	activityports "quwoquan_service/services/content-service/internal/content/profile_interaction_activity_view/domain/ports"
	readfactmodel "quwoquan_service/services/content-service/internal/content/profile_interaction_read_fact/domain/model"
	readfactports "quwoquan_service/services/content-service/internal/content/profile_interaction_read_fact/domain/ports"
)

const (
	sourceReaction = "content_reaction"
	sourceComment  = "comment"
	sourceShare    = "outbound_share_fact"
)

type Projector struct {
	sources activityports.ProjectionSourceReader
	writer  activityports.ActivityProjectionWriter
}

func NewProjector(
	sources activityports.ProjectionSourceReader,
	writer activityports.ActivityProjectionWriter,
) *Projector {
	if sources == nil || writer == nil {
		panic("ProfileInteractionActivity projector requires source reader and writer")
	}
	return &Projector{sources: sources, writer: writer}
}

type ReactionProjector struct{ projector *Projector }

func NewReactionProjector(projector *Projector) *ReactionProjector {
	return &ReactionProjector{projector: projector}
}

type reactionFact struct {
	ReactionID     string    `json:"reactionId"`
	Version        int64     `json:"version"`
	TargetKind     string    `json:"targetKind"`
	TargetID       string    `json:"targetId"`
	TargetAuthorID string    `json:"targetAuthorId,omitempty"`
	ActorDimension string    `json:"actorDimension"`
	ActorID        string    `json:"actorId"`
	Reaction       string    `json:"reaction"`
	OccurredAt     time.Time `json:"occurredAt"`
	IdempotencyKey string    `json:"idempotencyKey"`
}

func (p *ReactionProjector) Publish(
	ctx context.Context,
	fact reactionports.OutboxFact,
) error {
	if p == nil || p.projector == nil {
		return fmt.Errorf("ProfileInteraction reaction projector is not configured")
	}
	var payload reactionFact
	if err := decodeStrict(fact.Payload, &payload); err != nil {
		return fmt.Errorf("decode ContentReaction profile activity fact: %w", err)
	}
	if payload.ReactionID == "" || payload.Version <= 0 ||
		payload.ReactionID != fact.AggregateID ||
		payload.Version != fact.AggregateVersion {
		return fmt.Errorf("ContentReaction profile activity identity is incomplete")
	}
	if payload.ActorDimension != "persona" {
		return nil
	}
	if payload.TargetKind == "comment" {
		reaction := payload.Reaction
		if fact.EventType == "ContentReactionCleared" {
			reaction = "none"
		}
		return p.projector.writer.SetCommentViewerReaction(
			ctx,
			payload.TargetID,
			payload.ActorID,
			reaction,
			payload.Version,
		)
	}
	if payload.TargetKind != "post" {
		return nil
	}
	if fact.EventType == "ContentReactionCleared" || payload.Reaction == "none" {
		post, found, err := p.projector.sources.FindPost(ctx, payload.TargetID)
		if err != nil {
			return fmt.Errorf("load cleared reaction target post: %w", err)
		}
		if found && postAvailability(post) != "active" {
			// PostDeleted 独立 consumer 会保留历史活动并把目标标记为不可用；
			// 删除联动产生的 reaction clear 不能把历史行误删。
			return nil
		}
		return p.projector.writer.DeactivateActivity(
			ctx,
			payload.ReactionID,
			payload.Version,
		)
	}
	if fact.EventType != "ContentReactionSet" || payload.Reaction != "like" {
		return nil
	}
	post, found, err := p.projector.sources.FindPost(ctx, payload.TargetID)
	if err != nil {
		return fmt.Errorf("load reaction target post: %w", err)
	}
	if !found {
		return fmt.Errorf("reaction target post %q is missing", payload.TargetID)
	}
	return p.projector.upsertPair(
		ctx,
		projectionSeed{
			ActivityID:    payload.ReactionID,
			ActivityType:  activitymodel.TypeLike,
			SourceType:    sourceReaction,
			SourceEventID: fact.EventID,
			SourceVersion: payload.Version,
			ActorID:       payload.ActorID,
			OccurredAt:    payload.OccurredAt,
			Post:          post,
		},
	)
}

type CommentProjector struct{ projector *Projector }

func NewCommentProjector(projector *Projector) *CommentProjector {
	return &CommentProjector{projector: projector}
}

type commentCreatedFact struct {
	CommentID        string    `json:"commentId"`
	Version          int64     `json:"version"`
	PostID           string    `json:"postId"`
	PostAuthorID     string    `json:"postAuthorId"`
	AuthorID         string    `json:"authorId"`
	ReplyToCommentID string    `json:"replyToCommentId,omitempty"`
	ReplyToUserID    string    `json:"replyToUserId,omitempty"`
	ParentCommentID  string    `json:"parentCommentId,omitempty"`
	CreatedAt        time.Time `json:"createdAt"`
}

type commentDeletedFact struct {
	CommentID       string    `json:"commentId"`
	Version         int64     `json:"version"`
	PostID          string    `json:"postId"`
	AuthorID        string    `json:"authorId"`
	ParentCommentID string    `json:"parentCommentId,omitempty"`
	DeletedAt       time.Time `json:"deletedAt"`
}

func (p *CommentProjector) Publish(
	ctx context.Context,
	event commentports.OutboxEvent,
) error {
	if p == nil || p.projector == nil {
		return fmt.Errorf("ProfileInteraction comment projector is not configured")
	}
	switch event.EventType {
	case "CommentDeleted":
		var payload commentDeletedFact
		if err := decodeStrict(event.Payload, &payload); err != nil {
			return fmt.Errorf("decode CommentDeleted profile activity fact: %w", err)
		}
		if payload.CommentID == "" || payload.Version <= 0 ||
			payload.CommentID != event.AggregateID ||
			payload.Version != event.AggregateVersion {
			return fmt.Errorf("CommentDeleted profile activity identity is incomplete")
		}
		return p.projector.writer.DeactivateActivity(
			ctx,
			payload.CommentID,
			payload.Version,
		)
	case "CommentCreated":
		var payload commentCreatedFact
		if err := decodeStrict(event.Payload, &payload); err != nil {
			return fmt.Errorf("decode CommentCreated profile activity fact: %w", err)
		}
		if payload.CommentID == "" || payload.Version <= 0 ||
			payload.CommentID != event.AggregateID ||
			payload.Version != event.AggregateVersion {
			return fmt.Errorf("CommentCreated profile activity identity is incomplete")
		}
		post, found, err := p.projector.sources.FindPost(ctx, payload.PostID)
		if err != nil {
			return fmt.Errorf("load comment target post: %w", err)
		}
		if !found {
			return fmt.Errorf("comment target post %q is missing", payload.PostID)
		}
		comment, found, err := p.projector.sources.FindComment(ctx, payload.CommentID)
		if err != nil {
			return fmt.Errorf("load comment projection source: %w", err)
		}
		if !found {
			return fmt.Errorf("comment projection source %q is missing", payload.CommentID)
		}
		return p.projector.upsertPair(
			ctx,
			projectionSeed{
				ActivityID:    payload.CommentID,
				ActivityType:  activitymodel.TypeComment,
				SourceType:    sourceComment,
				SourceEventID: event.EventID,
				SourceVersion: payload.Version,
				ActorID:       payload.AuthorID,
				OccurredAt:    payload.CreatedAt,
				Post:          post,
				Comment:       &comment,
			},
		)
	default:
		return nil
	}
}

type OutboundShareProjector struct{ projector *Projector }

func NewOutboundShareProjector(projector *Projector) *OutboundShareProjector {
	return &OutboundShareProjector{projector: projector}
}

type outboundShareFact struct {
	EventID               string    `json:"eventId"`
	PostID                string    `json:"postId"`
	ActorDimension        string    `json:"actorDimension"`
	ActorID               string    `json:"actorId"`
	Channel               string    `json:"channel"`
	DestinationKind       string    `json:"destinationKind"`
	DestinationDigest     string    `json:"destinationDigest,omitempty"`
	ReferralID            string    `json:"referralId"`
	ProviderReceiptDigest string    `json:"providerReceiptDigest"`
	OccurredAt            time.Time `json:"occurredAt"`
}

func (p *OutboundShareProjector) Publish(
	ctx context.Context,
	event shareports.OutboxEvent,
) error {
	if p == nil || p.projector == nil {
		return fmt.Errorf("ProfileInteraction outbound share projector is not configured")
	}
	if event.EventType != "OutboundShareRecorded" {
		return nil
	}
	var payload outboundShareFact
	if err := decodeStrict(event.Payload, &payload); err != nil {
		return fmt.Errorf("decode OutboundShareRecorded profile activity fact: %w", err)
	}
	if payload.EventID == "" || payload.EventID != event.EventID {
		return fmt.Errorf("OutboundShareRecorded profile activity identity is incomplete")
	}
	if payload.ActorDimension != "persona" {
		return nil
	}
	post, found, err := p.projector.sources.FindPost(ctx, payload.PostID)
	if err != nil {
		return fmt.Errorf("load outbound share target post: %w", err)
	}
	if !found {
		return fmt.Errorf("outbound share target post %q is missing", payload.PostID)
	}
	return p.projector.upsertPair(
		ctx,
		projectionSeed{
			ActivityID:           payload.EventID,
			ActivityType:         activitymodel.TypeShare,
			SourceType:           sourceShare,
			SourceEventID:        event.EventID,
			SourceVersion:        1,
			ActorID:              payload.ActorID,
			OccurredAt:           payload.OccurredAt,
			Post:                 post,
			OutboundShareEventID: payload.EventID,
		},
	)
}

type PostTargetProjector struct {
	writer activityports.ActivityProjectionWriter
}

func NewPostTargetProjector(
	writer activityports.ActivityProjectionWriter,
) *PostTargetProjector {
	return &PostTargetProjector{writer: writer}
}

func (p *PostTargetProjector) Publish(
	ctx context.Context,
	event postports.OutboxEvent,
) error {
	if p == nil || p.writer == nil {
		return fmt.Errorf("ProfileInteraction post target projector is not configured")
	}
	if event.EventType != "PostDeleted" {
		return nil
	}
	return p.writer.MarkTargetUnavailable(
		ctx,
		event.AggregateID,
		event.AggregateVersion,
		event.OccurredAt,
	)
}

type ReadFactProjector struct {
	writer activityports.ActivityProjectionWriter
}

func NewReadFactProjector(
	writer activityports.ActivityProjectionWriter,
) *ReadFactProjector {
	return &ReadFactProjector{writer: writer}
}

func (p *ReadFactProjector) Publish(
	ctx context.Context,
	event readfactports.OutboxEvent,
) error {
	if p == nil || p.writer == nil {
		return fmt.Errorf("ProfileInteraction read fact projector is not configured")
	}
	if event.EventType != readfactports.EventTypeProfileInteractionReadFactAppended {
		return nil
	}
	var fact readfactmodel.Fact
	if err := decodeStrict(event.Payload, &fact); err != nil {
		return fmt.Errorf("decode ProfileInteractionReadFact: %w", err)
	}
	if err := fact.Validate(); err != nil {
		return err
	}
	if fact.FactID != event.EventID {
		return fmt.Errorf("ProfileInteractionReadFact event identity mismatch")
	}
	return p.writer.ApplyReadState(
		ctx,
		fact.OwnerPersonaID,
		fact.ActivityID,
		fact.State,
		fact.OccurredAt,
	)
}

type projectionSeed struct {
	ActivityID           string
	ActivityType         string
	SourceType           string
	SourceEventID        string
	SourceVersion        int64
	ActorID              string
	OccurredAt           time.Time
	Post                 activityports.PostSlice
	Comment              *activityports.CommentSlice
	OutboundShareEventID string
}

func (p *Projector) upsertPair(ctx context.Context, seed projectionSeed) error {
	if strings.TrimSpace(seed.ActorID) == "" ||
		strings.TrimSpace(seed.Post.AuthorPersonaID) == "" {
		return fmt.Errorf("profile interaction actor and target owner are required")
	}
	if seed.ActorID == seed.Post.AuthorPersonaID {
		return nil
	}
	for _, direction := range []string{
		activitymodel.DirectionReceived,
		activitymodel.DirectionSent,
	} {
		item := buildActivity(seed, direction)
		if !item.Valid() {
			return fmt.Errorf("profile interaction projection row is incomplete")
		}
		if err := p.writer.Upsert(ctx, item); err != nil {
			return err
		}
	}
	return nil
}

func buildActivity(seed projectionSeed, direction string) activitymodel.Activity {
	post := seed.Post
	availability := postAvailability(post)
	summary := postSummary(post)
	actorName := seed.ActorID
	actorAvatar := ""
	commentKind := "none"
	commentID := ""
	parentCommentID := ""
	contextText := ""
	if seed.Comment != nil {
		if name := strings.TrimSpace(seed.Comment.AuthorDisplayNameSnapshot); name != "" {
			actorName = name
		}
		actorAvatar = strings.TrimSpace(seed.Comment.AuthorAvatarURLSnapshot)
		commentID = seed.Comment.ID
		parentCommentID = seed.Comment.ParentCommentID
		if seed.Comment.ParentCommentID != "" ||
			seed.Comment.ReplyToCommentID != "" ||
			seed.Comment.ReplyToPersonaID != "" {
			commentKind = "reply"
		} else {
			commentKind = "comment"
		}
		if seed.Comment.ReplyToPersonaID != "" {
			contextText = "回复 " + seed.Comment.ReplyToPersonaID
		}
	}
	targetName := strings.TrimSpace(post.AuthorDisplayNameSnapshot)
	if targetName == "" {
		targetName = post.AuthorPersonaID
	}
	owner := post.AuthorPersonaID
	displayID := seed.ActorID
	displayName := actorName
	displayAvatar := actorAvatar
	if direction == activitymodel.DirectionSent {
		owner = seed.ActorID
		displayID = post.AuthorPersonaID
		displayName = targetName
		displayAvatar = strings.TrimSpace(post.AuthorAvatarURLSnapshot)
	}
	previewUnavailable := availability != "active"
	previewRoute := ""
	previewText := summary
	previewImage := strings.TrimSpace(post.CoverURL)
	if previewImage == "" {
		for _, candidate := range post.MediaURLs {
			if strings.TrimSpace(candidate) != "" {
				previewImage = strings.TrimSpace(candidate)
				break
			}
		}
	}
	if previewUnavailable {
		previewText = ""
		previewImage = ""
	} else {
		previewRoute = "workBrowser"
	}
	return activitymodel.Activity{
		OwnerPersonaID:          owner,
		ActivityID:              seed.ActivityID,
		ActivityType:            seed.ActivityType,
		Direction:               direction,
		SourceType:              seed.SourceType,
		SourceEventID:           seed.SourceEventID,
		SourceVersion:           seed.SourceVersion,
		TargetVersion:           post.Version,
		Active:                  true,
		CommentKind:             commentKind,
		CommentID:               commentID,
		ParentCommentID:         parentCommentID,
		ViewerReaction:          "none",
		ActorSubAccountID:       seed.ActorID,
		ActorDisplayName:        actorName,
		ActorAvatarURL:          actorAvatar,
		CounterpartSubAccountID: post.AuthorPersonaID,
		CounterpartDisplayName:  targetName,
		CounterpartAvatarURL:    strings.TrimSpace(post.AuthorAvatarURLSnapshot),
		TargetSubAccountID:      post.AuthorPersonaID,
		TargetContentID:         post.ID,
		TargetContentType:       post.ContentType,
		TargetContentSummary:    summary,
		TargetKind:              "record",
		TargetAvailability:      availability,
		DisplaySubAccountID:     displayID,
		DisplayName:             displayName,
		DisplayAvatarURL:        displayAvatar,
		DisplayUserRouteID:      "userProfile",
		PrimaryText:             activityPrimaryText(seed, direction, commentKind),
		ContextText:             contextText,
		PreviewMediaKind:        previewMediaKind(post, previewUnavailable),
		PreviewImageURL:         previewImage,
		PreviewText:             previewText,
		PreviewUnavailable:      previewUnavailable,
		PreviewObjectID:         post.ID,
		PreviewRouteID:          previewRoute,
		OutboundShareEventID:    seed.OutboundShareEventID,
		FilterKeys:              []string{activityFilterKey(seed.ActivityType)},
		CreatedAt:               seed.OccurredAt.UTC(),
		OccurredAt:              seed.OccurredAt.UTC(),
	}
}

func activityPrimaryText(seed projectionSeed, direction, commentKind string) string {
	switch seed.ActivityType {
	case activitymodel.TypeLike:
		if direction == activitymodel.DirectionSent {
			return "你点赞了TA的记录"
		}
		return "点赞了你的记录"
	case activitymodel.TypeShare:
		if direction == activitymodel.DirectionSent {
			return "你转发了TA的记录"
		}
		return "转发了你的记录"
	case activitymodel.TypeComment:
		content := ""
		if seed.Comment != nil {
			content = strings.TrimSpace(seed.Comment.Content)
		}
		if direction == activitymodel.DirectionSent {
			if commentKind == "reply" {
				return withContent("你回复了TA", content)
			}
			return withContent("你评论了TA的记录", content)
		}
		if commentKind == "reply" {
			return withContent("回复了你", content)
		}
		return withContent("评论了你的记录", content)
	default:
		return ""
	}
}

func withContent(prefix, content string) string {
	if content == "" {
		return prefix
	}
	return prefix + "：" + content
}

func activityFilterKey(activityType string) string {
	switch activityType {
	case activitymodel.TypeLike:
		return "likes"
	case activitymodel.TypeComment:
		return "comments"
	case activitymodel.TypeShare:
		return "shares"
	default:
		return ""
	}
}

func postSummary(post activityports.PostSlice) string {
	for _, candidate := range []string{post.Summary, post.Title, post.Body} {
		value := strings.TrimSpace(candidate)
		if value == "" {
			continue
		}
		runes := []rune(value)
		if len(runes) > 60 {
			return string(runes[:60])
		}
		return value
	}
	return ""
}

func postAvailability(post activityports.PostSlice) string {
	if !post.DeletedAt.IsZero() || strings.EqualFold(post.Status, "deleted") ||
		strings.EqualFold(post.Status, "removed") {
		return "deleted"
	}
	if strings.EqualFold(post.Visibility, "private") {
		return "private"
	}
	if !strings.EqualFold(post.Status, "published") {
		return "reviewing"
	}
	return "active"
}

func previewMediaKind(post activityports.PostSlice, unavailable bool) string {
	if unavailable {
		return "none"
	}
	switch strings.ToLower(strings.TrimSpace(post.ContentType)) {
	case "video":
		return "video"
	case "image", "photo":
		return "image"
	case "article":
		return "article"
	default:
		return "text"
	}
}

func decodeStrict(payload []byte, target any) error {
	decoder := json.NewDecoder(bytes.NewReader(payload))
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(target); err != nil {
		return err
	}
	var trailing any
	if err := decoder.Decode(&trailing); err != io.EOF {
		return fmt.Errorf("payload contains trailing JSON")
	}
	return nil
}

var (
	_ reactionports.OutboxPublisher = (*ReactionProjector)(nil)
	_ commentports.OutboxPublisher  = (*CommentProjector)(nil)
	_ shareports.OutboxPublisher    = (*OutboundShareProjector)(nil)
	_ postports.OutboxPublisher     = (*PostTargetProjector)(nil)
	_ readfactports.OutboxPublisher = (*ReadFactProjector)(nil)
)
