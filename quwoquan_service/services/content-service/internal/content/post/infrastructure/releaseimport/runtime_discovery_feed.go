package releaseimport

import (
	"context"
	"fmt"
	"strings"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	recinfra "quwoquan_service/services/content-service/internal/content/post/infrastructure/recommendation"
)

// ConditionProfileIndex 建立 entityRef→conditionProfile 映射，供发现流投影按主实体冗余条件画像。
func ConditionProfileIndex(entities []EntityDoc) map[string]map[string]any {
	idx := make(map[string]map[string]any, len(entities))
	for _, e := range entities {
		if len(e.ConditionProfile) > 0 {
			idx[e.EntityRef] = e.ConditionProfile
		}
	}
	return idx
}

type importedMediaSummary struct {
	MediaURLs        []string
	MediaItems       []bson.M
	MediaAssetIDs    []string
	CoverURL         string
	ThumbnailURL     string
	VideoURL         string
	CoverStrategy    string
	CoverFrameTimeMs int64
	DurationMs       int64
	Width            int64
	Height           int64
}

// MediaDeliveryAccessMode 契约 enum 值（_shared/types.yaml MediaDeliveryAccessMode）。
// research release 的媒体交付引用是相对私有 CAS key，App 必须换短签消费；
// commercial release 的交付引用是 canonical public slice。
const (
	MediaDeliveryAccessModePublic      = "public"
	MediaDeliveryAccessModeSignedGrant = "signed_grant"
)

// MediaDeliveryAccessModeForReleaseClass 把 release header 的 releaseClass 映射
// 为逐媒体 accessMode（DEC-033）：research → signed_grant、commercial → public。
// 其它/未声明类别返回空串作为 invalid sentinel；新 release importer 必须在写入前
// fail closed。该空串不得进入投影，也不得被消费端当成 public。
func MediaDeliveryAccessModeForReleaseClass(releaseClass string) string {
	switch strings.TrimSpace(releaseClass) {
	case "research":
		return MediaDeliveryAccessModeSignedGrant
	case "commercial":
		return MediaDeliveryAccessModePublic
	default:
		return ""
	}
}

// ImportedMediaFields 把 release 资产投影为 App 可消费的逐媒体交付绑定。
// mediaItems 逐项使用 canonical BSON 键（mediaAssetId/mediaAssetVersion，
// 与 contracts PostMediaItem 单轨对齐）；调用者必须先验证 accessMode，空值不会
// 被解释为 public。
func ImportedMediaFields(assets []AssetManifestItem, accessMode string) importedMediaSummary {
	urls := make([]string, 0, len(assets))
	items := make([]bson.M, 0, len(assets))
	assetIDs := make([]string, 0, len(assets))
	seenAssetIDs := make(map[string]struct{}, len(assets))
	appendAssetID := func(rawAssetID string) {
		assetID := strings.TrimSpace(rawAssetID)
		if assetID == "" {
			return
		}
		if _, seen := seenAssetIDs[assetID]; seen {
			return
		}
		seenAssetIDs[assetID] = struct{}{}
		assetIDs = append(assetIDs, assetID)
	}
	summary := importedMediaSummary{}
	for _, asset := range assets {
		itemAccessMode := strings.TrimSpace(asset.AccessMode)
		if itemAccessMode == "" {
			itemAccessMode = strings.TrimSpace(accessMode)
		}
		url := asset.CDNURL
		if url == "" {
			continue
		}
		appendAssetID(asset.AssetID)
		isVideoAsset := strings.EqualFold(strings.TrimSpace(asset.Kind), "video")
		if isVideoAsset {
			// poster（coverUrl）的配对资产标识必须进入 posts.mediaAssetIds，
			// 它是 grant 侧 release membership 判定的输入。
			appendAssetID(asset.PosterAssetID)
		}
		if summary.CoverURL == "" {
			if asset.CoverURL != "" {
				summary.CoverURL = asset.CoverURL
			} else {
				summary.CoverURL = url
			}
		}
		urls = append(urls, url)
		item := bson.M{
			"mediaAssetId":      asset.AssetID,
			"kind":              asset.Kind,
			"mediaAssetVersion": asset.Version,
			"url":               url,
		}
		if itemAccessMode != "" {
			item["accessMode"] = itemAccessMode
		}
		if isVideoAsset && strings.TrimSpace(asset.PosterAssetID) != "" {
			item["coverAssetId"] = strings.TrimSpace(asset.PosterAssetID)
		}
		if asset.Caption != "" {
			item["caption"] = asset.Caption
		}
		if asset.Role != "" {
			item["role"] = asset.Role
		}
		if asset.Width > 0 {
			item["width"] = asset.Width
		}
		if asset.Height > 0 {
			item["height"] = asset.Height
		}
		if asset.DurationMs > 0 {
			item["durationMs"] = asset.DurationMs
		}
		if asset.ThumbnailURL != "" {
			item["thumbnailUrl"] = asset.ThumbnailURL
		}
		if asset.CoverURL != "" {
			item["coverUrl"] = asset.CoverURL
		}
		if asset.CoverStrategy != "" {
			item["coverStrategy"] = asset.CoverStrategy
		}
		if asset.CoverFrameTimeMs > 0 {
			item["coverFrameTimeMs"] = asset.CoverFrameTimeMs
		}
		if isVideoAsset {
			item["coverStrategy"] = firstNonEmptyString(asset.CoverStrategy, "first_frame")
			item["coverFrameTimeMs"] = asset.CoverFrameTimeMs
		}
		items = append(items, item)
		if isVideoAsset && summary.VideoURL == "" {
			summary.VideoURL = url
			summary.ThumbnailURL = firstNonEmptyString(asset.ThumbnailURL, asset.CoverURL)
			summary.CoverURL = firstNonEmptyString(asset.CoverURL, asset.ThumbnailURL, summary.CoverURL)
			summary.CoverStrategy = firstNonEmptyString(asset.CoverStrategy, "first_frame")
			summary.CoverFrameTimeMs = asset.CoverFrameTimeMs
			summary.DurationMs = asset.DurationMs
			summary.Width = asset.Width
			summary.Height = asset.Height
		}
	}
	summary.MediaURLs = urls
	summary.MediaItems = items
	summary.MediaAssetIDs = assetIDs
	return summary
}

