package media

import (
	"context"

	mediaapp "quwoquan_service/services/content-service/internal/application/media"
	postapp "quwoquan_service/services/content-service/internal/application/post"
	mediamodel "quwoquan_service/services/content-service/internal/domain/media/model"
)

type mediaAssetBatchReader interface {
	FindMediaAssetsByIDs(context.Context, []string) (map[string]mediaapp.MediaAssetSlice, error)
}

type PostBindingReader struct{ assets mediaAssetBatchReader }

func NewPostBindingReader(assets mediaAssetBatchReader) *PostBindingReader {
	if assets == nil {
		panic("PostBindingReader requires MediaAsset batch reader")
	}
	return &PostBindingReader{assets: assets}
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
		result[assetID] = postapp.MediaAssetBindingSlice{
			AssetID: asset.AssetID,
			OwnerID: asset.OwnerID,
			Ready:   asset.ProcessingStatus == mediamodel.ProcessingStatusReady,
		}
	}
	return result, nil
}

var _ postapp.MediaAssetBindingReader = (*PostBindingReader)(nil)
