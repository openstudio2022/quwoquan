package post

import (
	"context"
	"errors"
	"fmt"
	"go.opentelemetry.io/otel/attribute"
	rterr "quwoquan_service/runtime/errors"
	rtobs "quwoquan_service/runtime/observability"
	rtrec "quwoquan_service/runtime/recommendation"
	postmodel "quwoquan_service/services/content-service/internal/domain/post/model"
	"quwoquan_service/services/content-service/internal/generated"
	"strings"
	"time"
)

func requirePostOwner(
	post *postmodel.Post,
	actorPersonaID string,
	action string,
) error {
	if post == nil {
		return generated.AppErrorFromPostNotFound("post aggregate missing for " + action)
	}
	actorPersonaID = strings.TrimSpace(actorPersonaID)
	if actorPersonaID == "" {
		return generated.AppErrorFromUnauthorized(
			"verified persona actor missing for " + action,
		)
	}
	if strings.TrimSpace(post.AuthorId) != actorPersonaID {
		return generated.AppErrorFromForbiddenEdit(
			"persona owner mismatch for " + action,
		)
	}
	return nil
}

func (s *PostService) CreatePost(ctx context.Context, payload map[string]any) (result *postmodel.Post, err error) {
	ctx, span := rtobs.StartBusinessSpan(ctx, "content.CreatePost",
		attribute.String("content.type", strings.TrimSpace(asString(payload["contentType"]))))
	defer func() { rtobs.EndSpan(span, err) }()

	contentType := strings.TrimSpace(asString(payload["contentType"]))
	if contentType == "" {
		return nil, rterr.NewInvalidArgument(rterr.ModuleContent, "contentType 必填", "missing contentType")
	}
	if _, ok := generated.AllowedContentTypes[contentType]; !ok {
		return nil, rterr.NewAppError(
			rterr.NewCode(rterr.ModuleContent, rterr.KindUser, "invalid_content_type"),
			"contentType 不支持",
			"unsupported contentType",
		)
	}
	now := time.Now().UTC()
	contentIdentity := normalizeContentIdentity(
		contentType,
		strings.TrimSpace(asString(payload["contentIdentity"])),
	)
	assistantUsePolicy := normalizeAssistantUsePolicy(
		strings.TrimSpace(asString(payload["assistantUsePolicy"])),
	)
	post := &postmodel.Post{
		ID:       fmt.Sprintf("post_%d", now.UnixNano()),
		AuthorId: strings.TrimSpace(asString(payload["authorId"])),
		PersonaContextVersion: asInt64Flexible(
			payload["personaContextVersion"],
		),
		AuthorDisplayNameSnapshot: strings.TrimSpace(
			asString(payload["authorDisplayNameSnapshot"]),
		),
		AuthorAvatarUrlSnapshot: strings.TrimSpace(
			asString(payload["authorAvatarUrlSnapshot"]),
		),
		ContentType:         contentType,
		ContentIdentity:     contentIdentity,
		Title:               strings.TrimSpace(asString(payload["title"])),
		Body:                strings.TrimSpace(asString(payload["body"])),
		TagRefs:             asStringSlice(payload["tagRefs"]),
		EntityRefs:          asStringSlice(payload["entityRefs"]),
		SemanticMentions:    payload["semanticMentions"],
		MediaUrls:           asStringSlice(payload["mediaUrls"]),
		MediaItems:          payload["mediaItems"],
		CoverUrl:            strings.TrimSpace(asString(payload["coverUrl"])),
		ThumbnailUrl:        strings.TrimSpace(asString(payload["thumbnailUrl"])),
		VideoUrl:            strings.TrimSpace(asString(payload["videoUrl"])),
		CoverStrategy:       strings.TrimSpace(asString(payload["coverStrategy"])),
		CoverFrameTimeMs:    asInt64Flexible(payload["coverFrameTimeMs"]),
		Location:            parseGeoPoint(payload["location"]),
		LocationName:        strings.TrimSpace(asString(payload["locationName"])),
		Visibility:          normalizeVisibility(asString(payload["visibility"])),
		AssistantUsePolicy:  assistantUsePolicy,
		SourcePostId:        strings.TrimSpace(asString(payload["sourcePostId"])),
		SourceType:          defaultString(strings.TrimSpace(asString(payload["sourceType"])), "original"),
		Summary:             strings.TrimSpace(asString(payload["summary"])),
		IllustrationAssetId: strings.TrimSpace(asString(payload["illustrationAssetId"])),
		PublishLocation:     asMap(payload["publishLocation"]),
		DeviceInfo:          asMap(payload["deviceInfo"]),
		ArticleMarkdown:     strings.TrimSpace(asString(payload["articleMarkdown"])),
		ArticleMarkdownVersion: defaultString(
			strings.TrimSpace(asString(payload["articleMarkdownVersion"])),
			"qwq-rich-md/1",
		),
		ArticleAssetManifest: asMap(payload["articleAssetManifest"]),
		ArticleRenderProfile: asMap(payload["articleRenderProfile"]),
		ArticleTemplate:      strings.TrimSpace(asString(payload["articleTemplate"])),
		ArticleFontPreset:    strings.TrimSpace(asString(payload["articleFontPreset"])),
		Status:               "draft",
		ModerationStatus:     "pending",
		CreatedAt:            now,
		UpdatedAt:            now,
	}
	normalizePostObjectAnchors(post, payload)
	if err := applySemanticMentionPayload(post, payload); err != nil {
		return nil, err
	}
	if post.AuthorId == "" {
		return nil, rterr.NewInvalidArgument(
			rterr.ModuleContent,
			"authorId 不能为空",
			"missing authorId/subAccountId",
		)
	}
	if post.SourceType == "" {
		post.SourceType = "original"
	}
	s.syncArticleMarkdownSnapshot(post)
	normalizeVideoCoverContract(post)
	if err := validateCreatePostPayload(post); err != nil {
		return nil, err
	}
	post.ContentDigest = postContentDigest(post)
	post, err = s.commitPostCommand(
		ctx,
		post,
		0,
		"CreatePost",
		payload,
		"PostCreated",
		projectionPayloadForPost(post),
		now,
	)
	if err != nil {
		var appError *rterr.AppError
		if errors.As(err, &appError) {
			return nil, appError
		}
		return nil, generated.AppErrorFromStorageWriteFailed(err.Error())
	}
	return post, nil
}

