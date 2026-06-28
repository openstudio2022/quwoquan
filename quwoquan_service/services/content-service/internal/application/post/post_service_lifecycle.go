package post

import (
	"context"
	"fmt"
	"go.opentelemetry.io/otel/attribute"
	rterr "quwoquan_service/runtime/errors"
	rtobs "quwoquan_service/runtime/observability"
	rtrec "quwoquan_service/runtime/recommendation"
	"quwoquan_service/runtime/repository"
	postmodel "quwoquan_service/services/content-service/internal/domain/post/model"
	"quwoquan_service/services/content-service/internal/generated"
	"strings"
	"time"
)

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
		CircleId:            strings.TrimSpace(asString(payload["circleId"])),
		CircleIds:           asStringSlice(payload["circleIds"]),
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
	if err := s.store.Create(ctx, post); err != nil {
		return nil, rterr.NewAppError(
			rterr.NewCode(rterr.ModuleContent, rterr.KindSystem, "create_failed"),
			"创建内容失败",
			err.Error(),
		)
	}
	s.mu.Lock()
	if circles := asStringSlice(post.CircleIds); len(circles) > 0 {
		if _, ok := s.distributions[post.ID]; !ok {
			s.distributions[post.ID] = map[string]bool{}
		}
		for _, circleID := range circles {
			if circleID != "" {
				s.distributions[post.ID][circleID] = true
			}
		}
	}
	s.mu.Unlock()

	// Publish PostCreated domain event for downstream consumers.
	if s.publisher != nil {
		_ = s.publisher.Publish(ctx, repository.DomainEvent{
			Type:          "PostCreated",
			AggregateType: "Post",
			AggregateID:   post.ID,
			Payload: map[string]any{
				"authorId":           post.AuthorId,
				"contentType":        post.ContentType,
				"contentIdentity":    post.ContentIdentity,
				"status":             post.Status,
				"visibility":         post.Visibility,
				"circleIds":          asStringSlice(post.CircleIds),
				"assistantUsePolicy": post.AssistantUsePolicy,
			},
			OccurredAt: now.Format(time.RFC3339),
		})
	}

	// Synchronous projection for DiscoveryFeed read model.
	s.projectPostEvent(ctx, "PostCreated", post, projectionPayloadForPost(post), now)

	return post, nil
}

