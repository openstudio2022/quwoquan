// spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-002
// spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-032
// release 媒体显式公开交付，稳定资产身份、poster 绑定与缺席语义不因类别移除而丢失。
package releaseimport_test

import (
	"strings"
	"testing"

	"go.mongodb.org/mongo-driver/v2/bson"

	postmodel "quwoquan_service/services/content-service/generated/content/post/contract/model"
	postports "quwoquan_service/services/content-service/internal/content/post/domain/ports"
	. "quwoquan_service/services/content-service/internal/content/post/infrastructure/releaseimport"
)

// spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-043
func TestImportedImageCaptionsReachQueryDTOWithoutReordering(t *testing.T) {
	media := ImportedMediaFields([]AssetManifestItem{
		{AssetID: "b", Kind: "image", CDNURL: "https://img.example/b.jpg", Caption: "先展示的图", AccessMode: "public"},
		{AssetID: "a", Kind: "image", CDNURL: "https://img.example/a.jpg", AccessMode: "public"},
	}, "public")
	raw, err := bson.Marshal(bson.M{"mediaItems": media.MediaItems})
	if err != nil {
		t.Fatal(err)
	}
	var query postports.PostDetailSlice
	if err := bson.Unmarshal(raw, &query); err != nil {
		t.Fatal(err)
	}
	if len(query.MediaItems) != 2 || query.MediaItems[0].MediaAssetID != "b" || query.MediaItems[1].MediaAssetID != "a" ||
		query.MediaItems[0].Caption != "先展示的图" || query.MediaItems[1].Caption != "" || query.MediaItems[0].AccessMode != "public" {
		t.Fatalf("importer -> query DTO lost order or caption: %#v", query.MediaItems)
	}
	if _, exists := media.MediaItems[1]["caption"]; exists {
		t.Fatal("missing caption must not be fabricated")
	}
}

func videoWithPosterAssets() []AssetManifestItem {
	return []AssetManifestItem{
		{
			AssetID: "clip_main", Kind: "video", Version: 3,
			CDNURL:        "https://video.example.test/media/video/s/asset/clip_main/v3/source.mp4",
			CoverURL:      "https://image.example.test/media/image/s/asset/poster_main/v1/source.webp",
			ThumbnailURL:  "https://image.example.test/media/image/s/asset/poster_main/v1/source.webp",
			PosterAssetID: "poster_main", DurationMs: 12000, AccessMode: MediaDeliveryAccessModePublic,
		},
		{
			AssetID: "poster_main", Kind: "image", Version: 1, Role: "cover",
			CDNURL:     "https://image.example.test/media/image/s/asset/poster_main/v1/source.webp",
			AccessMode: MediaDeliveryAccessModePublic,
		},
	}
}

func TestReleaseMediaBindingRequiresNoCategory(t *testing.T) {
	if err := ValidateImportedPostMediaBindings([]PostDoc{{PostRef: "posts/video/public/1", Assets: videoWithPosterAssets()}}); err != nil {
		t.Fatalf("default public release must require no category: %v", err)
	}
}

func TestImportedMediaFieldsWriteCanonicalPerMediaDeliveryBinding(t *testing.T) {
	media := ImportedMediaFields(videoWithPosterAssets(), MediaDeliveryAccessModePublic)
	if len(media.MediaItems) != 2 {
		t.Fatalf("mediaItems = %#v, want video + poster", media.MediaItems)
	}
	raw, err := bson.Marshal(bson.M{"mediaItems": media.MediaItems})
	if err != nil {
		t.Fatal(err)
	}
	var typed struct {
		MediaItems []postmodel.PostMediaItem `bson:"mediaItems"`
	}
	if err := bson.Unmarshal(raw, &typed); err != nil {
		t.Fatal(err)
	}
	video, poster := typed.MediaItems[0], typed.MediaItems[1]
	if video.MediaAssetId != "clip_main" || video.MediaAssetVersion != 3 || video.AccessMode != "public" || video.CoverAssetId != "poster_main" {
		t.Fatalf("video delivery binding drifted: %+v", video)
	}
	if poster.MediaAssetId != "poster_main" || poster.AccessMode != "public" || poster.CoverAssetId != "" {
		t.Fatalf("poster delivery binding drifted: %+v", poster)
	}
	for index, item := range media.MediaItems {
		for _, drifted := range []string{"assetId", "version", "publicSliceKey"} {
			if _, exists := item[drifted]; exists {
				t.Fatalf("mediaItems[%d] writes drifted key %q", index, drifted)
			}
		}
	}
	if len(media.MediaAssetIDs) != 2 || media.MediaAssetIDs[0] != "clip_main" || media.MediaAssetIDs[1] != "poster_main" {
		t.Fatalf("mediaAssetIds = %#v, want video and poster", media.MediaAssetIDs)
	}
}

