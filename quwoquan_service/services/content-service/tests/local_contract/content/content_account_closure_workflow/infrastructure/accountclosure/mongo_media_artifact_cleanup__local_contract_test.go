// spec_ref: specs/feature-tree/user-identity-profile-relationship/settings-and-device-token/account-lifecycle-self-service-account-closure/spec.md#gwt-003
// spec_ref: specs/feature-tree/user-identity-profile-relationship/settings-and-device-token/account-lifecycle-self-service-account-closure/spec.md#gwt-004
package accountclosure_test

import (
	"slices"
	"testing"

	. "quwoquan_service/services/content-service/internal/content/content_account_closure_workflow/infrastructure/accountclosure"

	mediamodel "quwoquan_service/services/content-service/internal/media/media_asset/domain/model"
)

// spec_ref: GWT-004
func TestMediaArtifactWorkCapturesAllKnownDeliveryAndPrivateArtifacts(
	t *testing.T,
) {
	row := MediaArtifactClosureRow{
		ID:                           "asset-closure-1",
		ObjectKey:                    "media/objects/sha256/aa/bb/source.jpg",
		ImageNormalizedObjectKey:     "media/processed/image/asset-closure-1/v1/source.jpg",
		ImagePublicSliceKey:          "media/image/s/asset/asset-closure-1/v1/source.jpg",
		VideoPublicSliceKey:          "media/video/s/asset/asset-closure-1/v1/source.mp4",
		CoverPublicSliceKey:          "media/video/s/asset/asset-closure-1/v1/cover.jpg",
		PreviewTrackManifestSliceKey: "media/video/s/asset/asset-closure-1/v1/preview/manifest.json",
		ImageDescriptorRevisions: []mediamodel.ImageDescriptorRevision{{
			Descriptor: mediamodel.ImageProcessingDescriptor{
				ImageNormalizedObjectKey: "media/processed/image/asset-closure-1/v2/source.jpg",
				ImagePublicSliceKey:      "media/image/s/asset/asset-closure-1/v2/source.jpg",
			},
		}},
	}

	work := NewMediaArtifactWorkDocument("event-closure-1", row)

	for _, key := range []string{
		"media/image/s/asset/asset-closure-1/v1/source.jpg",
		"media/image/s/asset/asset-closure-1/v2/source.jpg",
		"media/video/s/asset/asset-closure-1/v1/preview/manifest.json",
	} {
		if !slices.Contains(work.PublicSliceKeys, key) {
			t.Fatalf("missing public artifact %q: %+v", key, work)
		}
	}
	for _, key := range []string{
		"media/objects/sha256/aa/bb/source.jpg",
		"media/processed/image/asset-closure-1/v1/source.jpg",
		"media/processed/image/asset-closure-1/v2/source.jpg",
	} {
		if !slices.Contains(work.PrivateObjectKeys, key) {
			t.Fatalf("missing private artifact %q: %+v", key, work)
		}
	}
	if !slices.Contains(
		work.PublicPrefixes,
		"media/video/s/asset/asset-closure-1/",
	) || !slices.Contains(
		work.PrivatePrefixes,
		"media/processed/image/asset-closure-1/",
	) {
		t.Fatalf("asset-scoped deletion prefixes missing: %+v", work)
	}
}
