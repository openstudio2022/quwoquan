// spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-016
//
// data release importer 的逐媒体交付绑定（DEC-033，OPEN-015 缺陷回归）：
// mediaItems 必须用 canonical BSON 键（mediaAssetId/mediaAssetVersion）落库、
// 按 releaseClass 写 accessMode、为 video poster 写配对 coverAssetId，且
// posts.mediaAssetIds 覆盖含 poster 在内的全部媒体资产标识；作者头像的
// avatarAssetId 绑定自 release creator profile，禁止以 authorId 冒充。
package releaseimport_test

import (
	"strings"
	"testing"

	"go.mongodb.org/mongo-driver/v2/bson"

	postmodel "quwoquan_service/services/content-service/generated/content/post/contract/model"
	postports "quwoquan_service/services/content-service/internal/content/post/domain/ports"
	. "quwoquan_service/services/content-service/internal/content/post/infrastructure/releaseimport"
)

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

func TestMediaDeliveryAccessModeForReleaseClass(t *testing.T) {
	cases := []struct {
		releaseClass string
		want         string
	}{
		{releaseClass: "production", want: "public"},
		{releaseClass: "research", want: ""},
		{releaseClass: "commercial", want: ""},
		// 未声明/未知类别返回 invalid sentinel；新 release validator 必须拒绝。
		{releaseClass: "", want: ""},
		{releaseClass: "unknown_class", want: ""},
	}
	for _, testCase := range cases {
		got := MediaDeliveryAccessModeForReleaseClass(testCase.releaseClass)
		if got != testCase.want {
			t.Fatalf(
				"MediaDeliveryAccessModeForReleaseClass(%q) = %q, want %q",
				testCase.releaseClass,
				got,
				testCase.want,
			)
		}
	}
}

func videoWithPosterAssets() []AssetManifestItem {
	return []AssetManifestItem{
		{
			AssetID:       "clip_main",
			Kind:          "video",
			Version:       3,
			CDNURL:        "media/objects/sha256/aa/bb/clip.mp4",
			CoverURL:      "media/objects/sha256/cc/dd/poster.webp",
			ThumbnailURL:  "media/objects/sha256/cc/dd/poster.webp",
			PosterAssetID: "poster_main",
			DurationMs:    12000,
		},
		{
			AssetID: "poster_main",
			Kind:    "image",
			Version: 1,
			Role:    "cover",
			CDNURL:  "media/objects/sha256/cc/dd/poster.webp",
		},
	}
}

// mediaItems 落库后必须能被 canonical typed 模型逐项读出资产标识——这是
// OPEN-015 记录的 BSON 键漂移（旧键 assetId/version 导致 typed 读取缺席）的回归。
func TestImportedMediaFieldsWriteCanonicalPerMediaDeliveryBinding(t *testing.T) {
	media := ImportedMediaFields(videoWithPosterAssets(), "signed_grant")
	if len(media.MediaItems) != 2 {
		t.Fatalf("mediaItems = %#v, want video + poster", media.MediaItems)
	}

	raw, err := bson.Marshal(bson.M{"mediaItems": media.MediaItems})
	if err != nil {
		t.Fatalf("marshal imported mediaItems: %v", err)
	}
	var typed struct {
		MediaItems []postmodel.PostMediaItem `bson:"mediaItems"`
	}
	if err := bson.Unmarshal(raw, &typed); err != nil {
		t.Fatalf("typed decode imported mediaItems: %v", err)
	}
	video := typed.MediaItems[0]
	if video.MediaAssetId != "clip_main" || video.MediaAssetVersion != 3 {
		t.Fatalf("typed per-media identity is absent after import: %+v", video)
	}
	if video.AccessMode != "signed_grant" {
		t.Fatalf("video accessMode = %q, want signed_grant", video.AccessMode)
	}
	if video.CoverAssetId != "poster_main" {
		t.Fatalf("video poster coverAssetId = %q, want poster_main", video.CoverAssetId)
	}
	poster := typed.MediaItems[1]
	if poster.MediaAssetId != "poster_main" || poster.AccessMode != "signed_grant" {
		t.Fatalf("poster delivery binding is absent: %+v", poster)
	}
	if poster.CoverAssetId != "" {
		t.Fatalf("image item must not carry coverAssetId, got %q", poster.CoverAssetId)
	}

	// canonical 单轨：旧漂移键不得再出现在落库 item 中。
	for index, item := range media.MediaItems {
		for _, drifted := range []string{"assetId", "version", "publicSliceKey"} {
			if _, exists := item[drifted]; exists {
				t.Fatalf("mediaItems[%d] still writes drifted key %q: %#v", index, drifted, item)
			}
		}
	}

	// grant 侧 release membership 判定输入：poster 的资产标识必须进 mediaAssetIds。
	if len(media.MediaAssetIDs) != 2 ||
		media.MediaAssetIDs[0] != "clip_main" || media.MediaAssetIDs[1] != "poster_main" {
		t.Fatalf("mediaAssetIds = %#v, want [clip_main poster_main]", media.MediaAssetIDs)
	}
}

