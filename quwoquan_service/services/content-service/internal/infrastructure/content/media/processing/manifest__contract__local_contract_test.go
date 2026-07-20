package processing

import (
	"encoding/json"
	"strings"
	"testing"

	mediamodel "quwoquan_service/services/content-service/internal/domain/media/model"
)

// TestPlanPreviewTrackStaysInsideManifestSchema pins every layout output to
// the constraints of preview_track_manifest.schema.json across the full legal
// duration range, including the 1h domain ceiling.
func TestPlanPreviewTrackStaysInsideManifestSchema(t *testing.T) {
	durations := []int64{
		1,
		4_999,
		5_000,
		5_001,
		125_000,                       // media-canary seek asset
		475_000,                       // exactly one full sprite (95 frames)
		476_000,                       // spills into a second sprite
		mediamodel.MaxVideoDurationMs, // 1h ceiling
	}
	for _, durationMs := range durations {
		plan, err := PlanPreviewTrack(durationMs)
		if err != nil {
			t.Fatalf("plan %dms: %v", durationMs, err)
		}
		if plan.FrameIntervalMs < 1000 || plan.FrameIntervalMs > 30000 {
			t.Fatalf("%dms: frame interval %d outside schema", durationMs, plan.FrameIntervalMs)
		}
		if len(plan.Frames) < 1 || len(plan.Frames) > 1000 {
			t.Fatalf("%dms: frame count %d outside schema", durationMs, len(plan.Frames))
		}
		if len(plan.Sprites) < 1 || len(plan.Sprites) > 64 {
			t.Fatalf("%dms: sprite count %d outside schema", durationMs, len(plan.Sprites))
		}
		expectedFrames := int((durationMs-1)/5000) + 1
		if len(plan.Frames) != expectedFrames {
			t.Fatalf(
				"%dms: expected %d frames at 5s cadence, got %d",
				durationMs,
				expectedFrames,
				len(plan.Frames),
			)
		}
		totalPlanned := 0
		for _, sprite := range plan.Sprites {
			if sprite.Width < 1 || sprite.Width > 8192 ||
				sprite.Height < 1 || sprite.Height > 8192 {
				t.Fatalf("%dms: sprite %d size %dx%d outside schema",
					durationMs, sprite.Index, sprite.Width, sprite.Height)
			}
			totalPlanned += sprite.FrameCount
		}
		if totalPlanned != len(plan.Frames) {
			t.Fatalf(
				"%dms: sprites plan %d frames but timeline has %d",
				durationMs,
				totalPlanned,
				len(plan.Frames),
			)
		}
		for index, frame := range plan.Frames {
			if frame.TimeMs != int64(index)*5000 {
				t.Fatalf("%dms: frame %d timeMs %d is not monotonic 5s cadence",
					durationMs, index, frame.TimeMs)
			}
			sprite := plan.Sprites[frame.SpriteIndex]
			if frame.X+plan.FrameWidth > sprite.Width ||
				frame.Y+plan.FrameHeight > sprite.Height {
				t.Fatalf("%dms: frame %d crop exceeds sprite %d bounds",
					durationMs, index, frame.SpriteIndex)
			}
		}
	}
}

func TestPlanPreviewTrackRejectsNonPositiveDuration(t *testing.T) {
	if _, err := PlanPreviewTrack(0); err == nil {
		t.Fatal("zero duration must be rejected")
	}
	if _, err := PlanPreviewTrack(-1); err == nil {
		t.Fatal("negative duration must be rejected")
	}
}

