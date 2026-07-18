package post

import (
	"testing"

	postmodel "quwoquan_service/services/content-service/internal/domain/post/model"
)

func TestProjectBoundMediaAssetsKeepsPresentationMetadataButReplacesClientURLs(t *testing.T) {
	post := &postmodel.Post{
		ContentType: "video",
		MediaItems: []map[string]any{
			{
				"mediaId":    "mas_video_001",
				"durationMs": int64(12_000),
				"width":      int64(1080),
				"height":     int64(1920),
				"url":        "https://untrusted.example/video.mp4",
				"coverUrl":   "https://untrusted.example/cover.jpg",
				"unexpected": "must-not-survive",
			},
		},
	}
	const videoSlice = "media/video/s/asset/mas_video_001/v3/source.mp4"
	const coverSlice = "media/video/s/asset/mas_video_001/v3/cover.jpg"
	assets := map[string]MediaAssetBindingSlice{
		"mas_video_001": {
			AssetID:                      "mas_video_001",
			Ready:                        true,
			MediaType:                    "video",
			ContentType:                  "video/mp4",
			Version:                      3,
			PublicSliceKey:               videoSlice,
			VerifiedDurationMs:           12500,
			VideoWidth:                   720,
			VideoHeight:                  1280,
			VideoPublicSliceKey:          videoSlice,
			CoverPublicSliceKey:          coverSlice,
			PreviewTrackVersion:          2,
			PreviewTrackManifestSliceKey: "media/video/s/asset/mas_video_001/v3/storyboard.json",
			CoverFrameTimeMs:             400,
		},
	}

	if err := projectBoundMediaAssets(post, assets, []string{"mas_video_001"}); err != nil {
		t.Fatalf("project bound media assets: %v", err)
	}

	if post.VideoUrl != videoSlice {
		t.Fatalf("video URL must be a canonical public slice: %q", post.VideoUrl)
	}
	if post.CoverUrl != coverSlice {
		t.Fatalf("cover URL must be the verified VOD cover slice: %q", post.CoverUrl)
	}
	items, ok := post.MediaItems.([]map[string]any)
	if !ok || len(items) != 1 {
		t.Fatalf("expected one projected media item, got %#v", post.MediaItems)
	}
	item := items[0]
	if item["url"] != videoSlice {
		t.Fatalf("media item must replace client URL: %#v", item)
	}
	if item["coverUrl"] != post.CoverUrl {
		t.Fatalf("media item must replace client cover URL: %#v", item)
	}
	if item["durationMs"] != int64(12_500) || item["width"] != 720 || item["height"] != 1280 {
		t.Fatalf("video descriptor must replace unverified client metadata: %#v", item)
	}
	if item["mediaAssetId"] != "mas_video_001" || item["mediaAssetVersion"] != int64(3) ||
		item["previewTrackVersion"] != 2 ||
		item["previewTrackManifestUrl"] != "media/video/s/asset/mas_video_001/v3/storyboard.json" {
		t.Fatalf("video identity and preview track must come from the asset: %#v", item)
	}
	if _, found := item["unexpected"]; found {
		t.Fatalf("unapproved client metadata must not survive projection: %#v", item)
	}
}
