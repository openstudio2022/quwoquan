package post

import (
	"context"
	"fmt"
	"strings"

	rterr "quwoquan_service/runtime/errors"
	contentgenerated "quwoquan_service/services/content-service/generated/content/post"
	mediaerrors "quwoquan_service/services/content-service/generated/media/media_asset"
	postmodel "quwoquan_service/services/content-service/internal/content/post/domain/model"
)

func rejectClientMediaDeliveryReferences(post *postmodel.Post) error {
	if post == nil {
		return nil
	}
	if len(asStringSlice(post.MediaUrls)) > 0 ||
		strings.TrimSpace(post.VideoUrl) != "" ||
		strings.TrimSpace(post.CoverUrl) != "" ||
		strings.TrimSpace(post.ThumbnailUrl) != "" {
		return rterr.NewInvalidArgument(
			rterr.ModuleContent,
			"发布内容只能引用媒体资产",
			"Post command cannot carry media delivery references",
		)
	}
	for _, row := range mediaItemRows(post.MediaItems) {
		for _, forbidden := range []string{
			"url",
			"coverUrl",
			"thumbnailUrl",
			"localPath",
			"objectKey",
			"cdnUrl",
		} {
			if strings.TrimSpace(asString(row[forbidden])) != "" {
				return rterr.NewInvalidArgument(
					rterr.ModuleContent,
					"发布内容只能引用媒体资产",
					"Post mediaItems exposed "+forbidden,
				)
			}
		}
	}
	return nil
}

func (s *PostService) prepareMediaAssetsForPublication(
	ctx context.Context,
	post *postmodel.Post,
	ownerID string,
	assetIDs []string,
) error {
	if post == nil {
		return rterr.NewInvalidArgument(
			rterr.ModuleContent,
			"发布内容不能为空",
			"post is required",
		)
	}
	if err := validateArticleMediaCommand(post, assetIDs); err != nil {
		return err
	}
	if len(assetIDs) == 0 {
		post.MediaAssetIds = nil
		post.MediaUrls = nil
		post.VideoUrl = ""
		post.CoverUrl = ""
		post.ThumbnailUrl = ""
		return nil
	}
	if s.mediaAssetBindings == nil {
		return rterr.NewUnavailable(
			rterr.ModuleContent,
			"媒体读取服务未配置",
			"MediaAsset binding reader is required",
		)
	}
	assets, err := s.mediaAssetBindings.FindMediaAssetsForBinding(ctx, assetIDs)
	if err != nil {
		return rterr.NewUnavailable(rterr.ModuleContent, "读取媒体素材失败", err.Error())
	}
	bound := make([]string, 0, len(assetIDs))
	seen := make(map[string]struct{}, len(assetIDs))
	for _, rawID := range assetIDs {
		assetID := strings.TrimSpace(rawID)
		if assetID == "" {
			return rterr.NewInvalidArgument(rterr.ModuleContent, "素材 ID 不能为空", "empty media asset id")
		}
		if _, duplicate := seen[assetID]; duplicate {
			continue
		}
		seen[assetID] = struct{}{}
		asset, ok := assets[assetID]
		if !ok {
			return rterr.NewAppError(rterr.NewCode(rterr.ModuleContent, rterr.KindUser, "media_not_found"), "素材不存在", "media asset not found")
		}
		if err := requireMediaOwner(asset.OwnerID, ownerID); err != nil {
			return err
		}
		if !asset.Ready {
			switch strings.TrimSpace(asset.ProcessingStatus) {
			case "rejected":
				return mediaerrors.AppErrorFromMediaProcessingRejected(
					fmt.Sprintf("media asset %q was rejected by processing", assetID),
				)
			case "deleted":
				return mediaerrors.AppErrorFromMediaNotFound(
					fmt.Sprintf("media asset %q was deleted", assetID),
				)
			}
			return mediaerrors.AppErrorFromMediaNotReady(
				fmt.Sprintf("media asset %q is still processing", assetID),
			)
		}
		bound = append(bound, assetID)
	}
	if err := s.mediaAssetBindings.MaterializePublicSlices(ctx, bound); err != nil {
		return rterr.NewUnavailable(
			rterr.ModuleContent,
			"公开媒体交付准备失败",
			err.Error(),
		)
	}
	if err := ProjectBoundMediaAssets(post, assets, bound); err != nil {
		return rterr.NewInvalidArgument(
			rterr.ModuleContent,
			"素材不能用于当前内容",
			err.Error(),
		)
	}
	post.MediaAssetIds = append([]string(nil), bound...)
	return nil
}