func (s *PostService) UpdatePost(
	ctx context.Context,
	id string,
	actorPersonaID string,
	payload map[string]any,
) (*postmodel.Post, error) {
	post, ok := s.store.FindByID(ctx, strings.TrimSpace(id))
	if !ok {
		return nil, rterr.NewAppError(
			rterr.NewCode(rterr.ModuleContent, rterr.KindUser, "not_found"),
			"内容不存在",
			"post not found",
		)
	}
	if err := requirePostOwner(post, actorPersonaID, "更新内容"); err != nil {
		return nil, err
	}
	if strings.EqualFold(strings.TrimSpace(post.Status), "published") {
		return nil, rterr.NewAppError(
			rterr.NewCode(rterr.ModuleContent, rterr.KindUser, "conflict"),
			"内容发布后不可修改",
			"post immutable after publish",
		)
	}
	if title, exists := payload["title"]; exists {
		post.Title = strings.TrimSpace(asString(title))
	}
	if contentType, exists := payload["contentType"]; exists {
		post.ContentType = strings.TrimSpace(asString(contentType))
	}
	if contentIdentity, exists := payload["contentIdentity"]; exists {
		post.ContentIdentity = normalizeContentIdentity(
			post.ContentType,
			strings.TrimSpace(asString(contentIdentity)),
		)
	}
	if body, exists := payload["body"]; exists {
		post.Body = strings.TrimSpace(asString(body))
	}
	if summary, exists := payload["summary"]; exists {
		post.Summary = strings.TrimSpace(asString(summary))
	}
	if tags, exists := payload["tagRefs"]; exists {
		post.TagRefs = asStringSlice(tags)
	}
	if media, exists := payload["mediaUrls"]; exists {
		post.MediaUrls = asStringSlice(media)
	}
	if mediaItems, exists := payload["mediaItems"]; exists {
		post.MediaItems = mediaItems
	}
	if cover, exists := payload["coverUrl"]; exists {
		post.CoverUrl = strings.TrimSpace(asString(cover))
	}
	if thumbnail, exists := payload["thumbnailUrl"]; exists {
		post.ThumbnailUrl = strings.TrimSpace(asString(thumbnail))
	}
	if video, exists := payload["videoUrl"]; exists {
		post.VideoUrl = strings.TrimSpace(asString(video))
	}
	if coverStrategy, exists := payload["coverStrategy"]; exists {
		post.CoverStrategy = strings.TrimSpace(asString(coverStrategy))
	}
	if coverFrameTimeMs, exists := payload["coverFrameTimeMs"]; exists {
		post.CoverFrameTimeMs = asInt64Flexible(coverFrameTimeMs)
	}
	if loc, exists := payload["location"]; exists {
		post.Location = parseGeoPoint(loc)
	}
	if locName, exists := payload["locationName"]; exists {
		post.LocationName = strings.TrimSpace(asString(locName))
	}
	if visibility, exists := payload["visibility"]; exists {
		post.Visibility = normalizeVisibility(asString(visibility))
	}
	if assistantUsePolicy, exists := payload["assistantUsePolicy"]; exists {
		post.AssistantUsePolicy = normalizeAssistantUsePolicy(
			strings.TrimSpace(asString(assistantUsePolicy)),
		)
	}
	if illustrationAssetID, exists := payload["illustrationAssetId"]; exists {
		post.IllustrationAssetId = strings.TrimSpace(asString(illustrationAssetID))
	}
	if articleMarkdown, exists := payload["articleMarkdown"]; exists {
		post.ArticleMarkdown = strings.TrimSpace(asString(articleMarkdown))
	}
	if articleMarkdownVersion, exists := payload["articleMarkdownVersion"]; exists {
		post.ArticleMarkdownVersion = defaultString(
			strings.TrimSpace(asString(articleMarkdownVersion)),
			"qwq-rich-md/1",
		)
	}
	if articleAssetManifest, exists := payload["articleAssetManifest"]; exists {
		post.ArticleAssetManifest = asMap(articleAssetManifest)
	}
	if articleRenderProfile, exists := payload["articleRenderProfile"]; exists {
		post.ArticleRenderProfile = asMap(articleRenderProfile)
	}
	normalizePostObjectAnchors(post, payload)
	if err := applySemanticMentionPayload(post, payload); err != nil {
		return nil, err
	}
	now := time.Now().UTC()
	expectedVersion := post.Version
	previousDigest := post.ContentDigest
	post.UpdatedAt = now
	s.syncArticleMarkdownSnapshot(post)
	normalizeVideoCoverContract(post)
	if err := validateCreatePostPayload(post); err != nil {
		return nil, err
	}
	post.ContentDigest = postContentDigest(post)
	if post.ContentDigest != previousDigest {
		post.ModerationStatus = "pending"
	}
	post, err := s.commitPostCommand(
		ctx,
		post,
		expectedVersion,
		"UpdatePost",
		payload,
		"PostUpdated",
		projectionPayloadForPost(post),
		now,
	)
	if err != nil {
		return nil, rterr.NewAppError(
			rterr.NewCode(rterr.ModuleContent, rterr.KindSystem, "update_failed"),
			"更新内容失败",
			err.Error(),
		)
	}
	return post, nil
}

