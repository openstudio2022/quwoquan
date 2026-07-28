package runtimemedia

import (
	"encoding/json"
	"strings"
	"testing"
)

func TestBuildAvatarGroupAssetRefProjectsPublicDeliveryReference(t *testing.T) {
	ref := BuildAvatarGroupAssetRef(
		"conversation_001",
		"ga_conversation_001_v1",
		1,
		"abcdef1234567890",
		"https://cdn.example.com",
	)

	if ref.AssetKind != AssetKindAvatarGroup {
		t.Fatalf("expected avatar group kind, got %s", ref.AssetKind)
	}
	if ref.ObjectKey == "" {
		t.Fatal("expected internal storage key")
	}
	delivery := ref.DeliveryReference()
	want := "https://cdn.example.com/media/avatar/s/conversation/conversation_001/v1/abcdef1234567890.png?v=1"
	if delivery.DeliveryURI != want {
		t.Fatalf("unexpected delivery URI: %s", delivery.DeliveryURI)
	}
	if delivery.PublicSliceKey != "media/avatar/s/conversation/conversation_001/v1/abcdef1234567890.png" {
		t.Fatalf("unexpected public slice key: %s", delivery.PublicSliceKey)
	}
}

func TestInternalAssetRefDoesNotSerializeStorageKey(t *testing.T) {
	ref := BuildAvatarGroupAssetRef(
		"conversation_001",
		"ga_conversation_001_v1",
		1,
		"abcdef1234567890",
		"https://cdn.example.com",
	)
	encoded, err := json.Marshal(ref)
	if err != nil {
		t.Fatalf("marshal: %v", err)
	}
	if strings.Contains(string(encoded), "objectKey") || strings.Contains(string(encoded), "abcdef1234567890") {
		t.Fatalf("internal asset ref leaked storage data: %s", encoded)
	}
}

func TestBuildAssetURLEmptyOrInvalidBaseReturnsEmpty(t *testing.T) {
	if got := BuildAssetURL("", "media/avatar/s/conversation/c_1/v2/hash.png", 2); got != "" {
		t.Fatalf("expected empty URL, got %s", got)
	}
	if got := BuildAssetURL("cdn.example.com", "media/avatar/s/conversation/c_1/v2/hash.png", 2); got != "" {
		t.Fatalf("expected empty URL for bare host, got %s", got)
	}
}

func TestNormalizeMediaCDNBaseRequiresHTTPS(t *testing.T) {
	if got := NormalizeMediaCDNBase("https://cdn.example.com/"); got != "https://cdn.example.com" {
		t.Fatalf("unexpected %q", got)
	}
	if got := NormalizeMediaCDNBase("http://cdn.example.com"); got != "" {
		t.Fatalf("expected non-HTTPS base rejection, got %q", got)
	}
	if got := BuildPublicMediaURL("https://cdn.example.com", "media/avatar/a.png", 1); got != "" {
		t.Fatalf("unexpected non-canonical key URL %q", got)
	}
}

func TestBuildPublicMediaURLRejectsCASObjectKey(t *testing.T) {
	casKeys := []string{
		"media/objects/sha256/aa/bb/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa.jpg",
		"media/objects/sha256/0a/a5/0aa58a9a6d6061e8f28f86b88662a053bd3803e1215bc73325e8be6fce655d1d.png",
		"/media/objects/sha256/cc/dd/cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc.mp4",
	}
	for _, key := range casKeys {
		if got := BuildPublicMediaURL("https://cdn.example.com", key, 1); got != "" {
			t.Fatalf("expected CAS object key rejection for %q, got %q", key, got)
		}
	}
	if got := BuildPublicMediaURL(
		"https://cdn.example.com",
		"media/image/s/archived-image/post/fixture_photo_001/v1/cover.png",
		2,
	); got != "https://cdn.example.com/media/image/s/archived-image/post/fixture_photo_001/v1/cover.png?v=2" {
		t.Fatalf("unexpected valid public slice URL %q", got)
	}
}

func TestBuildContentMediaPublicSliceKeyUsesAssetIdentityNotCASKey(t *testing.T) {
	got := BuildContentMediaPublicSliceKey(
		"video",
		"mas_video_001",
		3,
		"video/mp4",
	)
	const want = "media/video/s/asset/mas_video_001/v3/source.mp4"
	if got != want {
		t.Fatalf("unexpected content public slice key: got %q want %q", got, want)
	}
	if strings.Contains(got, "objects") || strings.Contains(got, "sha256") {
		t.Fatalf("public slice key must not expose a CAS path: %q", got)
	}
	if got := BuildContentMediaPublicSliceKey(
		"image",
		"mas bad",
		1,
		"image/jpeg",
	); got != "" {
		t.Fatalf("invalid asset identity must not produce a public slice: %q", got)
	}
	unicodeAsset := BuildContentMediaPublicSliceKey(
		"image",
		"杭州西湖_cover_三潭印月",
		1,
		"image/jpeg",
	)
	if !strings.HasPrefix(unicodeAsset, "media/image/s/asset/unicode-") ||
		!strings.HasSuffix(unicodeAsset, "/v1/source.jpg") {
		t.Fatalf("historical unicode asset must receive a stable public path: %q", unicodeAsset)
	}
	if got := BuildContentMediaPublicSliceKey(
		"avatar",
		"creator_avatar_001",
		1,
		"image/png",
	); got != "media/avatar/s/asset/creator_avatar_001/v1/source.png" {
		t.Fatalf("avatar public slice kind drift: %q", got)
	}
}
