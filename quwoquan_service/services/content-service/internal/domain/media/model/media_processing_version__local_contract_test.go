package model

import (
	"strconv"
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
			ImageDominantColor:       "#1A2B3C",
			ImageLQIP:                "data:image/jpeg;base64,/9j/2Q==",
			ImageContentProfile:      "photographic",
			DerivativePolicyVersion:  1,
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
	descriptor := asset.ImageProcessingDescriptor()
	if descriptor.DerivativePolicyVersion != 1 ||
		descriptor.ImageDominantColor != "#1A2B3C" ||
		descriptor.ImageContentProfile != "photographic" {
		t.Fatalf("image descriptor lost delivery metadata: %+v", descriptor)
	}
}

func TestReadyVideoKeepsProcessingVersionAcrossCoverMutationAndRestore(t *testing.T) {
	createdAt := time.Date(2026, 7, 21, 0, 0, 0, 0, time.UTC)
	asset, err := CreateMediaAsset(CreateMediaAssetParams{
		ID:                 "media-video-processing-version",
		OwnerID:            "owner-1",
		SourceSessionID:    "session-1",
		ObjectKey:          "private/media-video-processing-version/source.mp4",
		SHA256:             "sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
		MediaType:          "video",
		ContentType:        "video/mp4",
		FileSize:           1024,
		AccessPolicy:       AccessPolicyOwnerOnly,
		ProcessingRequired: true,
		Now:                createdAt,
	})
	if err != nil {
		t.Fatalf("create processing video asset: %v", err)
	}

	const processingVersion int64 = 2
	videoSlice := runtimemedia.BuildContentMediaPublicSliceKey(
		"video",
		asset.ID(),
		processingVersion,
		"video/mp4",
	)
	videoPrefix := videoSlice[:len(videoSlice)-len("/source.mp4")]
	if err := asset.RecordProcessingResult(
		ProcessingStatusReady,
		"",
		MediaProcessingDescriptor{Video: VideoProcessingDescriptor{
			ProcessorProfile:             "content_video_transcode_v1",
			VerifiedDurationMs:           1_000,
			VideoWidth:                   1280,
			VideoHeight:                  720,
			VideoCodec:                   "h264",
			VideoContainer:               "mp4",
			VideoAudioCodec:              "aac",
			VideoKeyframeIntervalMs:      1_000,
			VideoFastStart:               true,
			VideoPublicSliceKey:          videoSlice,
			CoverPublicSliceKey:          videoPrefix + "/cover.jpg",
			PreviewTrackVersion:          1,
			PreviewTrackManifestSliceKey: videoPrefix + "/preview/manifest.json",
		}},
		createdAt.Add(time.Second),
	); err != nil {
		t.Fatalf("record ready video processing result: %v", err)
	}
	if err := asset.SelectAutoCover("owner-1", createdAt.Add(2*time.Second)); err != nil {
		t.Fatalf("select auto cover: %v", err)
	}

	snapshot := asset.Snapshot()
	if snapshot.Version != 3 || snapshot.ProcessingVersion != processingVersion {
		t.Fatalf(
			"version state=(aggregate=%d, processing=%d), want (3,%d)",
			snapshot.Version,
			snapshot.ProcessingVersion,
			processingVersion,
		)
	}
	restored, err := RestoreMediaAsset(snapshot)
	if err != nil {
		t.Fatalf("restore video after cover mutation: %v", err)
	}
	if got := restored.VideoProcessingDescriptor().VideoPublicSliceKey; got != videoSlice {
		t.Fatalf("restored video slice=%q, want processing-version slice %q", got, videoSlice)
	}
}

func TestImageDescriptorRevisionActivationAndRollbackRemainAuditable(t *testing.T) {
	createdAt := time.Date(2026, 7, 21, 0, 0, 0, 0, time.UTC)
	asset, err := CreateMediaAsset(CreateMediaAssetParams{
		ID:                 "media-image-revision",
		OwnerID:            "owner-1",
		SourceSessionID:    "session-image-revision",
		ObjectKey:          "private/media-image-revision/source.jpg",
		SHA256:             "sha256:cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc",
		MediaType:          "image",
		ContentType:        "image/jpeg",
		FileSize:           128,
		AccessPolicy:       AccessPolicyOwnerOnly,
		ProcessingRequired: true,
		Now:                createdAt,
	})
	if err != nil {
		t.Fatalf("create image asset: %v", err)
	}
	original := imageDescriptorForAssetVersion(asset.ID(), 2, 1)
	if err := asset.RecordProcessingResult(
		ProcessingStatusReady,
		"",
		MediaProcessingDescriptor{Image: original},
		createdAt.Add(time.Second),
	); err != nil {
		t.Fatalf("record initial descriptor: %v", err)
	}

	reprocessed := imageDescriptorForAssetVersion(asset.ID(), 3, 2)
	previous, activated, err := asset.ActivateReprocessedImageDescriptor(
		"run-1",
		reprocessed,
		createdAt.Add(2*time.Second),
	)
	if err != nil {
		t.Fatalf("activate reprocessed descriptor: %v", err)
	}
	if previous != 1 || activated != 2 || asset.Version() != 3 ||
		asset.ActiveImageDescriptorRevision() != 2 {
		t.Fatalf(
			"activation identity=(previous=%d,active=%d,version=%d,pointer=%d)",
			previous,
			activated,
			asset.Version(),
			asset.ActiveImageDescriptorRevision(),
		)
	}
	revisions := asset.ImageDescriptorRevisions()
	if len(revisions) != 2 ||
		revisions[0].CleanupCandidateAt == nil ||
		revisions[1].ActivatedByRunID != "run-1" ||
		revisions[1].Descriptor.DerivativePolicyVersion != 2 {
		t.Fatalf("activation audit is incomplete: %+v", revisions)
	}

	if err := asset.RollbackImageDescriptorRevision(
		"run-1",
		previous,
		activated,
		createdAt.Add(3*time.Second),
	); err != nil {
		t.Fatalf("rollback descriptor revision: %v", err)
	}
	if asset.Version() != 4 || asset.ActiveImageDescriptorRevision() != 1 ||
		asset.ImageProcessingDescriptor().ImagePublicSliceKey != original.ImagePublicSliceKey {
		t.Fatalf("rollback did not restore the previous descriptor: %+v", asset.Snapshot())
	}
	if err := asset.RollbackImageDescriptorRevision(
		"run-1",
		previous,
		activated,
		createdAt.Add(4*time.Second),
	); err == nil {
		t.Fatal("stale rollback must not overwrite a restored pointer")
	}
	if _, err := RestoreMediaAsset(asset.Snapshot()); err != nil {
		t.Fatalf("restored revision history must validate: %v", err)
	}
}

func imageDescriptorForAssetVersion(
	assetID string,
	version int64,
	policyVersion int,
) ImageProcessingDescriptor {
	return ImageProcessingDescriptor{
		ProcessorProfile:         "content_image_normalization_v1",
		ImageWidth:               540,
		ImageHeight:              960,
		ImageDeliveryContentType: "image/jpeg",
		ImageNormalizedObjectKey: "private/" + assetID + "/v" + strconv.FormatInt(version, 10) + "/source.jpg",
		ImagePublicSliceKey: runtimemedia.BuildContentMediaPublicSliceKey(
			"image",
			assetID,
			version,
			"image/jpeg",
		),
		ImageDominantColor:      "#1A2B3C",
		ImageLQIP:               "data:image/jpeg;base64,/9j/2Q==",
		ImageContentProfile:     "photographic",
		DerivativePolicyVersion: policyVersion,
	}
}
