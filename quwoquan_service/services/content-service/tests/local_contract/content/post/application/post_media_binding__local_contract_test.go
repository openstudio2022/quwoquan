package post_test

import (
	. "quwoquan_service/services/content-service/internal/content/post/application"
	"testing"

	postmodel "quwoquan_service/services/content-service/internal/content/post/domain/model"
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
	const coverDeliveryReference = coverSlice + "?variant=thumb"
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

	if err := ProjectBoundMediaAssets(post, assets, []string{"mas_video_001"}); err != nil {
		t.Fatalf("project bound media assets: %v", err)
	}

	if post.VideoUrl != videoSlice {
		t.Fatalf("video URL must be a canonical public slice: %q", post.VideoUrl)
	}
	if post.CoverUrl != coverDeliveryReference {
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

func TestProjectBoundMediaAssetsBindsDraftManualCoverAfterBothAssetsReady(t *testing.T) {
	post := &postmodel.Post{
		ContentType: "video",
		MediaItems: []map[string]any{
			{
				"mediaId":       "mas_video_002",
				"coverAssetId":  "mas_cover_002",
				"coverStrategy": "manual",
			},
		},
	}
	const videoSlice = "media/video/s/asset/mas_video_002/v2/source.mp4"
	const coverSlice = "media/image/s/asset/mas_cover_002/v2/source.jpg"
	assets := map[string]MediaAssetBindingSlice{
		"mas_video_002": {
			AssetID:             "mas_video_002",
			Ready:               true,
			ProcessingStatus:    "ready",
			MediaType:           "video",
			PublicSliceKey:      videoSlice,
			VideoPublicSliceKey: videoSlice,
			VerifiedDurationMs:  8_000,
			VideoWidth:          1080,
			VideoHeight:         1920,
		},
		"mas_cover_002": {
			AssetID:          "mas_cover_002",
			Ready:            true,
			ProcessingStatus: "ready",
			MediaType:        "image",
			PublicSliceKey:   coverSlice,
		},
	}

	if err := ProjectBoundMediaAssets(
		post,
		assets,
		[]string{"mas_video_002", "mas_cover_002"},
	); err != nil {
		t.Fatalf("project bound video and manual cover: %v", err)
	}

	if post.VideoUrl != videoSlice || post.CoverUrl != coverSlice ||
		post.ThumbnailUrl != coverSlice {
		t.Fatalf("manual cover did not use canonical image slice: %+v", post)
	}
	if len(post.MediaUrls) != 1 || post.MediaUrls[0] != videoSlice {
		t.Fatalf("cover-only image leaked into post media list: %+v", post.MediaUrls)
	}
	items, ok := post.MediaItems.([]map[string]any)
	if !ok || len(items) != 1 || items[0]["coverUrl"] != coverSlice {
		t.Fatalf("manual cover projection mismatch: %#v", post.MediaItems)
	}
}

func TestProjectBoundMediaAssetsRebuildsArticleManifestFromPublicSlices(
	t *testing.T,
) {
	post := &postmodel.Post{
		ContentType: "article",
		ArticleAssetManifest: map[string]any{
			"assets": []any{
				map[string]any{
					"assetId": "mas_article_cover",
					"role":    "cover",
				},
				map[string]any{
					"assetId": "mas_article_figure",
					"role":    "figure",
					"layout":  "wrapLeft",
					"caption": "配图",
				},
			},
		},
	}
	assets := map[string]MediaAssetBindingSlice{
		"mas_article_cover": {
			AssetID:        "mas_article_cover",
			Ready:          true,
			MediaType:      "image",
			PublicSliceKey: "media/image/s/asset/mas_article_cover/v2/source.webp",
		},
		"mas_article_figure": {
			AssetID:        "mas_article_figure",
			Ready:          true,
			MediaType:      "image",
			PublicSliceKey: "media/image/s/asset/mas_article_figure/v2/source.webp",
		},
	}
	if err := ProjectBoundMediaAssets(
		post,
		assets,
		[]string{"mas_article_cover", "mas_article_figure"},
	); err != nil {
		t.Fatalf("project article media: %v", err)
	}
	rows, ok := post.ArticleAssetManifest["assets"].([]map[string]any)
	if !ok || len(rows) != 2 {
		t.Fatalf(
			"article manifest rows were not rebuilt: %#v",
			post.ArticleAssetManifest,
		)
	}
	for _, row := range rows {
		if row["publicSliceKey"] == "" ||
			row["objectKey"] != nil ||
			row["localPath"] != nil {
			t.Fatalf("article manifest exposed storage authority: %#v", row)
		}
	}
	if rows[1]["layout"] != "wrapLeft" || rows[1]["caption"] != "配图" {
		t.Fatalf("article presentation metadata was lost: %#v", rows[1])
	}
}
