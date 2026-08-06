package post

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"strings"
	"time"

	"go.opentelemetry.io/otel/attribute"

	"quwoquan_service/runtime/commandmeta"
	rterr "quwoquan_service/runtime/errors"
	rtobs "quwoquan_service/runtime/observability"
	contentgenerated "quwoquan_service/services/content-service/generated/content/post"
	postevent "quwoquan_service/services/content-service/generated/content/post/contract/event"
	postmodel "quwoquan_service/services/content-service/generated/content/post/contract/model"
	postports "quwoquan_service/services/content-service/internal/content/post/domain/ports"
)

// SubmitPostPublicationCommand 是 Post 的唯一公开创建命令。
// 编辑态只存在于端侧 LocalPostDraft，不进入远端聚合。
type SubmitPostPublicationCommand struct {
	PublishIntentID string
	LocalDraftID    string
	AuthorID        string
	Content         postmodel.Post
}

// PostPublicationReceipt 是一次性发布的稳定回执。
type PostPublicationReceipt struct {
	PublishIntentID  string    `json:"publishIntentId"`
	LocalDraftID     string    `json:"localDraftId"`
	PostID           string    `json:"postId"`
	State            string    `json:"state"`
	CommittedVersion int64     `json:"committedVersion"`
	AcceptedAt       time.Time `json:"acceptedAt"`
}

func (s *PostService) SubmitPostPublication(
	ctx context.Context,
	command SubmitPostPublicationCommand,
) (receipt PostPublicationReceipt, err error) {
	command.PublishIntentID = strings.TrimSpace(command.PublishIntentID)
	command.LocalDraftID = strings.TrimSpace(command.LocalDraftID)
	command.AuthorID = strings.TrimSpace(command.AuthorID)
	ctx, span := rtobs.StartBusinessSpan(
		ctx,
		"content.SubmitPostPublication",
		attribute.String("content.type", strings.TrimSpace(command.Content.ContentType)),
	)
	defer func() { rtobs.EndSpan(span, err) }()

	if err := validatePostPublicationIdentity(command); err != nil {
		return PostPublicationReceipt{}, err
	}
	if transportKey := commandmeta.IdempotencyKey(ctx); transportKey != command.PublishIntentID {
		return PostPublicationReceipt{}, rterr.NewInvalidArgument(
			rterr.ModuleContent,
			"发布意图标识不一致",
			"Idempotency-Key must equal publishIntentId",
		)
	}

	if existing, found := s.store.FindByPublicationIntent(
		ctx,
		command.AuthorID,
		command.PublishIntentID,
	); found {
		return publicationReceipt(existing, command.AuthorID, command.LocalDraftID)
	}
	postID := stablePublicationPostID(command.AuthorID, command.LocalDraftID)
	if existing, found := s.store.FindByID(ctx, postID); found {
		return publicationReceipt(existing, command.AuthorID, command.LocalDraftID)
	}
	post := command.Content
	// MongoDB persists timestamps with millisecond precision. Normalize before
	// the first response so a concurrent replay returns a byte-stable receipt.
	now := time.Now().UTC().Truncate(time.Millisecond)
	post.ID = postID
	post.Version = 0
	post.PublishIntentId = command.PublishIntentID
	post.LocalDraftId = command.LocalDraftID
	post.AuthorId = command.AuthorID
	post.ContentType = strings.TrimSpace(post.ContentType)
	post.ContentIdentity = normalizeContentIdentity(
		post.ContentType,
		strings.TrimSpace(post.ContentIdentity),
	)
	post.Visibility = normalizeVisibility(post.Visibility)
	post.AssistantUsePolicy = normalizeAssistantUsePolicy(post.AssistantUsePolicy)
	post.SourceType = defaultString(strings.TrimSpace(post.SourceType), "original")
	post.MarkdownDialect = defaultString(
		strings.TrimSpace(post.MarkdownDialect),
		"qwq-rich-md",
	)
	if err := rejectClientMediaDeliveryReferences(&post); err != nil {
		return PostPublicationReceipt{}, err
	}
	post.MediaUrls = nil
	post.VideoUrl = ""
	post.CoverUrl = ""
	post.ThumbnailUrl = ""
	post.CreatedAt = now
	post.UpdatedAt = now
	post.LastActiveAt = now

	if _, supported := contentgenerated.AllowedContentTypes[post.ContentType]; !supported {
		return PostPublicationReceipt{}, contentgenerated.AppErrorFromInvalidContentType(
			"unsupported contentType",
		)
	}
	if err := applySemanticMentionPayload(
		&post,
		map[string]any{
			"semanticMentions": post.SemanticMentions,
			"entityRefs":       post.EntityRefs,
			"tagRefs":          post.TagRefs,
		},
	); err != nil {
		return PostPublicationReceipt{}, err
	}
	s.syncArticleMarkdownSnapshot(&post)
	normalizeVideoCoverContract(&post)
	if err := validatePostPublicationLimits(&post); err != nil {
		return PostPublicationReceipt{}, err
	}
	if err := s.prepareMediaAssetsForPublication(
		ctx,
		&post,
		command.AuthorID,
		post.MediaAssetIds,
	); err != nil {
		return PostPublicationReceipt{}, err
	}
	if err := validatePostPublicationPayload(&post); err != nil {
		return PostPublicationReceipt{}, err
	}
	post.ContentDigest = postContentDigest(&post)
	admissionDecision, err := s.admitPostPublication(ctx, command, &post, now)
	if err != nil {
		return PostPublicationReceipt{}, err
	}
	eventType := postevent.PostPublished
	switch admissionDecision {
	case postports.PublicationSafetyAllow:
		post.Status = "published"
		post.ModerationStatus = "approved"
		post.PublishedAt = now
	case postports.PublicationSafetyReview:
		post.Status = "pending_review"
		post.ModerationStatus = "pending"
		eventType = postevent.PostSubmittedForReview
	default:
		return PostPublicationReceipt{}, contentgenerated.AppErrorFromRequiredDependencyUnavailable(
			"Post publication admission produced no terminal submission state",
		)
	}

	// 引用发布的 PostPublished payload 自包含源帖作者，"被引用"通知由
	// notification consumer 消费该字段，不设第二个 PostQuoted 事实。
	sourcePostAuthorID := ""
	if sourcePostID := strings.TrimSpace(post.SourcePostId); sourcePostID != "" {
		sourcePost, sourceFound := s.store.FindByID(ctx, sourcePostID)
		if !sourceFound {
			return PostPublicationReceipt{}, contentgenerated.AppErrorFromPostNotFound(
				"quoted source post does not exist",
			)
		}
		sourcePostAuthorID = strings.TrimSpace(sourcePost.AuthorId)
	}

	publicationKey := "post-publication:" + postID
	ctx = commandmeta.WithIdempotencyKey(ctx, publicationKey)
	publishedPayload := projectionPayloadForPost(&post)
	if sourcePostAuthorID != "" && eventType == postevent.PostPublished {
		publishedPayload["sourcePostId"] = strings.TrimSpace(post.SourcePostId)
		publishedPayload["sourcePostAuthorId"] = sourcePostAuthorID
	}
	committed, commitErr := s.commitPostCommand(
		ctx,
		&post,
		0,
		"SubmitPostPublication",
		struct {
			PostID string `json:"postId"`
		}{PostID: postID},
		eventType,
		publishedPayload,
		now,
	)
	if commitErr == nil {
		return publicationReceipt(committed, command.AuthorID, command.LocalDraftID)
	}

	// 同一草稿的并发或延迟重放只能有一个 CAS 胜者。失败方回读稳定
	// 聚合并返回原回执，绝不把内部 version 冲突暴露给发布用户。
	if existing, found := s.store.FindByPublicationIntent(
		ctx,
		command.AuthorID,
		command.PublishIntentID,
	); found {
		return publicationReceipt(existing, command.AuthorID, command.LocalDraftID)
	}
	if existing, found := s.store.FindByID(ctx, postID); found {
		return publicationReceipt(existing, command.AuthorID, command.LocalDraftID)
	}
	var appError *rterr.AppError
	if errors.As(commitErr, &appError) {
		return PostPublicationReceipt{}, appError
	}
	return PostPublicationReceipt{},
		contentgenerated.AppErrorFromStorageWriteFailed(commitErr.Error())
}

