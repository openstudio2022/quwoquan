// spec_ref: specs/feature-tree/runtime/runtime-media/spec.md#sit-002
package processing_test

import (
	. "quwoquan_service/services/content-service/internal/content/post/infrastructure/content/media/processing"
	"testing"
)

func TestHLSCMAFLadderIsBoundedAlignedAndNeverUpscales(t *testing.T) {
	renditions, err := PlanHLSCMAFRenditions(540, 960)
	if err != nil {
		t.Fatalf("plan portrait HLS/CMAF ladder: %v", err)
	}
	if len(renditions) != 3 {
		t.Fatalf("portrait ladder count=%d, want 3: %+v", len(renditions), renditions)
	}
	previousHeight := 0
	previousBitrate := 0
	for _, rendition := range renditions {
		if rendition.Width <= 0 || rendition.Height <= 0 ||
			rendition.Width%2 != 0 || rendition.Height%2 != 0 {
			t.Fatalf("rendition dimensions must be positive and codec-aligned: %+v", rendition)
		}
		if rendition.Width > 540 || rendition.Height > 960 {
			t.Fatalf("rendition must not upscale the source: %+v", rendition)
		}
		if rendition.Height <= previousHeight || rendition.VideoBitrateBPS <= previousBitrate {
			t.Fatalf("rendition ladder must increase monotonically: %+v", renditions)
		}
		if rendition.AudioBitrateBPS <= 0 {
			t.Fatalf("rendition must declare an AAC bitrate: %+v", rendition)
		}
		previousHeight = rendition.Height
		previousBitrate = rendition.VideoBitrateBPS
	}
}

func TestHLSCMAFLadderUsesOneSourceSizedRenditionForSmallVideo(t *testing.T) {
	renditions, err := PlanHLSCMAFRenditions(240, 320)
	if err != nil {
		t.Fatalf("plan small HLS/CMAF ladder: %v", err)
	}
	if len(renditions) != 1 || renditions[0].Width != 240 || renditions[0].Height != 320 {
		t.Fatalf("small source must not be upscaled: %+v", renditions)
	}
}

func TestHLSCMAFLadderRejectsMissingSourceDimensions(t *testing.T) {
	for _, size := range [][2]int{{0, 960}, {540, 0}, {-1, 960}} {
		if _, err := PlanHLSCMAFRenditions(size[0], size[1]); err == nil {
			t.Fatalf("dimensions %v must fail closed", size)
		}
	}
}
