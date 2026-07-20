package post

import (
	"context"
	rterr "quwoquan_service/runtime/errors"
	postmodel "quwoquan_service/services/content-service/internal/domain/post/model"
	postports "quwoquan_service/services/content-service/internal/domain/post/ports"
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
		"postId":             post.ID,
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
	if markdownDialect, exists := payload["markdownDialect"]; exists {
		post.MarkdownDialect = defaultString(
			strings.TrimSpace(asString(markdownDialect)),
			"qwq-rich-md",
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
		"postId":          post.ID,
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
		func(commit *postports.Commit) {
			// 墓碑与聚合 state/receipt/outbox 同事务追加（content.DeletedPostTombstone；
			// _id=postId dedupe，保留期 TTL 由存储索引承载）。
			commit.Tombstone = &postports.PostDeletionTombstone{
				PostID:    post.ID,
				AuthorID:  post.AuthorId,
				Reason:    "author_delete",
				DeletedAt: now,
				ExpireAt:  now.Add(deletedPostTombstoneRetention),
			}
		},
	)
	if err != nil {
		return rterr.NewAppError(
			rterr.NewCode(rterr.ModuleContent, rterr.KindSystem, "delete_failed"),
			"删除内容失败",
			err.Error(),
		)
	}
	_ = post
	return nil
}

// deletedPostTombstoneRetention 是删除保留期（410 语义窗口）。到期后 TTL 清理，
// 读取回落 post_not_found（404）。
const deletedPostTombstoneRetention = 30 * 24 * time.Hour