// ProjectBoundMediaAssets is the only Post projection from MediaAsset identity
// to consumer-visible media references. It deliberately emits canonical public
// slice keys, never the upload response's signed delivery URL or CAS key.
func ProjectBoundMediaAssets(
	post *postmodel.Post,
	assets map[string]MediaAssetBindingSlice,
	boundAssetIDs []string,
) error {
	if post == nil {
		return fmt.Errorf("post is required")
	}
	// The draft carries non-delivery presentation metadata from the App. Keep it
	// before clearing all client-controlled URL fields below; the bind projection
	// will rebuild each media item with canonical public slice references.
	metadataByAssetID := boundMediaItemMetadata(post.MediaItems)
	manualCoverIDs := make(map[string]struct{})
	for _, assetID := range boundAssetIDs {
		asset := assets[assetID]
		if !strings.EqualFold(asset.MediaType, "video") {
			continue
		}
		coverAssetID := strings.TrimSpace(asset.ManualCoverAssetID)
		if draftCoverAssetID := strings.TrimSpace(
			asString(metadataByAssetID[assetID]["coverAssetId"]),
		); draftCoverAssetID != "" {
			coverAssetID = draftCoverAssetID
		}
		if coverAssetID != "" {
			manualCoverIDs[coverAssetID] = struct{}{}
		}
	}

	// Binding supersedes any client-supplied media URL fields, so a successful
	// bind removes the historical cdnUrl/CAS persistence bypass.
	post.MediaUrls = nil
	post.MediaItems = nil
	post.VideoUrl = ""
	post.CoverUrl = ""
	post.ThumbnailUrl = ""

	mediaURLs := make([]string, 0, len(boundAssetIDs))
	mediaItems := make([]map[string]any, 0, len(boundAssetIDs))
	var firstImageSlice string
	var firstVideoSlice string
	var firstVideoCover string
	for _, assetID := range boundAssetIDs {
		asset := assets[assetID]
		publicSliceKey := strings.TrimSpace(asset.PublicSliceKey)
		if publicSliceKey == "" {
			return fmt.Errorf("media asset %q has no public slice key", assetID)
		}
		switch strings.ToLower(strings.TrimSpace(asset.MediaType)) {
		case "image":
			if _, isManualCoverOnly := manualCoverIDs[assetID]; isManualCoverOnly {
				continue
			}
			mediaURLs = append(mediaURLs, publicSliceKey)
			item := boundMediaItem(metadataByAssetID[assetID])
			item["kind"] = "image"
			item["url"] = publicSliceKey
			mediaItems = append(mediaItems, item)
			if firstImageSlice == "" {
				firstImageSlice = publicSliceKey
			}
		case "video":
			coverSlice, err := boundVideoCoverSlice(
				asset,
				assets,
				metadataByAssetID[assetID],
			)
			if err != nil {
				return err
			}
			mediaURLs = append(mediaURLs, publicSliceKey)
			item := boundMediaItem(metadataByAssetID[assetID])
			item["kind"] = "video"
			item["mediaAssetId"] = asset.AssetID
			item["mediaAssetVersion"] = asset.Version
			item["url"] = publicSliceKey
			item["coverUrl"] = coverSlice
			item["durationMs"] = asset.VerifiedDurationMs
			item["width"] = asset.VideoWidth
			item["height"] = asset.VideoHeight
			if asset.PreviewTrackVersion > 0 {
				item["previewTrackVersion"] = asset.PreviewTrackVersion
				item["previewTrackManifestUrl"] = asset.PreviewTrackManifestSliceKey
			}
			mediaItems = append(mediaItems, item)
			if firstVideoSlice == "" {
				firstVideoSlice = publicSliceKey
				firstVideoCover = coverSlice
			}
		}
	}

	post.MediaUrls = mediaURLs
	if len(mediaItems) > 0 {
		post.MediaItems = mediaItems
	}
	if firstImageSlice != "" {
		post.CoverUrl = firstImageSlice
	}
	if firstVideoSlice != "" {
		post.VideoUrl = firstVideoSlice
		post.ThumbnailUrl = firstVideoCover
		post.CoverUrl = firstVideoCover
		for _, assetID := range boundAssetIDs {
			asset := assets[assetID]
			if !strings.EqualFold(strings.TrimSpace(asset.MediaType), "video") {
				continue
			}
			post.Width = int64(asset.VideoWidth)
			post.Height = int64(asset.VideoHeight)
			post.DurationMs = asset.VerifiedDurationMs
			break
		}
	}
	if strings.EqualFold(strings.TrimSpace(post.ContentType), "video") &&
		firstVideoSlice == "" {
		return fmt.Errorf("video post requires a bound ready video MediaAsset")
	}
	if strings.EqualFold(strings.TrimSpace(post.ContentType), "article") {
		projectArticleAssetManifest(post, assets, boundAssetIDs)
	}
	return nil
}

