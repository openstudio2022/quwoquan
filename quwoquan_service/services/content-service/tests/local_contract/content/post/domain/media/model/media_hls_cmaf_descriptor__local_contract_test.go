// spec_ref: specs/feature-tree/runtime/runtime-media/spec.md#sit-002
package model_test

import (
	. "quwoquan_service/services/content-service/internal/content/post/domain/media/model"
	"testing"
	"time"
)

func TestReadyVideoPersistsCompleteHLSCMAFDescriptorAlongsideP0Fallback(t *testing.T) {
	now := time.Date(2026, 7, 28, 0, 0, 0, 0, time.UTC)
	asset := newProcessingVideoForHLSCMAF(t, "asset-hls-complete", now)
	prefix := "media/video/s/asset/asset-hls-complete/v2"
	descriptor := validVideoDescriptorForHLSCMAF(prefix)
	descriptor.HLSCMAFDescriptorVersion = 1
	descriptor.HLSCMAFDescriptorSliceKey = prefix + "/hls/descriptor.json"
	descriptor.HLSCMAFMasterManifestSliceKey = prefix + "/hls/master.m3u8"
	descriptor.HLSCMAFRenditionCount = 3

	if err := asset.RecordProcessingResult(
		ProcessingStatusReady,
		"",
		MediaProcessingDescriptor{Video: descriptor},
		now.Add(time.Second),
	); err != nil {
		t.Fatalf("record complete HLS/CMAF descriptor: %v", err)
	}
	restored, err := RestoreMediaAsset(asset.Snapshot())
	if err != nil {
		t.Fatalf("restore ready HLS/CMAF asset: %v", err)
	}
	got := restored.VideoProcessingDescriptor()
	if got.VideoPublicSliceKey != prefix+"/source.mp4" ||
		got.HLSCMAFDescriptorVersion != 1 ||
		got.HLSCMAFDescriptorSliceKey != prefix+"/hls/descriptor.json" ||
		got.HLSCMAFMasterManifestSliceKey != prefix+"/hls/master.m3u8" ||
		got.HLSCMAFRenditionCount != 3 {
		t.Fatalf("ready descriptor lost HLS/CMAF or P0 pairing: %+v", got)
	}
}

func TestReadyVideoRejectsPartialOrCrossVersionHLSCMAFDescriptor(t *testing.T) {
	now := time.Date(2026, 7, 28, 0, 0, 0, 0, time.UTC)
	prefix := "media/video/s/asset/asset-hls-invalid/v2"

	tests := map[string]func(*VideoProcessingDescriptor){
		"partial": func(descriptor *VideoProcessingDescriptor) {
			descriptor.HLSCMAFDescriptorVersion = 1
		},
		"cross_version": func(descriptor *VideoProcessingDescriptor) {
			descriptor.HLSCMAFDescriptorVersion = 1
			descriptor.HLSCMAFDescriptorSliceKey =
				"media/video/s/asset/asset-hls-invalid/v1/hls/descriptor.json"
			descriptor.HLSCMAFMasterManifestSliceKey = prefix + "/hls/master.m3u8"
			descriptor.HLSCMAFRenditionCount = 2
		},
		"unbounded_renditions": func(descriptor *VideoProcessingDescriptor) {
			descriptor.HLSCMAFDescriptorVersion = 1
			descriptor.HLSCMAFDescriptorSliceKey = prefix + "/hls/descriptor.json"
			descriptor.HLSCMAFMasterManifestSliceKey = prefix + "/hls/master.m3u8"
			descriptor.HLSCMAFRenditionCount = 5
		},
	}
	for name, mutate := range tests {
		t.Run(name, func(t *testing.T) {
			asset := newProcessingVideoForHLSCMAF(t, "asset-hls-invalid", now)
			descriptor := validVideoDescriptorForHLSCMAF(prefix)
			mutate(&descriptor)
			if err := asset.RecordProcessingResult(
				ProcessingStatusReady,
				"",
				MediaProcessingDescriptor{Video: descriptor},
				now.Add(time.Second),
			); err == nil {
				t.Fatalf("invalid HLS/CMAF descriptor must fail closed: %+v", descriptor)
			}
		})
	}
}

func newProcessingVideoForHLSCMAF(
	t *testing.T,
	assetID string,
	now time.Time,
) *MediaAsset {
	t.Helper()
	asset, err := CreateMediaAsset(CreateMediaAssetParams{
		ID:                 assetID,
		OwnerID:            "owner-hls",
		SourceSessionID:    "session-" + assetID,
		ObjectKey:          "uploads/" + assetID + "/source.mp4",
		SHA256:             "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
		MediaType:          "video",
		MimeType:           "video/mp4",
		FileSize:           4096,
		AccessPolicy:       AccessPolicyOwnerOnly,
		ProcessingRequired: true,
		Now:                now,
	})
	if err != nil {
		t.Fatalf("create HLS/CMAF test asset: %v", err)
	}
	return asset
}

func validVideoDescriptorForHLSCMAF(prefix string) VideoProcessingDescriptor {
	return VideoProcessingDescriptor{
		ProcessorProfile:             "content_processing_progressive_mp4",
		VerifiedDurationMs:           2_000,
		VideoWidth:                   540,
		VideoHeight:                  960,
		VideoCodec:                   "h264",
		VideoContainer:               "mp4",
		VideoAudioCodec:              "aac",
		VideoKeyframeIntervalMs:      2_000,
		VideoFastStart:               true,
		VideoPublicSliceKey:          prefix + "/source.mp4",
		CoverPublicSliceKey:          prefix + "/cover.jpg",
		PreviewTrackVersion:          1,
		PreviewTrackManifestSliceKey: prefix + "/preview/manifest.json",
	}
}
