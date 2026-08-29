// spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-016
//
// data release importer 的逐媒体交付绑定（DEC-033，OPEN-015 缺陷回归）：
// mediaItems 必须用 canonical BSON 键（mediaAssetId/mediaAssetVersion）落库、
// 按 releaseClass 写 accessMode、为 video poster 写配对 coverAssetId，且
// posts.mediaAssetIds 覆盖含 poster 在内的全部媒体资产标识；作者头像的
// avatarAssetId 绑定自 release creator profile，禁止以 authorId 冒充。
package releaseimport_test

import (
	"testing"

	"go.mongodb.org/mongo-driver/v2/bson"

	postmodel "quwoquan_service/services/content-service/generated/content/post/contract/model"
	. "quwoquan_service/services/content-service/internal/content/post/infrastructure/releaseimport"
)

func TestMediaDeliveryAccessModeForReleaseClass(t *testing.T) {
	cases := []struct {
		releaseClass string
		want         string
	}{
		{releaseClass: "research", want: "signed_grant"},
		{releaseClass: "commercial", want: "public"},
		// 未声明/未知类别缺席，不得由 importer 造值。
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

func TestImportedMediaFieldsOmitAccessModeWhenReleaseClassUndeclared(t *testing.T) {
	media := ImportedMediaFields(videoWithPosterAssets(), MediaDeliveryAccessModeForReleaseClass(""))
	for index, item := range media.MediaItems {
		if _, exists := item["accessMode"]; exists {
			t.Fatalf("mediaItems[%d] must keep accessMode absent for undeclared releaseClass: %#v", index, item)
		}
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