func validateArticleMediaCommand(
	post *postmodel.Post,
	boundAssetIDs []string,
) error {
	if !strings.EqualFold(strings.TrimSpace(post.ContentType), "article") {
		return nil
	}
	allowed := make(map[string]struct{}, len(boundAssetIDs))
	for _, assetID := range boundAssetIDs {
		allowed[strings.TrimSpace(assetID)] = struct{}{}
	}
	for _, row := range articleManifestRows(post.ArticleAssetManifest) {
		for _, forbidden := range []string{
			"localPath",
			"objectKey",
			"cdnUrl",
			"uploadUrl",
			"presignUrl",
		} {
			if strings.TrimSpace(asString(row[forbidden])) != "" {
				return rterr.NewInvalidArgument(
					rterr.ModuleContent,
					"文章素材只能引用媒体资产",
					"article media command exposed "+forbidden,
				)
			}
		}
		assetID := strings.TrimSpace(asString(row["assetId"]))
		if assetID == "" {
			return rterr.NewInvalidArgument(
				rterr.ModuleContent,
				"文章素材标识不能为空",
				"article media manifest requires assetId",
			)
		}
		if _, found := allowed[assetID]; !found {
			return rterr.NewInvalidArgument(
				rterr.ModuleContent,
				"文章素材未绑定",
				"article media manifest references an unbound MediaAsset",
			)
		}
	}
	return nil
}

func projectArticleAssetManifest(
	post *postmodel.Post,
	assets map[string]MediaAssetBindingSlice,
	boundAssetIDs []string,
) {
	metadata := make(map[string]map[string]any)
	for _, row := range articleManifestRows(post.ArticleAssetManifest) {
		assetID := strings.TrimSpace(asString(row["assetId"]))
		if assetID != "" {
			metadata[assetID] = row
		}
	}
	rows := make([]map[string]any, 0, len(boundAssetIDs))
	for _, assetID := range boundAssetIDs {
		asset := assets[assetID]
		if !strings.EqualFold(strings.TrimSpace(asset.MediaType), "image") {
			continue
		}
		source := metadata[assetID]
		role := strings.TrimSpace(asString(source["role"]))
		if role == "" {
			role = "figure"
		}
		row := map[string]any{
			"assetId":        assetID,
			"kind":           "image",
			"role":           role,
			"publicSliceKey": strings.TrimSpace(asset.PublicSliceKey),
		}
		for _, field := range []string{"layout", "caption"} {
			if value := strings.TrimSpace(asString(source[field])); value != "" {
				row[field] = value
			}
		}
		rows = append(rows, row)
	}
	post.ArticleAssetManifest = map[string]any{
		"schema":          "article-asset-manifest",
		"markdownVersion": "qwq-rich-md",
		"assets":          rows,
	}
}

