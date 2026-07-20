package processing

import (
	"encoding/json"
	"fmt"
)

// Preview track geometry mirrors the media-canary reference profile
// (quwoquan_data/reference/media_canary/video_playback.yaml) so data-imported
// and UGC videos share one delivery contract. All values stay inside
// contracts/metadata/content/media_asset/preview_track_manifest.schema.json:
// frameIntervalMs 1000..30000, sprites<=64, frames<=1000, sprite边长<=8192。
const (
	previewFrameIntervalMs = 5000
	previewFrameWidth      = 240
	previewFrameHeight     = 426
	previewColumns         = 5
	// 19 行 × 426px = 8094 < schema 上限 8192。
	previewMaxRowsPerSprite = 19
	previewMaxFramesSprite  = previewColumns * previewMaxRowsPerSprite

	previewManifestSchema = "quwoquan.content.preview_track_manifest"
	previewTrackVersion   = 1
)

// PreviewFramePlan positions one timeline frame inside a sprite atlas.
type PreviewFramePlan struct {
	TimeMs      int64
	SpriteIndex int
	X           int
	Y           int
}

// PreviewSpritePlan sizes one sprite atlas.
type PreviewSpritePlan struct {
	Index      int
	FrameCount int
	Width      int
	Height     int
}

// PreviewTrackPlan is the deterministic layout for a duration. It is a pure
// function of durationMs so tests can pin every schema constraint.
type PreviewTrackPlan struct {
	FrameIntervalMs int
	FrameWidth      int
	FrameHeight     int
	Frames          []PreviewFramePlan
	Sprites         []PreviewSpritePlan
}

// PlanPreviewTrack lays frames sampled every previewFrameIntervalMs into
// 5-column sprite atlases. At the 1h domain ceiling this yields 720 frames in
// 8 sprites, comfortably inside the manifest schema limits.
func PlanPreviewTrack(durationMs int64) (PreviewTrackPlan, error) {
	if durationMs <= 0 {
		return PreviewTrackPlan{}, fmt.Errorf("preview track requires positive duration, got %d", durationMs)
	}
	frameCount := int((durationMs-1)/previewFrameIntervalMs) + 1
	if frameCount < 1 {
		frameCount = 1
	}
	plan := PreviewTrackPlan{
		FrameIntervalMs: previewFrameIntervalMs,
		FrameWidth:      previewFrameWidth,
		FrameHeight:     previewFrameHeight,
		Frames:          make([]PreviewFramePlan, 0, frameCount),
	}
	for index := 0; index < frameCount; index++ {
		spriteIndex := index / previewMaxFramesSprite
		frameInSprite := index % previewMaxFramesSprite
		plan.Frames = append(plan.Frames, PreviewFramePlan{
			TimeMs:      int64(index) * previewFrameIntervalMs,
			SpriteIndex: spriteIndex,
			X:           (frameInSprite % previewColumns) * previewFrameWidth,
			Y:           (frameInSprite / previewColumns) * previewFrameHeight,
		})
	}
	spriteCount := (frameCount + previewMaxFramesSprite - 1) / previewMaxFramesSprite
	for index := 0; index < spriteCount; index++ {
		framesInSprite := previewMaxFramesSprite
		if index == spriteCount-1 {
			framesInSprite = frameCount - index*previewMaxFramesSprite
		}
		columns := previewColumns
		if framesInSprite < previewColumns {
			columns = framesInSprite
		}
		rows := (framesInSprite + previewColumns - 1) / previewColumns
		plan.Sprites = append(plan.Sprites, PreviewSpritePlan{
			Index:      index,
			FrameCount: framesInSprite,
			Width:      columns * previewFrameWidth,
			Height:     rows * previewFrameHeight,
		})
	}
	return plan, nil
}

type manifestSprite struct {
	SpriteID       string `json:"spriteId"`
	PublicSliceKey string `json:"publicSliceKey"`
	MimeType       string `json:"mimeType"`
	SHA256         string `json:"sha256"`
	Width          int    `json:"width"`
	Height         int    `json:"height"`
}

type manifestFrame struct {
	TimeMs   int64  `json:"timeMs"`
	SpriteID string `json:"spriteId"`
	X        int    `json:"x"`
	Y        int    `json:"y"`
	Width    int    `json:"width"`
	Height   int    `json:"height"`
}

type previewManifest struct {
	Schema           string           `json:"schema"`
	AssetID          string           `json:"assetId"`
	AssetVersion     int64            `json:"assetVersion"`
	TrackVersion     int              `json:"trackVersion"`
	ProcessorProfile string           `json:"processorProfile"`
	AccessPolicy     string           `json:"accessPolicy"`
	FrameIntervalMs  int              `json:"frameIntervalMs"`
	Sprites          []manifestSprite `json:"sprites"`
	Frames           []manifestFrame  `json:"frames"`
}

type spriteArtifact struct {
	PublicSliceKey string
	SHA256         string
	Width          int
	Height         int
}

func previewSpriteID(index int) string {
	return fmt.Sprintf("sprite-%03d", index)
}

// EncodePreviewManifest renders the delivery manifest JSON. The manifest is a
// public delivery artifact bound to (assetId, trackVersion); assetVersion
// records the aggregate version the processing result was applied to.
func EncodePreviewManifest(
	assetID string,
	assetVersion int64,
	processorProfile string,
	plan PreviewTrackPlan,
	sprites []spriteArtifact,
) ([]byte, error) {
	if len(sprites) != len(plan.Sprites) {
		return nil, fmt.Errorf(
			"preview manifest sprite artifacts (%d) do not match plan (%d)",
			len(sprites),
			len(plan.Sprites),
		)
	}
	manifest := previewManifest{
		Schema:           previewManifestSchema,
		AssetID:          assetID,
		AssetVersion:     assetVersion,
		TrackVersion:     previewTrackVersion,
		ProcessorProfile: processorProfile,
		AccessPolicy:     "public",
		FrameIntervalMs:  plan.FrameIntervalMs,
		Sprites:          make([]manifestSprite, 0, len(sprites)),
		Frames:           make([]manifestFrame, 0, len(plan.Frames)),
	}
	for index, sprite := range sprites {
		manifest.Sprites = append(manifest.Sprites, manifestSprite{
			SpriteID:       previewSpriteID(index),
			PublicSliceKey: sprite.PublicSliceKey,
			MimeType:       "image/jpeg",
			SHA256:         sprite.SHA256,
			Width:          sprite.Width,
			Height:         sprite.Height,
		})
	}
	for _, frame := range plan.Frames {
		manifest.Frames = append(manifest.Frames, manifestFrame{
			TimeMs:   frame.TimeMs,
			SpriteID: previewSpriteID(frame.SpriteIndex),
			X:        frame.X,
			Y:        frame.Y,
			Width:    plan.FrameWidth,
			Height:   plan.FrameHeight,
		})
	}
	return json.Marshal(manifest)
}