func (s *PostService) UpdatePost(ctx context.Context, id string, payload map[string]any) (*postmodel.Post, error) {
	post, ok := s.store.FindByID(ctx, strings.TrimSpace(id))
	if !ok {
		return nil, rterr.NewAppError(
			rterr.NewCode(rterr.ModuleContent, rterr.KindUser, "not_found"),
			"内容不存在",
			"post not found",
		)
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
	if circles, exists := payload["circleIds"]; exists {
		post.CircleIds = asStringSlice(circles)
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
	post.UpdatedAt = time.Now().UTC()
	s.syncArticleMarkdownSnapshot(post)
	normalizeVideoCoverContract(post)
	if err := validateCreatePostPayload(post); err != nil {
		return nil, err
	}
	if updated := s.store.Update(ctx, post.ID, post); !updated {
		return nil, rterr.NewAppError(
			rterr.NewCode(rterr.ModuleContent, rterr.KindSystem, "update_failed"),
			"更新内容失败",
			"post disappeared while updating",
		)
	}
	return post, nil
}

func (s *PostService) PublishPost(ctx context.Context, postID string, payload map[string]any) (result *postmodel.Post, err error) {
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
	post.Status = "published"
	if post.PublishedAt.IsZero() {
		post.PublishedAt = now
	}
	post.UpdatedAt = now
	normalizeVideoCoverContract(post)
	if err := validateCreatePostPayload(post); err != nil {
		return nil, err
	}
	if !s.store.Update(ctx, post.ID, post) {
		return nil, rterr.NewAppError(
			rterr.NewCode(rterr.ModuleContent, rterr.KindSystem, "internal_error"),
			"发布失败",
			"update failed",
		)
	}
	s.syncDistributionsFromPost(post)
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
	eventPayload := projectionPayloadForPost(post)
	s.publishPostEvent(ctx, "PostPublished", post, eventPayload, now)
	s.projectPostEvent(ctx, "PostPublished", post, eventPayload, now)
	return post, nil
}

func promoteSettingsPayload(payload map[string]any) map[string]any {
	settings := map[string]any{}
	for _, key := range []string{
		"primaryHomepageId",
		"primaryHomepageType",
		"primaryHomepageSnapshot",
		"visibility",
		"circleIds",
		"groupId",
		"nodeId",
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
	if post.AuthorId != "" && userID != "" && post.AuthorId != userID {
		return nil, rterr.NewAppError(
			rterr.NewCode(rterr.ModuleContent, rterr.KindUser, "forbidden"),
			"无权更新内容设置",
			"author mismatch",
		)
	}
	previousCircleIDs := asStringSlice(post.CircleIds)
	if err := applyPostSettingsPayload(post, payload); err != nil {
		return nil, err
	}
	addedCircleIDs, removedCircleIDs := diffCircleIDs(previousCircleIDs, asStringSlice(post.CircleIds))
	now := time.Now().UTC()
	post.UpdatedAt = now
	if !s.store.Update(ctx, post.ID, post) {
		return nil, rterr.NewAppError(
			rterr.NewCode(rterr.ModuleContent, rterr.KindSystem, "update_failed"),
			"更新内容设置失败",
			"post disappeared while updating settings",
		)
	}
	s.syncDistributionsFromPost(post)
	s.publishPostEvent(ctx, "PostSettingsUpdated", post, map[string]any{
		"_id":                post.ID,
		"authorId":           post.AuthorId,
		"contentType":        post.ContentType,
		"contentIdentity":    post.ContentIdentity,
		"status":             post.Status,
		"visibility":         post.Visibility,
		"circleIds":          asStringSlice(post.CircleIds),
		"addedCircleIds":     addedCircleIDs,
		"removedCircleIds":   removedCircleIDs,
		"assistantUsePolicy": post.AssistantUsePolicy,
		"publishedAt":        formatTimePtr(post.PublishedAt),
		"title":              post.Title,
		"tagRefs":            asStringSlice(post.TagRefs),
		"coverUrl":           post.CoverUrl,
	}, now)
	s.projectPostEvent(ctx, "PostSettingsUpdated", post, map[string]any{
		"_id":                post.ID,
		"authorId":           post.AuthorId,
		"contentType":        post.ContentType,
		"contentIdentity":    post.ContentIdentity,
		"status":             post.Status,
		"visibility":         post.Visibility,
		"circleIds":          asStringSlice(post.CircleIds),
		"addedCircleIds":     addedCircleIDs,
		"removedCircleIds":   removedCircleIDs,
		"assistantUsePolicy": post.AssistantUsePolicy,
		"publishedAt":        formatTimePtr(post.PublishedAt),
		"title":              post.Title,
		"tagRefs":            asStringSlice(post.TagRefs),
		"coverUrl":           post.CoverUrl,
	}, now)
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
	if post.AuthorId != "" && userID != "" && post.AuthorId != userID {
		return nil, rterr.NewAppError(
			rterr.NewCode(rterr.ModuleContent, rterr.KindUser, "forbidden"),
			"无权升级该内容",
			"author mismatch",
		)
	}
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
	if !s.store.Update(ctx, post.ID, post) {
		return nil, rterr.NewAppError(
			rterr.NewCode(rterr.ModuleContent, rterr.KindSystem, "update_failed"),
			"升级作品失败",
			"post disappeared while promoting",
		)
	}
	s.syncDistributionsFromPost(post)
	eventPayload := projectionPayloadForPost(post)
	s.publishPostEvent(ctx, "PostPromotedToWork", post, eventPayload, now)
	s.projectPostEvent(ctx, "PostPromotedToWork", post, eventPayload, now)
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
	if userID != "" && post.AuthorId != "" && post.AuthorId != userID {
		return rterr.NewAppError(
			rterr.NewCode(rterr.ModuleContent, rterr.KindUser, "forbidden"),
			"无权删除此内容",
			"author mismatch",
		)
	}
	statusBeforeDelete := post.Status
	now := time.Now().UTC()
	post.Status = "deleted"
	post.DeletedAt = now
	post.UpdatedAt = now
	if !s.store.Update(ctx, post.ID, post) {
		return rterr.NewAppError(
			rterr.NewCode(rterr.ModuleContent, rterr.KindSystem, "delete_failed"),
			"删除内容失败",
			"post disappeared while deleting",
		)
	}
	s.mu.Lock()
	s.tombstones[post.ID] = now
	delete(s.distributions, post.ID)
	delete(s.reshares, post.ID)
	s.mu.Unlock()
	s.publishPostEvent(ctx, "PostDeleted", post, map[string]any{
		"_id":             post.ID,
		"authorId":        post.AuthorId,
		"contentType":     post.ContentType,
		"contentIdentity": post.ContentIdentity,
		"status":          statusBeforeDelete,
		"circleIds":       asStringSlice(post.CircleIds),
		"deletedAt":       post.DeletedAt.Format(time.RFC3339),
	}, now)
	s.projectPostEvent(ctx, "PostDeleted", post, map[string]any{
		"_id":             post.ID,
		"contentType":     post.ContentType,
		"contentIdentity": post.ContentIdentity,
		"status":          statusBeforeDelete,
		"circleIds":       asStringSlice(post.CircleIds),
		"deletedAt":       post.DeletedAt.Format(time.RFC3339),
	}, now)
	return nil
}

func (s *PostService) UpdatePostCircles(ctx context.Context, postID, userID string, add, remove []string) (map[string]any, error) {
	post, ok := s.store.FindByID(ctx, strings.TrimSpace(postID))
	if !ok {
		return nil, rterr.NewAppError(
			rterr.NewCode(rterr.ModuleContent, rterr.KindUser, "not_found"),
			"内容不存在",
			"post not found",
		)
	}
	if post.AuthorId != "" && userID != "" && post.AuthorId != userID {
		return nil, rterr.NewAppError(
			rterr.NewCode(rterr.ModuleContent, rterr.KindUser, "forbidden"),
			"无权修改圈子分发关系",
			"author mismatch",
		)
	}
	if !supportsCircleDistribution(post.Visibility) {
		return nil, rterr.NewInvalidArgument(
			rterr.ModuleContent,
			"发布到圈子前需设置为公开或圈内可见",
			"visibility must be public or circle_visible",
		)
	}
	s.mu.Lock()
	defer s.mu.Unlock()
	previousCircleIDs := asStringSlice(post.CircleIds)
	byPost, ok := s.distributions[post.ID]
	if !ok {
		byPost = map[string]bool{}
		s.distributions[post.ID] = byPost
	}
	for _, circleID := range add {
		if cid := strings.TrimSpace(circleID); cid != "" {
			byPost[cid] = true
		}
	}
	for _, circleID := range remove {
		delete(byPost, strings.TrimSpace(circleID))
	}
	active := make([]string, 0, len(byPost))
	for cid, on := range byPost {
		if on {
			active = append(active, cid)
		}
	}
	post.CircleIds = active
	addedCircleIDs, removedCircleIDs := diffCircleIDs(previousCircleIDs, active)
	now := time.Now().UTC()
	post.UpdatedAt = now
	_ = s.store.Update(ctx, post.ID, post)
	s.syncDistributionsFromPost(post)
	s.publishPostEvent(ctx, "PostSettingsUpdated", post, map[string]any{
		"_id":                post.ID,
		"authorId":           post.AuthorId,
		"contentType":        post.ContentType,
		"contentIdentity":    post.ContentIdentity,
		"status":             post.Status,
		"visibility":         post.Visibility,
		"circleIds":          asStringSlice(post.CircleIds),
		"addedCircleIds":     addedCircleIDs,
		"removedCircleIds":   removedCircleIDs,
		"assistantUsePolicy": post.AssistantUsePolicy,
		"publishedAt":        formatTimePtr(post.PublishedAt),
		"title":              post.Title,
		"tagRefs":            asStringSlice(post.TagRefs),
		"coverUrl":           post.CoverUrl,
	}, now)
	s.projectPostEvent(ctx, "PostSettingsUpdated", post, map[string]any{
		"_id":                post.ID,
		"authorId":           post.AuthorId,
		"contentType":        post.ContentType,
		"contentIdentity":    post.ContentIdentity,
		"status":             post.Status,
		"visibility":         post.Visibility,
		"circleIds":          asStringSlice(post.CircleIds),
		"addedCircleIds":     addedCircleIDs,
		"removedCircleIds":   removedCircleIDs,
		"assistantUsePolicy": post.AssistantUsePolicy,
		"publishedAt":        formatTimePtr(post.PublishedAt),
		"title":              post.Title,
		"tagRefs":            asStringSlice(post.TagRefs),
		"coverUrl":           post.CoverUrl,
	}, now)
	return map[string]any{
		"postId":    post.ID,
		"circleIds": active,
	}, nil
}