func articleManifestRows(manifest map[string]any) []map[string]any {
	raw, exists := manifest["assets"]
	if !exists {
		return nil
	}
	rows := make([]map[string]any, 0)
	switch values := raw.(type) {
	case []map[string]any:
		rows = append(rows, values...)
	case []any:
		for _, value := range values {
			if row, ok := value.(map[string]any); ok {
				rows = append(rows, row)
			}
		}
	}
	return rows
}

func boundMediaItemMetadata(raw any) map[string]map[string]any {
	items := mediaItemRows(raw)
	result := make(map[string]map[string]any, len(items))
	for _, item := range items {
		assetID := strings.TrimSpace(asString(item["mediaId"]))
		if assetID == "" {
			continue
		}
		result[assetID] = item
	}
	return result
}

func mediaItemRows(raw any) []map[string]any {
	items := make([]map[string]any, 0)
	switch value := raw.(type) {
	case []map[string]any:
		items = append(items, value...)
	case []any:
		for _, item := range value {
			if typed, ok := item.(map[string]any); ok {
				items = append(items, typed)
			}
		}
	}
	return items
}

func boundMediaItem(source map[string]any) map[string]any {
	item := make(map[string]any)
	// The client may retain non-delivery presentation metadata while a draft is
	// awaiting binding. URL-shaped fields are deliberately excluded: only this
	// function supplies url/coverUrl from public slice projection.
	for _, field := range []string{
		"mediaId",
		"coverAssetId",
		"durationMs",
		"width",
		"height",
		"title",
		"coverStrategy",
		"coverFrameTimeMs",
	} {
		if value, exists := source[field]; exists {
			item[field] = value
		}
	}
	return item
}

func boundVideoCoverSlice(
	video MediaAssetBindingSlice,
	assets map[string]MediaAssetBindingSlice,
	presentation map[string]any,
) (string, error) {
	coverAssetID := strings.TrimSpace(video.ManualCoverAssetID)
	if draftCoverAssetID := strings.TrimSpace(
		asString(presentation["coverAssetId"]),
	); draftCoverAssetID != "" {
		coverAssetID = draftCoverAssetID
	}
	if coverAssetID != "" {
		cover, found := assets[coverAssetID]
		if !found || !cover.Ready || !strings.EqualFold(cover.MediaType, "image") {
			return "", fmt.Errorf(
				"video asset %q references an unavailable manual cover asset %q",
				video.AssetID,
				coverAssetID,
			)
		}
		if coverSlice := strings.TrimSpace(cover.PublicSliceKey); coverSlice != "" {
			return coverSlice, nil
		}
		return "", fmt.Errorf(
			"manual cover asset %q has no public slice key",
			coverAssetID,
		)
	}
	if coverSlice := strings.TrimSpace(video.CoverPublicSliceKey); coverSlice != "" {
		return videoThumbnailPublicSlice(coverSlice), nil
	}
	return "", fmt.Errorf("video asset %q has no VOD cover public slice key", video.AssetID)
}

func videoThumbnailPublicSlice(publicSliceKey string) string {
	publicSliceKey = strings.TrimSpace(publicSliceKey)
	if publicSliceKey == "" || strings.Contains(publicSliceKey, "?") {
		return publicSliceKey
	}
	return publicSliceKey + "?variant=thumb"
}

func requireMediaOwner(resourceOwnerID, actorID string) error {
	resourceOwnerID = strings.TrimSpace(resourceOwnerID)
	actorID = strings.TrimSpace(actorID)
	if actorID == "" {
		return contentgenerated.AppErrorFromUnauthorized("media operation requires a verified actor")
	}
	if resourceOwnerID == "" || resourceOwnerID != actorID {
		return contentgenerated.AppErrorFromForbiddenEdit("media owner mismatch")
	}
	return nil
}