func TestValidateImportedPostMediaBindingsRejectsNullUnknownSignedAssetAndPrivateHLS(t *testing.T) {
	for _, test := range []struct {
		name   string
		mutate func(*AssetManifestItem)
		want   string
	}{
		{"null accessMode", func(a *AssetManifestItem) { a.AccessMode = "" }, "accessMode must be public"},
		{"unknown accessMode", func(a *AssetManifestItem) { a.AccessMode = "private" }, "accessMode must be public"},
		{"missing asset identity", func(a *AssetManifestItem) { a.AssetID = "" }, "requires assetId"},
		{"signed progressive MP4", func(a *AssetManifestItem) { a.AccessMode = "signed_grant" }, "accessMode must be public"},
		{"private HLS m3u8", func(a *AssetManifestItem) {
			a.AccessMode = "signed_grant"
			a.CDNURL = "media/objects/private/master.m3u8"
		}, "accessMode must be public"},
		{"private DASH mime", func(a *AssetManifestItem) { a.AccessMode = "signed_grant"; a.MimeType = "application/dash+xml" }, "accessMode must be public"},
	} {
		t.Run(test.name, func(t *testing.T) {
			post := PostDoc{PostRef: "posts/video/public/1", Assets: videoWithPosterAssets()}
			test.mutate(&post.Assets[0])
			if err := ValidateImportedPostMediaBindings([]PostDoc{post}); err == nil || !strings.Contains(err.Error(), test.want) {
				t.Fatalf("want %q rejection, got %v", test.want, err)
			}
		})
	}
}

func TestValidateImportedPostMediaBindingsChecksArticleAssetsIndependently(t *testing.T) {
	post := PostDoc{PostRef: "posts/article/public/1", Assets: videoWithPosterAssets(), ArticleAssetManifest: &ArticleAssetManifestDoc{Assets: []AssetManifestItem{{AssetID: "article_cover", AccessMode: "signed_grant"}}}}
	if err := ValidateImportedPostMediaBindings([]PostDoc{post}); err == nil {
		t.Fatal("private article asset must not bypass release validation")
	}
	post.ArticleAssetManifest.Assets[0].AccessMode = MediaDeliveryAccessModePublic
	if err := ValidateImportedPostMediaBindings([]PostDoc{post}); err != nil {
		t.Fatal(err)
	}
}

func TestBindPostAuthorSnapshotsProjectsAvatarAssetIdentity(t *testing.T) {
	posts := []PostDoc{
		{PostRef: "posts/article/体验/带头像/1", AuthorID: "builtin_with_avatar"},
		{PostRef: "posts/article/体验/无头像/1", AuthorID: "builtin_without_avatar"},
	}
	err := BindPostAuthorSnapshots(posts, map[string]CreatorAuthorSnapshot{
		"builtin_with_avatar":    {AuthorID: "builtin_with_avatar", DisplayName: "旅行博主", AvatarURL: "https://avatar.example.test/media/avatar/s/asset/avatar_travel_blogger/v1/source.webp", AvatarAssetID: "avatar_travel_blogger"},
		"builtin_without_avatar": {AuthorID: "builtin_without_avatar", DisplayName: "无头像作者"},
	})
	if err != nil {
		t.Fatal(err)
	}
	if posts[0].AuthorAvatarAssetID != "avatar_travel_blogger" || posts[1].AuthorAvatarAssetID != "" {
		t.Fatalf("avatar identity drifted: %+v", posts)
	}
}

func TestApplyImportedAuthorAvatarDeliveryFields(t *testing.T) {
	withAvatar := bson.M{}
	ApplyImportedAuthorAvatarDeliveryFields(withAvatar, PostDoc{AuthorAvatarAssetID: "avatar_travel_blogger"}, MediaDeliveryAccessModePublic)
	if withAvatar["authorAvatarAssetId"] != "avatar_travel_blogger" || withAvatar["authorAvatarAccessMode"] != "public" {
		t.Fatalf("avatar binding drifted: %#v", withAvatar)
	}
	withoutAvatar := bson.M{"authorAvatarAssetId": "stale_asset", "authorAvatarAccessMode": "signed_grant"}
	ApplyImportedAuthorAvatarDeliveryFields(withoutAvatar, PostDoc{}, MediaDeliveryAccessModePublic)
	if withoutAvatar["authorAvatarAssetId"] != nil || withoutAvatar["authorAvatarAccessMode"] != nil {
		t.Fatalf("absent avatar retained stale fields: %#v", withoutAvatar)
	}
	missingMode := bson.M{}
	ApplyImportedAuthorAvatarDeliveryFields(missingMode, PostDoc{AuthorAvatarAssetID: "avatar_travel_blogger"}, "")
	if missingMode["authorAvatarAssetId"] != "avatar_travel_blogger" || missingMode["authorAvatarAccessMode"] != nil {
		t.Fatalf("missing explicit mode must remain absent: %#v", missingMode)
	}
}
