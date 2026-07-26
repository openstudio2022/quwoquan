package application

import (
	"strings"
	"time"

	mediamodel "quwoquan_service/services/content-service/internal/content/post/domain/media/model"
	assetports "quwoquan_service/services/content-service/internal/media/media_asset/domain/ports"
)

type UploadCreationParams struct {
	ID              string
	OwnerID         string
	SourceSessionID string
	ObjectKey       string
	SHA256          string
	MediaType       string
	ContentType     string
	FileSize        int64
	AccessPolicy    string
	Now             time.Time
}

// BuildUploadCreation is the MediaAsset-owned factory used by upload-session
// completion. It keeps MediaAsset invariants and defaults out of sibling
// application and persistence code.
func BuildUploadCreation(params UploadCreationParams) (assetports.Creation, error) {
	asset, err := mediamodel.CreateMediaAsset(mediamodel.CreateMediaAssetParams{
		ID:                 strings.TrimSpace(params.ID),
		OwnerID:            strings.TrimSpace(params.OwnerID),
		SourceSessionID:    strings.TrimSpace(params.SourceSessionID),
		ObjectKey:          strings.TrimSpace(params.ObjectKey),
		SHA256:             strings.TrimSpace(params.SHA256),
		MediaType:          strings.TrimSpace(params.MediaType),
		ContentType:        strings.TrimSpace(params.ContentType),
		FileSize:           params.FileSize,
		AccessPolicy:       mediamodel.AccessPolicy(strings.TrimSpace(params.AccessPolicy)),
		ProcessingRequired: params.MediaType == "image" || params.MediaType == "video",
		Now:                params.Now.UTC(),
	})
	if err != nil {
		return assetports.Creation{}, err
	}
	snapshot := asset.Snapshot()
	return assetports.Creation{
		ID:               snapshot.ID,
		Version:          snapshot.Version,
		OwnerID:          snapshot.OwnerID,
		SourceSessionID:  snapshot.SourceSessionID,
		ObjectKey:        snapshot.ObjectKey,
		SHA256:           snapshot.SHA256,
		MediaType:        snapshot.MediaType,
		ContentType:      snapshot.ContentType,
		FileSize:         snapshot.FileSize,
		AccessPolicy:     string(snapshot.AccessPolicy),
		ProcessingStatus: string(snapshot.ProcessingStatus),
		CoverStrategy:    snapshot.CoverStrategy,
		CreatedAt:        snapshot.CreatedAt,
		UpdatedAt:        snapshot.UpdatedAt,
	}, nil
}
