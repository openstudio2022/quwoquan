package model

import (
	"testing"
	"time"

	runtimemedia "quwoquan_service/runtime/media"
)

func TestRecordImageProcessingResultValidatesTargetAggregateVersion(t *testing.T) {
	createdAt := time.Date(2026, 7, 21, 0, 0, 0, 0, time.UTC)
	asset, err := CreateMediaAsset(CreateMediaAssetParams{
		ID:                 "media-version-contract",
		OwnerID:            "owner-1",
		SourceSessionID:    "session-1",
		ObjectKey:          "private/media-version-contract/source.jpg",
		SHA256:             "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
		MediaType:          "image",
		ContentType:        "image/jpeg",
		FileSize:           128,
		AccessPolicy:       AccessPolicyOwnerOnly,
		ProcessingRequired: true,
		Now:                createdAt,
	})
	if err != nil {
		t.Fatalf("create processing asset: %v", err)
	}
	if asset.Version() != 1 {
		t.Fatalf("initial version=%d, want 1", asset.Version())
	}

	const targetVersion int64 = 2
	publicSlice := runtimemedia.BuildContentMediaPublicSliceKey(
		"image",
		asset.ID(),
		targetVersion,
		"image/jpeg",
	)
	err = asset.RecordProcessingResult(
		ProcessingStatusReady,
		"",
		MediaProcessingDescriptor{Image: ImageProcessingDescriptor{
			ProcessorProfile:         "content_image_normalization_v1",
			ImageWidth:               540,
			ImageHeight:              960,
			ImageDeliveryContentType: "image/jpeg",
			ImageNormalizedObjectKey: "private/media-version-contract/v2/source.jpg",
			ImagePublicSliceKey:      publicSlice,
		}},
		createdAt.Add(time.Second),
	)
	if err != nil {
		t.Fatalf("record canonical v2 processing result: %v", err)
	}
	if asset.Version() != targetVersion ||
		asset.ProcessingStatus() != ProcessingStatusReady {
		t.Fatalf(
			"processing result state=(version=%d,status=%s), want (2,ready)",
			asset.Version(),
			asset.ProcessingStatus(),
		)
	}
}
