package processing

import "testing"

func TestDeliverySliceKeysUseCanonicalRuntimeAssetIdentity(t *testing.T) {
	slices := deliverySliceKeys("mas_video_001", 3)
	const prefix = "media/video/s/asset/mas_video_001/v3"
	if slices.prefix != prefix ||
		slices.video != prefix+"/source.mp4" ||
		slices.cover != prefix+"/cover.jpg" ||
		slices.manifest != prefix+"/preview/manifest.json" ||
		slices.sprite(7) != prefix+"/preview/sprite-007.jpg" {
		t.Fatalf("video delivery slices drifted from runtime canonical root: %#v", slices)
	}
}
