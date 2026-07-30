package media

import (
	"context"
	"fmt"

	runtimemedia "quwoquan_service/runtime/media"
	postapp "quwoquan_service/services/content-service/internal/content/post/application"
	mediaapp "quwoquan_service/services/content-service/internal/content/post/application/media"
	mediamodel "quwoquan_service/services/content-service/internal/content/post/domain/media/model"
)

type mediaAssetBatchReader interface {
	FindMediaAssetsByIDs(context.Context, []string) (map[string]mediaapp.MediaAssetSlice, error)
}

type publicSlicePublisher interface {
	PublishPublicSlice(context.Context, string, string) error
}

type PostBindingReader struct {
	assets    mediaAssetBatchReader
	publisher publicSlicePublisher
}

func NewPostBindingReader(
	assets mediaAssetBatchReader,
	publisher publicSlicePublisher,
) *PostBindingReader {
	if assets == nil || publisher == nil {
		panic("PostBindingReader requires MediaAsset batch reader and public slice publisher")
	}
	return &PostBindingReader{assets: assets, publisher: publisher}
}

func (r *PostBindingReader) FindMediaAssetsForBinding(
	ctx context.Context,
	assetIDs []string,
) (map[string]postapp.MediaAssetBindingSlice, error) {
	assets, err := r.assets.FindMediaAssetsByIDs(ctx, assetIDs)
	if err != nil {
		return nil, err
	}
	result := make(map[string]postapp.MediaAssetBindingSlice, len(assets))
	for assetID, asset := range assets {
		publicSliceKey := asset.ImagePublicSliceKey
		if asset.MediaType == "video" {
			publicSliceKey = asset.VideoPublicSliceKey
		} else if asset.MediaType != "image" {
			publicSliceKey = runtimemedia.BuildContentMediaPublicSliceKey(
				asset.MediaType,
				asset.AssetID,
				asset.Version,
				asset.MimeType,
			)
		}
		ready := asset.ProcessingStatus == mediamodel.ProcessingStatusReady
		if ready && publicSliceKey == "" {
			return nil, fmt.Errorf(
				"media asset %q cannot derive a canonical public slice key",
				asset.AssetID,
			)
		}
		result[assetID] = postapp.MediaAssetBindingSlice{
			AssetID:                       asset.AssetID,
			OwnerID:                       asset.OwnerID,
			Ready:                         ready,
			ProcessingStatus:              string(asset.ProcessingStatus),
			MediaType:                     asset.MediaType,
			MimeType:                      asset.MimeType,
			Version:                       asset.Version,
			PublicSliceKey:                publicSliceKey,
			VerifiedDurationMs:            asset.VerifiedDurationMs,
			VideoWidth:                    asset.VideoWidth,
			VideoHeight:                   asset.VideoHeight,
			VideoPublicSliceKey:           asset.VideoPublicSliceKey,
			CoverPublicSliceKey:           asset.CoverPublicSliceKey,
			PreviewTrackVersion:           asset.PreviewTrackVersion,
			PreviewTrackManifestSliceKey:  asset.PreviewTrackManifestSliceKey,
			HLSCMAFDescriptorVersion:      asset.HLSCMAFDescriptorVersion,
			HLSCMAFDescriptorSliceKey:     asset.HLSCMAFDescriptorSliceKey,
			HLSCMAFMasterManifestSliceKey: asset.HLSCMAFMasterManifestSliceKey,
			HLSCMAFRenditionCount:         asset.HLSCMAFRenditionCount,
			CoverStrategy:                 asset.CoverStrategy,
			ManualCoverAssetID:            asset.ManualCoverAssetID,
			CoverFrameTimeMs:              asset.CoverFrameTimeMs,
		}
	}
	return result, nil
}

// MaterializePublicSlices runs only after the Post application layer has
// completed owner and ready-state validation. This prevents an unauthorized
// binding attempt from making a private asset reachable on a public slice.
func (r *PostBindingReader) MaterializePublicSlices(
	ctx context.Context,
	assetIDs []string,
) error {
	assets, err := r.assets.FindMediaAssetsByIDs(ctx, assetIDs)
	if err != nil {
		return err
	}
	for _, assetID := range assetIDs {
		asset, ok := assets[assetID]
		if !ok {
			return fmt.Errorf("media asset %q is unavailable for public slice materialization", assetID)
		}
		if asset.MediaType == "video" {
			if asset.VideoPublicSliceKey == "" || asset.CoverPublicSliceKey == "" {
				return fmt.Errorf("ready video asset %q has no VOD delivery slices", asset.AssetID)
			}
			continue
		}
		sourceObjectKey := asset.ObjectKey
		publicSliceKey := runtimemedia.BuildContentMediaPublicSliceKey(
			asset.MediaType,
			asset.AssetID,
			asset.Version,
			asset.MimeType,
		)
		if asset.MediaType == "image" {
			sourceObjectKey = asset.ImageNormalizedObjectKey
			publicSliceKey = asset.ImagePublicSliceKey
			if sourceObjectKey == "" {
				return fmt.Errorf(
					"ready image asset %q has no normalized source object",
					asset.AssetID,
				)
			}
		}
		if publicSliceKey == "" {
			return fmt.Errorf(
				"media asset %q cannot derive a canonical public slice key",
				asset.AssetID,
			)
		}
		if err := r.publisher.PublishPublicSlice(
			ctx,
			sourceObjectKey,
			publicSliceKey,
		); err != nil {
			return fmt.Errorf(
				"materialize public slice for media asset %q: %w",
				asset.AssetID,
				err,
			)
		}
	}
	return nil
}

var _ postapp.MediaAssetBindingReader = (*PostBindingReader)(nil)