func firstNonEmptyString(values ...string) string {
	for _, value := range values {
		if strings.TrimSpace(value) != "" {
			return strings.TrimSpace(value)
		}
	}
	return ""
}

func applyImportedVideoFields(target bson.M, media importedMediaSummary) {
	if media.VideoURL == "" {
		return
	}
	target["videoUrl"] = media.VideoURL
	if media.ThumbnailURL != "" {
		target["thumbnailUrl"] = media.ThumbnailURL
	}
	if media.CoverURL != "" {
		target["coverUrl"] = media.CoverURL
	}
	if media.CoverStrategy != "" {
		target["coverStrategy"] = media.CoverStrategy
	}
	target["coverFrameTimeMs"] = media.CoverFrameTimeMs
	if media.DurationMs > 0 {
		target["durationMs"] = media.DurationMs
	}
	if media.Width > 0 {
		target["width"] = media.Width
	}
	if media.Height > 0 {
		target["height"] = media.Height
	}
}

// UpsertDiscoveryFeed 把发布主线内容同写发现流 ReadModel（rm_discovery_feed）。
// postId 用运行时安全 ID；postRef 保留发布证据引用；conditionProfile 取首个命中实体的画像冗余。
// status/visibility 固定 published/public（冷启动内容均为公开发布），保证召回可见。
// authorId/coverUrl 由 manifest 契约补齐（P1 produce 侧）后再透传；缺省留空不影响 tag/hot/explore 召回。
func UpsertDiscoveryFeed(ctx context.Context, coll *mongo.Collection, posts []PostDoc, condByEntity map[string]map[string]any, now time.Time) (int, error) {
	return UpsertDiscoveryFeedWithOptions(ctx, coll, posts, condByEntity, now, NormalizeImportOptions(ImportOptions{}))
}

