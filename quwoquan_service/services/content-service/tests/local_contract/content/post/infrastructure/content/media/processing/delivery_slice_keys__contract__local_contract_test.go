package processing_test

import (
	. "quwoquan_service/services/content-service/internal/content/post/infrastructure/content/media/processing"
	"testing"
)

func TestDeliverySliceKeysUseCanonicalRuntimeAssetIdentity(t *testing.T) {
	slices := DeliverySliceKeys("mas_video_001", 3)
	const prefix = "media/video/s/asset/mas_video_001/v3"
	if slices.Prefix != prefix ||
		slices.Video != prefix+"/source.mp4" ||
		slices.Cover != prefix+"/cover.jpg" ||
		slices.Manifest != prefix+"/preview/manifest.json" ||
		slices.Sprite(7) != prefix+"/preview/sprite-007.jpg" {
		t.Fatalf("video delivery slices drifted from runtime canonical root: %#v", slices)
	}
}
