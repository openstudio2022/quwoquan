package post

import (
	"context"
	"fmt"
	"strings"

	rterr "quwoquan_service/runtime/errors"
	contentgenerated "quwoquan_service/services/content-service/generated/content/post"
	postmodel "quwoquan_service/services/content-service/generated/content/post/contract/model"
	mediaerrors "quwoquan_service/services/content-service/generated/media/media_asset"
)

func rejectClientMediaDeliveryReferences(post *postmodel.Post) error {
	if post == nil {
		return nil
	}
	if err := validateCaptureDisclosure(post); err != nil {
		return err
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
	for _, item := range post.MediaItems {
		if strings.TrimSpace(item.Url) != "" ||
			strings.TrimSpace(item.CoverUrl) != "" ||
			strings.TrimSpace(item.ThumbnailUrl) != "" {
			return rterr.NewInvalidArgument(
				rterr.ModuleContent,
				"发布内容只能引用媒体资产",
				"Post mediaItems exposed a delivery reference",
			)
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
	// Client-owned capture tags are never trusted. Start from a withdrawn
	// subtree and repopulate it only from bound MediaAsset facts below.
	projectCaptureMetadataFeatures(post, nil, nil)
	if len(assetIDs) == 0 {
		post.MediaAssetIds = nil
		post.MediaUrls = nil
		post.VideoUrl = ""
		post.CoverUrl = ""
		post.ThumbnailUrl = ""
		return nil
	}
	if s.mediaAssetBindings == nil {
		return contentgenerated.AppErrorFromRequiredDependencyUnavailable("MediaAsset binding reader is required")
	}
	assets, err := s.mediaAssetBindings.FindMediaAssetsForBinding(ctx, assetIDs)
	if err != nil {
		return contentgenerated.AppErrorFromRequiredDependencyUnavailable(err.Error())
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
		return contentgenerated.AppErrorFromRequiredDependencyUnavailable(err.Error())
	}
	if err := ProjectBoundMediaAssets(post, assets, bound); err != nil {
		return rterr.NewInvalidArgument(
			rterr.ModuleContent,
			"素材不能用于当前内容",
			err.Error(),
		)
	}
	projectCaptureMetadataFeatures(post, assets, bound)
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
	manualCoverIDs := make(map[string]struct{})
	for _, assetID := range boundAssetIDs {
		asset := assets[assetID]
		if !strings.EqualFold(asset.MediaType, "video") {
			continue
		}
		coverAssetID := strings.TrimSpace(asset.ManualCoverAssetID)
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
	mediaItems := make([]postmodel.PostMediaItem, 0, len(boundAssetIDs))
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
			item := postmodel.PostMediaItem{
				Kind:              "image",
				MediaAssetId:      asset.AssetID,
				MediaAssetVersion: asset.Version,
				Url:               publicSliceKey,
			}
			mediaItems = append(mediaItems, item)
			if firstImageSlice == "" {
				firstImageSlice = publicSliceKey
			}
		case "video":
			coverSlice, err := boundVideoCoverSlice(
				asset,
				assets,
			)
			if err != nil {
				return err
			}
			mediaURLs = append(mediaURLs, publicSliceKey)
			item := postmodel.PostMediaItem{
				Kind:                     "video",
				MediaAssetId:             asset.AssetID,
				MediaAssetVersion:        asset.Version,
				Url:                      publicSliceKey,
				CoverUrl:                 coverSlice,
				ThumbnailUrl:             coverSlice,
				DurationMs:               asset.VerifiedDurationMs,
				Width:                    int64(asset.VideoWidth),
				Height:                   int64(asset.VideoHeight),
				CoverStrategy:            strings.TrimSpace(asset.CoverStrategy),
				CoverFrameTimeMs:         asset.CoverFrameTimeMs,
				PreviewTrackVersion:      int64(asset.PreviewTrackVersion),
				PreviewTrackManifestUrl:  strings.TrimSpace(asset.PreviewTrackManifestSliceKey),
				HlsCmafDescriptorVersion: int64(asset.HLSCMAFDescriptorVersion),
				HlsCmafMasterManifestUrl: strings.TrimSpace(asset.HLSCMAFMasterManifestSliceKey),
			}
			if asset.PreviewTrackVersion > 0 {
				item.PreviewTrackVersion = int64(asset.PreviewTrackVersion)
				item.PreviewTrackManifestUrl = asset.PreviewTrackManifestSliceKey
			}
			if asset.HLSCMAFDescriptorVersion > 0 {
				item.HlsCmafDescriptorVersion = int64(asset.HLSCMAFDescriptorVersion)
				item.HlsCmafMasterManifestUrl = asset.HLSCMAFMasterManifestSliceKey
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
	for _, asset := range post.ArticleAssetManifest.Assets {
		if strings.TrimSpace(asset.PublicSliceKey) != "" {
			return rterr.NewInvalidArgument(
				rterr.ModuleContent,
				"文章素材只能引用媒体资产",
				"article media command exposed a storage or delivery reference",
			)
		}
		assetID := strings.TrimSpace(asset.AssetId)
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
	metadata := make(map[string]postmodel.PostArticleAsset)
	for _, asset := range post.ArticleAssetManifest.Assets {
		assetID := strings.TrimSpace(asset.AssetId)
		if assetID != "" {
			metadata[assetID] = asset
		}
	}
	rows := make([]postmodel.PostArticleAsset, 0, len(boundAssetIDs))
	for _, assetID := range boundAssetIDs {
		asset := assets[assetID]
		if !strings.EqualFold(strings.TrimSpace(asset.MediaType), "image") {
			continue
		}
		source := metadata[assetID]
		role := strings.TrimSpace(source.Role)
		if role == "" {
			role = "figure"
		}
		row := postmodel.PostArticleAsset{
			AssetId:        assetID,
			Kind:           "image",
			Role:           role,
			Layout:         strings.TrimSpace(source.Layout),
			Caption:        strings.TrimSpace(source.Caption),
			PublicSliceKey: strings.TrimSpace(asset.PublicSliceKey),
		}
		rows = append(rows, row)
	}
	manifest := post.ArticleAssetManifest
	manifest.Schema = "article-asset-manifest"
	manifest.MarkdownVersion = "qwq-rich-md"
	manifest.MarkdownDialect = defaultString(
		strings.TrimSpace(post.MarkdownDialect),
		"qwq-rich-md",
	)
	manifest.ArticleMarkdownDigest = strings.TrimSpace(post.ArticleMarkdownDigest)
	manifest.Assets = rows
	post.ArticleAssetManifest = manifest
}

func boundVideoCoverSlice(
	video MediaAssetBindingSlice,
	assets map[string]MediaAssetBindingSlice,
) (string, error) {
	coverAssetID := strings.TrimSpace(video.ManualCoverAssetID)
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