func UpsertDiscoveryFeedWithOptions(ctx context.Context, coll *mongo.Collection, posts []PostDoc, condByEntity map[string]map[string]any, now time.Time, opts ImportOptions) (int, error) {
	opts = NormalizeImportOptions(opts)
	n := 0
	for _, p := range posts {
		contentIdentity, err := canonicalImportedContentIdentity(p.ContentIdentity)
		if err != nil {
			return n, fmt.Errorf("%s: %w", p.PostRef, err)
		}
		postID := RuntimePostID(p.ContentID)
		if postID == "" {
			return n, fmt.Errorf("contentId is required to derive discovery feed postId")
		}
		var cond map[string]any
		runtimeEntityRefs := p.NormalizedEntityRefs
		if len(runtimeEntityRefs) == 0 {
			runtimeEntityRefs = p.EntityRefs
		}
		joinEntityRefs := p.EntityRefs
		if len(joinEntityRefs) == 0 {
			joinEntityRefs = runtimeEntityRefs
		}
		for _, er := range joinEntityRefs {
			if c, ok := condByEntity[er]; ok {
				cond = c
				break
			}
		}
		newHash := sourceHash(p)
		set := bson.M{
			"postId":                    postID,
			"postRef":                   p.PostRef,
			"contentId":                 p.ContentID,
			"contentVersion":            p.ContentVersion,
			"title":                     p.Title,
			"contentType":               p.ContentType,
			"contentIdentity":           contentIdentity,
			"authorId":                  p.AuthorID,
			"authorDisplayNameSnapshot": p.AuthorDisplayName,
			"authorAvatarUrlSnapshot":   p.AuthorAvatarURL,
			"creatorProfileId":          p.CreatorProfileID,
			"creatorArchetype":          p.CreatorArchetype,
			"creatorProfileVersion":     p.CreatorProfileVersion,
			"creatorDisclosure":         p.CreatorDisclosure,
			"experienceClaimMode":       p.ExperienceClaimMode,
			"authorQualitySignals":      p.AuthorQualitySignals,
			"tagRefs":                   p.TagRefs,
			"entityRefs":                runtimeEntityRefs,
			"intersectionHints":         p.IntersectionHints,
			"semanticMentions":          p.SemanticMentions,
			"sourceCollectionId":        p.SourceCollectionID,
			"sourcePlatform":            p.SourcePlatform,
			"creator":                   p.Creator,
			"page":                      p.Page,
			"licenseProof":              p.LicenseProof,
			"articleAssetManifest":      p.ArticleAssetManifest,
			"conditionProfile":          cond,
			"status":                    "published",
			"visibility":                "public",
			"sourceHash":                newHash,
			"createdAt":                 p.CreatedAt,
			"updatedAt":                 p.UpdatedAt,
			"publishedAt":               p.PublishedAt,
		}
		accessMode := MediaDeliveryAccessModeForReleaseClass(opts.ReleaseClass)
		media := ImportedMediaFields(importedPostAssets(p), accessMode)
		if len(media.MediaURLs) > 0 {
			set["mediaUrls"] = media.MediaURLs
			set["mediaItems"] = media.MediaItems
			set["coverUrl"] = media.CoverURL
			applyImportedVideoFields(set, media)
		}
		ApplyImportedAuthorAvatarDeliveryFields(set, p, accessMode)
		for key, value := range recinfra.BuildRecommendationProjectionFields(set) {
			set[key] = value
		}
		for k, v := range releaseFields(opts, now, "active") {
			set[k] = v
		}
		if err := removePriorDiscoveryFeedIdentity(
			ctx, coll, p.ContentID, p.PostRef, postID, opts,
		); err != nil {
			return n, err
		}
		if _, err := coll.UpdateOne(ctx,
			bson.M{"postId": postID},
			bson.M{"$set": set, "$setOnInsert": bson.M{
				"likeCount": int64(0), "commentCount": int64(0),
				"viewCount": int64(0),
			}},
			options.UpdateOne().SetUpsert(true),
		); err != nil {
			return n, err
		}
		n++
	}
	return n, nil
}

// ApplyImportedAuthorAvatarDeliveryFields 写作者头像的媒体交付绑定（DEC-033）。
// 真实来源是 release creator profile 的 avatarAsset.assetId（经
// BindPostAuthorSnapshots 绑定到 PostDoc）；头像缺席时两字段写 BSON null，
// 覆盖旧 release 残留值并保持契约 NULLABLE 的缺席语义，禁止以 authorId 冒充。
func ApplyImportedAuthorAvatarDeliveryFields(target bson.M, post PostDoc, accessMode string) {
	avatarAssetID := strings.TrimSpace(post.AuthorAvatarAssetID)
	if avatarAssetID == "" {
		target["authorAvatarAssetId"] = nil
		target["authorAvatarAccessMode"] = nil
		return
	}
	target["authorAvatarAssetId"] = avatarAssetID
	if accessMode == "" {
		target["authorAvatarAccessMode"] = nil
		return
	}
	target["authorAvatarAccessMode"] = accessMode
}

