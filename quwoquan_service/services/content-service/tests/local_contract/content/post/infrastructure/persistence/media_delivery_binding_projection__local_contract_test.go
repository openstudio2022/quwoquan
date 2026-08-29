// spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-016
//
// Mongo 读投影的媒体交付绑定（DEC-033，OPEN-015 App 消费面缺口）：feed 与
// detail slice 两路都必须把逐媒体 mediaAssetId/accessMode/coverAssetId 与作者
// 头像的 authorAvatarAssetId/authorAvatarAccessMode 输出为 canonical wire 键；
// 缺席（旧文档无字段）时保持省略键，不塌陷为零值也不造值。
package persistence_test

import (
	"encoding/json"
	"strings"
	"testing"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"

	. "quwoquan_service/services/content-service/internal/content/post/infrastructure/persistence"
	postports "quwoquan_service/services/content-service/internal/content/post/domain/ports"
)

func TestFeedAndDetailProjectionsCarryAuthorAvatarDeliveryBinding(t *testing.T) {
	for _, projection := range []struct {
		name   string
		fields bson.D
	}{
		{name: "PostFeedProjection", fields: PostFeedProjection()},
		{name: "PostDetailProjection", fields: PostDetailProjection()},
	} {
		for _, field := range []string{"authorAvatarAssetId", "authorAvatarAccessMode"} {
			if got := bsonFieldValue(projection.fields, field); got != 1 {
				t.Fatalf("%s %q = %#v, want explicit inclusion", projection.name, field, got)
			}
		}
	}
}

func TestPostFeedItemSliceDecodesPerMediaDeliveryBinding(t *testing.T) {
	raw, err := bson.Marshal(bson.D{
		{Key: "_id", Value: "data_post_media_binding"},
		{Key: "authorId", Value: "builtin_travel_blogger"},
		{Key: "authorAvatarUrlSnapshot", Value: "media/objects/sha256/ee/ff/avatar.webp"},
		{Key: "authorAvatarAssetId", Value: "avatar_travel_blogger"},
		{Key: "authorAvatarAccessMode", Value: "signed_grant"},
		{Key: "contentType", Value: "video"},
		{Key: "mediaItems", Value: bson.A{
			bson.D{
				{Key: "kind", Value: "video"},
				{Key: "mediaAssetId", Value: "clip_main"},
				{Key: "mediaAssetVersion", Value: int64(3)},
				{Key: "accessMode", Value: "signed_grant"},
				{Key: "url", Value: "media/objects/sha256/aa/bb/clip.mp4"},
				{Key: "coverUrl", Value: "media/objects/sha256/cc/dd/poster.webp"},
				{Key: "coverAssetId", Value: "poster_main"},
			},
		}},
		{Key: "createdAt", Value: time.Date(2026, time.August, 20, 12, 0, 0, 0, time.UTC)},
		{Key: "updatedAt", Value: time.Date(2026, time.August, 20, 12, 0, 0, 0, time.UTC)},
	})
	if err != nil {
		t.Fatalf("marshal feed fixture: %v", err)
	}

	var slice postports.PostFeedItemSlice
	if err := bson.Unmarshal(raw, &slice); err != nil {
		t.Fatalf("decode PostFeedItemSlice: %v", err)
	}
	if slice.AuthorAvatarAssetID != "avatar_travel_blogger" ||
		slice.AuthorAvatarAccessMode != "signed_grant" {
		t.Fatalf("author avatar delivery binding is absent: %+v", slice)
	}
	if len(slice.MediaItems) != 1 {
		t.Fatalf("mediaItems = %+v, want one item", slice.MediaItems)
	}
	item := slice.MediaItems[0]
	if item.MediaAssetID != "clip_main" || item.MediaAssetVersion != 3 ||
		item.AccessMode != "signed_grant" || item.CoverAssetID != "poster_main" {
		t.Fatalf("per-media delivery binding is absent: %+v", item)
	}

	// wire 键名必须是契约 canonical 名。
	serialized, err := json.Marshal(slice)
	if err != nil {
		t.Fatalf("marshal feed slice: %v", err)
	}
	for _, key := range []string{
		`"authorAvatarAssetId":"avatar_travel_blogger"`,
		`"authorAvatarAccessMode":"signed_grant"`,
		`"mediaAssetId":"clip_main"`,
		`"accessMode":"signed_grant"`,
		`"coverAssetId":"poster_main"`,
	} {
		if !strings.Contains(string(serialized), key) {
			t.Fatalf("feed wire lacks %s: %s", key, serialized)
		}
	}
}

