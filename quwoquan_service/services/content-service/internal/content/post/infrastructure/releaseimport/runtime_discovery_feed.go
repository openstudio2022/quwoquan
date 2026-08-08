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
	CoverURL         string
	ThumbnailURL     string
	VideoURL         string
	CoverStrategy    string
	CoverFrameTimeMs int64
	DurationMs       int64
	Width            int64
	Height           int64
}

func ImportedMediaFields(assets []AssetManifestItem) importedMediaSummary {
	urls := make([]string, 0, len(assets))
	items := make([]bson.M, 0, len(assets))
	summary := importedMediaSummary{}
	for _, asset := range assets {
		url := asset.CDNURL
		if url == "" {
			continue
		}
		isVideoAsset := strings.EqualFold(strings.TrimSpace(asset.Kind), "video")
		if summary.CoverURL == "" {
			if asset.CoverURL != "" {
				summary.CoverURL = asset.CoverURL
			} else {
				summary.CoverURL = url
			}
		}
		urls = append(urls, url)
		item := bson.M{
			"assetId":        asset.AssetID,
			"kind":           asset.Kind,
			"version":        asset.Version,
			"publicSliceKey": asset.PublicSliceKey,
			"url":            url,
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
		postID := RuntimePostID(p.PostRef)
		if postID == "" {
			return n, fmt.Errorf("postRef is required to derive discovery feed postId")
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
			"postId":                postID,
			"postRef":               p.PostRef,
			"title":                 p.Title,
			"contentType":           p.ContentType,
			"contentIdentity":       contentIdentity,
			"authorId":              p.AuthorID,
			"creatorProfileId":      p.CreatorProfileID,
			"creatorArchetype":      p.CreatorArchetype,
			"creatorProfileVersion": p.CreatorProfileVersion,
			"creatorDisclosure":     p.CreatorDisclosure,
			"experienceClaimMode":   p.ExperienceClaimMode,
			"authorQualitySignals":  p.AuthorQualitySignals,
			"tagRefs":               p.TagRefs,
			"entityRefs":            runtimeEntityRefs,
			"intersectionHints":     p.IntersectionHints,
			"semanticMentions":      p.SemanticMentions,
			"sourceCollectionId":    p.SourceCollectionID,
			"sourcePlatform":        p.SourcePlatform,
			"creator":               p.Creator,
			"page":                  p.Page,
			"licenseProof":          p.LicenseProof,
			"articleAssetManifest":  p.ArticleAssetManifest,
			"sourceTaskId":          p.SourceTaskId,
			"conditionProfile":      cond,
			"status":                "published",
			"visibility":            "public",
			"sourceHash":            newHash,
			"createdAt":             p.CreatedAt,
			"updatedAt":             p.UpdatedAt,
			"publishedAt":           p.PublishedAt,
		}
		media := ImportedMediaFields(importedPostAssets(p))
		if len(media.MediaURLs) > 0 {
			set["mediaUrls"] = media.MediaURLs
			set["mediaItems"] = media.MediaItems
			set["coverUrl"] = media.CoverURL
			applyImportedVideoFields(set, media)
		}
		for key, value := range recinfra.BuildRecommendationProjectionFields(set) {
			set[key] = value
		}
		for k, v := range releaseFields(opts, now, "active") {
			set[k] = v
		}
		if err := removePriorDiscoveryFeedIdentity(ctx, coll, p.PostRef, postID, opts); err != nil {
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

func removePriorDiscoveryFeedIdentity(ctx context.Context, coll *mongo.Collection, postRef string, runtimeID string, opts ImportOptions) error {
	filter := bson.M{"postId": postRef}
	if opts.SourceOwner != "" {
		filter["sourceOwner"] = opts.SourceOwner
	}
	res, err := coll.DeleteOne(ctx, filter)
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