// ImportedArticleAssetManifest 给文章素材清单逐项打上交付访问模式（DEC-033）。
//
// articleAssetManifest 与 mediaItems 是两条独立的 import 路径：后者已在
// ImportedMediaFields 里写 accessMode，前者此前直接透传 release 文档，于是
// 文章内嵌图在 research 相位没有任何交付声明，App 只能按公开 URL 取址而
// 整片打不开。这里按同一个 releaseClass 单点映射补齐，不逐资产猜测。
//
// 返回 nil 表示该 Post 没有文章素材清单，调用方照原样写 null。
func ImportedArticleAssetManifest(
	manifest *ArticleAssetManifestDoc,
	accessMode string,
) *ArticleAssetManifestDoc {
	if manifest == nil {
		return nil
	}
	stamped := *manifest
	if len(manifest.Assets) == 0 {
		return &stamped
	}
	assets := make([]AssetManifestItem, len(manifest.Assets))
	copy(assets, manifest.Assets)
	for index := range assets {
		if strings.TrimSpace(assets[index].AccessMode) == "" {
			assets[index].AccessMode = accessMode
		}
	}
	stamped.Assets = assets
	return &stamped
}

// importedPostAssets keeps the release-import projection on one canonical
// media source. LoadPosts promotes articleAssetManifest.assets into Assets,
// while direct typed callers may still provide only the canonical article
// manifest. Both posts and rm_discovery_feed must therefore resolve the same
// effective asset set instead of silently projecting an article without media.
func importedPostAssets(post PostDoc) []AssetManifestItem {
	if len(post.Assets) > 0 {
		return post.Assets
	}
	if post.ArticleAssetManifest != nil {
		return post.ArticleAssetManifest.Assets
	}
	return nil
}

func removePriorDiscoveryFeedIdentity(
	ctx context.Context,
	coll *mongo.Collection,
	contentID string,
	postRef string,
	runtimeID string,
	opts ImportOptions,
) error {
	priorIdentityFilters := bson.A{bson.M{"postId": postRef}}
	if stableContentID := strings.TrimSpace(contentID); stableContentID != "" {
		priorIdentityFilters = append(
			priorIdentityFilters,
			bson.M{"contentId": stableContentID},
		)
	}
	filter := bson.M{
		"postId": bson.M{"$ne": runtimeID},
		"$or":    priorIdentityFilters,
	}
	if opts.SourceOwner != "" {
		filter["sourceOwner"] = opts.SourceOwner
	}
	res, err := coll.DeleteMany(ctx, filter)
	if err != nil {
		return err
	}
	if res.DeletedCount > 0 {
		return nil
	}
	return nil
}

func ApplyMissingFeedPolicy(ctx context.Context, coll *mongo.Collection, posts []PostDoc, now time.Time, opts ImportOptions) (int64, error) {
	opts = NormalizeImportOptions(opts)
	if !missingPolicyEnabled(opts) || opts.DeletePolicy == "none" {
		return 0, nil
	}
	filter := bson.M{
		"sourceOwner": opts.SourceOwner,
		"postId":      bson.M{"$nin": desiredRuntimePostIDs(posts)},
		"$or": bson.A{
			bson.M{"lifecycleStatus": bson.M{"$ne": "tombstone"}},
			bson.M{"deletedByReleaseId": bson.M{"$ne": opts.ReleaseID}},
		},
	}
	if opts.DeletePolicy == "hard-delete" {
		res, err := coll.DeleteMany(ctx, filter)
		if err != nil {
			return 0, err
		}
		return res.DeletedCount, nil
	}
	res, err := coll.UpdateMany(ctx, filter, bson.M{"$set": bson.M{
		"status": "deleted", "visibility": "hidden", "lifecycleStatus": "tombstone",
		"deletedAt": now, "deletedByReleaseId": opts.ReleaseID, "updatedAt": now,
	}})
	if err != nil {
		return 0, err
	}
	return res.ModifiedCount, nil
}