func (s *PostService) PublishPost(
	ctx context.Context,
	postID string,
	actorPersonaID string,
	payload map[string]any,
) (result *postmodel.Post, err error) {
	ctx, span := rtobs.StartBusinessSpan(ctx, "content.PublishPost",
		attribute.String("post.id", postID))
	defer func() { rtobs.EndSpan(span, err) }()

	post, ok := s.store.FindByID(ctx, strings.TrimSpace(postID))
	if !ok {
		return nil, rterr.NewAppError(
			rterr.NewCode(rterr.ModuleContent, rterr.KindUser, "not_found"),
			"内容不存在",
			"post not found",
		)
	}
	if err := requirePostOwner(post, actorPersonaID, "发布内容"); err != nil {
		return nil, err
	}
	if strings.EqualFold(post.Status, "deleted") {
		return nil, rterr.NewAppError(
			rterr.NewCode(rterr.ModuleContent, rterr.KindUser, "conflict"),
			"内容已删除",
			"post deleted",
		)
	}
	if err := applyPostSettingsPayload(post, payload); err != nil {
		return nil, err
	}
	now := time.Now().UTC()
	expectedVersion := post.Version
	post.Status = "published"
	if post.PublishedAt.IsZero() {
		post.PublishedAt = now
	}
	post.UpdatedAt = now
	normalizeVideoCoverContract(post)
	if err := validateCreatePostPayload(post); err != nil {
		return nil, err
	}
	post.ContentDigest = postContentDigest(post)
	eventPayload := projectionPayloadForPost(post)
	post, err = s.commitPostCommand(
		ctx,
		post,
		expectedVersion,
		"PublishPost",
		payload,
		"PostPublished",
		eventPayload,
		now,
	)
	if err != nil {
		return nil, rterr.NewAppError(
			rterr.NewCode(rterr.ModuleContent, rterr.KindSystem, "internal_error"),
			"发布失败",
			err.Error(),
		)
	}
	if s.signaler != nil {
		tags := behaviorTagsFromPost(post)
		_ = s.signaler.ProcessSignal(ctx, rtrec.BehaviorSignal{
			UserID:    post.AuthorId,
			ContentID: post.ID,
			Action:    "impression",
			Tags:      tags,
			Timestamp: now,
		})
	}
	return post, nil
}

