// spec_ref: specs/feature-tree/user-identity-profile-relationship/settings-and-device-token/account-lifecycle-self-service-account-closure/spec.md#gwt-004
package mediaprocessing_test

import (
	"slices"
	"testing"

	mediaprocessing "quwoquan_service/services/content-service/internal/content/post/application/media/processing"
)

// spec_ref: GWT-004
func TestArtifactCleanupPlanIsCompleteAndStable(t *testing.T) {
	source := mediaprocessing.ArtifactCleanupSource{
		AssetID:                      "asset-cleanup-1",
		ObjectKey:                    "media/objects/sha256/aa/bb/source.jpg",
		ImageNormalizedObjectKey:     "media/processed/image/asset-cleanup-1/v1/source.jpg",
		ImagePublicSliceKey:          "media/image/s/asset/asset-cleanup-1/v1/source.jpg",
		VideoPublicSliceKey:          "media/video/s/asset/asset-cleanup-1/v1/source.mp4",
		CoverPublicSliceKey:          "media/video/s/asset/asset-cleanup-1/v1/cover.jpg",
		PreviewTrackManifestSliceKey: "media/video/s/asset/asset-cleanup-1/v1/preview/manifest.json",
		HistoricalImageArtifacts: []mediaprocessing.ImageArtifactSource{{
			NormalizedObjectKey: "media/processed/image/asset-cleanup-1/v2/source.jpg",
			PublicSliceKey:      "media/image/s/asset/asset-cleanup-1/v2/source.jpg",
		}},
	}

	first := mediaprocessing.PlanArtifactCleanup("event-cleanup-1", source)
	second := mediaprocessing.PlanArtifactCleanup("event-cleanup-1", source)
	if first.WorkID == "" || first.WorkID != second.WorkID {
		t.Fatalf("cleanup work identity is not stable: first=%q second=%q", first.WorkID, second.WorkID)
	}
	if !slices.Contains(
		first.PublicSliceKeys,
		"media/image/s/asset/asset-cleanup-1/v2/source.jpg",
	) {
		t.Fatalf("cleanup plan omitted historical public artifact: %+v", first)
	}
	if !slices.Contains(
		first.PrivateObjectKeys,
		"media/processed/image/asset-cleanup-1/v2/source.jpg",
	) {
		t.Fatalf("cleanup plan omitted historical private artifact: %+v", first)
	}
	if !slices.Contains(
		first.PublicPrefixes,
		"media/video/s/asset/asset-cleanup-1/",
	) {
		t.Fatalf("cleanup plan omitted public bounded prefix: %+v", first)
	}
	if !slices.Contains(
		first.PrivatePrefixes,
		"media/processed/image/asset-cleanup-1/",
	) {
		t.Fatalf("cleanup plan omitted private bounded prefix: %+v", first)
	}
}
