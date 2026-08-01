package post_test

import (
	. "quwoquan_service/services/content-service/internal/content/post/application"
	"testing"

	postmodel "quwoquan_service/services/content-service/generated/content/post/contract/model"
)

func TestProjectBoundMediaAssetsReplacesClientDeliveryReferences(t *testing.T) {
	post := &postmodel.Post{
		ContentType: "video",
		MediaItems: []postmodel.PostMediaItem{{
			MediaAssetId: "mas_video_001",
			DurationMs:   12_000,
			Width:        1080,
			Height:       1920,
			Url:          "https://untrusted.example/video.mp4",
			CoverUrl:     "https://untrusted.example/cover.jpg",
		}},
	}
	const videoSlice = "media/video/s/asset/mas_video_001/v3/source.mp4"
	const coverSlice = "media/video/s/asset/mas_video_001/v3/cover.jpg"
	const hlsMasterSlice = "media/video/s/asset/mas_video_001/v3/hls/master.m3u8"
	const coverDeliveryReference = coverSlice + "?variant=thumb"
	assets := map[string]MediaAssetBindingSlice{
		"mas_video_001": {
			AssetID:                       "mas_video_001",
			Ready:                         true,
			MediaType:                     "video",
			MimeType:                      "video/mp4",
			Version:                       3,
			PublicSliceKey:                videoSlice,
			VerifiedDurationMs:            12500,
			VideoWidth:                    720,
			VideoHeight:                   1280,
			VideoPublicSliceKey:           videoSlice,
			CoverPublicSliceKey:           coverSlice,
			PreviewTrackVersion:           2,
			PreviewTrackManifestSliceKey:  "media/video/s/asset/mas_video_001/v3/storyboard.json",
			HLSCMAFDescriptorVersion:      1,
			HLSCMAFDescriptorSliceKey:     "media/video/s/asset/mas_video_001/v3/hls/descriptor.json",
			HLSCMAFMasterManifestSliceKey: hlsMasterSlice,
			HLSCMAFRenditionCount:         3,
			CoverFrameTimeMs:              400,
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
	items := post.MediaItems
	if len(items) != 1 {
		t.Fatalf("expected one projected media item, got %#v", post.MediaItems)
	}
	item := items[0]
	if item.Url != videoSlice {
		t.Fatalf("media item must replace client URL: %#v", item)
	}
	if item.CoverUrl != post.CoverUrl {
		t.Fatalf("media item must replace client cover URL: %#v", item)
	}
	if item.DurationMs != int64(12_500) || item.Width != 720 || item.Height != 1280 {
		t.Fatalf("video descriptor must replace unverified client metadata: %#v", item)
	}
	if item.MediaAssetId != "mas_video_001" || item.MediaAssetVersion != int64(3) ||
		item.PreviewTrackVersion != 2 ||
		item.PreviewTrackManifestUrl != "media/video/s/asset/mas_video_001/v3/storyboard.json" ||
		item.HlsCmafDescriptorVersion != 1 ||
		item.HlsCmafMasterManifestUrl != hlsMasterSlice {
		t.Fatalf("video identity and preview track must come from the asset: %#v", item)
	}
}

func TestProjectBoundMediaAssetsBindsDraftManualCoverAfterBothAssetsReady(t *testing.T) {
	post := &postmodel.Post{
		ContentType: "video",
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
			CoverStrategy:       "manual",
			ManualCoverAssetID:  "mas_cover_002",
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
	items := post.MediaItems
	if len(items) != 1 || items[0].CoverUrl != coverSlice {
		t.Fatalf("manual cover projection mismatch: %#v", post.MediaItems)
	}
}

func TestProjectBoundMediaAssetsRebuildsArticleManifestFromPublicSlices(
	t *testing.T,
) {
	post := &postmodel.Post{
		ContentType: "article",
		ArticleAssetManifest: postmodel.PostArticleAssetManifest{
			Assets: []postmodel.PostArticleAsset{
				{AssetId: "mas_article_cover", Role: "cover"},
				{AssetId: "mas_article_figure", Role: "figure", Layout: "wrapLeft", Caption: "配图"},
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
	rows := post.ArticleAssetManifest.Assets
	if len(rows) != 2 {
		t.Fatalf(
			"article manifest rows were not rebuilt: %#v",
			post.ArticleAssetManifest,
		)
	}
	for _, row := range rows {
		if row.PublicSliceKey == "" {
			t.Fatalf("article manifest exposed storage authority: %#v", row)
		}
	}
	if rows[1].Layout != "wrapLeft" || rows[1].Caption != "配图" {
		t.Fatalf("article presentation metadata was lost: %#v", rows[1])
	}
}