func promoteSettingsPayload(payload map[string]any) map[string]any {
	settings := map[string]any{}
	for _, key := range []string{
		"primaryHomepageId",
		"primaryHomepageType",
		"primaryHomepageSnapshot",
		"visibility",
		"assistantUsePolicy",
	} {
		if value, exists := payload[key]; exists {
			settings[key] = value
		}
	}
	return settings
}

func (s *PostService) UpdatePostSettings(ctx context.Context, postID, userID string, payload map[string]any) (*postmodel.Post, error) {
	post, ok := s.store.FindByID(ctx, strings.TrimSpace(postID))
	if !ok {
		return nil, rterr.NewAppError(
			rterr.NewCode(rterr.ModuleContent, rterr.KindUser, "not_found"),
			"内容不存在",
			"post not found",
		)
	}
	if err := requirePostOwner(post, userID, "更新内容设置"); err != nil {
		return nil, err
	}
	expectedVersion := post.Version
	if err := applyPostSettingsPayload(post, payload); err != nil {
		return nil, err
	}
	now := time.Now().UTC()
	post.UpdatedAt = now
	eventPayload := map[string]any{
		"_id":                post.ID,
		"authorId":           post.AuthorId,
		"contentType":        post.ContentType,
		"contentIdentity":    post.ContentIdentity,
		"status":             post.Status,
		"visibility":         post.Visibility,
		"assistantUsePolicy": post.AssistantUsePolicy,
		"publishedAt":        formatTimePtr(post.PublishedAt),
		"title":              post.Title,
		"tagRefs":            asStringSlice(post.TagRefs),
		"coverUrl":           post.CoverUrl,
	}
	post, err := s.commitPostCommand(
		ctx,
		post,
		expectedVersion,
		"UpdatePostSettings",
		payload,
		"PostSettingsUpdated",
		eventPayload,
		now,
	)
	if err != nil {
		return nil, rterr.NewAppError(
			rterr.NewCode(rterr.ModuleContent, rterr.KindSystem, "update_failed"),
			"更新内容设置失败",
			err.Error(),
		)
	}
	return post, nil
}