// 旧文档（导入修复前）没有交付绑定字段：typed 读取输出缺席（wire 省略键），
// 不得以 authorId 或零值冒充媒体资产标识。
func TestPostFeedItemSliceKeepsDeliveryBindingAbsentForLegacyDocuments(t *testing.T) {
	raw, err := bson.Marshal(bson.D{
		{Key: "_id", Value: "data_post_legacy"},
		{Key: "authorId", Value: "builtin_travel_blogger"},
		{Key: "contentType", Value: "image"},
		{Key: "mediaItems", Value: bson.A{
			bson.D{
				{Key: "kind", Value: "image"},
				{Key: "url", Value: "https://img.example.com/legacy.jpg"},
			},
		}},
	})
	if err != nil {
		t.Fatalf("marshal legacy fixture: %v", err)
	}

	var slice postports.PostFeedItemSlice
	if err := bson.Unmarshal(raw, &slice); err != nil {
		t.Fatalf("decode legacy PostFeedItemSlice: %v", err)
	}
	serialized, err := json.Marshal(slice)
	if err != nil {
		t.Fatalf("marshal legacy feed slice: %v", err)
	}
	for _, forbidden := range []string{
		"authorAvatarAssetId",
		"authorAvatarAccessMode",
		"accessMode",
		"coverAssetId",
	} {
		if strings.Contains(string(serialized), forbidden) {
			t.Fatalf("legacy document must keep %q absent on wire: %s", forbidden, serialized)
		}
	}
}

func TestPostDetailSliceCarriesAuthorAvatarDeliveryBinding(t *testing.T) {
	raw, err := bson.Marshal(bson.D{
		{Key: "_id", Value: "data_post_detail_binding"},
		{Key: "authorId", Value: "builtin_travel_blogger"},
		{Key: "authorAvatarAssetId", Value: "avatar_travel_blogger"},
		{Key: "authorAvatarAccessMode", Value: "signed_grant"},
		{Key: "contentType", Value: "video"},
		{Key: "status", Value: "published"},
		{Key: "visibility", Value: "public"},
		{Key: "mediaItems", Value: bson.A{
			bson.D{
				{Key: "kind", Value: "video"},
				{Key: "mediaAssetId", Value: "clip_main"},
				{Key: "accessMode", Value: "signed_grant"},
				{Key: "url", Value: "media/objects/sha256/aa/bb/clip.mp4"},
				{Key: "coverAssetId", Value: "poster_main"},
			},
		}},
		{Key: "createdAt", Value: time.Date(2026, time.August, 20, 12, 0, 0, 0, time.UTC)},
		{Key: "updatedAt", Value: time.Date(2026, time.August, 20, 12, 0, 0, 0, time.UTC)},
	})
	if err != nil {
		t.Fatalf("marshal detail fixture: %v", err)
	}

	var detail postports.PostDetailSlice
	if err := bson.Unmarshal(raw, &detail); err != nil {
		t.Fatalf("decode PostDetailSlice: %v", err)
	}
	if detail.AuthorAvatarAssetID != "avatar_travel_blogger" ||
		detail.AuthorAvatarAccessMode != "signed_grant" {
		t.Fatalf("detail author avatar delivery binding is absent: %+v", detail)
	}
	if len(detail.MediaItems) != 1 ||
		detail.MediaItems[0].AccessMode != "signed_grant" ||
		detail.MediaItems[0].CoverAssetID != "poster_main" {
		t.Fatalf("detail per-media delivery binding is absent: %+v", detail.MediaItems)
	}

	serialized, err := json.Marshal(detail)
	if err != nil {
		t.Fatalf("marshal detail slice: %v", err)
	}
	for _, key := range []string{
		`"authorAvatarAssetId":"avatar_travel_blogger"`,
		`"authorAvatarAccessMode":"signed_grant"`,
	} {
		if !strings.Contains(string(serialized), key) {
			t.Fatalf("detail wire lacks %s: %s", key, serialized)
		}
	}
}