func TestEncodePreviewManifestMatchesDeliveryContract(t *testing.T) {
	plan, err := PlanPreviewTrack(480_000) // 96 frames -> 2 sprites
	if err != nil {
		t.Fatalf("plan: %v", err)
	}
	digest := "sha256:" + strings.Repeat("ab", 32)
	artifacts := []spriteArtifact{
		{
			PublicSliceKey: "media/video/s/asset-1/v2/preview/sprite-000.jpg",
			SHA256:         digest,
			Width:          plan.Sprites[0].Width,
			Height:         plan.Sprites[0].Height,
		},
		{
			PublicSliceKey: "media/video/s/asset-1/v2/preview/sprite-001.jpg",
			SHA256:         digest,
			Width:          plan.Sprites[1].Width,
			Height:         plan.Sprites[1].Height,
		},
	}
	payload, err := EncodePreviewManifest("asset-1", 2, ProcessorProfile, plan, artifacts)
	if err != nil {
		t.Fatalf("encode manifest: %v", err)
	}
	var decoded map[string]any
	if err := json.Unmarshal(payload, &decoded); err != nil {
		t.Fatalf("manifest is not valid JSON: %v", err)
	}
	if decoded["schema"] != "quwoquan.content.preview_track_manifest" {
		t.Fatalf("manifest schema constant drifted: %v", decoded["schema"])
	}
	if decoded["assetId"] != "asset-1" ||
		decoded["assetVersion"] != float64(2) ||
		decoded["trackVersion"] != float64(1) ||
		decoded["accessPolicy"] != "public" ||
		decoded["processorProfile"] != ProcessorProfile {
		t.Fatalf("manifest identity fields drifted: %v", decoded)
	}
	sprites := decoded["sprites"].([]any)
	if len(sprites) != 2 {
		t.Fatalf("expected 2 sprites, got %d", len(sprites))
	}
	firstSprite := sprites[0].(map[string]any)
	if firstSprite["spriteId"] != "sprite-000" ||
		firstSprite["mimeType"] != "image/jpeg" ||
		!strings.HasPrefix(firstSprite["publicSliceKey"].(string), "media/video/s/") {
		t.Fatalf("sprite entry drifted: %v", firstSprite)
	}
	frames := decoded["frames"].([]any)
	if len(frames) != 96 {
		t.Fatalf("expected 96 frames, got %d", len(frames))
	}
	lastFrame := frames[95].(map[string]any)
	if lastFrame["spriteId"] != "sprite-001" ||
		lastFrame["width"] != float64(240) ||
		lastFrame["height"] != float64(426) {
		t.Fatalf("frame entry drifted: %v", lastFrame)
	}
}

func TestEncodePreviewManifestRejectsSpriteMismatch(t *testing.T) {
	plan, err := PlanPreviewTrack(480_000)
	if err != nil {
		t.Fatalf("plan: %v", err)
	}
	if _, err := EncodePreviewManifest("asset-1", 2, ProcessorProfile, plan, nil); err == nil {
		t.Fatal("missing sprite artifacts must be rejected")
	}
}

func TestParseFFprobeOutputReadsStreamsAndFormat(t *testing.T) {
	raw := []byte(`{
		"streams": [
			{"codec_type": "video", "codec_name": "H264", "width": 540, "height": 960,
			 "avg_frame_rate": "30000/1001", "duration": "12.4"},
			{"codec_type": "audio", "codec_name": "AAC"}
		],
		"format": {"format_name": "mov,mp4,m4a,3gp,3g2,mj2", "duration": "12.480000"}
	}`)
	probe, err := ParseFFprobeOutput(raw)
	if err != nil {
		t.Fatalf("parse: %v", err)
	}
	if !probe.HasVideo || !probe.HasAudio {
		t.Fatalf("stream detection failed: %+v", probe)
	}
	if probe.VideoCodec != "h264" || probe.AudioCodec != "aac" {
		t.Fatalf("codec normalization failed: %+v", probe)
	}
	if probe.Width != 540 || probe.Height != 960 {
		t.Fatalf("dimension parse failed: %+v", probe)
	}
	if probe.DurationMs != 12_480 {
		t.Fatalf("format duration must win: %d", probe.DurationMs)
	}
	if probe.FrameRate < 29.9 || probe.FrameRate > 30.0 {
		t.Fatalf("frame rate parse failed: %f", probe.FrameRate)
	}
}

func TestParseFFprobeOutputHandlesMissingStreams(t *testing.T) {
	probe, err := ParseFFprobeOutput([]byte(`{"streams": [], "format": {}}`))
	if err != nil {
		t.Fatalf("parse: %v", err)
	}
	if probe.HasVideo || probe.HasAudio || probe.DurationMs != 0 {
		t.Fatalf("empty media must probe empty: %+v", probe)
	}
}