func validatePostPublicationIdentity(command SubmitPostPublicationCommand) error {
	if command.PublishIntentID == "" || command.LocalDraftID == "" ||
		command.AuthorID == "" {
		return rterr.NewInvalidArgument(
			rterr.ModuleContent,
			"发布意图、本地草稿和作者标识不能为空",
			"publishIntentId, localDraftId and authorId are required",
		)
	}
	if len(command.PublishIntentID) > 128 || len(command.LocalDraftID) > 128 {
		return rterr.NewInvalidArgument(
			rterr.ModuleContent,
			"发布标识格式不合法",
			"publication identity exceeds 128 bytes",
		)
	}
	return nil
}

func stablePublicationPostID(authorID, localDraftID string) string {
	digest := sha256.Sum256([]byte(
		strings.TrimSpace(authorID) + "\x00" + strings.TrimSpace(localDraftID),
	))
	return "post_" + hex.EncodeToString(digest[:16])
}

func publicationReceipt(
	post *postmodel.Post,
	authorID string,
	localDraftID string,
) (PostPublicationReceipt, error) {
	if post == nil || strings.TrimSpace(post.AuthorId) != strings.TrimSpace(authorID) ||
		strings.TrimSpace(post.LocalDraftId) != strings.TrimSpace(localDraftID) {
		return PostPublicationReceipt{}, contentgenerated.AppErrorFromIdempotencyConflict(
			"publication identity resolved to a different Post",
		)
	}
	return PostPublicationReceipt{
		PublishIntentID:  post.PublishIntentId,
		LocalDraftID:     post.LocalDraftId,
		PostID:           post.ID,
		State:            post.Status,
		CommittedVersion: post.Version,
		AcceptedAt:       publicationAcceptedAt(post),
	}, nil
}

func publicationAcceptedAt(post *postmodel.Post) time.Time {
	if post == nil {
		return time.Time{}
	}
	if !post.PublishedAt.IsZero() {
		return post.PublishedAt
	}
	return post.CreatedAt
}
