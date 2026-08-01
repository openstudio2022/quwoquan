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
	MimeType        string
	FileSize        int64
	CaptureMetadata mediamodel.CaptureMetadata
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
		MediaType:          mediamodel.MediaType(strings.TrimSpace(params.MediaType)),
		MimeType:           strings.TrimSpace(params.MimeType),
		FileSize:           params.FileSize,
		CaptureMetadata:    params.CaptureMetadata,
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
		MediaType:        string(snapshot.MediaType),
		MimeType:         snapshot.MimeType,
		FileSize:         snapshot.FileSize,
		CaptureMetadata:  snapshot.CaptureMetadata,
		AccessPolicy:     string(snapshot.AccessPolicy),
		ProcessingStatus: string(snapshot.ProcessingStatus),
		CoverStrategy:    string(snapshot.CoverStrategy),
		CreatedAt:        snapshot.CreatedAt,
		UpdatedAt:        snapshot.UpdatedAt,
	}, nil
}