func TestValidateImportedPostMediaBindingsRejectsNullUnknownAndPrivateDelivery(t *testing.T) {
	base := PostDoc{
		PostRef: "posts/video/production/public/1",
		Assets: []AssetManifestItem{{
			AssetID:    "clip_main",
			Kind:       "video",
			MimeType:   "video/mp4",
			AccessMode: MediaDeliveryAccessModePublic,
			CDNURL:     "https://cdn.example.test/media/video/s/clip_main/v1/source.mp4",
		}},
	}
	if err := ValidateImportedPostMediaBindings([]PostDoc{base}, "production"); err != nil {
		t.Fatalf("valid explicit public MP4 must pass: %v", err)
	}

	tests := []struct {
		name   string
		mutate func(*PostDoc)
		want   string
	}{
		{
			name:   "null accessMode",
			mutate: func(post *PostDoc) { post.Assets[0].AccessMode = "" },
			want:   "accessMode must be public",
		},
		{
			name:   "unknown accessMode",
			mutate: func(post *PostDoc) { post.Assets[0].AccessMode = "private" },
			want:   "accessMode must be public",
		},
		{
			name:   "retired private delivery",
			mutate: func(post *PostDoc) { post.Assets[0].AccessMode = "signed_grant" },
			want:   "accessMode must be public",
		},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			post := base
			post.Assets = append([]AssetManifestItem(nil), base.Assets...)
			test.mutate(&post)
			err := ValidateImportedPostMediaBindings([]PostDoc{post}, "production")
			if err == nil || !strings.Contains(err.Error(), test.want) {
				t.Fatalf("want %q rejection, got %v", test.want, err)
			}
		})
	}
}

func TestValidateImportedPostMediaBindingsAcceptsExplicitPublicAndRejectsClassMismatch(t *testing.T) {
	post := PostDoc{
		PostRef: "posts/image/production/public/1",
		Assets: []AssetManifestItem{{
			AssetID:    "cover",
			Kind:       "image",
			MimeType:   "image/jpeg",
			AccessMode: MediaDeliveryAccessModePublic,
			CDNURL:     "https://cdn.example.test/media/image/s/asset/cover/v1/source.jpg",
		}},
	}
	for _, retired := range []string{"research", "commercial"} {
		if err := ValidateImportedPostMediaBindings([]PostDoc{post}, retired); err == nil {
			t.Fatalf("retired releaseClass %q must fail closed", retired)
		}
	}
	if err := ValidateImportedPostMediaBindings([]PostDoc{post}, "production"); err != nil {
		t.Fatalf("explicit public production binding must pass (DEC-041): %v", err)
	}
	if err := ValidateImportedPostMediaBindings([]PostDoc{post}, ""); err == nil ||
		!strings.Contains(err.Error(), "releaseClass must be production") {
		t.Fatalf("missing releaseClass must fail closed, got %v", err)
	}
}

func TestBindPostAuthorSnapshotsProjectsAvatarAssetIdentity(t *testing.T) {
	posts := []PostDoc{
		{PostRef: "posts/article/体验/带头像/1", AuthorID: "builtin_with_avatar"},
		{PostRef: "posts/article/体验/无头像/1", AuthorID: "builtin_without_avatar"},
	}
	err := BindPostAuthorSnapshots(posts, map[string]CreatorAuthorSnapshot{
		"builtin_with_avatar": {
			AuthorID:      "builtin_with_avatar",
			DisplayName:   "旅行博主",
			AvatarURL:     "media/objects/sha256/ee/ff/avatar.webp",
			AvatarAssetID: "avatar_travel_blogger",
		},
		"builtin_without_avatar": {
			AuthorID:    "builtin_without_avatar",
			DisplayName: "无头像作者",
		},
	})
	if err != nil {
		t.Fatalf("bind post author snapshots: %v", err)
	}
	if posts[0].AuthorAvatarAssetID != "avatar_travel_blogger" {
		t.Fatalf("authorAvatarAssetId = %q, want creator profile avatarAsset.assetId", posts[0].AuthorAvatarAssetID)
	}
	if posts[1].AuthorAvatarAssetID != "" {
		t.Fatalf("author without avatar must keep avatarAssetId absent, got %q", posts[1].AuthorAvatarAssetID)
	}
}

// 头像交付字段的缺席语义：无头像或未声明 releaseClass 时写 BSON null（缺席），
// 覆盖旧 release 残留值；在场时 assetId 与 accessMode 成对可读。
func TestApplyImportedAuthorAvatarDeliveryFields(t *testing.T) {
	withAvatar := bson.M{}
	ApplyImportedAuthorAvatarDeliveryFields(
		withAvatar,
		PostDoc{AuthorAvatarAssetID: "avatar_travel_blogger"},
		"signed_grant",
	)
	if withAvatar["authorAvatarAssetId"] != "avatar_travel_blogger" ||
		withAvatar["authorAvatarAccessMode"] != "signed_grant" {
		t.Fatalf("avatar delivery binding drifted: %#v", withAvatar)
	}

	withoutAvatar := bson.M{
		"authorAvatarAssetId":    "stale_asset",
		"authorAvatarAccessMode": "signed_grant",
	}
	ApplyImportedAuthorAvatarDeliveryFields(withoutAvatar, PostDoc{}, "signed_grant")
	if withoutAvatar["authorAvatarAssetId"] != nil || withoutAvatar["authorAvatarAccessMode"] != nil {
		t.Fatalf("absent avatar must overwrite stale binding with null: %#v", withoutAvatar)
	}

	undeclaredClass := bson.M{}
	ApplyImportedAuthorAvatarDeliveryFields(
		undeclaredClass,
		PostDoc{AuthorAvatarAssetID: "avatar_travel_blogger"},
		MediaDeliveryAccessModeForReleaseClass(""),
	)
	if undeclaredClass["authorAvatarAssetId"] != "avatar_travel_blogger" ||
		undeclaredClass["authorAvatarAccessMode"] != nil {
		t.Fatalf("undeclared releaseClass must keep accessMode absent: %#v", undeclaredClass)
	}
}
