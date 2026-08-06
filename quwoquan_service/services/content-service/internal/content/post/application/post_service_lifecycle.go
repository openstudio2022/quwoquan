package post

import (
	"context"
	rterr "quwoquan_service/runtime/errors"
	"quwoquan_service/services/content-service/generated/content/post"
	contentgenerated "quwoquan_service/services/content-service/generated/content/post"
	postmodel "quwoquan_service/services/content-service/generated/content/post/contract/model"
	postports "quwoquan_service/services/content-service/internal/content/post/domain/ports"
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
		return nil, contentgenerated.AppErrorFromPostNotFound("post not found")
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
	// 所有会改变候选资格或索引字段的 Post 生命周期事实都携带同一份完整
	// canonical projection snapshot。消费者不得把缺失字段解释成空值，否则一次
	// visibility/assistant setting 更新会静默抹掉 entity/tag 等推荐与搜索索引。
	eventPayload := projectionPayloadForPost(post)
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
		return nil, contentgenerated.AppErrorFromStorageWriteFailed("update post settings: " + err.Error())
	}
	return post, nil
}

func (s *PostService) PromotePostToWork(ctx context.Context, postID, userID string, payload map[string]any) (*postmodel.Post, error) {
	post, ok := s.store.FindByID(ctx, strings.TrimSpace(postID))
	if !ok {
		return nil, contentgenerated.AppErrorFromPostNotFound("post not found")
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
		decoded, err := decodePostMediaItems(mediaItems)
		if err != nil {
			return nil, rterr.NewInvalidArgument(
				rterr.ModuleContent,
				"媒体列表格式不合法",
				err.Error(),
			)
		}
		post.MediaItems = decoded
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
		decoded, err := decodePostArticleAssetManifest(articleAssetManifest)
		if err != nil {
			return nil, rterr.NewInvalidArgument(
				rterr.ModuleContent,
				"文章素材清单格式不合法",
				err.Error(),
			)
		}
		post.ArticleAssetManifest = decoded
	}
	if articleRenderProfile, exists := payload["articleRenderProfile"]; exists {
		decoded, err := decodePostArticleRenderProfile(articleRenderProfile)
		if err != nil {
			return nil, rterr.NewInvalidArgument(
				rterr.ModuleContent,
				"文章渲染配置格式不合法",
				err.Error(),
			)
		}
		post.ArticleRenderProfile = decoded
	}
	if err := NormalizePostObjectAnchors(post, payload); err != nil {
		return nil, err
	}
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
		return nil, contentgenerated.AppErrorFromStorageWriteFailed("promote post to work: " + err.Error())
	}
	return post, nil
}

type PostDeletionReceipt struct {
	PostID   string `json:"postId"`
	Status   string `json:"status"`
	Replayed bool   `json:"replayed"`
}

func (s *PostService) DeletePost(ctx context.Context, postID, userID string) (PostDeletionReceipt, error) {
	post, ok := s.store.FindByID(ctx, strings.TrimSpace(postID))
	if !ok {
		return PostDeletionReceipt{}, contentgenerated.AppErrorFromPostNotFound("post not found")
	}
	if err := requirePostOwner(post, userID, "删除内容"); err != nil {
		return PostDeletionReceipt{}, err
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
	post, replayed, err := s.commitPostCommandWithResult(
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
		return PostDeletionReceipt{}, contentgenerated.AppErrorFromStorageWriteFailed("delete post: " + err.Error())
	}
	return PostDeletionReceipt{
		PostID:   post.ID,
		Status:   post.Status,
		Replayed: replayed,
	}, nil
}

// deletedPostTombstoneRetention 是删除保留期（410 语义窗口）。到期后 TTL 清理，
// 读取回落 post_not_found（404）。
const deletedPostTombstoneRetention = 30 * 24 * time.Hour