func (s *PostService) PromotePostToWork(ctx context.Context, postID, userID string, payload map[string]any) (*postmodel.Post, error) {
	post, ok := s.store.FindByID(ctx, strings.TrimSpace(postID))
	if !ok {
		return nil, rterr.NewAppError(
			rterr.NewCode(rterr.ModuleContent, rterr.KindUser, "not_found"),
			"内容不存在",
			"post not found",
		)
	}
	if err := requirePostOwner(post, userID, "升级内容"); err != nil {
		return nil, err
	}
	expectedVersion := post.Version
	post.ContentIdentity = "work"
	if contentType := strings.TrimSpace(asString(payload["contentType"])); contentType != "" {
		post.ContentType = contentType
	} else {
		post.ContentType = recommendedPromotedContentType(post)
	}
	if title, exists := payload["title"]; exists {
		post.Title = strings.TrimSpace(asString(title))
	}
	if summary, exists := payload["summary"]; exists {
		post.Summary = strings.TrimSpace(asString(summary))
	}
	if tags, exists := payload["tagRefs"]; exists {
		post.TagRefs = asStringSlice(tags)
	}
	if entityRefs, exists := payload["entityRefs"]; exists {
		post.EntityRefs = asStringSlice(entityRefs)
	}
	if coverURL, exists := payload["coverUrl"]; exists {
		post.CoverUrl = strings.TrimSpace(asString(coverURL))
	}
	if thumbnailURL, exists := payload["thumbnailUrl"]; exists {
		post.ThumbnailUrl = strings.TrimSpace(asString(thumbnailURL))
	}
	if videoURL, exists := payload["videoUrl"]; exists {
		post.VideoUrl = strings.TrimSpace(asString(videoURL))
	}
	if mediaItems, exists := payload["mediaItems"]; exists {
		post.MediaItems = mediaItems
	}
	if coverStrategy, exists := payload["coverStrategy"]; exists {
		post.CoverStrategy = strings.TrimSpace(asString(coverStrategy))
	}
	if coverFrameTimeMs, exists := payload["coverFrameTimeMs"]; exists {
		post.CoverFrameTimeMs = asInt64Flexible(coverFrameTimeMs)
	}
	if articleMarkdown, exists := payload["articleMarkdown"]; exists {
		post.ArticleMarkdown = strings.TrimSpace(asString(articleMarkdown))
	}
	if articleMarkdownVersion, exists := payload["articleMarkdownVersion"]; exists {
		post.ArticleMarkdownVersion = defaultString(
			strings.TrimSpace(asString(articleMarkdownVersion)),
			"qwq-rich-md/1",
		)
	}
	if articleAssetManifest, exists := payload["articleAssetManifest"]; exists {
		post.ArticleAssetManifest = asMap(articleAssetManifest)
	}
	if articleRenderProfile, exists := payload["articleRenderProfile"]; exists {
		post.ArticleRenderProfile = asMap(articleRenderProfile)
	}
	normalizePostObjectAnchors(post, payload)
	if err := applySemanticMentionPayload(post, payload); err != nil {
		return nil, err
	}
	if err := applyPostSettingsPayload(post, promoteSettingsPayload(payload)); err != nil {
		return nil, err
	}
	s.syncArticleMarkdownSnapshot(post)
	normalizeVideoCoverContract(post)
	now := time.Now().UTC()
	post.UpdatedAt = now
	post.ContentDigest = postContentDigest(post)
	eventPayload := projectionPayloadForPost(post)
	post, err := s.commitPostCommand(
		ctx,
		post,
		expectedVersion,
		"PromotePostToWork",
		payload,
		"PostPromotedToWork",
		eventPayload,
		now,
	)
	if err != nil {
		return nil, rterr.NewAppError(
			rterr.NewCode(rterr.ModuleContent, rterr.KindSystem, "update_failed"),
			"升级作品失败",
			err.Error(),
		)
	}
	return post, nil
}

func (s *PostService) DeletePost(ctx context.Context, postID, userID string) error {
	post, ok := s.store.FindByID(ctx, strings.TrimSpace(postID))
	if !ok {
		return rterr.NewAppError(
			rterr.NewCode(rterr.ModuleContent, rterr.KindUser, "not_found"),
			"内容不存在",
			"post not found",
		)
	}
	if err := requirePostOwner(post, userID, "删除内容"); err != nil {
		return err
	}
	statusBeforeDelete := post.Status
	expectedVersion := post.Version
	now := time.Now().UTC()
	post.Status = "deleted"
	post.DeletedAt = now
	post.UpdatedAt = now
	eventPayload := map[string]any{
		"_id":             post.ID,
		"authorId":        post.AuthorId,
		"contentType":     post.ContentType,
		"contentIdentity": post.ContentIdentity,
		"status":          statusBeforeDelete,
		"deletedAt":       post.DeletedAt.Format(time.RFC3339),
	}
	post, err := s.commitPostCommand(
		ctx,
		post,
		expectedVersion,
		"DeletePost",
		map[string]any{"postId": post.ID, "actorId": userID},
		"PostDeleted",
		eventPayload,
		now,
	)
	if err != nil {
		return rterr.NewAppError(
			rterr.NewCode(rterr.ModuleContent, rterr.KindSystem, "delete_failed"),
			"删除内容失败",
			err.Error(),
		)
	}
	s.mu.Lock()
	s.tombstones[post.ID] = now
	s.mu.Unlock()
	return nil
}
